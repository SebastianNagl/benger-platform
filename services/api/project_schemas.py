"""
Pydantic schemas for Clean architecture API

These schemas define the request/response models for the new project-based API
that follows Label Studio patterns while preserving BenGER's LLM features.
"""

from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, TypeVar, Union

from pydantic import BaseModel, Field, field_validator, model_validator

T = TypeVar("T")


# ============= Prompt Structure Schemas (Issue #762) =============


class PromptStructureBase(BaseModel):
    """Base schema for prompt structure definition

    Validation Rules:
    - name: 1-255 characters, required
    - description: optional text
    - system_prompt: required string or dict template
    - instruction_prompt: required string or dict template
    - evaluation_prompt: optional string or dict template
    - judge_*: optional fields for LLM-as-Judge evaluation
    - Prompts cannot be empty strings
    - Template dicts must be valid JSON objects
    """

    name: str = Field(
        ..., min_length=1, max_length=255, description="Display name for the structure"
    )
    description: Optional[str] = Field(
        None, description="Description of what this structure is used for"
    )
    system_prompt: Union[str, Dict[str, Any]] = Field(
        ..., description="System prompt (string or template)"
    )
    instruction_prompt: Union[str, Dict[str, Any]] = Field(
        ..., description="Instruction prompt (string or template)"
    )
    evaluation_prompt: Optional[Union[str, Dict[str, Any]]] = Field(
        None, description="Optional evaluation prompt"
    )
    # LLM-as-Judge specific fields
    judge_system_prompt: Optional[str] = Field(
        None,
        description="System prompt for LLM judge. Supports {criterion}, {rubric} variables",
    )
    judge_instruction_prompt: Optional[str] = Field(
        None,
        description="Instruction prompt for LLM judge. Supports {candidate}, {reference}, {criterion} variables",
    )
    judge_criteria: Optional[List[str]] = Field(
        None,
        description="List of criteria to evaluate when using this prompt structure",
    )

    @field_validator('system_prompt', 'instruction_prompt', 'evaluation_prompt')
    @classmethod
    def validate_prompt_structure(cls, v, info):
        """Validate that prompt is either string or dict with required fields"""
        if v is None:
            # evaluation_prompt is optional
            if info.field_name == 'evaluation_prompt':
                return v
            raise ValueError(f"{info.field_name} is required")

        if isinstance(v, str):
            # Don't allow empty strings
            if not v.strip():
                raise ValueError(f"{info.field_name} cannot be empty")
            return v

        if isinstance(v, dict):
            # If it's a template dict, validate it has the required fields
            # This is a basic validation - actual template validation happens in parser
            if not v:
                raise ValueError(f"{info.field_name} cannot be an empty dictionary")
            return v

        raise ValueError(f"{info.field_name} must be either a string or a dictionary")


class PromptStructureCreate(PromptStructureBase):
    """Schema for creating a new prompt structure"""


class PromptStructureUpdate(BaseModel):
    """Schema for updating an existing prompt structure"""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    system_prompt: Optional[Union[str, Dict[str, Any]]] = None
    instruction_prompt: Optional[Union[str, Dict[str, Any]]] = None
    evaluation_prompt: Optional[Union[str, Dict[str, Any]]] = None
    # LLM-as-Judge specific fields
    judge_system_prompt: Optional[str] = None
    judge_instruction_prompt: Optional[str] = None
    judge_criteria: Optional[List[str]] = None


class PromptStructureResponse(PromptStructureBase):
    """Schema for prompt structure responses"""

    key: str = Field(..., description="Unique key for this structure within the project")


class GenerationConfigStructures(BaseModel):
    """Schema for generation_config with prompt structures support"""

    selected_configuration: Dict[str, Any] = Field(
        default_factory=dict,
        description="Currently selected configuration with models and active_structures",
    )
    prompt_structures: Dict[str, PromptStructureBase] = Field(
        default_factory=dict, description="Map of structure_key to prompt structure definitions"
    )

    @field_validator('selected_configuration')
    @classmethod
    def validate_selected_config(cls, v):
        """Ensure selected_configuration has required fields"""
        if not v:
            return {"models": [], "active_structures": []}
        if "models" not in v:
            v["models"] = []
        if "active_structures" not in v:
            v["active_structures"] = []
        return v


