"""Audio routes — /api/audio (STT/TTS)."""

from fastapi import APIRouter

router = APIRouter()


@router.post("/stt")
async def speech_to_text() -> dict:
    """Convert speech audio to text."""
    return {"status": "not_implemented"}


@router.post("/tts")
async def text_to_speech() -> dict:
    """Convert text to speech audio."""
    return {"status": "not_implemented"}
