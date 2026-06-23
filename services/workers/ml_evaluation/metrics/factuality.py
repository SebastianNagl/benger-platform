"""Factuality & coherence metric-family computations.

Covers factcc / qags / coherence and the coherence sub-helpers
(language detection, entity extraction, entity- and semantic-coherence).
Extracted from ``SampleEvaluator``.

``torch``, ``sent_tokenize``, ``word_tokenize`` and ``pos_tag`` are
deterministic library objects (not monkeypatched), so they're imported
directly. The lazy-loaders (``_get_backend_selector`` / ``_get_factcc_model``
/ ``_get_sentence_transformer``), ``st_util`` and the module ``logger`` are
imported lazily from ``..sample_evaluator`` inside the function bodies so
that test patches on ``ml_evaluation.sample_evaluator`` take effect and so
log records keep the original logger name.

``_get_de_spacy`` (a @classmethod) deliberately stays on ``SampleEvaluator``;
``extract_entities_german`` reaches it via ``ev._get_de_spacy``.
"""

from typing import Any, Dict, List, Optional

from nltk.tag import pos_tag
from nltk.tokenize import sent_tokenize, word_tokenize

# NOTE: `torch` is imported LAZILY inside compute_factuality_metric (not at
# module top) so importing this module — and transitively `import tasks` —
# stays cheap. See ml_evaluation/sample_evaluator.py for the full rationale.


