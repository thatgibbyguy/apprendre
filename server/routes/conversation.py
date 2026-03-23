"""Conversation routes — /api/conversation.

Manages conversation sessions where a learner chats with an AI playing a role
in a scenario. Transcripts are persisted to the sessions table as a JSON list
of message dicts: {"role": "system"|"user"|"assistant", "content": str,
"feedback_type": str|null}.

Endpoints:
    POST /                      — Start a new conversation session
    POST /{session_id}/message  — Send a learner message
    POST /{session_id}/end      — End a conversation and get a summary
    GET  /                      — List conversations for a learner
"""

import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from server.config import settings
from server.models.database import (
    get_connection,
    get_content_item,
    get_learner,
    create_session,
    get_session,
    end_session,
)
from server.prompts import CONVERSATION, FEEDBACK_CLASSIFIER, LEVEL_INSTRUCTIONS, SESSION_SUMMARY
from server.services.ai_provider import OllamaProvider
from server.services.feedback import FeedbackSelector

router = APIRouter()

# ---------------------------------------------------------------------------
# In-memory session cache
# Maps session_id → {
#     "provider": OllamaProvider,
#     "prompt_params": dict,       # template vars for CONVERSATION (no feedback_type)
#     "register": str,             # expected register ("tu" or "vous")
#     "example_exchanges": list,   # few-shot message dicts pre-seeded before history
# }
# Avoids reconstructing the provider on every message.
# ---------------------------------------------------------------------------

_active_sessions: dict[int, dict] = {}


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------


class StartConversationBody(BaseModel):
    learner_id: int
    scenario_id: int


