"""Tests for debrief + meeting-memory MCP tools (brief_mcp.tools.debrief_tool).

Covers: debrief_meeting, search_meeting_history, get_person_history,
get_open_action_items, brief_with_history.

All tests use the ``memory_db`` fixture (from conftest.py) to redirect
SQLite storage to a pytest tmp_path, and mock external API calls.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import FastMCP

from src.brief_mcp.cache import clear_cache
from src.brief_mcp.models import PersonProfile
from src.brief_mcp.tools.debrief_tool import (
    _format_action_items_list,
    _parse_action_items_from_text,
    register_debrief_tools,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_text(result) -> str:
    """Extract the string text from a FastMCP ToolResult."""
    return result.content[0].text


def _make_mcp(memory_db_fixture=None):
    """Create a fresh FastMCP instance with debrief tools registered."""
    mcp = FastMCP("test-debrief")
    register_debrief_tools(mcp)
    return mcp


# ── Helper function tests (no MCP needed) ────────────────────────────────────


class TestParseActionItemsFromText:
    def test_extracts_todo_marker(self):
        """Lines with TODO: prefix are parsed as action items."""
        notes = "Good meeting.\nTODO: Alice to send the report by Friday.\nSee you next week."
        items = _parse_action_items_from_text(notes)
        assert len(items) >= 1
        tasks = [i["task"] for i in items]
        assert any("report" in t.lower() for t in tasks)

    def test_ai_marker_not_extracted_without_colon(self):
        """Bare AI keyword without colon must NOT be extracted (false-positive fix)."""
        notes = "Our AI strategy is gaining momentum. AI adoption is accelerating."
        items = _parse_action_items_from_text(notes)
        assert len(items) == 0  # "AI" alone must not match

    def test_extracts_action_marker(self):
        """Lines with ACTION: prefix are parsed."""
        notes = "Discussion complete.\nACTION: Carol to review the contract."
        items = _parse_action_items_from_text(notes)
        assert len(items) >= 1
        assert any("contract" in i["task"].lower() for i in items)

    def test_empty_text_returns_empty(self):
        """Empty or whitespace-only notes return an empty list."""
        assert _parse_action_items_from_text("") == []
        assert _parse_action_items_from_text("   ") == []

    def test_no_markers_returns_empty(self):
        """Text without any action markers returns an empty list."""
        # Avoid the words ACTION/TODO/AI/FOLLOW-UP which trigger the regex
        notes = "Great session. Many topics covered. Nothing to track here."
        items = _parse_action_items_from_text(notes)
        assert len(items) == 0


class TestFormatActionItemsList:
    def test_formats_dict_items(self):
        items = [
            {"owner": "Alice", "task": "Write spec", "due_date": "2026-11-01"},
            {"owner": "Bob", "task": "Review code", "due_date": ""},
        ]
        result = _format_action_items_list(items)
        assert "Write spec" in result
        assert "Alice" in result
        assert "Review code" in result

    def test_formats_string_items(self):
        items = ["Send the invoice", "Follow up with client"]
        result = _format_action_items_list(items)
        assert "Send the invoice" in result
        assert "Follow up with client" in result

    def test_empty_list_returns_no_items_message(self):
        result = _format_action_items_list([])
        assert "No action items" in result


# ── debrief_meeting tool ──────────────────────────────────────────────────────


class TestDebriefMeetingTool:
    def setup_method(self):
        clear_cache()

    async def test_debrief_meeting_returns_card(self, memory_db):
        """debrief_meeting with notes returns a formatted card string."""
        mcp = _make_mcp()
        with patch(
            "src.brief_mcp.tools.debrief_tool.get_upcoming_events",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await mcp.call_tool(
                "debrief_meeting",
                {
                    "meeting_title": "Q4 Planning Session",
                    "notes": "Discussed budget allocation.\nTODO: Alice to prepare budget doc.",
                },
            )

        assert not result.is_error
        text = _get_text(result)
        assert "Q4 Planning Session" in text
        assert "MEETING DEBRIEF" in text

    async def test_debrief_meeting_saves_to_memory(self, memory_db):
        """After debrief_meeting, the record appears in the memory DB via search."""
        from src.brief_mcp.memory import search_meetings

        mcp = _make_mcp()
        with patch(
            "src.brief_mcp.tools.debrief_tool.get_upcoming_events",
            new_callable=AsyncMock,
            return_value=[],
        ):
            await mcp.call_tool(
                "debrief_meeting",
                {
                    "meeting_title": "Memory Persistence Check",
                    "notes": "We aligned on the roadmap priorities for next quarter.",
                },
            )

        results = search_meetings("Memory Persistence Check")
        assert len(results) >= 1
        assert results[0]["title"] == "Memory Persistence Check"

    async def test_debrief_extracts_action_items_from_notes(self, memory_db):
        """Raw notes containing TODO:/AI: markers → action items extracted automatically."""
        mcp = _make_mcp()
        with patch(
            "src.brief_mcp.tools.debrief_tool.get_upcoming_events",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await mcp.call_tool(
                "debrief_meeting",
                {
                    "meeting_title": "Action Extraction Test",
                    "notes": (
                        "Great session today.\n"
                        "TODO: Bob to send the contract draft by Monday.\n"
                        "AI: Alice will schedule the technical review."
                    ),
                },
            )

        assert not result.is_error
        text = _get_text(result)
        # Action items section should be present (not "None recorded")
        assert "Action Items" in text
        # The extracted tasks should appear in the output
        assert "contract" in text.lower() or "Bob" in text
        assert "Alice" in text or "technical review" in text.lower()

    async def test_debrief_meeting_no_title_returns_error(self, memory_db):
        """Calling debrief_meeting without a title returns an error message."""
        mcp = _make_mcp()
        with patch(
            "src.brief_mcp.tools.debrief_tool.get_upcoming_events",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await mcp.call_tool(
                "debrief_meeting",
                {"meeting_title": "", "notes": "Some notes"},
            )
        text = _get_text(result)
        assert "meeting_title" in text.lower() or "Please provide" in text

    async def test_debrief_meeting_no_notes_returns_error(self, memory_db):
        """Calling debrief_meeting without notes returns an error message."""
        mcp = _make_mcp()
        with patch(
            "src.brief_mcp.tools.debrief_tool.get_upcoming_events",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await mcp.call_tool(
                "debrief_meeting",
                {"meeting_title": "Test Meeting", "notes": ""},
            )
        text = _get_text(result)
        assert "notes" in text.lower() or "Please provide" in text

    async def test_owner_is_single_word_not_two(self, memory_db):
        """@Alice send X → owner=Alice, task=send X (not owner=Alice send, task=X)"""
        mcp = _make_mcp()
        with patch(
            "src.brief_mcp.tools.debrief_tool.get_upcoming_events",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await mcp.call_tool(
                "debrief_meeting",
                {
                    "meeting_title": "Owner Regex Test",
                    "notes": "ACTION: @Alice send the spec by Friday",
                },
            )
        assert not result.is_error
        text = _get_text(result)
        # "send" must appear in the output (it's part of the task, not the owner)
        assert "send" in text.lower()
        # "Alice send" must NOT appear as the owner value in the action items section
        assert "owner: Alice send" not in text.lower()


# ── search_meeting_history tool ───────────────────────────────────────────────


class TestSearchMeetingHistoryTool:
    async def test_search_meeting_history_finds_record(self, memory_db):
        """After debrief_meeting, search_meeting_history finds the saved record."""
        mcp = _make_mcp()
        with patch(
            "src.brief_mcp.tools.debrief_tool.get_upcoming_events",
            new_callable=AsyncMock,
            return_value=[],
        ):
            # Save a meeting via debrief
            await mcp.call_tool(
                "debrief_meeting",
                {
                    "meeting_title": "Findable Meeting Title XYZ",
                    "notes": "Discussed revenue strategy and go-to-market.",
                },
            )
            # Search for it
            result = await mcp.call_tool(
                "search_meeting_history",
                {"query": "Findable Meeting Title XYZ"},
            )

        assert not result.is_error
        text = _get_text(result)
        assert "Findable Meeting Title XYZ" in text

    async def test_search_meeting_history_no_results(self, memory_db):
        """Searching for something not in memory returns a 'not found' message."""
        mcp = _make_mcp()
        result = await mcp.call_tool(
            "search_meeting_history",
            {"query": "absolutely-nonexistent-topic-abc-xyz-9999"},
        )
        text = _get_text(result)
        assert "No past meetings found" in text or "not found" in text.lower()

    async def test_search_meeting_history_empty_query(self, memory_db):
        """Calling search_meeting_history without a query returns an error message."""
        mcp = _make_mcp()
        result = await mcp.call_tool(
            "search_meeting_history",
            {"query": ""},
        )
        text = _get_text(result)
        assert "provide" in text.lower() or "query" in text.lower()


# ── get_person_history tool ───────────────────────────────────────────────────


class TestGetPersonHistoryTool:
    async def test_get_person_history_returns_timeline(self, memory_db):
        """Debrief 2 meetings with same attendee → get_person_history shows both."""
        from src.brief_mcp.memory import save_meeting_record, save_person_interaction

        # Directly save two meetings + person interactions
        rec1 = save_meeting_record({
            "title": "First Meet With Frank",
            "date": datetime(2026, 9, 10, tzinfo=timezone.utc).isoformat(),
            "attendees": ["Frank Stone"],
        })
        rec2 = save_meeting_record({
            "title": "Second Meet With Frank",
            "date": datetime(2026, 10, 1, tzinfo=timezone.utc).isoformat(),
            "attendees": ["Frank Stone"],
        })
        save_person_interaction("Frank Stone", rec1, ["product demo"], "WidgetCo")
        save_person_interaction("Frank Stone", rec2, ["contract review"], "WidgetCo")

        mcp = _make_mcp()
        result = await mcp.call_tool("get_person_history", {"name": "Frank Stone"})

        assert not result.is_error
        text = _get_text(result)
        # The history header uppercases the name
        assert "FRANK STONE" in text
        assert "2 interaction" in text or "interactions" in text

    async def test_get_person_history_no_results(self, memory_db):
        """Unknown person → returns informative message, not an error."""
        mcp = _make_mcp()
        result = await mcp.call_tool(
            "get_person_history",
            {"name": "Absolutely Unknown Person XYZ 99999"},
        )
        assert not result.is_error
        text = _get_text(result)
        assert "No interaction history found" in text or "no history" in text.lower() or "No past" in text


# ── get_open_action_items tool ────────────────────────────────────────────────


class TestGetOpenActionItemsTool:
    async def test_get_open_action_items_empty(self, memory_db):
        """No meetings saved → 'No open action items found'."""
        mcp = _make_mcp()
        result = await mcp.call_tool("get_open_action_items", {})
        assert not result.is_error
        text = _get_text(result)
        assert "No open action items" in text

    async def test_get_open_action_items_shows_tasks(self, memory_db):
        """Meeting with action items → get_open_action_items lists them."""
        from src.brief_mcp.memory import save_meeting_record

        save_meeting_record({
            "title": "Action Item Source Meeting",
            "date": datetime.now(timezone.utc).isoformat(),
            "attendees": ["Grace"],
            "action_items": [
                {"owner": "Grace", "task": "Prepare the quarterly report", "due_date": "2026-11-15"}
            ],
            "follow_up_sent": 0,
        })

        mcp = _make_mcp()
        result = await mcp.call_tool("get_open_action_items", {})
        assert not result.is_error
        text = _get_text(result)
        assert "quarterly report" in text.lower()
        assert "Grace" in text


# ── brief_with_history tool ───────────────────────────────────────────────────


class TestBriefWithHistoryTool:
    def setup_method(self):
        clear_cache()

    async def test_brief_with_history_no_history(self, memory_db, sample_meeting):
        """When attendee has no prior history, brief still works; history section
        says 'No past meetings recorded'."""
        mcp = _make_mcp()
        with patch(
            "src.brief_mcp.tools.debrief_tool.get_upcoming_events",
            new_callable=AsyncMock,
            return_value=[sample_meeting],
        ), patch(
            "src.brief_mcp.tools._shared.research_person",
            new_callable=AsyncMock,
            return_value=PersonProfile(name="Bob Patel", company="PartnerCo"),
        ):
            result = await mcp.call_tool(
                "brief_with_history",
                {"meeting_title": "Q4 Partnership Review"},
            )

        assert not result.is_error
        text = _get_text(result)
        # Brief card should be present
        assert "Q4 PARTNERSHIP REVIEW" in text
        # History section should note no past records
        assert "No past" in text or "no past" in text.lower()

    async def test_brief_with_history_meeting_not_found(self, memory_db):
        """When the title doesn't match any calendar meeting, returns helpful error."""
        mcp = _make_mcp()
        with patch(
            "src.brief_mcp.tools.debrief_tool.get_upcoming_events",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await mcp.call_tool(
                "brief_with_history",
                {"meeting_title": "Absolutely Nonexistent Meeting XYZ"},
            )

        assert not result.is_error
        text = _get_text(result)
        assert "not found" in text.lower() or "Meeting not found" in text

    async def test_brief_with_history_no_identifier(self, memory_db):
        """Calling without title or id returns a helpful error string."""
        mcp = _make_mcp()
        result = await mcp.call_tool("brief_with_history", {})
        assert not result.is_error
        text = _get_text(result)
        assert "provide" in text.lower() or "meeting_title" in text.lower()
