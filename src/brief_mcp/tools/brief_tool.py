"""MCP tools: get_meeting_brief + brief_all_today.

These are the highest-level tools — they orchestrate calendar lookup,
parallel attendee research, and formatted output.
"""

import asyncio
import logging
from datetime import datetime, timezone
from fastmcp import FastMCP

from ..integrations.google_calendar import get_upcoming_events
from ..models import Meeting, MeetingBrief
from ._shared import _find_meeting, _research_attendee_with_cache

logger = logging.getLogger(__name__)


def _generate_talking_points(meeting: Meeting, profiles: list) -> list[str]:
    """Generate contextual talking points from the meeting and attendee profiles."""
    points: list[str] = []

    # Meeting purpose signals
    title_lower = meeting.title.lower()
    if any(w in title_lower for w in ["review", "sync", "standup", "check-in"]):
        points.append("Share progress since last meeting — lead with metrics or milestones.")
    if any(w in title_lower for w in ["intro", "meet", "introduction", "first"]):
        points.append("Prepare a 60-second personal introduction covering your current role and goals.")
    if any(w in title_lower for w in ["pitch", "demo", "presentation", "proposal"]):
        points.append("Confirm your demo environment is working 15 minutes before the call.")
    if any(w in title_lower for w in ["negotiat", "contract", "agreement", "deal"]):
        points.append("Know your walk-away position before the meeting starts.")

    # Profile-driven points
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
    """Generate potential sensitivities or things to be aware of."""
    watch_outs: list[str] = []

    # Duration-based
    if meeting.duration_minutes <= 15:
        watch_outs.append(
            f"Short meeting ({meeting.duration_minutes} min) — get to your main point within 2 minutes."
        )
    if meeting.duration_minutes >= 90:
        watch_outs.append("Long meeting — set a clear agenda to avoid scope creep.")

    # No meeting link
    if not meeting.meeting_url and not meeting.location:
        watch_outs.append(
            "No meeting link or location found — confirm connection details beforehand."
        )

    # Profile gaps
    for profile in profiles:
        if not profile.current_role and not profile.background:
            watch_outs.append(
                f"Limited public information found for {profile.name} — review LinkedIn manually."
            )

    return watch_outs[:4]


async def _build_brief(meeting: Meeting) -> MeetingBrief:
    """Research all non-organizer attendees in parallel and build a MeetingBrief."""
    # Research external attendees only (skip the calendar owner / organizer)
    attendees_to_research = meeting.external_attendees or meeting.attendees

    # Cap at 8 attendees to avoid runaway API costs
    attendees_to_research = attendees_to_research[:8]

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

    return MeetingBrief(
        meeting=meeting,
        attendee_profiles=profiles,
        talking_points=talking_points,
        watch_outs=watch_outs,
        generated_at=datetime.now(timezone.utc),
    )


