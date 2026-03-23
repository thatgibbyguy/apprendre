"""Drill routes — /api/drills.

Endpoints:
    GET  /due?learner_id=X          — Return cards due for review (due_date <= now
                                       or state = 'new'), ordered overdue-first.
    GET  /{card_id}                  — Return a single card with its content item.
    POST /{card_id}/rate             — Submit a rating and schedule the next review.
    POST /seed?learner_id=X          — Seed initial A1 chunk cards for a learner.
"""

import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from server.content_loader import load_content
from server.models.database import (
    get_card,
    get_cards_for_learner,
    get_connection,
    get_content_item,
    get_learner,
)
from server.services.srs_engine import (
    create_cards_for_learner,
    get_due_cards,
    get_review_stats,
    schedule_review,
)

router = APIRouter()

# Path to the A1 content directory, resolved relative to this file's project root.
_A1_CONTENT_DIR = Path(__file__).parent.parent.parent / "content" / "a1"

# Mapping from human-readable rating label to integer understood by schedule_review.
_RATING_MAP: dict[str, int] = {
    "again": 1,
    "hard": 2,
    "good": 3,
    "easy": 4,
}


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class RateCardBody(BaseModel):
    rating: Literal["again", "hard", "good", "easy"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _card_with_content(conn, card_id: int) -> dict:
    """Return a card row augmented with a parsed ``content_item`` sub-dict.

    Raises HTTPException 404 if the card does not exist.
    """
    card = get_card(conn, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail=f"Card {card_id} not found")

    content_item = get_content_item(conn, card["content_item_id"])
    if content_item is None:
        raise HTTPException(
            status_code=500,
            detail=f"Content item {card['content_item_id']} missing for card {card_id}",
        )

    # Parse content_json so the caller receives a dict, not a raw JSON string.
    try:
        content_data = json.loads(content_item["content_json"])
    except (json.JSONDecodeError, TypeError):
        content_data = {}

    card_dict = dict(card)
    card_dict["content_item"] = {
        **{k: v for k, v in content_item.items() if k != "content_json"},
        "content": content_data,
    }
    return card_dict


def _ensure_learner(conn, learner_id: int) -> dict:
    """Return the learner row or raise 404."""
    learner = get_learner(conn, learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail=f"Learner {learner_id} not found")
    return learner


# ---------------------------------------------------------------------------
# GET /due?learner_id=X
# ---------------------------------------------------------------------------


@router.get("/due")
async def get_due(learner_id: int = Query(...)) -> dict:
    """Return cards due for review for a learner.

    Overdue cards (due_date <= now) are returned before new cards.

    Query params:
        learner_id: ID of the learner.

    Returns:
        cards: List of card dicts, each with a ``content_item`` sub-dict.
        stats: Summary counts (total, due_now, new, learning, review, relearning).
    """
    conn = get_connection()
    try:
        _ensure_learner(conn, learner_id)
        cards = get_due_cards(conn, learner_id)
        stats = get_review_stats(conn, learner_id)
    finally:
        conn.close()

    # Parse content_json strings in the nested content_item for each card.
    for card in cards:
        ci = card.get("content_item", {})
        raw_json = ci.get("content_json")
        if isinstance(raw_json, str):
            try:
                ci["content"] = json.loads(raw_json)
            except (json.JSONDecodeError, TypeError):
                ci["content"] = {}
            del ci["content_json"]

    return {"cards": cards, "stats": stats}


# ---------------------------------------------------------------------------
# GET /{card_id}
# ---------------------------------------------------------------------------


@router.get("/{card_id}")
async def get_single_card(card_id: int) -> dict:
    """Return a single card with its content item.

    Path param:
        card_id: Primary key of the card.

    Returns:
        card: Card dict with a ``content_item`` sub-dict.
    """
    conn = get_connection()
    try:
        card = _card_with_content(conn, card_id)
    finally:
        conn.close()
    return {"card": card}


# ---------------------------------------------------------------------------
# POST /{card_id}/rate
# ---------------------------------------------------------------------------


@router.post("/{card_id}/rate")
async def rate_card(card_id: int, body: RateCardBody) -> dict:
    """Submit a rating for a card and schedule its next review.

    Path param:
        card_id: Primary key of the card being rated.

    Request body:
        rating: One of "again" | "hard" | "good" | "easy".

    Returns:
        card: The updated card dict with new scheduling fields.
        next_due: ISO string of the card's new due_date (or null for brand-new cards).
    """
    rating_int = _RATING_MAP[body.rating]  # always valid — Literal enforces it

    conn = get_connection()
    try:
        # Verify the card exists before calling the engine.
        if get_card(conn, card_id) is None:
            raise HTTPException(status_code=404, detail=f"Card {card_id} not found")

        try:
            updated = schedule_review(conn, card_id, rating_int)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        # Re-fetch with content_item attached.
        card = _card_with_content(conn, card_id)
    finally:
        conn.close()

    return {
        "card": card,
        "next_due": updated.get("due_date"),
    }


# ---------------------------------------------------------------------------
# POST /seed?learner_id=X
# ---------------------------------------------------------------------------


@router.post("/seed")
async def seed_cards(learner_id: int = Query(...)) -> dict:
    """Seed initial A1 chunk cards for a learner.

    Loads all A1 chunk content items from the database (seeding them from the
    JSON file if they do not yet exist), then creates a card for each one that
    the learner does not already have.  Idempotent — safe to call multiple times.

    Query params:
        learner_id: ID of the learner to seed cards for.

    Returns:
        created: Number of new cards created.
        total: Total number of A1 chunk cards the learner now has.
        learner_id: The learner ID that was seeded.
    """
    conn = get_connection()
    try:
        _ensure_learner(conn, learner_id)

        # Ensure A1 chunks are loaded into content_items (idempotent).
        if _A1_CONTENT_DIR.exists():
            load_content(conn, _A1_CONTENT_DIR)

        # Fetch all A1 chunk content item IDs.
        cur = conn.execute(
            "SELECT id FROM content_items WHERE type = 'chunk' AND cefr_level = 'A1'",
        )
        content_item_ids = [row[0] for row in cur.fetchall()]

        created_ids = create_cards_for_learner(conn, learner_id, content_item_ids)

        total_cards = len(get_cards_for_learner(conn, learner_id))
    finally:
        conn.close()

    return {
        "created": len(created_ids),
        "total": total_cards,
        "learner_id": learner_id,
    }
