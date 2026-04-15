# Evaluation Metrics Reference

Complete reference for all 44 evaluation metrics implemented in BenGER.

## Quick Reference

| Category | Metrics | Use Case |
|----------|---------|----------|
| Classification | exact_match, accuracy, precision, recall, f1, cohen_kappa, confusion_matrix | Binary/multi-class answers |
| Multi-label | jaccard, hamming_loss, subset_accuracy, token_f1 | Multiple selections, checkbox answers |
| Numeric | mae, rmse, mape, r2, correlation | Rating scales, numeric answers |
| Ranking | weighted_kappa, spearman_correlation, kendall_tau, ndcg, map | Ordered lists, rankings |
| Lexical | bleu, rouge, meteor, chrf, edit_distance | Text generation, summarization |
| Semantic | bertscore, moverscore, semantic_similarity | Paraphrase detection, meaning comparison |
| Factuality | factcc, qags, summac, coherence | Fact checking, consistency |
| Structured | json_accuracy, schema_validation, field_accuracy | JSON/structured outputs |
| Span | span_exact_match, iou, partial_match, boundary_accuracy | NER, span extraction |
| Hierarchical | hierarchical_f1, path_accuracy, lca_accuracy | Taxonomy classification |

---

## Classification Metrics

### exact_match
**Description:** Checks if prediction exactly matches ground truth (case-insensitive, whitespace-normalized).
**Citation:** Standard metric
**Output:** 1.0 (match) or 0.0 (no match)
**When to use:** Binary yes/no questions, single correct answer

### accuracy
**Description:** Proportion of correct predictions out of total predictions.
**Citation:** Standard metric
**Output:** 0.0 - 1.0
**When to use:** Multi-class classification with balanced classes

### precision
**Description:** Proportion of true positives among predicted positives.
**Citation:** Standard metric
**Formula:** TP / (TP + FP)
**Output:** 0.0 - 1.0
**When to use:** When false positives are costly

### recall
**Description:** Proportion of true positives among actual positives.
**Citation:** Standard metric
**Formula:** TP / (TP + FN)
**Output:** 0.0 - 1.0
**When to use:** When false negatives are costly

### f1
**Description:** Harmonic mean of precision and recall.
**Citation:** Standard metric
**Formula:** 2 * (precision * recall) / (precision + recall)
**Output:** 0.0 - 1.0
**When to use:** Balance between precision and recall

### cohen_kappa
**Description:** Inter-rater agreement accounting for chance.
**Citation:** Cohen, J. (1960). A coefficient of agreement for nominal scales. Educational and Psychological Measurement.
**Output:** -1.0 to 1.0 (1.0 = perfect agreement, 0 = chance, negative = worse than chance)
**When to use:** Comparing two annotators

### confusion_matrix
**Description:** Table showing true vs predicted class counts.
**Citation:** Standard metric
**Output:** NxN matrix for N classes
**When to use:** Detailed error analysis

---

## Multi-Label Metrics

### jaccard
**Description:** Intersection over union of predicted and actual label sets.
**Citation:** Jaccard, P. (1912). The distribution of the flora in the alpine zone.
**Formula:** |A ∩ B| / |A ∪ B|
**Output:** 0.0 - 1.0
**When to use:** Multiple correct labels, partial credit needed

### hamming_loss
**Description:** Fraction of labels incorrectly predicted.
**Citation:** Standard metric
**Output:** 0.0 - 1.0 (lower is better)
**When to use:** All labels equally important

### subset_accuracy
**Description:** Requires exact match of entire label set.
**Citation:** Standard metric
**Output:** 1.0 (exact match) or 0.0
**When to use:** All-or-nothing evaluation

### token_f1
**Description:** F1 score computed on token level.
**Citation:** Standard metric
**Output:** 0.0 - 1.0
**When to use:** Partial credit for overlapping tokens

---

## Numeric Metrics

### mae
**Description:** Mean Absolute Error - average absolute difference.
**Citation:** Standard metric
**Formula:** Σ|predicted - actual| / n
**Output:** 0+ (lower is better)
**When to use:** Numeric predictions, interpretable error

### rmse
**Description:** Root Mean Square Error - penalizes large errors more.
**Citation:** Standard metric
**Formula:** √(Σ(predicted - actual)² / n)
**Output:** 0+ (lower is better)
**When to use:** Large errors are especially bad

### mape
**Description:** Mean Absolute Percentage Error.
**Citation:** Standard metric
**Formula:** Σ|predicted - actual| / actual * 100
**Output:** 0%+ (lower is better)
**When to use:** Relative error interpretation

### r2
**Description:** Coefficient of determination - explained variance.
**Citation:** Standard metric
**Formula:** 1 - SS_res / SS_tot
**Output:** -∞ to 1.0 (1.0 = perfect)
**When to use:** Regression quality assessment

### correlation
**Description:** Pearson correlation coefficient.
**Citation:** Standard metric
**Output:** -1.0 to 1.0
**When to use:** Linear relationship strength

