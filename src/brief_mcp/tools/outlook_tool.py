"""MCP tools: get_outlook_meetings + get_outlook_brief.

Reads Outlook/Microsoft 365 calendar via Microsoft Graph API.
Configure AZURE_CLIENT_ID (and optionally AZURE_TENANT_ID) in .env to enable.
"""

import asyncio
import logging
from datetime import datetime, timezone

from fastmcp import FastMCP

from ..integrations.outlook_calendar import get_outlook_events
from ..models import Meeting, MeetingBrief
from ._shared import _find_meeting, _research_attendee_with_cache
from .brief_tool import _generate_talking_points, _generate_watch_outs

logger = logging.getLogger(__name__)


def register_outlook_tools(mcp: FastMCP) -> None:
    """Register Outlook MCP tools onto the server."""

    @mcp.tool()
    async def get_outlook_meetings(hours_ahead: int = 24) -> list[dict]:
        """List upcoming meetings from Outlook / Microsoft 365 calendar.

        Use instead of get_upcoming_meetings when the user's calendar is on
        Microsoft 365 / Exchange rather than Google. Do not call if AZURE_CLIENT_ID
        is not configured — returns an empty list silently.

        On first use, a device-code authentication prompt appears in the server
        terminal. The user must visit the printed URL and enter the code; the token
        is then cached locally for subsequent calls.

        Read-only. Does not modify calendar data or local storage.

        Args:
            hours_ahead: How many hours ahead to look (default 24, max recommended 168).

        Returns:
            List of meeting objects identical in shape to get_upcoming_meetings output
            (id, title, start_time, end_time, duration_minutes, attendees, meeting_url,
            location) plus source="outlook". Returns [] if AZURE_CLIENT_ID is not set
            or no meetings exist in the window.
        """
        try:
            meetings = await get_outlook_events(hours_ahead)
        except Exception as exc:
            logger.error("get_outlook_meetings: fetch failed: %s", exc)
            return [{"error": f"Failed to fetch Outlook calendar: {exc}"}]

        if not meetings:
            return []

        results: list[dict] = []
        for m in meetings:
            results.append(
                {
                    "id": m.id,
                    "title": m.title,
                    "start_time": m.start_time.isoformat(),
                    "end_time": m.end_time.isoformat(),
                    "duration_minutes": m.duration_minutes,
                    "attendees": [
                        {
                            "name": a.display_name(),
                            "email": a.email,
                            "is_organizer": a.is_organizer,
                        }
                        for a in m.attendees
                    ],
                    "location": m.location,
                    "meeting_url": m.meeting_url,
                    "source": "outlook",
                }
            )

        return results

    @mcp.tool()
    async def get_outlook_brief(
        meeting_title: str = "",
        meeting_id: str = "",
        hours_ahead: int = 24,
    ) -> str:
        """Generate a pre-meeting brief for an Outlook / Microsoft 365 meeting.

        Identical behaviour to get_meeting_brief but reads from Microsoft 365 instead
        of Google Calendar. Use this when the user's calendar is on Outlook/Exchange.
        Requires AZURE_CLIENT_ID in .env; returns an explanatory message if absent.
        Must provide at least one of meeting_title or meeting_id.

        Read-only. Attendee profiles cached 60 min. Does not write to calendar or memory.

        Args:
            meeting_title: Partial or full title (case-insensitive substring match).
                           Call get_outlook_meetings first if unsure of exact title.
            meeting_id: Exact Graph API event ID from get_outlook_meetings (takes
                        priority over title when both provided).
            hours_ahead: Search window in hours (default 24).

        Returns:
            Multi-line formatted brief card with attendee profiles, talking points,
            and watch-outs, labelled "[Source: Outlook / Microsoft 365]".
            Returns a plain-text error listing available meeting titles if no match,
            or if AZURE_CLIENT_ID is not configured.
        """
        if not meeting_title and not meeting_id:
            return (
                "Please provide either a meeting_title or meeting_id. "
                "Use get_outlook_meetings first to see what's on your Outlook calendar."
            )

        try:
            meetings = await get_outlook_events(hours_ahead)
        except Exception as exc:
            logger.error("get_outlook_brief: calendar fetch failed: %s", exc)
            return f"Failed to fetch Outlook calendar: {exc}"

        if not meetings:
            return (
                "No Outlook meetings found. "
                "If you expected meetings, check that AZURE_CLIENT_ID is set in your .env file."
            )

        meeting = _find_meeting(meetings, meeting_title, meeting_id)
        if meeting is None:
            available = ", ".join(f'"{m.title}"' for m in meetings[:5]) or "none"
            return (
                f"Meeting not found matching title='{meeting_title}' id='{meeting_id}'. "
                f"Upcoming Outlook meetings in the next {hours_ahead}h: {available}. "
                "Try get_outlook_meetings for the full list."
            )

        # Research attendees in parallel (same pattern as brief_tool.py)
        attendees_to_research = (meeting.external_attendees or meeting.attendees)[:8]
        if attendees_to_research:
            tasks = [
                _research_attendee_with_cache(a.display_name(), "")
                for a in attendees_to_research
            ]
            profiles = list(await asyncio.gather(*tasks))
        else:
            profiles = []

        talking_points = _generate_talking_points(meeting, profiles)
        watch_outs = _generate_watch_outs(meeting, profiles)

        brief = MeetingBrief(
            meeting=meeting,
            attendee_profiles=profiles,
            talking_points=talking_points,
            watch_outs=watch_outs,
            generated_at=datetime.now(timezone.utc),
        )

        return brief.format_card() + "\n  [Source: Outlook / Microsoft 365]"
