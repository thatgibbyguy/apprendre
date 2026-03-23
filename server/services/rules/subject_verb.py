"""Tier 2: Subject-verb agreement rule.

Detects person/number mismatches between a subject pronoun and its verb
by checking the verb's surface form against a conjugation table.
Only flags errors for tracked verbs where we KNOW the correct form.
This avoids false positives from spaCy's unreliable Person tagging.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

from spacy.tokens import Doc

from .base import ErrorResult, Rule

# Subject pronouns → expected (person, number).
_PRONOUN_FEATURES: dict[str, tuple[str, str]] = {
    "je": ("1", "Sing"),
    "j'": ("1", "Sing"),
    "tu": ("2", "Sing"),
    "il": ("3", "Sing"),
    "elle": ("3", "Sing"),
    "on": ("3", "Sing"),
    "nous": ("1", "Plur"),
    "vous": ("2", "Plur"),
    "ils": ("3", "Plur"),
    "elles": ("3", "Plur"),
}

# Conjugation tables for tracked verbs.
# (lemma, person, number) → correct surface form.
_CONJUGATIONS: dict[tuple[str, str, str], str] = {
    # être — present
    ("être", "1", "Sing"): "suis",
    ("être", "2", "Sing"): "es",
    ("être", "3", "Sing"): "est",
    ("être", "1", "Plur"): "sommes",
    ("être", "2", "Plur"): "êtes",
    ("être", "3", "Plur"): "sont",
    # avoir — present
    ("avoir", "1", "Sing"): "ai",
    ("avoir", "2", "Sing"): "as",
    ("avoir", "3", "Sing"): "a",
    ("avoir", "1", "Plur"): "avons",
    ("avoir", "2", "Plur"): "avez",
    ("avoir", "3", "Plur"): "ont",
    # aller — present
    ("aller", "1", "Sing"): "vais",
    ("aller", "2", "Sing"): "vas",
    ("aller", "3", "Sing"): "va",
    ("aller", "1", "Plur"): "allons",
    ("aller", "2", "Plur"): "allez",
    ("aller", "3", "Plur"): "vont",
    # faire — present
    ("faire", "1", "Sing"): "fais",
    ("faire", "2", "Sing"): "fais",
    ("faire", "3", "Sing"): "fait",
    ("faire", "1", "Plur"): "faisons",
    ("faire", "2", "Plur"): "faites",
    ("faire", "3", "Plur"): "font",
    # faire — future (common A1 error: "il feras" instead of "il fera")
    ("faire", "1", "Sing", "Fut"): "ferai",
    ("faire", "2", "Sing", "Fut"): "feras",
    ("faire", "3", "Sing", "Fut"): "fera",
    ("faire", "1", "Plur", "Fut"): "ferons",
    ("faire", "2", "Plur", "Fut"): "ferez",
    ("faire", "3", "Plur", "Fut"): "feront",
}

# Build a reverse lookup: surface form → set of (person, number) it's valid for.
# This handles ambiguous forms like "fais" (valid for both je and tu).
_VALID_FOR: dict[str, set[tuple[str, str]]] = defaultdict(set)
for _key, _form in _CONJUGATIONS.items():
    # Keys can be 3-tuple (lemma, person, number) or 4-tuple (+ tense)
    _person, _number = _key[1], _key[2]
    _VALID_FOR[_form].add((_person, _number))

# All surface forms of tracked verbs (to know when we can make a judgment).
_TRACKED_FORMS: set[str] = set(_VALID_FOR.keys())

# Tracked lemmas
_TRACKED_LEMMAS: set[str] = {"être", "avoir", "aller", "faire"}


class SubjectVerbRule(Rule):
    """Detect subject-verb agreement errors using conjugation lookup."""

    levels = {"A1", "A2", "B1", "B2"}

    def check(self, doc: Doc) -> Optional[ErrorResult]:
        for token in doc:
            lower = token.text.lower()
            if lower not in _PRONOUN_FEATURES:
                continue

            # Must be a subject of a verb
            if token.dep_ not in ("nsubj", "nsubj:pass", "expl:subj"):
                continue

            verb = token.head
            if verb.pos_ not in ("VERB", "AUX"):
                continue

            # Only check tracked verbs where we have conjugation data
            verb_lemma = verb.lemma_.lower()
            verb_form = verb.text.lower()
            if verb_lemma not in _TRACKED_LEMMAS and verb_form not in _TRACKED_FORMS:
                continue

            expected_person, expected_number = _PRONOUN_FEATURES[lower]

            # Check if the actual verb form is valid for this subject
            valid_combos = _VALID_FOR.get(verb_form, set())
            if (expected_person, expected_number) in valid_combos:
                continue  # Form is correct for this subject

            # The form exists in our table but NOT for this subject → error
            if valid_combos:
                # Find the correct form for this subject + verb lemma
                correct = _CONJUGATIONS.get((verb_lemma, expected_person, expected_number))
                return ErrorResult(
                    error_found=True,
                    error_type="subject_verb_agreement",
                    error_detail=(
                        f"'{token.text} {verb.text}' — with '{token.text}', "
                        f"use '{correct or '?'}'"
                    ),
                    corrected_form=f"{token.text} {correct}" if correct else None,
                    source="rule",
                )

            # Form not in our table at all (e.g. a tense we don't track)
            # but lemma IS tracked — check by lemma + expected person
            if verb_lemma in _TRACKED_LEMMAS:
                correct = _CONJUGATIONS.get((verb_lemma, expected_person, expected_number))
                if correct and correct != verb_form:
                    return ErrorResult(
                        error_found=True,
                        error_type="subject_verb_agreement",
                        error_detail=(
                            f"'{token.text} {verb.text}' — with '{token.text}', "
                            f"use '{correct}'"
                        ),
                        corrected_form=f"{token.text} {correct}" if correct else None,
                        source="rule",
                    )

        return None
