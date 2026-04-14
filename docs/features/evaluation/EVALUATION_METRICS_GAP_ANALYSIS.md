# Evaluation Metrics Gap Analysis: Advanced NLG Metrics

**Date:** 2025-10-17
**Query:** Check for BERTScore, MoverScore, FactCC, QAGS, and LLMaaJ in planned metrics
**Status:** ✅ ANALYSIS COMPLETE

---

## Summary

Out of the 5 advanced metrics queried:
- ✅ **BERTScore** - Already in the list (coming soon)
- ✅ **LLM-as-Judge** - Already has UI placeholder (coming soon)
- ❌ **MoverScore** - NOT in the list
- ❌ **FactCC** - NOT in the list
- ❌ **QAGS** - NOT in the list

---

## Current Metrics Inventory

### All Planned Automated Metrics (35 total)

**Classification & Accuracy (10 metrics):**
1. exact_match ✅ (Stable)
2. accuracy ✅ (Stable)
3. precision ⚠️ (Coming Soon)
4. recall ⚠️ (Coming Soon)
5. f1 ⚠️ (Coming Soon)
6. cohen_kappa ⚠️ (Coming Soon)
7. confusion_matrix ⚠️ (Coming Soon)
8. jaccard ⚠️ (Coming Soon)
9. hamming_loss ⚠️ (Coming Soon)
10. subset_accuracy ⚠️ (Coming Soon)

**Numeric Metrics (5 metrics):**
11. mae ✅ (Stable)
12. rmse ✅ (Stable)
13. mape ✅ (Stable)
14. r2 ⚠️ (Coming Soon)
15. correlation ⚠️ (Coming Soon)

**Text Similarity - Traditional (6 metrics):**
16. bleu 🔵 (Beta - simplified)
17. rouge 🔵 (Beta - simplified)
18. meteor ⚠️ (Coming Soon)
19. edit_distance ✅ (Stable)
20. semantic_similarity ⚠️ (Coming Soon)
21. coherence ⚠️ (Coming Soon)

**Text Similarity - Neural (1 metric):**
22. **bertscore** ⚠️ (Coming Soon) **← FOUND**

**Structured Data (3 metrics):**
23. json_accuracy ⚠️ (Coming Soon)
24. schema_validation ⚠️ (Coming Soon)
25. field_accuracy ⚠️ (Coming Soon)

**NER/Span Metrics (4 metrics):**
26. token_f1 ⚠️ (Coming Soon)
27. span_exact_match ⚠️ (Coming Soon)
28. partial_match ⚠️ (Coming Soon)
29. boundary_accuracy ⚠️ (Coming Soon)

**Vision/Spatial (4 metrics):**
30. iou ⚠️ (Coming Soon)
31. map ⚠️ (Coming Soon)
32. pixel_accuracy ⚠️ (Coming Soon)
33. dice_coefficient ⚠️ (Coming Soon)

**Ranking Metrics (2 metrics):**
34. spearman_correlation ⚠️ (Coming Soon)
35. kendall_tau ⚠️ (Coming Soon)
36. ndcg ⚠️ (Coming Soon)
37. weighted_kappa ⚠️ (Coming Soon)

**Hierarchical (3 metrics):**
38. hierarchical_f1 ⚠️ (Coming Soon)
39. path_accuracy ⚠️ (Coming Soon)
40. lca_accuracy ⚠️ (Coming Soon)

### Human Evaluation Methods (5 total)

1. agreement ⚠️ (Coming Soon)
2. preference ⚠️ (Coming Soon)
3. likert ⚠️ (Coming Soon)
4. ranking ⚠️ (Coming Soon)
5. detailed_review ⚠️ (Coming Soon)

### LLM-as-Judge Infrastructure

**Frontend:** `/services/frontend/src/app/evaluations/page.tsx`
- Has dedicated evaluation step: `'llm-judge'`
- UI placeholder exists: "LLM-as-Judge Evaluation"
- Tab navigation: "LLM-as-Judge"
- Results section: "LLM Judge Results"

**Status:** UI structure exists, backend implementation pending

---

## Detailed Analysis of Queried Metrics

### 1. ✅ BERTScore - FOUND IN LIST

**Status:** Planned (Coming Soon)

