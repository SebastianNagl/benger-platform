# Inter-Annotator Agreement (IAA) System

## Overview

The Inter-Annotator Agreement (IAA) system provides comprehensive tools for measuring, tracking, and improving annotation quality through statistical agreement metrics. This system is essential for ensuring data quality in annotation projects and achieving parity with Label Studio Enterprise.

## Features

### Agreement Metrics
- **Cohen's Kappa (κ)**: Measures agreement between two annotators, accounting for chance agreement
- **Fleiss' Kappa**: Extension of Cohen's for multiple annotators
- **Krippendorff's Alpha (α)**: Flexible metric supporting various data types and missing values
- **Percent Agreement**: Simple percentage of matching annotations
- **Pearson Correlation**: For continuous/numerical annotations
- **Spearman Correlation**: For ranked/ordinal annotations
- **Intraclass Correlation (ICC)**: For interval/ratio scale measurements

### Key Components

#### 1. Database Models
- **TaskAgreement**: Stores agreement scores for individual tasks
- **AnnotatorAgreementMatrix**: Pairwise agreement between annotators
- **AgreementThreshold**: Configurable thresholds for quality control

#### 2. Agreement Engine
The `AgreementMetricsEngine` provides:
- Automatic metric calculation
- Redis caching for performance
- Support for various data types
- Confidence intervals and p-values
- Batch processing capabilities

#### 3. Frontend Components
- **AgreementScore**: Visual display of agreement levels
- **AgreementMatrix**: Interactive heatmap of annotator pairs
- **AgreementTimeline**: Track agreement over time
- **AgreementSettings**: Configure metrics and thresholds
- **ConsensusView**: Side-by-side comparison for conflict resolution

## API Endpoints

### Get Project Agreement
```http
GET /api/agreement/projects/{project_id}
```
Returns overall agreement statistics for a project.

**Response:**
```json
{
  "overall_agreement": {
    "kappa": 0.75,
    "alpha": 0.72,
    "percent_agreement": 0.85
  },
  "metrics": [...],
  "task_count": 100,
  "annotator_count": 5
}
```

### Get Task Agreement
```http
GET /api/agreement/tasks/{task_id}
```
Returns agreement metrics for a specific task.

### Calculate Agreement
```http
POST /api/agreement/tasks/{task_id}/calculate
```
Manually trigger agreement calculation.

**Request:**
```json
{
  "metrics": ["cohen_kappa", "fleiss_kappa", "percent_agreement"]
}
```

### Set Agreement Thresholds
```http
POST /api/agreement/projects/{project_id}/thresholds
```
Configure automatic quality control thresholds.

**Request:**
```json
{
  "metric_type": "cohen_kappa",
  "threshold_low": 0.2,
  "threshold_moderate": 0.4,
  "threshold_good": 0.6,
  "action_on_low": "require_review",
  "action_on_moderate": "flag"
}
```

### Get Low Agreement Tasks
```http
GET /api/agreement/projects/{project_id}/low-agreement-tasks?threshold=0.5
```
Find tasks needing review based on agreement scores.

### Get Annotator Matrix
```http
GET /api/agreement/projects/{project_id}/matrix
```
Returns pairwise agreement between all annotators.

## Usage Examples

### Python Integration
```python
from agreement_metrics import AgreementMetricsEngine
from models import AgreementMetricType

# Initialize engine
engine = AgreementMetricsEngine(cache_client=redis_client)

# Calculate Cohen's Kappa
annotations = [
    {"annotator_id": "user1", "label": "positive"},
    {"annotator_id": "user2", "label": "positive"}
]

result = engine.calculate_metric(
    AgreementMetricType.COHEN_KAPPA,
    annotations
)

print(f"Kappa: {result.score}")
print(f"Agreement level: {result.interpretation}")
```

### React Component Usage
```tsx
import { AgreementScore, ConsensusView } from '@/components/annotations'

// Display agreement score
<AgreementScore
  score={0.75}
  metric="kappa"
  showInterpretation={true}
/>

// Show consensus interface
<ConsensusView
  items={conflictItems}
  onResolve={handleConsensus}
  onEscalate={handleEscalation}
/>
```

