"""Three-tier error detection system.

Tier 1: Allowlist — known-correct phrases get instant pass.
Tier 2: Rule engine — spaCy morphological analysis for deterministic checks.
Tier 3: LLM fallback — only for B1+ when rules are insufficient.
"""

from __future__ import annotations

from typing import Optional

import spacy

from server.services.rules.allowlist import is_known_correct
from server.services.rules.base import ErrorResult
from server.services.rules.auxiliary import AuxiliaryRule
from server.services.rules.gender import GenderRule
from server.services.rules.register import RegisterRule
from server.services.rules.subject_verb import SubjectVerbRule
from server.services.rules.verb_forms import VerbFormRule

# Load spaCy model once at module level.
_nlp = spacy.load("fr_core_news_md")

# Static rules (no per-call context needed), checked in priority order.
_RULES = [
    SubjectVerbRule(),
    GenderRule(),
    AuxiliaryRule(),
    VerbFormRule(),
]


def detect_error(
    message: str,
    cefr_level: str,
    expected_register: str = "tu",
) -> ErrorResult:
    """Run the three-tier error detection pipeline.

    Args:
        message: The learner's French text.
        cefr_level: The learner's current CEFR level (A1-B2).
        expected_register: "tu" or "vous" — the register appropriate for
            this scenario context.

    Returns:
        An ErrorResult with error details, or error_found=False.
    """
    # Tier 1: Allowlist
    if is_known_correct(message):
        return ErrorResult(error_found=False, source="allowlist")

    # Tier 2: Rule engine
    doc = _nlp(message)

    # Register rule is context-dependent — built per call.
    rules = [RegisterRule(expected_register)] + _RULES

    for rule in rules:
        if not rule.applies_at_level(cefr_level):
            continue
        result = rule.check(doc)
        if result is not None:
            return result

    # No error found by rules
    return ErrorResult(error_found=False, source="none")