**Locations:**
- `services/api/evaluation_config.py:75` - In LONG_TEXT automated metrics
- `services/api/evaluation_config.py:124` - In CUSTOM type metrics
- `services/frontend/src/components/evaluation/EvaluationMethodSelector.tsx:80` - In ALL_AUTOMATED_METRICS
- `services/frontend/src/components/evaluation/EvaluationMethodSelector.tsx:135` - Status: 'coming-soon'

**Description (from frontend):**
> "BERT-based semantic similarity"

**Mapped to Answer Types:**
- LONG_TEXT (essays, multi-line text)
- CUSTOM (fallback for unknown types)

**Implementation Status:** Not yet implemented
**Badge:** 🟡 Coming Soon

---

### 2. ✅ LLM-as-Judge - UI EXISTS

**Status:** Infrastructure ready, implementation pending

**Locations:**
- `services/frontend/src/app/evaluations/page.tsx:type EvaluationStep` - Has 'llm-judge' step
- `services/frontend/src/app/evaluations/page.tsx:{ key: 'llm-judge', label: 'LLM-as-Judge' }`
- `services/frontend/src/app/evaluations/page.tsx:{currentStep === 'llm-judge' && ...}`
- `services/frontend/src/app/evaluations/__tests__/page.test.tsx` - Multiple test cases

**Frontend Components:**
- Tab in evaluation steps navigation
- Dedicated results section
- Placeholder UI: "No LLM judge evaluations have been run yet."

**Test Coverage:**
- Navigation to llm-judge step
- LLM-as-Judge evaluation section rendering
- Results display expectations

**Implementation Status:** UI structure complete, backend pending
**Badge:** N/A (separate evaluation type, not a metric)

---

### 3. ❌ MoverScore - NOT IN LIST

**Status:** Not planned

**What is MoverScore?**
- Advanced semantic similarity metric
- Based on contextualized embeddings and Earth Mover's Distance
- Better correlation with human judgments than BLEU/ROUGE
- Published 2019 (Wei Zhao et al.)

**Why Add It?**
- More nuanced than simple word overlap
- Handles paraphrasing better than BLEU
- Good for legal text where phrasing varies but meaning is preserved

**Potential Location:**
- LONG_TEXT automated metrics
- SHORT_TEXT automated metrics
- Could complement BERTScore

**Recommendation:** ✅ Add to roadmap for neural text similarity metrics

---

### 4. ❌ FactCC - NOT IN LIST

**Status:** Not planned

**What is FactCC?**
- Factual Consistency Checking
- Uses BERT-based classifier to detect hallucinations/factual errors
- Specifically for checking if summary is consistent with source
- Published 2020 (Kryscinski et al.)

**Why Add It?**
- Critical for legal domain where factual accuracy is paramount
- Detects hallucinations in LLM-generated summaries
- Can verify legal case summaries against original documents

**Use Cases in BenGER:**
- Legal case summarization
- Document classification justifications
- Fact extraction verification

**Potential Location:**
- LONG_TEXT automated metrics (specifically for summarization)
- STRUCTURED_TEXT (for factual claim verification)

**Recommendation:** ✅✅ **HIGH PRIORITY** - Add to roadmap for legal text evaluation

---

### 5. ❌ QAGS - NOT IN LIST

**Status:** Not planned

**What is QAGS?**
- Question Answering and Generation for Summarization
- Evaluates summary quality by generating QA pairs
- Checks if questions about summary can be answered from source
- Published 2020 (Wang et al.)