## Agreement Interpretation

### Cohen's Kappa & Fleiss' Kappa
- **< 0**: Poor agreement (worse than chance)
- **0.01-0.20**: Slight agreement
- **0.21-0.40**: Fair agreement
- **0.41-0.60**: Moderate agreement
- **0.61-0.80**: Substantial agreement
- **0.81-1.00**: Almost perfect agreement

### Krippendorff's Alpha
- **< 0.667**: Insufficient agreement
- **0.667-0.800**: Tentative conclusions
- **≥ 0.800**: Good reliability

### Percent Agreement
- **< 50%**: Poor
- **50-65%**: Fair
- **65-75%**: Moderate
- **75-85%**: Good
- **> 85%**: Excellent

## Quality Control Actions

When agreement falls below thresholds, the system can automatically:

1. **FLAG**: Mark task for attention
2. **REQUIRE_REVIEW**: Send to senior annotator
3. **REQUIRE_CONSENSUS**: Require annotators to discuss
4. **ADD_ANNOTATOR**: Assign additional annotator
5. **ESCALATE**: Send to project manager
6. **RETRAIN**: Flag annotator for additional training

## Performance Optimization

### Caching Strategy
- Agreement scores cached for 5 minutes
- Matrix calculations cached for 10 minutes
- Invalidated on new annotations

### Database Indexes
```sql
-- Optimized queries
CREATE INDEX ix_task_agreements_project_id ON task_agreements(project_id);
CREATE INDEX ix_task_agreements_agreement_score ON task_agreements(agreement_score);
CREATE INDEX ix_annotator_matrix_project_id ON annotator_agreement_matrix(project_id);
```

### Batch Processing
For large projects, use batch calculation:
```python
engine.calculate_project_agreement(
    project_id,
    batch_size=100,
    use_parallel=True
)
```

## Configuration

### Environment Variables
```bash
# Redis for caching
REDIS_HOST=localhost
REDIS_PORT=6379

# Agreement calculation settings
IAA_CACHE_TTL=300
IAA_BATCH_SIZE=100
IAA_PARALLEL_WORKERS=4
```

### Project Settings
```json
{
  "agreement_settings": {
    "primary_metric": "fleiss_kappa",
    "min_annotators": 2,
    "confidence_level": 0.95,
    "auto_calculate": true,
    "calculation_schedule": "*/30 * * * *"
  }
}
```

## Troubleshooting

### Common Issues

1. **Low Agreement Scores**
   - Check annotation guidelines clarity
   - Verify training consistency
   - Look for ambiguous items

2. **Calculation Errors**
   - Ensure sufficient overlapping annotations
   - Check for missing data handling
   - Verify metric appropriateness for data type

3. **Performance Issues**
   - Enable Redis caching
   - Use batch processing for large datasets
   - Optimize database queries with indexes

## Migration Guide

If upgrading from a system without IAA:

1. Run database migration:
```bash
alembic upgrade 266_add_inter_annotator_agreement
```

2. Calculate historical agreement:
```python
from scripts import backfill_agreement
backfill_agreement.run(start_date="2024-01-01")
```

3. Configure thresholds based on baseline:
```python
baseline = analyze_historical_agreement()
set_thresholds(baseline.percentile(25), baseline.median(), baseline.percentile(75))
```

## Best Practices

1. **Regular Monitoring**: Review agreement weekly
2. **Continuous Improvement**: Adjust guidelines based on disagreements
3. **Annotator Feedback**: Share agreement scores with team
4. **Consensus Building**: Use ConsensusView for conflicts
5. **Documentation**: Document resolution decisions

## Integration with Label Studio

For projects migrating from Label Studio:
- IAA metrics are compatible with Label Studio export format
- Can import Label Studio agreement history
- Supports Label Studio annotation format

## Future Enhancements

- Real-time agreement calculation
- Machine learning for disagreement prediction
- Advanced visualization options
- Integration with active learning pipelines
- Automated annotator assignment based on expertise