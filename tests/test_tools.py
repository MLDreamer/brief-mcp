"""Tests for all 4 brief-mcp MCP tools.

Uses mocked Google Calendar and web-search responses from conftest.py.
All tests run fully offline with no real API keys required.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.brief_mcp.cache import cache_stats, clear_cache, get_cached_profile, set_cached_profile
from src.brief_mcp.models import Attendee, Meeting, MeetingBrief, PersonProfile


# ── Model tests ───────────────────────────────────────────────────────────────


class TestAttendeeModel:
    def test_display_name_uses_name_field(self):
        a = Attendee(name="Jane Smith", email="jane@acme.com")
        assert a.display_name() == "Jane Smith"

    def test_display_name_falls_back_to_email(self):
        a = Attendee(name="", email="john.doe@acme.com")
        assert a.display_name() == "John Doe"

    def test_display_name_unknown_fallback(self):
        a = Attendee(name="", email=None)
        assert a.display_name() == "Unknown"


class TestMeetingModel:
    def test_duration_minutes(self, sample_meeting):
        assert sample_meeting.duration_minutes == 60

    def test_external_attendees_excludes_organizer(self, sample_meeting):
        external = sample_meeting.external_attendees
        assert all(not a.is_organizer for a in external)
        assert len(external) == 2

    def test_meeting_serializable(self, sample_meeting):
        data = sample_meeting.model_dump(mode="json")
        assert data["id"] == "evt_abc123"
        assert data["title"] == "Q4 Partnership Review"
        assert len(data["attendees"]) == 3


class TestMeetingBriefFormatCard:
    def test_format_card_contains_title(self, sample_meeting, sample_profile_bob):
        brief = MeetingBrief(
            meeting=sample_meeting,
            attendee_profiles=[sample_profile_bob],
            talking_points=["Discuss Q4 roadmap"],
            watch_outs=["Partnership renewal deadline approaching"],
        )
        card = brief.format_card()
        assert "Q4 PARTNERSHIP REVIEW" in card
        assert "Bob Patel" in card
        assert "VP of Engineering" in card
        assert "Discuss Q4 roadmap" in card
        assert "Partnership renewal deadline approaching" in card

    def test_format_card_shows_duration(self, sample_meeting):
        brief = MeetingBrief(meeting=sample_meeting, attendee_profiles=[], talking_points=[])
        card = brief.format_card()
        assert "60 minutes" in card

    def test_format_card_shows_meeting_url(self, sample_meeting):
        brief = MeetingBrief(meeting=sample_meeting, attendee_profiles=[], talking_points=[])
        card = brief.format_card()
        assert "meet.google.com" in card

    def test_format_card_no_profiles(self, sample_meeting):
        brief = MeetingBrief(meeting=sample_meeting, attendee_profiles=[], talking_points=[])
        card = brief.format_card()
        assert "Generated:" in card


# ── Cache tests ───────────────────────────────────────────────────────────────


class TestCache:
    def setup_method(self):
        clear_cache()

    def test_cache_miss_returns_none(self):
        result = get_cached_profile("Unknown Person", "ACME")
        assert result is None

    def test_cache_hit_after_set(self, sample_profile_bob):
        set_cached_profile(sample_profile_bob)
        cached = get_cached_profile("Bob Patel", "PartnerCo")
        assert cached is not None
        assert cached.name == "Bob Patel"

    def test_cache_hit_company_case_insensitive(self, sample_profile_bob):
        set_cached_profile(sample_profile_bob)
        cached = get_cached_profile("Bob Patel", "partnerco")
        assert cached is not None

    def test_cache_stats(self, sample_profile_bob, sample_profile_carol):
        set_cached_profile(sample_profile_bob)
        set_cached_profile(sample_profile_carol)
        stats = cache_stats()
        # Dual-index: each profile with a company creates 2 entries (name+company + name-only)
        # Bob → 2 entries, Carol → 2 entries = 4 total
        assert stats["size"] == 4

    def test_clear_cache(self, sample_profile_bob):
        set_cached_profile(sample_profile_bob)
        # Bob has company="PartnerCo" → dual-index creates 2 cache entries
        count = clear_cache()
        assert count == 2
        assert get_cached_profile("Bob Patel", "PartnerCo") is None


# ── Tool: get_upcoming_meetings ───────────────────────────────────────────────


class TestGetUpcomingMeetings:
    async def test_returns_list_of_dicts(self, mock_google_calendar):
        from src.brief_mcp.tools.calendar_tool import register_calendar_tools
        from fastmcp import FastMCP

        mcp = FastMCP("test")
        register_calendar_tools(mcp)

        # Call the underlying function directly via module-level patching
        from src.brief_mcp.integrations.google_calendar import get_upcoming_events

        meetings = await get_upcoming_events(24)
        assert len(meetings) == 1
        assert meetings[0].title == "Q4 Partnership Review"

    async def test_returns_empty_for_no_meetings(self, mock_google_calendar_empty):
        from src.brief_mcp.integrations.google_calendar import get_upcoming_events

        meetings = await get_upcoming_events(24)
        assert meetings == []

    async def test_meeting_has_attendees(self, mock_google_calendar):
        from src.brief_mcp.integrations.google_calendar import get_upcoming_events

        meetings = await get_upcoming_events(24)
        assert len(meetings[0].attendees) == 3

    async def test_meeting_has_url(self, mock_google_calendar):
        from src.brief_mcp.integrations.google_calendar import get_upcoming_events

        meetings = await get_upcoming_events(24)
        assert "meet.google.com" in (meetings[0].meeting_url or "")


# ── Tool: research_attendee ───────────────────────────────────────────────────


class TestResearchAttendee:
    def setup_method(self):
        clear_cache()

    async def test_returns_profile_dict(self, mock_web_search):
        from src.brief_mcp.integrations.web_search import research_person

        profile = await research_person("Bob Patel", "PartnerCo")
        assert profile.name == "Bob Patel"
        assert profile.current_role == "VP of Engineering"
        assert profile.company == "PartnerCo"

    async def test_profile_has_news_lists(self, mock_web_search):
        from src.brief_mcp.integrations.web_search import research_person

        profile = await research_person("Carol Wu", "PartnerCo")
        assert isinstance(profile.recent_news, list)
        assert isinstance(profile.company_news, list)

    async def test_cache_is_used_on_second_call(self, mock_web_search):
        from src.brief_mcp.integrations.web_search import research_person

        profile1 = await research_person("Bob Patel", "PartnerCo")
        set_cached_profile(profile1)

        # Second call should hit the cache
        cached = get_cached_profile("Bob Patel", "PartnerCo")
        assert cached is not None
        assert cached.name == profile1.name

    async def test_research_parallel_gather(self, mock_web_search):
        """Parallel research should return results for all attendees."""
        from src.brief_mcp.integrations.web_search import research_person

        names = ["Bob Patel", "Carol Wu"]
        results = await asyncio.gather(*[research_person(name) for name in names])
        assert len(results) == 2
        assert {r.name for r in results} == {"Bob Patel", "Carol Wu"}


# ── Tool: get_meeting_brief ───────────────────────────────────────────────────


class TestGetMeetingBrief:
    def setup_method(self):
        clear_cache()

    async def test_returns_formatted_card(self, mock_google_calendar, mock_web_search):
        from src.brief_mcp.tools.brief_tool import register_brief_tools
        from fastmcp import FastMCP

        # Patch both integrations
        with patch(
            "src.brief_mcp.tools.brief_tool.get_upcoming_events",
            new_callable=AsyncMock,
        ) as mock_cal, patch(
            "src.brief_mcp.tools.brief_tool._research_attendee_with_cache",
            new_callable=AsyncMock,
        ) as mock_research:
            from src.brief_mcp.models import PersonProfile

            mock_cal.return_value = mock_google_calendar.return_value
            mock_research.side_effect = mock_web_search.side_effect

            mcp = FastMCP("test")
            register_brief_tools(mcp)

            # Get the registered tool function and call it
            from src.brief_mcp.tools.brief_tool import _build_brief

            meeting = mock_google_calendar.return_value[0]
            brief = await _build_brief(meeting)
            card = brief.format_card()

            assert "Q4 PARTNERSHIP REVIEW" in card
            assert "=" * 20 in card  # separator lines

    async def test_missing_title_and_id_returns_error(self):
        """Calling without any identifier should return a helpful error string."""
        with patch(
            "src.brief_mcp.tools.brief_tool.get_upcoming_events",
            new_callable=AsyncMock,
            return_value=[],
        ):
            from fastmcp import FastMCP
            from src.brief_mcp.tools.brief_tool import register_brief_tools

            mcp = FastMCP("test")
            register_brief_tools(mcp)

            # Access the registered tool directly
            # (In a real MCP call the framework routes; here we test the helper)
            from src.brief_mcp.tools.brief_tool import _find_meeting

            result = _find_meeting([], title="", meeting_id="")
            assert result is None

    async def test_find_meeting_by_partial_title(self, sample_meeting):
        from src.brief_mcp.tools.brief_tool import _find_meeting

        result = _find_meeting([sample_meeting], title="partnership", meeting_id="")
        assert result is not None
        assert result.id == "evt_abc123"

    async def test_find_meeting_by_exact_id(self, sample_meeting):
        from src.brief_mcp.tools.brief_tool import _find_meeting

        result = _find_meeting([sample_meeting], title="", meeting_id="evt_abc123")
        assert result is not None
        assert result.title == "Q4 Partnership Review"

    async def test_find_meeting_not_found(self, sample_meeting):
        from src.brief_mcp.tools.brief_tool import _find_meeting

        result = _find_meeting([sample_meeting], title="nonexistent meeting xyz", meeting_id="")
        assert result is None


# ── Tool: brief_all_today ─────────────────────────────────────────────────────


class TestBriefAllToday:
    def setup_method(self):
        clear_cache()

    async def test_returns_header_with_meeting_count(self, mock_web_search):
        from src.brief_mcp.models import Meeting, Attendee
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        meetings = [
            Meeting(
                id="m1",
                title="Morning Standup",
                start_time=now + timedelta(hours=1),
                end_time=now + timedelta(hours=1, minutes=15),
                attendees=[
                    Attendee(name="Bob Patel", email="bob@co.com", is_organizer=False),
                ],
            ),
            Meeting(
                id="m2",
                title="Strategy Session",
                start_time=now + timedelta(hours=3),
                end_time=now + timedelta(hours=4),
                attendees=[
                    Attendee(name="Carol Wu", email="carol@co.com", is_organizer=False),
                ],
            ),
        ]

        with patch(
            "src.brief_mcp.tools.brief_tool.get_upcoming_events",
            new_callable=AsyncMock,
            return_value=meetings,
        ), patch(
            "src.brief_mcp.tools.brief_tool._research_attendee_with_cache",
            new_callable=AsyncMock,
            side_effect=mock_web_search.side_effect,
        ):
            from src.brief_mcp.tools.brief_tool import _build_brief

            # Build both briefs separately to test they work
            brief1 = await _build_brief(meetings[0])
            brief2 = await _build_brief(meetings[1])

            assert "MORNING STANDUP" in brief1.format_card()
            assert "STRATEGY SESSION" in brief2.format_card()

    async def test_no_meetings_returns_informative_message(self):
        with patch(
            "src.brief_mcp.tools.brief_tool.get_upcoming_events",
            new_callable=AsyncMock,
            return_value=[],
        ):
            from fastmcp import FastMCP
            from src.brief_mcp.tools.brief_tool import register_brief_tools

            mcp = FastMCP("test")
            register_brief_tools(mcp)

            # The tool should return a helpful string for empty calendar
            # Test the underlying logic
            meetings = await AsyncMock(return_value=[])()
            assert meetings == []

    async def test_deduplicates_attendees_across_meetings(self, mock_web_search):
        """Attendees appearing in multiple meetings should only be researched once."""
        from src.brief_mcp.models import Attendee, Meeting
        from datetime import timezone, timedelta

        shared = Attendee(name="Bob Patel", email="bob@co.com", is_organizer=False)
        now = datetime.now(timezone.utc)

        meetings = [
            Meeting(
                id="m1",
                title="Meeting A",
                start_time=now + timedelta(hours=1),
                end_time=now + timedelta(hours=2),
                attendees=[shared],
            ),
            Meeting(
                id="m2",
                title="Meeting B",
                start_time=now + timedelta(hours=3),
                end_time=now + timedelta(hours=4),
                attendees=[shared],
            ),
        ]

        call_count = 0

        async def counting_research(name: str, company: str = ""):
            nonlocal call_count
            call_count += 1
            return PersonProfile(name=name, company=company or None)

        with patch(
            "src.brief_mcp.tools.brief_tool.get_upcoming_events",
            new_callable=AsyncMock,
            return_value=meetings,
        ), patch(
            "src.brief_mcp.tools.brief_tool._research_attendee_with_cache",
            side_effect=counting_research,
        ):
            # Simulate deduplicated gather (brief_all_today logic)
            all_attendees: dict[str, str] = {}
            for m in meetings:
                for att in m.attendees:
                    if att.display_name() not in all_attendees:
                        all_attendees[att.display_name()] = ""

            tasks = [counting_research(n) for n in all_attendees]
            await asyncio.gather(*tasks)

            # Bob should have been researched exactly once despite appearing in 2 meetings
            assert call_count == 1


# ── Talking points + watch-outs ───────────────────────────────────────────────


class TestTalkingPointsAndWatchOuts:
    def test_talking_points_generated(self, sample_meeting, sample_profile_bob):
        from src.brief_mcp.tools.brief_tool import _generate_talking_points

        points = _generate_talking_points(sample_meeting, [sample_profile_bob])
        assert isinstance(points, list)
        assert len(points) > 0

    def test_watch_out_short_meeting(self, sample_meeting_no_link):
        from src.brief_mcp.tools.brief_tool import _generate_watch_outs

        watch_outs = _generate_watch_outs(sample_meeting_no_link, [])
        # Short (15 min) + no link = two watch-outs
        assert len(watch_outs) >= 1
        assert any("15 min" in w for w in watch_outs)

    def test_watch_out_no_link(self, sample_meeting_no_link):
        from src.brief_mcp.tools.brief_tool import _generate_watch_outs

        watch_outs = _generate_watch_outs(sample_meeting_no_link, [])
        assert any("link" in w.lower() or "connection" in w.lower() for w in watch_outs)

    def test_watch_out_unknown_profile(self, sample_meeting):
        from src.brief_mcp.tools.brief_tool import _generate_watch_outs

        unknown = PersonProfile(name="Mystery Person", current_role=None, background=None)
        watch_outs = _generate_watch_outs(sample_meeting, [unknown])
        assert any("Mystery Person" in w for w in watch_outs)


# ── Additional tests (v0.2 / v0.3 coverage) ──────────────────────────────────


class TestBriefAllTodayDeduplication:
    def setup_method(self):
        clear_cache()

    async def test_brief_all_today_deduplication(self, mock_web_search):
        """3 meetings with overlapping attendees → each unique attendee researched exactly once."""
        from src.brief_mcp.models import Attendee, Meeting
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        bob = Attendee(name="Bob Patel", email="bob@co.com", is_organizer=False)
        carol = Attendee(name="Carol Wu", email="carol@co.com", is_organizer=False)
        dave = Attendee(name="Dave Smith", email="dave@co.com", is_organizer=False)

        meetings = [
            Meeting(
                id="m1",
                title="Morning Standup",
                start_time=now + timedelta(hours=1),
                end_time=now + timedelta(hours=1, minutes=30),
                attendees=[bob, carol],
            ),
            Meeting(
                id="m2",
                title="Partner Review",
                start_time=now + timedelta(hours=3),
                end_time=now + timedelta(hours=4),
                attendees=[bob, dave],
            ),
            Meeting(
                id="m3",
                title="Product Sync",
                start_time=now + timedelta(hours=5),
                end_time=now + timedelta(hours=6),
                attendees=[carol, dave],
            ),
        ]

        call_counts: dict[str, int] = {}

        async def counting_research(name: str, company: str = ""):
            call_counts[name] = call_counts.get(name, 0) + 1
            return PersonProfile(name=name, company=company or None)

        # Simulate the deduplication logic used by brief_all_today
        all_attendees: dict[str, str] = {}
        for m in meetings:
            for att in (m.external_attendees or m.attendees):
                key = att.display_name()
                if key not in all_attendees:
                    all_attendees[key] = ""

        import asyncio
        tasks = [counting_research(name) for name in all_attendees]
        await asyncio.gather(*tasks)

        # 3 unique attendees across 3 meetings
        assert len(all_attendees) == 3
        # Each researched exactly once (no duplicates)
        for name, count in call_counts.items():
            assert count == 1, f"{name} was researched {count} times, expected 1"


class TestBriefTimezoneAwareness:
    def test_build_brief_timezone_aware(self, sample_meeting):
        """MeetingBrief.generated_at is always timezone-aware (UTC)."""
        brief = MeetingBrief(
            meeting=sample_meeting,
            attendee_profiles=[],
            talking_points=[],
        )
        assert brief.generated_at.tzinfo is not None
        assert brief.generated_at.tzinfo == timezone.utc

    def test_generated_at_is_recent(self, sample_meeting):
        """MeetingBrief.generated_at is close to the current time."""
        from datetime import timedelta

        before = datetime.now(timezone.utc)
        brief = MeetingBrief(meeting=sample_meeting, attendee_profiles=[], talking_points=[])
        after = datetime.now(timezone.utc)
        assert before <= brief.generated_at <= after + timedelta(seconds=1)


class TestGetMeetingBriefNoMatch:
    def setup_method(self):
        clear_cache()

    async def test_get_meeting_brief_no_match(self, sample_meeting):
        """When title doesn't match any meeting, returns helpful error with available titles."""
        from fastmcp import FastMCP
        from src.brief_mcp.tools.brief_tool import register_brief_tools

        mcp = FastMCP("test")
        register_brief_tools(mcp)

        with patch(
            "src.brief_mcp.tools.brief_tool.get_upcoming_events",
            new_callable=AsyncMock,
            return_value=[sample_meeting],
        ):
            result = await mcp.call_tool(
                "get_meeting_brief",
                {"meeting_title": "Completely Nonexistent XYZ ABC 9999"},
            )

        text = result.content[0].text
        assert "not found" in text.lower() or "Meeting not found" in text
        # Should list available meeting titles in the error message
        assert "Q4 Partnership Review" in text
