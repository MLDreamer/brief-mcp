"""Google Calendar OAuth2 client for brief-mcp.

Reads calendar events and extracts attendee + meeting-link information.
Credentials follow the standard OAuth2 desktop flow:
  - GOOGLE_CREDENTIALS_PATH → path to the credentials.json downloaded from GCP
  - Token is stored at ~/.brief-mcp/token.json (refreshed automatically)
"""

import asyncio
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Lazy imports for google libs so the package can be imported without them installed
# in environments where only DuckDuckGo search is used.
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError

    _GOOGLE_AVAILABLE = True
except ImportError:
    _GOOGLE_AVAILABLE = False
    logger.warning(
        "google-api-python-client not installed. "
        "Google Calendar integration is disabled — install the [google] extra."
    )

from ..models import Attendee, Meeting

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
]

_TOKEN_DIR = Path.home() / ".brief-mcp"
_TOKEN_PATH = _TOKEN_DIR / "token.json"

# Patterns for common video-meeting links
_MEET_PATTERNS = [
    re.compile(r"https://meet\.google\.com/[a-z0-9\-]+", re.IGNORECASE),
    re.compile(r"https://zoom\.us/j/[^\s>\"']+", re.IGNORECASE),
    re.compile(r"https://teams\.microsoft\.com/l/meetup-join/[^\s>\"']+", re.IGNORECASE),
    re.compile(r"https://[a-z]+\.zoom\.us/j/[^\s>\"']+", re.IGNORECASE),
    re.compile(r"https://webex\.com/[^\s>\"']+", re.IGNORECASE),
]


def _get_credentials() -> Optional[object]:
    """Load or refresh OAuth2 credentials for Google Calendar."""
    if not _GOOGLE_AVAILABLE:
        return None

    credentials_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "")
    if not credentials_path:
        logger.warning(
            "GOOGLE_CREDENTIALS_PATH not set. "
            "Google Calendar is disabled. Set this env var to enable it."
        )
        return None

    creds = None
    _TOKEN_DIR.mkdir(parents=True, exist_ok=True)

    if _TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(_TOKEN_PATH), SCOPES)

    # Refresh or run the initial OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                logger.info("Google OAuth token refreshed successfully.")
            except Exception as exc:
                logger.error("Failed to refresh Google token: %s", exc)
                creds = None

        if not creds:
            if not Path(credentials_path).exists():
                logger.error(
                    "credentials.json not found at %s. "
                    "Download it from Google Cloud Console.",
                    credentials_path,
                )
                return None
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
            logger.info("Google OAuth flow completed — new token saved.")

        # Persist the token
        _TOKEN_PATH.write_text(creds.to_json())

    return creds


def _extract_meeting_url(text: Optional[str]) -> Optional[str]:
    """Search text for a video-meeting URL and return the first match."""
    if not text:
        return None
    for pattern in _MEET_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(0)
    return None


def _parse_event(event: dict) -> Optional[Meeting]:
    """Convert a Google Calendar event dict into a Meeting model."""
    event_id = event.get("id", "")
    summary = event.get("summary", "(No Title)")

    # Parse start/end — can be dateTime or all-day date
    start_raw = event.get("start", {})
    end_raw = event.get("end", {})

    try:
        if "dateTime" in start_raw:
            start_time = datetime.fromisoformat(start_raw["dateTime"])
        else:
            # All-day event — treat as midnight UTC
            start_time = datetime.fromisoformat(start_raw["date"] + "T00:00:00+00:00")

        if "dateTime" in end_raw:
            end_time = datetime.fromisoformat(end_raw["dateTime"])
        else:
            end_time = datetime.fromisoformat(end_raw["date"] + "T23:59:59+00:00")
    except (ValueError, KeyError) as exc:
        logger.warning("Could not parse event times for '%s': %s", summary, exc)
        return None

    # Ensure timezone-aware
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)

    # Attendees
    raw_attendees = event.get("attendees", [])
    organizer_email = event.get("organizer", {}).get("email", "")
    attendees: list[Attendee] = []
    for raw in raw_attendees:
        email = raw.get("email", "")
        display = raw.get("displayName", "")
        is_organizer = email == organizer_email or raw.get("organizer", False)
        # Skip rooms / resources
        if raw.get("resource", False):
            continue
        attendees.append(
            Attendee(
                name=display or email.split("@")[0].replace(".", " ").title(),
                email=email,
                is_organizer=is_organizer,
            )
        )

    # If no attendees listed, add organizer
    if not attendees and organizer_email:
        attendees.append(Attendee(name=organizer_email, email=organizer_email, is_organizer=True))

    description = event.get("description", "")
    location = event.get("location", "")

    # Meeting link: check conferenceData first, then description/location
    meeting_url: Optional[str] = None
    conf_data = event.get("conferenceData", {})
    entry_points = conf_data.get("entryPoints", [])
    for ep in entry_points:
        if ep.get("entryPointType") == "video":
            meeting_url = ep.get("uri")
            break

    if not meeting_url:
        meeting_url = _extract_meeting_url(description) or _extract_meeting_url(location)

    # Google Calendar HTML link
    html_link = event.get("htmlLink")

    return Meeting(
        id=event_id,
        title=summary,
        start_time=start_time,
        end_time=end_time,
        attendees=attendees,
        location=location or None,
        description=description or None,
        meeting_url=meeting_url,
        calendar_link=html_link,
    )


async def get_upcoming_events(hours_ahead: int = 24) -> list[Meeting]:
    """Fetch upcoming Google Calendar events for the next N hours.

    Returns an empty list (with a log warning) if Google Calendar is not configured
    rather than raising an exception — graceful degradation.
    """
    if not _GOOGLE_AVAILABLE:
        logger.warning("Google Calendar unavailable: google-api-python-client not installed.")
        return []

    creds = _get_credentials()
    if creds is None:
        logger.warning("Google Calendar not configured — returning empty meeting list.")
        return []

    now = datetime.now(timezone.utc)
    time_max = now + timedelta(hours=hours_ahead)

    # Run the blocking Google API call in a thread pool to keep async safety
    def _fetch() -> list[dict]:
        try:
            service = build("calendar", "v3", credentials=creds, cache_discovery=False)
            result = (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=now.isoformat(),
                    timeMax=time_max.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                    maxResults=25,
                )
                .execute()
            )
            return result.get("items", [])
        except HttpError as exc:
            logger.error("Google Calendar API error: %s", exc)
            return []

    raw_events: list[dict] = await asyncio.get_event_loop().run_in_executor(None, _fetch)

    meetings: list[Meeting] = []
    for event in raw_events:
        parsed = _parse_event(event)
        if parsed is not None:
            meetings.append(parsed)

    logger.info("Fetched %d upcoming meetings (next %dh)", len(meetings), hours_ahead)
    return meetings
