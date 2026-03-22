"""Tier 2: Basic verb form rule.

Detects incorrect conjugation of high-frequency irregular verbs (être, avoir,
aller, faire) by comparing the actual token against expected forms for the
detected person/number.
"""

from __future__ import annotations

from typing import Optional

from spacy.tokens import Doc

from .base import ErrorResult, Rule

# Present tense conjugations for common irregular verbs.
# Keyed by (lemma, person, number) → correct surface form.
_PRESENT_FORMS: dict[tuple[str, str, str], str] = {
    # être
    ("être", "1", "Sing"): "suis",
    ("être", "2", "Sing"): "es",
    ("être", "3", "Sing"): "est",
    ("être", "1", "Plur"): "sommes",
    ("être", "2", "Plur"): "êtes",
    ("être", "3", "Plur"): "sont",
    # avoir
    ("avoir", "1", "Sing"): "ai",
    ("avoir", "2", "Sing"): "as",
    ("avoir", "3", "Sing"): "a",
    ("avoir", "1", "Plur"): "avons",
    ("avoir", "2", "Plur"): "avez",
    ("avoir", "3", "Plur"): "ont",
    # aller
    ("aller", "1", "Sing"): "vais",
    ("aller", "2", "Sing"): "vas",
    ("aller", "3", "Sing"): "va",
    ("aller", "1", "Plur"): "allons",
    ("aller", "2", "Plur"): "allez",
    ("aller", "3", "Plur"): "vont",
    # faire
    ("faire", "1", "Sing"): "fais",
    ("faire", "2", "Sing"): "fais",
    ("faire", "3", "Sing"): "fait",
    ("faire", "1", "Plur"): "faisons",
    ("faire", "2", "Plur"): "faites",
    ("faire", "3", "Plur"): "font",
}

_TRACKED_LEMMAS: set[str] = {"être", "avoir", "aller", "faire"}


class VerbFormRule(Rule):
    """Detect incorrect conjugation of common irregular verbs."""

    levels = {"A1", "A2"}

    def check(self, doc: Doc) -> Optional[ErrorResult]:
        for token in doc:
            if token.pos_ not in ("VERB", "AUX"):
                continue

            lemma = token.lemma_.lower()
            if lemma not in _TRACKED_LEMMAS:
                continue

            morph = token.morph

            # Only check present indicative
            tense = morph.get("Tense")
            mood = morph.get("Mood")
            if not tense or "Pres" not in tense:
                continue
            if mood and "Ind" not in mood:
                continue

            person = morph.get("Person")
            number = morph.get("Number")
            if not person or not number:
                continue

            key = (lemma, person[0], number[0])
            expected = _PRESENT_FORMS.get(key)
            if expected is None:
                continue

            actual = token.text.lower()
            if actual != expected:
                return ErrorResult(
                    error_found=True,
                    error_type="verb_conjugation",
                    error_detail=(
                        f"'{token.text}' — the correct form of "
                        f"'{lemma}' here is '{expected}'"
                    ),
                    corrected_form=expected,
                )

        return None
