"""MCP tools: get_outlook_meetings + get_outlook_brief.

Reads Outlook/Microsoft 365 calendar via Microsoft Graph API.
Configure AZURE_CLIENT_ID (and optionally AZURE_TENANT_ID) in .env to enable.
"""

import asyncio
import logging
from datetime import datetime, timezone

from fastmcp import FastMCP

from ..cache import get_cached_profile, set_cached_profile
from ..integrations.outlook_calendar import get_outlook_events
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


def _generate_talking_points(meeting: Meeting, profiles: list) -> list[str]:
    """Generate contextual talking points (mirrors brief_tool logic)."""
    points: list[str] = []
    title_lower = meeting.title.lower()

    if any(w in title_lower for w in ["review", "sync", "standup", "check-in"]):
        points.append("Share progress since last meeting — lead with metrics or milestones.")
    if any(w in title_lower for w in ["intro", "meet", "introduction", "first"]):
        points.append("Prepare a 60-second personal introduction covering your current role and goals.")
    if any(w in title_lower for w in ["pitch", "demo", "presentation", "proposal"]):
        points.append("Confirm your demo environment is working 15 minutes before the call.")
    if any(w in title_lower for w in ["negotiat", "contract", "agreement", "deal"]):
        points.append("Know your walk-away position before the meeting starts.")

    for profile in profiles:
        if profile.current_role:
            points.append(
                f"Ask {profile.name.split()[0]} about their priorities as {profile.current_role}."
            )
        if profile.recent_news:
            points.append(
                f"Reference recent news about {profile.name.split()[0]}: "
                f'"{profile.recent_news[0][:80]}"'
            )
        if profile.company_news:
            company = profile.company or "their company"
            points.append(
                f"Acknowledge recent {company} news: "
                f'"{profile.company_news[0][:80]}"'
            )

    if not points:
        points.append("Clarify the desired outcome before the meeting ends.")
        points.append("Agree on next steps and owners before you hang up.")

    return points[:6]


def _generate_watch_outs(meeting: Meeting, profiles: list) -> list[str]:
    """Generate potential sensitivities."""
    watch_outs: list[str] = []

    if meeting.duration_minutes <= 15:
        watch_outs.append(
            f"Short meeting ({meeting.duration_minutes} min) — get to your main point within 2 minutes."
        )
    if meeting.duration_minutes >= 90:
        watch_outs.append("Long meeting — set a clear agenda to avoid scope creep.")

    if not meeting.meeting_url and not meeting.location:
        watch_outs.append(
            "No meeting link or location found — confirm connection details beforehand."
        )

    for profile in profiles:
        if not profile.current_role and not profile.background:
            watch_outs.append(
                f"Limited public information found for {profile.name} — review LinkedIn manually."
            )

    return watch_outs[:4]


def register_outlook_tools(mcp: FastMCP) -> None:
    """Register Outlook MCP tools onto the server."""

    @mcp.tool()
    async def get_outlook_meetings(hours_ahead: int = 24) -> list[dict]:
        """Get upcoming meetings from Outlook/Microsoft 365 calendar.

        Configure AZURE_CLIENT_ID in .env to enable. On first run, a device-code
        authentication prompt will appear in the terminal — visit the URL shown
        and enter the code to authorise access.

        Returns the same format as get_upcoming_meetings (Google Calendar).

        Args:
            hours_ahead: How far ahead to look in hours (default: 24).

        Returns:
            List of meeting dicts with id, title, start/end times, attendees, and meeting URL.
            Returns an empty list with an explanation if Outlook is not configured.
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
        """Generate a meeting brief from your Outlook/Microsoft 365 calendar.

        Same behaviour as get_meeting_brief but reads from Microsoft 365 instead of
        Google Calendar. Requires AZURE_CLIENT_ID to be set in .env.

        Args:
            meeting_title: Partial or full Outlook meeting title to match.
            meeting_id: Exact Graph API event ID (takes priority over title).
            hours_ahead: How far ahead to look for the meeting (default: 24h).

        Returns:
            A formatted brief card string, or an error message if the meeting is not found.
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
