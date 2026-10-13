"""SQLite-based persistent meeting memory for brief-mcp.

Stores meeting records, action items, and person interaction history.
Uses FTS5 for full-text search across meetings.

Database location: ~/.brief-mcp/memory.db

All functions are synchronous (sqlite3 is sync). Callers in async context
should wrap with asyncio.get_running_loop().run_in_executor(None, fn, *args).
"""

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_DB_DIR = Path.home() / ".brief-mcp"
_DB_PATH = _DB_DIR / "memory.db"

# ── Schema ─────────────────────────────────────────────────────────────────────

_CREATE_MEETINGS = """
CREATE TABLE IF NOT EXISTS meetings (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    date TEXT NOT NULL,
    attendees TEXT NOT NULL,
    brief_summary TEXT,
    action_items TEXT,
    outcomes TEXT,
    follow_up_sent INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);
"""

_CREATE_MEETINGS_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS meetings_fts USING fts5(
    title,
    attendees,
    brief_summary,
    action_items,
    outcomes,
    content='meetings',
    content_rowid='rowid'
);
"""

_CREATE_FTS_TRIGGER_INSERT = """
CREATE TRIGGER IF NOT EXISTS meetings_fts_insert
AFTER INSERT ON meetings BEGIN
    INSERT INTO meetings_fts(rowid, title, attendees, brief_summary, action_items, outcomes)
    VALUES (new.rowid, new.title, new.attendees, new.brief_summary, new.action_items, new.outcomes);
END;
"""

_CREATE_FTS_TRIGGER_UPDATE = """
CREATE TRIGGER IF NOT EXISTS meetings_fts_update
AFTER UPDATE ON meetings BEGIN
    UPDATE meetings_fts
    SET title=new.title, attendees=new.attendees, brief_summary=new.brief_summary,
        action_items=new.action_items, outcomes=new.outcomes
    WHERE rowid=new.rowid;
END;
"""

_CREATE_FTS_TRIGGER_DELETE = """
CREATE TRIGGER IF NOT EXISTS meetings_fts_delete
AFTER DELETE ON meetings BEGIN
    DELETE FROM meetings_fts WHERE rowid=old.rowid;
END;
"""

_CREATE_PERSON_HISTORY = """
CREATE TABLE IF NOT EXISTS person_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_name TEXT NOT NULL,
    company TEXT,
    meeting_id TEXT REFERENCES meetings(id),
    interaction_date TEXT NOT NULL,
    topics TEXT,
    sentiment TEXT,
    notes TEXT
);
"""


# ── Internal helpers ───────────────────────────────────────────────────────────


def _get_connection() -> sqlite3.Connection:
    """Open (and return) a database connection. Creates the file if needed."""
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a sqlite3.Row to a plain dict."""
    return dict(row)


def _safe_json_loads(value: Optional[str], default: Any = None) -> Any:
    """Parse a JSON string safely, returning default on failure."""
    if value is None:
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Public API ─────────────────────────────────────────────────────────────────


def init_db() -> None:
    """Create database tables if they do not exist."""
    with _get_connection() as conn:
        conn.execute(_CREATE_MEETINGS)
        conn.execute(_CREATE_MEETINGS_FTS)
        conn.execute(_CREATE_FTS_TRIGGER_INSERT)
        conn.execute(_CREATE_FTS_TRIGGER_UPDATE)
        conn.execute(_CREATE_FTS_TRIGGER_DELETE)
        conn.execute(_CREATE_PERSON_HISTORY)
        conn.commit()
    logger.debug("brief-mcp memory.db initialized at %s", _DB_PATH)


def save_meeting_record(record: dict) -> str:
    """Insert or replace a meeting record.

    The record dict may contain:
        id (str, optional — auto-generated UUID if absent)
        title (str, required)
        date (str ISO format, required)
        attendees (list[str] or JSON str)
        brief_summary (str, optional)
        action_items (list[dict] or JSON str, optional)
            Each dict: {owner: str, task: str, due_date: str}
        outcomes (list[str] or JSON str, optional)
        follow_up_sent (bool/int, optional)

    Returns the meeting id.
    """
    init_db()
    meeting_id = record.get("id") or str(uuid.uuid4())

    title = record.get("title", "Untitled Meeting")
    date = record.get("date", _now_iso())
    created_at = record.get("created_at", _now_iso())
    follow_up_sent = int(bool(record.get("follow_up_sent", False)))

    # Normalise list fields to JSON strings
    def _to_json(val: Any) -> str:
        if val is None:
            return "[]"
        if isinstance(val, str):
            return val
        return json.dumps(val, ensure_ascii=False)

    attendees_json = _to_json(record.get("attendees", []))
    action_items_json = _to_json(record.get("action_items", []))
    outcomes_json = _to_json(record.get("outcomes", []))
    brief_summary = record.get("brief_summary") or None

    with _get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO meetings
                (id, title, date, attendees, brief_summary, action_items, outcomes,
                 follow_up_sent, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                meeting_id,
                title,
                date,
                attendees_json,
                brief_summary,
                action_items_json,
                outcomes_json,
                follow_up_sent,
                created_at,
            ),
        )
        conn.commit()

    logger.info("Saved meeting record id=%s title='%s'", meeting_id, title)
    return meeting_id