**Why Add It?**
- Reference-free evaluation (doesn't need gold standard)
- Good for open-ended generation tasks
- Can assess information completeness

**Use Cases in BenGER:**
- Legal document summarization
- Question answering quality
- Information coverage assessment

**Potential Location:**
- LONG_TEXT automated metrics
- Could be a new category: "Reference-Free Metrics"

**Recommendation:** ⚠️ Medium priority - Useful but computationally expensive

---

## Recommendations

### Immediate Additions (High Priority)

#### 1. FactCC ✅✅
**Reason:** Essential for legal domain - factual consistency is critical
**Implementation Complexity:** Medium (requires BERT fine-tuned model)
**Use Case:** Verify legal summaries don't introduce factual errors
**Add to:**
```python
AnswerType.LONG_TEXT: {
    "automated": [
        "bleu", "rouge", "meteor", "bertscore",
        "factcc",  # NEW - Factual consistency
        "semantic_similarity", "coherence"
    ]
}
```

#### 2. MoverScore ✅
**Reason:** Better semantic similarity than word overlap metrics
**Implementation Complexity:** Medium (requires pre-trained embeddings)
**Use Case:** Better evaluation of paraphrased legal arguments
**Add to:**
```python
AnswerType.LONG_TEXT: {
    "automated": [
        "bleu", "rouge", "meteor", "bertscore",
        "moverscore",  # NEW - Earth Mover's Distance similarity
        "semantic_similarity", "coherence"
    ]
}

AnswerType.SHORT_TEXT: {
    "automated": [
        "exact_match", "bleu", "rouge", "edit_distance",
        "moverscore",  # NEW
        "semantic_similarity"
    ]
}
```

### Future Additions (Medium Priority)

#### 3. QAGS ⚠️
**Reason:** Reference-free evaluation useful but computationally expensive
**Implementation Complexity:** High (requires QA model + generation)
**Use Case:** Evaluate summaries without reference text
**Add to:**
```python
AnswerType.LONG_TEXT: {
    "automated": [
        "bleu", "rouge", "meteor", "bertscore",
        "factcc", "moverscore",
        "qags",  # NEW - Question-based evaluation
        "semantic_similarity", "coherence"
    ]
}
```

### Additional Advanced Metrics to Consider

#### 4. BLANC (Beyond-ROUGE, similar to QAGS)
- Reference-free summarization metric
- Uses language model's understanding
- Less computationally expensive than QAGS

#### 5. SummaC (Summary Consistency)
- Similar to FactCC
- Detects factual inconsistencies in summaries
- More recent (2022) and potentially better

#### 6. UniEval (Universal Evaluator)
- Multi-dimensional evaluation
- Covers coherence, consistency, fluency, relevance
- Unified framework for multiple metrics

---

## Implementation Priority Matrix

| Metric | Priority | Domain Fit | Complexity | Status |
|--------|----------|------------|------------|--------|
| BERTScore | High | ★★★★☆ | Medium | ✅ Planned |
| FactCC | **Highest** | ★★★★★ | Medium | ❌ Not planned |
| MoverScore | High | ★★★★☆ | Medium | ❌ Not planned |
| QAGS | Medium | ★★★☆☆ | High | ❌ Not planned |
| LLM-as-Judge | High | ★★★★★ | Low | ✅ UI ready |

---

## Updated Metrics Roadmap

### Phase 1: Core Metrics (Current Focus)
- ✅ exact_match, accuracy, mae, rmse, mape, edit_distance (Stable)
- 🔵 bleu, rouge (Beta)
- ⚠️ precision, recall, f1, confusion_matrix (Coming Soon)

### Phase 2: Neural Similarity (Recommended Next)
- ⚠️ **bertscore** (Already planned)
- 🆕 **moverscore** (Should add)
- ⚠️ semantic_similarity (Already planned)

### Phase 3: Factual Consistency (Critical for Legal)
- 🆕 **factcc** (Should add - HIGH PRIORITY)
- 🆕 summac (Alternative to FactCC)

### Phase 4: Advanced Evaluation
- 🆕 qags (Optional)
- 🆕 blanc (Alternative to QAGS)
- 🆕 unieval (Comprehensive)

### Phase 5: LLM-Based
- ⚠️ LLM-as-Judge implementation (UI exists)
- Custom prompt-based evaluation
- GPT-4 as evaluator

---

## Code Changes Needed

### 1. Add New Metrics to Backend

**File:** `services/api/evaluation_config.py`

```python
AnswerType.LONG_TEXT: {
    "automated": [
        "bleu", "rouge", "meteor", "bertscore",
        "moverscore",  # NEW - Earth Mover's Distance
        "factcc",      # NEW - Factual consistency
        "qags",        # NEW - QA-based evaluation
        "semantic_similarity", "coherence"
    ],
    "human": ["likert", "preference", "ranking", "detailed_review"],
}

AnswerType.SHORT_TEXT: {
    "automated": [
        "exact_match", "bleu", "rouge", "edit_distance",
        "moverscore",  # NEW
        "semantic_similarity"
    ],
    "human": ["likert", "preference", "agreement"],
}
```

### 2. Add to Frontend Lists

**File:** `services/frontend/src/components/evaluation/EvaluationMethodSelector.tsx`

```typescript
const ALL_AUTOMATED_METRICS = [
  // ... existing metrics ...
  'bertscore',
  'moverscore',    // NEW
  'factcc',        // NEW
  'qags',          // NEW
  'semantic_similarity',
  // ... rest ...
]

const METRIC_IMPLEMENTATION_STATUS = {
  // ... existing ...
  bertscore: 'coming-soon',
  moverscore: 'coming-soon',    // NEW
  factcc: 'coming-soon',        // NEW
  qags: 'coming-soon',          // NEW
}
```

### 3. Add Descriptions

```typescript
const descriptions = {
  // ... existing ...
  bertscore: 'BERT-based semantic similarity',
  moverscore: 'Contextualized embedding similarity with Earth Mover\'s Distance',
  factcc: 'Factual consistency checking for summaries',
  qags: 'Question answering-based summarization quality',
}
```

### 4. Update Documentation

Both English and German locale files need updates for:
- New metric names
- Descriptions
- Use cases
- Examples

---

## Implementation Dependencies

### BERTScore
```bash
pip install bert-score
# Requires: transformers, torch, numpy
```

### MoverScore
```bash
pip install moverscore
# Requires: transformers, torch, pyemd, numpy
```

### FactCC
```bash
# No official package - need to implement from paper
# Requires: transformers, torch, fine-tuned BERT model
```

### QAGS
```bash
# No official package - need to implement
# Requires: transformers, question generation model, QA model
```

---

## Testing Plan

### Unit Tests
- Test metric computation on known examples
- Verify score ranges (0-1 vs unbounded)
- Check handling of edge cases (empty strings, mismatched types)

### Integration Tests
- Test full evaluation pipeline with new metrics
- Verify database storage of new metric results
- Check API endpoint responses include new metrics

### Validation Tests
- Compare against published benchmarks
- Verify correlation with human judgments
- Test on legal domain specific examples

---

## Documentation Updates Needed

### English (`en/common.json`)
```json
"answerTypes": {
  "longText": {
    "metrics": "bleu, rouge, meteor, bertscore, moverscore, factcc, qags, semantic_similarity, coherence"
  }
},
"currentlyImplemented": {
  "comingSoon": [
    "bertscore - BERT-based semantic similarity",
    "moverscore - Contextualized embedding similarity",
    "factcc - Factual consistency for summaries",
    "qags - Question answering-based evaluation"
  ]
}
```

### German (`de/common.json`)
```json
"answerTypes": {
  "longText": {
    "metrics": "bleu, rouge, meteor, bertscore, moverscore, factcc, qags, semantic_similarity, coherence"
  }
},
"currentlyImplemented": {
  "comingSoon": [
    "bertscore - BERT-basierte semantische Ähnlichkeit",
    "moverscore - Kontextualisierte Embedding-Ähnlichkeit",
    "factcc - Faktische Konsistenzprüfung für Zusammenfassungen",
    "qags - Fragenbasierte Evaluierung"
  ]
}
```

---

## Summary

### Found in Current List ✅
1. **BERTScore** - Already planned for LONG_TEXT metrics
2. **LLM-as-Judge** - UI infrastructure exists, backend pending

### Missing from List ❌
3. **MoverScore** - Should add (High Priority)
4. **FactCC** - Should add (Highest Priority for legal domain)
5. **QAGS** - Consider adding (Medium Priority)

### Recommendation
Add MoverScore, FactCC, and QAGS to the roadmap as advanced neural metrics for text evaluation, with FactCC being highest priority due to critical importance of factual accuracy in legal applications.

---

**Analysis By:** Development Team
**Analysis Time:** ~30 minutes
**Files Analyzed:** 4
**Metrics Found:** 2/5
**Recommendation:** Add 3 missing metrics to roadmap
**Priority:** FactCC (Highest), MoverScore (High), QAGS (Medium)
