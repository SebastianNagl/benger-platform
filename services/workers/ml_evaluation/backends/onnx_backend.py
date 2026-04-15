"""
ONNX Runtime backend for ARM64-compatible metric computation.

Uses sentence-transformers ONNX support and HuggingFace Optimum.

References:
- ONNX Runtime: https://onnxruntime.ai/
- Sentence Transformers ONNX: https://sbert.net/docs/sentence_transformer/usage/efficiency.html
- Optimum: https://huggingface.co/docs/optimum/index
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .base import BERTScoreBackend, EmbeddingBackend, QAGSBackend, SummaCBackend

logger = logging.getLogger(__name__)


class ONNXEmbeddingBackend(EmbeddingBackend):
    """
    ONNX-based embedding backend using sentence-transformers ONNX support.
    Works natively on ARM64.
    """

    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        self.model_name = model_name
        self._model = None
        self._onnx_available: Optional[bool] = None

    def is_available(self) -> bool:
        if self._onnx_available is None:
            try:
                import onnxruntime  # noqa: F401
                from sentence_transformers import SentenceTransformer  # noqa: F401

                self._onnx_available = True
            except ImportError:
                self._onnx_available = False
        return self._onnx_available

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            # Use ONNX backend - native ARM64 support
            self._model = SentenceTransformer(self.model_name, backend="onnx")
            logger.info(f"Loaded ONNX embedding model: {self.model_name}")
        return self._model

    def encode(self, texts: List[str]) -> np.ndarray:
        """Encode texts to embeddings using ONNX model."""
        model = self._get_model()
        return model.encode(texts, convert_to_numpy=True)


class ONNXBERTScoreBackend(BERTScoreBackend):
    """
    ONNX-based BERTScore computation.
    Uses sentence-transformers with ONNX backend for embeddings.

    Reference: Zhang et al. (2020) "BERTScore: Evaluating Text Generation with BERT"
    """

    def __init__(self, model_name: str = "bert-base-multilingual-cased"):
        self.model_name = model_name
        self._embedding_backend: Optional[ONNXEmbeddingBackend] = None

    def is_available(self) -> bool:
        try:
            import onnxruntime  # noqa: F401
            from sentence_transformers import SentenceTransformer  # noqa: F401

            return True
        except ImportError:
            return False

    def _get_embedding_backend(self) -> ONNXEmbeddingBackend:
        if self._embedding_backend is None:
            # Use multilingual model for German support
            self._embedding_backend = ONNXEmbeddingBackend("paraphrase-multilingual-MiniLM-L12-v2")
        return self._embedding_backend

    def compute(
        self, candidates: List[str], references: List[str], lang: str = "en"
    ) -> Tuple[float, float, float]:
        """
        Compute BERTScore using ONNX model.

        Args:
            candidates: List of candidate texts
            references: List of reference texts
            lang: Language code (used for model selection)

        Returns:
            Tuple of (precision, recall, f1)
        """
        backend = self._get_embedding_backend()

        # Get embeddings
        cand_embs = backend.encode(candidates)
        ref_embs = backend.encode(references)

        # Compute BERTScore from embeddings
        precision, recall, f1 = self._compute_bertscore(cand_embs, ref_embs)

        return precision, recall, f1

    def _compute_bertscore(
        self, cand_embs: np.ndarray, ref_embs: np.ndarray
    ) -> Tuple[float, float, float]:
        """Compute precision, recall, F1 from embeddings."""
        # Normalize embeddings
        cand_norm = cand_embs / np.linalg.norm(cand_embs, axis=-1, keepdims=True)
        ref_norm = ref_embs / np.linalg.norm(ref_embs, axis=-1, keepdims=True)

        # Compute cosine similarity
        similarity = np.dot(cand_norm, ref_norm.T)

        # BERTScore: max over alignment
        precision = float(similarity.max(axis=1).mean())
        recall = float(similarity.max(axis=0).mean())

        if precision + recall > 0:
            f1 = 2 * precision * recall / (precision + recall)
        else:
            f1 = 0.0

        return precision, recall, f1


class ONNXQAGSBackend(QAGSBackend):
    """
    ONNX-optimized QAGS backend for ARM64.

    Uses HuggingFace Optimum to load T5 and DistilBERT models with ONNX Runtime.

    Reference: Wang et al. (2020) "Asking and Answering Questions to
    Evaluate the Factual Consistency of Summaries"
    """

    def __init__(self):
        self._qg_model = None  # T5 for question generation
        self._qa_model = None  # DistilBERT for QA
        self._qg_tokenizer = None
        self._qa_tokenizer = None
        self._onnx_available: Optional[bool] = None

    def is_available(self) -> bool:
        if self._onnx_available is None:
            try:
                import onnxruntime  # noqa: F401
                from optimum.onnxruntime import ORTModelForQuestionAnswering  # noqa: F401
                from optimum.onnxruntime import ORTModelForSeq2SeqLM  # noqa: F401

                self._onnx_available = True
            except ImportError:
                self._onnx_available = False
        return self._onnx_available

    def _load_qg_model(self):
        """Lazy load T5 model for question generation."""
        if self._qg_model is None:
            from optimum.onnxruntime import ORTModelForSeq2SeqLM
            from transformers import T5Tokenizer

            logger.info("Loading ONNX T5 model for question generation...")
            self._qg_tokenizer = T5Tokenizer.from_pretrained('t5-small')
            self._qg_model = ORTModelForSeq2SeqLM.from_pretrained(
                't5-small', export=True  # Auto-export to ONNX if not cached
            )
            logger.info("ONNX T5 model loaded")

    def _load_qa_model(self):
        """Lazy load DistilBERT model for question answering."""
        if self._qa_model is None:
            from optimum.onnxruntime import ORTModelForQuestionAnswering
            from transformers import AutoTokenizer

            model_name = 'distilbert-base-cased-distilled-squad'
            logger.info(f"Loading ONNX QA model: {model_name}...")
            self._qa_tokenizer = AutoTokenizer.from_pretrained(model_name)
            self._qa_model = ORTModelForQuestionAnswering.from_pretrained(model_name, export=True)
            logger.info("ONNX QA model loaded")

    def generate_questions(self, text: str, num_questions: int = 5) -> List[str]:
        """Generate questions from text using ONNX T5."""
        self._load_qg_model()

        # Split text into sentences for question generation
        import nltk

        try:
            sentences = nltk.sent_tokenize(text)
        except LookupError:
            nltk.download('punkt', quiet=True)
            nltk.download('punkt_tab', quiet=True)
            sentences = nltk.sent_tokenize(text)

        questions = []
        for sentence in sentences[: num_questions * 2]:  # Process more sentences
            if len(sentence.strip()) < 10:
                continue

            # T5 question generation prompt
            prompt = f"generate question: {sentence}"

            inputs = self._qg_tokenizer.encode(
                prompt, return_tensors="pt", max_length=512, truncation=True
            )

            outputs = self._qg_model.generate(
                inputs, max_length=64, num_beams=4, early_stopping=True, no_repeat_ngram_size=2
            )

            question = self._qg_tokenizer.decode(outputs[0], skip_special_tokens=True)

            # Validate question
            if question and ('?' in question or len(question) > 5):
                questions.append(question)

            if len(questions) >= num_questions:
                break

        return questions

    def answer_question(self, question: str, context: str) -> Dict[str, Any]:
        """Answer question using ONNX DistilBERT."""
        self._load_qa_model()

        inputs = self._qa_tokenizer(
            question, context, return_tensors="pt", max_length=512, truncation=True
        )

        outputs = self._qa_model(**inputs)

        # Get answer span
        start_idx = outputs.start_logits.argmax()
        end_idx = outputs.end_logits.argmax()

        # Decode answer
        input_ids = inputs["input_ids"][0]
        answer_tokens = input_ids[start_idx : end_idx + 1]
        answer = self._qa_tokenizer.decode(answer_tokens, skip_special_tokens=True)

        # Get confidence score
        import torch

        start_probs = torch.softmax(outputs.start_logits, dim=-1)
        end_probs = torch.softmax(outputs.end_logits, dim=-1)
        score = float(start_probs[0, start_idx] * end_probs[0, end_idx])

        return {"answer": answer, "score": score}


class ONNXSummaCBackend(SummaCBackend):
    """
    ONNX ViTC-based SummaC reimplementation for ARM64.

    Uses the ViTC (Vitamin C) NLI model directly via HuggingFace Optimum,
    avoiding the summac package dependency conflict.

    Reference: Laban et al. (2022) "SummaC: Re-Visiting NLI-based Models
    for Inconsistency Detection in Summarization"

    Model: Schuster et al. (2021) "Get Your Vitamin C! Robust Fact
    Verification with Contrastive Evidence"
    """

    VITC_MODEL = 'tals/albert-xlarge-vitaminc-mnli'

    def __init__(self):
        self._model = None
        self._tokenizer = None
        self._onnx_available: Optional[bool] = None

    def is_available(self) -> bool:
        if self._onnx_available is None:
            try:
                import onnxruntime  # noqa: F401
                from optimum.onnxruntime import ORTModelForSequenceClassification  # noqa: F401

                self._onnx_available = True
            except ImportError:
                self._onnx_available = False
        return self._onnx_available

    def _load_model(self):
        """Lazy load ViTC NLI model."""
        if self._model is None:
            from optimum.onnxruntime import ORTModelForSequenceClassification
            from transformers import AutoTokenizer

            logger.info(f"Loading ONNX ViTC model: {self.VITC_MODEL}...")
            self._tokenizer = AutoTokenizer.from_pretrained(self.VITC_MODEL)
            self._model = ORTModelForSequenceClassification.from_pretrained(
                self.VITC_MODEL, export=True  # Auto-export to ONNX
            )
            logger.info("ONNX ViTC model loaded")

    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences using NLTK."""
        import nltk

        try:
            return nltk.sent_tokenize(text)
        except LookupError:
            nltk.download('punkt', quiet=True)
            nltk.download('punkt_tab', quiet=True)
            return nltk.sent_tokenize(text)

    def score_consistency(self, document: str, summary: str) -> float:
        """
        Reimplementation of SummaCConv algorithm.

        For each summary sentence, find the max entailment score across
        all document sentences, then average across summary sentences.
        """
        self._load_model()
        import torch

        doc_sentences = self._split_sentences(document)
        sum_sentences = self._split_sentences(summary)

        if not doc_sentences or not sum_sentences:
            return 0.0

        # Build NLI pair matrix
        scores = []
        for sum_sent in sum_sentences:
            sent_scores = []
            for doc_sent in doc_sentences:
                inputs = self._tokenizer(
                    doc_sent, sum_sent, return_tensors="pt", truncation=True, max_length=512
                )
                outputs = self._model(**inputs)

                # ViTC output: [SUPPORTS, REFUTES, NOT ENOUGH INFO]
                # SUPPORTS (index 0) = entailment
                probs = torch.softmax(outputs.logits, dim=-1)
                entailment_prob = probs[0][0].item()  # SUPPORTS score
                sent_scores.append(entailment_prob)

            # Take max score for this summary sentence (best evidence)
            scores.append(max(sent_scores) if sent_scores else 0.0)

        # Aggregate: mean of all summary sentence scores
        return sum(scores) / len(scores) if scores else 0.0
