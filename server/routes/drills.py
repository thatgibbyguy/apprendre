"""Drill routes — /api/drills."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_drills() -> dict:
    """List available drills."""
    return {"drills": []}


@router.post("/")
async def start_drill() -> dict:
    """Start a new drill session."""
    return {"status": "not_implemented"}