def compute_factuality_metric(
    ev, metric_name: str, gt: Any, pred: Any, parameters: Optional[Dict[str, Any]] = None
) -> float:
    """
    Compute factuality and coherence metrics.
    NO FALLBACKS - These metrics require proper model implementations.

    Args:
        metric_name: One of 'factcc', 'qags', 'coherence'
        gt: Ground truth/source text
        pred: Predicted/generated text
        parameters: Optional metric-specific parameters
            - method: For FactCC, one of 'summac' or 'factcc' (default: 'summac')

    Returns:
        Score (0.0-1.0)

    Raises:
        NotImplementedError: If metric implementation is not yet available
    """
    from ..sample_evaluator import _get_backend_selector, _get_factcc_model, logger

    if parameters is None:
        parameters = {}

    if metric_name == "factcc":
        # FactCC - Real factual consistency checking
        # Supports both SummaC (2022) and original FactCC (2020)
        # User selects method via parameters: 'summac' (default) or 'factcc'
        gt_str = str(gt)
        pred_str = str(pred)
        method = parameters.get("method", "summac")

        if method == "summac":
            # SummaC: NLI-based consistency scoring using ViTC model
            # Uses backend selector for platform compatibility (ONNX on ARM64, PyTorch on x86_64)
            # Reference: Laban et al. (2022) "SummaC: Re-Visiting NLI-based Models"
            try:
                selector = _get_backend_selector()
                backend = selector.get_summac_backend()
                score = backend.score_consistency(gt_str, pred_str)
                return float(score)
            except Exception as e:
                logger.error(f"SummaC scoring failed: {e}")
                raise RuntimeError(f"SummaC scoring failed: {e}")

        elif method == "factcc":
            # Original FactCC: BERT-based binary classification
            model, tokenizer = _get_factcc_model()
            if model is None or tokenizer is None:
                raise RuntimeError(
                    "FactCC model could not be loaded. "
                    "Ensure transformers package is installed with BERT models."
                )

            try:
                # FactCC expects claim-context pairs in specific format
                # Format: [CLS] claim [SEP] context [SEP]
                inputs = tokenizer(
                    pred_str,
                    gt_str,
                    max_length=512,
                    truncation='only_second',
                    padding='max_length',
                    return_tensors='pt',
                )

                # Move to same device as model (torch imported lazily here to
                # keep module import — and `import tasks` — light).
                import torch

                if torch.cuda.is_available():
                    inputs = {k: v.cuda() for k, v in inputs.items()}

                # Get prediction
                with torch.no_grad():
                    outputs = model(**inputs)
                    logits = outputs.logits
                    # Apply softmax to get probabilities
                    probs = torch.nn.functional.softmax(logits, dim=-1)
                    # FactCC: class 0 = incorrect, class 1 = correct
                    score = probs[0][1].item()

                return float(score)
            except Exception as e:
                logger.error(f"FactCC scoring failed: {e}")
                raise RuntimeError(f"FactCC scoring failed: {e}")
        else:
            raise ValueError(
                f"Unknown FactCC method: {method}. " "Must be 'summac' or 'factcc'"
            )

    elif metric_name == "qags":
        # QAGS - Question Generation + Question Answering pipeline
        # Uses backend selector for platform compatibility (ONNX on ARM64, PyTorch on x86_64)
        # Reference: Wang et al. (2020) "Asking and Answering Questions to Evaluate
        # the Factual Consistency of Summaries"
        gt_str = str(gt)
        pred_str = str(pred)

        # Parameters
        num_questions = parameters.get("num_questions", 5)  # Number of questions to generate
        min_answer_overlap = parameters.get(
            "min_answer_overlap", 0.5
        )  # Threshold for answer match

        try:
            # Get QAGS backend (ONNX on ARM64, PyTorch on x86_64)
            selector = _get_backend_selector()
            qags_backend = selector.get_qags_backend()

            # Step 1: Question Generation from ground truth
            questions = qags_backend.generate_questions(gt_str, num_questions=num_questions)

            if not questions:
                logger.warning("QAGS: No questions generated from ground truth")
                return 0.0

            # Step 2: Answer questions using both ground truth and prediction
            matching_answers = 0
            total_questions = 0

            for question in questions:
                try:
                    # Answer using ground truth
                    gt_answer = qags_backend.answer_question(question, gt_str)
                    # Answer using prediction
                    pred_answer = qags_backend.answer_question(question, pred_str)

                    # Compare answers
                    if ev._answers_match_qags(
                        gt_answer['answer'], pred_answer['answer'], threshold=min_answer_overlap
                    ):
                        matching_answers += 1

                    total_questions += 1

                except Exception as e:
                    logger.debug(f"QAGS: Failed to answer question '{question}': {e}")
                    # Count as non-matching
                    total_questions += 1
                    continue

            # Step 3: Calculate QAGS score
            if total_questions == 0:
                logger.warning("QAGS: No valid question-answer pairs generated")
                return 0.0

            qags_score = matching_answers / total_questions
            return qags_score

        except Exception as e:
            logger.error(f"QAGS computation failed: {e}")
            raise RuntimeError(f"QAGS computation failed: {e}")

    elif metric_name == "coherence":
        """
        Coherence - Entity-based coherence using Entity Grid Method + Semantic Coherence

        Implementation based on:
        - Barzilay & Lapata (2008): "Modeling Local Coherence: An Entity-based Approach"
        - Combines entity grid transitions with sentence embedding similarity

        Method:
        1. Entity Grid: Extract entities (nouns) and track their grammatical roles across sentences
        2. Transition Analysis: Measure smoothness of entity transitions between sentences
        3. Semantic Coherence: Measure cosine similarity of adjacent sentence embeddings
        4. Combined Score: Weighted average of entity-based and semantic coherence

        Returns score between 0.0-1.0 where higher = more coherent
        """
        pred_str = str(pred)

        # Parameters
        method = parameters.get("method", "hybrid")  # 'entity', 'semantic', or 'hybrid'
        entity_weight = parameters.get(
            "entity_weight", 0.6
        )  # Weight for entity-based coherence
        semantic_weight = parameters.get(
            "semantic_weight", 0.4
        )  # Weight for semantic coherence

        try:
            # Validate text is suitable for coherence analysis
            ev._validate_text_for_coherence(pred_str)

            # Split into sentences
            sentences = sent_tokenize(pred_str)

            coherence_scores = []

            # Method 1: Entity-based coherence (Entity Grid Method)
            #
            # In hybrid mode we don't want a missing-entity failure (e.g.
            # German legal text dominated by single-letter party
            # abbreviations like "K", "V" that fall under the entity
            # length threshold) to abort the whole metric — fall through
            # to semantic-only scoring instead. Pure 'entity' mode still
            # raises so the caller sees a clear error.
            if method in ["entity", "hybrid"]:
                try:
                    entity_score = ev._compute_entity_coherence(sentences)
                    coherence_scores.append((entity_score, entity_weight))
                except Exception as entity_err:
                    if method == "entity":
                        raise
                    logger.info(
                        f"Coherence: entity grid unavailable ({entity_err}); "
                        "falling back to semantic-only score"
                    )

            # Method 2: Semantic coherence (sentence embedding transitions)
            if method in ["semantic", "hybrid"]:
                semantic_score = ev._compute_semantic_coherence(sentences)
                coherence_scores.append((semantic_score, semantic_weight))

            # Combine scores with weights
            if not coherence_scores:
                raise ValueError(f"Invalid coherence method: {method}")

            # Normalize weights
            total_weight = sum(w for _, w in coherence_scores)
            if total_weight == 0:
                return 0.0

            weighted_score = sum(
                score * (weight / total_weight) for score, weight in coherence_scores
            )

            return max(0.0, min(1.0, weighted_score))  # Clamp to [0, 1]

        except Exception as e:
            logger.error(f"Coherence computation failed: {e}")
            raise RuntimeError(f"Coherence computation failed: {e}")

    raise ValueError(f"Unknown factuality metric: {metric_name}")