# Project schemas
class ProjectBase(BaseModel):
    """Base project schema"""

    title: str = Field(..., min_length=1, max_length=255, description="Project title")
    description: Optional[str] = Field(None, description="Project description")
    label_config: Optional[str] = Field(
        None, description="Label Studio XML/JSON config for annotation interface"
    )
    # Note: generation_structure removed in Issue #762 - now in generation_config.prompt_structures
    expert_instruction: Optional[str] = Field(None, description="Instructions for annotators")
    show_instruction: bool = Field(True, description="Show instructions to annotators")
    instructions_always_visible: bool = Field(False, description="Override 'don't show again' and always show instructions")
    show_skip_button: bool = Field(True, description="Allow annotators to skip tasks")
    enable_empty_annotation: bool = Field(True, description="Allow empty annotations")
    show_annotation_history: bool = Field(False, description="Show annotation history")


class ProjectCreate(ProjectBase):
    """Schema for creating a project"""

    is_private: bool = Field(
        False, description="Whether this is a private project (not assigned to any organization)"
    )


class ProjectUpdate(BaseModel):
    """Schema for updating a project"""

    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    label_config: Optional[str] = None
    # Note: generation_structure removed in Issue #762 - now in generation_config.prompt_structures
    expert_instruction: Optional[str] = None
    instructions: Optional[str] = None  # Alias for expert_instruction
    show_instruction: Optional[bool] = None
    instructions_always_visible: Optional[bool] = None
    conditional_instructions: Optional[List[Dict[str, Any]]] = Field(
        None, description="Conditional instruction variants [{id, content, weight}]"
    )
    show_skip_button: Optional[bool] = None
    show_submit_button: Optional[bool] = None  # Frontend field
    require_comment_on_skip: Optional[bool] = None  # Frontend field
    require_confirm_before_submit: Optional[bool] = None  # Frontend field
    skip_queue: Optional[str] = Field(None, pattern="^(requeue_for_me|requeue_for_others|ignore_skipped)$", description="Skip behavior: requeue_for_me, requeue_for_others, ignore_skipped")
    # Post-annotation questionnaire (Issue #1208)
    questionnaire_enabled: Optional[bool] = Field(
        None, description="Show post-annotation questionnaire after submission"
    )
    questionnaire_config: Optional[str] = Field(
        None, description="Label Studio XML config for post-annotation questionnaire"
    )
    enable_empty_annotation: Optional[bool] = None
    show_annotation_history: Optional[bool] = None
    # Note: color and sampling fields removed in migration 95726e4be27e
    maximum_annotations: Optional[int] = None
    min_annotations_per_task: Optional[int] = Field(
        None, ge=1, description="Minimum annotations required per task"
    )
    llm_model_ids: Optional[List[str]] = Field(
        None,
        description="DEPRECATED: Use generation_config instead. List of LLM model IDs for generation",
    )
    generation_config: Optional[Dict[str, Any]] = Field(
        None, description="Generation configuration including model selection"
    )
    evaluation_config: Optional[Dict[str, Any]] = Field(
        None, description="Evaluation configuration with selected methods and parameters"
    )
    is_published: Optional[bool] = None
    is_archived: Optional[bool] = None
    # Extended feature flags
    annotation_time_limit_enabled: Optional[bool] = None
    annotation_time_limit_seconds: Optional[int] = None
    strict_timer_enabled: Optional[bool] = None
    review_enabled: Optional[bool] = None
    review_mode: Optional[str] = None
    allow_self_review: Optional[bool] = None
    feedback_enabled: Optional[bool] = None
    feedback_config: Optional[List[Dict[str, Any]]] = None
    immediate_evaluation_enabled: Optional[bool] = None

    # Task assignment
    assignment_mode: Optional[str] = Field(
        None, pattern="^(open|manual|auto)$",
        description="Task assignment mode: open, manual, or auto"
    )
    # Task ordering
    randomize_task_order: Optional[bool] = Field(
        None, description="Randomize task order per user for even annotation distribution"
    )
    @field_validator("conditional_instructions")
    @classmethod
    def validate_conditional_instructions(cls, v):
        """Validate conditional instruction variants have required fields."""
        if v is None:
            return v
        if not isinstance(v, list):
            raise ValueError("conditional_instructions must be a list")
        seen_ids = set()
        for i, variant in enumerate(v):
            if not isinstance(variant, dict):
                raise ValueError(f"Variant {i} must be an object")
            vid = variant.get("id")
            if not vid or not isinstance(vid, str) or not vid.strip():
                raise ValueError(f"Variant {i} must have a non-empty string 'id'")
            if vid in seen_ids:
                raise ValueError(f"Duplicate variant id: {vid}")
            seen_ids.add(vid)
            content = variant.get("content")
            if not content or not isinstance(content, str) or not content.strip():
                raise ValueError(f"Variant {i} must have a non-empty string 'content'")
            weight = variant.get("weight")
            if weight is None or not isinstance(weight, (int, float)) or weight <= 0:
                raise ValueError(f"Variant {i} must have a positive numeric 'weight'")
            ai_allowed = variant.get("ai_allowed")
            if ai_allowed is not None and not isinstance(ai_allowed, bool):
                raise ValueError(f"Variant {i} 'ai_allowed' must be a boolean")
        return v



