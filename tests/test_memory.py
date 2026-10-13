"""Tests for the SQLite-based meeting memory module (brief_mcp.memory).

Covers: init_db, save_meeting_record, search_meetings, get_person_history,
get_recent_meetings, get_action_items, mark_action_done, save_person_interaction.

All tests use the ``memory_db`` fixture (from conftest.py) which redirects
the SQLite database to a pytest tmp_path so the real ~/.brief-mcp/ is never touched.
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.brief_mcp.memory import (
    get_action_items,
    get_person_history,
    get_recent_meetings,
    init_db,
    mark_action_done,
    save_meeting_record,
    save_person_interaction,
    search_meetings,
)


# ── init_db ───────────────────────────────────────────────────────────────────


class TestInitDb:
    def test_init_db_creates_tables(self, memory_db):
        """init_db() creates meetings, meetings_fts, and person_history tables."""
        import sqlite3

        init_db()
        conn = sqlite3.connect(str(memory_db))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'shadow')"
        )
        names = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert "meetings" in names
        assert "person_history" in names
        # FTS5 tables appear with their content-table name in sqlite_master
        # The trigger names confirm FTS is set up
        cursor2 = sqlite3.connect(str(memory_db)).execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        )
        triggers = {row[0] for row in cursor2.fetchall()}
        assert "meetings_fts_insert" in triggers


# ── save_meeting_record ───────────────────────────────────────────────────────


class TestSaveMeetingRecord:
    def test_save_meeting_returns_id(self, memory_db):
        """save_meeting_record returns a non-empty string ID."""
        record = {
            "title": "Test Meeting",
            "date": datetime.now(timezone.utc).isoformat(),
            "attendees": ["Alice", "Bob"],
        }
        meeting_id = save_meeting_record(record)
        assert isinstance(meeting_id, str)
        assert len(meeting_id) > 0

    def test_save_and_retrieve_meeting(self, memory_db):
        """Save a meeting record and retrieve it back intact via search."""
        now = datetime.now(timezone.utc).isoformat()
        record = {
            "title": "Q4 Strategy Session",
            "date": now,
            "attendees": ["Alice Chen", "Bob Patel"],
            "brief_summary": "Discussed Q4 OKRs and budget",
            "action_items": [
                {"owner": "Alice", "task": "Write OKR doc", "due_date": "2026-11-01"}
            ],
            "outcomes": ["Agreed on three Q4 initiatives"],
        }
        meeting_id = save_meeting_record(record)

        results = search_meetings("Q4 Strategy")
        assert len(results) >= 1
        found = next((r for r in results if r["id"] == meeting_id), None)
        assert found is not None
        assert found["title"] == "Q4 Strategy Session"
        assert "Alice Chen" in found["attendees"]
        assert found["brief_summary"] == "Discussed Q4 OKRs and budget"
        assert isinstance(found["action_items"], list)
        assert found["action_items"][0]["task"] == "Write OKR doc"
        assert found["outcomes"] == ["Agreed on three Q4 initiatives"]

    def test_save_meeting_uses_provided_id(self, memory_db):
        """When a record includes an id, that exact id is stored and returned."""
        record = {
            "id": "custom-uuid-abc-123",
            "title": "Custom ID Meeting",
            "date": datetime.now(timezone.utc).isoformat(),
            "attendees": [],
        }
        meeting_id = save_meeting_record(record)
        assert meeting_id == "custom-uuid-abc-123"

    def test_multiple_saves_no_collision(self, memory_db):
        """Save 5 meetings without providing IDs — all should have unique auto-generated IDs."""
        ids = []
        for i in range(5):
            record = {
                "title": f"Meeting Number {i}",
                "date": datetime.now(timezone.utc).isoformat(),
                "attendees": [f"Person{i}"],
            }
            mid = save_meeting_record(record)
            ids.append(mid)

        assert len(set(ids)) == 5, "Expected 5 distinct IDs, got duplicates"


# ── search_meetings ───────────────────────────────────────────────────────────


class TestSearchMeetings:
    def test_search_meetings_fts(self, memory_db):
        """Save 3 meetings, search by keyword — only the matching one is returned."""
        save_meeting_record({
            "title": "Budget Planning Alpha",
            "date": datetime.now(timezone.utc).isoformat(),
            "attendees": ["Alice"],
            "brief_summary": "Reviewed the annual budget numbers",
        })
        save_meeting_record({
            "title": "Engineering Sprint Review",
            "date": datetime.now(timezone.utc).isoformat(),
            "attendees": ["Bob"],
            "brief_summary": "Sprint 42 retrospective",
        })
        save_meeting_record({
            "title": "Sales Pipeline Review",
            "date": datetime.now(timezone.utc).isoformat(),
            "attendees": ["Carol"],
            "brief_summary": "Q4 pipeline analysis",
        })

        results = search_meetings("Budget")
        assert len(results) >= 1
        assert any("Budget" in r["title"] for r in results)
        assert all("Sprint" not in r["title"] for r in results)

    def test_search_meetings_empty_returns_empty(self, memory_db):
        """Search on an empty DB returns an empty list."""
        results = search_meetings("completely-nonexistent-keyword-xyz-99")
        assert results == []

    def test_search_by_attendee_name(self, memory_db):
        """FTS search works across the attendees field too."""
        save_meeting_record({
            "title": "Random Meeting Title",
            "date": datetime.now(timezone.utc).isoformat(),
            "attendees": ["Unique Person Grünwald"],
            "brief_summary": "Some summary text",
        })
        results = search_meetings("Grünwald")
        assert len(results) >= 1


# ── get_person_history ────────────────────────────────────────────────────────


class TestGetPersonHistory:
    def test_get_person_history(self, memory_db):
        """Save 2 meetings with same attendee; get_person_history returns both."""
        rec1 = save_meeting_record({
            "title": "First Meeting with Alice",
            "date": datetime.now(timezone.utc).isoformat(),
            "attendees": ["Alice Smith"],
        })
        rec2 = save_meeting_record({
            "title": "Second Meeting with Alice",
            "date": datetime.now(timezone.utc).isoformat(),
            "attendees": ["Alice Smith"],
        })
        save_person_interaction("Alice Smith", rec1, ["Q4 planning"], "Acme")
        save_person_interaction("Alice Smith", rec2, ["budget review"], "Acme")

        history = get_person_history("Alice Smith")
        assert len(history) == 2
        assert all(entry["person_name"] == "Alice Smith" for entry in history)

    def test_get_person_history_unknown(self, memory_db):
        """Looking up an unknown person returns an empty list without errors."""
        history = get_person_history("Nobody XYZ Doesnotexist 99999")
        assert history == []

    def test_get_person_history_case_insensitive(self, memory_db):
        """Person history lookup is case-insensitive substring match."""
        rec = save_meeting_record({
            "title": "Case Test Meeting",
            "date": datetime.now(timezone.utc).isoformat(),
            "attendees": ["Dave Clark"],
        })
        save_person_interaction("Dave Clark", rec)
        # Search with different casing / partial name
        history = get_person_history("dave")
        assert len(history) >= 1


# ── get_recent_meetings ───────────────────────────────────────────────────────


class TestGetRecentMeetings:
    def test_get_recent_meetings(self, memory_db):
        """Meetings within the last N days appear; older meetings are excluded."""
        now = datetime.now(timezone.utc)

        save_meeting_record({
            "title": "Recent Meeting",
            "date": (now - timedelta(days=5)).isoformat(),
            "attendees": [],
        })
        save_meeting_record({
            "title": "Ancient Meeting",
            "date": (now - timedelta(days=60)).isoformat(),
            "attendees": [],
        })

        results = get_recent_meetings(days=30)
        titles = [r["title"] for r in results]
        assert "Recent Meeting" in titles
        assert "Ancient Meeting" not in titles

    def test_get_recent_meetings_returns_dicts_with_parsed_json(self, memory_db):
        """attendees, action_items, outcomes come back as Python lists, not raw JSON strings."""
        save_meeting_record({
            "title": "JSON Fields Meeting",
            "date": datetime.now(timezone.utc).isoformat(),
            "attendees": ["Alice", "Bob"],
            "action_items": [{"owner": "Alice", "task": "Do something", "due_date": ""}],
            "outcomes": ["Decision was made"],
        })
        results = get_recent_meetings(days=1)
        assert len(results) >= 1
        r = next(r for r in results if r["title"] == "JSON Fields Meeting")
        assert isinstance(r["attendees"], list)
        assert isinstance(r["action_items"], list)
        assert isinstance(r["outcomes"], list)


# ── get_action_items / mark_action_done ───────────────────────────────────────


class TestActionItems:
    def test_get_action_items_open(self, memory_db):
        """Meetings with action items and follow_up_sent=0 show all items as open."""
        save_meeting_record({
            "title": "Action Items Test Meeting",
            "date": datetime.now(timezone.utc).isoformat(),
            "attendees": ["Bob"],
            "action_items": [
                {"owner": "Bob", "task": "Write technical spec", "due_date": "2026-11-01"},
                {"owner": "Alice", "task": "Review PR #42", "due_date": ""},
            ],
            "follow_up_sent": 0,
        })
        items = get_action_items(status="open")
        tasks = [i["task"] for i in items]
        assert "Write technical spec" in tasks
        assert "Review PR #42" in tasks

    def test_mark_action_done(self, memory_db):
        """mark_action_done sets follow_up_sent=1 so items no longer appear as open."""
        meeting_id = save_meeting_record({
            "title": "Mark Done Test Meeting",
            "date": datetime.now(timezone.utc).isoformat(),
            "attendees": [],
            "action_items": [{"owner": "Bob", "task": "Send follow-up email", "due_date": ""}],
            "follow_up_sent": 0,
        })

        # Verify item starts as open
        open_before = get_action_items(status="open")
        assert any(i["meeting_id"] == meeting_id for i in open_before)

        # Mark done and verify return value
        result = mark_action_done(meeting_id)
        assert result is True

        # Should no longer appear under open
        open_after = get_action_items(status="open")
        assert not any(i["meeting_id"] == meeting_id for i in open_after)

    def test_mark_action_done_nonexistent_id_returns_false(self, memory_db):
        """mark_action_done on a non-existent ID returns False."""
        init_db()  # Ensure DB exists
        result = mark_action_done("nonexistent-meeting-id-xyz")
        assert result is False

    def test_get_action_items_string_tasks(self, memory_db):
        """Action items stored as plain strings (not dicts) are also returned."""
        save_meeting_record({
            "title": "String Action Items Meeting",
            "date": datetime.now(timezone.utc).isoformat(),
            "attendees": [],
            "action_items": ["Send invoice", "Schedule follow-up"],
            "follow_up_sent": 0,
        })
        items = get_action_items(status="open")
        tasks = [i["task"] for i in items]
        assert "Send invoice" in tasks
        assert "Schedule follow-up" in tasks


# ── save_person_interaction ───────────────────────────────────────────────────


class TestSavePersonInteraction:
    def test_save_person_interaction(self, memory_db):
        """save_person_interaction stores a record that get_person_history retrieves."""
        rec_id = save_meeting_record({
            "title": "Interaction Test Meeting",
            "date": datetime.now(timezone.utc).isoformat(),
            "attendees": ["Dave Clark"],
        })
        save_person_interaction(
            person_name="Dave Clark",
            meeting_id=rec_id,
            topics=["product roadmap", "pricing strategy"],
            company="WidgetCo",
            sentiment="positive",
            notes="Dave was enthusiastic about the new features.",
        )

        history = get_person_history("Dave Clark")
        assert len(history) == 1
        entry = history[0]
        assert entry["person_name"] == "Dave Clark"
        assert entry["company"] == "WidgetCo"
        assert entry["sentiment"] == "positive"
        assert isinstance(entry["topics"], list)
        assert "product roadmap" in entry["topics"]
        assert entry["notes"] == "Dave was enthusiastic about the new features."

    def test_save_multiple_interactions_same_person(self, memory_db):
        """Multiple interactions for the same person all appear in history."""
        for i in range(3):
            rec_id = save_meeting_record({
                "title": f"Meeting {i} with Eve",
                "date": datetime.now(timezone.utc).isoformat(),
                "attendees": ["Eve Turner"],
            })
            save_person_interaction(
                person_name="Eve Turner",
                meeting_id=rec_id,
                topics=[f"topic-{i}"],
            )

        history = get_person_history("Eve Turner")
        assert len(history) == 3