class MessageBody(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_provider() -> OllamaProvider:
    """Return a new OllamaProvider configured from application settings."""
    return OllamaProvider(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
    )


def _build_messages_from_transcript(
    transcript: list[dict],
    system_prompt: str,
    example_exchanges: list[dict] | None = None,
) -> list[dict]:
    """Convert stored transcript entries to the messages list for generate_with_history.

    The system prompt is prepended as a system message. Few-shot example_exchanges
    are inserted after the system message and before the real conversation history,
    demonstrating the desired style and register. Any system entries in the
    transcript are skipped to avoid duplication.
    """
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    if example_exchanges:
        messages.extend(example_exchanges)
    for entry in transcript:
        if entry.get("role") == "system":
            continue
        messages.append({"role": entry["role"], "content": entry["content"]})
    return messages


def _error_patterns_summary(conn, learner_id: int) -> str:
    """Return a short text description of the learner's active error patterns."""
    from server.models.database import get_error_patterns_for_learner

    patterns = get_error_patterns_for_learner(conn, learner_id)
    active = [p for p in patterns if not p["resolved"]]
    if not active:
        return "none recorded"
    return ", ".join(
        f"{p['error_type']} (x{p['occurrence_count']})" for p in active
    )


# ---------------------------------------------------------------------------
# POST / — Start a new conversation
# ---------------------------------------------------------------------------


@router.post("/")
async def start_conversation(body: StartConversationBody) -> dict:
    """Start a new conversation session.

    Validates the learner and scenario content item, builds an AI system prompt
    from the CONVERSATION template, generates the AI's opening message, and
    persists the session transcript to the database.

    Request body:
        learner_id: ID of the learner starting the conversation.
        scenario_id: ID of a content_item of type "scenario".

    Returns:
        session_id: The newly created session id.
        message: The AI's opening message in French.
        scenario: Dict with ai_role, description, target_structures, cefr_level.
    """
    conn = get_connection()
    try:
        learner = get_learner(conn, body.learner_id)
        if learner is None:
            raise HTTPException(status_code=404, detail="Learner not found")

        content_item = get_content_item(conn, body.scenario_id)
        if content_item is None:
            raise HTTPException(status_code=404, detail="Scenario not found")
        if content_item["type"] != "scenario":
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Content item {body.scenario_id} is not a scenario "
                    f"(type={content_item['type']})"
                ),
            )

        try:
            scenario_data: dict = json.loads(content_item["content_json"])
        except (json.JSONDecodeError, TypeError) as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Scenario content_json is not valid JSON: {exc}",
            ) from exc

        ai_role: str = scenario_data.get("ai_role_fr") or scenario_data.get("ai_role", "a French speaker")
        description: str = scenario_data.get("description_fr") or scenario_data.get("description", content_item.get("situation", ""))
        target_structures: str = scenario_data.get(
            "target_structures",
            content_item.get("target_structure", ""),
        )
        cefr_level: str = content_item["cefr_level"]
        instruction_language: str = learner.get("instruction_language", "en")
        example_exchanges: list[dict] = scenario_data.get("example_exchanges", [])

        prompt_params: dict = {
            "ai_role": ai_role,
            "scenario_description": description,
            "level_instruction": LEVEL_INSTRUCTIONS.get(cefr_level, LEVEL_INSTRUCTIONS["A1"]),
            "instruction_language": instruction_language,
        }

        # Persist with feedback_type="none" as a stable default for cache-miss
        # recovery; the live path rebuilds the prompt per-turn from prompt_params.
        system_prompt_for_db: str = CONVERSATION.format(
            **prompt_params,
            feedback_type="none",
        )

        session_id: int = create_session(
            conn,
            body.learner_id,
            "conversation",
            scenario=description,
            cefr_level=cefr_level,
            system_prompt=system_prompt_for_db,
        )
    finally:
        conn.close()

    # Use the scenario's curated starter_prompt instead of generating one.
    # This is instant (no LLM call) and gives consistent, level-appropriate openings.
    opening_message: str = scenario_data.get("starter_prompt", "Bonjour !")

    # Lazily create the provider — only needed when the learner sends a message.
    provider = _make_provider()

    transcript: list[dict] = [
        {"role": "assistant", "content": opening_message, "feedback_type": None},
    ]

    conn = get_connection()
    try:
        from server.models.database import _update  # noqa: PLC0415

        _update(conn, "sessions", session_id, {"transcript_json": json.dumps(transcript)})
    finally:
        conn.close()

    expected_register: str = scenario_data.get("register", "tu")

    _active_sessions[session_id] = {
        "provider": provider,
        "prompt_params": prompt_params,
        "register": expected_register,
        "example_exchanges": example_exchanges,
    }

    return {
        "session_id": session_id,
        "message": opening_message,
        "scenario": {
            "ai_role": ai_role,
            "description": description,
            "target_structures": target_structures,
            "cefr_level": cefr_level,
            "register": expected_register,
            "title": scenario_data.get("title", ""),
            "title_fr": scenario_data.get("title_fr", ""),
            "situation": content_item.get("situation", ""),
            "feedback_focus": scenario_data.get("feedback_focus", []),
            "topic_suggestions": scenario_data.get("topic_suggestions", []),
        },
    }


# ---------------------------------------------------------------------------
# POST /{session_id}/message — Send a learner message
# ---------------------------------------------------------------------------