def answers_match_qags(ev, answer1: str, answer2: str, threshold: float = 0.5) -> bool:
    """
    Check if two answers match for QAGS scoring.

    Uses token overlap (F1-based) to determine if answers are similar enough.

    Args:
        answer1: First answer
        answer2: Second answer
        threshold: Minimum F1 score for match (default: 0.5)

    Returns:
        True if answers match, False otherwise
    """
    # Normalize answers
    ans1 = answer1.lower().strip()
    ans2 = answer2.lower().strip()

    # Exact match
    if ans1 == ans2:
        return True

    # Empty answers
    if not ans1 or not ans2:
        return False

    # Token-level F1 score
    tokens1 = set(ans1.split())
    tokens2 = set(ans2.split())

    if not tokens1 or not tokens2:
        return False

    intersection = len(tokens1 & tokens2)

    if intersection == 0:
        return False

    precision = intersection / len(tokens2)
    recall = intersection / len(tokens1)

    f1 = 2 * (precision * recall) / (precision + recall)

    return f1 >= threshold


def validate_text_for_coherence(ev, text: str) -> None:
    """Validate text is suitable for coherence analysis.

    Raises:
        ValueError: If text is empty, too short, or has fewer than 2 sentences.
    """
    if not text or not text.strip():
        raise ValueError("Coherence requires non-empty text")
    if len(text.strip()) < 20:
        raise ValueError("Coherence requires text of at least 20 characters")

    sentences = sent_tokenize(text)
    if len(sentences) < 2:
        raise ValueError(f"Coherence requires at least 2 sentences, found {len(sentences)}")


def detect_language_heuristic(ev, sentences: List[str]) -> str:
    """
    Detect whether text is German or English using simple heuristics.

    German detection signals:
    - Sentences starting with common German articles/pronouns
    - Presence of German-specific characters (umlauts, eszett)
    - High ratio of capitalized non-sentence-initial words (German noun capitalization)

    Args:
        sentences: List of sentences to analyze

    Returns:
        'de' for German, 'en' for English (default fallback)
    """
    german_articles = {
        'der', 'die', 'das', 'ein', 'eine', 'dem', 'den', 'des',
        'einem', 'einer', 'eines', 'im', 'am', 'zum', 'zur',
    }
    german_char_pattern = any(
        ch in text for text in sentences for ch in 'äöüÄÖÜß'
    )

    german_start_count = 0
    for sentence in sentences:
        words = sentence.strip().split()
        if words and words[0].lower() in german_articles:
            german_start_count += 1

    german_start_ratio = german_start_count / max(len(sentences), 1)

    capitalized_non_initial = 0
    total_non_initial = 0
    for sentence in sentences:
        words = sentence.strip().split()
        for word in words[1:]:
            cleaned = word.strip('.,;:!?()[]"\'')
            if cleaned.isalpha() and len(cleaned) >= 2:
                total_non_initial += 1
                if cleaned[0].isupper():
                    capitalized_non_initial += 1

    cap_ratio = capitalized_non_initial / max(total_non_initial, 1)

    if german_char_pattern or german_start_ratio > 0.3 or cap_ratio > 0.15:
        return 'de'

    return 'en'


