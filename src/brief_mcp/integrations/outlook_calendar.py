"""Microsoft Graph API OAuth2 client for brief-mcp.

Uses MSAL device-code flow (works headless/CLI). Reads Outlook/Microsoft 365 calendar.

Required env vars:
    AZURE_CLIENT_ID  — App registration client ID from Azure portal
    AZURE_TENANT_ID  — Directory (tenant) ID, or "common" for personal accounts

Token is stored at ~/.brief-mcp/ms_token.json and refreshed automatically.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

try:
    import msal

    _MSAL_AVAILABLE = True
except ImportError:
    _MSAL_AVAILABLE = False
    logger.warning(
        "msal not installed. Outlook Calendar integration is disabled. "
        "Install with: pip install msal"
    )

try:
    import httpx

    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False

from ..models import Attendee, Meeting

_TOKEN_DIR = Path.home() / ".brief-mcp"
_MS_TOKEN_PATH = _TOKEN_DIR / "ms_token.json"
_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_SCOPES = ["Calendars.Read", "offline_access"]


def _get_client_id() -> str:
    return os.getenv("AZURE_CLIENT_ID", "")


def _get_tenant_id() -> str:
    return os.getenv("AZURE_TENANT_ID", "common")


def _build_app() -> Optional[Any]:
    """Build and return the MSAL PublicClientApplication."""
    if not _MSAL_AVAILABLE:
        return None
    client_id = _get_client_id()
    if not client_id:
        return None
    tenant_id = _get_tenant_id()
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    return msal.PublicClientApplication(
        client_id=client_id,
        authority=authority,
        token_cache=_build_token_cache(),
    )


def _build_token_cache() -> Optional[Any]:
    """Load token cache from disk, or return a fresh one."""
    if not _MSAL_AVAILABLE:
        return None
    cache = msal.SerializableTokenCache()
    if _MS_TOKEN_PATH.exists():
        try:
            cache.deserialize(_MS_TOKEN_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Could not load MS token cache: %s", exc)
    return cache


def _save_token_cache(cache: Any) -> None:
    """Persist a dirty token cache to disk."""
    if cache is None or not cache.has_state_changed:
        return
    try:
        _TOKEN_DIR.mkdir(parents=True, exist_ok=True)
        _MS_TOKEN_PATH.write_text(cache.serialize(), encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not save MS token cache: %s", exc)


def _acquire_token_sync() -> Optional[str]:
    """Acquire an access token synchronously (used inside run_in_executor)."""
    app = _build_app()
    if app is None:
        return None

    cache = app.token_cache

    # Try silent first (cached / refresh token)
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(_SCOPES, account=accounts[0])
        if result and "access_token" in result:
            _save_token_cache(cache)
            logger.debug("MS token acquired silently.")
            return result["access_token"]

    # Fall back to device-code flow
    logger.info("No cached MS token — starting device-code flow.")
    flow = app.initiate_device_flow(scopes=_SCOPES)
    if "user_code" not in flow:
        logger.error("Device-code flow failed to initiate: %s", flow.get("error_description", ""))
        return None

    # Print instructions so the user (or developer) can authenticate
    print(flow["message"])  # e.g. "To sign in, visit https://... and enter code XXXX"

    result = app.acquire_token_by_device_flow(flow)
    if "access_token" in result:
        _save_token_cache(cache)
        logger.info("MS OAuth device-code flow completed successfully.")
        return result["access_token"]

    logger.error(
        "MS token acquisition failed: %s — %s",
        result.get("error", "unknown"),
        result.get("error_description", ""),
    )
    return None


_WIN_TO_IANA = {
    # Existing entries
    "Eastern Standard Time": "America/New_York",
    "Eastern Daylight Time": "America/New_York",
    "Central Standard Time": "America/Chicago",
    "Central Daylight Time": "America/Chicago",
    "Mountain Standard Time": "America/Denver",
    "Mountain Daylight Time": "America/Denver",
    "Pacific Standard Time": "America/Los_Angeles",
    "Pacific Daylight Time": "America/Los_Angeles",
    "India Standard Time": "Asia/Kolkata",
    "GMT Standard Time": "Europe/London",
    "W. Europe Standard Time": "Europe/Berlin",
    "Tokyo Standard Time": "Asia/Tokyo",
    "China Standard Time": "Asia/Shanghai",
    "AUS Eastern Standard Time": "Australia/Sydney",
    # New entries
    "UTC": "UTC",
    "Romance Standard Time": "Europe/Paris",
    "Central Europe Standard Time": "Europe/Prague",
    "Central European Standard Time": "Europe/Warsaw",
    "E. Europe Standard Time": "Asia/Nicosia",
    "FLE Standard Time": "Europe/Helsinki",
    "GTB Standard Time": "Europe/Athens",
    "Turkey Standard Time": "Europe/Istanbul",
    "Russia Time Zone 3": "Europe/Moscow",
    "Russian Standard Time": "Europe/Moscow",
    "W. Central Africa Standard Time": "Africa/Lagos",
    "South Africa Standard Time": "Africa/Johannesburg",
    "Egypt Standard Time": "Africa/Cairo",
    "Arab Standard Time": "Asia/Riyadh",
    "Arabian Standard Time": "Asia/Dubai",
    "Pakistan Standard Time": "Asia/Karachi",
    "Bangladesh Standard Time": "Asia/Dhaka",
    "Sri Lanka Standard Time": "Asia/Colombo",
    "Myanmar Standard Time": "Asia/Yangon",
    "SE Asia Standard Time": "Asia/Bangkok",
    "Singapore Standard Time": "Asia/Singapore",
    "Korea Standard Time": "Asia/Seoul",
    "Taipei Standard Time": "Asia/Taipei",
    "North Asia East Standard Time": "Asia/Irkutsk",
    "Yakutsk Standard Time": "Asia/Yakutsk",
    "Vladivostok Standard Time": "Asia/Vladivostok",
    "New Zealand Standard Time": "Pacific/Auckland",
    "Fiji Standard Time": "Pacific/Fiji",
    "Tonga Standard Time": "Pacific/Tongatapu",
    "Hawaiian Standard Time": "Pacific/Honolulu",
    "Alaskan Standard Time": "America/Anchorage",
    "US Mountain Standard Time": "America/Phoenix",
    "Canada Central Standard Time": "America/Winnipeg",
    "Mexico Standard Time": "America/Mexico_City",
    "Central America Standard Time": "America/Guatemala",
    "SA Eastern Standard Time": "America/Argentina/Buenos_Aires",
    "E. South America Standard Time": "America/Sao_Paulo",
    "Atlantic Standard Time": "America/Halifax",
    "Newfoundland Standard Time": "America/St_Johns",
    "W. Australia Standard Time": "Australia/Perth",
    "Cen. Australia Standard Time": "Australia/Adelaide",
    "E. Australia Standard Time": "Australia/Brisbane",
    "Tasmania Standard Time": "Australia/Hobart",
    "Israel Standard Time": "Asia/Jerusalem",
    "Middle East Standard Time": "Asia/Beirut",
    "Ulaanbaatar Standard Time": "Asia/Ulaanbaatar",
    "Central Pacific Standard Time": "Pacific/Guadalcanal",
    "Dateline Standard Time": "Etc/GMT+12",
    "UTC-11": "Pacific/Pago_Pago",
    "UTC+12": "Etc/GMT-12",
}


def _parse_ms_datetime(dt_obj: Optional[dict]) -> Optional[datetime]:
    """Parse a Graph API dateTime object {'dateTime': '...', 'timeZone': '...'} to a datetime.

    Graph API returns naive datetime strings with a separate timeZone field (Windows or IANA name).
    We must check tz_name FIRST and attach the correct timezone, not blindly attach UTC.
    """
    if not dt_obj:
        return None
    raw = dt_obj.get("dateTime", "")
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.rstrip("Z"))
        tz_name = dt_obj.get("timeZone", "UTC")
        # Resolve timezone: UTC variants → utc, IANA name → ZoneInfo, Windows name → map
        if tz_name.upper() in ("UTC", "COORDINATED UNIVERSAL TIME", ""):
            return dt.replace(tzinfo=timezone.utc)
        # Try direct IANA lookup first
        try:
            return dt.replace(tzinfo=ZoneInfo(tz_name))
        except (ZoneInfoNotFoundError, KeyError):
            pass
        # Fall back to Windows-to-IANA mapping
        iana = _WIN_TO_IANA.get(tz_name)
        if iana:
            return dt.replace(tzinfo=ZoneInfo(iana))
        logger.warning("Unknown timezone '%s' for Graph datetime — defaulting to UTC", tz_name)
        return dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError) as exc:
        logger.warning("Could not parse MS datetime '%s': %s", raw, exc)
        return None


def _parse_event(event: dict) -> Optional[Meeting]:
    """Convert a Microsoft Graph calendar event to a Meeting model."""
    event_id = event.get("id", "")
    title = event.get("subject", "(No Title)")

    start_time = _parse_ms_datetime(event.get("start"))
    end_time = _parse_ms_datetime(event.get("end"))

    if start_time is None or end_time is None:
        logger.warning("Skipping event '%s': could not parse times.", title)
        return None

    # Attendees
    raw_attendees = event.get("attendees", [])
    attendees: list[Attendee] = []
    for raw in raw_attendees:
        email_obj = raw.get("emailAddress", {})
        email = email_obj.get("address", "")
        name = email_obj.get("name", "")
        attendee_type = raw.get("type", "required")
        is_organizer = attendee_type == "organizer"
        if not name and email:
            name = email.split("@")[0].replace(".", " ").title()
        if name or email:
            attendees.append(Attendee(name=name, email=email or None, is_organizer=is_organizer))

    # Meeting link — Teams URL from onlineMeeting, or location
    meeting_url: Optional[str] = None
    online_meeting = event.get("onlineMeeting")
    if online_meeting:
        meeting_url = online_meeting.get("joinUrl")

    location_obj = event.get("location", {})
    location: Optional[str] = None
    if isinstance(location_obj, dict):
        location = location_obj.get("displayName") or None
    elif isinstance(location_obj, str):
        location = location_obj or None

    description: Optional[str] = event.get("bodyPreview") or None

    return Meeting(
        id=event_id,
        title=title,
        start_time=start_time,
        end_time=end_time,
        attendees=attendees,
        location=location,
        description=description,
        meeting_url=meeting_url,
        calendar_link=None,
    )


def _fetch_events_sync(hours_ahead: int, hours_past: int = 0) -> list[dict]:
    """Blocking function: authenticate and fetch calendar events from Graph API."""
    if not _MSAL_AVAILABLE:
        logger.warning("msal not installed — Outlook calendar unavailable.")
        return []

    if not _HTTPX_AVAILABLE:
        logger.warning("httpx not installed — Outlook calendar unavailable.")
        return []

    token = _acquire_token_sync()
    if token is None:
        logger.warning("Could not acquire MS token — Outlook calendar unavailable.")
        return []

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=hours_past)
    end = now + timedelta(hours=hours_ahead)

    params: dict[str, str] = {
        "startDateTime": start.isoformat(),
        "endDateTime": end.isoformat(),
        "$select": "id,subject,start,end,attendees,location,onlineMeeting,bodyPreview",
        "$orderby": "start/dateTime",
        "$top": "50",
    }
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    url: Optional[str] = f"{_GRAPH_BASE}/me/calendarView"
    all_events: list[dict] = []

    with httpx.Client(timeout=30.0) as client:
        while url:
            try:
                response = client.get(url, headers=headers, params=params if url.endswith("calendarView") else None)
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPStatusError as exc:
                logger.error("Graph API error %s: %s", exc.response.status_code, exc.response.text[:200])
                break
            except Exception as exc:
                logger.error("Graph API request failed: %s", exc)
                break

            all_events.extend(data.get("value", []))
            url = data.get("@odata.nextLink")
            # nextLink already contains query params — clear local params for subsequent calls
            params = {}

    logger.info("Fetched %d events from Outlook Graph API.", len(all_events))
    return all_events


async def get_outlook_events(hours_ahead: int = 24, hours_past: int = 0) -> list[Meeting]:
    """Fetch Outlook/Microsoft 365 events spanning a window around the current time.

    Args:
        hours_ahead: How many hours into the future to fetch (default 24).
        hours_past:  How many hours into the past to include (default 0).

    Returns an empty list with a log warning if AZURE_CLIENT_ID is not configured.
    Blocking MSAL + httpx calls are executed in a thread pool.
    """
    client_id = _get_client_id()
    if not client_id:
        logger.warning(
            "AZURE_CLIENT_ID not set — Outlook Calendar is disabled. "
            "Set AZURE_CLIENT_ID (and optionally AZURE_TENANT_ID) in your .env to enable."
        )
        return []

    loop = asyncio.get_running_loop()
    raw_events: list[dict] = await loop.run_in_executor(
        None, _fetch_events_sync, hours_ahead, hours_past
    )

    meetings: list[Meeting] = []
    for event in raw_events:
        parsed = _parse_event(event)
        if parsed is not None:
            meetings.append(parsed)

    logger.info(
        "Parsed %d Outlook meetings (past %dh / ahead %dh).",
        len(meetings), hours_past, hours_ahead,
    )
    return meetings
