"""MCP tool: get_upcoming_meetings — reads Google Calendar for the next N hours."""

import logging

from fastmcp import FastMCP

from ..integrations.google_calendar import get_upcoming_events

logger = logging.getLogger(__name__)


def register_calendar_tools(mcp: FastMCP) -> None:
    """Register calendar-related MCP tools onto the server."""

    @mcp.tool()
    async def get_upcoming_meetings(hours_ahead: int = 24) -> list[dict]:
        """Get upcoming meetings from Google Calendar for the next N hours.

        Returns a list of meeting objects with:
        - id, title, start_time, end_time (ISO format)
        - attendees (name + email)
        - meeting_url (Google Meet / Zoom / Teams link if present)
        - location, description

        Args:
            hours_ahead: How many hours into the future to look (default: 24).

        Returns:
            List of meeting dicts. Empty list if Google Calendar is not configured.
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