def extract_entities_german(ev, sentences: List[str]) -> Dict[str, List[str]]:
    """
    Extract entities from German text via spaCy ``de_core_news_md``.

    Uses real Named Entity Recognition (PER, LOC, ORG, MISC) — replaces
    the previous capitalization heuristic which a) missed single-letter
    party abbreviations like "K", "V" common in German legal exam
    text, and b) couldn't distinguish proper nouns from common nouns
    at the start of sentences.

    The chosen model :code:`de_core_news_md` is the medium-size German
    news pipeline (~50 MB). It's pinned via a versioned wheel in
    :code:`requirements.txt` so worker images are reproducible. If
    loading fails (model not installed, e.g. during a partial
    development install), this method falls back to the legacy
    capitalization heuristic and records that on the evaluator
    instance via :code:`_last_coherence_ner_model` — the coherence
    provenance helper surfaces this in :code:`details.ner_model` so
    researchers always know which extractor produced their score.

    Args:
        sentences: List of sentences to analyze

    Returns:
        Entity grid: dict mapping entity (lowercase) -> list of roles per sentence
    """
    from ..sample_evaluator import logger

    nlp = ev._get_de_spacy()
    if nlp is not None:
        ev._last_coherence_ner_model = "de_core_news_md"
        entity_grid: Dict[str, List[str]] = {}
        for sent_idx, sentence in enumerate(sentences):
            doc = nlp(sentence)
            for ent in doc.ents:
                key = ent.text.strip().lower()
                if not key:
                    continue
                entity_grid.setdefault(key, ["-"] * len(sentences))
                entity_grid[key][sent_idx] = "X"
        return entity_grid

    # Fallback: legacy capitalization heuristic (kept as defense in
    # depth — production worker images should always have the spaCy
    # model installed; if they don't, log loud and degrade).
    logger.warning(
        "German spaCy model unavailable; falling back to capitalization "
        "heuristic for coherence entity extraction. Install "
        "`de_core_news_md` for real NER."
    )
    ev._last_coherence_ner_model = "capitalization_heuristic"

    german_pronouns = {
        'er', 'sie', 'es', 'ihm', 'ihr', 'ihnen', 'ihn',
        'wir', 'uns', 'dieser', 'diese', 'dieses', 'diesen',
        'diesem', 'jener', 'jene', 'jenes', 'welcher', 'welche',
        'welches', 'man', 'sich',
    }

    entity_grid = {}

    for sent_idx, sentence in enumerate(sentences):
        tokens = word_tokenize(sentence)

        for token_idx, token in enumerate(tokens):
            cleaned = token.strip('.,;:!?()[]"\'-')
            if not cleaned or len(cleaned) < 2:
                continue

            is_entity = False

            if cleaned.lower() in german_pronouns:
                is_entity = True
            elif token_idx > 0 and cleaned[0].isupper() and cleaned.isalpha():
                is_entity = True

            if is_entity:
                entity = cleaned.lower()
                if entity not in entity_grid:
                    entity_grid[entity] = ['-'] * len(sentences)
                entity_grid[entity][sent_idx] = 'X'

    return entity_grid


def extract_entities_english(ev, sentences: List[str]) -> Dict[str, List[str]]:
    """
    Extract entities from English text using NLTK POS tagging.

    Uses the Penn Treebank POS tagger to identify nouns (NN, NNS, NNP, NNPS)
    and pronouns (PRP, PRP$) as entities for the Entity Grid Method.

    Args:
        sentences: List of sentences to analyze

    Returns:
        Entity grid: dict mapping entity (lowercase) -> list of roles per sentence
    """
    entity_grid = {}

    for sent_idx, sentence in enumerate(sentences):
        tokens = word_tokenize(sentence)
        pos_tags = pos_tag(tokens)

        for word, pos in pos_tags:
            if pos.startswith('NN') or pos.startswith('PRP'):
                entity = word.lower()
                if entity not in entity_grid:
                    entity_grid[entity] = ['-'] * len(sentences)
                entity_grid[entity][sent_idx] = 'X'

    return entity_grid


