"""FSRS spaced retrieval engine.

Wraps the py-fsrs library to schedule card reviews using the FSRS algorithm.
All functions accept a sqlite3.Connection as their first argument to keep the
data-access layer consistent with the rest of the codebase.
"""

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from fsrs import FSRS, Card, Rating, State

from server.models.database import (
    create_card,
    create_review,
    get_card,
    update_card,
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Map py-fsrs State enum values to the string names stored in the DB.
_STATE_TO_DB: dict[State, str] = {
    State.New: "new",
    State.Learning: "learning",
    State.Review: "review",
    State.Relearning: "relearning",
}

# Reverse map for reconstructing a py-fsrs Card from DB data.
_DB_TO_STATE: dict[str, State] = {v: k for k, v in _STATE_TO_DB.items()}

_SCHEDULER = FSRS()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO/SQLite datetime string to an aware UTC datetime."""
    if not value:
        return None
    # SQLite stores datetimes as "YYYY-MM-DD HH:MM:SS" (no timezone suffix).
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    raise ValueError(f"Unrecognised datetime format: {value!r}")


def _format_dt(dt: datetime) -> str:
    """Format a datetime to the SQLite-compatible string used in the DB."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _db_card_to_fsrs(card_row: dict) -> Card:
    """Reconstruct a py-fsrs Card from a DB card row.

    py-fsrs Card fields that we persist: difficulty, stability, due, last_review,
    reps, lapses, state.  All other FSRS internals are derived by the scheduler.
    """
    fsrs_card = Card()
    state_str = card_row.get("state", "new")
    fsrs_card.state = _DB_TO_STATE.get(state_str, State.New)
    fsrs_card.difficulty = float(card_row.get("difficulty") or 0.0)
    fsrs_card.stability = float(card_row.get("stability") or 0.0)
    fsrs_card.reps = int(card_row.get("reps") or 0)
    fsrs_card.lapses = int(card_row.get("lapses") or 0)

    due_str = card_row.get("due_date")
    if due_str:
        fsrs_card.due = _parse_dt(due_str)  # type: ignore[assignment]

    last_review_str = card_row.get("last_review")
    if last_review_str:
        fsrs_card.last_review = _parse_dt(last_review_str)  # type: ignore[assignment]

    return fsrs_card


def _elapsed_days(card_row: dict, now: datetime) -> float:
    """Days elapsed since the card was last reviewed (0 for new cards)."""
    last_review_str = card_row.get("last_review")
    if not last_review_str:
        return 0.0
    last_review = _parse_dt(last_review_str)
    if last_review is None:
        return 0.0
    delta = now - last_review
    return max(0.0, delta.total_seconds() / 86400)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def schedule_review(conn: sqlite3.Connection, card_id: int, rating: int) -> dict:
    """Schedule the next review for a card based on a rating.

    Args:
        conn: Active database connection.
        card_id: Primary key of the card to review.
        rating: 1=Again, 2=Hard, 3=Good, 4=Easy.

    Returns:
        The updated card as a dict.

    Raises:
        ValueError: If the card does not exist or the rating is invalid.
    """
    if rating not in (1, 2, 3, 4):
        raise ValueError(f"Invalid rating {rating!r}. Must be 1 (Again), 2 (Hard), 3 (Good), or 4 (Easy).")

    card_row = get_card(conn, card_id)
    if card_row is None:
        raise ValueError(f"Card {card_id} not found.")

    fsrs_rating = Rating(rating)
    now = _now_utc()
    elapsed = _elapsed_days(card_row, now)

    fsrs_card = _db_card_to_fsrs(card_row)
    updated_fsrs_card, review_log = _SCHEDULER.review_card(fsrs_card, fsrs_rating, now)

    # scheduled_days is how many days until the next due date.
    scheduled_days: float = getattr(updated_fsrs_card, "scheduled_days", 0.0) or 0.0

    # Compute retrievability (FSRS R value).  py-fsrs may or may not expose
    # get_retrievability; fall back to reading .retrievability if available.
    retrievability: float = 1.0
    if hasattr(_SCHEDULER, "get_retrievability"):
        try:
            retrievability = _SCHEDULER.get_retrievability(updated_fsrs_card)
        except Exception:
            pass
    elif hasattr(updated_fsrs_card, "retrievability"):
        retrievability = float(updated_fsrs_card.retrievability or 1.0)

    due_dt: Optional[datetime] = getattr(updated_fsrs_card, "due", None)
    last_review_dt: Optional[datetime] = getattr(updated_fsrs_card, "last_review", now)

    update_card(conn, card_id, {
        "difficulty": float(updated_fsrs_card.difficulty or 0.0),
        "stability": float(updated_fsrs_card.stability or 0.0),
        "retrievability": retrievability,
        "due_date": _format_dt(due_dt) if due_dt else None,
        "last_review": _format_dt(last_review_dt) if last_review_dt else _format_dt(now),
        "reps": int(updated_fsrs_card.reps or 0),
        "lapses": int(updated_fsrs_card.lapses or 0),
        "state": _STATE_TO_DB.get(updated_fsrs_card.state, "new"),
    })

    create_review(
        conn,
        card_id=card_id,
        learner_id=card_row["learner_id"],
        rating=rating,
        elapsed_days=elapsed,
        scheduled_days=scheduled_days,
    )

    return get_card(conn, card_id)  # type: ignore[return-value]


def get_due_cards(conn: sqlite3.Connection, learner_id: int, limit: int = 20) -> list[dict]:
    """Return cards due for review for a learner.

    Ordering:
      1. Overdue cards (due_date <= now), oldest first.
      2. New cards (state = 'new'), by creation date.

    Each returned dict includes the card fields plus a nested ``content_item``
    dict from the joined content_items row.

    Args:
        conn: Active database connection.
        learner_id: Learner whose cards to query.
        limit: Maximum number of cards to return.

    Returns:
        List of card dicts with ``content_item`` sub-dict.
    """
    now_str = _format_dt(_now_utc())

    sql = """
        SELECT
            c.*,
            ci.type          AS ci_type,
            ci.situation     AS ci_situation,
            ci.cefr_level    AS ci_cefr_level,
            ci.target_structure AS ci_target_structure,
            ci.content_json  AS ci_content_json,
            ci.register      AS ci_register
        FROM cards c
        JOIN content_items ci ON ci.id = c.content_item_id
        WHERE c.learner_id = ?
          AND (
              (c.state != 'new' AND c.due_date <= ?)
              OR c.state = 'new'
          )
        ORDER BY
            CASE WHEN c.state = 'new' THEN 1 ELSE 0 END ASC,
            c.due_date ASC,
            c.created_at ASC
        LIMIT ?
    """
    cur = conn.execute(sql, (learner_id, now_str, limit))
    rows = cur.fetchall()

    result = []
    for row in rows:
        d = dict(row)
        content_item = {
            "id": d.pop("content_item_id"),
            "type": d.pop("ci_type"),
            "situation": d.pop("ci_situation"),
            "cefr_level": d.pop("ci_cefr_level"),
            "target_structure": d.pop("ci_target_structure"),
            "content_json": d.pop("ci_content_json"),
            "register": d.pop("ci_register"),
        }
        d["content_item"] = content_item
        result.append(d)

    return result


def create_cards_for_learner(
    conn: sqlite3.Connection,
    learner_id: int,
    content_item_ids: list[int],
) -> list[int]:
    """Bulk-create new cards for a learner from content item IDs.

    Skips any (learner_id, content_item_id) pair that already has a card.

    Args:
        conn: Active database connection.
        learner_id: Learner to create cards for.
        content_item_ids: Content items to turn into cards.

    Returns:
        List of newly created card IDs (excludes skipped duplicates).
    """
    # Fetch existing content_item_ids for this learner in one query.
    cur = conn.execute(
        "SELECT content_item_id FROM cards WHERE learner_id = ?",
        (learner_id,),
    )
    existing = {row[0] for row in cur.fetchall()}

    created_ids: list[int] = []
    for citem_id in content_item_ids:
        if citem_id in existing:
            continue
        card_id = create_card(conn, learner_id, citem_id)
        created_ids.append(card_id)
        existing.add(citem_id)

    return created_ids


def get_review_stats(conn: sqlite3.Connection, learner_id: int) -> dict:
    """Return a review-count summary for a learner.

    Args:
        conn: Active database connection.
        learner_id: Learner to summarise.

    Returns:
        Dict with keys: total, due_now, new, learning, review, relearning.
    """
    now_str = _format_dt(_now_utc())

    cur = conn.execute(
        """
        SELECT
            COUNT(*)                                                   AS total,
            SUM(CASE WHEN state = 'new'        THEN 1 ELSE 0 END)     AS new_count,
            SUM(CASE WHEN state = 'learning'   THEN 1 ELSE 0 END)     AS learning_count,
            SUM(CASE WHEN state = 'review'     THEN 1 ELSE 0 END)     AS review_count,
            SUM(CASE WHEN state = 'relearning' THEN 1 ELSE 0 END)     AS relearning_count,
            SUM(
                CASE WHEN (state != 'new' AND due_date <= ?) OR state = 'new'
                THEN 1 ELSE 0 END
            ) AS due_now
        FROM cards
        WHERE learner_id = ?
        """,
        (now_str, learner_id),
    )
    row = cur.fetchone()
    if row is None:
        return {"total": 0, "due_now": 0, "new": 0, "learning": 0, "review": 0, "relearning": 0}

    return {
        "total": row["total"] or 0,
        "due_now": row["due_now"] or 0,
        "new": row["new_count"] or 0,
        "learning": row["learning_count"] or 0,
        "review": row["review_count"] or 0,
        "relearning": row["relearning_count"] or 0,
    }