class ProjectResponse(ProjectBase):
    """Schema for project responses"""

    id: str
    created_by: str
    created_by_name: Optional[str] = None
    organization_id: Optional[str] = None  # Deprecated: use organizations instead
    organization: Optional[Dict[str, Any]] = None  # Legacy: primary organization
    organizations: Optional[List[Dict[str, Any]]] = None  # New: all assigned organizations
    task_count: int = 0
    annotation_count: int = 0
    min_annotations_per_task: int = 1
    completed_tasks_count: int = 0
    progress_percentage: float = 0.0
    is_private: bool = False
    is_published: bool = False
    is_archived: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None

    # Additional fields not in ProjectBase
    instructions: Optional[str] = None  # Mapped from expert_instruction
    # Note: color and sampling fields removed in migration 95726e4be27e
    maximum_annotations: int = 1
    show_submit_button: bool = True
    require_comment_on_skip: bool = False
    require_confirm_before_submit: bool = False
    skip_queue: str = "requeue_for_others"
    # Post-annotation questionnaire (Issue #1208)
    questionnaire_enabled: bool = False
    questionnaire_config: Optional[str] = None
    conditional_instructions: Optional[List[Dict[str, Any]]] = None
    llm_model_ids: Optional[List[str]] = Field(
        None, description="List of LLM model IDs for generation"
    )
    evaluation_config: Optional[Dict[str, Any]] = Field(
        None, description="Evaluation configuration with selected methods"
    )
    generation_config: Optional[Dict[str, Any]] = Field(
        None, description="Generation configuration including model selection"
    )

    # Extended feature flags (DB columns with defaults, used by extended package)
    annotation_time_limit_enabled: bool = False
    annotation_time_limit_seconds: Optional[int] = None
    strict_timer_enabled: bool = False
    review_enabled: bool = False
    review_mode: Optional[str] = "in_place"
    allow_self_review: bool = False
    feedback_enabled: bool = False
    feedback_config: Optional[List[Dict[str, Any]]] = None
    immediate_evaluation_enabled: bool = False

    # Task assignment
    assignment_mode: str = "open"

    # Task ordering
    randomize_task_order: bool = False

    # Compatibility fields
    num_tasks: Optional[int] = None
    num_annotations: Optional[int] = None

    # Generation-related fields for /generation page
    generation_prompts_ready: bool = False
    generation_config_ready: bool = False
    generation_models_count: int = 0
    generation_completed: bool = False

    class Config:
        from_attributes = True

    @classmethod
    def from_orm(cls, obj):
        # Convert SQLAlchemy object to dict with custom mappings
        data = {}

        # Copy basic fields
        for field_name in cls.__fields__:
            if hasattr(obj, field_name):
                # Skip organizations field - it will be handled separately
                if field_name == "organizations":
                    continue
                value = getattr(obj, field_name)
                if value is not None:
                    data[field_name] = value

        # Handle special mappings
        data["instructions"] = getattr(obj, "expert_instruction", "") or ""
        data["num_tasks"] = getattr(obj, "task_count", 0)
        data["num_annotations"] = getattr(obj, "annotation_count", 0)

        # Note: progress_percentage is calculated in the API endpoints after
        # task_count and completed_tasks_count are fetched from the database

        # Handle organization relationship
        if hasattr(obj, "organization") and obj.organization:
            data["organization"] = {
                "id": obj.organization.id,
                "name": obj.organization.name,
            }
        else:
            data["organization"] = None

        # Handle organizations relationship (many-to-many)
        if hasattr(obj, "organizations") and obj.organizations:
            data["organizations"] = [
                {
                    "id": org.id,
                    "name": org.name,
                }
                for org in obj.organizations
            ]
        else:
            data["organizations"] = None

        # Calculate generation_models_count from generation_config (single source of truth)
        generation_config = getattr(obj, "generation_config", None)
        if generation_config and isinstance(generation_config, dict):
            selected_config = generation_config.get("selected_configuration", {})
            models = selected_config.get("models", [])
            if models and isinstance(models, list):
                data["generation_models_count"] = len(models)
            else:
                data["generation_models_count"] = 0
        else:
            data["generation_models_count"] = 0

        return cls(**data)