def search_meetings(query: str, limit: int = 10) -> list[dict]:
    """Full-text search across meeting title, attendees, summary, action items, and outcomes.

    Returns a list of meeting dicts with JSON fields deserialized.
    """
    init_db()

    if not query or not query.strip():
        return get_recent_meetings(days=90)[:limit]

    # FTS5 match query — escape special characters minimally
    fts_query = query.replace('"', '""')

    with _get_connection() as conn:
        try:
            rows = conn.execute(
                """
                SELECT m.*
                FROM meetings m
                JOIN meetings_fts fts ON m.rowid = fts.rowid
                WHERE meetings_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (fts_query, limit),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            logger.warning("FTS search error for query '%s': %s — falling back to LIKE", query, exc)
            like_q = f"%{query}%"
            rows = conn.execute(
                """
                SELECT * FROM meetings
                WHERE title LIKE ? OR attendees LIKE ? OR brief_summary LIKE ?
                ORDER BY date DESC
                LIMIT ?
                """,
                (like_q, like_q, like_q, limit),
            ).fetchall()

    results = []
    for row in rows:
        d = _row_to_dict(row)
        d["attendees"] = _safe_json_loads(d.get("attendees"), [])
        d["action_items"] = _safe_json_loads(d.get("action_items"), [])
        d["outcomes"] = _safe_json_loads(d.get("outcomes"), [])
        results.append(d)

    return results


def get_person_history(name: str, limit: int = 20) -> list[dict]:
    """Return all person_history records for a given name (case-insensitive substring match)."""
    init_db()
    with _get_connection() as conn:
        rows = conn.execute(
            """
            SELECT ph.*, m.title as meeting_title, m.date as meeting_date
            FROM person_history ph
            LEFT JOIN meetings m ON ph.meeting_id = m.id
            WHERE LOWER(ph.person_name) LIKE LOWER(?)
            ORDER BY ph.interaction_date DESC
            LIMIT ?
            """,
            (f"%{name}%", limit),
        ).fetchall()

    results = []
    for row in rows:
        d = _row_to_dict(row)
        d["topics"] = _safe_json_loads(d.get("topics"), [])
        results.append(d)

    return results


def get_recent_meetings(days: int = 30) -> list[dict]:
    """Return meetings from the past N days, ordered newest first."""
    init_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with _get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM meetings
            WHERE date >= ?
            ORDER BY date DESC
            """,
            (cutoff,),
        ).fetchall()

    results = []
    for row in rows:
        d = _row_to_dict(row)
        d["attendees"] = _safe_json_loads(d.get("attendees"), [])
        d["action_items"] = _safe_json_loads(d.get("action_items"), [])
        d["outcomes"] = _safe_json_loads(d.get("outcomes"), [])
        results.append(d)

    return results


def get_action_items(status: str = "open") -> list[dict]:
    """Return action items from all meetings, with meeting context.

    status: "open" returns meetings where follow_up_sent=0,
            "all" returns every action item.
    """
    init_db()
    with _get_connection() as conn:
        if status == "all":
            rows = conn.execute(
                "SELECT * FROM meetings WHERE action_items IS NOT NULL AND action_items != '[]' ORDER BY date DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM meetings
                WHERE action_items IS NOT NULL
                  AND action_items != '[]'
                  AND follow_up_sent = 0
                ORDER BY date DESC
                """
            ).fetchall()

    results = []
    for row in rows:
        d = _row_to_dict(row)
        action_items = _safe_json_loads(d.get("action_items"), [])
        for item in action_items:
            if isinstance(item, dict):
                results.append(
                    {
                        "meeting_id": d["id"],
                        "meeting_title": d["title"],
                        "meeting_date": d["date"],
                        "owner": item.get("owner", ""),
                        "task": item.get("task", ""),
                        "due_date": item.get("due_date", ""),
                        "follow_up_sent": d.get("follow_up_sent", 0),
                    }
                )
            elif isinstance(item, str):
                results.append(
                    {
                        "meeting_id": d["id"],
                        "meeting_title": d["title"],
                        "meeting_date": d["date"],
                        "owner": "",
                        "task": item,
                        "due_date": "",
                        "follow_up_sent": d.get("follow_up_sent", 0),
                    }
                )

    return results


def mark_action_done(action_id: str) -> bool:
    """Mark a meeting's follow_up_sent flag as done (1).

    action_id is the meeting id. Returns True on success.
    """
    init_db()
    try:
        with _get_connection() as conn:
            cursor = conn.execute(
                "UPDATE meetings SET follow_up_sent = 1 WHERE id = ?",
                (action_id,),
            )
            conn.commit()
            return cursor.rowcount > 0
    except Exception as exc:
        logger.error("mark_action_done failed for id=%s: %s", action_id, exc)
        return False


def save_person_interaction(
    person_name: str,
    meeting_id: str,
    topics: list[str] | None = None,
    company: str = "",
    sentiment: str = "neutral",
    notes: str = "",
) -> None:
    """Insert a person_history record for a meeting interaction."""
    init_db()
    interaction_date = _now_iso()
    topics_json = json.dumps(topics or [], ensure_ascii=False)
    with _get_connection() as conn:
        conn.execute(
            """
            INSERT INTO person_history
                (person_name, company, meeting_id, interaction_date, topics, sentiment, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (person_name, company or None, meeting_id, interaction_date, topics_json, sentiment, notes or None),
        )
        conn.commit()
