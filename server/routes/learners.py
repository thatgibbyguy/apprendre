"""Learner routes — /api/learners."""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from server.models.database import create_learner, get_connection, get_learner
from server.services.srs_engine import get_due_cards

router = APIRouter()


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CreateLearnerBody(BaseModel):
    name: str


# ---------------------------------------------------------------------------
# POST / — Create a learner
# ---------------------------------------------------------------------------


@router.post("/")
async def create_learner_route(body: CreateLearnerBody) -> dict:
    """Create a new learner and return their id and name."""
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name must not be empty")

    conn = get_connection()
    try:
        learner_id = create_learner(conn, name)
        learner = get_learner(conn, learner_id)
    finally:
        conn.close()

    return {"id": learner_id, "name": learner["name"]}  # type: ignore[index]


# ---------------------------------------------------------------------------
# GET / — List learners
# ---------------------------------------------------------------------------


@router.get("/")
async def list_learners() -> dict:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM learners ORDER BY id").fetchall()
        return {"learners": [dict(r) for r in rows]}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# GET /scenarios — List available scenarios
# ---------------------------------------------------------------------------


@router.get("/scenarios")
async def list_scenarios() -> dict:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, situation, cefr_level, content_json FROM content_items WHERE type = 'scenario' ORDER BY cefr_level, id"
        ).fetchall()
        scenarios = []
        for r in rows:
            data = json.loads(r["content_json"])
            scenarios.append({
                "id": r["id"],
                "description": data.get("description", r["situation"]),
                "ai_role": data.get("ai_role", ""),
                "cefr_level": r["cefr_level"],
            })
        return {"scenarios": scenarios}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# GET /dashboard — Dashboard data for a learner
# (defined before /{learner_id} so the literal path segment is matched first)
# ---------------------------------------------------------------------------


@router.get("/dashboard")
async def get_dashboard(learner_id: int = Query(...)) -> dict:
    """Return aggregated dashboard data for a learner.

    Query params:
        learner_id: ID of the learner.

    Returns:
        learner: Profile with name, levels, instruction_language.
        due_count: Number of cards due for review right now.
        active_session: Most recent unfinished conversation session (or null).
        last_session: Most recent ended session with basic stats (or null).
    """
    conn = get_connection()
    try:
        learner = get_learner(conn, learner_id)
        if learner is None:
            raise HTTPException(status_code=404, detail="Learner not found")

        # Due card count — cards where due_date <= now OR state = 'new'
        due_cards = get_due_cards(conn, learner_id)
        due_count = len(due_cards)

        # Most recent unfinished conversation (ended_at IS NULL)
        active_row = conn.execute(
            "SELECT id, scenario, cefr_level, started_at, transcript_json"
            " FROM sessions"
            " WHERE learner_id = ? AND mode = 'conversation' AND ended_at IS NULL"
            " ORDER BY started_at DESC"
            " LIMIT 1",
            (learner_id,),
        ).fetchone()

        active_session = None
        if active_row:
            active = dict(active_row)
            try:
                transcript = json.loads(active["transcript_json"] or "[]")
            except (json.JSONDecodeError, TypeError):
                transcript = []
            exchange_count = sum(
                1 for t in transcript if t.get("role") in ("user", "assistant")
            )
            active_session = {
                "session_id": active["id"],
                "scenario": active["scenario"],
                "cefr_level": active["cefr_level"],
                "started_at": active["started_at"],
                "exchange_count": exchange_count,
            }

        # Most recent ended session for "last session summary"
        last_row = conn.execute(
            "SELECT id, scenario, cefr_level, started_at, ended_at, transcript_json, feedback_summary"
            " FROM sessions"
            " WHERE learner_id = ? AND mode = 'conversation' AND ended_at IS NOT NULL"
            " ORDER BY ended_at DESC"
            " LIMIT 1",
            (learner_id,),
        ).fetchone()

        last_session = None
        if last_row:
            last = dict(last_row)
            try:
                transcript = json.loads(last["transcript_json"] or "[]")
            except (json.JSONDecodeError, TypeError):
                transcript = []
            exchange_count = sum(
                1 for t in transcript if t.get("role") == "user"
            )
            duration_min = None
            if last["started_at"] and last["ended_at"]:
                try:
                    fmt = "%Y-%m-%d %H:%M:%S"
                    start_dt = datetime.strptime(last["started_at"], fmt).replace(tzinfo=timezone.utc)
                    end_dt = datetime.strptime(last["ended_at"], fmt).replace(tzinfo=timezone.utc)
                    delta_sec = (end_dt - start_dt).total_seconds()
                    duration_min = max(1, round(delta_sec / 60))
                except ValueError:
                    duration_min = None

            last_session = {
                "session_id": last["id"],
                "scenario": last["scenario"],
                "cefr_level": last["cefr_level"],
                "started_at": last["started_at"],
                "ended_at": last["ended_at"],
                "exchange_count": exchange_count,
                "duration_min": duration_min,
                "feedback_summary": last["feedback_summary"],
            }

    finally:
        conn.close()

    return {
        "learner": dict(learner),
        "due_count": due_count,
        "active_session": active_session,
        "last_session": last_session,
    }


# ---------------------------------------------------------------------------
# GET /{learner_id} — Get a single learner
# ---------------------------------------------------------------------------


@router.get("/{learner_id}")
async def get_learner_route(learner_id: int) -> dict:
    """Return a single learner by id."""
    conn = get_connection()
    try:
        learner = get_learner(conn, learner_id)
    finally:
        conn.close()

    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")

    return dict(learner)