---

## Ranking Metrics

### weighted_kappa
**Description:** Cohen's kappa with ordinal weights.
**Citation:** Cohen, J. (1968). Weighted kappa.
**Output:** -1.0 to 1.0
**Parameters:** `weights`: "linear" or "quadratic"
**When to use:** Ordinal scales (e.g., 1-5 ratings)

### spearman_correlation
**Description:** Rank correlation (monotonic relationships).
**Citation:** Spearman, C. (1904). The proof and measurement of association.
**Output:** -1.0 to 1.0
**When to use:** Ranking agreement, ordinal data

### kendall_tau
**Description:** Rank correlation based on concordant/discordant pairs.
**Citation:** Kendall, M. (1938). A new measure of rank correlation.
**Output:** -1.0 to 1.0
**When to use:** Small samples, robust to outliers

### ndcg
**Description:** Normalized Discounted Cumulative Gain.
**Citation:** Järvelin & Kekäläinen (2002). Cumulated gain-based evaluation of IR techniques.
**Output:** 0.0 - 1.0
**Parameters:** `k`: top-k cutoff
**When to use:** Information retrieval, recommendation

### map
**Description:** Mean Average Precision.
**Citation:** Standard IR metric
**Output:** 0.0 - 1.0
**When to use:** Ranked retrieval results

---

## Lexical Metrics

### bleu
**Description:** Bilingual Evaluation Understudy - n-gram precision with brevity penalty.
**Citation:** Papineni et al. (2002). BLEU: a Method for Automatic Evaluation of Machine Translation. ACL.
**Output:** 0.0 - 1.0
**Parameters:** `max_order`: 1-4 (default: 4), `weights`: n-gram weights
**When to use:** Machine translation, text generation

### rouge
**Description:** Recall-Oriented Understudy for Gisting Evaluation.
**Citation:** Lin, C. (2004). ROUGE: A Package for Automatic Evaluation of Summaries. ACL Workshop.
**Output:** 0.0 - 1.0 (precision, recall, F1)
**Parameters:** `variant`: "rouge1", "rouge2", "rougeL"
**When to use:** Summarization, text generation

### meteor
**Description:** Metric for Evaluation of Translation with Explicit ORdering.
**Citation:** Banerjee & Lavie (2005). METEOR: An Automatic Metric for MT Evaluation. ACL Workshop.
**Output:** 0.0 - 1.0
**When to use:** Machine translation (considers synonyms, stems)

### chrf
**Description:** Character n-gram F-score.
**Citation:** Popović, M. (2015). chrF: character n-gram F-score for automatic MT evaluation. WMT.
**Output:** 0.0 - 100.0
**Parameters:** `n_char`: character n-gram size, `n_word`: word n-gram size
**When to use:** Morphologically rich languages, robust to tokenization

### edit_distance
**Description:** Levenshtein distance normalized by length.
**Citation:** Levenshtein, V. (1966). Binary codes capable of correcting deletions.
**Output:** 0.0 - 1.0 (1.0 = identical)
**When to use:** Typo detection, string similarity

---

## Semantic Metrics

### bertscore
**Description:** Contextual embedding similarity using BERT.
**Citation:** Zhang et al. (2020). BERTScore: Evaluating Text Generation with BERT. ICLR.
**Output:** 0.0 - 1.0 (precision, recall, F1)
**Parameters:** `lang`: "en", "de", etc.
**When to use:** Semantic similarity, paraphrase detection

### moverscore
**Description:** Earth Mover's Distance on contextualized embeddings.
**Citation:** Zhao et al. (2019). MoverScore: Text Generation Evaluating with Contextualized Embeddings. EMNLP.
**Output:** 0.0 - 1.0
**Parameters:** `lang`: "en", "de", `n_gram`: 1-2, `remove_subwords`: bool
**When to use:** Semantic similarity (word alignment aware)

### semantic_similarity
**Description:** Cosine similarity of sentence embeddings.
**Citation:** Reimers & Gurevych (2019). Sentence-BERT. EMNLP.
**Output:** 0.0 - 1.0
**When to use:** Quick semantic similarity check

---

## Factuality Metrics

### factcc
**Description:** Factual Consistency Checking using NLI.
**Citation:** Kryscinski et al. (2020). Evaluating the Factual Consistency of Abstractive Text Summarization. EMNLP.
**Output:** 0.0 - 1.0
**Parameters:** `method`: "summac" (default) or "factcc"
**When to use:** Summary fact-checking

### qags
**Description:** Question Answering and Generation for Summarization.
**Citation:** Wang et al. (2020). Asking and Answering Questions to Evaluate the Factual Consistency of Summaries. ACL.
**Output:** 0.0 - 1.0
**When to use:** Detailed factual consistency analysis

### summac
**Description:** NLI-based summary consistency.
**Citation:** Laban et al. (2022). SummaC: Re-Visiting NLI-based Models for Inconsistency Detection. TACL.
**Output:** 0.0 - 1.0
**When to use:** State-of-the-art factual consistency

