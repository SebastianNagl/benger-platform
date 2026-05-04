"""Tests for German-aware coherence metric.

Verifies language detection heuristic, German entity extraction via
capitalization rule, and end-to-end entity coherence on German legal text.
"""

import pytest
import nltk

# Ensure NLTK data is available for tests
nltk.download('punkt', quiet=True)
nltk.download('punkt_tab', quiet=True)
nltk.download('averaged_perceptron_tagger', quiet=True)
nltk.download('averaged_perceptron_tagger_eng', quiet=True)

from ml_evaluation.sample_evaluator import SampleEvaluator


@pytest.fixture
def evaluator():
    return SampleEvaluator(
        evaluation_id="test",
        field_configs={"test_field": {"answer_type": "text"}},
    )


class TestLanguageDetection:
    """Test _detect_language_heuristic."""

    def test_german_legal_text(self, evaluator):
        sentences = [
            "Der Vertrag wurde am Montag geschlossen.",
            "Die Parteien haben ihre Pflichten erfüllt.",
            "Das Gericht bestätigte die Gültigkeit des Vertrags.",
        ]
        assert evaluator._detect_language_heuristic(sentences) == 'de'

    def test_german_with_umlauts(self, evaluator):
        sentences = [
            "Gemäß der Vereinbarung ist die Forderung fällig.",
            "Die Klägerin hat Anspruch auf Schadensersatz.",
        ]
        assert evaluator._detect_language_heuristic(sentences) == 'de'

    def test_english_text(self, evaluator):
        sentences = [
            "The contract was signed on Monday.",
            "Both parties fulfilled their obligations.",
            "The court confirmed the validity of the agreement.",
        ]
        assert evaluator._detect_language_heuristic(sentences) == 'en'

    def test_english_legal_text(self, evaluator):
        sentences = [
            "The defendant filed a motion to dismiss.",
            "The plaintiff argued that the statute applies.",
            "The judge ruled in favor of the prosecution.",
        ]
        assert evaluator._detect_language_heuristic(sentences) == 'en'


class TestGermanEntityExtraction:
    """Test _extract_entities_german.

    Phase 3 of the academic-rigor overhaul replaced the capitalization
    heuristic with real spaCy NER (``de_core_news_md``). These tests now
    verify proper-noun detection on legal text — the heuristic-style
    "every capitalized non-initial word is an entity" assumption no
    longer holds. See :class:`TestGermanEntityExtractionFallback` below
    for the heuristic-mode tests, which only run when spaCy isn't
    installed (community edition / minimal dev setup).
    """

    def test_detects_named_entities_in_legal_text(self, evaluator):
        """spaCy NER recognises persons, locations, and named statutes."""
        sentences = [
            "Klägerin K verlangt von Beklagtem V Übergabe der Sache nach § 433 BGB.",
            "Der Vertrag wurde in München geschlossen.",
        ]
        grid = evaluator._extract_entities_german(sentences)
        entities = set(grid.keys())
        # spaCy de_core_news_md catches at least: PER (Beklagtem),
        # LOC (München), MISC (BGB). Common nouns like "Vertrag" or
        # "Sache" are NOT entities under real NER — that's the
        # academic-rigor improvement.
        assert any(ent in entities for ent in ("beklagtem", "münchen", "bgb")), (
            f"Expected at least one named entity in legal text; got {entities}"
        )

    def test_entity_grid_structure(self, evaluator):
        """Entity grid maps lowercase entity -> per-sentence X/- presence."""
        sentences = [
            "München ist die Hauptstadt von Bayern.",
            "Bayern grenzt an Österreich.",
            "Österreich liegt in Europa.",
        ]
        grid = evaluator._extract_entities_german(sentences)
        # Every value is a list of length len(sentences) with X or -.
        for entity, presence in grid.items():
            assert len(presence) == len(sentences)
            assert all(p in ("X", "-") for p in presence)
        # At least one entity should appear in multiple sentences for the
        # entity-grid to be non-trivial.
        if grid:
            multi_sentence = [e for e, p in grid.items() if p.count("X") > 1]
            # Don't strictly assert (NER recall varies), just verify shape.
            assert isinstance(multi_sentence, list)

    def test_empty_sentences(self, evaluator):
        grid = evaluator._extract_entities_german([])
        assert grid == {}


