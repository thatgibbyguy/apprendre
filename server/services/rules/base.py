"""Base class for rule-based error detection rules."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from spacy.tokens import Doc


@dataclass
class ErrorResult:
    """Result from a rule check."""

    error_found: bool
    error_type: Optional[str] = None
    error_detail: Optional[str] = None
    corrected_form: Optional[str] = None
    source: str = "rule"


class Rule(ABC):
    """Abstract base for a single error detection rule."""

    # Subclasses set which CEFR levels this rule applies at.
    levels: set[str] = {"A1", "A2", "B1", "B2"}

    def applies_at_level(self, cefr_level: str) -> bool:
        return cefr_level.upper() in self.levels

    @abstractmethod
    def check(self, doc: Doc) -> Optional[ErrorResult]:
        """Check a spaCy Doc for this error type.

        Returns an ErrorResult if an error is found, None otherwise.
        """
