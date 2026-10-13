"""Tests for the HubSpot CRM integration (brief_mcp.integrations.hubspot).

All tests are fully offline: httpx.AsyncClient is mocked so no real HTTP
requests are made and no HUBSPOT_API_KEY is required.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.brief_mcp.integrations.hubspot import (
    HubSpotContact,
    HubSpotDeal,
    get_crm_context,
    search_contact,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _mock_post_response(results: list) -> MagicMock:
    """Build a fake successful POST response containing the given contact results."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"results": results}
    return resp


def _mock_get_response(body: dict) -> MagicMock:
    """Build a fake successful GET response with the given body."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = body
    return resp


def _mock_error_response(status_code: int) -> MagicMock:
    """Build a fake HTTP error response."""
    err_resp = MagicMock()
    err_resp.status_code = status_code
    err_resp.text = f"HTTP {status_code} error"
    resp = MagicMock()
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        f"HTTP error {status_code}",
        request=MagicMock(),
        response=err_resp,
    )
    return resp


def _make_async_client_mock(post_resp=None, get_responses=None):
    """Return a context-manager-compatible AsyncMock for httpx.AsyncClient."""
    mock_client = AsyncMock()
    if post_resp is not None:
        mock_client.post = AsyncMock(return_value=post_resp)
    if get_responses is not None:
        mock_client.get = AsyncMock(side_effect=get_responses)
    else:
        mock_client.get = AsyncMock(return_value=_mock_get_response({"results": []}))

    async_ctx = MagicMock()
    async_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    async_ctx.__aexit__ = AsyncMock(return_value=False)
    return async_ctx


# ── Model tests ───────────────────────────────────────────────────────────────


class TestHubSpotModels:
    def test_hubspot_contact_model(self):
        """HubSpotContact and HubSpotDeal validate correctly via Pydantic."""
        deal = HubSpotDeal(
            name="Big Enterprise Deal",
            stage="proposal",
            amount=75000.0,
            close_date=datetime(2026, 12, 31, tzinfo=timezone.utc),
        )
        contact = HubSpotContact(
            name="Jane Doe",
            email="jane@acme.com",
            company="Acme Corp",
            job_title="VP Sales",
            lifecycle_stage="customer",
            deals=[deal],
        )
        assert contact.name == "Jane Doe"
        assert contact.email == "jane@acme.com"
        assert contact.company == "Acme Corp"
        assert len(contact.deals) == 1
        assert contact.deals[0].amount == 75000.0
        assert contact.deals[0].stage == "proposal"

    def test_hubspot_contact_defaults(self):
        """HubSpotContact fields default to None/empty-list when not provided."""
        contact = HubSpotContact(name="Minimal Person")
        assert contact.email is None
        assert contact.company is None
        assert contact.deals == []
        assert contact.notes == []

    def test_hubspot_deal_optional_fields(self):
        """HubSpotDeal can be created with just a name."""
        deal = HubSpotDeal(name="Unnamed Opportunity")
        assert deal.name == "Unnamed Opportunity"
        assert deal.stage is None
        assert deal.amount is None


# ── search_contact ────────────────────────────────────────────────────────────


class TestSearchContact:
    async def test_search_contact_no_api_key(self):
        """When HUBSPOT_API_KEY is not set, search_contact returns None without crashing."""
        with patch("src.brief_mcp.integrations.hubspot._get_api_key", return_value=""):
            result = await search_contact(name="Alice Smith", email="alice@acme.com")
        assert result is None

    async def test_search_contact_not_found(self):
        """A 200 response with empty results → returns None."""
        async_ctx = _make_async_client_mock(
            post_resp=_mock_post_response(results=[]),
        )
        with patch("src.brief_mcp.integrations.hubspot._get_api_key", return_value="test-key"), \
             patch("src.brief_mcp.integrations.hubspot.httpx.AsyncClient", return_value=async_ctx):
            result = await search_contact(name="Ghost Person", email="ghost@nowhere.com")
        assert result is None

    async def test_search_contact_by_email_success(self, sample_hs_contact_obj):
        """Successful email search returns a HubSpotContact with expected fields."""
        # No deals associated
        assoc_resp = _mock_get_response({"results": []})
        async_ctx = _make_async_client_mock(
            post_resp=_mock_post_response(results=[sample_hs_contact_obj]),
            get_responses=[assoc_resp],
        )
        with patch("src.brief_mcp.integrations.hubspot._get_api_key", return_value="test-key"), \
             patch("src.brief_mcp.integrations.hubspot.httpx.AsyncClient", return_value=async_ctx):
            result = await search_contact(email="jane.doe@acme.com")

        assert result is not None
        assert result.name == "Jane Doe"
        assert result.email == "jane.doe@acme.com"
        assert result.company == "Acme Corp"
        assert result.job_title == "VP Sales"
        assert result.lifecycle_stage == "customer"

    async def test_search_contact_api_error(self):
        """A 401 HTTP error from the API → search_contact returns None, logs warning."""
        async_ctx = _make_async_client_mock(
            post_resp=_mock_error_response(401),
        )
        with patch("src.brief_mcp.integrations.hubspot._get_api_key", return_value="bad-key"), \
             patch("src.brief_mcp.integrations.hubspot.httpx.AsyncClient", return_value=async_ctx):
            result = await search_contact(name="Alice")
        assert result is None

    async def test_search_contact_with_deals(self, sample_hs_contact_obj, sample_hs_deal_obj):
        """Contact with 2 associated deals → both deals returned on the contact."""
        # Associations endpoint returns 2 deal IDs
        assoc_resp = _mock_get_response({
            "results": [{"id": "deal_001"}, {"id": "deal_002"}]
        })
        # Individual deal fetches
        deal_resp_1 = _mock_get_response({
            "id": "deal_001",
            "properties": {
                "dealname": "Deal Alpha",
                "dealstage": "closed_won",
                "amount": "50000",
                "closedate": None,
                "notes_last_updated": None,
            },
        })
        deal_resp_2 = _mock_get_response({
            "id": "deal_002",
            "properties": {
                "dealname": "Deal Beta",
                "dealstage": "proposal",
                "amount": "25000",
                "closedate": None,
                "notes_last_updated": None,
            },
        })
        async_ctx = _make_async_client_mock(
            post_resp=_mock_post_response(results=[sample_hs_contact_obj]),
            get_responses=[assoc_resp, deal_resp_1, deal_resp_2],
        )
        with patch("src.brief_mcp.integrations.hubspot._get_api_key", return_value="test-key"), \
             patch("src.brief_mcp.integrations.hubspot.httpx.AsyncClient", return_value=async_ctx):
            result = await search_contact(email="jane.doe@acme.com")

        assert result is not None
        assert len(result.deals) == 2
        deal_names = {d.name for d in result.deals}
        assert "Deal Alpha" in deal_names
        assert "Deal Beta" in deal_names


# ── get_crm_context ───────────────────────────────────────────────────────────


class TestGetCrmContext:
    async def test_get_crm_context_found(self, sample_hs_contact_obj, sample_hs_deal_obj):
        """When a contact is found, returns a formatted string with name/company/deal."""
        assoc_resp = _mock_get_response({"results": [{"id": "deal_001"}]})
        deal_resp = _mock_get_response({
            "id": "deal_001",
            "properties": {
                "dealname": "Acme Enterprise Deal",
                "dealstage": "proposal",
                "amount": "75000",
                "closedate": "2026-12-31T00:00:00.000Z",
                "notes_last_updated": None,
            },
        })
        async_ctx = _make_async_client_mock(
            post_resp=_mock_post_response(results=[sample_hs_contact_obj]),
            get_responses=[assoc_resp, deal_resp],
        )
        with patch("src.brief_mcp.integrations.hubspot._get_api_key", return_value="test-key"), \
             patch("src.brief_mcp.integrations.hubspot.httpx.AsyncClient", return_value=async_ctx):
            result = await get_crm_context(name="Jane Doe", email="jane.doe@acme.com")

        assert "Jane Doe" in result
        assert "Acme Corp" in result
        assert "VP Sales" in result
        # Deal info included
        assert "Acme Enterprise Deal" in result

    async def test_get_crm_context_not_found(self):
        """When no contact matches, returns a 'No CRM record found' message."""
        async_ctx = _make_async_client_mock(
            post_resp=_mock_post_response(results=[]),
        )
        with patch("src.brief_mcp.integrations.hubspot._get_api_key", return_value="test-key"), \
             patch("src.brief_mcp.integrations.hubspot.httpx.AsyncClient", return_value=async_ctx):
            result = await get_crm_context(name="Ghost Person")

        assert "No CRM record found" in result
        assert "Ghost Person" in result

    async def test_get_crm_context_no_api_key(self):
        """Without HUBSPOT_API_KEY, returns an informative message (no crash)."""
        with patch("src.brief_mcp.integrations.hubspot._get_api_key", return_value=""):
            result = await get_crm_context(name="Anyone")

        assert "HUBSPOT_API_KEY" in result
        assert "Anyone" in result
