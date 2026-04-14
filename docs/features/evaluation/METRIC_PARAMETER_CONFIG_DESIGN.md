# Metric Parameter Configuration System Design

**Date:** 2025-10-17
**Purpose:** Enable configurable metric parameters while maintaining sensible defaults
**Status:** 🔨 IMPLEMENTATION IN PROGRESS

---

## Design Philosophy

1. **Simple by default**: `"bleu"` works out of the box with industry standards
2. **Configurable when needed**: Advanced users can tune parameters
3. **Backwards compatible**: Existing configs with string names still work
4. **Well-documented**: Clear defaults and parameter explanations

---

## Configuration Schema

### Simple Format (Default Parameters)

```json
{
  "selected_methods": {
    "explanation_field": {
      "automated": ["bleu", "rouge", "meteor"],
      "human": []
    }
  }
}
```

**Behavior:** Uses hard-coded industry-standard defaults

### Advanced Format (Custom Parameters)

```json
{
  "selected_methods": {
    "explanation_field": {
      "automated": [
        "exact_match",
        {
          "name": "bleu",
          "parameters": {
            "max_order": 2,
            "weights": [0.5, 0.5],
            "smoothing": "method1"
          }
        },
        {
          "name": "rouge",
          "parameters": {
            "variant": "rouge1",
            "use_stemmer": true
          }
        }
      ]
    }
  }
}
```

**Behavior:** Uses specified parameters, falls back to defaults if parameter missing

### Mixed Format (Supported)

```json
{
  "selected_methods": {
    "explanation_field": {
      "automated": [
        "exact_match",           // Simple - use defaults
        {                        // Advanced - custom config
          "name": "bleu",
          "parameters": {"max_order": 2}
        },
        "rouge",                 // Simple - use defaults
        {
          "name": "chrf",
          "parameters": {"char_order": 4}
        }
      ]
    }
  }
}
```

---

## Default Parameters Reference

### BLEU - BiLingual Evaluation Understudy

**Defaults:**
```python
{
  "max_order": 4,                          # BLEU-4 (n-grams 1-4)
  "weights": [0.25, 0.25, 0.25, 0.25],    # Equal weights
  "smoothing": "method1"                   # SmoothingFunction.method1
}
```

**Configurable Parameters:**
- `max_order` (int, 1-4): Highest n-gram order
  - 1 = BLEU-1 (unigram only)
  - 2 = BLEU-2 (up to bigrams)
  - 4 = BLEU-4 (standard)
- `weights` (list[float]): Weight for each n-gram order
  - Must match `max_order` length
  - Must sum to 1.0
- `smoothing` (str): Smoothing method for short sentences
  - "method1" (default) - add epsilon to zero counts
  - "method2" - add 1 to all counts
  - "method3" - NIST geometric average
  - "method4" - chen & cherry smoothing

**Use Cases:**
- BLEU-1: Very short texts (< 5 words)
- BLEU-2: Short summaries (5-15 words)
- BLEU-4: Standard for MT evaluation

---

### ROUGE - Recall-Oriented Understudy for Gisting Evaluation

**Defaults:**
```python
{
  "variant": "rougeL",       # Longest Common Subsequence
  "use_stemmer": true        # Enable stemming
}
```

**Configurable Parameters:**
- `variant` (str): ROUGE metric variant
  - "rouge1" - Unigram overlap
  - "rouge2" - Bigram overlap
  - "rougeL" (default) - LCS-based
  - "rougeLsum" - LCS for multi-sentence
- `use_stemmer` (bool): Apply Porter stemmer
  - true (default) - Better matching
  - false - Exact word matching

**Use Cases:**
- ROUGE-1: Keyword coverage, content selection
- ROUGE-2: Phrase-level matching
- ROUGE-L: Sentence structure preservation

---

### METEOR - Metric for Evaluation of Translation with Explicit ORdering

**Defaults:**
```python
{
  "alpha": 0.9,     # Precision weight
  "beta": 3.0,      # Recall preference
  "gamma": 0.5      # Chunk penalty
}
```

**Configurable Parameters:**
- `alpha` (float, 0-1): Weight for precision vs recall
  - 0.9 (default) - balanced
  - Higher = more precision-focused
- `beta` (float): Recall preference strength
  - 3.0 (default) - prefer recall
- `gamma` (float): Fragmentation penalty
  - 0.5 (default) - penalize non-contiguous matches

**Note:** METEOR's core strength (synonyms/stemming) is not configurable

---

### chrF - Character n-gram F-score

**Defaults:**
```python
{
  "char_order": 6,    # Character 6-grams
  "word_order": 0,    # No word n-grams (chrF, not chrF++)
  "beta": 2           # F2-score (recall-weighted)
}
```

**Configurable Parameters:**
- `char_order` (int, 1-6): Max character n-gram order
  - 4 - Good for morphologically simple languages
  - 6 (default) - Standard for MT evaluation
- `word_order` (int, 0-2): Word n-gram order
  - 0 (default) - chrF (character only)
  - 2 - chrF++ (characters + words)
