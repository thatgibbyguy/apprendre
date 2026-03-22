"""Lesson routes — /api/lessons."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_lessons() -> dict:
    """List available lessons."""
    return {"lessons": []}


@router.get("/{lesson_id}")
async def get_lesson(lesson_id: int) -> dict:
    """Get a specific lesson."""
    return {"lesson_id": lesson_id, "status": "not_implemented"}
