"""Optional Gmail integration for prior email context.

Adds the gmail.readonly scope and looks up prior email threads with a
given attendee to surface relationship context in meeting briefs.

Enable by setting BRIEF_MCP_GMAIL_ENABLED=true in your .env file.
Requires the credentials.json OAuth2 flow to complete with the gmail scope.
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

GMAIL_ENABLED = os.getenv("BRIEF_MCP_GMAIL_ENABLED", "false").lower() == "true"
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"

try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError

    _GOOGLE_AVAILABLE = True
except ImportError:
    _GOOGLE_AVAILABLE = False


async def get_email_context(
    email: str,
    creds: object,
    days_back: int = 90,
    max_threads: int = 5,
) -> list[str]:
    """Return a list of recent email subject lines with this person.

    Returns an empty list if Gmail is not enabled or credentials are unavailable.
    This is a best-effort enrichment — failures are logged, not raised.
    """
    if not GMAIL_ENABLED:
        logger.debug("Gmail integration disabled (BRIEF_MCP_GMAIL_ENABLED != true)")
        return []

    if not _GOOGLE_AVAILABLE:
        logger.warning("Gmail integration requires google-api-python-client.")
        return []

    if not email:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    query = f"from:{email} OR to:{email} after:{cutoff.strftime('%Y/%m/%d')}"

    def _fetch() -> list[str]:
        try:
            service = build("gmail", "v1", credentials=creds, cache_discovery=False)
            result = (
                service.users()
                .threads()
                .list(userId="me", q=query, maxResults=max_threads)
                .execute()
            )
            threads = result.get("threads", [])
            subjects: list[str] = []
            for thread in threads:
                thread_data = (
                    service.users()
                    .threads()
                    .get(userId="me", id=thread["id"], format="metadata", metadataHeaders=["Subject"])
                    .execute()
                )
                msgs = thread_data.get("messages", [])
                if msgs:
                    headers = msgs[0].get("payload", {}).get("headers", [])
                    for h in headers:
                        if h.get("name", "").lower() == "subject":
                            subjects.append(h.get("value", ""))
                            break
            return subjects
        except HttpError as exc:
            logger.warning("Gmail API error for %s: %s", email, exc)
            return []
        except Exception as exc:
            logger.warning("Gmail fetch failed for %s: %s", email, exc)
            return []

    subjects = await asyncio.get_event_loop().run_in_executor(None, _fetch)
    if subjects:
        logger.info("Gmail: found %d prior threads with %s", len(subjects), email)
    return subjects


def gmail_scope() -> Optional[str]:
    """Return the Gmail scope string if Gmail is enabled, else None."""
    return GMAIL_SCOPE if GMAIL_ENABLED else None
