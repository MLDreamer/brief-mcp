"""MCP tools: get_crm_context + enrich_brief_with_crm.

Connects to HubSpot CRM via the HubSpot REST API.
Configure HUBSPOT_API_KEY in .env to enable.
"""

import asyncio
import logging
from datetime import datetime, timezone

from fastmcp import FastMCP

from ..integrations.google_calendar import get_upcoming_events
from ..integrations.hubspot import get_crm_context as _hubspot_crm_context
from ..models import Meeting, MeetingBrief
from ._shared import _find_meeting, _research_attendee_with_cache

logger = logging.getLogger(__name__)


def register_crm_tools(mcp: FastMCP) -> None:
    """Register CRM MCP tools onto the server."""

    @mcp.tool()
    async def get_crm_context(
        name: str,
        email: str = "",
        company: str = "",
    ) -> str:
        """Look up a person's record in HubSpot CRM.

        Returns deal stage, last contact date, lifecycle stage, associated deals,
        and interaction notes for the contact. Use before sales, partner, or customer
        meetings to surface deal context. Do not call if HUBSPOT_API_KEY is not set —
        returns a "not configured" message rather than an error.

        Read-only. Does not create or modify CRM records.

        Args:
            name: Full name of the contact to search (required).
            email: Email address — greatly improves match precision when provided.
                   Recommended whenever the attendee's email is known.
            company: Company name to disambiguate contacts with common names (optional).

        Returns:
            Formatted text summary with deal stage, lifecycle, last contact, and notes.
            Returns a plain-text message (not an error) if no HubSpot record exists,
            if HUBSPOT_API_KEY is not configured, or if the contact is not found.
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
        """Generate a meeting brief that includes HubSpot CRM deal context.

        Combines three data sources in one call: Google Calendar (meeting lookup),
        web research (attendee profiles), and HubSpot CRM (deal stage, lifecycle,
        notes). Best for sales meetings, partner reviews, and customer calls.
        Use get_meeting_brief instead if CRM data is not needed or HUBSPOT_API_KEY
        is not set — enrich_brief_with_crm gracefully omits the CRM section when
        the key is absent.

        Read-only. Does not modify calendar, CRM records, or local memory.
        Attendee profiles and CRM lookups are not cached between calls.

        Args:
            meeting_title: Partial or full Google Calendar meeting title
                           (case-insensitive substring match, 24-hour window).

        Returns:
            Formatted brief card followed by a CRM CONTEXT section per attendee.
            The CRM section is omitted if HUBSPOT_API_KEY is not configured or no
            HubSpot records are found. Returns a plain-text error if the meeting
            title does not match any event in the next 24 hours.
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
        _CRM_SKIP = ("not configured", "No CRM record", "CRM error", "Error:", "Too Many Requests")
        for crm_text in crm_results:
            if crm_text and not any(pat in crm_text for pat in _CRM_SKIP):
                has_crm_data = True
                crm_section_lines.append(crm_text)

        if has_crm_data:
            crm_block = (
                f"\n{sep}\n"
                "  CRM CONTEXT (HubSpot)\n"
                f"{sep}\n"
                + "\n\n".join(f"  {line}" for block in crm_section_lines for line in block.splitlines())
            )
            sep_line = "=" * 60
            if card.endswith(sep_line):
                card = card[: -len(sep_line)]
            card = card.rstrip()
            card = card + crm_block + "\n" + sep_line
        else:
            card += (
                "\n\n  [CRM: No HubSpot records found for attendees. "
                "Set HUBSPOT_API_KEY in .env to enable CRM enrichment.]"
            )

        return card
