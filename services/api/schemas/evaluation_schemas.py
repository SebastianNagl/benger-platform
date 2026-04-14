"""
Pydantic schemas for evaluation system

Issue #763: Per-sample evaluation results and visualization dashboard
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SampleEvaluationResult(BaseModel):
    """Schema for individual sample evaluation result"""

    id: str
    evaluation_id: str
    task_id: str
    generation_id: Optional[str] = None

    field_name: str
    answer_type: str

    ground_truth: Dict[str, Any]
    prediction: Dict[str, Any]

    metrics: Dict[str, float]

    passed: bool
    confidence_score: Optional[float] = None

    error_message: Optional[str] = None
    processing_time_ms: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class SampleEvaluationResultCreate(BaseModel):
    """Schema for creating a sample evaluation result"""

    evaluation_id: str
    task_id: str
    generation_id: Optional[str] = None

    field_name: str
    answer_type: str

    ground_truth: Dict[str, Any]
    prediction: Dict[str, Any]

    metrics: Dict[str, float]

    passed: bool
    confidence_score: Optional[float] = None

    error_message: Optional[str] = None
    processing_time_ms: Optional[int] = None


class SampleEvaluationListResponse(BaseModel):
    """Paginated list of sample evaluation results"""

    items: List[SampleEvaluationResult]
    total: int
    page: int
    page_size: int
    has_next: bool


class MetricDistribution(BaseModel):
    """Distribution statistics for a metric"""

    metric_name: str
    mean: float
    median: float
    std: float
    min: float
    max: float
    quartiles: Dict[str, float]  # q1, q2 (median), q3
    histogram: Dict[str, int]  # bucket -> count


class ConfusionMatrix(BaseModel):
    """Confusion matrix for classification metrics"""

    field_name: str
    labels: List[str]
    matrix: List[List[int]]
    accuracy: float
    precision_per_class: Dict[str, float]
    recall_per_class: Dict[str, float]
    f1_per_class: Dict[str, float]


class EvaluationSummary(BaseModel):
    """Summary statistics for an evaluation"""

    evaluation_id: str
    project_id: str
    model_id: str

    total_samples: int
    passed_samples: int
    failed_samples: int
    pass_rate: float

    # Aggregate metrics
    aggregate_metrics: Dict[str, float]

    # Per-field metrics
    field_metrics: Dict[str, Dict[str, float]]

    # Answer type distribution
    answer_types: Dict[str, int]

    # Execution statistics
    total_processing_time_ms: int
    avg_processing_time_ms: float

    created_at: datetime
    completed_at: Optional[datetime]


class ModelComparisonMetrics(BaseModel):
    """Metrics for comparing multiple models"""

    project_id: str
    field_name: str
    metric_name: str

    models: List[str]
    values: List[float]

    # Statistical comparison
    best_model: str
    worst_model: str
    mean: float
    std: float


class ConfigValidationResult(BaseModel):
    """Result of validating generation_config and evaluation_config alignment"""

    valid: bool
    errors: List[str] = []
    warnings: List[str] = []

    # Field mapping validation
    generation_fields: List[str]
    evaluation_fields: List[str]
    matched_fields: List[str]
    missing_in_evaluation: List[str]
    missing_in_generation: List[str]


class EvaluationFilterParams(BaseModel):
    """Parameters for filtering evaluation results"""

    field_name: Optional[str] = None
    passed: Optional[bool] = None
    min_confidence: Optional[float] = None
    answer_type: Optional[str] = None
    metric_threshold: Optional[Dict[str, float]] = None  # metric_name -> threshold


class ExportFormat(BaseModel):
    """Export configuration"""

    format: str = Field(..., description="Export format: json, csv, pdf")
    include_sample_details: bool = Field(True, description="Include per-sample results")
    include_visualizations: bool = Field(False, description="Include chart images (PDF only)")
    fields: Optional[List[str]] = Field(None, description="Specific fields to export")
