"""MCP tool: research_attendee — web search + news for a person and company."""

import logging

from fastmcp import FastMCP

from ..cache import get_cached_profile, set_cached_profile
from ..integrations.web_search import research_person

logger = logging.getLogger(__name__)


def register_research_tools(mcp: FastMCP) -> None:
    """Register research-related MCP tools onto the server."""

    @mcp.tool()
    async def research_attendee(name: str, company: str = "", context: str = "") -> dict:
        """Research a person's professional background, role, and recent news.

        Use before any meeting where you need context on an attendee. Prefer
        brief_all_today or get_meeting_brief when researching all attendees for a
        meeting — they batch-research in parallel. Call this tool directly only when
        researching a single person outside of a calendar flow.

        Writes the profile to a 60-minute in-memory cache. Subsequent calls for the
        same name+company pair return the cached result instantly with cached=true.
        If all web searches fail (rate limit, network error), returns an empty profile
        with no role or sources rather than raising an error — check research_sources
        to confirm results were found.

        Args:
            name: Full name of the person (required). More specific is better —
                  "Jane Smith" outperforms "Jane".
            company: Current employer or organization. Strongly recommended for common
                     names; significantly narrows search results.
            context: Any background you already know (optional). Used to fill the
                     background field if web research finds nothing.

        Returns:
            Profile dict with: name, current_role, company, background,
            linkedin_summary, recent_news (list), company_news (list),
            research_timestamp (ISO), research_sources (list of URLs), cached (bool).
            Returns {error: ...} only if name is blank.
        """
        if not name or not name.strip():
            return {"error": "name is required"}

        name = name.strip()
        company = company.strip()

        # Check cache first
        cached = get_cached_profile(name, company)
        if cached is not None:
            logger.info("Cache hit for '%s'", name)
            result = cached.model_dump(mode="json")
            result["cached"] = True
            return result

        try:
            profile = await research_person(name, company)
        except Exception as exc:
            logger.error("research_attendee error for '%s': %s", name, exc)
            return {
                "name": name,
                "company": company or None,
                "error": f"Research failed: {exc}",
                "recent_news": [],
                "company_news": [],
            }

        # Enrich with any user-provided context
        if context and not profile.background:
            profile.background = context

        set_cached_profile(profile)

        result = profile.model_dump(mode="json")
        result["cached"] = False
        return result
