"""Exercise routes — /api/exercises."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_exercises() -> dict:
    """List available exercises."""
    return {"exercises": []}


@router.get("/{exercise_id}")
async def get_exercise(exercise_id: int) -> dict:
    """Get a specific exercise."""
    return {"exercise_id": exercise_id, "status": "not_implemented"}
