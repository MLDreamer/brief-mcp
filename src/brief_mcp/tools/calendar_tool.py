"""MCP tool: get_upcoming_meetings — reads Google Calendar for the next N hours."""

import logging

from fastmcp import FastMCP

from ..integrations.google_calendar import get_upcoming_events

logger = logging.getLogger(__name__)


def register_calendar_tools(mcp: FastMCP) -> None:
    """Register calendar-related MCP tools onto the server."""

    @mcp.tool()
    async def get_upcoming_meetings(hours_ahead: int = 24) -> list[dict]:
        """List upcoming meetings from Google Calendar.

        Call this first to discover meeting IDs and titles before calling
        get_meeting_brief or brief_with_history. Do not call if GOOGLE_CREDENTIALS_PATH
        is not configured — it will return an empty list without an error.

        Read-only. Does not modify calendar data or write to local storage.
        Safe to call multiple times; subsequent calls reflect real-time calendar state.

        Args:
            hours_ahead: How many hours ahead to look (1–168; default 24).
                         Use 2 for imminent meetings, 24 for today, 168 for the week.

        Returns:
            List of meeting objects, each containing:
              id (str) — use this in get_meeting_brief to skip title matching
              title, start_time, end_time (ISO 8601 with timezone)
              duration_minutes (int)
              attendees — list of {name, email, is_organizer}
              meeting_url — video link if present (Meet / Zoom / Teams), else null
              location, description (truncated to 300 chars)
            Returns [] if no meetings exist in the window or Google Calendar
            is not configured (GOOGLE_CREDENTIALS_PATH not set).
        """
        if hours_ahead < 1 or hours_ahead > 168:
            return [{"error": "hours_ahead must be between 1 and 168"}]

        try:
            meetings = await get_upcoming_events(hours_ahead)
        except Exception as exc:
            logger.error("get_upcoming_meetings error: %s", exc)
            return [{"error": f"Failed to fetch calendar: {exc}"}]

        if not meetings:
            return []

        result = []
        for m in meetings:
            result.append(
                {
                    "id": m.id,
                    "title": m.title,
                    "start_time": m.start_time.isoformat(),
                    "end_time": m.end_time.isoformat(),
                    "duration_minutes": m.duration_minutes,
                    "attendees": [
                        {"name": a.display_name(), "email": a.email, "is_organizer": a.is_organizer}
                        for a in m.attendees
                    ],
                    "meeting_url": m.meeting_url,
                    "location": m.location,
                    "description": (m.description[:300] if m.description else None),
                    "calendar_link": m.calendar_link,
                }
            )

        logger.info("get_upcoming_meetings returned %d meetings", len(result))
        return result
