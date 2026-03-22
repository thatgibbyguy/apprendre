"""Tier 2: Être/avoir auxiliary rule.

Detects incorrect auxiliary verb in passé composé. A closed list of ~17
verbs (DR MRS VANDERTRAMP) require être; everything else uses avoir.
"""

from __future__ import annotations

from typing import Optional

from spacy.tokens import Doc

from .base import ErrorResult, Rule

# Verbs that take être as auxiliary in passé composé.
# Includes the base verbs and their common derivatives.
_ETRE_VERBS: set[str] = {
    "aller",
    "arriver",
    "descendre",
    "devenir",
    "entrer",
    "monter",
    "mourir",
    "naître",
    "partir",
    "passer",
    "rentrer",
    "rester",
    "retourner",
    "revenir",
    "sortir",
    "tomber",
    "venir",
}

# All reflexive verbs also take être, but we detect those by the "se" pronoun
# rather than listing them.


class AuxiliaryRule(Rule):
    """Detect wrong auxiliary in passé composé."""

    levels = {"A1", "A2", "B1", "B2"}

    def check(self, doc: Doc) -> Optional[ErrorResult]:
        for token in doc:
            # Look for past participles
            if token.pos_ != "VERB":
                continue

            morph = token.morph
            verb_form = morph.get("VerbForm")
            if not verb_form or "Part" not in verb_form:
                continue

            tense = morph.get("Tense")
            if not tense or "Past" not in tense:
                continue

            # Find the auxiliary
            aux = None
            for child in token.children:
                if child.dep_ == "aux" and child.pos_ == "AUX":
                    aux = child
                    break

            if aux is None:
                continue

            aux_lemma = aux.lemma_.lower()
            verb_lemma = token.lemma_.lower()

            # Check if this verb requires être
            needs_etre = verb_lemma in _ETRE_VERBS

            # Check for reflexive (se/s' pronoun) — always takes être
            for child in token.children:
                if child.dep_ == "expl:comp" or (
                    child.pos_ == "PRON"
                    and child.lemma_.lower() == "se"
                ):
                    needs_etre = True
                    break

            if needs_etre and aux_lemma == "avoir":
                return ErrorResult(
                    error_found=True,
                    error_type="auxiliary_choice",
                    error_detail=(
                        f"'{verb_lemma}' uses être in passé composé, "
                        f"not avoir"
                    ),
                    corrected_form=f"être {token.text}",
                )

            if not needs_etre and aux_lemma == "être":
                # Less common error but possible
                return ErrorResult(
                    error_found=True,
                    error_type="auxiliary_choice",
                    error_detail=(
                        f"'{verb_lemma}' uses avoir in passé composé, "
                        f"not être"
                    ),
                    corrected_form=f"avoir {token.text}",
                )

        return None
