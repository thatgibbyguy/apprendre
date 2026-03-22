"""SQLite database initialization, schema, and data access layer."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

DB_PATH = Path(__file__).parent.parent.parent / "apprendre.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS learners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    level_listening TEXT NOT NULL DEFAULT 'A1',
    level_reading TEXT NOT NULL DEFAULT 'A1',
    level_speaking TEXT NOT NULL DEFAULT 'A1',
    level_writing TEXT NOT NULL DEFAULT 'A1',
    instruction_language TEXT NOT NULL DEFAULT 'en',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS content_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    situation TEXT NOT NULL,
    cefr_level TEXT NOT NULL,
    target_structure TEXT NOT NULL,
    content_json TEXT NOT NULL DEFAULT '{}',
    register TEXT NOT NULL DEFAULT 'spoken',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id INTEGER NOT NULL REFERENCES learners(id),
    content_item_id INTEGER NOT NULL REFERENCES content_items(id),
    difficulty REAL NOT NULL DEFAULT 0.0,
    stability REAL NOT NULL DEFAULT 0.0,
    retrievability REAL NOT NULL DEFAULT 1.0,
    due_date TEXT,
    last_review TEXT,
    reps INTEGER NOT NULL DEFAULT 0,
    lapses INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL DEFAULT 'new',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS review_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL REFERENCES cards(id),
    learner_id INTEGER NOT NULL REFERENCES learners(id),
    rating INTEGER NOT NULL,
    review_date TEXT NOT NULL DEFAULT (datetime('now')),
    elapsed_days REAL NOT NULL DEFAULT 0.0,
    scheduled_days REAL NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id INTEGER NOT NULL REFERENCES learners(id),
    mode TEXT NOT NULL,
    scenario TEXT,
    cefr_level TEXT,
    system_prompt TEXT NOT NULL DEFAULT '',
    transcript_json TEXT NOT NULL DEFAULT '[]',
    feedback_summary TEXT,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at TEXT
);

CREATE TABLE IF NOT EXISTS error_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id INTEGER NOT NULL REFERENCES learners(id),
    error_type TEXT NOT NULL,
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    last_seen TEXT NOT NULL DEFAULT (datetime('now')),
    resolved INTEGER NOT NULL DEFAULT 0
);
"""


def get_connection(db_path: Optional[Union[str, Path]] = None) -> sqlite3.Connection:
    """Get a database connection with row factory enabled."""
    path = str(db_path or DB_PATH)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Optional[Union[str, Path]] = None) -> None:
    """Initialize the database schema."""
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def _insert(conn: sqlite3.Connection, table: str, data: Dict[str, Any]) -> int:
    """Insert a row and return the new row id."""
    cols = ", ".join(data.keys())
    placeholders = ", ".join("?" for _ in data)
    cur = conn.execute(
        f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
        list(data.values()),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def _get_by_id(conn: sqlite3.Connection, table: str, row_id: int) -> Optional[dict]:
    """Get a single row by id."""
    cur = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def _get_all(conn: sqlite3.Connection, table: str) -> List[dict]:
    """Get all rows from a table."""
    cur = conn.execute(f"SELECT * FROM {table}")
    return [dict(r) for r in cur.fetchall()]


def _update(conn: sqlite3.Connection, table: str, row_id: int, data: Dict[str, Any]) -> bool:
    """Update a row by id. Returns True if a row was updated."""
    if not data:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in data)
    cur = conn.execute(
        f"UPDATE {table} SET {set_clause} WHERE id = ?",
        [*data.values(), row_id],
    )
    conn.commit()
    return cur.rowcount > 0


def _delete(conn: sqlite3.Connection, table: str, row_id: int) -> bool:
    """Delete a row by id. Returns True if a row was deleted."""
    cur = conn.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,))
    conn.commit()
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Learners
# ---------------------------------------------------------------------------

