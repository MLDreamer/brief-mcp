"""Shared pytest fixtures for brief-mcp tests.

All external API calls (Google Calendar, Brave Search, DuckDuckGo) are mocked
so tests run offline without credentials.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.brief_mcp.models import Attendee, Meeting, PersonProfile


# ── Fixture: sample meetings ──────────────────────────────────────────────────


@pytest.fixture
def now_utc() -> datetime:
    return datetime(2026, 10, 13, 9, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def sample_attendees() -> list[Attendee]:
    return [
        Attendee(name="Alice Chen", email="alice@acme.com", is_organizer=True),
        Attendee(name="Bob Patel", email="bob@partnerco.com", is_organizer=False),
        Attendee(name="Carol Wu", email="carol@partnerco.com", is_organizer=False),
    ]


@pytest.fixture
def sample_meeting(now_utc, sample_attendees) -> Meeting:
    return Meeting(
        id="evt_abc123",
        title="Q4 Partnership Review",
        start_time=now_utc + timedelta(hours=1),
        end_time=now_utc + timedelta(hours=2),
        attendees=sample_attendees,
        location=None,
        description="Quarterly review of the Acme-PartnerCo integration roadmap.",
        meeting_url="https://meet.google.com/abc-defg-hij",
        calendar_link="https://calendar.google.com/event?id=abc123",
    )


@pytest.fixture
def sample_meeting_no_link(now_utc, sample_attendees) -> Meeting:
    """Meeting with no video link, to test watch-outs."""
    return Meeting(
        id="evt_xyz999",
        title="Quick Intro Call",
        start_time=now_utc + timedelta(hours=3),
        end_time=now_utc + timedelta(hours=3, minutes=15),
        attendees=sample_attendees[:2],
        meeting_url=None,
        location=None,
    )


@pytest.fixture
def sample_profile_bob() -> PersonProfile:
    return PersonProfile(
        name="Bob Patel",
        current_role="VP of Engineering",
        company="PartnerCo",
        linkedin_summary="VP of Engineering at PartnerCo. 15 years in distributed systems.",
        recent_news=["Bob Patel promoted to VP at PartnerCo", "PartnerCo raises Series B"],
        company_news=["PartnerCo launches new AI platform", "PartnerCo expands to APAC"],
        background="Seasoned engineering leader with focus on developer tooling.",
        research_sources=["https://linkedin.com/in/bobpatel", "https://techcrunch.com/..."],
    )


@pytest.fixture
def sample_profile_carol() -> PersonProfile:
    return PersonProfile(
        name="Carol Wu",
        current_role="Director of Product",
        company="PartnerCo",
        linkedin_summary="Director of Product at PartnerCo, ex-Google.",
        recent_news=["Carol Wu joins PartnerCo from Google"],
        company_news=["PartnerCo launches new AI platform"],
        background="Product leader with 10 years in enterprise SaaS.",
        research_sources=["https://linkedin.com/in/carolwu"],
    )


# ── Fixture: mocked Google Calendar ──────────────────────────────────────────


@pytest.fixture
def mock_google_calendar(sample_meeting):
    """Patch get_upcoming_events to return our sample meeting."""
    with patch(
        "src.brief_mcp.integrations.google_calendar.get_upcoming_events",
        new_callable=AsyncMock,
        return_value=[sample_meeting],
    ) as mock:
        yield mock


@pytest.fixture
def mock_google_calendar_multi(sample_meeting, sample_meeting_no_link):
    """Patch get_upcoming_events to return two meetings."""
    with patch(
        "src.brief_mcp.integrations.google_calendar.get_upcoming_events",
        new_callable=AsyncMock,
        return_value=[sample_meeting, sample_meeting_no_link],
    ) as mock:
        yield mock


@pytest.fixture
def mock_google_calendar_empty():
    """Patch get_upcoming_events to return an empty list."""
    with patch(
        "src.brief_mcp.integrations.google_calendar.get_upcoming_events",
        new_callable=AsyncMock,
        return_value=[],
    ) as mock:
        yield mock


# ── Fixture: mocked web search ────────────────────────────────────────────────


MOCK_BRAVE_RESULTS = [
    {
        "title": "Bob Patel – VP of Engineering at PartnerCo",
        "snippet": "Bob Patel is VP of Engineering at PartnerCo, leading the platform team.",
        "url": "https://linkedin.com/in/bobpatel",
    },
    {
        "title": "PartnerCo raises $50M Series B",
        "snippet": "PartnerCo announced a $50M Series B round to expand its AI platform.",
        "url": "https://techcrunch.com/partnerco-series-b",
    },
]


@pytest.fixture
def mock_web_search(sample_profile_bob, sample_profile_carol):
    """Patch research_person to return sample profiles."""

    async def _fake_research(name: str, company: str = "") -> PersonProfile:
        if "bob" in name.lower():
            return sample_profile_bob
        if "carol" in name.lower():
            return sample_profile_carol
        return PersonProfile(name=name, company=company or None)

    with patch(
        "src.brief_mcp.integrations.web_search.research_person",
        side_effect=_fake_research,
    ) as mock:
        yield mock


@pytest.fixture
def mock_httpx_brave():
    """Patch httpx.AsyncClient.get for Brave Search API responses."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(
        return_value={
            "web": {
                "results": MOCK_BRAVE_RESULTS,
            }
        }
    )

    with patch(
        "httpx.AsyncClient.get",
        new_callable=AsyncMock,
        return_value=mock_resp,
    ) as mock:
        yield mock