@router.post("/{session_id}/message")
async def send_message(session_id: int, body: MessageBody) -> dict:
    """Send a learner message and receive an AI response with feedback metadata.

    Classifies any grammatical error in the learner's message via the
    FEEDBACK_CLASSIFIER prompt, selects a pedagogical feedback strategy via
    FeedbackSelector, appends both turns to the persistent transcript, and
    returns the AI reply with feedback information.

    Path param:
        session_id: The active session ID.

    Request body:
        message: The learner's French text.

    Returns:
        message: The AI's response.
        feedback: Dict with error_found, error_type, error_detail,
                  feedback_type, corrected_form.
    """
    conn = get_connection()
    try:
        session = get_session(conn, session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        if session.get("ended_at") is not None:
            raise HTTPException(status_code=409, detail="Session has already ended")

        learner = get_learner(conn, session["learner_id"])
        if learner is None:
            raise HTTPException(status_code=404, detail="Learner not found")

        cefr_level: str = session.get("cefr_level") or learner.get("level_speaking", "A1")
        error_patterns_text: str = _error_patterns_summary(conn, session["learner_id"])

        try:
            transcript: list[dict] = json.loads(session["transcript_json"])
        except (json.JSONDecodeError, TypeError):
            transcript = []
    finally:
        conn.close()

    # Retrieve or rebuild provider from cache.
    if session_id in _active_sessions:
        cached = _active_sessions[session_id]
        provider: OllamaProvider = cached["provider"]
        prompt_params: dict | None = cached.get("prompt_params")
        expected_register: str = cached.get("register", "tu")
        example_exchanges: list[dict] = cached.get("example_exchanges", [])
    else:
        # Cache miss (e.g. server restart) — rebuild provider; prompt_params are
        # unavailable so we fall back to the DB-stored prompt (feedback_type="none").
        provider = _make_provider()
        prompt_params = None
        expected_register = "tu"
        example_exchanges = []
        _active_sessions[session_id] = {
            "provider": provider,
            "prompt_params": prompt_params,
            "register": expected_register,
            "example_exchanges": example_exchanges,
        }

    # --- Feedback classification ---
    # A1-A2: Use deterministic rule-based detection (no LLM).
    # B1+: Fall back to LLM classifier for semantic errors.
    if cefr_level in ("A1", "A2"):
        from server.services.error_detection import detect_error  # noqa: PLC0415

        error_result = detect_error(body.message, cefr_level, expected_register)
        classification = {
            "error_found": error_result.error_found,
            "error_type": error_result.error_type,
            "error_detail": error_result.error_detail,
            "corrected_form": error_result.corrected_form,
            "feedback_type": "none",
        }
    else:
        classifier_system = FEEDBACK_CLASSIFIER.format(
            cefr_level=cefr_level,
            error_patterns=error_patterns_text,
        )
        classification = await provider.generate_json(
            body.message,
            system=classifier_system,
            temperature=0.2,
        )

    error_found: bool = bool(classification.get("error_found", False))
    feedback_type: str = classification.get("feedback_type", "none")
    error_type: Optional[str] = classification.get("error_type")

    # --- Record error and select pedagogical feedback strategy ---
    if error_found and error_type:
        conn = get_connection()
        try:
            selector = FeedbackSelector()
            feedback_type = selector.record_and_select(
                conn,
                session["learner_id"],
                error_type,
                cefr_level,
            )
        finally:
            conn.close()
        classification["feedback_type"] = feedback_type

    # Append the learner's turn to the transcript.
    transcript.append({
        "role": "user",
        "content": body.message,
        "feedback_type": feedback_type if error_found else None,
    })

    # Build the system prompt per-turn so feedback_type is baked in directly.
    # On cache hit, prompt_params is available and we format with the real
    # feedback_type. On cache miss, fall back to the DB-stored prompt which
    # was saved with feedback_type="none".
    if prompt_params:
        system_prompt: str = CONVERSATION.format(**prompt_params, feedback_type=feedback_type)
    else:
        system_prompt = session.get("system_prompt", "")

    messages = _build_messages_from_transcript(transcript, system_prompt, example_exchanges)

    # Cap output length by CEFR level to enforce brevity at lower levels.
    _LEVEL_MAX_TOKENS: dict[str, int] = {"A1": 20, "A2": 40}
    max_tokens = _LEVEL_MAX_TOKENS.get(cefr_level)

    ai_response: str = await provider.generate_with_history(
        messages, temperature=0.7, max_tokens=max_tokens,
    )

    # Vocabulary check — identify words above the learner's level so the
    # frontend can provide translation help.  No retry (model can't simplify).
    vocab_help: list[str] = []
    if cefr_level in ("A1", "A2"):
        from server.services.vocab_gate import check_a1_vocab  # noqa: PLC0415

        _passes, _ratio, unknown = check_a1_vocab(ai_response)
        vocab_help = unknown

    # Append AI response and persist the updated transcript.
    transcript.append({
        "role": "assistant",
        "content": ai_response,
        "feedback_type": None,
    })

    conn = get_connection()
    try:
        from server.models.database import _update  # noqa: PLC0415

        _update(conn, "sessions", session_id, {"transcript_json": json.dumps(transcript)})
    finally:
        conn.close()

    return {
        "message": ai_response,
        "feedback": {
            "error_found": error_found,
            "error_type": classification.get("error_type"),
            "error_detail": classification.get("error_detail"),
            "feedback_type": feedback_type,
            "corrected_form": classification.get("corrected_form"),
        },
        "vocab_help": vocab_help,
    }


# ---------------------------------------------------------------------------
# POST /{session_id}/end — End a conversation
# ---------------------------------------------------------------------------


@router.post("/{session_id}/end")
async def end_conversation(session_id: int) -> dict:
    """End a conversation session and generate an encouraging summary.

    Loads the full transcript, calls the LLM with the SESSION_SUMMARY prompt
    to produce learner-facing feedback, then marks the session as ended in
    the database.

    Path param:
        session_id: The session to end.

    Returns:
        summary: Learner-facing session summary text.
        session_id: The ended session id.
    """
    conn = get_connection()
    try:
        session = get_session(conn, session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        if session.get("ended_at") is not None:
            raise HTTPException(status_code=409, detail="Session has already ended")

        learner = get_learner(conn, session["learner_id"])
        cefr_level: str = session.get("cefr_level") or (
            learner.get("level_speaking", "A1") if learner else "A1"
        )
        instruction_language: str = (
            learner.get("instruction_language", "en") if learner else "en"
        )

        try:
            transcript: list[dict] = json.loads(session["transcript_json"])
        except (json.JSONDecodeError, TypeError):
            transcript = []
    finally:
        conn.close()

    # Build a readable transcript string for the summary prompt (user/assistant
    # turns only — system entries are not useful for the learner summary).
    transcript_lines: list[str] = []
    for entry in transcript:
        role = entry.get("role", "")
        if role == "user":
            transcript_lines.append(f"Learner: {entry['content']}")
        elif role == "assistant":
            transcript_lines.append(f"AI: {entry['content']}")
    transcript_text = "\n".join(transcript_lines) if transcript_lines else "(empty)"

    summary_system = SESSION_SUMMARY.format(
        cefr_level=cefr_level,
        instruction_language=instruction_language,
        transcript=transcript_text,
    )

    if session_id in _active_sessions:
        provider: OllamaProvider = _active_sessions[session_id]["provider"]
    else:
        provider = _make_provider()

    summary: str = await provider.generate(
        "Please generate the session summary now.",
        system=summary_system,
        temperature=0.5,
    )

    transcript_json_str = json.dumps(transcript)

    conn = get_connection()
    try:
        end_session(
            conn,
            session_id,
            transcript_json=transcript_json_str,
            feedback_summary=summary,
        )
    finally:
        conn.close()

    _active_sessions.pop(session_id, None)

    return {"summary": summary, "session_id": session_id}


# ---------------------------------------------------------------------------
# GET / — List conversations for a learner
# ---------------------------------------------------------------------------


@router.get("/")
async def list_conversations(learner_id: int = Query(...)) -> dict:
    """List all conversation sessions for a learner, most recent first.

    Query params:
        learner_id: ID of the learner whose conversations to retrieve.

    Returns:
        conversations: List of session dicts.
    """
    conn = get_connection()
    try:
        learner = get_learner(conn, learner_id)
        if learner is None:
            raise HTTPException(status_code=404, detail="Learner not found")

        cur = conn.execute(
            "SELECT * FROM sessions"
            " WHERE learner_id = ? AND mode = 'conversation'"
            " ORDER BY started_at DESC",
            (learner_id,),
        )
        conversations = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    return {"conversations": conversations}
