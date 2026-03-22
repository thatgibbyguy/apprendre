"""CEFR adaptive level system.

Tracks and adjusts a learner's CEFR level per skill (listening, reading,
speaking, writing). Levels are A1, A2, B1, B2.

Level changes are conservative: a "confidence score" per skill must reach a
threshold before the level is actually updated. This prevents bouncing.
"""

import json
import re
import sqlite3
from typing import Optional

from server.models.database import _now, update_learner

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CEFR_ORDER: list[str] = ["A1", "A2", "B1", "B2"]

SKILLS: list[str] = ["listening", "reading", "speaking", "writing"]

# Minimum consecutive-session confidence before a level change is committed.
SESSIONS_REQUIRED_FOR_CHANGE: int = 3

# Error-rate thresholds
LOW_ERROR_RATE: float = 0.20
HIGH_ERROR_RATE: float = 0.60

# Grammar markers that signal A2+ production
A2_MARKERS: list[str] = [
    # passé composé auxiliaries
    r"\bai\b", r"\bas\b", r"\ba\b", r"\bavons\b", r"\bavez\b", r"\bont\b",
    r"\bsuis\b", r"\bes\b", r"\best\b", r"\bsommes\b", r"\bêtes\b", r"\bsont\b",
    # imparfait endings
    r"\w+ais\b", r"\w+ait\b", r"\w+aient\b",
    # common A2 vocabulary
    r"\bparce que\b", r"\bquand\b", r"\bpendant\b", r"\bd'abord\b", r"\bensuite\b",
]

B1_MARKERS: list[str] = [
    # subjunctive indicators
    r"\bque je\b", r"\bque tu\b", r"\bqu'il\b", r"\bqu'elle\b",
    r"\bpour que\b", r"\bbien que\b", r"\bquoique\b",
    # conditional
    r"\w+rais\b", r"\w+rait\b", r"\w+raient\b",
    # relative clauses
    r"\bqui\b.*\bverb\b", r"\bque\b", r"\bdont\b", r"\bLequel\b",
    # complex connectors
    r"\bcependant\b", r"\btoutefois\b", r"\bnéanmoins\b", r"\bainsi\b",
]

# Assessment thresholds (vocab range, avg sentence length)
_LEVEL_THRESHOLDS: list[tuple[str, int, float, int]] = [
    # (level, min_unique_words, min_avg_words_per_sentence, min_a2_markers)
    ("B1", 60, 8.0, 5),
    ("A2", 25, 5.0, 2),
    ("A1", 0, 0.0, 0),
]


# ---------------------------------------------------------------------------
# Confidence tracking table (created lazily alongside the main schema)
# ---------------------------------------------------------------------------

_CONFIDENCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS level_confidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id INTEGER NOT NULL,
    skill TEXT NOT NULL,
    direction INTEGER NOT NULL DEFAULT 0,   -- +1 = up, -1 = down
    session_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(learner_id, skill)
);
"""


def _ensure_confidence_table(conn: sqlite3.Connection) -> None:
    conn.executescript(_CONFIDENCE_SCHEMA)
    conn.commit()


# ---------------------------------------------------------------------------
# CEFR level helpers
# ---------------------------------------------------------------------------

def level_up(level: str) -> str:
    """Return the next CEFR level, or the same level if already at the top."""
    idx = CEFR_ORDER.index(level)
    return CEFR_ORDER[min(idx + 1, len(CEFR_ORDER) - 1)]


def level_down(level: str) -> str:
    """Return the previous CEFR level, or the same level if already at A1."""
    idx = CEFR_ORDER.index(level)
    return CEFR_ORDER[max(idx - 1, 0)]


def is_above(level_a: str, level_b: str) -> bool:
    """Return True if level_a is strictly higher than level_b."""
    return CEFR_ORDER.index(level_a) > CEFR_ORDER.index(level_b)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_current_levels(conn: sqlite3.Connection, learner_id: int) -> dict[str, str]:
    """Return the learner's current CEFR levels for all four skills.

    Returns a dict such as::

        {"listening": "A1", "reading": "A2", "speaking": "A1", "writing": "A1"}

    Raises ValueError if the learner does not exist.
    """
    cur = conn.execute(
        "SELECT level_listening, level_reading, level_speaking, level_writing "
        "FROM learners WHERE id = ?",
        (learner_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"Learner {learner_id} not found")
    return {
        "listening": row[0],
        "reading": row[1],
        "speaking": row[2],
        "writing": row[3],
    }


def assess_initial_level(
    conn: sqlite3.Connection,
    learner_id: int,
    assessment_responses: list[str],
) -> dict[str, str]:
    """Assess initial CEFR levels from a list of learner utterances.

    The assessment is rule-based and applied uniformly across all skills
    (since early assessment cannot distinguish skills reliably from text
    alone). The result is stored in the database and returned.

    Args:
        conn: Active SQLite connection.
        learner_id: ID of the learner being assessed.
        assessment_responses: List of text strings the learner produced.

    Returns:
        Dict of skill -> CEFR level, e.g. ``{"speaking": "A2", ...}``.

    Raises:
        ValueError: If the learner does not exist.
    """
    # Verify learner exists
    cur = conn.execute("SELECT id FROM learners WHERE id = ?", (learner_id,))
    if cur.fetchone() is None:
        raise ValueError(f"Learner {learner_id} not found")

    combined = " ".join(assessment_responses).lower()
    sentences = [s.strip() for s in re.split(r"[.!?]+", combined) if s.strip()]

    # Vocabulary breadth
    words = re.findall(r"[a-zàâäéèêëîïôùûüç']+", combined)
    unique_words = len(set(words))

    # Sentence complexity
    avg_words = (
        sum(len(re.findall(r"\S+", s)) for s in sentences) / len(sentences)
        if sentences
        else 0.0
    )

    # Grammar marker counts
    a2_hits = sum(
        1 for pattern in A2_MARKERS if re.search(pattern, combined)
    )
    b1_hits = sum(
        1 for pattern in B1_MARKERS if re.search(pattern, combined)
    )

    # Map to CEFR level
    assessed: str = "A1"
    if b1_hits >= 3 and unique_words >= 60 and avg_words >= 8.0:
        assessed = "B1"
    elif a2_hits >= 2 and unique_words >= 25 and avg_words >= 5.0:
        assessed = "A2"

    levels: dict[str, str] = {skill: assessed for skill in SKILLS}

    update_learner(conn, learner_id, {
        "level_listening": assessed,
        "level_reading": assessed,
        "level_speaking": assessed,
        "level_writing": assessed,
    })

    return levels


def update_level_from_session(
    conn: sqlite3.Connection,
    learner_id: int,
    session_data: dict,
) -> dict:
    """Check whether session performance warrants a level change.

    The system is conservative: it tracks a directional confidence score per
    skill and only commits a level change after
    ``SESSIONS_REQUIRED_FOR_CHANGE`` consecutive sessions pointing the same
    way.

    Args:
        conn: Active SQLite connection.
        learner_id: ID of the learner.
        session_data: Dict with keys:
            - ``skill`` (str): e.g. ``"speaking"``
            - ``error_count`` (int)
            - ``exchange_count`` (int)
            - ``structures_used`` (list[str])
            - ``cefr_level`` (str): target level of the scenario

    Returns:
        ``{"changed": True, "skill": str, "old_level": str, "new_level": str}``
        or ``{"changed": False}``.

    Raises:
        ValueError: If the learner does not exist or skill is invalid.
    """
    _ensure_confidence_table(conn)

    skill: str = session_data.get("skill", "")
    if skill not in SKILLS:
        raise ValueError(f"Invalid skill: {skill!r}. Must be one of {SKILLS}")

    error_count: int = int(session_data.get("error_count", 0))
    exchange_count: int = int(session_data.get("exchange_count", 1))
    structures_used: list[str] = session_data.get("structures_used", [])
    scenario_level: str = session_data.get("cefr_level", "A1")

    if scenario_level not in CEFR_ORDER:
        raise ValueError(f"Invalid cefr_level: {scenario_level!r}")

    current_levels = get_current_levels(conn, learner_id)
    current_level: str = current_levels[skill]

    # Avoid division by zero
    exchanges = max(exchange_count, 1)
    error_rate: float = error_count / exchanges

    # Determine directional signal for this session
    direction: int = 0  # neutral

    if error_rate < LOW_ERROR_RATE:
        # Good performance — check if structures are above current level
        learner_used_higher = any(
            _structure_implies_level_above(s, current_level)
            for s in structures_used
        )
        if learner_used_higher or is_above(scenario_level, current_level):
            direction = 1  # candidate for level up
        # Good performance at current level: neutral (not enough to level up alone)

    elif error_rate > HIGH_ERROR_RATE and not is_above(current_level, scenario_level):
        # High errors at or below current level → candidate for level down
        direction = -1

    # Update confidence counter
    row = conn.execute(
        "SELECT id, direction, session_count FROM level_confidence "
        "WHERE learner_id = ? AND skill = ?",
        (learner_id, skill),
    ).fetchone()

    if row is None:
        conn.execute(
            "INSERT INTO level_confidence (learner_id, skill, direction, session_count, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (learner_id, skill, direction, 1 if direction != 0 else 0, _now()),
        )
        conn.commit()
        return {"changed": False}

    stored_direction: int = row[1]
    session_count: int = row[2]

    if direction == 0 or direction != stored_direction:
        # Reset — inconsistent signal
        conn.execute(
            "UPDATE level_confidence SET direction = ?, session_count = ?, updated_at = ? "
            "WHERE learner_id = ? AND skill = ?",
            (direction, 1 if direction != 0 else 0, _now(), learner_id, skill),
        )
        conn.commit()
        return {"changed": False}

    new_count = session_count + 1
    conn.execute(
        "UPDATE level_confidence SET session_count = ?, updated_at = ? "
        "WHERE learner_id = ? AND skill = ?",
        (new_count, _now(), learner_id, skill),
    )
    conn.commit()

    if new_count < SESSIONS_REQUIRED_FOR_CHANGE:
        return {"changed": False}

    # Threshold reached — commit the level change
    old_level = current_level
    if direction == 1:
        new_level = level_up(current_level)
    else:
        new_level = level_down(current_level)

    if new_level == old_level:
        # Already at ceiling/floor — reset counter
        conn.execute(
            "UPDATE level_confidence SET session_count = 0, updated_at = ? "
            "WHERE learner_id = ? AND skill = ?",
            (_now(), learner_id, skill),
        )
        conn.commit()
        return {"changed": False}

    update_learner(conn, learner_id, {f"level_{skill}": new_level})

    # Reset confidence after applying change
    conn.execute(
        "UPDATE level_confidence SET direction = 0, session_count = 0, updated_at = ? "
        "WHERE learner_id = ? AND skill = ?",
        (_now(), learner_id, skill),
    )
    conn.commit()

    return {"changed": True, "skill": skill, "old_level": old_level, "new_level": new_level}


def get_scenarios_for_level(
    conn: sqlite3.Connection,
    learner_id: int,
) -> list[dict]:
    """Return scenario content items matching the learner's current speaking level.

    Args:
        conn: Active SQLite connection.
        learner_id: ID of the learner.

    Returns:
        List of content_items rows (as dicts) with type='scenario' at the
        learner's speaking level. Returns an empty list if none exist.
    """
    levels = get_current_levels(conn, learner_id)
    speaking_level = levels["speaking"]

    cur = conn.execute(
        "SELECT * FROM content_items WHERE type = 'scenario' AND cefr_level = ?",
        (speaking_level,),
    )
    return [dict(row) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Grammar structures associated with each level boundary
_LEVEL_STRUCTURES: dict[str, list[str]] = {
    "A2": [
        "passé composé", "passe compose", "imparfait", "imperfect",
        "futur proche", "near future", "negation ne pas", "reflexive verbs",
        "verbes pronominaux",
    ],
    "B1": [
        "subjunctive", "subjonctif", "conditionnel", "conditional",
        "relative clause", "proposition relative", "reported speech",
        "discours indirect", "plus-que-parfait", "pluperfect",
    ],
    "B2": [
        "subjunctif imparfait", "gérondif", "gerund", "passive voice",
        "voix passive", "nominalization", "complex subordination",
    ],
}


def _structure_implies_level_above(structure: str, current_level: str) -> bool:
    """Return True if the grammar structure belongs to a level above current."""
    struct_lower = structure.lower()
    current_idx = CEFR_ORDER.index(current_level)

    for level, structures in _LEVEL_STRUCTURES.items():
        level_idx = CEFR_ORDER.index(level)
        if level_idx > current_idx:
            if any(s in struct_lower for s in structures):
                return True
    return False
