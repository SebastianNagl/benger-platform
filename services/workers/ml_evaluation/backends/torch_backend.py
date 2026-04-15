"""
PyTorch backend for ML metric computation.

Used on x86_64 for optimal performance with existing libraries.

References:
- BERTScore: Zhang et al. (2020) "BERTScore: Evaluating Text Generation with BERT"
- Sentence Transformers: Reimers & Gurevych (2019) "Sentence-BERT"
- QAGS: Wang et al. (2020) "Asking and Answering Questions to Evaluate Factual Consistency"
- SummaC: Laban et al. (2022) "SummaC: Re-Visiting NLI-based Models"
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .base import BERTScoreBackend, EmbeddingBackend, QAGSBackend, SummaCBackend

logger = logging.getLogger(__name__)


class TorchEmbeddingBackend(EmbeddingBackend):
    """
    PyTorch-based embedding backend using sentence-transformers.
    Optimal performance on x86_64.
    """

    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        self.model_name = model_name
        self._model = None
        self._torch_available: Optional[bool] = None

    def is_available(self) -> bool:
        if self._torch_available is None:
            try:
                import torch  # noqa: F401
                from sentence_transformers import SentenceTransformer  # noqa: F401

                self._torch_available = True
            except ImportError:
                self._torch_available = False
        return self._torch_available

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
            logger.info(f"Loaded PyTorch embedding model: {self.model_name}")
        return self._model

    def encode(self, texts: List[str]) -> np.ndarray:
        """Encode texts to embeddings using PyTorch model."""
        model = self._get_model()
        return model.encode(texts, convert_to_numpy=True)


class TorchBERTScoreBackend(BERTScoreBackend):
    """
    PyTorch-based BERTScore computation using bert-score library.
    Optimal performance on x86_64.

    Reference: Zhang et al. (2020) "BERTScore: Evaluating Text Generation with BERT"
    """

    def __init__(self):
        self._bert_score_available: Optional[bool] = None

    def is_available(self) -> bool:
        if self._bert_score_available is None:
            try:
                from bert_score import score  # noqa: F401

                self._bert_score_available = True
            except ImportError:
                self._bert_score_available = False
        return self._bert_score_available

    def compute(
        self, candidates: List[str], references: List[str], lang: str = "en"
    ) -> Tuple[float, float, float]:
        """
        Compute BERTScore using bert-score library.

        Args:
            candidates: List of candidate texts
            references: List of reference texts
            lang: Language code for model selection

        Returns:
            Tuple of (precision, recall, f1)
        """
        from bert_score import score as bert_score_compute

        P, R, F1 = bert_score_compute(candidates, references, lang=lang, verbose=False)

        return (float(P.mean().item()), float(R.mean().item()), float(F1.mean().item()))


class TorchQAGSBackend(QAGSBackend):
    """
    PyTorch QAGS backend for x86_64.

    Uses standard transformers models for optimal performance.

    Reference: Wang et al. (2020) "Asking and Answering Questions to
    Evaluate the Factual Consistency of Summaries"
    """

    def __init__(self):
        self._qg_model = None
        self._qg_tokenizer = None
        self._qa_pipeline = None
        self._torch_available: Optional[bool] = None

    def is_available(self) -> bool:
        if self._torch_available is None:
            try:
                import torch  # noqa: F401
                from transformers import T5ForConditionalGeneration  # noqa: F401
                from transformers import pipeline  # noqa: F401

                self._torch_available = True
            except ImportError:
                self._torch_available = False
        return self._torch_available

    def _load_qg_model(self):
        """Lazy load T5 model for question generation."""
        if self._qg_model is None:
            from transformers import T5ForConditionalGeneration, T5Tokenizer

            logger.info("Loading PyTorch T5 model for question generation...")
            self._qg_tokenizer = T5Tokenizer.from_pretrained('t5-small')
            self._qg_model = T5ForConditionalGeneration.from_pretrained('t5-small')
            logger.info("PyTorch T5 model loaded")

    def _load_qa_pipeline(self):
        """Lazy load DistilBERT pipeline for question answering."""
        if self._qa_pipeline is None:
            from transformers import pipeline

            logger.info("Loading PyTorch QA pipeline...")
            self._qa_pipeline = pipeline(
                'question-answering',
                model='distilbert-base-cased-distilled-squad',
                tokenizer='distilbert-base-cased-distilled-squad',
            )
            logger.info("PyTorch QA pipeline loaded")

    def generate_questions(self, text: str, num_questions: int = 5) -> List[str]:
        """Generate questions from text using PyTorch T5."""
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
        for sentence in sentences[: num_questions * 2]:
            if len(sentence.strip()) < 10:
                continue

            prompt = f"generate question: {sentence}"

            inputs = self._qg_tokenizer.encode(
                prompt, return_tensors="pt", max_length=512, truncation=True
            )

            outputs = self._qg_model.generate(
                inputs, max_length=64, num_beams=4, early_stopping=True, no_repeat_ngram_size=2
            )

            question = self._qg_tokenizer.decode(outputs[0], skip_special_tokens=True)

            if question and ('?' in question or len(question) > 5):
                questions.append(question)

            if len(questions) >= num_questions:
                break

        return questions

    def answer_question(self, question: str, context: str) -> Dict[str, Any]:
        """Answer question using PyTorch DistilBERT pipeline."""
        self._load_qa_pipeline()

        result = self._qa_pipeline(question=question, context=context)
        return {"answer": result["answer"], "score": result["score"]}


class TorchSummaCBackend(SummaCBackend):
    """
    PyTorch ViTC-based SummaC reimplementation for x86_64.

    Uses the ViTC (Vitamin C) NLI model directly, avoiding the summac
    package dependency conflict.

    Reference: Laban et al. (2022) "SummaC: Re-Visiting NLI-based Models
    for Inconsistency Detection in Summarization"

    Model: Schuster et al. (2021) "Get Your Vitamin C! Robust Fact
    Verification with Contrastive Evidence"
    """

    VITC_MODEL = 'tals/albert-xlarge-vitaminc-mnli'

    def __init__(self):
        self._model = None
        self._tokenizer = None
        self._torch_available: Optional[bool] = None

    def is_available(self) -> bool:
        if self._torch_available is None:
            try:
                import torch  # noqa: F401
                from transformers import AutoModelForSequenceClassification  # noqa: F401

                self._torch_available = True
            except ImportError:
                self._torch_available = False
        return self._torch_available

    def _load_model(self):
        """Lazy load ViTC NLI model."""
        if self._model is None:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            logger.info(f"Loading PyTorch ViTC model: {self.VITC_MODEL}...")
            self._tokenizer = AutoTokenizer.from_pretrained(self.VITC_MODEL)
            self._model = AutoModelForSequenceClassification.from_pretrained(self.VITC_MODEL)
            logger.info("PyTorch ViTC model loaded")

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
                with torch.no_grad():
                    outputs = self._model(**inputs)

                # ViTC output: [SUPPORTS, REFUTES, NOT ENOUGH INFO]
                # SUPPORTS (index 0) = entailment
                probs = torch.softmax(outputs.logits, dim=-1)
                entailment_prob = probs[0][0].item()
                sent_scores.append(entailment_prob)

            scores.append(max(sent_scores) if sent_scores else 0.0)

        return sum(scores) / len(scores) if scores else 0.0
