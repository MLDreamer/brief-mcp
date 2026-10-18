"""Tests for CRM MCP tools (brief_mcp.tools.crm_tool).

Covers: get_crm_context (MCP tool), enrich_brief_with_crm.

All tests mock HubSpot API calls and Google Calendar to run offline.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import FastMCP

from src.brief_mcp.cache import clear_cache
from src.brief_mcp.models import PersonProfile
from src.brief_mcp.tools.crm_tool import register_crm_tools


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_text(result) -> str:
    """Extract the string text from a FastMCP ToolResult."""
    return result.content[0].text


def _make_mcp():
    """Create a fresh FastMCP instance with CRM tools registered."""
    mcp = FastMCP("test-crm")
    register_crm_tools(mcp)
    return mcp


# ── get_crm_context tool ──────────────────────────────────────────────────────


class TestGetCrmContextTool:
    async def test_get_crm_context_tool_no_key(self):
        """When no HUBSPOT_API_KEY is set, returns a helpful error message."""
        mcp = _make_mcp()
        with patch(
            "src.brief_mcp.integrations.hubspot._get_api_key",
            return_value="",
        ):
            result = await mcp.call_tool(
                "get_crm_context",
                {"name": "Alice Smith"},
            )

        assert not result.is_error
        text = _get_text(result)
        assert "HUBSPOT_API_KEY" in text

    async def test_get_crm_context_tool_found(self):
        """When HubSpot returns a contact, get_crm_context returns formatted context string."""
        crm_text = (
            "CRM Profile: Alice Smith\n"
            "  Role: VP Sales @ Acme Corp\n"
            "  Email: alice@acme.com\n"
            "  Lifecycle Stage: Customer\n"
            "  Deals (1):\n"
            "    - Big Deal [Proposal] — $50,000"
        )
        mcp = _make_mcp()
        with patch(
            "src.brief_mcp.tools.crm_tool._hubspot_crm_context",
            new_callable=AsyncMock,
            return_value=crm_text,
        ):
            result = await mcp.call_tool(
                "get_crm_context",
                {"name": "Alice Smith", "email": "alice@acme.com"},
            )

        assert not result.is_error
        text = _get_text(result)
        assert "Alice Smith" in text
        assert "Acme Corp" in text
        assert "Big Deal" in text

    async def test_get_crm_context_tool_empty_name(self):
        """Calling get_crm_context without a name returns an error message."""
        mcp = _make_mcp()
        result = await mcp.call_tool("get_crm_context", {"name": ""})
        assert not result.is_error
        text = _get_text(result)
        assert "name" in text.lower() or "provide" in text.lower()


# ── enrich_brief_with_crm tool ────────────────────────────────────────────────


class TestEnrichBriefWithCrmTool:
    def setup_method(self):
        clear_cache()

    async def test_enrich_brief_with_crm_no_calendar(self):
        """When Google Calendar raises an exception, returns a graceful error message."""
        mcp = _make_mcp()
        with patch(
            "src.brief_mcp.tools.crm_tool.get_upcoming_events",
            new_callable=AsyncMock,
            side_effect=Exception("Google Calendar not configured"),
        ):
            result = await mcp.call_tool(
                "enrich_brief_with_crm",
                {"meeting_title": "Any Meeting"},
            )

        assert not result.is_error
        text = _get_text(result)
        assert "Failed to fetch calendar" in text

    async def test_enrich_brief_with_crm_meeting_not_found(self):
        """When no meeting matches the title, returns a helpful error."""
        mcp = _make_mcp()
        with patch(
            "src.brief_mcp.tools.crm_tool.get_upcoming_events",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await mcp.call_tool(
                "enrich_brief_with_crm",
                {"meeting_title": "Totally Nonexistent XYZ"},
            )

        assert not result.is_error
        text = _get_text(result)
        assert "not found" in text.lower() or "Meeting not found" in text

    async def test_enrich_brief_with_crm_no_crm_key(self, sample_meeting):
        """When HUBSPOT_API_KEY is absent, brief still works but CRM section is absent."""
        mcp = _make_mcp()
        with patch(
            "src.brief_mcp.tools.crm_tool.get_upcoming_events",
            new_callable=AsyncMock,
            return_value=[sample_meeting],
        ), patch(
            "src.brief_mcp.tools._shared.research_person",
            new_callable=AsyncMock,
            return_value=PersonProfile(name="Bob Patel", company="PartnerCo"),
        ), patch(
            "src.brief_mcp.tools.crm_tool._hubspot_crm_context",
            new_callable=AsyncMock,
            return_value=(
                "CRM context unavailable for Bob Patel: HUBSPOT_API_KEY not configured."
            ),
        ):
            result = await mcp.call_tool(
                "enrich_brief_with_crm",
                {"meeting_title": "Q4 Partnership Review"},
            )

        assert not result.is_error
        text = _get_text(result)
        # The meeting brief card should be present
        assert "Q4 PARTNERSHIP REVIEW" in text
        # CRM section should indicate no records found
        assert "No HubSpot records found" in text

    async def test_enrich_brief_with_crm_found(self, sample_meeting):
        """When HubSpot returns contact data, the CRM section is appended to the brief."""
        crm_context = (
            "CRM Profile: Bob Patel\n"
            "  Role: VP Engineering @ PartnerCo\n"
            "  Deals (1):\n"
            "    - PartnerCo Integration Deal [Negotiation] — $120,000"
        )
        mcp = _make_mcp()
        with patch(
            "src.brief_mcp.tools.crm_tool.get_upcoming_events",
            new_callable=AsyncMock,
            return_value=[sample_meeting],
        ), patch(
            "src.brief_mcp.tools._shared.research_person",
            new_callable=AsyncMock,
            return_value=PersonProfile(name="Bob Patel", company="PartnerCo"),
        ), patch(
            "src.brief_mcp.tools.crm_tool._hubspot_crm_context",
            new_callable=AsyncMock,
            return_value=crm_context,
        ):
            result = await mcp.call_tool(
                "enrich_brief_with_crm",
                {"meeting_title": "Q4 Partnership Review"},
            )

        assert not result.is_error
        text = _get_text(result)
        assert "Q4 PARTNERSHIP REVIEW" in text
        assert "CRM CONTEXT" in text
        assert "PartnerCo Integration Deal" in text

    async def test_enrich_brief_with_crm_empty_title(self):
        """Calling enrich_brief_with_crm without a title returns an error."""
        mcp = _make_mcp()
        result = await mcp.call_tool(
            "enrich_brief_with_crm",
            {"meeting_title": ""},
        )
        assert not result.is_error
        text = _get_text(result)
        assert "meeting_title" in text.lower() or "provide" in text.lower()

    async def test_crm_error_not_shown_as_crm_data(self, sample_meeting):
        """CRM error strings (e.g. 429 Too Many Requests) must NOT appear as CRM data."""
        mcp = _make_mcp()
        with patch(
            "src.brief_mcp.tools.crm_tool.get_upcoming_events",
            new_callable=AsyncMock,
            return_value=[sample_meeting],
        ), patch(
            "src.brief_mcp.tools._shared.research_person",
            new_callable=AsyncMock,
            return_value=PersonProfile(name="Bob Patel", company="PartnerCo"),
        ), patch(
            "src.brief_mcp.tools.crm_tool._hubspot_crm_context",
            new_callable=AsyncMock,
            return_value="CRM error for Bob Patel: 429 Too Many Requests",
        ):
            result = await mcp.call_tool(
                "enrich_brief_with_crm",
                {"meeting_title": "Q4 Partnership Review"},
            )

        assert not result.is_error
        text = _get_text(result)
        assert "Too Many Requests" not in text
        assert "CRM error" not in text
        # The section should fall back to the "no records found" message
        assert "No HubSpot records found" in text
