"""Tier 2: Gender agreement rule.

Detects mismatches between determiner gender and noun gender using spaCy
morphological features. Only flags when both the determiner and noun have
unambiguous gender annotations.
"""

from __future__ import annotations

from typing import Optional

from spacy.tokens import Doc, Token

from .base import ErrorResult, Rule

# Determiners where gender matters. Maps lemma → {masc_form, fem_form}.
_DET_FORMS: dict[str, dict[str, str]] = {
    "le": {"Masc": "le", "Fem": "la"},
    "un": {"Masc": "un", "Fem": "une"},
    "ce": {"Masc": "ce", "Fem": "cette"},
    "mon": {"Masc": "mon", "Fem": "ma"},
    "ton": {"Masc": "ton", "Fem": "ta"},
    "son": {"Masc": "son", "Fem": "sa"},
}

# Common nouns where spaCy might get the gender wrong.
# Overrides keyed by lemma → correct gender.
_GENDER_OVERRIDES: dict[str, str] = {
    # Feminine nouns often misclassified
    "maison": "Fem",
    "voiture": "Fem",
    "table": "Fem",
    "chaise": "Fem",
    "école": "Fem",
    "rue": "Fem",
    "fille": "Fem",
    "femme": "Fem",
    "nuit": "Fem",
    "vie": "Fem",
    "chose": "Fem",
    "personne": "Fem",
    "place": "Fem",
    "porte": "Fem",
    "chambre": "Fem",
    "cuisine": "Fem",
    "bouche": "Fem",
    "main": "Fem",
    # Masculine nouns sometimes misclassified
    "livre": "Masc",
    "garçon": "Masc",
    "homme": "Masc",
    "jour": "Masc",
    "soir": "Masc",
    "matin": "Masc",
    "travail": "Masc",
    "problème": "Masc",
}


def _get_gender(token: Token) -> Optional[str]:
    """Extract gender from a token's morphological features."""
    morph = token.morph
    gender = morph.get("Gender")
    if gender:
        return gender[0]  # Returns "Masc" or "Fem"
    return None


def _noun_gender(token: Token) -> Optional[str]:
    """Get the gender of a noun, using overrides when available."""
    lemma = token.lemma_.lower()
    if lemma in _GENDER_OVERRIDES:
        return _GENDER_OVERRIDES[lemma]
    return _get_gender(token)


class GenderRule(Rule):
    """Detect determiner-noun gender disagreement."""

    levels = {"A1", "A2", "B1", "B2"}

    def check(self, doc: Doc) -> Optional[ErrorResult]:
        for token in doc:
            # Look for determiners
            if token.pos_ != "DET":
                continue

            det_lemma = token.lemma_.lower()
            if det_lemma not in _DET_FORMS:
                continue

            # Find the noun this determiner modifies
            head = token.head
            if head.pos_ not in ("NOUN", "PROPN"):
                continue

            det_gender = _get_gender(token)
            noun_gender = _noun_gender(head)

            # Only flag when both genders are unambiguous
            if not det_gender or not noun_gender:
                continue

            if det_gender != noun_gender:
                forms = _DET_FORMS[det_lemma]
                correct_det = forms.get(noun_gender, token.text)
                return ErrorResult(
                    error_found=True,
                    error_type="gender_agreement",
                    error_detail=(
                        f"'{token.text}' with '{head.text}' "
                        f"({noun_gender.lower()}) — "
                        f"should be '{correct_det}'"
                    ),
                    corrected_form=f"{correct_det} {head.text}",
                )

        return None