def create_learner(
    conn: sqlite3.Connection,
    name: str,
    *,
    level_listening: str = "A1",
    level_reading: str = "A1",
    level_speaking: str = "A1",
    level_writing: str = "A1",
    instruction_language: str = "en",
) -> int:
    """Create a learner and return the id."""
    now = _now()
    return _insert(conn, "learners", {
        "name": name,
        "level_listening": level_listening,
        "level_reading": level_reading,
        "level_speaking": level_speaking,
        "level_writing": level_writing,
        "instruction_language": instruction_language,
        "created_at": now,
        "updated_at": now,
    })


def get_learner(conn: sqlite3.Connection, learner_id: int) -> Optional[dict]:
    return _get_by_id(conn, "learners", learner_id)


def get_all_learners(conn: sqlite3.Connection) -> List[dict]:
    return _get_all(conn, "learners")


def update_learner(conn: sqlite3.Connection, learner_id: int, data: Dict[str, Any]) -> bool:
    data["updated_at"] = _now()
    return _update(conn, "learners", learner_id, data)


def delete_learner(conn: sqlite3.Connection, learner_id: int) -> bool:
    return _delete(conn, "learners", learner_id)


# ---------------------------------------------------------------------------
# Content Items
# ---------------------------------------------------------------------------

def create_content_item(
    conn: sqlite3.Connection,
    *,
    type: str,
    situation: str,
    cefr_level: str,
    target_structure: str,
    content_json: Union[dict, str] = "{}",
    register: str = "spoken",
) -> int:
    if isinstance(content_json, dict):
        content_json = json.dumps(content_json)
    return _insert(conn, "content_items", {
        "type": type,
        "situation": situation,
        "cefr_level": cefr_level,
        "target_structure": target_structure,
        "content_json": content_json,
        "register": register,
        "created_at": _now(),
    })


def get_content_item(conn: sqlite3.Connection, item_id: int) -> Optional[dict]:
    return _get_by_id(conn, "content_items", item_id)


def get_all_content_items(conn: sqlite3.Connection) -> List[dict]:
    return _get_all(conn, "content_items")


def delete_content_item(conn: sqlite3.Connection, item_id: int) -> bool:
    return _delete(conn, "content_items", item_id)


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------

def create_card(
    conn: sqlite3.Connection,
    learner_id: int,
    content_item_id: int,
    *,
    state: str = "new",
) -> int:
    now = _now()
    return _insert(conn, "cards", {
        "learner_id": learner_id,
        "content_item_id": content_item_id,
        "state": state,
        "created_at": now,
        "updated_at": now,
    })


def get_card(conn: sqlite3.Connection, card_id: int) -> Optional[dict]:
    return _get_by_id(conn, "cards", card_id)


def get_cards_for_learner(conn: sqlite3.Connection, learner_id: int) -> List[dict]:
    cur = conn.execute("SELECT * FROM cards WHERE learner_id = ?", (learner_id,))
    return [dict(r) for r in cur.fetchall()]


def update_card(conn: sqlite3.Connection, card_id: int, data: Dict[str, Any]) -> bool:
    data["updated_at"] = _now()
    return _update(conn, "cards", card_id, data)


def delete_card(conn: sqlite3.Connection, card_id: int) -> bool:
    return _delete(conn, "cards", card_id)


# ---------------------------------------------------------------------------
# Review History
# ---------------------------------------------------------------------------

def create_review(
    conn: sqlite3.Connection,
    card_id: int,
    learner_id: int,
    rating: int,
    *,
    elapsed_days: float = 0.0,
    scheduled_days: float = 0.0,
) -> int:
    return _insert(conn, "review_history", {
        "card_id": card_id,
        "learner_id": learner_id,
        "rating": rating,
        "review_date": _now(),
        "elapsed_days": elapsed_days,
        "scheduled_days": scheduled_days,
    })