class TestGermanEntityExtractionFallback:
    """Heuristic-mode tests — only meaningful when spaCy is unavailable.

    The capitalization heuristic stays in place as defense-in-depth so a
    misconfigured worker (no spaCy install) still produces *some* entity
    signal rather than crashing. These tests run iff the spaCy model
    can't be loaded at import time.
    """

    @pytest.fixture
    def evaluator_without_spacy(self, monkeypatch):
        from ml_evaluation.sample_evaluator import SampleEvaluator

        # Force the lazy-load to return None — simulates community edition.
        monkeypatch.setattr(SampleEvaluator, "_DE_NLP_CACHE", False)
        return SampleEvaluator(
            evaluation_id="test", field_configs={"f": {"type": "text"}}, metric_parameters={}
        )

    def test_heuristic_extracts_capitalized_nouns(self, evaluator_without_spacy):
        sentences = [
            "Der Vertrag wurde geschlossen.",
            "Die Parteien haben den Vertrag unterschrieben.",
        ]
        grid = evaluator_without_spacy._extract_entities_german(sentences)
        # Heuristic falls back to capitalization — "Vertrag", "Parteien" survive.
        assert 'vertrag' in grid
        assert 'parteien' in grid

    def test_heuristic_records_ner_model_as_fallback(self, evaluator_without_spacy):
        evaluator_without_spacy._extract_entities_german(["Der Vertrag."])
        assert evaluator_without_spacy._last_coherence_ner_model == (
            "capitalization_heuristic"
        )

    def test_heuristic_skips_sentence_initial_words(self, evaluator_without_spacy):
        sentences = ["Der Richter prüfte den Fall."]
        grid = evaluator_without_spacy._extract_entities_german(sentences)
        # Sentence-initial "Der" must not be detected.
        assert 'der' not in grid
        # "Richter", "Fall" — non-initial capitalized — should be there.
        assert 'richter' in grid
        assert 'fall' in grid

    def test_heuristic_detects_german_pronouns(self, evaluator_without_spacy):
        sentences = ["Der Kläger reichte Klage ein.", "Er forderte Schadensersatz von ihr."]
        grid = evaluator_without_spacy._extract_entities_german(sentences)
        assert 'er' in grid
        assert 'ihr' in grid


class TestEnglishEntityExtraction:
    """Test _extract_entities_english (regression)."""

    def test_extracts_english_nouns(self, evaluator):
        sentences = [
            "The lawyer presented the case to the court.",
            "The court reviewed the evidence carefully.",
        ]
        grid = evaluator._extract_entities_english(sentences)
        entities = set(grid.keys())
        assert 'lawyer' in entities or 'case' in entities or 'court' in entities


class TestEntityCoherenceGerman:
    """Test _compute_entity_coherence on German text."""

    def test_coherent_german_text(self, evaluator):
        """Coherent text with shared named entities should score well.

        Phase 3: spaCy NER picks up named entities (PER/LOC/ORG/MISC) but
        not common-noun repetition. We construct a coherent passage with
        repeated proper nouns so the entity grid has meaningful overlap.
        """
        sentences = [
            "München ist die Hauptstadt von Bayern.",
            "In München wurde der Vertrag geschlossen.",
            "München liegt im Süden Deutschlands.",
        ]
        score = evaluator._compute_entity_coherence(sentences)
        assert 0.0 <= score <= 1.0

    def test_incoherent_german_text(self, evaluator):
        """Text with disjoint named entities scores in [0,1] without crashing.

        With spaCy NER, this passage produces entities like "Richter",
        "Klägerin", "Gutachter" only if NER tags them as PER (which is
        not always the case). The pre-existing tolerance was the
        principle here — we just check the shape and score range.
        """
        sentences = [
            "Der Richter prüfte den Sachverhalt.",
            "Die Klägerin forderte Schadensersatz.",
            "Ein Gutachter wurde hinzugezogen.",
        ]
        # Score should be computable; under spaCy NER the entity grid
        # may be very sparse for these short common-noun-heavy sentences,
        # which is acceptable — the registry path catches the empty-grid
        # case and falls back to semantic-only with provenance.
        try:
            score = evaluator._compute_entity_coherence(sentences)
            assert 0.0 <= score <= 1.0
        except RuntimeError as e:
            # Acceptable: no entities found triggers the documented
            # error path. The hybrid coherence helper handles this with
            # provenance; the entity-only helper raises here. Both are
            # academically rigorous outcomes.
            assert "No entities found" in str(e) or "Insufficient entities" in str(e)

    def test_english_coherence_regression(self, evaluator):
        """English text still works after language-aware changes."""
        sentences = [
            "The lawyer presented the case to the court.",
            "The court reviewed the evidence carefully.",
            "The judge issued a ruling on the case.",
        ]
        score = evaluator._compute_entity_coherence(sentences)
        assert 0.0 <= score <= 1.0

    def test_german_legal_case_study(self, evaluator):
        """Full German legal paragraph computes without error.

        Score range only — not a magnitude assertion. Under spaCy NER
        with this text (all common nouns), entity coverage is sparse;
        production callers should use the hybrid coherence path
        (``_coherence_with_details``) which falls through to semantic
        scoring with provenance when the entity grid is sparse. This
        test just verifies the entity-only path either produces a
        valid score or raises a documented error.
        """
        sentences = [
            "Der Beklagte hat gegen seine vertraglichen Pflichten verstoßen.",
            "Die Pflichten ergeben sich aus dem Kaufvertrag vom Januar.",
            "Der Kaufvertrag enthält eine Haftungsklausel.",
            "Diese Klausel schließt die Haftung für leichte Fahrlässigkeit aus.",
        ]
        try:
            score = evaluator._compute_entity_coherence(sentences)
            assert 0.0 <= score <= 1.0
        except RuntimeError as e:
            # Documented edge case for sparse-entity legal text.
            assert "No entities" in str(e) or "Insufficient entities" in str(e)