- `beta` (int): F-score beta parameter
  - 1 - F1-score (balanced)
  - 2 (default) - F2-score (recall-weighted)
  - 3 - F3-score (even more recall)

**Use Cases:**
- char_order=4: Morphologically simple languages
- char_order=6: Morphologically rich languages (German)
- word_order=2: chrF++ for better correlation with human judgment

---

## Implementation Strategy

### Backend Changes

#### 1. Update evaluation_config.py

Add normalization function to support both formats:

```python
def normalize_metric_selection(selection: Union[str, Dict]) -> Dict:
    """
    Normalize metric selection to standard format.

    Args:
        selection: Either "metric_name" or {"name": "metric_name", "parameters": {...}}

    Returns:
        Normalized dict with name and parameters
    """
    if isinstance(selection, str):
        return {"name": selection, "parameters": {}}
    return selection

def get_metric_defaults(metric_name: str) -> Dict[str, Any]:
    """Get default parameters for a metric"""
    defaults = {
        "bleu": {
            "max_order": 4,
            "weights": [0.25, 0.25, 0.25, 0.25],
            "smoothing": "method1"
        },
        "rouge": {
            "variant": "rougeL",
            "use_stemmer": True
        },
        "meteor": {
            "alpha": 0.9,
            "beta": 3.0,
            "gamma": 0.5
        },
        "chrf": {
            "char_order": 6,
            "word_order": 0,
            "beta": 2
        }
    }
    return defaults.get(metric_name, {})
```

#### 2. Update sample_evaluator.py

Accept parameters in compute methods:

```python
def _compute_text_similarity(
    self,
    metric_name: str,
    gt: str,
    pred: str,
    parameters: Optional[Dict[str, Any]] = None
) -> float:
    """Compute text similarity metrics with configurable parameters"""
    if parameters is None:
        parameters = {}

    if metric_name == "bleu":
        # Get parameters with defaults
        max_order = parameters.get("max_order", 4)
        weights_map = {
            1: [1.0],
            2: [0.5, 0.5],
            3: [0.33, 0.33, 0.34],
            4: [0.25, 0.25, 0.25, 0.25]
        }
        weights = parameters.get("weights", weights_map[max_order])
        smoothing = parameters.get("smoothing", "method1")

        # Use configured parameters
        ...
```

#### 3. Add Pydantic Schemas

```python
# services/api/schemas/evaluation_schemas.py

class BLEUParameters(BaseModel):
    max_order: int = Field(4, ge=1, le=4)
    weights: Optional[List[float]] = None
    smoothing: str = Field("method1", pattern="^method[1-4]$")

class ROUGEParameters(BaseModel):
    variant: str = Field("rougeL", pattern="^rouge(1|2|L|Lsum)$")
    use_stemmer: bool = True

class METEORParameters(BaseModel):
    alpha: float = Field(0.9, ge=0.0, le=1.0)
    beta: float = Field(3.0, ge=0.0)
    gamma: float = Field(0.5, ge=0.0)

class chrFParameters(BaseModel):
    char_order: int = Field(6, ge=1, le=6)
    word_order: int = Field(0, ge=0, le=2)
    beta: int = Field(2, ge=1, le=3)

class MetricSelection(BaseModel):
    """Metric selection with optional parameters"""
    name: str
    parameters: Optional[Dict[str, Any]] = {}

    @classmethod
    def from_simple(cls, metric_name: str):
        """Create from simple string format"""
        return cls(name=metric_name, parameters={})
```

### Frontend Changes

#### 1. Update EvaluationMethodSelector.tsx

Add collapsible "Advanced" section for each metric:

```typescript
// Show basic checkbox
<Checkbox checked={isSelected} onChange={handleToggle}>
  {metric}
</Checkbox>

// Show advanced config when metric is selected
{isSelected && (
  <Collapsible>
    <CollapsibleTrigger>
      ⚙️ Advanced Parameters
    </CollapsibleTrigger>
    <CollapsibleContent>
      {metric === 'bleu' && <BLEUConfig />}
      {metric === 'rouge' && <ROUGEConfig />}
      {metric === 'meteor' && <METEORConfig />}
      {metric === 'chrf' && <chrFConfig />}
    </CollapsibleContent>
  </Collapsible>
)}
```

#### 2. Create Parameter Components

```typescript
function BLEUConfig({ value, onChange }) {
  return (
    <div className="space-y-2 pl-6">
      <Select value={value.max_order} onChange={...}>
        <option value={1}>BLEU-1 (unigram)</option>
        <option value={2}>BLEU-2 (up to bigram)</option>
        <option value={4}>BLEU-4 (standard) ⭐</option>
      </Select>

      <Select value={value.smoothing} onChange={...}>
        <option value="method1">Method 1 (default) ⭐</option>
        <option value="method2">Method 2 (add-one)</option>
        <option value="method3">Method 3 (NIST)</option>
      </Select>
    </div>
  )
}
```

