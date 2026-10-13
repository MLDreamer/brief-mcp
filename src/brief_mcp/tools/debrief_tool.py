"""MCP tools: debrief_meeting, search_meeting_history, get_person_history,
get_open_action_items, brief_with_history.

Powered by the SQLite-based meeting memory (memory.py).
"""

import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastmcp import FastMCP

from ..cache import get_cached_profile, set_cached_profile
from ..integrations.google_calendar import get_upcoming_events
from ..integrations.web_search import research_person
from ..memory import (
    get_action_items,
    get_person_history as _db_person_history,
    get_recent_meetings,
    init_db,
    save_meeting_record,
    save_person_interaction,
    search_meetings as _db_search_meetings,
)
from ..models import Meeting, MeetingBrief

logger = logging.getLogger(__name__)


# ── Helper utilities ───────────────────────────────────────────────────────────


def _find_meeting(meetings: list[Meeting], title: str = "", meeting_id: str = "") -> Optional[Meeting]:
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


def _parse_action_items_from_text(text: str) -> list[dict]:
    """Extract action items from free-form notes text.

    Looks for patterns like:
    - "ACTION: @Alice do X by Friday"
    - "TODO: Bob to send report"
    - Bullet lines starting with "- [ ]" or "* "
    """
    items: list[dict] = []
    if not text:
        return items

    # Explicit action/todo markers
    action_patterns = [
        re.compile(r"(?:ACTION|TODO|FOLLOW.?UP|AI)\s*:?\s*(?:@(\w+(?:\s\w+)?)\s+)?(.+?)(?:\s+by\s+(\w.+?))?$", re.IGNORECASE | re.MULTILINE),
        re.compile(r"^[-*]\s+\[\s?\]\s+(.+)$", re.MULTILINE),
    ]

    for pattern in action_patterns:
        for match in pattern.finditer(text):
            groups = match.groups()
            if len(groups) == 3:
                owner = groups[0] or ""
                task = groups[1].strip() if groups[1] else ""
                due_date = groups[2].strip() if groups[2] else ""
            else:
                owner = ""
                task = groups[0].strip() if groups[0] else ""
                due_date = ""

            if task:
                items.append({"owner": owner, "task": task, "due_date": due_date})

    return items


def _format_action_items_list(items: list) -> str:
    """Format action items as a readable checklist."""
    if not items:
        return "No action items recorded."
    lines: list[str] = []
    for i, item in enumerate(items, 1):
        if isinstance(item, dict):
            task = item.get("task", "")
            owner = item.get("owner", "")
            due = item.get("due_date", "")
            parts = [f"{i}. {task}"]
            if owner:
                parts.append(f"(owner: {owner})")
            if due:
                parts.append(f"— due: {due}")
            lines.append(" ".join(parts))
        elif isinstance(item, str):
            lines.append(f"{i}. {item}")
    return "\n".join(lines)


def _generate_follow_up_email(
    meeting_title: str,
    attendee_names: list[str],
    summary: str,
    action_items: list,
    outcomes: list[str],
) -> str:
    """Generate a draft follow-up email for a debriefed meeting."""
    recipient_line = ", ".join(attendee_names) if attendee_names else "Team"
    today_str = datetime.now(timezone.utc).strftime("%B %d, %Y")

    lines: list[str] = [
        f"To: {recipient_line}",
        f"Subject: Follow-up: {meeting_title}",
        "",
        f"Hi {recipient_line.split(',')[0].strip()},",
        "",
        f"Thank you for your time today ({today_str}). Here's a summary of what we discussed and the next steps we agreed on.",
        "",
    ]

    if summary:
        lines.append("**Summary**")
        lines.append(summary)
        lines.append("")

    if outcomes:
        lines.append("**Key Outcomes / Decisions**")
        for outcome in outcomes:
            lines.append(f"- {outcome}")
        lines.append("")

    if action_items:
        lines.append("**Action Items**")
        for item in action_items:
            if isinstance(item, dict):
                task = item.get("task", "")
                owner = item.get("owner", "")
                due = item.get("due_date", "")
                line = f"- [ ] {task}"
                if owner:
                    line += f" ({owner})"
                if due:
                    line += f" — by {due}"
                lines.append(line)
            elif isinstance(item, str):
                lines.append(f"- [ ] {item}")
        lines.append("")

    lines += [
        "Please let me know if I missed anything or if you'd like to adjust any of the above.",
        "",
        "Best regards,",
    ]

    return "\n".join(lines)


