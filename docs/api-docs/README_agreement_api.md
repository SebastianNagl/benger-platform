# Inter-Annotator Agreement API Endpoints

This document describes the comprehensive API endpoints for the Inter-Annotator Agreement system in BenGER, providing statistical measures and management capabilities for annotation quality assessment.

## Overview

The Agreement API (`/api/agreement/`) provides REST endpoints to:
- Calculate agreement metrics between annotators
- Monitor agreement thresholds and quality
- Generate annotator agreement matrices
- Manage agreement configurations
- Get recommendations for appropriate metrics

## API Endpoints

### 1. Project Agreement Statistics

**GET** `/api/agreement/projects/{project_id}`

Get comprehensive agreement statistics for a project.

**Parameters:**
- `project_id`: Project identifier
- `metric_types` (optional): List of specific metrics to calculate
- `force_recalculate` (optional): Force recalculation instead of using cache

**Response:**
```json
{
  "project_id": "project-123",
  "task_id": "task-456", 
  "total_annotations": 150,
  "total_annotators": 3,
  "total_items": 50,
  "agreement_scores": [
    {
      "metric_type": "cohen_kappa",
      "score": 0.78,
      "confidence_interval": [0.65, 0.91],
      "p_value": 0.001,
      "standard_error": 0.06,
      "sample_size": 150,
      "agreement_level": "good",
      "metadata": {...},
      "calculated_at": "2025-01-12T10:30:00Z"
    }
  ],
  "last_updated": "2025-01-12T10:30:00Z",
  "avg_agreement_score": 0.78,
  "min_agreement_score": 0.65,
  "max_agreement_score": 0.91,
  "recommended_metrics": ["cohen_kappa", "fleiss_kappa"]
}
```

### 2. Task Agreement Score

**GET** `/api/agreement/tasks/{task_id}`

Get agreement score for a specific task.

**Parameters:**
- `task_id`: Task identifier
- `metric_type`: Agreement metric to calculate (default: cohen_kappa)

**Response:**
```json
{
  "task_id": "task-456",
  "task_name": "Legal Document Classification",
  "agreement_scores": [...],
  "total_annotations": 75,
  "total_annotators": 3,
  "items_annotated": 25,
  "coverage_percentage": 100.0,
  "last_calculation": "2025-01-12T10:30:00Z"
}
```

### 3. Annotator Agreement Matrix

**GET** `/api/agreement/projects/{project_id}/matrix`

Get pairwise agreement matrix between all annotators.

**Parameters:**
- `project_id`: Project identifier
- `metric_type`: Agreement metric for matrix calculation

**Response:**
```json
{
  "project_id": "project-123",
  "task_id": "task-456",
  "annotators": [
    {"id": "user1", "name": "John Doe"},
    {"id": "user2", "name": "Jane Smith"}
  ],
  "metric_type": "cohen_kappa",
  "agreement_matrix": [
    [1.0, 0.78],
    [0.78, 1.0]
  ],
  "pairwise_agreements": [
    {
      "annotator_1_id": "user1",
      "annotator_1_name": "John Doe", 
      "annotator_2_id": "user2",
      "annotator_2_name": "Jane Smith",
      "metric_type": "cohen_kappa",
      "agreement_score": 0.78,
      "agreement_level": "good",
      "total_annotations": 50,
      "agreeing_annotations": 39,
      "disagreement_details": {...},
      "calculated_at": "2025-01-12T10:30:00Z"
    }
  ],
  "summary_stats": {
    "mean_agreement": 0.78,
    "min_agreement": 0.65,
    "max_agreement": 0.91,
    "std_agreement": 0.08
  },
  "calculated_at": "2025-01-12T10:30:00Z"
}
```

### 4. Agreement Threshold Management

**POST** `/api/agreement/projects/{project_id}/thresholds`

Set or update agreement thresholds for a project.

**Request Body:**
```json
{
  "metric_type": "cohen_kappa",
  "threshold_low": 0.2,
  "threshold_moderate": 0.4,
  "threshold_good": 0.6,
  "action_below_low": "notify",
  "action_below_moderate": "flag",
  "is_active": true
}
```

**Response:**
```json
{
  "id": "threshold-789",
  "project_id": "project-123",
  "organization_id": "org-456",
  "metric_type": "cohen_kappa",
  "threshold_low": 0.2,
  "threshold_moderate": 0.4,
  "threshold_good": 0.6,
  "action_below_low": "notify",
  "action_below_moderate": "flag",
  "is_active": true,
  "created_by": "user-123",
  "created_at": "2025-01-12T10:30:00Z",
  "updated_at": null
}
```

### 5. Low Agreement Tasks

**GET** `/api/agreement/projects/{project_id}/low-agreement-tasks`

Get tasks with agreement below specified threshold.

**Parameters:**
- `project_id`: Project identifier
- `metric_type`: Agreement metric to check
- `threshold_level`: Threshold level ("low" or "moderate")

**Response:**
```json
[
  {
    "task_id": "task-789",
    "task_name": "Problematic Legal Analysis",
    "project_id": "project-123",
    "metric_type": "cohen_kappa",
    "agreement_score": 0.15,
    "agreement_level": "poor",
    "threshold_violated": "low",
    "total_annotations": 20,
    "annotators_involved": ["user1", "user2"],
    "flagged_at": "2025-01-12T10:30:00Z"
  }
]
```

### 6. Manual Agreement Calculation

**POST** `/api/agreement/tasks/{task_id}/calculate`

Manually trigger agreement calculation for a task.

**Request Body:**
```json
{
  "metric_types": ["cohen_kappa", "percent_agreement"],
  "force_recalculate": false,
  "include_historical": false
}
```

