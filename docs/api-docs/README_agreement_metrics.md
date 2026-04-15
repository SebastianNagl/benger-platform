# Agreement Metrics Calculation Engine

A comprehensive, mathematically accurate implementation of various inter-annotator agreement metrics for the BenGER annotation system.

## Overview

The Agreement Metrics Calculation Engine provides robust implementations of all major agreement metrics used in annotation tasks, with support for different data types, caching, and comprehensive error handling.

## Features

- **Complete Metric Coverage**: Implements all metrics defined in the system models
- **Multiple Data Types**: Supports categorical, numerical, ordinal, and text annotations
- **Performance Optimized**: Redis caching for fast repeated calculations
- **Mathematically Accurate**: Based on established statistical formulas with proper references
- **Robust Error Handling**: Graceful handling of edge cases and invalid data
- **Flexible Input**: Easy conversion from various data formats
- **Comprehensive Testing**: 43+ unit tests covering all functionality

## Supported Metrics

### Categorical Data
- **Cohen's Kappa**: Pairwise agreement correcting for chance
- **Fleiss' Kappa**: Multi-rater agreement correcting for chance
- **Percent Agreement**: Simple proportion of agreeing annotations
- **Krippendorff's Alpha**: Robust agreement measure for any number of annotators

### Numerical Data
- **Pearson Correlation**: Linear relationship between numerical annotations
- **Spearman Correlation**: Rank-based correlation for ordinal data
- **Intraclass Correlation (ICC)**: Reliability measure for numerical ratings

## Quick Start

### Basic Usage

```python
from agreement_metrics import AgreementMetricsEngine, AnnotationValue
from models import AgreementMetricType

# Create annotation data
annotations = [
    AnnotationValue("positive", "annotator_1", "item_1", "categorical"),
    AnnotationValue("positive", "annotator_2", "item_1", "categorical"),
    AnnotationValue("negative", "annotator_1", "item_2", "categorical"),
    AnnotationValue("negative", "annotator_2", "item_2", "categorical"),
]

# Initialize engine
engine = AgreementMetricsEngine()

# Calculate specific metric
result = engine.calculate_metric(AgreementMetricType.COHEN_KAPPA, annotations)
print(f"Cohen's Kappa: {result.score:.4f}")

# Calculate all metrics
all_results = engine.calculate_all_metrics(annotations)
```

### With Caching

```python
import redis
from agreement_metrics import AgreementMetricsEngine

# Connect to Redis
redis_client = redis.Redis(host='localhost', port=6379)

# Initialize engine with caching
engine = AgreementMetricsEngine(cache_client=redis_client)

# Calculations are automatically cached
result = engine.calculate_metric(AgreementMetricType.FLEISS_KAPPA, annotations)
```

### Convert from Dictionary Data

```python
from agreement_metrics import convert_annotations_from_dict

# Your existing data format
annotations_data = [
    {"annotator_id": "user_1", "item_id": "doc_1", "value": "positive"},
    {"annotator_id": "user_2", "item_id": "doc_1", "value": "positive"},
]

# Convert to required format
annotations = convert_annotations_from_dict(annotations_data)

# Calculate metrics
engine = AgreementMetricsEngine()
results = engine.calculate_all_metrics(annotations)
```

## Detailed Usage

### Data Structure

The core data structure is `AnnotationValue`:

```python
@dataclass
class AnnotationValue:
    value: Any                    # The annotation value
    annotator_id: str            # Unique annotator identifier
    item_id: str                 # Unique item identifier
    data_type: str               # 'categorical', 'numerical', 'ordinal', 'text'
    confidence: Optional[float]   # Optional confidence score
    timestamp: Optional[datetime] # Optional timestamp
```

### Results Structure

All calculations return `AgreementResult`:

```python
@dataclass
class AgreementResult:
    metric_type: AgreementMetricType      # Type of metric calculated
    score: float                          # Agreement score
    confidence_interval: Optional[Tuple[float, float]]  # 95% CI if available
    p_value: Optional[float]              # Statistical significance
    standard_error: Optional[float]       # Standard error
    sample_size: int                      # Number of annotations
    metadata: Optional[Dict[str, Any]]    # Additional calculation details
```

### Metric-Specific Parameters

#### Krippendorff's Alpha
```python
result = engine.calculate_metric(
    AgreementMetricType.KRIPPENDORFF_ALPHA,
    annotations,
    distance_function='nominal'  # 'nominal', 'ordinal', 'interval', 'ratio'
)
```

#### Intraclass Correlation
```python
result = engine.calculate_metric(
    AgreementMetricType.INTRACLASS_CORRELATION,
    annotations,
    icc_type='ICC(2,1)'  # ICC type specification
)
```

## Mathematical Formulations

### Cohen's Kappa
```
κ = (p_o - p_e) / (1 - p_e)
```
Where:
- `p_o` = observed agreement
- `p_e` = expected agreement by chance

### Fleiss' Kappa
```
κ = (P̄ - P̄_e) / (1 - P̄_e)
```
Where:
- `P̄` = mean pairwise agreement
- `P̄_e` = expected agreement

### Krippendorff's Alpha
```
α = 1 - (D_o / D_e)
```
Where:
- `D_o` = observed disagreement
- `D_e` = expected disagreement

### Intraclass Correlation
```
ICC = (MS_items - MS_error) / (MS_items + (k-1) * MS_error + k * (MS_raters - MS_error) / n)
```
Where:
- `MS_items` = Mean square between items
- `MS_error` = Mean square error
- `MS_raters` = Mean square between raters
- `k` = number of raters
- `n` = number of items

