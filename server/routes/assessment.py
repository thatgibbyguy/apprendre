"""Assessment routes — /api/assessment.

Endpoints:
    GET  /              — Get assessment status for a learner
    POST /              — Start a new assessment session
    POST /{session_id}/message  — Send a learner message in an active assessment
    POST /{session_id}/end      — Force-end (cancel) an active assessment
"""

import json
import re
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from server.config import settings
from server.models.database import (
    create_session,
    end_session,
    get_connection,
    get_learner,
    get_session,
    update_learner,
)
from server.prompts import ASSESSMENT
from server.services.ai_provider import OllamaProvider

router = APIRouter()

# In-memory store: session_id → {"provider": OllamaProvider}
_active_assessments: dict[int, dict] = {}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class StartAssessmentBody(BaseModel):
    learner_id: int


class MessageBody(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_assessment_json(text: str) -> Optional[dict]:
    """Extract the assessment JSON block from the AI's response.

    Looks for a ```json ... ``` code fence first, then falls back to a bare
    {"assessment": ...} pattern anywhere in the text.

    Returns the parsed dict on success, or None if no assessment block found.
    """
    # Try fenced code block: ```json ... ```
    fenced = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass

    # Try bare {"assessment": ...} — greedy match to end of object
    bare = re.search(r'(\{"assessment"\s*:.*\})', text, re.DOTALL)
    if bare:
        try:
            return json.loads(bare.group(1))
        except json.JSONDecodeError:
            pass

    return None


def _count_exchanges(transcript: list[dict]) -> int:
    """Count the number of complete learner → assistant exchange pairs."""
    return sum(1 for msg in transcript if msg["role"] == "user")


def _build_messages(transcript: list[dict]) -> list[dict]:
    """Prepend the ASSESSMENT system prompt to the transcript for the AI call."""
    return [{"role": "system", "content": ASSESSMENT}] + transcript


# ---------------------------------------------------------------------------
# GET / — assessment status
# ---------------------------------------------------------------------------


@router.get("/")
async def get_assessment_status(learner_id: int = Query(...)) -> dict:
    """Return whether the learner has an active assessment session.

    Query params:
        learner_id: ID of the learner to check.

    Returns:
        has_active: True if there is an unfinished assessment session.
        session_id: The session id, or null.
        exchange_count: Number of learner messages sent so far.
    """
    conn = get_connection()
    try:
        learner = get_learner(conn, learner_id)
        if learner is None:
            raise HTTPException(status_code=404, detail="Learner not found")

        cur = conn.execute(
            "SELECT * FROM sessions WHERE learner_id = ? AND mode = 'assessment' AND ended_at IS NULL"
            " ORDER BY started_at DESC LIMIT 1",
            (learner_id,),
        )
        row = cur.fetchone()
        if row is None:
            return {"has_active": False, "session_id": None, "exchange_count": 0}

        session = dict(row)
        transcript: list[dict] = json.loads(session.get("transcript_json") or "[]")
        return {
            "has_active": True,
            "session_id": session["id"],
            "exchange_count": _count_exchanges(transcript),
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# POST / — start assessment
# ---------------------------------------------------------------------------


@router.post("/")
async def start_assessment(body: StartAssessmentBody) -> dict:
    """Create a new assessment session and return the AI's opening message.

    Request body:
        learner_id: ID of the learner starting the assessment.

    Returns:
        session_id: The newly created session id.
        message: The AI's opening question in French.
    """
    conn = get_connection()
    try:
        learner = get_learner(conn, body.learner_id)
        if learner is None:
            raise HTTPException(status_code=404, detail="Learner not found")

        session_id = create_session(conn, body.learner_id, "assessment")
    finally:
        conn.close()

    provider = OllamaProvider(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
    )

    # Ask the AI to open with its first question — no user message yet.
    opening_prompt = "Bonjour !"
    messages = [
        {"role": "system", "content": ASSESSMENT},
        {"role": "user", "content": opening_prompt},
    ]
    ai_message = await provider.generate_with_history(messages, temperature=0.7)

    # Persist the opening exchange to the transcript.
    transcript = [
        {"role": "user", "content": opening_prompt},
        {"role": "assistant", "content": ai_message},
    ]
    conn = get_connection()
    try:
        from server.models.database import _update  # noqa: PLC0415

        _update(conn, "sessions", session_id, {"transcript_json": json.dumps(transcript)})
    finally:
        conn.close()

    _active_assessments[session_id] = {"provider": provider}

    return {"session_id": session_id, "message": ai_message}


# ---------------------------------------------------------------------------
# POST /{session_id}/message — learner sends a message
# ---------------------------------------------------------------------------


@router.post("/{session_id}/message")
async def send_message(session_id: int, body: MessageBody) -> dict:
    """Process a learner's message in an active assessment.

    Path param:
        session_id: The assessment session to send a message to.

    Request body:
        message: The learner's French text.

    Returns (incomplete):
        message: The AI's response.
        exchange_count: Number of learner turns so far.
        complete: false

    Returns (assessment complete):
        message: The AI's final response (may contain the JSON block).
        assessment: Parsed assessment dict.
        complete: true
    """
    conn = get_connection()
    try:
        session = get_session(conn, session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        if session.get("ended_at") is not None:
            raise HTTPException(status_code=409, detail="Session has already ended")
        if session.get("mode") != "assessment":
            raise HTTPException(status_code=400, detail="Session is not an assessment")

        transcript: list[dict] = json.loads(session.get("transcript_json") or "[]")
    finally:
        conn.close()

    # Append the learner's message.
    transcript.append({"role": "user", "content": body.message})

    # Retrieve or create a provider for this session.
    if session_id not in _active_assessments:
        _active_assessments[session_id] = {
            "provider": OllamaProvider(
                base_url=settings.ollama_base_url,
                model=settings.ollama_model,
            )
        }
    provider: OllamaProvider = _active_assessments[session_id]["provider"]

    ai_response = await provider.generate_with_history(
        _build_messages(transcript), temperature=0.7
    )

    # Check whether the AI has appended the final assessment JSON block.
    assessment_data = _extract_assessment_json(ai_response)

    transcript.append({"role": "assistant", "content": ai_response})
    transcript_json = json.dumps(transcript)

    if assessment_data is not None:
        # --- Assessment complete ---
        levels = assessment_data.get("assessment", {})
        learner_update: dict = {}
        if "speaking" in levels:
            learner_update["level_speaking"] = levels["speaking"]
        if "listening" in levels:
            learner_update["level_listening"] = levels["listening"]
        if "reading" in levels:
            learner_update["level_reading"] = levels["reading"]
        if "writing" in levels:
            learner_update["level_writing"] = levels["writing"]

        conn = get_connection()
        try:
            if learner_update:
                update_learner(conn, session["learner_id"], learner_update)
            end_session(
                conn,
                session_id,
                transcript_json=transcript_json,
                feedback_summary=json.dumps(assessment_data),
            )
        finally:
            conn.close()

        _active_assessments.pop(session_id, None)

        return {"message": ai_response, "assessment": assessment_data, "complete": True}

    # --- Assessment still in progress ---
    conn = get_connection()
    try:
        from server.models.database import _update  # noqa: PLC0415

        _update(conn, "sessions", session_id, {"transcript_json": transcript_json})
    finally:
        conn.close()

    exchange_count = _count_exchanges(transcript)
    return {"message": ai_response, "exchange_count": exchange_count, "complete": False}


# ---------------------------------------------------------------------------
# POST /{session_id}/end — cancel an assessment
# ---------------------------------------------------------------------------


@router.post("/{session_id}/end")
async def end_assessment(session_id: int) -> dict:
    """Force-end (cancel) an active assessment without updating learner levels.

    Path param:
        session_id: The assessment session to cancel.

    Returns:
        session_id: The cancelled session id.
        cancelled: true
    """
    conn = get_connection()
    try:
        session = get_session(conn, session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        if session.get("mode") != "assessment":
            raise HTTPException(status_code=400, detail="Session is not an assessment")

        transcript_json = session.get("transcript_json") or "[]"
        end_session(conn, session_id, transcript_json=transcript_json, feedback_summary=None)
    finally:
        conn.close()

    _active_assessments.pop(session_id, None)

    return {"session_id": session_id, "cancelled": True}
