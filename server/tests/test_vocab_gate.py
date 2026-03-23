"""Tests for server.services.vocab_gate.

check_a1_vocab() returns structured dicts instead of plain strings so the
frontend can display English translations in hover tooltips.

spaCy is an optional runtime dependency (not installed in the test
environment).  These tests mock it out at the sys.modules level so that the
module can be imported and the pure-Python logic can be exercised.
"""

from __future__ import annotations

import sys
import types
import importlib
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# spaCy stub — injected into sys.modules before vocab_gate is imported so
# the top-level ``import spacy`` succeeds even without the real package.
# ---------------------------------------------------------------------------

def _install_spacy_stub() -> None:
    """Install a minimal spaCy stub into sys.modules if spaCy is absent."""
    if "spacy" in sys.modules:
        return  # real spaCy is available — nothing to do

    stub = types.ModuleType("spacy")

    # spacy.load() will be overridden per-test; provide a default that raises
    # OSError so _nlp is set to None (safe fallback path).
    def _load(model_name: str, **kwargs):
        raise OSError(f"stub: model {model_name!r} not found")

    stub.load = _load

    # spacy.tokens is referenced in the type annotation import (Doc).
    tokens_stub = types.ModuleType("spacy.tokens")
    tokens_stub.Doc = object

    sys.modules["spacy"] = stub
    sys.modules["spacy.tokens"] = tokens_stub


_install_spacy_stub()


# ---------------------------------------------------------------------------
# Helpers — build lightweight spaCy-style token / doc mocks
# ---------------------------------------------------------------------------

def _make_token(text: str, lemma: str, pos: str, is_punct: bool = False) -> MagicMock:
    tok = MagicMock()
    tok.text = text
    tok.lemma_ = lemma
    tok.pos_ = pos
    tok.is_punct = is_punct
    tok.is_space = False
    return tok


def _make_doc(tokens: list) -> MagicMock:
    doc = MagicMock()
    doc.__iter__ = lambda self: iter(tokens)
    return doc


def _load_module():
    """Import (or reload) vocab_gate so tests get a clean module state."""
    # Remove any cached copy so the module-level try/except re-runs.
    for key in list(sys.modules.keys()):
        if "vocab_gate" in key:
            del sys.modules[key]
    import server.services.vocab_gate as vg
    return vg


# ---------------------------------------------------------------------------
# Fixture: a fresh module with _nlp stubbed to a controllable callable
# ---------------------------------------------------------------------------

@pytest.fixture()
def vg_with_nlp(monkeypatch):
    """Return (module, nlp_mock) where nlp_mock is assigned to module._nlp."""
    vg = _load_module()
    nlp_mock = MagicMock()
    monkeypatch.setattr(vg, "_nlp", nlp_mock)
    return vg, nlp_mock


@pytest.fixture()
def vg_no_nlp(monkeypatch):
    """Return the module with _nlp set to None (spaCy unavailable path)."""
    vg = _load_module()
    monkeypatch.setattr(vg, "_nlp", None)
    return vg


# ---------------------------------------------------------------------------
# Tests: return shape and values
# ---------------------------------------------------------------------------

