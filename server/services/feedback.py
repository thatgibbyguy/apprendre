"""Rule-based feedback type selection.

Application logic picks the feedback type (recast, prompt, metalinguistic cue),
then the LLM generates content within that constraint.

Level-aware rules (aligned with EPI + TBLT + spaced retrieval methodology):

  A1-A2: Default to recast. Escalate to prompt at 3+ occurrences.
  A2-B1: Recast for first occurrence, prompt for 2+, metalinguistic_cue for 4+.
  B1-B2: Default to prompt. Escalate to metalinguistic_cue at 2+ occurrences.
"""

import sqlite3
from typing import Optional

from server.models.database import (
    create_error_pattern,
    get_error_patterns_for_learner,
    increment_error_pattern,
)

# Maps CEFR level strings to a normalised numeric band for rule lookup.
# Each band maps to a tuple of (prompt_threshold, metalinguistic_threshold).
# None means that feedback type is never reached by this band.
_LEVEL_THRESHOLDS: dict[str, tuple[int, Optional[int]]] = {
    # (prompt_at, metalinguistic_at)
    "A1": (3, None),
    "A2": (2, 4),
    "B1": (1, 2),
    "B2": (1, 2),
}

_FALLBACK_THRESHOLDS: tuple[int, Optional[int]] = (2, 4)


class FeedbackSelector:
    """Selects appropriate feedback type based on learner level and error history."""

    def select_feedback_type(
        self,
        error_type: str,
        occurrence_count: int,
        learner_level: str,
    ) -> str:
        """Return the feedback type appropriate for this learner and error.

        Args:
            error_type: The category of grammatical or lexical error (unused in
                threshold logic but available for future per-error overrides).
            occurrence_count: How many times this error has been recorded for
                the learner, including the current occurrence.
            learner_level: CEFR level string — one of A1, A2, B1, B2.

        Returns:
            One of 'recast', 'prompt', or 'metalinguistic_cue'.

        Level rules:
            A1      — recast always; prompt at 3+.
            A2/A2-B1 — recast at 1; prompt at 2+; metalinguistic_cue at 4+.
            B1/B2   — prompt at 1+; metalinguistic_cue at 2+.
        """
        prompt_at, metalinguistic_at = _LEVEL_THRESHOLDS.get(
            learner_level.upper(), _FALLBACK_THRESHOLDS
        )

        if metalinguistic_at is not None and occurrence_count >= metalinguistic_at:
            return "metalinguistic_cue"
        if occurrence_count >= prompt_at:
            return "prompt"
        return "recast"

    def record_and_select(
        self,
        conn: sqlite3.Connection,
        learner_id: int,
        error_type: str,
        cefr_level: str,
    ) -> str:
        """Record an error occurrence in the DB and return the appropriate feedback type.

        Looks up the error pattern for this learner and error type. If an
        existing unresolved pattern is found it is incremented; otherwise a new
        pattern is created (occurrence_count starts at 1).

        Args:
            conn: An open SQLite connection (caller owns the lifecycle).
            learner_id: The id of the learner who made the error.
            error_type: The category of error (e.g. 'gender_agreement').
            cefr_level: The learner's current CEFR level (e.g. 'A2').

        Returns:
            One of 'recast', 'prompt', or 'metalinguistic_cue'.
        """
        patterns = get_error_patterns_for_learner(conn, learner_id)
        match = next(
            (p for p in patterns if p["error_type"] == error_type and not p["resolved"]),
            None,
        )

        if match is not None:
            increment_error_pattern(conn, match["id"])
            occurrence_count = match["occurrence_count"] + 1
        else:
            create_error_pattern(conn, learner_id, error_type)
            occurrence_count = 1

        return self.select_feedback_type(error_type, occurrence_count, cefr_level)