---

## Migration Strategy

### Phase 1: Backend Support (Current)
- ✅ Add parameter support to sample_evaluator
- ✅ Add normalization helpers
- ✅ Support both string and dict formats
- ✅ Document defaults

### Phase 2: API Integration
- Add Pydantic schemas for validation
- Update API endpoints to accept new format
- Add validation for parameter ranges
- Update database storage (no schema change needed - JSON field)

### Phase 3: Frontend UI
- Add "Advanced" collapsible sections
- Create parameter input components
- Add tooltips explaining each parameter
- Show defaults with star (⭐) indicator

### Phase 4: Documentation
- Update how-to guides
- Add parameter tuning guide
- Add examples for common use cases
- Add research paper references

---

## Validation Rules

### BLEU
- `max_order` must be 1-4
- `weights` length must match `max_order`
- `weights` must sum to 1.0
- `smoothing` must be one of: method1, method2, method3, method4

### ROUGE
- `variant` must be: rouge1, rouge2, rougeL, rougeLsum
- `use_stemmer` must be boolean

### METEOR
- `alpha` must be 0.0-1.0
- `beta` must be positive
- `gamma` must be positive

### chrF
- `char_order` must be 1-6
- `word_order` must be 0-2
- `beta` must be 1-3

---

## Example Use Cases

### Use Case 1: Short Legal Snippets (< 10 words)

```json
{
  "selected_methods": {
    "verdict_field": {
      "automated": [
        {
          "name": "bleu",
          "parameters": {
            "max_order": 2,
            "weights": [0.5, 0.5]
          }
        }
      ]
    }
  }
}
```

**Why:** Shorter n-grams work better for very short texts

### Use Case 2: Research Replication

```json
{
  "selected_methods": {
    "summary_field": {
      "automated": [
        {
          "name": "rouge",
          "parameters": {
            "variant": "rouge2",
            "use_stemmer": false
          }
        }
      ]
    }
  }
}
```

**Why:** Paper used ROUGE-2 without stemming

### Use Case 3: German Legal Text Optimization

```json
{
  "selected_methods": {
    "explanation_field": {
      "automated": [
        {
          "name": "chrf",
          "parameters": {
            "char_order": 6,
            "word_order": 2,
            "beta": 2
          }
        }
      ]
    }
  }
}
```

**Why:** chrF++ (word_order=2) works better for German compound words

---

## Testing Plan

### Unit Tests

```python
def test_simple_metric_selection():
    """Test simple string format uses defaults"""
    config = {"automated": ["bleu", "rouge"]}
    metrics = normalize_config(config)
    assert metrics[0]["parameters"]["max_order"] == 4

def test_advanced_metric_selection():
    """Test custom parameters override defaults"""
    config = {
        "automated": [
            {"name": "bleu", "parameters": {"max_order": 2}}
        ]
    }
    metrics = normalize_config(config)
    assert metrics[0]["parameters"]["max_order"] == 2

def test_mixed_metric_selection():
    """Test mixing simple and advanced formats"""
    config = {
        "automated": [
            "rouge",
            {"name": "bleu", "parameters": {"max_order": 2}}
        ]
    }
    metrics = normalize_config(config)
    assert len(metrics) == 2
```

### Integration Tests

- Test evaluation with custom BLEU-2
- Test evaluation with ROUGE-1 vs ROUGE-L
- Test parameter validation rejects invalid values
- Test backwards compatibility with string-only configs

---

## Performance Considerations

**Parameter Overhead:** Negligible
- Parsing parameters: < 1ms
- Using different n-gram orders: Same complexity

**Memory Overhead:** Minimal
- Additional JSON fields: ~100 bytes per metric
- No impact on computation memory

---

## Documentation Deliverables

1. **User Guide:**
   - "When to Use Custom Parameters"
   - Parameter tuning cookbook
   - Common configurations for legal text

2. **API Reference:**
   - Parameter schemas
   - Validation rules
   - Example requests

3. **Frontend Help:**
   - Tooltips for each parameter
   - "Learn More" links to research papers
   - Recommended values for different text lengths

---

## Future Enhancements

### Phase 5: Presets
```json
{
  "preset": "short_text",  // Uses BLEU-2, ROUGE-1, chrF with char_order=4
  "metrics": ["bleu", "rouge", "chrf"]
}
```

### Phase 6: Automatic Tuning
- Analyze text length distribution
- Suggest optimal n-gram orders
- A/B test different parameter combinations

### Phase 7: Per-Sample Parameters
- Different parameters for different text lengths
- Adaptive n-gram selection
- Context-aware configuration

---

## Success Criteria

- ✅ Simple path still works (backwards compatible)
- ✅ Advanced users can tune parameters
- ✅ Defaults are well-documented
- ✅ Parameter validation prevents errors
- ✅ UI makes advanced options discoverable but not overwhelming
- ✅ Performance impact < 5% overhead

---

**Status:** Design complete, ready for implementation
**Next Steps:** Implement backend normalization and parameter passing
