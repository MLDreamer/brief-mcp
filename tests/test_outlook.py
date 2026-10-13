"""Tests for the Outlook Calendar integration (brief_mcp.integrations.outlook_calendar).

All tests are fully offline: MSAL and httpx are mocked so no real OAuth flows
or Graph API requests are made.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.brief_mcp.integrations.outlook_calendar import (
    _fetch_events_sync,
    _parse_event,
    get_outlook_events,
)
from src.brief_mcp.models import Meeting


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_event(
    event_id: str = "graph_evt_001",
    subject: str = "Test Meeting",
    start: str = "2026-10-13T10:00:00",
    end: str = "2026-10-13T11:00:00",
    attendees: list | None = None,
    join_url: str | None = None,
    location: str | None = None,
) -> dict:
    """Construct a minimal Microsoft Graph API calendar event dict."""
    raw: dict = {
        "id": event_id,
        "subject": subject,
        "start": {"dateTime": start, "timeZone": "UTC"},
        "end": {"dateTime": end, "timeZone": "UTC"},
        "attendees": attendees if attendees is not None else [],
        "location": {"displayName": location} if location else {},
        "bodyPreview": "Preview text.",
    }
    if join_url:
        raw["onlineMeeting"] = {"joinUrl": join_url}
    return raw


# ── get_outlook_events — early-exit guards ────────────────────────────────────


class TestGetOutlookEventsGuards:
    async def test_get_outlook_events_no_client_id(self):
        """When AZURE_CLIENT_ID is not set, get_outlook_events returns [] immediately."""
        with patch(
            "src.brief_mcp.integrations.outlook_calendar._get_client_id",
            return_value="",
        ):
            meetings = await get_outlook_events(24)
        assert meetings == []

    async def test_get_outlook_events_with_client_id_calls_executor(self):
        """When AZURE_CLIENT_ID is set, _fetch_events_sync is called in an executor."""
        event_raw = _make_event(
            event_id="e1",
            subject="Executor Test Meeting",
            start="2026-10-13T14:00:00",
            end="2026-10-13T15:00:00",
        )
        with patch(
            "src.brief_mcp.integrations.outlook_calendar._get_client_id",
            return_value="fake-client-id",
        ), patch(
            "src.brief_mcp.integrations.outlook_calendar._fetch_events_sync",
            return_value=[event_raw],
        ):
            meetings = await get_outlook_events(24)

        assert len(meetings) == 1
        assert meetings[0].title == "Executor Test Meeting"
        assert isinstance(meetings[0], Meeting)


# ── _parse_event ──────────────────────────────────────────────────────────────


class TestParseOutlookEvent:
    def test_parse_outlook_event_with_teams(self):
        """An event with onlineMeeting.joinUrl → Meeting.meeting_url is set."""
        event = _make_event(
            event_id="teams_evt",
            subject="Weekly Sync",
            join_url="https://teams.microsoft.com/join/xyz123",
            attendees=[
                {
                    "emailAddress": {"address": "alice@example.com", "name": "Alice"},
                    "type": "required",
                }
            ],
        )
        meeting = _parse_event(event)
        assert meeting is not None
        assert meeting.meeting_url == "https://teams.microsoft.com/join/xyz123"
        assert meeting.title == "Weekly Sync"

    def test_parse_outlook_event_all_day(self):
        """All-day events (date-only, no dateTime) have no parseable time → returns None."""
        event = {
            "id": "allday-id",
            "subject": "Company Holiday",
            "start": {"date": "2026-10-13"},  # No dateTime key
            "end": {"date": "2026-10-14"},
            "attendees": [],
        }
        result = _parse_event(event)
        # Implementation returns None for events it cannot parse a datetime for
        assert result is None

    def test_parse_outlook_event_multiple_attendees(self):
        """Three attendees in the raw event are all parsed into Meeting.attendees."""
        event = _make_event(
            subject="3-Person Meeting",
            attendees=[
                {
                    "emailAddress": {"address": "alice@x.com", "name": "Alice"},
                    "type": "required",
                },
                {
                    "emailAddress": {"address": "bob@x.com", "name": "Bob"},
                    "type": "required",
                },
                {
                    "emailAddress": {"address": "carol@x.com", "name": "Carol"},
                    "type": "optional",
                },
            ],
        )
        meeting = _parse_event(event)
        assert meeting is not None
        assert len(meeting.attendees) == 3
        names = {a.name for a in meeting.attendees}
        assert names == {"Alice", "Bob", "Carol"}

    def test_parse_event_no_attendees(self):
        """An event with an empty attendees list → Meeting with empty attendees list."""
        event = _make_event(subject="Solo Meeting", attendees=[])
        meeting = _parse_event(event)
        assert meeting is not None
        assert meeting.attendees == []

    def test_parse_event_location_display_name(self):
        """location.displayName is mapped to Meeting.location."""
        event = _make_event(
            subject="In-Person Meeting",
            location="Board Room 3A",
        )
        meeting = _parse_event(event)
        assert meeting is not None
        assert meeting.location == "Board Room 3A"

    def test_parse_event_no_subject_defaults(self):
        """An event without a subject defaults to '(No Title)'."""
        event = _make_event()
        event.pop("subject", None)
        event["subject"] = ""  # Empty subject
        # Manually set to empty so the code uses its default
        event_missing = dict(event)
        event_missing.pop("subject")
        meeting = _parse_event(event_missing)
        assert meeting is not None
        assert meeting.title == "(No Title)"


# ── _fetch_events_sync — pagination ──────────────────────────────────────────


class TestFetchEventsPagination:
    def test_pagination_follows_next_link(self):
        """_fetch_events_sync follows @odata.nextLink to retrieve events from page 2."""
        event1 = _make_event(event_id="e1", subject="Page 1 Meeting")
        event2 = _make_event(event_id="e2", subject="Page 2 Meeting")

        page1_resp = MagicMock()
        page1_resp.raise_for_status = MagicMock()
        page1_resp.json.return_value = {
            "value": [event1],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/calendarView?$skip=1",
        }

        page2_resp = MagicMock()
        page2_resp.raise_for_status = MagicMock()
        page2_resp.json.return_value = {"value": [event2]}

        mock_sync_client = MagicMock()
        mock_sync_client.get.side_effect = [page1_resp, page2_resp]
        mock_sync_client.__enter__ = MagicMock(return_value=mock_sync_client)
        mock_sync_client.__exit__ = MagicMock(return_value=False)

        with patch(
            "src.brief_mcp.integrations.outlook_calendar._acquire_token_sync",
            return_value="fake-access-token",
        ), patch(
            "src.brief_mcp.integrations.outlook_calendar._MSAL_AVAILABLE",
            True,
        ), patch(
            "src.brief_mcp.integrations.outlook_calendar._HTTPX_AVAILABLE",
            True,
        ), patch(
            "src.brief_mcp.integrations.outlook_calendar.httpx.Client",
            return_value=mock_sync_client,
        ):
            events = _fetch_events_sync(24)

        assert len(events) == 2
        subjects = {e["subject"] for e in events}
        assert "Page 1 Meeting" in subjects
        assert "Page 2 Meeting" in subjects
        # Verify the second GET was called (nextLink was followed)
        assert mock_sync_client.get.call_count == 2

    def test_fetch_events_no_token_returns_empty(self):
        """When no access token can be acquired, _fetch_events_sync returns []."""
        with patch(
            "src.brief_mcp.integrations.outlook_calendar._acquire_token_sync",
            return_value=None,
        ), patch(
            "src.brief_mcp.integrations.outlook_calendar._MSAL_AVAILABLE",
            True,
        ), patch(
            "src.brief_mcp.integrations.outlook_calendar._HTTPX_AVAILABLE",
            True,
        ):
            events = _fetch_events_sync(24)
        assert events == []