**Response:**
```json
{
  "task_id": "task-456",
  "calculation_started": "2025-01-12T10:30:00Z",
  "requested_metrics": ["cohen_kappa", "percent_agreement"],
  "status": "completed",
  "message": "Successfully calculated 2 agreement metrics"
}
```

### 7. Available Metric Types

**GET** `/api/agreement/metrics/types`

Get list of available agreement metrics with descriptions.

**Response:**
```json
{
  "available_metrics": [
    "cohen_kappa",
    "fleiss_kappa", 
    "percent_agreement",
    "krippendorff_alpha",
    "pearson_correlation",
    "spearman_correlation",
    "intraclass_correlation"
  ],
  "metrics_info": {
    "cohen_kappa": {
      "name": "Cohen's Kappa",
      "description": "Inter-rater agreement for two annotators on categorical data",
      "best_for": "Two annotators, categorical labels",
      "range": "[-1, 1]",
      "interpretation": {
        "< 0.2": "poor",
        "0.2-0.4": "fair",
        "0.4-0.6": "good", 
        "> 0.6": "excellent"
      }
    }
  },
  "total_metrics": 7
}
```

### 8. Metric Recommendations

**GET** `/api/agreement/projects/{project_id}/recommendations`

Get recommended metrics for a project based on annotation characteristics.

**Response:**
```json
{
  "project_id": "project-123",
  "recommended_metrics": ["cohen_kappa", "percent_agreement"],
  "reasons": [
    "Two annotators detected - Cohen's Kappa recommended",
    "Categorical data detected - Kappa metrics recommended"
  ],
  "data_characteristics": {
    "data_types": ["categorical"],
    "annotator_count": 2,
    "item_count": 50,
    "total_annotations": 100,
    "avg_annotations_per_item": 2.0
  }
}
```

### 9. System Health

**GET** `/api/agreement/health`

Health check endpoint for the agreement system.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-01-12T10:30:00Z",
  "components": {
    "redis": "connected",
    "agreement_engine": "operational",
    "available_metrics": 7
  }
}
```

## Agreement Metrics

The system supports multiple statistical agreement measures:

### 1. Cohen's Kappa
- **Use case**: Two annotators, categorical data
- **Range**: [-1, 1]
- **Interpretation**: < 0.2 poor, 0.2-0.4 fair, 0.4-0.6 good, > 0.6 excellent

### 2. Fleiss' Kappa  
- **Use case**: Multiple annotators, categorical data
- **Range**: [-1, 1] 
- **Interpretation**: Same as Cohen's Kappa

### 3. Percent Agreement
- **Use case**: Quick assessment, any number of annotators
- **Range**: [0, 1]
- **Interpretation**: < 0.6 poor, 0.6-0.8 fair, 0.8-0.9 good, > 0.9 excellent

### 4. Krippendorff's Alpha
- **Use case**: Universal measure for any data type and annotators
- **Range**: [0, 1]
- **Interpretation**: < 0.67 poor, 0.67-0.8 fair, 0.8-0.9 good, > 0.9 excellent

### 5. Pearson Correlation
- **Use case**: Numerical ratings, continuous scales
- **Range**: [-1, 1]
- **Interpretation**: < 0.3 poor, 0.3-0.5 fair, 0.5-0.7 good, > 0.7 excellent

### 6. Spearman Correlation
- **Use case**: Ordinal ratings, ranked data
- **Range**: [-1, 1]
- **Interpretation**: Same as Pearson

### 7. Intraclass Correlation (ICC)
- **Use case**: Numerical data, multiple annotators, reliability assessment
- **Range**: [0, 1]
- **Interpretation**: < 0.5 poor, 0.5-0.75 fair, 0.75-0.9 good, > 0.9 excellent

## Authentication & Authorization

All endpoints require authentication:
- **User-level endpoints**: `require_user`
- **Management endpoints**: `require_org_contributor` 
- **Admin endpoints**: `require_superadmin`

## Error Responses

Standard HTTP status codes:
- **200**: Success
- **400**: Bad Request (invalid parameters)
- **401**: Unauthorized (authentication required)
- **403**: Forbidden (insufficient permissions) 
- **404**: Not Found (resource doesn't exist)
- **500**: Internal Server Error

## Integration

The Agreement API integrates with:
- **Native Annotation System**: Automatic calculation for annotation projects
- **Redis Cache**: Performance optimization for expensive calculations
- **Database Models**: `TaskAgreement`, `AnnotatorAgreementMatrix`, `AgreementThreshold`
- **Agreement Metrics Engine**: Mathematical calculations and statistical measures

## Usage Examples

### Calculate Cohen's Kappa for a project:
```bash
curl -X GET \
  "http://localhost:8000/api/agreement/projects/project-123?metric_types=cohen_kappa" \
  -H "Authorization: Bearer $TOKEN"
```

### Set agreement thresholds:
```bash
curl -X POST \
  "http://localhost:8000/api/agreement/projects/project-123/thresholds" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "metric_type": "cohen_kappa",
    "threshold_low": 0.2,
    "threshold_moderate": 0.4,
    "threshold_good": 0.6,
    "action_below_low": "notify",
    "action_below_moderate": "flag"
  }'
```

### Get annotator agreement matrix:
```bash
curl -X GET \
  "http://localhost:8000/api/agreement/projects/project-123/matrix?metric_type=cohen_kappa" \
  -H "Authorization: Bearer $TOKEN"
```

This comprehensive API provides all the tools needed for monitoring and managing inter-annotator agreement in BenGER's annotation system.