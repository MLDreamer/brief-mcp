"""Web search integration for attendee research.

Primary: Brave Search API (set BRAVE_API_KEY env var).
Fallback: DuckDuckGo HTML scraper via httpx (no key required).

Runs 3 searches in parallel per person:
  1. "{name} {company}" — general bio
  2. "{name} LinkedIn" — professional profile
  3. "{company} news 2026" — company news
"""

import asyncio
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional

import httpx
from dotenv import load_dotenv

from ..models import PersonProfile

load_dotenv()

logger = logging.getLogger(__name__)

BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")
BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
DDG_URL = "https://html.duckduckgo.com/html/"

# Shared async HTTP client (connection-pooled)
_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0),
            headers={"User-Agent": "brief-mcp/0.1.0 (meeting prep assistant)"},
            follow_redirects=True,
        )
    return _client


async def _brave_search(query: str, count: int = 5) -> list[dict]:
    """Perform a Brave Search API request. Returns list of result dicts."""
    client = _get_client()
    try:
        resp = await client.get(
            BRAVE_SEARCH_URL,
            params={"q": query, "count": count, "search_lang": "en"},
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": BRAVE_API_KEY,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("web", {}).get("results", [])
        return [{"title": r.get("title", ""), "snippet": r.get("description", ""), "url": r.get("url", "")} for r in results]
    except httpx.HTTPStatusError as exc:
        logger.warning("Brave Search HTTP error for '%s': %s", query, exc.response.status_code)
        return []
    except Exception as exc:
        logger.warning("Brave Search failed for '%s': %s", query, exc)
        return []


async def _ddg_search(query: str, max_results: int = 5) -> list[dict]:
    """DuckDuckGo HTML fallback search. Parses the HTML result page."""
    client = _get_client()
    try:
        resp = await client.post(
            DDG_URL,
            data={"q": query, "b": "", "kl": "us-en"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        html = resp.text

        # Lightweight parse — extract result snippets without a heavy HTML parser
        results: list[dict] = []

        # Match result blocks: <a class="result__a" ...>TITLE</a> + snippet
        title_pattern = re.compile(r'class="result__a"[^>]*>(.*?)</a>', re.DOTALL)
        snippet_pattern = re.compile(r'class="result__snippet"[^>]*>(.*?)</span>', re.DOTALL)
        url_pattern = re.compile(r'class="result__url"[^>]*>(.*?)</a>', re.DOTALL)

        titles = [re.sub(r"<[^>]+>", "", t).strip() for t in title_pattern.findall(html)]
        snippets = [re.sub(r"<[^>]+>", "", s).strip() for s in snippet_pattern.findall(html)]
        urls = [re.sub(r"<[^>]+>", "", u).strip() for u in url_pattern.findall(html)]

        for i in range(min(max_results, len(titles))):
            results.append(
                {
                    "title": titles[i] if i < len(titles) else "",
                    "snippet": snippets[i] if i < len(snippets) else "",
                    "url": urls[i] if i < len(urls) else "",
                }
            )
        return results
    except Exception as exc:
        logger.warning("DuckDuckGo search failed for '%s': %s", query, exc)
        return []


async def _search(query: str, count: int = 5) -> list[dict]:
    """Route to Brave (if key set) or DuckDuckGo."""
    if BRAVE_API_KEY:
        return await _brave_search(query, count)
    return await _ddg_search(query, count)


def _extract_role_company(snippets: list[str]) -> tuple[Optional[str], Optional[str]]:
    """Heuristically extract role and company from search snippets."""
    role_patterns = [
        re.compile(r"\b(CEO|CTO|CFO|COO|VP|SVP|EVP|President|Director|Head of|Chief|Founder|Co-Founder|Partner|Manager|Lead|Principal|Senior|Staff)\b[^.]{0,50}", re.IGNORECASE),
    ]
    company_pattern = re.compile(r"\bat\s+([A-Z][A-Za-z0-9&\s,\.]{2,40})", re.UNICODE)

    role: Optional[str] = None
    company: Optional[str] = None

    for snippet in snippets:
        if not role:
            for pattern in role_patterns:
                m = pattern.search(snippet)
                if m:
                    role = m.group(0).strip().rstrip(",.")
                    break
        if not company:
            m = company_pattern.search(snippet)
            if m:
                company = m.group(1).strip().rstrip(",.")

        if role and company:
            break

    return role, company


def _snippets_to_bullets(results: list[dict], max_items: int = 4) -> list[str]:
    """Convert search result dicts into readable bullet strings."""
    bullets: list[str] = []
    for r in results[:max_items]:
        title = r.get("title", "").strip()
        snippet = r.get("snippet", "").strip()
        if snippet:
            bullets.append(f"{title}: {snippet}" if title else snippet)
        elif title:
            bullets.append(title)
    return bullets


async def research_person(name: str, company: str = "") -> PersonProfile:
    """Research a person and return a structured PersonProfile.

    Runs 3 parallel searches: general bio, LinkedIn, and company news.
    Uses Brave Search if BRAVE_API_KEY is set, else falls back to DuckDuckGo.
    """
    logger.info("Researching '%s' at '%s'", name, company or "(no company)")

    year = datetime.now().year
    queries = [
        f'"{name}" {company}'.strip(),
        f'"{name}" LinkedIn professional',
        f'"{company}" news {year}' if company else f'"{name}" news {year}',
    ]

    # Parallel search
    general_results, linkedin_results, news_results = await asyncio.gather(
        _search(queries[0], 5),
        _search(queries[1], 3),
        _search(queries[2], 4),
    )

    # Build profile from results
    all_snippets = [r.get("snippet", "") for r in general_results + linkedin_results if r.get("snippet")]
    role, detected_company = _extract_role_company(all_snippets)

    # LinkedIn summary from top LinkedIn result
    linkedin_summary: Optional[str] = None
    for r in linkedin_results:
        url = r.get("url", "")
        snippet = r.get("snippet", "")
        if "linkedin.com" in url and snippet:
            linkedin_summary = snippet[:300]
            break

    # Background: best general snippet
    background: Optional[str] = None
    for r in general_results:
        snippet = r.get("snippet", "")
        if snippet and name.split()[0].lower() in snippet.lower():
            background = snippet[:400]
            break
    if not background and general_results:
        background = general_results[0].get("snippet", "")[:400] or None

    # Recent personal news bullets
    recent_news = _snippets_to_bullets(general_results[1:], 3)

    # Company news bullets
    company_news = _snippets_to_bullets(news_results, 4)

    # Collect source URLs
    sources = list(
        {
            r["url"]
            for r in (general_results + linkedin_results + news_results)
            if r.get("url")
        }
    )[:6]

    profile = PersonProfile(
        name=name,
        current_role=role,
        company=detected_company or company or None,
        linkedin_summary=linkedin_summary,
        recent_news=recent_news,
        company_news=company_news,
        background=background,
        research_timestamp=datetime.now(timezone.utc),
        research_sources=sources,
    )

    logger.info(
        "Research complete for '%s': role=%s company=%s",
        name,
        profile.current_role or "unknown",
        profile.company or "unknown",
    )
    return profile


async def close_client() -> None:
    """Close the shared HTTP client (call on shutdown)."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