# Task schemas
class TaskBase(BaseModel):
    """Base task schema"""

    data: Dict[str, Any] = Field(..., description="Task data (flexible JSON)")
    meta: Optional[Dict[str, Any]] = Field(None, description="Task metadata")


class TaskCreate(TaskBase):
    """Schema for creating a task"""


class TaskUpdate(BaseModel):
    """Schema for updating a task"""

    data: Optional[Dict[str, Any]] = None
    meta: Optional[Dict[str, Any]] = None


class TaskResponse(TaskBase):
    """Schema for task responses"""

    id: str
    project_id: str
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    is_labeled: bool = False
    total_annotations: int = 0
    cancelled_annotations: int = 0
    total_generations: int = 0  # Calculated from Generation table, not stored
    comment_count: int = 0
    unresolved_comment_count: int = 0
    last_comment_updated_at: Optional[datetime] = None
    comment_authors: Optional[Dict[str, Any]] = None
    file_upload_id: Optional[str] = None
    inner_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Annotation schemas
class AnnotationBase(BaseModel):
    """Base annotation schema"""

    result: List[Dict[str, Any]] = Field(
        ..., description="Annotation result in Label Studio format"
    )
    draft: Optional[List[Dict[str, Any]]] = Field(None, description="Draft annotation data")
    was_cancelled: bool = Field(False, description="Whether annotation was cancelled")
    lead_time: Optional[float] = Field(None, description="Time taken to complete (seconds)")


class AnnotationCreate(AnnotationBase):
    """Schema for creating an annotation"""

    # Enhanced timing (Issue #1208)
    active_duration_ms: Optional[int] = Field(
        None, description="Time in ms when browser tab was visible"
    )
    focused_duration_ms: Optional[int] = Field(
        None, description="Time in ms with active user interaction"
    )
    tab_switches: Optional[int] = Field(
        None, ge=0, description="Number of tab visibility changes"
    )
    instruction_variant: Optional[str] = Field(
        None, description="ID of the instruction variant shown to the annotator"
    )
    ai_assisted: Optional[bool] = Field(
        False, description="Whether the annotator was allowed AI assistance (derived server-side from instruction variant)"
    )


class AnnotationUpdate(BaseModel):
    """Schema for updating an annotation"""

    result: Optional[List[Dict[str, Any]]] = None
    draft: Optional[List[Dict[str, Any]]] = None
    ground_truth: Optional[bool] = None