# ── Fixture: memory database (tmp_path isolated) ─────────────────────────────


@pytest.fixture
def memory_db(tmp_path, monkeypatch):
    """Patch the memory module to use a temp directory for DB isolation.

    Prevents tests from writing to ~/.brief-mcp/memory.db.
    """
    db_path = tmp_path / "memory.db"
    monkeypatch.setattr("src.brief_mcp.memory._DB_PATH", db_path)
    monkeypatch.setattr("src.brief_mcp.memory._DB_DIR", tmp_path)
    yield db_path


# ── Fixtures: HubSpot mock data ───────────────────────────────────────────────


@pytest.fixture
def sample_hs_contact_props() -> dict:
    """Raw HubSpot contact properties dict as returned by the API."""
    return {
        "firstname": "Jane",
        "lastname": "Doe",
        "email": "jane.doe@acme.com",
        "company": "Acme Corp",
        "jobtitle": "VP Sales",
        "phone": "+1-555-0100",
        "lifecyclestage": "customer",
        "notes_last_contacted": "1728000000000",  # epoch ms
    }


@pytest.fixture
def sample_hs_contact_obj(sample_hs_contact_props) -> dict:
    """Full HubSpot contact object as returned from the search API."""
    return {
        "id": "hs_contact_001",
        "properties": sample_hs_contact_props,
    }


@pytest.fixture
def sample_hs_deal_obj() -> dict:
    """Full HubSpot deal object as returned from the deals API."""
    return {
        "id": "hs_deal_001",
        "properties": {
            "dealname": "Acme Enterprise Deal",
            "dealstage": "proposal",
            "amount": "75000",
            "closedate": "2026-12-31T00:00:00.000Z",
            "notes_last_updated": None,
        },
    }


# ── Fixtures: Outlook mock events ─────────────────────────────────────────────


def _make_outlook_event(
    event_id: str = "ot_evt_001",
    subject: str = "Test Outlook Meeting",
    start: str = "2026-10-13T10:00:00",
    end: str = "2026-10-13T11:00:00",
    attendees: list | None = None,
    join_url: str | None = None,
    location: str | None = None,
) -> dict:
    """Build a minimal Microsoft Graph API calendar event dict."""
    raw: dict = {
        "id": event_id,
        "subject": subject,
        "start": {"dateTime": start, "timeZone": "UTC"},
        "end": {"dateTime": end, "timeZone": "UTC"},
        "attendees": attendees or [],
        "location": {"displayName": location} if location else {},
        "bodyPreview": "Test meeting body preview.",
    }
    if join_url:
        raw["onlineMeeting"] = {"joinUrl": join_url}
    return raw


@pytest.fixture
def sample_outlook_event() -> dict:
    return _make_outlook_event(
        event_id="ot_evt_teams",
        subject="Weekly Team Sync",
        attendees=[
            {
                "emailAddress": {"address": "alice@example.com", "name": "Alice Example"},
                "type": "required",
            },
            {
                "emailAddress": {"address": "bob@example.com", "name": "Bob Example"},
                "type": "required",
            },
        ],
        join_url="https://teams.microsoft.com/join/abc123",
        location="Microsoft Teams",
    )