def compute_entity_coherence(ev, sentences: List[str]) -> float:
    """
    Compute entity-based coherence using Entity Grid Method.

    Based on Barzilay & Lapata (2008): "Modeling Local Coherence: An Entity-based Approach"

    Language-aware entity extraction:
    - German: Uses spaCy ``de_core_news_md`` NER, with a capitalization
      heuristic only as the fallback when the spaCy model is unavailable.
    - English: Uses NLTK POS tagger (NN, NNS, NNP, NNPS, PRP, PRP$)

    Args:
        sentences: List of sentences to analyze

    Returns:
        Coherence score between 0.0-1.0 (higher = more coherent)
    """
    from ..sample_evaluator import logger

    try:
        lang = ev._detect_language_heuristic(sentences)

        if lang == 'de':
            entity_grid = ev._extract_entities_german(sentences)
        else:
            entity_grid = ev._extract_entities_english(sentences)

        if not entity_grid:
            raise RuntimeError(
                f"No entities found in text (detected language: {lang}). "
                "Text may lack proper nouns/pronouns or entity detection "
                "failed for this language."
            )

        smooth_transitions = 0
        total_transitions = 0

        for entity, roles in entity_grid.items():
            for i in range(len(roles) - 1):
                if roles[i] != '-' and roles[i + 1] != '-':
                    smooth_transitions += 2.0
                elif roles[i] != '-' or roles[i + 1] != '-':
                    smooth_transitions += 0.5

                total_transitions += 1

        if total_transitions == 0:
            raise RuntimeError("No entity transitions found across sentences")

        coherence_score = smooth_transitions / (
            total_transitions * 2.0
        )
        return max(0.0, min(1.0, coherence_score))

    except Exception as e:
        logger.error(f"Entity coherence computation failed: {e}")
        raise RuntimeError(f"Entity coherence computation failed: {e}") from e


def compute_semantic_coherence(ev, sentences: List[str]) -> float:
    """
    Compute semantic coherence using sentence embeddings.

    Measures coherence as the average cosine similarity between adjacent sentences.
    Coherent texts have semantically related adjacent sentences.

    Algorithm:
    1. Encode each sentence using sentence transformer model
    2. Compute cosine similarity between adjacent sentence pairs
    3. Average similarities to get overall coherence score

    Args:
        sentences: List of sentences to analyze

    Returns:
        Coherence score between 0.0-1.0 (higher = more coherent)
    """
    from ..sample_evaluator import _get_sentence_transformer, st_util

    try:
        # Load sentence transformer model
        model = _get_sentence_transformer()
        if model is None:
            raise RuntimeError(
                "Sentence transformer model could not be loaded. "
                "Ensure sentence-transformers package is installed."
            )

        # Encode all sentences
        embeddings = model.encode(sentences, convert_to_tensor=True)

        # Compute cosine similarities between adjacent sentences
        similarities = []
        for i in range(len(embeddings) - 1):
            # Cosine similarity between adjacent sentences
            sim = st_util.cos_sim(embeddings[i], embeddings[i + 1]).item()
            similarities.append(sim)

        if not similarities:
            return 1.0  # Single sentence is perfectly coherent

        # Average similarity is the coherence score
        avg_similarity = sum(similarities) / len(similarities)

        # Normalize to [0, 1] range (cosine similarity is already in [-1, 1])
        # Map [-1, 1] to [0, 1] where 1 = high similarity (coherent)
        coherence_score = (avg_similarity + 1.0) / 2.0

        return max(0.0, min(1.0, coherence_score))

    except Exception as e:
        raise RuntimeError(f"Semantic coherence computation failed: {e}")
