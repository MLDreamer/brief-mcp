"""Extended tests for the TTL cache module (brief_mcp.cache).

Focuses on the dual-index behaviour added in v0.2: when a profile has a company,
``set_cached_profile`` stores it under both the name+company key AND a name-only
key so callers that don't know the company still get a cache hit.

All tests call ``clear_cache()`` / ``configure_cache()`` in setup so they are
fully isolated from each other.
"""

import pytest

from src.brief_mcp.cache import (
    cache_stats,
    clear_cache,
    configure_cache,
    get_cached_profile,
    invalidate_profile,
    set_cached_profile,
)
from src.brief_mcp.models import PersonProfile


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def profile_with_company() -> PersonProfile:
    return PersonProfile(
        name="Heather Grant",
        current_role="CTO",
        company="TechStartup Inc",
    )


@pytest.fixture
def profile_no_company() -> PersonProfile:
    return PersonProfile(
        name="Ivan Torres",
        current_role="Freelance Consultant",
        company=None,
    )


# ── Dual-index lookup tests ───────────────────────────────────────────────────


class TestDualIndexCache:
    def setup_method(self):
        clear_cache()

    def test_dual_index_name_only_lookup(self, profile_with_company):
        """Save profile with company; retrieve with empty company → cache HIT."""
        set_cached_profile(profile_with_company)

        result = get_cached_profile("Heather Grant", "")
        assert result is not None
        assert result.name == "Heather Grant"

    def test_dual_index_full_key_still_works(self, profile_with_company):
        """Save with company; retrieve with same company string → still HIT."""
        set_cached_profile(profile_with_company)

        result = get_cached_profile("Heather Grant", "TechStartup Inc")
        assert result is not None
        assert result.name == "Heather Grant"

    def test_no_company_profile_only_one_key(self, profile_no_company):
        """Profile without a company creates only one cache entry (no dual-index)."""
        set_cached_profile(profile_no_company)
        stats = cache_stats()
        assert stats["size"] == 1

    def test_dual_index_different_profiles_independent(
        self, profile_with_company, profile_no_company
    ):
        """Dual-indexed and single-indexed profiles coexist without clobbering each other."""
        set_cached_profile(profile_with_company)  # 2 entries
        set_cached_profile(profile_no_company)  # 1 entry
        stats = cache_stats()
        assert stats["size"] == 3

        assert get_cached_profile("Heather Grant", "") is not None
        assert get_cached_profile("Ivan Torres", "") is not None


# ── cache_stats tests ─────────────────────────────────────────────────────────


class TestCacheStatsDualIndex:
    def setup_method(self):
        clear_cache()

    def test_cache_stats_reflects_dual_index(self, profile_with_company):
        """Saving 1 profile with company creates exactly 2 cache entries."""
        set_cached_profile(profile_with_company)
        stats = cache_stats()
        assert stats["size"] == 2

    def test_cache_stats_keys_include_both(self, profile_with_company):
        """cache_stats().keys lists both the full key and the name-only key."""
        set_cached_profile(profile_with_company)
        keys = cache_stats()["keys"]
        # name+company key
        assert "heather_grant__techstartup_inc" in keys
        # name-only key
        assert "heather_grant__" in keys

    def test_cache_stats_maxsize_and_ttl_defaults(self):
        """cache_stats() reports the expected default maxsize and TTL."""
        stats = cache_stats()
        assert stats["maxsize"] == 256
        assert stats["ttl_seconds"] == 3600


# ── configure_cache tests ─────────────────────────────────────────────────────


class TestConfigureCache:
    def setup_method(self):
        clear_cache()

    def test_configure_cache_clears_entries(
        self, profile_with_company, sample_profile_bob
    ):
        """Saving profiles then calling configure_cache() removes all entries."""
        set_cached_profile(profile_with_company)
        set_cached_profile(sample_profile_bob)
        assert cache_stats()["size"] > 0

        configure_cache()  # uses default TTL/maxsize, replaces cache

        assert cache_stats()["size"] == 0

    def test_configure_cache_new_settings_take_effect(self):
        """configure_cache with custom TTL/maxsize is reflected in stats."""
        configure_cache(ttl_seconds=120, maxsize=50)
        stats = cache_stats()
        assert stats["ttl_seconds"] == 120
        assert stats["maxsize"] == 50
        # Reset to defaults for other tests
        configure_cache()


# ── invalidate_profile tests ──────────────────────────────────────────────────


class TestInvalidateProfile:
    def setup_method(self):
        clear_cache()

    def test_invalidate_by_name_only(self, profile_with_company):
        """invalidate_profile with empty company removes the name-only key."""
        set_cached_profile(profile_with_company)
        # Should have 2 entries
        assert cache_stats()["size"] == 2

        # Invalidate via name-only key
        result = invalidate_profile("Heather Grant", "")
        assert result is True

        # Name-only lookup should miss now
        assert get_cached_profile("Heather Grant", "") is None

    def test_invalidate_by_full_key(self, profile_with_company):
        """invalidate_profile with company removes the name+company key."""
        set_cached_profile(profile_with_company)

        result = invalidate_profile("Heather Grant", "TechStartup Inc")
        assert result is True

        assert get_cached_profile("Heather Grant", "TechStartup Inc") is None

    def test_invalidate_nonexistent_key_returns_false(self):
        """Invalidating a key that was never stored returns False."""
        result = invalidate_profile("Ghost Person XYZ", "")
        assert result is False

    def test_invalidate_by_name_only_full_key_still_present(self, profile_with_company):
        """Removing the name-only key does not affect the name+company key."""
        set_cached_profile(profile_with_company)

        invalidate_profile("Heather Grant", "")  # Remove name-only key

        # Full key is still present
        found = get_cached_profile("Heather Grant", "TechStartup Inc")
        assert found is not None
