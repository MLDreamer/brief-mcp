"""TTL-based cache to avoid re-researching the same person within 60 minutes."""

import logging
from datetime import datetime, timezone
from typing import Optional

from cachetools import TTLCache

from .models import PersonProfile

logger = logging.getLogger(__name__)

# Default TTL: 60 minutes (3600 seconds)
# Default max size: 256 entries
_DEFAULT_TTL = 3600
_DEFAULT_MAXSIZE = 256

# Module-level cache instance (shared across the process)
_profile_cache: TTLCache = TTLCache(maxsize=_DEFAULT_MAXSIZE, ttl=_DEFAULT_TTL)


def get_cached_profile(name: str, company: str = "") -> Optional[PersonProfile]:
    """Return a cached PersonProfile, or None if not cached / expired."""
    key = _make_key(name, company)
    profile = _profile_cache.get(key)
    if profile is not None:
        age_seconds = (datetime.now(timezone.utc) - profile.research_timestamp).total_seconds()
        logger.debug("Cache HIT for '%s' (%.0fs old)", name, age_seconds)
    return profile


def set_cached_profile(profile: PersonProfile) -> None:
    """Store a PersonProfile in the TTL cache.

    Indexes under both name+company and name-only keys so callers that
    don't know the company (e.g. calendar lookups) still get a cache hit.
    """
    key = _make_key(profile.name, profile.company or "")
    _profile_cache[key] = profile
    # Also store under name-only key so get_cached_profile(name, "") always hits
    if profile.company:
        name_only_key = _make_key(profile.name, "")
        existing = _profile_cache.get(name_only_key)
        # Write name-only key if: no entry yet, OR same company is refreshing its own entry.
        # Never overwrite a different company's entry — that causes same-name collisions.
        if existing is None or existing.company == profile.company:
            _profile_cache[name_only_key] = profile
    logger.debug("Cache SET for '%s'", profile.name)


def invalidate_profile(name: str, company: str = "") -> bool:
    """Remove a profile from cache. Returns True if it was present."""
    key = _make_key(name, company)
    if key in _profile_cache:
        del _profile_cache[key]
        logger.debug("Cache EVICT for '%s'", name)
        return True
    return False


def clear_cache() -> int:
    """Clear all cached profiles. Returns the number of entries cleared."""
    count = len(_profile_cache)
    _profile_cache.clear()
    logger.info("Cache cleared (%d entries removed)", count)
    return count


def cache_stats() -> dict:
    """Return current cache statistics."""
    return {
        "size": len(_profile_cache),
        "maxsize": _profile_cache.maxsize,
        "ttl_seconds": _profile_cache.ttl,
        "keys": list(_profile_cache.keys()),
    }


def configure_cache(ttl_seconds: int = _DEFAULT_TTL, maxsize: int = _DEFAULT_MAXSIZE) -> None:
    """Reconfigure the cache (replaces existing cache, clears all entries)."""
    global _profile_cache
    _profile_cache = TTLCache(maxsize=maxsize, ttl=ttl_seconds)
    logger.info("Cache reconfigured: ttl=%ds maxsize=%d", ttl_seconds, maxsize)


def _make_key(name: str, company: str) -> str:
    """Create a normalized cache key from name + company."""
    name_slug = name.strip().lower().replace(" ", "_")
    company_slug = company.strip().lower().replace(" ", "_")
    return f"{name_slug}__{company_slug}"
