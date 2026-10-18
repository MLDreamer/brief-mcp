"""Shared helper utilities used by multiple brief-mcp tools.

Canonical implementations of _find_meeting and _research_attendee_with_cache
live here so that crm_tool, outlook_tool, and debrief_tool do not each carry
their own copy.
"""

import logging
from typing import Optional

from cachetools import TTLCache

from ..cache import get_cached_profile, set_cached_profile
from ..integrations.web_search import research_person
from ..models import Meeting

logger = logging.getLogger(__name__)

# Short-lived negative cache: prevents hammering the search API for people
# with no public web presence. Entries expire after 5 minutes so a retry
# happens soon without flooding the API on every brief call.
_negative_cache: TTLCache = TTLCache(maxsize=256, ttl=300)


def _find_meeting(meetings: list[Meeting], title: str = "", meeting_id: str = "") -> Optional[Meeting]:
    """Find a meeting by partial title match or exact ID."""
    if meeting_id:
        for m in meetings:
            if m.id == meeting_id:
                return m

    if title:
        title_lower = title.lower()
        # Exact match first
        for m in meetings:
            if m.title.lower() == title_lower:
                return m
        # Partial match
        for m in meetings:
            if title_lower in m.title.lower():
                return m

    return None


async def _research_attendee_with_cache(name: str, company: str = "") -> object:
    """Research a single attendee, using cache if available."""
    cached = get_cached_profile(name, company)
    if cached is not None:
        return cached

    neg_key = f"{name.lower().strip()}:{company.lower().strip()}"
    if neg_key in _negative_cache:
        from ..models import PersonProfile
        return PersonProfile(name=name, company=company or None)

    try:
        profile = await research_person(name, company)
        if profile.research_sources:
            set_cached_profile(profile)
        else:
            _negative_cache[neg_key] = True
        return profile
    except Exception as exc:
        logger.warning("Research failed for '%s': %s", name, exc)
        from ..models import PersonProfile
        return PersonProfile(name=name, company=company or None)
