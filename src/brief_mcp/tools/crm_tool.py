"""MCP tools: get_crm_context + enrich_brief_with_crm.

Connects to HubSpot CRM via the HubSpot REST API.
Configure HUBSPOT_API_KEY in .env to enable.
"""

import asyncio
import logging
from datetime import datetime, timezone

from fastmcp import FastMCP

from ..cache import get_cached_profile, set_cached_profile
from ..integrations.google_calendar import get_upcoming_events
from ..integrations.hubspot import get_crm_context as _hubspot_crm_context
from ..integrations.web_search import research_person
from ..models import Meeting, MeetingBrief

logger = logging.getLogger(__name__)


def _find_meeting(meetings: list[Meeting], title: str = "", meeting_id: str = "") -> Meeting | None:
    """Find a meeting by partial title match or exact ID."""
    if meeting_id:
        for m in meetings:
            if m.id == meeting_id:
                return m
    if title:
        title_lower = title.lower()
        for m in meetings:
            if m.title.lower() == title_lower:
                return m
        for m in meetings:
            if title_lower in m.title.lower():
                return m
    return None


async def _research_attendee_with_cache(name: str, company: str = "") -> object:
    """Research a single attendee, using cache if available."""
    cached = get_cached_profile(name, company)
    if cached is not None:
        return cached
    try:
        profile = await research_person(name, company)
        set_cached_profile(profile)
        return profile
    except Exception as exc:
        logger.warning("Research failed for '%s': %s", name, exc)
        from ..models import PersonProfile
        return PersonProfile(name=name, company=company or None)


def register_crm_tools(mcp: FastMCP) -> None:
    """Register CRM MCP tools onto the server."""

    @mcp.tool()
    async def get_crm_context(
        name: str,
        email: str = "",
        company: str = "",
    ) -> str:
        """Look up a person in HubSpot CRM.

        Returns deal stage, last contact date, lifecycle stage, associated deals,
        and interaction notes for the given person.

        Set HUBSPOT_API_KEY in .env to enable CRM integration.

        Args:
            name: Full name of the person to look up (required).
            email: Email address for a more precise match (optional but recommended).
            company: Company name to narrow the search (optional).

        Returns:
            A formatted CRM summary string, or a message if no record is found.
        """
        if not name.strip():
            return "Please provide a name to look up in HubSpot."

        try:
            return await _hubspot_crm_context(name=name, email=email, company=company)
        except Exception as exc:
            logger.error("get_crm_context failed for '%s': %s", name, exc)
            return f"CRM lookup failed for {name}: {exc}"

    @mcp.tool()
    async def enrich_brief_with_crm(meeting_title: str) -> str:
        """Generate a meeting brief enriched with HubSpot CRM data.

        Combines Google Calendar lookup + parallel web research on attendees +
        HubSpot CRM deal context for each attendee.  Best used for sales meetings,
        partner reviews, and customer calls where CRM context matters.

        Set HUBSPOT_API_KEY in .env to unlock CRM enrichment.

        Args:
            meeting_title: Partial or full meeting title to look up on Google Calendar.

        Returns:
            A formatted brief card with an appended CRM context section,
            or an error message if the meeting is not found.
        """
        if not meeting_title.strip():
            return (
                "Please provide a meeting_title. "
                "Use get_upcoming_meetings first to see what's on your calendar."
            )

        # 1. Fetch calendar
        try:
            meetings = await get_upcoming_events(24)
        except Exception as exc:
            logger.error("enrich_brief_with_crm: calendar fetch failed: %s", exc)
            return f"Failed to fetch calendar: {exc}"

        meeting = _find_meeting(meetings, title=meeting_title)
        if meeting is None:
            available = ", ".join(f'"{m.title}"' for m in meetings[:5]) or "none"
            return (
                f"Meeting not found matching '{meeting_title}'. "
                f"Upcoming meetings: {available}. "
                "Try get_upcoming_meetings for the full list."
            )

        # 2. Research attendees in parallel
        attendees_to_research = (meeting.external_attendees or meeting.attendees)[:8]
        if attendees_to_research:
            tasks = [
                _research_attendee_with_cache(a.display_name(), "")
                for a in attendees_to_research
            ]
            profiles = list(await asyncio.gather(*tasks))
        else:
            profiles = []

        # 3. Fetch CRM context for each attendee in parallel
        crm_tasks = [
            _hubspot_crm_context(
                name=a.display_name(),
                email=a.email or "",
                company=getattr(p, "company", "") or "",
            )
            for a, p in zip(attendees_to_research, profiles)
        ]
        crm_results: list[str] = list(await asyncio.gather(*crm_tasks))

        # 4. Build standard brief
        from ..tools.brief_tool import _generate_talking_points, _generate_watch_outs

        talking_points = _generate_talking_points(meeting, profiles)
        watch_outs = _generate_watch_outs(meeting, profiles)
        brief = MeetingBrief(
            meeting=meeting,
            attendee_profiles=profiles,
            talking_points=talking_points,
            watch_outs=watch_outs,
            generated_at=datetime.now(timezone.utc),
        )
        card = brief.format_card()

        # 5. Append CRM section
        crm_section_lines: list[str] = []
        sep = "-" * 60
        has_crm_data = False
        for crm_text in crm_results:
            if crm_text and "not configured" not in crm_text and "No CRM record" not in crm_text:
                has_crm_data = True
                crm_section_lines.append(crm_text)

        if has_crm_data:
            crm_block = (
                f"\n{sep}\n"
                "  CRM CONTEXT (HubSpot)\n"
                f"{sep}\n"
                + "\n\n".join(f"  {line}" for block in crm_section_lines for line in block.splitlines())
            )
            card = card.rstrip("=" * 60).rstrip() + crm_block + "\n" + "=" * 60
        else:
            card += (
                "\n\n  [CRM: No HubSpot records found for attendees. "
                "Set HUBSPOT_API_KEY in .env to enable CRM enrichment.]"
            )

        return card