def register_brief_tools(mcp: FastMCP) -> None:
    """Register briefing MCP tools onto the server."""

    @mcp.tool()
    async def get_meeting_brief(
        meeting_title: str = "",
        meeting_id: str = "",
        hours_ahead: int = 24,
    ) -> str:
        """Generate a pre-meeting intelligence brief for one Google Calendar meeting.

        Looks up the meeting, researches all external attendees in parallel via web
        search, and returns a formatted brief card. Use this for a single upcoming
        meeting. For all of today's meetings at once, use brief_all_today instead.
        For recurring meetings where past interaction history matters, prefer
        brief_with_history.

        Read-only. Does not write to calendar or memory. Attendee profiles are cached
        for 60 minutes — repeated calls for the same meeting are fast.
        Must provide at least one of meeting_title or meeting_id.

        Args:
            meeting_title: Partial or full title (case-insensitive substring match).
                           Example: "Q4 review" matches "Q4 Partnership Review".
            meeting_id: Exact id from get_upcoming_meetings output (takes priority
                        over title when both are provided).
            hours_ahead: Search window in hours (default 24). Increase if the meeting
                         is further out.

        Returns:
            Multi-line formatted brief card with attendee profiles, talking points,
            and watch-outs. Returns a plain-text error with available meeting titles
            if no match is found, or if Google Calendar is not configured.
        """
        if not meeting_title and not meeting_id:
            return (
                "Please provide either a meeting_title or meeting_id. "
                "Use get_upcoming_meetings first to see what's on your calendar."
            )

        try:
            meetings = await get_upcoming_events(hours_ahead)
        except Exception as exc:
            logger.error("get_meeting_brief: calendar fetch failed: %s", exc)
            return f"Failed to fetch calendar: {exc}"

        meeting = _find_meeting(meetings, meeting_title, meeting_id)

        if meeting is None:
            available = ", ".join(f'"{m.title}"' for m in meetings[:5]) or "none"
            return (
                f"Meeting not found matching title='{meeting_title}' id='{meeting_id}'. "
                f"Upcoming meetings in the next {hours_ahead}h: {available}. "
                "Try get_upcoming_meetings for the full list."
            )

        try:
            brief = await _build_brief(meeting)
        except Exception as exc:
            logger.error("get_meeting_brief: brief build failed: %s", exc)
            return f"Failed to generate brief for '{meeting.title}': {exc}"

        return brief.format_card()

    @mcp.tool()
    async def brief_all_today() -> str:
        """Generate intelligence briefs for every meeting in the next 24 hours.

        The most efficient morning-prep tool: fetches the full day's calendar, then
        researches all unique attendees in parallel (each person researched once even
        if they appear in multiple meetings). Use this at the start of the day.
        For a single specific meeting, use get_meeting_brief instead.

        Read-only. Does not write to calendar or memory. Requires Google Calendar
        (GOOGLE_CREDENTIALS_PATH). Attendee profiles are cached for 60 minutes.

        Returns:
            Concatenated brief cards for every meeting today, separated by dividers,
            with a header showing the date and meeting count.
            Returns a plain-text message if no meetings exist in the next 24 hours
            or if Google Calendar is not configured.
        """
        # Look ahead just enough to cover today (up to midnight)
        now = datetime.now(timezone.utc)
        # Use 24h to always capture a full day regardless of time zone
        hours = 24

        try:
            meetings = await get_upcoming_events(hours)
        except Exception as exc:
            logger.error("brief_all_today: calendar fetch failed: %s", exc)
            return f"Failed to fetch calendar: {exc}"

        if not meetings:
            return (
                "No meetings found in the next 24 hours. "
                "If you expected meetings, check that Google Calendar is configured "
                "(see GOOGLE_CREDENTIALS_PATH in your .env file)."
            )

        # Deduplicate attendees across meetings for efficient parallel research
        all_attendees: dict[str, str] = {}  # name -> company
        for meeting in meetings:
            for attendee in (meeting.external_attendees or meeting.attendees)[:8]:
                aname = attendee.display_name()
                if aname not in all_attendees:
                    all_attendees[aname] = ""

        # Research all unique attendees in parallel
        logger.info(
            "brief_all_today: researching %d unique attendees across %d meetings",
            len(all_attendees),
            len(meetings),
        )

        research_tasks = [
            _research_attendee_with_cache(name, company)
            for name, company in all_attendees.items()
        ]
        all_profiles_list = list(await asyncio.gather(*research_tasks))
        profiles_by_name: dict[str, object] = {
            p.name: p for p in all_profiles_list if hasattr(p, "name")
        }

        # Build briefs (reuse cached profiles — no re-fetch)
        briefs: list[str] = []
        for i, meeting in enumerate(meetings, 1):
            attendee_profiles = []
            for attendee in (meeting.external_attendees or meeting.attendees)[:8]:
                aname = attendee.display_name()
                if aname in profiles_by_name:
                    attendee_profiles.append(profiles_by_name[aname])

            talking_points = _generate_talking_points(meeting, attendee_profiles)
            watch_outs = _generate_watch_outs(meeting, attendee_profiles)

            brief = MeetingBrief(
                meeting=meeting,
                attendee_profiles=attendee_profiles,
                talking_points=talking_points,
                watch_outs=watch_outs,
                generated_at=datetime.now(timezone.utc),
            )
            briefs.append(brief.format_card())

        header = (
            f"DAILY BRIEFING — {now.strftime('%A, %B %d %Y')}\n"
            f"{len(meetings)} meeting(s) today\n"
            f"{'#' * 60}\n\n"
        )
        return header + "\n\n".join(briefs)
