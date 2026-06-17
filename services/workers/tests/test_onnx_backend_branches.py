"""
Branch-coverage tests for ml_evaluation/backends/onnx_backend.py.

The ONNX backend classes wrap downloaded HuggingFace/sentence-transformers
models. We DO NOT download or run any real model here — instead we:

  * test ``is_available()`` guards by pre-seeding the cached ``_onnx_available``
    flag (the import-probe path is exercised once per class, but its result is
    only asserted to be a bool, never that a specific package is present),
  * test the pure-numpy scoring math in ``ONNXBERTScoreBackend._compute_bertscore``
    with crafted embedding arrays (known cosine-similarity outcomes),
  * inject MagicMock models/tokenizers onto the lazy-loaded attributes so the
    real ``_load_*`` paths never fire, then drive ``generate_questions`` /
    ``answer_question`` / ``score_consistency`` / ``encode`` / ``compute``
    through their surrounding control flow.

Mirrors the mocking idioms in test_ml_evaluation_deep_coverage.py
(TestTorchBackendAvailability): set the cached availability attribute, inject
``backend._model`` / ``backend._qa_pipeline`` MagicMocks, assert on returns.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# Ensure workers root is importable (mirrors conftest / deep_coverage)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _has_real_torch() -> bool:
    """True only when a full torch (with tensor/softmax) is importable.

    A couple of branches in answer_question / score_consistency call real
    torch ops (argmax / softmax) on the model output. The worker test image
    ships a full torch (conftest imports it), so those tests execute there.
    Some bare environments expose only a partial torch stub; skip cleanly
    rather than fail on a missing attribute that the production code never
    hits in those envs.
    """
    try:
        import torch

        return hasattr(torch, "tensor") and hasattr(torch, "softmax")
    except ImportError:
        return False


requires_torch = pytest.mark.skipif(
    not _has_real_torch(), reason="requires a full torch build (tensor/softmax)"
)


# ============================================================================
# ONNXEmbeddingBackend
# ============================================================================


class TestONNXEmbeddingBackend:
    def _backend(self):
        from ml_evaluation.backends.onnx_backend import ONNXEmbeddingBackend

        return ONNXEmbeddingBackend()

    def test_init_defaults(self):
        b = self._backend()
        assert b.model_name == "paraphrase-multilingual-MiniLM-L12-v2"
        assert b._model is None
        assert b._onnx_available is None

    def test_init_custom_model_name(self):
        from ml_evaluation.backends.onnx_backend import ONNXEmbeddingBackend

        b = ONNXEmbeddingBackend("my-custom-model")
        assert b.model_name == "my-custom-model"

    def test_is_available_returns_bool(self):
        b = self._backend()
        b._onnx_available = None
        result = b.is_available()
        assert isinstance(result, bool)

    def test_is_available_caches_true(self):
        b = self._backend()
        b._onnx_available = True
        assert b.is_available() is True

    def test_is_available_caches_false(self):
        b = self._backend()
        b._onnx_available = False
        assert b.is_available() is False

    def test_get_model_caches_injected(self):
        """If a model is already set, _get_model returns it without reloading."""
        b = self._backend()
        sentinel = MagicMock()
        b._model = sentinel
        assert b._get_model() is sentinel

    def test_encode_delegates_to_model(self):
        b = self._backend()
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1, 0.2, 0.3]])
        b._model = mock_model

        out = b.encode(["hello world"])
        mock_model.encode.assert_called_once_with(["hello world"], convert_to_numpy=True)
        assert out.shape == (1, 3)


# ============================================================================
# ONNXBERTScoreBackend — pure-numpy scoring + delegation
# ============================================================================


class TestONNXBERTScoreBackend:
    def _backend(self):
        from ml_evaluation.backends.onnx_backend import ONNXBERTScoreBackend

        return ONNXBERTScoreBackend()

    def test_init_defaults(self):
        b = self._backend()
        assert b.model_name == "bert-base-multilingual-cased"
        assert b._embedding_backend is None

    def test_is_available_returns_bool(self):
        b = self._backend()
        result = b.is_available()
        assert isinstance(result, bool)

    def test_get_embedding_backend_lazy_creates_and_caches(self):
        from ml_evaluation.backends.onnx_backend import ONNXEmbeddingBackend

        b = self._backend()
        eb = b._get_embedding_backend()
        assert isinstance(eb, ONNXEmbeddingBackend)
        # multilingual model selected for German support
        assert eb.model_name == "paraphrase-multilingual-MiniLM-L12-v2"
        # second call returns the same cached instance
        assert b._get_embedding_backend() is eb

    def test_compute_bertscore_identical_embeddings_is_one(self):
        """Identical normalized embeddings -> cosine sim 1.0 -> P=R=F1=1.0."""
        b = self._backend()
        embs = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        p, r, f1 = b._compute_bertscore(embs, embs)
        assert abs(p - 1.0) < 1e-9
        assert abs(r - 1.0) < 1e-9
        assert abs(f1 - 1.0) < 1e-9

    def test_compute_bertscore_orthogonal_embeddings(self):
        """Orthogonal single-token embeddings -> cosine sim 0 -> all 0, f1 0."""
        b = self._backend()
        cand = np.array([[1.0, 0.0]])
        ref = np.array([[0.0, 1.0]])
        p, r, f1 = b._compute_bertscore(cand, ref)
        assert abs(p - 0.0) < 1e-9
        assert abs(r - 0.0) < 1e-9
        # precision + recall == 0 -> f1 forced to 0.0 (the else branch)
        assert f1 == 0.0

    def test_compute_bertscore_f1_harmonic_mean(self):
        """Asymmetric alignment yields P != R and F1 as their harmonic mean.

        cand has 2 tokens, ref has 1 token. Token A aligns perfectly (sim 1),
        token B aligns at sim 0.5 to the single ref token.
          precision = mean(max over ref per cand) = mean(1.0, 0.5) = 0.75
          recall    = mean(max over cand per ref) = max(1.0, 0.5) = 1.0
          f1 = 2*0.75*1.0/(0.75+1.0) = 1.5/1.75
        """
        b = self._backend()
        # Build embeddings whose normalized cosine sims are exactly 1.0 and 0.5.
        # cand0 == ref0 (sim 1). cand1 at 60deg to ref0 (cos 60 = 0.5).
        ref = np.array([[1.0, 0.0]])
        cand = np.array(
            [
                [1.0, 0.0],  # sim 1.0 with ref0
                [0.5, np.sqrt(3) / 2],  # unit vector at 60deg -> cos = 0.5
            ]
        )
        p, r, f1 = b._compute_bertscore(cand, ref)
        assert abs(p - 0.75) < 1e-6
        assert abs(r - 1.0) < 1e-6
        assert abs(f1 - (2 * 0.75 * 1.0) / (0.75 + 1.0)) < 1e-6

    def test_compute_delegates_through_embedding_backend(self):
        """compute() encodes both sides via the embedding backend then scores."""
        b = self._backend()
        mock_emb = MagicMock()
        # Return identical embeddings for cand and ref -> F1 == 1.0
        mock_emb.encode.side_effect = [
            np.array([[1.0, 0.0]]),  # candidates
            np.array([[1.0, 0.0]]),  # references
        ]
        b._embedding_backend = mock_emb

        p, r, f1 = b.compute(["cand text"], ["ref text"], lang="de")
        assert mock_emb.encode.call_count == 2
        assert abs(f1 - 1.0) < 1e-9
        assert isinstance(f1, float)


# ============================================================================
# ONNXQAGSBackend — generation/answering control flow with mocked models
# ============================================================================


class TestONNXQAGSBackend:
    def _backend(self):
        from ml_evaluation.backends.onnx_backend import ONNXQAGSBackend

        return ONNXQAGSBackend()

    def test_init_state(self):
        b = self._backend()
        assert b._qg_model is None
        assert b._qa_model is None
        assert b._qg_tokenizer is None
        assert b._qa_tokenizer is None
        assert b._onnx_available is None

    def test_is_available_returns_bool(self):
        b = self._backend()
        b._onnx_available = None
        assert isinstance(b.is_available(), bool)

    def test_is_available_caches_true(self):
        b = self._backend()
        b._onnx_available = True
        assert b.is_available() is True

    def test_generate_questions_skips_short_sentences_and_caps_count(self):
        """Drive generate_questions with mocked tokenizer/model so no T5
        download occurs. Short sentences (<10 chars) are skipped; the loop
        stops once num_questions is reached."""
        b = self._backend()

        # Pre-seed the lazy-loaded model + tokenizer so _load_qg_model no-ops.
        b._qg_model = MagicMock()
        b._qg_model.generate.return_value = [[0, 1, 2]]  # opaque token ids
        b._qg_tokenizer = MagicMock()
        b._qg_tokenizer.encode.return_value = "encoded"
        # Every decode returns a valid-looking question (contains '?')
        b._qg_tokenizer.decode.return_value = "What is the contract about?"

        text = (
            "The contract governs the sale of goods between two parties. "
            "Hi. "  # < 10 chars after strip -> skipped
            "It specifies delivery terms and payment schedules clearly. "
            "Disputes are resolved under German law in Munich courts."
        )
        questions = b.generate_questions(text, num_questions=2)
        assert isinstance(questions, list)
        assert len(questions) == 2
        assert all("?" in q for q in questions)

    def test_generate_questions_filters_non_question_output(self):
        """Decoded output that is neither a question nor long enough is dropped."""
        b = self._backend()
        b._qg_model = MagicMock()
        b._qg_model.generate.return_value = [[0]]
        b._qg_tokenizer = MagicMock()
        b._qg_tokenizer.encode.return_value = "x"
        # Output is short and has no '?' -> filtered out -> no questions
        b._qg_tokenizer.decode.return_value = "no"

        text = "This is a sufficiently long sentence to be processed here."
        questions = b.generate_questions(text, num_questions=3)
        assert questions == []

    @requires_torch
    def test_answer_question_extracts_span_and_score(self):
        """answer_question decodes the argmax span and returns answer+score
        from softmaxed start/end logits, all with mocked ONNX model."""
        import torch

        b = self._backend()
        b._qa_model = MagicMock()

        # Logits: start peaks at index 1, end peaks at index 2.
        start_logits = torch.tensor([[0.1, 5.0, 0.2, 0.3]])
        end_logits = torch.tensor([[0.1, 0.2, 5.0, 0.3]])
        outputs = MagicMock()
        outputs.start_logits = start_logits
        outputs.end_logits = end_logits
        b._qa_model.return_value = outputs

        b._qa_tokenizer = MagicMock()
        b._qa_tokenizer.return_value = {"input_ids": torch.tensor([[10, 11, 12, 13]])}
        b._qa_tokenizer.decode.return_value = "Berlin"

        result = b.answer_question("Where?", "Berlin is the capital.")
        assert result["answer"] == "Berlin"
        assert 0.0 <= result["score"] <= 1.0
        # span tokens 1..2 inclusive were decoded
        decoded_arg = b._qa_tokenizer.decode.call_args[0][0]
        assert list(np.array(decoded_arg)) == [11, 12]


# ============================================================================
# ONNXSummaCBackend — sentence splitting + NLI aggregation
# ============================================================================


class TestONNXSummaCBackend:
    def _backend(self):
        from ml_evaluation.backends.onnx_backend import ONNXSummaCBackend

        return ONNXSummaCBackend()

    def test_init_state(self):
        b = self._backend()
        assert b._model is None
        assert b._tokenizer is None
        assert b._onnx_available is None
        assert b.VITC_MODEL == "tals/albert-xlarge-vitaminc-mnli"

    def test_is_available_returns_bool(self):
        b = self._backend()
        b._onnx_available = None
        assert isinstance(b.is_available(), bool)

    def test_is_available_caches_false(self):
        b = self._backend()
        b._onnx_available = False
        assert b.is_available() is False

    def test_split_sentences_uses_nltk(self):
        b = self._backend()
        out = b._split_sentences("First sentence. Second sentence. Third one.")
        assert isinstance(out, list)
        assert len(out) == 3

    def test_score_consistency_empty_document_returns_zero(self):
        """No document sentences -> early 0.0 (before any model call)."""
        b = self._backend()
        # Model intentionally left as a tripwire: it must NOT be called.
        b._model = MagicMock(side_effect=AssertionError("model should not run"))
        b._tokenizer = MagicMock()
        score = b.score_consistency("", "Some summary sentence here.")
        assert score == 0.0

    def test_score_consistency_empty_summary_returns_zero(self):
        b = self._backend()
        b._model = MagicMock(side_effect=AssertionError("model should not run"))
        b._tokenizer = MagicMock()
        score = b.score_consistency("A real document sentence.", "")
        assert score == 0.0

    @requires_torch
    def test_score_consistency_aggregates_max_entailment(self):
        """With a mocked ViTC model returning fixed entailment probabilities,
        score is the mean over summary sentences of the max SUPPORTS prob
        across document sentences.

        One summary sentence, two doc sentences. SUPPORTS (index 0) probs:
        doc0 -> ~high, doc1 -> ~low. The summary score is the max (high one).
        """
        import torch

        b = self._backend()
        b._tokenizer = MagicMock(return_value={"input_ids": torch.tensor([[1, 2]])})

        # Two model calls (one per doc sentence) for the single summary sentence.
        # Logits chosen so softmax index-0 (SUPPORTS) is high then low.
        high = MagicMock()
        high.logits = torch.tensor([[5.0, 0.0, 0.0]])  # softmax -> ~0.985 SUPPORTS
        low = MagicMock()
        low.logits = torch.tensor([[0.0, 5.0, 0.0]])  # softmax -> ~0.007 SUPPORTS
        b._model = MagicMock(side_effect=[high, low])

        # Force a deterministic 2-doc / 1-summary split. score_consistency
        # splits the document first, then the summary, so the side_effect
        # list is ordered [doc_sentences, summary_sentences].
        with patch.object(
            b, "_split_sentences", side_effect=[["d1.", "d2."], ["s1."]]
        ):
            score = b.score_consistency("d1. d2.", "s1.")

        assert b._model.call_count == 2  # one per doc sentence
        # max of (~0.985, ~0.007) ~= 0.985, mean over 1 summary sentence
        assert 0.9 < score <= 1.0
