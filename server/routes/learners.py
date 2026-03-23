"""Learner routes — /api/learners."""

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.models.database import create_learner, get_connection, get_learner

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class CreateLearnerBody(BaseModel):
    name: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/")
async def create_learner_route(body: CreateLearnerBody) -> dict:
    """Create a new learner and return their id and name.

    Request body:
        name: The learner's display name.

    Returns:
        id: The newly created learner id.
        name: The learner's name as stored.
    """
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


@router.get("/")
async def list_learners() -> dict:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM learners ORDER BY id").fetchall()
        return {"learners": [dict(r) for r in rows]}
    finally:
        conn.close()


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


@router.get("/{learner_id}")
async def get_learner_route(learner_id: int) -> dict:
    """Return a single learner by id.

    Path param:
        learner_id: The learner's id.

    Returns:
        The learner record, or 404.
    """
    conn = get_connection()
    try:
        learner = get_learner(conn, learner_id)
    finally:
        conn.close()

    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")

    return dict(learner)
