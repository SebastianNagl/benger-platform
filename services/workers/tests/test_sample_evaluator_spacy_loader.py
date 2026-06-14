"""Branch coverage for SampleEvaluator._get_de_spacy (the lazy spaCy German
model loader/cacher) in ml_evaluation/sample_evaluator.py.

The German-coherence suite (test_coherence_german.py) only ever forces the
NEGATIVE cache (``monkeypatch.setattr(SampleEvaluator, "_DE_NLP_CACHE", False)``)
to exercise the capitalization-heuristic fallback. It never drives
``_get_de_spacy`` itself, so the loader's three arms are unreached:

  * cache is None + ``spacy.load`` succeeds -> caches and returns the nlp object,
  * cache is None + the import/load raises ImportError/OSError -> warns, caches
    ``False``, returns None (model wheel absent / spaCy not installed),
  * cache already populated -> returns it without re-loading (the ``== None``
    guard short-circuits).

``spacy`` may or may not be installed in the test image, so we inject a fake
``spacy`` module into ``sys.modules`` for the success/OSError cases and delete
it for the ImportError case — all via monkeypatch so the real module state is
restored afterwards. ``_DE_NLP_CACHE`` is a CLASS attribute; we reset it per
test through monkeypatch.setattr so cross-test ordering can't leak a cached
value. No real model is downloaded. Mirrors test_coherence_german.py idioms.
"""

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml_evaluation.sample_evaluator import SampleEvaluator  # noqa: E402


class TestGetDeSpacyLoader:
    def test_successful_load_caches_and_returns_nlp(self, monkeypatch):
        """cache None -> spacy.load returns an object -> it is cached + returned,
        and load() is called with the lean disable=[...] pipeline list."""
        # Reset the class cache to the "not yet attempted" state.
        monkeypatch.setattr(SampleEvaluator, "_DE_NLP_CACHE", None)

        fake_nlp = MagicMock(name="nlp")
        fake_spacy = MagicMock(name="spacy")
        fake_spacy.load.return_value = fake_nlp
        monkeypatch.setitem(sys.modules, "spacy", fake_spacy)

        result = SampleEvaluator._get_de_spacy()

        assert result is fake_nlp
        # Cached on the class for the next call.
        assert SampleEvaluator._DE_NLP_CACHE is fake_nlp
        fake_spacy.load.assert_called_once()
        load_args, load_kwargs = fake_spacy.load.call_args
        assert load_args[0] == "de_core_news_md"
        # The heavy components are disabled (NER-only load).
        assert "parser" in load_kwargs["disable"]
        assert "lemmatizer" in load_kwargs["disable"]

    def test_already_cached_returns_without_reloading(self, monkeypatch):
        """A populated cache short-circuits the ``== None`` guard: spacy.load is
        never invoked again."""
        sentinel = MagicMock(name="cached_nlp")
        monkeypatch.setattr(SampleEvaluator, "_DE_NLP_CACHE", sentinel)

        fake_spacy = MagicMock(name="spacy")
        monkeypatch.setitem(sys.modules, "spacy", fake_spacy)

        result = SampleEvaluator._get_de_spacy()

        assert result is sentinel
        fake_spacy.load.assert_not_called()

    def test_import_error_caches_false_and_returns_none(self, monkeypatch):
        """spaCy not importable: the ``import spacy`` raises ImportError -> warn,
        cache False, return None (community-edition / no-spaCy path)."""
        monkeypatch.setattr(SampleEvaluator, "_DE_NLP_CACHE", None)
        # Make ``import spacy`` fail inside the method.
        monkeypatch.setitem(sys.modules, "spacy", None)

        result = SampleEvaluator._get_de_spacy()

        assert result is None
        # Negative result is cached so we don't retry on every sentence.
        assert SampleEvaluator._DE_NLP_CACHE is False

    def test_oserror_on_load_caches_false_and_returns_none(self, monkeypatch):
        """spaCy installed but the model wheel is missing: ``spacy.load`` raises
        OSError -> warn, cache False, return None."""
        monkeypatch.setattr(SampleEvaluator, "_DE_NLP_CACHE", None)

        fake_spacy = MagicMock(name="spacy")
        fake_spacy.load.side_effect = OSError("model 'de_core_news_md' not found")
        monkeypatch.setitem(sys.modules, "spacy", fake_spacy)

        result = SampleEvaluator._get_de_spacy()

        assert result is None
        assert SampleEvaluator._DE_NLP_CACHE is False

    def test_cached_false_returns_none_without_reload(self, monkeypatch):
        """A cached negative (False) also short-circuits the ``== None`` guard
        and maps to a None return (the ``if cls._DE_NLP_CACHE else None`` tail)."""
        monkeypatch.setattr(SampleEvaluator, "_DE_NLP_CACHE", False)

        fake_spacy = MagicMock(name="spacy")
        monkeypatch.setitem(sys.modules, "spacy", fake_spacy)

        result = SampleEvaluator._get_de_spacy()

        assert result is None
        fake_spacy.load.assert_not_called()
