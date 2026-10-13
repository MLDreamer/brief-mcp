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
        """Research a meeting attendee: current role, company news, and background.

        Results are cached for 60 minutes — repeated calls for the same person
        return instantly without new API requests.

        Args:
            name: Full name of the person to research (required).
            company: Their company or organization (improves accuracy).
            context: Any additional context you know about them (optional).

        Returns:
            A structured profile dict with keys:
              - name, current_role, company
              - background (short bio)
              - linkedin_summary
              - recent_news (list of headlines)
              - company_news (list of company headlines)
              - research_timestamp (ISO datetime)
              - research_sources (list of URLs)
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