## Data Type Recommendations

| Data Type | Recommended Metrics |
|-----------|-------------------|
| **Categorical** | Cohen's Kappa, Fleiss' Kappa, Percent Agreement, Krippendorff's Alpha |
| **Numerical** | Pearson Correlation, ICC, Krippendorff's Alpha (interval/ratio) |
| **Ordinal** | Spearman Correlation, Krippendorff's Alpha (ordinal) |
| **Text** | Percent Agreement, Krippendorff's Alpha (nominal) |

## Interpretation Guidelines

### Cohen's Kappa / Fleiss' Kappa
- `< 0.20`: Poor agreement
- `0.20 - 0.40`: Fair agreement
- `0.40 - 0.60`: Moderate agreement
- `0.60 - 0.80`: Substantial agreement
- `> 0.80`: Excellent agreement

### Percent Agreement
- `< 0.60`: Poor agreement
- `0.60 - 0.80`: Fair agreement
- `0.80 - 0.90`: Good agreement
- `> 0.90`: Excellent agreement

### Correlation Coefficients
- `< 0.30`: Weak correlation
- `0.30 - 0.50`: Moderate correlation
- `0.50 - 0.70`: Strong correlation
- `> 0.70`: Very strong correlation

## Validation and Error Handling

The engine includes comprehensive validation:

```python
# Check if annotations are valid for a specific metric
valid, error = engine.validate_annotations_for_metric(
    AgreementMetricType.COHEN_KAPPA,
    annotations
)

if not valid:
    print(f"Validation error: {error}")
```

Common validation rules:
- Minimum 2 annotators required
- Cohen's Kappa requires exactly 2 annotators
- Pearson correlation requires numerical data
- Minimum sample size requirements

## Performance Considerations

### Caching
- Automatic cache key generation based on annotation content
- Configurable TTL (default: 1 hour)
- Transparent cache hits/misses

### Complexity
- **Cohen's Kappa**: O(n²) where n = categories
- **Fleiss' Kappa**: O(n × m × k) where n = items, m = annotators, k = categories
- **Correlations**: O(n log n) for sorting
- **ICC**: O(n × m) for matrix operations

## Integration with BenGER

### Database Integration
```python
from agreement_metrics import AgreementMetricsEngine, AnnotationValue
from models import AgreementMetricType, TaskAgreement

def calculate_task_agreement(task_id: str, db: Session):
    """Calculate agreement metrics for a task"""
    
    # Fetch annotations from database
    annotations_data = db.query(FlexibleAnnotation).filter(
        FlexibleAnnotation.task_id == task_id
    ).all()
    
    # Convert to AnnotationValue format
    annotations = []
    for ann in annotations_data:
        annotations.append(AnnotationValue(
            value=ann.annotation_data.get('answer'),  # Extract relevant field
            annotator_id=ann.annotator_id,
            item_id=ann.item_id,
            data_type='categorical'  # Infer or specify
        ))
    
    # Calculate metrics
    engine = AgreementMetricsEngine(cache_client=redis_client)
    results = engine.calculate_all_metrics(annotations)
    
    # Store in database
    for metric_type, result in results.items():
        agreement = TaskAgreement(
            task_id=task_id,
            metric_type=metric_type,
            agreement_score=result.score,
            total_annotations=result.sample_size,
            calculation_metadata=result.metadata
        )
        db.add(agreement)
    
    db.commit()
```

### API Integration
```python
from fastapi import APIRouter
from agreement_metrics import AgreementMetricsEngine

router = APIRouter()

@router.get("/tasks/{task_id}/agreement")
async def get_task_agreement(task_id: str):
    """Get agreement metrics for a task"""
    
    # Fetch and convert annotations
    annotations = get_task_annotations(task_id)
    
    # Calculate metrics
    engine = AgreementMetricsEngine()
    results = engine.calculate_all_metrics(annotations)
    
    # Format response
    return {
        "task_id": task_id,
        "metrics": {
            metric.value: {
                "score": result.score,
                "confidence_interval": result.confidence_interval,
                "interpretation": get_interpretation(metric, result.score)
            }
            for metric, result in results.items()
        }
    }
```

## Testing

Run the comprehensive test suite:

```bash
# Run all agreement metrics tests
pytest tests/unit/test_agreement_metrics.py -v

# Run specific test class
pytest tests/unit/test_agreement_metrics.py::TestCohenKappaCalculator -v

# Run with coverage
pytest tests/unit/test_agreement_metrics.py --cov=agreement_metrics
```

## Examples

See `agreement_metrics_example.py` for complete working examples including:
- Categorical annotations
- Numerical annotations  
- Multiple annotators
- Caching usage
- Dictionary conversion
- Validation examples
- Different distance functions

## References

1. Cohen, J. (1960). A coefficient of agreement for nominal scales. *Educational and psychological measurement*, 20(1), 37-46.

2. Fleiss, J. L. (1971). Measuring nominal scale agreement among many raters. *Psychological bulletin*, 76(5), 378.

3. Krippendorff, K. (2004). Reliability in content analysis: Some common misconceptions and recommendations. *Human communication research*, 30(3), 411-433.

4. Shrout, P. E., & Fleiss, J. L. (1979). Intraclass correlations: uses in assessing rater reliability. *Psychological bulletin*, 86(2), 420.

## License

This module is part of the BenGER project and follows the same license terms.