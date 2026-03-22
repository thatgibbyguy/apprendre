"""Tier 1: Allowlist checker.

Known-correct phrases and patterns that should never be flagged as errors.
This catches false positives before they reach the rule engine or LLM.
"""

from __future__ import annotations

import re

# Normalized (lowercased, stripped) phrases that are always correct.
# These are common greetings, responses, and formulaic expressions
# that small LLMs frequently misclassify.
_EXACT_PHRASES: set[str] = {
    # Greetings
    "bonjour",
    "bonsoir",
    "bonne nuit",
    "salut",
    "coucou",
    "allô",
    # Farewells
    "au revoir",
    "à bientôt",
    "à demain",
    "à plus",
    "à plus tard",
    "bonne journée",
    "bonne soirée",
    # How are you / responses
    "ça va",
    "ça va bien",
    "ça va bien merci",
    "ça va et toi",
    "ça va et vous",
    "comment ça va",
    "comment vas-tu",
    "comment allez-vous",
    "je vais bien",
    "je vais bien merci",
    "je vais bien et toi",
    "je vais très bien",
    "je vais très bien merci",
    "pas mal",
    "pas mal merci",
    "comme ci comme ça",
    "et toi",
    "et vous",
    # Politeness
    "merci",
    "merci beaucoup",
    "merci bien",
    "s'il te plaît",
    "s'il vous plaît",
    "de rien",
    "je vous en prie",
    "je t'en prie",
    "excusez-moi",
    "excuse-moi",
    "pardon",
    # Common responses
    "oui",
    "non",
    "d'accord",
    "bien sûr",
    "peut-être",
    "je ne sais pas",
    "je sais pas",
    "c'est vrai",
    "c'est pas vrai",
    "ah bon",
    "ah oui",
    "ah non",
    "tant pis",
    "tant mieux",
    "pas de problème",
    # Introductions
    "enchanté",
    "enchantée",
    "ravi de vous rencontrer",
    "ravi de te rencontrer",
    "ravie de vous rencontrer",
    "ravie de te rencontrer",
}

# Patterns that are always correct (regex on normalized text).
_CORRECT_PATTERNS: list[re.Pattern[str]] = [
    # "je m'appelle X" — always correct
    re.compile(r"^je m'appelle\b"),
    # "j'habite à/en/au X" — always correct
    re.compile(r"^j'habite\b"),
    # "je suis + nationality/profession" — always correct at this level
    re.compile(r"^je suis\b"),
    # "il y a" — always correct
    re.compile(r"\bil y a\b"),
    # "c'est + adjective" — always correct structure
    re.compile(r"^c'est\b"),
]


def _normalize(text: str) -> str:
    """Lowercase, strip, collapse whitespace, remove trailing punctuation."""
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    text = text.rstrip("?!.,;:")
    return text.strip()


def is_known_correct(message: str) -> bool:
    """Return True if the message matches a known-correct pattern."""
    normalized = _normalize(message)

    if normalized in _EXACT_PHRASES:
        return True

    for pattern in _CORRECT_PATTERNS:
        if pattern.search(normalized):
            return True

    return False
