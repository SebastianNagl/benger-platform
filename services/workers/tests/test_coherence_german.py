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
    """Test _extract_entities_german."""

    def test_extracts_capitalized_nouns(self, evaluator):
        sentences = [
            "Der Vertrag wurde geschlossen.",
            "Die Parteien haben den Vertrag unterschrieben.",
        ]
        grid = evaluator._extract_entities_german(sentences)
        entities = set(grid.keys())
        assert 'vertrag' in entities
        assert 'parteien' in entities

    def test_skips_sentence_initial_words(self, evaluator):
        """First word of each sentence is always capitalized, should be skipped."""
        sentences = [
            "Der Richter prüfte den Fall.",
            "Der Anwalt legte Berufung ein.",
        ]
        grid = evaluator._extract_entities_german(sentences)
        entities = set(grid.keys())
        # "Richter", "Fall" should be detected (non-initial, capitalized)
        assert 'richter' in entities
        assert 'fall' in entities
        # "Der" should NOT be detected (sentence-initial)
        assert 'der' not in entities

    def test_detects_german_pronouns(self, evaluator):
        sentences = [
            "Der Kläger reichte die Klage ein.",
            "Er forderte Schadensersatz von ihr.",
        ]
        grid = evaluator._extract_entities_german(sentences)
        entities = set(grid.keys())
        assert 'er' in entities
        assert 'ihr' in entities

    def test_entity_grid_structure(self, evaluator):
        sentences = [
            "Der Vertrag regelt die Pflichten.",
            "Der Vertrag wurde unterschrieben.",
            "Die Pflichten sind klar definiert.",
        ]
        grid = evaluator._extract_entities_german(sentences)
        # "vertrag" appears in sentences 0 and 1
        assert grid['vertrag'][0] == 'X'
        assert grid['vertrag'][1] == 'X'
        assert grid['vertrag'][2] == '-'
        # "pflichten" appears in sentences 0 and 2
        assert grid['pflichten'][0] == 'X'
        assert grid['pflichten'][2] == 'X'

    def test_empty_sentences(self, evaluator):
        grid = evaluator._extract_entities_german([])
        assert grid == {}


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
        """Coherent text with shared entities should score well."""
        sentences = [
            "Der Vertrag wurde am Montag geschlossen.",
            "Der Vertrag regelt die Pflichten beider Parteien.",
            "Die Parteien haben den Vertrag unterschrieben.",
        ]
        score = evaluator._compute_entity_coherence(sentences)
        assert 0.0 <= score <= 1.0
        assert score > 0.3, f"Coherent text should score > 0.3, got {score}"

    def test_incoherent_german_text(self, evaluator):
        """Text with no shared entities should score lower."""
        sentences = [
            "Der Richter prüfte den Sachverhalt.",
            "Die Klägerin forderte Schadensersatz.",
            "Ein Gutachter wurde hinzugezogen.",
        ]
        score = evaluator._compute_entity_coherence(sentences)
        assert 0.0 <= score <= 1.0

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
        """Full German legal paragraph should compute without error."""
        sentences = [
            "Der Beklagte hat gegen seine vertraglichen Pflichten verstoßen.",
            "Die Pflichten ergeben sich aus dem Kaufvertrag vom Januar.",
            "Der Kaufvertrag enthält eine Haftungsklausel.",
            "Diese Klausel schließt die Haftung für leichte Fahrlässigkeit aus.",
        ]
        score = evaluator._compute_entity_coherence(sentences)
        assert 0.0 <= score <= 1.0
        # Shared entities across sentences: Pflichten, Kaufvertrag, Klausel, Haftung
        assert score > 0.15