def _format_meeting_record(record: dict) -> str:
    """Format a meeting record dict as a readable card."""
    lines: list[str] = []
    sep = "=" * 60
    lines.append(sep)
    title = record.get("title", "Untitled")
    date_str = record.get("date", "")
    if date_str:
        try:
            dt = datetime.fromisoformat(date_str)
            date_str = dt.strftime("%A, %B %d %Y")
        except (ValueError, TypeError):
            pass
    lines.append(f"  {title.upper()}")
    lines.append(f"  {date_str}")
    lines.append(sep)

    attendees = record.get("attendees", [])
    if attendees:
        if isinstance(attendees, list):
            names = ", ".join(str(a) for a in attendees)
        else:
            names = str(attendees)
        lines.append(f"\n  Attendees: {names}")

    summary = record.get("brief_summary")
    if summary:
        lines.append(f"\n  Summary: {summary}")

    outcomes = record.get("outcomes", [])
    if outcomes and isinstance(outcomes, list) and outcomes:
        lines.append("\n  Outcomes:")
        for o in outcomes:
            lines.append(f"    - {o}")

    action_items = record.get("action_items", [])
    if action_items and isinstance(action_items, list) and action_items:
        lines.append("\n  Action Items:")
        for item in action_items:
            if isinstance(item, dict):
                task = item.get("task", "")
                owner = item.get("owner", "")
                due = item.get("due_date", "")
                line = f"    - {task}"
                if owner:
                    line += f" ({owner})"
                if due:
                    line += f" — due {due}"
                lines.append(line)
            elif isinstance(item, str):
                lines.append(f"    - {item}")

    lines.append(sep)
    return "\n".join(lines)


# ── Tool registration ──────────────────────────────────────────────────────────