### coherence
**Description:** Text coherence using entity grid and semantic methods.
**Citation:** Barzilay & Lapata (2008). Modeling Local Coherence: An Entity-based Approach. Computational Linguistics.
**Output:** 0.0 - 1.0
**Parameters:** `method`: "entity", "semantic", "hybrid" (default), `entity_weight`, `semantic_weight`
**When to use:** Assessing text flow and structure

---

## Structured Data Metrics

### json_accuracy
**Description:** Exact match of JSON structure and values.
**Citation:** Standard metric
**Output:** 1.0 (match) or 0.0
**When to use:** Structured output validation

### schema_validation
**Description:** JSON Schema compliance checking.
**Citation:** Standard metric
**Output:** 1.0 (valid) or 0.0 (invalid)
**When to use:** Output format validation

### field_accuracy
**Description:** Per-field accuracy for structured data.
**Citation:** Standard metric
**Output:** 0.0 - 1.0
**When to use:** Partial credit for structured outputs

---

## Span/NER Metrics

### span_exact_match
**Description:** Exact boundary and label match for spans.
**Citation:** Standard NER metric
**Output:** 1.0 (match) or 0.0
**When to use:** Strict NER evaluation

### iou
**Description:** Intersection over Union for span boundaries.
**Citation:** Standard metric (from computer vision)
**Output:** 0.0 - 1.0
**When to use:** Partial overlap credit

### partial_match
**Description:** Partial credit for overlapping spans.
**Citation:** SemEval NER evaluation
**Output:** 0.0 - 1.0
**When to use:** Lenient span evaluation

### boundary_accuracy
**Description:** Separate evaluation of start/end boundaries.
**Citation:** Standard NER metric
**Output:** 0.0 - 1.0
**When to use:** Boundary error analysis

---

## Hierarchical Metrics

### hierarchical_f1
**Description:** F1 accounting for hierarchical relationships.
**Citation:** Kiritchenko et al. (2005). Functional annotation of genes.
**Output:** 0.0 - 1.0
**When to use:** Taxonomy classification

### path_accuracy
**Description:** Accuracy of full taxonomy path prediction.
**Citation:** Standard metric
**Output:** 0.0 - 1.0
**When to use:** Multi-level classification

### lca_accuracy
**Description:** Lowest Common Ancestor distance.
**Citation:** Standard metric
**Output:** 0.0 - 1.0
**When to use:** Hierarchical error severity

---

## Metric Selection Guide

### By Answer Type

| Answer Type | Recommended Metrics |
|-------------|-------------------|
| Binary (Yes/No) | exact_match, accuracy, f1, cohen_kappa |
| Single Choice | exact_match, accuracy, confusion_matrix |
| Multiple Choice | jaccard, hamming_loss, subset_accuracy |
| Rating (1-5) | weighted_kappa, mae, spearman_correlation |
| Short Text | exact_match, edit_distance, token_f1 |
| Long Text | bleu, rouge, bertscore, coherence |
| Summary | rouge, factcc, summac, qags |
| Span/NER | span_exact_match, iou, partial_match |
| Taxonomy | hierarchical_f1, path_accuracy |
| JSON/Structured | json_accuracy, schema_validation |

### By Evaluation Goal

| Goal | Metrics |
|------|---------|
| Exact correctness | exact_match, accuracy |
| Semantic meaning | bertscore, moverscore, semantic_similarity |
| Factual accuracy | factcc, summac, qags |
| Text quality | bleu, rouge, coherence, meteor |
| Annotator agreement | cohen_kappa, fleiss_kappa |
| Ranking quality | ndcg, map, spearman_correlation |

---

## German Legal Domain Notes

All metrics support German text. For best results:

- **bertscore/moverscore**: Use `lang="de"` parameter
- **coherence**: Entity extraction uses NLTK (English-trained, works reasonably for German)
- **factcc/summac**: Models trained on English; results may vary for German
- **bleu/rouge**: Language-agnostic, work well with German

Example German legal text metrics:
```python
# BERTScore with German
bertscore(candidate, reference, lang="de")

# MoverScore with German
moverscore(candidate, reference, lang="de")
```

---

## Dependencies

Required packages for each metric category:

```
# Lexical
nltk>=3.8.1
sacrebleu>=2.4.0
rouge-score>=0.1.2

# Semantic
bert-score>=0.3.13
sentence-transformers>=2.2.2
moverscore>=1.0.3

# Factuality
summac>=0.0.4
transformers>=4.30.0

# Statistics
scipy>=1.10.0
scikit-learn>=1.2.0
statsmodels>=0.14.0
```

---

## Error Handling

All metrics follow the "no fallback" principle:
- Empty inputs raise `ValueError`
- Missing dependencies raise `RuntimeError`
- Invalid parameters raise `ValueError`

Errors are explicit and informative for debugging.
