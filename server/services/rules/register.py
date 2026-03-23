"""Tier 2: Tu/vous register rule.

Detects when the learner uses the wrong register for the scenario context.
For example, using "tu" with a café server (should be "vous") or "vous"
with a friend (should be "tu"). Uses simple token matching — no spaCy needed.
"""

from __future__ import annotations

import re
from typing import Optional

from spacy.tokens import Doc

from .base import ErrorResult, Rule

# Tokens that signal tu-register usage
_TU_PATTERNS = re.compile(
    r"\b(tu\b|toi\b|ton\b|ta\b|tes\b|t')",
    re.IGNORECASE,
)

# Tokens that signal vous-register usage.
# Excludes "s'il vous plaît" — fixed expression used in both registers.
_VOUS_PATTERNS = re.compile(
    r"\b(vous\b|votre\b|vos\b)",
    re.IGNORECASE,
)

_SVPL = re.compile(r"s'il\s+vous\s+plaît", re.IGNORECASE)


class RegisterRule(Rule):
    """Detect tu/vous register mismatch based on scenario context."""

    levels = {"A1", "A2", "B1", "B2"}

    def __init__(self, expected_register: str = "tu") -> None:
        self.expected_register = expected_register.lower()

    def check(self, doc: Doc) -> Optional[ErrorResult]:
        text = doc.text

        if self.expected_register == "vous":
            # Strip out "s'il vous plaît" before checking for tu-forms
            cleaned = _SVPL.sub("", text)
            match = _TU_PATTERNS.search(cleaned)
            if match:
                return ErrorResult(
                    error_found=True,
                    error_type="register_tu_vous",
                    error_detail=(
                        f"used '{match.group()}' — this situation calls for "
                        f"'vous' (formal). Use 'vous' with people you don't "
                        f"know well, in shops, cafés, etc."
                    ),
                    corrected_form=None,
                    source="rule",
                )

        elif self.expected_register == "tu":
            # Strip out "s'il vous plaît" — acceptable even in tu-register
            cleaned = _SVPL.sub("", text)
            match = _VOUS_PATTERNS.search(cleaned)
            if match:
                return ErrorResult(
                    error_found=True,
                    error_type="register_tu_vous",
                    error_detail=(
                        f"used '{match.group()}' — this is a casual situation, "
                        f"'tu' is more natural here. Use 'tu' with friends, "
                        f"family, children, and people your age in relaxed settings."
                    ),
                    corrected_form=None,
                    source="rule",
                )

        return None