def register_debrief_tools(mcp: FastMCP) -> None:
    """Register debrief and meeting-memory MCP tools onto the server."""

    @mcp.tool()
    async def debrief_meeting(
        meeting_title: str,
        notes: str,
        action_items: str = "",
        outcomes: str = "",
    ) -> str:
        """Record what happened in a meeting and generate follow-up materials.

        Provide:
        - meeting_title: Matches a recent meeting on your calendar (or just the meeting name).
        - notes: Your raw meeting notes (bullet points, transcript snippet, anything).
        - action_items: Comma-separated list of tasks and owners (optional — will be
                        auto-extracted from notes if not provided).
        - outcomes: What was decided/agreed (optional — comma-separated).

        Returns:
        - Structured meeting record saved to memory
        - Draft follow-up email
        - Action item list with owners
        - Next-step suggestions
        """
        if not meeting_title.strip():
            return "Please provide a meeting_title to record the debrief."
        if not notes.strip():
            return "Please provide meeting notes. Even rough bullet points work."

        # Attempt to match meeting from calendar (best-effort — don't block debrief if offline)
        meeting_date = datetime.now(timezone.utc).isoformat()
        attendee_names: list[str] = []
        meeting_id_for_record = str(uuid.uuid4())

        try:
            meetings = await get_upcoming_events(48)
            calendar_meeting = _find_meeting(meetings, title=meeting_title)
            if calendar_meeting:
                meeting_date = calendar_meeting.start_time.isoformat()
                attendee_names = [a.display_name() for a in calendar_meeting.attendees]
                meeting_id_for_record = calendar_meeting.id
        except Exception as exc:
            logger.warning("debrief_meeting: calendar lookup failed (non-fatal): %s", exc)

        # Parse action items
        parsed_action_items: list[dict] = []
        if action_items.strip():
            # User supplied comma-separated list
            for raw_item in action_items.split(","):
                item = raw_item.strip()
                if item:
                    # Try to detect "Task by Owner" or "@Owner: Task" patterns
                    owner = ""
                    task = item
                    owner_match = re.match(r"@(\w+(?:\s\w+)?)\s*:?\s*(.+)", item)
                    if owner_match:
                        owner = owner_match.group(1)
                        task = owner_match.group(2).strip()
                    parsed_action_items.append({"owner": owner, "task": task, "due_date": ""})
        else:
            # Auto-extract from notes
            parsed_action_items = _parse_action_items_from_text(notes)

        # Parse outcomes
        parsed_outcomes: list[str] = []
        if outcomes.strip():
            parsed_outcomes = [o.strip() for o in outcomes.split(",") if o.strip()]

        # Generate a brief summary from notes (first 3 non-empty lines)
        note_lines = [l.strip() for l in notes.splitlines() if l.strip()]
        brief_summary = " ".join(note_lines[:3])
        if len(brief_summary) > 400:
            brief_summary = brief_summary[:397] + "..."

        # Save to memory DB (run in executor — sqlite is sync)
        loop = asyncio.get_running_loop()
        record = {
            "id": meeting_id_for_record,
            "title": meeting_title,
            "date": meeting_date,
            "attendees": attendee_names,
            "brief_summary": brief_summary,
            "action_items": parsed_action_items,
            "outcomes": parsed_outcomes,
            "follow_up_sent": 0,
        }

        try:
            saved_id = await loop.run_in_executor(None, save_meeting_record, record)
        except Exception as exc:
            logger.error("debrief_meeting: DB save failed: %s", exc)
            saved_id = meeting_id_for_record

        # Save person interaction history for each attendee
        for aname in attendee_names[:10]:
            try:
                await loop.run_in_executor(
                    None,
                    save_person_interaction,
                    aname,
                    saved_id,
                    None,
                    "",
                    "neutral",
                    brief_summary,
                )
            except Exception as exc:
                logger.debug("Could not save person interaction for '%s': %s", aname, exc)

        # Generate follow-up email draft
        follow_up_email = _generate_follow_up_email(
            meeting_title=meeting_title,
            attendee_names=attendee_names,
            summary=brief_summary,
            action_items=parsed_action_items,
            outcomes=parsed_outcomes,
        )

        # Build response card
        sep = "=" * 60
        lines: list[str] = [
            sep,
            f"  MEETING DEBRIEF: {meeting_title.upper()}",
            sep,
            f"\n  Recorded: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC",
            f"  Meeting ID: {saved_id}",
        ]

        if attendee_names:
            lines.append(f"  Attendees: {', '.join(attendee_names)}")

        if brief_summary:
            lines.append(f"\n  Summary:\n  {brief_summary}")

        if parsed_outcomes:
            lines.append("\n  Outcomes:")
            for o in parsed_outcomes:
                lines.append(f"    - {o}")

        if parsed_action_items:
            lines.append("\n  Action Items:")
            lines.append(_format_action_items_list(parsed_action_items))
        else:
            lines.append("\n  Action Items: None recorded.")

        lines += [
            "\n" + "-" * 60,
            "  DRAFT FOLLOW-UP EMAIL",
            "-" * 60,
            "",
            follow_up_email,
            "",
            sep,
            "  Debrief saved to ~/.brief-mcp/memory.db",
            "  Use search_meeting_history or get_person_history to retrieve later.",
            sep,
        ]

        return "\n".join(lines)

    @mcp.tool()
    async def search_meeting_history(query: str, limit: int = 10) -> str:
        """Search your past meeting history.

        Query by person name, company name, topic, decision, or date.
        Uses full-text search (FTS5) across meeting titles, attendees,
        summaries, action items, and outcomes.

        Args:
            query: Search term (name, topic, company, or keyword).
            limit: Maximum number of meetings to return (default: 10).

        Returns:
            Formatted list of matching past meetings with summaries and action items.
        """
        if not query.strip():
            return "Please provide a search query (name, topic, or keyword)."

        loop = asyncio.get_running_loop()
        try:
            results = await loop.run_in_executor(None, _db_search_meetings, query, min(limit, 20))
        except Exception as exc:
            logger.error("search_meeting_history failed: %s", exc)
            return f"Search failed: {exc}"

        if not results:
            return f"No past meetings found matching '{query}'."

        lines: list[str] = [
            f"Found {len(results)} meeting(s) matching '{query}':\n",
        ]

        for record in results:
            lines.append(_format_meeting_record(record))
            lines.append("")

        return "\n".join(lines)

    @mcp.tool()
    async def get_person_history(name: str) -> str:
        """Get the full interaction history with a specific person.

        Shows all past meetings with this person, topics discussed,
        commitments made, and outcomes.

        Args:
            name: Full or partial name of the person to look up.

        Returns:
            Formatted interaction history, or a message if no history exists.
        """
        if not name.strip():
            return "Please provide a person's name."

        loop = asyncio.get_running_loop()
        try:
            history = await loop.run_in_executor(None, _db_person_history, name, 20)
        except Exception as exc:
            logger.error("get_person_history failed for '%s': %s", name, exc)
            return f"Failed to retrieve history for {name}: {exc}"

        if not history:
            # Also try searching meetings by name
            try:
                meeting_results = await loop.run_in_executor(None, _db_search_meetings, name, 10)
            except Exception:
                meeting_results = []

            if not meeting_results:
                return (
                    f"No interaction history found for '{name}'. "
                    "Use debrief_meeting after calls to build up your history."
                )

            lines = [f"Meeting history involving '{name}' (from meeting records):\n"]
            for record in meeting_results:
                lines.append(_format_meeting_record(record))
                lines.append("")
            return "\n".join(lines)

        sep = "=" * 60
        lines: list[str] = [
            sep,
            f"  INTERACTION HISTORY: {name.upper()}",
            sep,
            f"  {len(history)} interaction(s) on record\n",
        ]

        for entry in history:
            date_str = entry.get("interaction_date", "")
            if date_str:
                try:
                    dt = datetime.fromisoformat(date_str)
                    date_str = dt.strftime("%Y-%m-%d")
                except (ValueError, TypeError):
                    pass

            meeting_title = entry.get("meeting_title") or entry.get("meeting_id", "Unknown Meeting")
            sentiment = entry.get("sentiment", "neutral")
            topics = entry.get("topics", [])
            notes = entry.get("notes", "")

            lines.append(f"  {date_str} — {meeting_title}")
            if topics:
                topics_str = ", ".join(str(t) for t in topics) if isinstance(topics, list) else str(topics)
                lines.append(f"    Topics: {topics_str}")
            if sentiment and sentiment != "neutral":
                lines.append(f"    Sentiment: {sentiment}")
            if notes:
                truncated = notes[:150] + "..." if len(notes) > 150 else notes
                lines.append(f"    Notes: {truncated}")
            lines.append("")

        lines.append(sep)
        return "\n".join(lines)

    @mcp.tool()
    async def get_open_action_items() -> str:
        """List all open action items from past meetings.

        Shows task, owner, meeting context, and how long it has been open.
        An action item is considered open if the meeting's follow-up has not been marked done.

        Returns:
            Formatted list of open action items with meeting context.
        """
        loop = asyncio.get_running_loop()
        try:
            items = await loop.run_in_executor(None, get_action_items, "open")
        except Exception as exc:
            logger.error("get_open_action_items failed: %s", exc)
            return f"Failed to retrieve action items: {exc}"

        if not items:
            return (
                "No open action items found. "
                "Use debrief_meeting after calls to record action items and outcomes."
            )

        now = datetime.now(timezone.utc)
        lines: list[str] = [
            f"Open action items ({len(items)} total):\n",
        ]

        for i, item in enumerate(items, 1):
            task = item.get("task", "")
            owner = item.get("owner", "")
            due = item.get("due_date", "")
            meeting_title = item.get("meeting_title", "")
            meeting_date_str = item.get("meeting_date", "")

            age_str = ""
            if meeting_date_str:
                try:
                    meeting_dt = datetime.fromisoformat(meeting_date_str)
                    if meeting_dt.tzinfo is None:
                        meeting_dt = meeting_dt.replace(tzinfo=timezone.utc)
                    days_open = (now - meeting_dt).days
                    age_str = f"{days_open}d ago"
                except (ValueError, TypeError):
                    pass

            line = f"  {i}. {task}"
            if owner:
                line += f"\n     Owner: {owner}"
            if due:
                line += f"\n     Due: {due}"
            meta_parts = []
            if meeting_title:
                meta_parts.append(f"from '{meeting_title}'")
            if age_str:
                meta_parts.append(age_str)
            if meta_parts:
                line += f"\n     ({', '.join(meta_parts)})"
            lines.append(line)
            lines.append("")

        return "\n".join(lines)

    @mcp.tool()
    async def brief_with_history(
        meeting_title: str = "",
        meeting_id: str = "",
    ) -> str:
        """Generate a pre-meeting brief that includes past interaction history.

        Combines:
        1. Live calendar lookup + parallel attendee web research (like get_meeting_brief)
        2. Past meeting history for each attendee (from your memory DB)
        3. Previous action items and commitments involving these people

        This gives a richer "full context" brief — especially valuable for recurring
        meetings and follow-up calls.

        Args:
            meeting_title: Partial or full meeting title (Google Calendar).
            meeting_id: Exact meeting ID from get_upcoming_meetings (takes priority).

        Returns:
            Formatted brief card with appended history section.
        """
        if not meeting_title and not meeting_id:
            return (
                "Please provide either a meeting_title or meeting_id. "
                "Use get_upcoming_meetings first to see what's on your calendar."
            )

        # 1. Fetch calendar
        try:
            meetings = await get_upcoming_events(24)
        except Exception as exc:
            logger.error("brief_with_history: calendar fetch failed: %s", exc)
            return f"Failed to fetch calendar: {exc}"

        meeting = _find_meeting(meetings, meeting_title, meeting_id)
        if meeting is None:
            available = ", ".join(f'"{m.title}"' for m in meetings[:5]) or "none"
            return (
                f"Meeting not found matching title='{meeting_title}' id='{meeting_id}'. "
                f"Upcoming meetings in the next 24h: {available}. "
                "Try get_upcoming_meetings for the full list."
            )

        # 2. Research attendees in parallel
        attendees_to_research = (meeting.external_attendees or meeting.attendees)[:8]
        if attendees_to_research:
            research_tasks = [
                _research_attendee_with_cache(a.display_name(), "")
                for a in attendees_to_research
            ]
            profiles = list(await asyncio.gather(*research_tasks))
        else:
            profiles = []

        # 3. Build standard brief
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

        # 4. Retrieve history for each attendee from memory DB
        loop = asyncio.get_running_loop()
        history_sections: list[str] = []
        sep = "-" * 60

        for attendee in attendees_to_research:
            aname = attendee.display_name()
            try:
                person_hist = await loop.run_in_executor(None, _db_person_history, aname, 5)
            except Exception as exc:
                logger.debug("History lookup failed for '%s': %s", aname, exc)
                person_hist = []

            if person_hist:
                hist_lines = [f"  Past interactions with {aname}:"]
                for entry in person_hist:
                    date_str = entry.get("interaction_date", "")
                    if date_str:
                        try:
                            dt = datetime.fromisoformat(date_str)
                            date_str = dt.strftime("%Y-%m-%d")
                        except (ValueError, TypeError):
                            pass
                    mtitle = entry.get("meeting_title") or "Unknown Meeting"
                    notes = entry.get("notes", "")
                    hist_lines.append(f"    {date_str} — {mtitle}")
                    if notes:
                        truncated = notes[:120] + "..." if len(notes) > 120 else notes
                        hist_lines.append(f"      {truncated}")
                history_sections.append("\n".join(hist_lines))

        # 5. Retrieve open action items involving meeting attendees
        try:
            all_open = await loop.run_in_executor(None, get_action_items, "open")
        except Exception:
            all_open = []

        attendee_name_set = {a.display_name().lower() for a in attendees_to_research}
        relevant_actions = [
            item for item in all_open
            if item.get("owner", "").lower() in attendee_name_set
            or any(
                name in item.get("task", "").lower()
                for name in attendee_name_set
            )
        ]

        # 6. Append history and open actions to the card
        if history_sections or relevant_actions:
            history_block_lines = [
                f"\n{sep}",
                "  PAST INTERACTION HISTORY",
                sep,
            ]

            if history_sections:
                history_block_lines.extend(history_sections)
            else:
                history_block_lines.append("  No past interaction records found for these attendees.")

            if relevant_actions:
                history_block_lines.append(f"\n{sep}")
                history_block_lines.append("  OPEN ACTION ITEMS (INVOLVING THESE ATTENDEES)")
                history_block_lines.append(sep)
                for item in relevant_actions[:10]:
                    task = item.get("task", "")
                    owner = item.get("owner", "")
                    mtitle = item.get("meeting_title", "")
                    line = f"  - {task}"
                    if owner:
                        line += f" (owner: {owner})"
                    if mtitle:
                        line += f" [from: {mtitle}]"
                    history_block_lines.append(line)

            card = card.rstrip() + "\n" + "\n".join(history_block_lines) + "\n" + "=" * 60
        else:
            card += (
                "\n\n  [History: No past meetings recorded for these attendees. "
                "Use debrief_meeting after calls to build your meeting memory.]"
            )

        return card