class AnnotationResponse(AnnotationBase):
    """Schema for annotation responses"""

    id: str
    task_id: str  # Changed to string to match database schema
    project_id: str
    completed_by: str
    ground_truth: bool = False
    prediction_scores: Optional[Dict[str, float]] = None
    # Enhanced timing (Issue #1208)
    active_duration_ms: Optional[int] = None
    focused_duration_ms: Optional[int] = None
    tab_switches: int = 0
    instruction_variant: Optional[str] = None
    ai_assisted: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Post-annotation questionnaire schemas (Issue #1208)
class PostAnnotationResponseCreate(BaseModel):
    """Schema for submitting a post-annotation questionnaire response"""

    annotation_id: str = Field(..., description="ID of the annotation this response belongs to")
    result: List[Dict[str, Any]] = Field(
        ..., description="Questionnaire result in Label Studio format"
    )


class PostAnnotationResponseOut(BaseModel):
    """Schema for post-annotation questionnaire response"""

    id: str
    annotation_id: str
    task_id: str
    project_id: str
    user_id: str
    result: List[Dict[str, Any]]
    created_at: datetime

    class Config:
        from_attributes = True


# Review/Feedback schemas (used by extended package routers)
class ReviewSubmit(BaseModel):
    """Schema for submitting a review action"""

    action: str = Field(..., description="Review action: approve, fix, reject, independent")
    result: Optional[List[Dict[str, Any]]] = Field(
        None, description="Updated/independent annotation result"
    )
    comment: Optional[str] = Field(None, description="Reviewer feedback comment")


class ReviewResponse(BaseModel):
    """Schema for review action response"""

    annotation_id: str
    review_result: str
    reviewed_by: str
    reviewed_at: datetime
    review_comment: Optional[str] = None

    class Config:
        from_attributes = True


class ReviewPendingItem(BaseModel):
    """Schema for an annotation pending review"""

    annotation: AnnotationResponse
    task: TaskResponse


class FeedbackCommentCreate(BaseModel):
    """Schema for creating a feedback comment"""

    target_type: str = Field(..., description="Target type: annotation, generation, or evaluation")
    target_id: str = Field(..., description="ID of the target entity")
    parent_id: Optional[str] = Field(None, description="Parent comment ID for replies")
    text: str = Field(..., description="Comment text")
    highlight_start: Optional[int] = Field(None, description="Highlight start offset")
    highlight_end: Optional[int] = Field(None, description="Highlight end offset")
    highlight_text: Optional[str] = Field(None, description="Selected text content")
    highlight_label: Optional[str] = Field(None, description="Highlight label")

    @field_validator("target_type")
    @classmethod
    def validate_target_type(cls, v):
        if v not in ("annotation", "generation", "evaluation"):
            raise ValueError("target_type must be annotation, generation, or evaluation")
        return v


class FeedbackCommentUpdate(BaseModel):
    """Schema for updating a feedback comment"""

    text: str = Field(..., description="Updated comment text")


class FeedbackCommentResponse(BaseModel):
    """Schema for feedback comment response"""

    id: str
    project_id: str
    task_id: str
    target_type: str
    target_id: str
    parent_id: Optional[str] = None
    text: str
    highlight_start: Optional[int] = None
    highlight_end: Optional[int] = None
    highlight_text: Optional[str] = None
    highlight_label: Optional[str] = None
    is_resolved: bool = False
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    created_by: str
    created_by_name: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    replies: List["FeedbackCommentResponse"] = []

    class Config:
        from_attributes = True


class FeedbackStats(BaseModel):
    """Schema for feedback statistics"""

    total_tasks: int
    tasks_with_feedback: int
    tasks_without_feedback: int
    total_comments: int
    unresolved_comments: int
    feedback_enabled: bool


class FeedbackPendingItem(BaseModel):
    """Schema for a task in the feedback list"""

    task: TaskResponse
    annotation_count: int = 0
    generation_count: int = 0
    evaluation_count: int = 0
    feedback_count: int = 0
    unresolved_feedback_count: int = 0


class FeedbackTaskDetail(BaseModel):
    """Schema for full task data in feedback view"""

    task: TaskResponse
    annotations: List[Dict[str, Any]] = []
    generations: List[Dict[str, Any]] = []
    evaluations: List[Dict[str, Any]] = []
    feedback_config: Optional[List[Dict[str, Any]]] = None
    annotator_name: Optional[str] = None


# Import/Export schemas
class ProjectImportData(BaseModel):
    """Schema for importing basic task data into a project"""

    data: List[Dict[str, Any]] = Field(..., description="List of data items to import")
    meta: Optional[Dict[str, Any]] = Field(None, description="Metadata for all imported items")
    evaluation_runs: Optional[List[Dict[str, Any]]] = Field(
        None, description="Evaluation run records for roundtrip import"
    )


class ComprehensiveProjectExport(BaseModel):
    """Schema for comprehensive round-trip project export"""

    format_version: str = Field(default="2.0.0", description="Export format version")
    exported_at: str = Field(..., description="Export timestamp")
    exported_by: str = Field(..., description="User who exported")

    # Core project data
    project: Dict[str, Any] = Field(..., description="Project configuration and metadata")
    tasks: List[Dict[str, Any]] = Field(default=[], description="All project tasks")
    annotations: List[Dict[str, Any]] = Field(default=[], description="All annotations")
    generations: List[Dict[str, Any]] = Field(default=[], description="All LLM generations")
    predictions: List[Dict[str, Any]] = Field(default=[], description="All ML predictions")

    # Configuration data
    prompts: List[Dict[str, Any]] = Field(default=[], description="Task prompts")
    response_generations: List[Dict[str, Any]] = Field(default=[], description="Generation jobs")

    # User and assignment data
    project_members: List[Dict[str, Any]] = Field(default=[], description="Project memberships")
    task_assignments: List[Dict[str, Any]] = Field(default=[], description="Task assignments")
    users: List[Dict[str, Any]] = Field(default=[], description="User references for import")

    # Statistics
    statistics: Dict[str, Any] = Field(default={}, description="Export statistics")


class ComprehensiveProjectImport(BaseModel):
    """Schema for comprehensive round-trip project import"""

    # Import data (same structure as export)
    export_data: ComprehensiveProjectExport = Field(..., description="Exported project data")

    # Import options
    import_options: Dict[str, Any] = Field(default={}, description="Import configuration")
    user_mappings: Optional[Dict[str, str]] = Field(
        None, description="Map old user IDs to new user IDs"
    )
    conflict_resolution: Dict[str, str] = Field(default={}, description="How to handle conflicts")
    preserve_timestamps: bool = Field(True, description="Keep original timestamps")
    preserve_user_assignments: bool = Field(
        True, description="Keep user assignments if users exist"
    )


class ProjectExportRequest(BaseModel):
    """Schema for export requests"""

    format: str = Field(..., description="Export format: json, csv, tsv, coco, conll")
    download: bool = Field(True, description="Download as file")
    filters: Optional[Dict[str, Any]] = Field(None, description="Export filters")
    include_annotations: bool = Field(True, description="Include annotations")
    include_predictions: bool = Field(False, description="Include predictions")


# LLM specific schemas (BenGER features)
class LLMGenerationRequest(BaseModel):
    """Schema for LLM generation requests"""

    model_ids: Optional[List[str]] = Field(
        None, description="Models to use (overrides project config)"
    )
    prompt_template: Optional[str] = Field(None, description="Custom prompt template")
    temperature: float = Field(0.7, ge=0.0, le=2.0, description="Generation temperature")
    max_tokens: Optional[int] = Field(None, ge=1, le=8192, description="Maximum tokens")
    task_ids: Optional[List[int]] = Field(None, description="Specific tasks (default: all)")


class LLMEvaluationRequest(BaseModel):
    """Schema for LLM evaluation requests"""

    evaluation_types: List[str] = Field(..., description="Evaluation methods to apply")
    include_human_annotations: bool = Field(True, description="Include human annotations")
    include_llm_responses: bool = Field(True, description="Include LLM responses")


# Pagination response
class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response"""

    items: List[T]
    total: int
    page: int
    page_size: int
    pages: int


# Label configuration helpers
class LabelConfigField(BaseModel):
    """Schema for label config field definition"""

    name: str = Field(..., description="Field name")
    type: str = Field(..., description="Field type: Text, TextArea, Choices, etc.")
    to_name: Optional[str] = Field(None, description="Target field name")
    required: bool = Field(False, description="Is field required")
    placeholder: Optional[str] = Field(None, description="Placeholder text")
    choices: Optional[List[str]] = Field(None, description="Choices for Choices field")
    rows: Optional[int] = Field(None, description="Rows for TextArea")


class LabelConfigTemplate(BaseModel):
    """Schema for label configuration templates"""

    name: str = Field(..., description="Template name")
    description: Optional[str] = Field(None, description="Template description")
    config: str = Field(..., description="Label Studio XML config")
    task_type: str = Field(..., description="Task type this template is for")
    is_default: bool = Field(False, description="Is default for task type")


# Skip task schemas
class SkipTaskRequest(BaseModel):
    """Schema for skipping a task with optional comment"""

    comment: Optional[str] = Field(None, description="Optional reason for skipping")


class SkipTaskResponse(BaseModel):
    """Schema for skip task response"""

    id: str = Field(..., description="Skip record ID")
    task_id: str = Field(..., description="Task ID that was skipped")
    project_id: str = Field(..., description="Project ID")
    skipped_by: str = Field(..., description="User who skipped the task")
    comment: Optional[str] = Field(None, description="Skip comment if provided")
    skipped_at: datetime = Field(..., description="When task was skipped")

    class Config:
        from_attributes = True