class TestCheckA1VocabReturnShape:

    def test_nlp_none_returns_pass(self, vg_no_nlp):
        """When spaCy is unavailable the gate should pass everything."""
        passes, ratio, unknown = vg_no_nlp.check_a1_vocab("quelque chose")
        assert passes is True
        assert ratio == 1.0
        assert unknown == []

    def test_empty_doc_returns_pass(self, vg_with_nlp):
        vg, nlp_mock = vg_with_nlp
        nlp_mock.return_value = _make_doc([])
        passes, ratio, unknown = vg.check_a1_vocab("")
        assert passes is True
        assert ratio == 1.0
        assert unknown == []

    def test_all_a1_words_returns_empty_unknown(self, vg_with_nlp):
        vg, nlp_mock = vg_with_nlp
        tokens = [
            _make_token("mange", "manger", "VERB"),
            _make_token("pain", "pain", "NOUN"),
        ]
        nlp_mock.return_value = _make_doc(tokens)
        passes, ratio, unknown = vg.check_a1_vocab("Il mange du pain.")
        assert passes is True
        assert ratio == 1.0
        assert unknown == []

    def test_unknown_word_returns_dict_with_required_keys(self, vg_with_nlp):
        vg, nlp_mock = vg_with_nlp
        tokens = [_make_token("déroulé", "dérouler", "VERB")]
        nlp_mock.return_value = _make_doc(tokens)
        _, _, unknown = vg.check_a1_vocab("Ça s'est bien déroulé.")
        assert len(unknown) == 1
        item = unknown[0]
        assert "word" in item
        assert "lemma" in item
        assert "translation" in item

    def test_unknown_word_surface_form_preserved(self, vg_with_nlp):
        vg, nlp_mock = vg_with_nlp
        tokens = [_make_token("déroulé", "dérouler", "VERB")]
        nlp_mock.return_value = _make_doc(tokens)
        _, _, unknown = vg.check_a1_vocab("Ça s'est bien déroulé.")
        assert unknown[0]["word"] == "déroulé"
        assert unknown[0]["lemma"] == "dérouler"

    def test_known_translation_populated(self, vg_with_nlp):
        vg, nlp_mock = vg_with_nlp
        tokens = [_make_token("déroulé", "dérouler", "VERB")]
        nlp_mock.return_value = _make_doc(tokens)
        _, _, unknown = vg.check_a1_vocab("Ça s'est bien déroulé.")
        translation = unknown[0]["translation"]
        assert translation is not None
        # Accept any of the reasonable English glosses
        assert any(
            kw in translation
            for kw in ("unroll", "unfold", "take place", "go")
        )

    def test_unknown_lemma_translation_is_none(self, vg_with_nlp):
        """An obscure lemma absent from TRANSLATIONS yields translation=None."""
        vg, nlp_mock = vg_with_nlp
        tokens = [_make_token("zythophile", "zythophile", "NOUN")]
        nlp_mock.return_value = _make_doc(tokens)
        _, _, unknown = vg.check_a1_vocab("Un zythophile.")
        assert unknown[0]["translation"] is None

    def test_ratio_calculation_two_unknown_of_four(self, vg_with_nlp):
        vg, nlp_mock = vg_with_nlp
        tokens = [
            _make_token("mange", "manger", "VERB"),       # A1
            _make_token("délicieux", "délicieux", "ADJ"),  # above A1
            _make_token("pain", "pain", "NOUN"),           # A1
            _make_token("frais", "frais", "ADJ"),          # above A1
        ]
        nlp_mock.return_value = _make_doc(tokens)
        passes, ratio, unknown = vg.check_a1_vocab("Il mange du pain délicieux et frais.")
        assert ratio == pytest.approx(0.5)
        assert passes is False
        assert len(unknown) == 2

    def test_non_content_pos_skipped(self, vg_with_nlp):
        """Determiners and conjunctions are not counted."""
        vg, nlp_mock = vg_with_nlp
        tokens = [
            _make_token("le", "le", "DET"),
            _make_token("et", "et", "CCONJ"),
        ]
        nlp_mock.return_value = _make_doc(tokens)
        passes, ratio, unknown = vg.check_a1_vocab("le et")
        assert passes is True
        assert ratio == 1.0
        assert unknown == []

    def test_punct_tokens_skipped(self, vg_with_nlp):
        vg, nlp_mock = vg_with_nlp
        tokens = [
            _make_token(",", ",", "PUNCT", is_punct=True),
        ]
        nlp_mock.return_value = _make_doc(tokens)
        passes, ratio, unknown = vg.check_a1_vocab(",")
        assert passes is True
        assert unknown == []


# ---------------------------------------------------------------------------
# Tests: TRANSLATIONS constant invariants
# ---------------------------------------------------------------------------

class TestTranslationsDict:

    def test_translations_is_dict(self):
        vg = _load_module()
        assert isinstance(vg.TRANSLATIONS, dict)

    def test_translations_keys_are_lowercase(self):
        vg = _load_module()
        for key in vg.TRANSLATIONS:
            assert key == key.lower(), f"Key not lowercase: {key!r}"

    def test_translations_values_are_non_empty_strings(self):
        vg = _load_module()
        for key, value in vg.TRANSLATIONS.items():
            assert isinstance(value, str) and value.strip(), (
                f"Empty or non-string value for key {key!r}"
            )

    def test_a1_words_not_in_translations(self):
        """Words in A1_WORDS would never be flagged, so TRANSLATIONS entries
        for them would be dead code."""
        vg = _load_module()
        overlap = vg.A1_WORDS & set(vg.TRANSLATIONS.keys())
        assert not overlap, (
            f"Keys in both A1_WORDS and TRANSLATIONS (dead code): {overlap}"
        )