def get_reviews_for_card(conn: sqlite3.Connection, card_id: int) -> List[dict]:
    cur = conn.execute("SELECT * FROM review_history WHERE card_id = ?", (card_id,))
    return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def create_session(
    conn: sqlite3.Connection,
    learner_id: int,
    mode: str,
    *,
    scenario: Optional[str] = None,
    cefr_level: Optional[str] = None,
    system_prompt: str = "",
) -> int:
    return _insert(conn, "sessions", {
        "learner_id": learner_id,
        "mode": mode,
        "scenario": scenario,
        "cefr_level": cefr_level,
        "system_prompt": system_prompt,
        "transcript_json": "[]",
        "started_at": _now(),
    })


def get_session(conn: sqlite3.Connection, session_id: int) -> Optional[dict]:
    return _get_by_id(conn, "sessions", session_id)


def end_session(
    conn: sqlite3.Connection,
    session_id: int,
    *,
    transcript_json: str = "[]",
    feedback_summary: Optional[str] = None,
) -> bool:
    return _update(conn, "sessions", session_id, {
        "transcript_json": transcript_json,
        "feedback_summary": feedback_summary,
        "ended_at": _now(),
    })


# ---------------------------------------------------------------------------
# Error Patterns
# ---------------------------------------------------------------------------

def create_error_pattern(
    conn: sqlite3.Connection,
    learner_id: int,
    error_type: str,
) -> int:
    return _insert(conn, "error_patterns", {
        "learner_id": learner_id,
        "error_type": error_type,
        "occurrence_count": 1,
        "last_seen": _now(),
        "resolved": 0,
    })


def increment_error_pattern(conn: sqlite3.Connection, pattern_id: int) -> bool:
    cur = conn.execute(
        "UPDATE error_patterns SET occurrence_count = occurrence_count + 1, last_seen = ? WHERE id = ?",
        (_now(), pattern_id),
    )
    conn.commit()
    return cur.rowcount > 0


def get_error_patterns_for_learner(conn: sqlite3.Connection, learner_id: int) -> List[dict]:
    cur = conn.execute("SELECT * FROM error_patterns WHERE learner_id = ?", (learner_id,))
    return [dict(r) for r in cur.fetchall()]


def resolve_error_pattern(conn: sqlite3.Connection, pattern_id: int) -> bool:
    return _update(conn, "error_patterns", pattern_id, {"resolved": 1})


# ---------------------------------------------------------------------------
# Seed Data
# ---------------------------------------------------------------------------

def seed_test_data(conn: sqlite3.Connection) -> Dict[str, List[int]]:
    """Insert test data and return created ids."""
    ids: Dict[str, List[int]] = {}

    # Learners
    l1 = create_learner(conn, "Alice", level_listening="A2", level_reading="A2")
    l2 = create_learner(conn, "Bob")
    ids["learners"] = [l1, l2]

    # Content items
    c1 = create_content_item(
        conn,
        type="chunk",
        situation="parenting",
        cefr_level="A1",
        target_structure="present_tense",
        content_json={"french": "Je veux de l'eau", "english": "I want some water"},
    )
    c2 = create_content_item(
        conn,
        type="grammar",
        situation="social",
        cefr_level="A2",
        target_structure="passe_compose",
        content_json={"french": "J'ai mangé", "english": "I ate"},
        register="both",
    )
    ids["content_items"] = [c1, c2]

    # Cards
    k1 = create_card(conn, l1, c1)
    k2 = create_card(conn, l1, c2)
    ids["cards"] = [k1, k2]

    # Reviews
    r1 = create_review(conn, k1, l1, 3, elapsed_days=0, scheduled_days=1)
    ids["reviews"] = [r1]

    # Sessions
    s1 = create_session(conn, l1, "conversation", scenario="ordering food", cefr_level="A2")
    ids["sessions"] = [s1]

    # Error patterns
    e1 = create_error_pattern(conn, l1, "gender_agreement")
    ids["error_patterns"] = [e1]

    return ids
