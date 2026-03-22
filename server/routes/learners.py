"""Learner routes — /api/learners."""

import json

from fastapi import APIRouter

from server.models.database import get_connection

router = APIRouter()


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
