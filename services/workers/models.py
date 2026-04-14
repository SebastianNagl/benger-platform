"""
Database models for BenGER API
"""

import os
from enum import Enum

import sqlalchemy as sa
from sqlalchemy import JSON, Boolean, Column, DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import Float, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

# Handle SQLite compatibility for testing
if "sqlite" in os.environ.get("DATABASE_URL", "sqlite:///:memory:").lower():
    from sqlalchemy import JSON as JSONB
else:
    from sqlalchemy.dialects.postgresql import JSONB

from database import Base

# Import Task, Project, Annotation models so SQLAlchemy can resolve foreign keys
from project_models import Annotation, Project, Task  # noqa: F401

# Association table for many-to-many relationship between Task and EvaluationType
task_evaluation_methods_table = Table(
    "task_evaluation_methods",
    Base.metadata,
    Column(
        "task_id",
        String,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "evaluation_type_id",
        String,
        ForeignKey("evaluation_types.id"),
        primary_key=True,
    ),
)

# Association table for many-to-many relationship between Task and LLMModel
task_llm_models_table = Table(
    "task_llm_models",
    Base.metadata,
    Column(
        "task_id",
        String,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "llm_model_id",
        String,
        ForeignKey("llm_models.id"),
        primary_key=True,
    ),
)

# Association table for many-to-many relationship between Task and Organization
task_organizations_table = Table(
    "task_organizations",
    Base.metadata,
    Column(
        "task_id",
        String,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "organization_id",
        String,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


# UserRole enum removed - replaced with is_superadmin boolean flag


class OrganizationRole(str, Enum):
    """User roles within an organization - standardized across all organizations"""

    ORG_ADMIN = "ORG_ADMIN"  # Can manage organization and invite users
    CONTRIBUTOR = "CONTRIBUTOR"  # Can create and manage tasks
    ANNOTATOR = "ANNOTATOR"  # Can annotate tasks


class TaskVisibility(str, Enum):
    """Task visibility options"""

    PUBLIC = "public"
    PRIVATE = "private"


class User(Base):
    """User database model"""

    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_superadmin = Column(Boolean, default=False, nullable=False)  # Global admin flag

    # default_organization_id removed - users can be in multiple orgs with different roles
    is_active = Column(Boolean, default=True, nullable=False)

    # User-provided API keys (encrypted)
    encrypted_openai_api_key = Column(Text, nullable=True)
    encrypted_anthropic_api_key = Column(Text, nullable=True)
    encrypted_google_api_key = Column(Text, nullable=True)
    encrypted_deepinfra_api_key = Column(Text, nullable=True)

    # Notification preferences (timezone only)
    timezone = Column(
        String, nullable=True, default="UTC"
    )  # User's timezone (e.g., "America/New_York")

    # NOTE: Quiet hours and email digest features have been removed
    # These fields are kept commented for potential future use:
    # quiet_hours_start = Column(String, nullable=True)
    # quiet_hours_end = Column(String, nullable=True)
    # enable_quiet_hours = Column(Boolean, default=False, nullable=False)
    # enable_email_digest = Column(Boolean, default=False, nullable=False)
    # digest_frequency = Column(String, nullable=True, default="daily")
    # digest_time = Column(String, nullable=True, default="09:00")
    # digest_days = Column(String, nullable=True)
    # last_digest_sent = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    # created_tasks relationship removed - Task model now comes from API's project_models
    organization_memberships = relationship("OrganizationMembership", back_populates="user")
    sent_invitations = relationship("Invitation", back_populates="inviter")
    # Note: ignored_enterprise_projects relationship removed in migration 411540fa6c40

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username}, email={self.email})>"


class RefreshToken(Base):
    """Refresh token model for persistent authentication"""

    __tablename__ = "refresh_tokens"

    id = Column(String, primary_key=True, index=True)
    token_hash = Column(String, nullable=False, unique=True, index=True)  # Hashed refresh token
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    user_agent = Column(String, nullable=True)  # Browser/device identification
    ip_address = Column(String, nullable=True)  # IP address for security tracking

    # Relationships
    user = relationship("User", backref="refresh_tokens")

    def __repr__(self):
        return f"<RefreshToken(id={self.id}, user_id={self.user_id}, expires_at={self.expires_at}, is_active={self.is_active})>"


class Organization(Base):
    """Organization database model for multi-tenant structure"""

    __tablename__ = "organizations"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, index=True, nullable=False)  # URL-friendly identifier
    description = Column(Text, nullable=True)
    settings = Column(JSON, nullable=True, default={})  # Organization-specific configuration
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    memberships = relationship("OrganizationMembership", back_populates="organization")
    invitations = relationship("Invitation", back_populates="organization")
    # tasks relationship now handled via many-to-many backref

    def __repr__(self):
        return f"<Organization(id={self.id}, name={self.name}, slug={self.slug})>"


class OrganizationMembership(Base):
    """User membership in organizations with role-based access"""

    __tablename__ = "organization_memberships"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False)
    role = Column(SQLEnum(OrganizationRole), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    joined_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="organization_memberships")
    organization = relationship("Organization", back_populates="memberships")

    # Unique constraint to prevent duplicate memberships
    __table_args__ = (
        sa.UniqueConstraint("user_id", "organization_id", name="unique_user_organization"),
    )

    def __repr__(self):
        return f"<OrganizationMembership(user_id={self.user_id}, org_id={self.organization_id}, role={self.role})>"


class OrganizationApiKey(Base):
    """Encrypted API keys stored at the organization level (Issue #1180)"""

    __tablename__ = "organization_api_keys"

    id = Column(String, primary_key=True, index=True)
    organization_id = Column(
        String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider = Column(String, nullable=False)
    encrypted_key = Column(Text, nullable=False)
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    organization = relationship("Organization")

    __table_args__ = (
        sa.UniqueConstraint("organization_id", "provider", name="unique_org_provider_key"),
    )

    def __repr__(self):
        return f"<OrganizationApiKey(id={self.id}, org_id={self.organization_id}, provider={self.provider})>"


class Invitation(Base):
    """Organization invitation system for user onboarding"""

    __tablename__ = "invitations"

    id = Column(String, primary_key=True, index=True)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False)
    email = Column(String, nullable=False)
    role = Column(SQLEnum(OrganizationRole), nullable=False)
    token = Column(String, unique=True, index=True, nullable=False)  # Secure invitation token
    invited_by = Column(String, ForeignKey("users.id"), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    is_accepted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    organization = relationship("Organization", back_populates="invitations")
    inviter = relationship("User", back_populates="sent_invitations")

    def __repr__(self):
        return f"<Invitation(id={self.id}, email={self.email}, org_id={self.organization_id}, role={self.role})>"


class EvaluationType(Base):
    """Evaluation type definitions stored in database"""

    __tablename__ = "evaluation_types"

    # e.g., "accuracy", "f1", "bleu"
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)  # Human-readable name
    description = Column(Text, nullable=True)  # Description of the metric
    category = Column(String, nullable=False)  # e.g., "classification", "generation", "similarity"
    higher_is_better = Column(
        Boolean, default=True, nullable=False
    )  # Whether higher values are better
    value_range = Column(JSON, nullable=True)  # {"min": 0, "max": 1} or null for unbounded
    applicable_task_types = Column(
        JSON, nullable=False
    )  # List of task type IDs this metric applies to
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<EvaluationType(id={self.id}, name={self.name}, category={self.category})>"


# Task model removed - Workers should use the API's Task model from project_models
# to avoid SQLAlchemy metadata conflicts when both services are loaded.
# All foreign keys in this file reference "tasks.id" which is the API's table.


class UploadedData(Base):
    """Uploaded data files database model"""

    __tablename__ = "uploaded_data"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    size = Column(Integer, nullable=False)  # File size in bytes
    # File format (pdf, docx, txt, etc.)
    format = Column(String, nullable=False)
    document_count = Column(Integer, default=1, nullable=False)  # Number of documents in the file
    description = Column(Text, nullable=True)
    task_id = Column(String, nullable=True)  # Associated task ID
    uploaded_by = Column(String, nullable=False)  # User ID who uploaded
    upload_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed = Column(Boolean, default=False, nullable=False)

    def __repr__(self):
        return f"<UploadedData(id={self.id}, name={self.name}, format={self.format})>"


class SyntheticDataGeneration(Base):
    """Synthetic data generation jobs database model"""

    __tablename__ = "synthetic_data_generations"

    id = Column(String, primary_key=True, index=True)
    # User who initiated the generation
    user_id = Column(String, nullable=False)
    # JSON array of source data IDs
    source_data_ids = Column(Text, nullable=False)
    # Task to add generated data to
    target_task_id = Column(String, nullable=False)
    model_id = Column(String, nullable=False)  # Selected LLM model ID
    # User instructions for generation
    instructions = Column(Text, nullable=False)
    status = Column(
        String, default="pending", nullable=False
    )  # pending, running, completed, failed
    generated_count = Column(Integer, default=0, nullable=False)  # Number of generated items
    error_message = Column(Text, nullable=True)  # Error message if failed
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<SyntheticDataGeneration(id={self.id}, status={self.status})>"


class ResponseGeneration(Base):
    """Response generation tracking database model"""

    __tablename__ = "response_generations"

    id = Column(String, primary_key=True, index=True)
    project_id = Column(String, nullable=True)  # Associated project ID
    task_id = Column(String, ForeignKey("tasks.id"), nullable=False)  # Associated task ID
    model_id = Column(String, nullable=False)  # Model used for generation
    config_id = Column(
        String,
        nullable=False,
        # Configuration used (can be task_evaluation_config or generation_config ID)
    )
    structure_key = Column(String, nullable=True, index=True)  # Prompt structure key (Issue #762)
    status = Column(
        String, default="pending", nullable=False
    )  # pending, running, completed, failed
    # Number of responses generated
    responses_generated = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)  # Error message if failed
    # Generation result (actual generated content)
    result = Column(JSON, nullable=True)
    # Prompt used for generation (system_prompt + instruction_prompt template as JSON)
    prompt_used = Column(Text, nullable=True)
    # Parameters used for generation (temperature, max_tokens, etc.)
    parameters = Column(JSON, nullable=True)
    # Additional generation metadata
    generation_metadata = Column(JSON, nullable=True)
    # User who started the generation
    created_by = Column(String, nullable=False)
    # Organization context for key resolution (Issue #1180)
    organization_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    # task relationship - references API's Task model from project_models
    # Note: config_id can reference either TaskEvaluationConfig or GenerationConfig
    # No direct relationship defined due to polymorphic nature

    def __repr__(self):
        return f"<ResponseGeneration(id={self.id}, task_id={self.task_id}, model_id={self.model_id}, status={self.status})>"


class LLMResponse(Base):
    """Individual LLM response content database model"""

    __tablename__ = "generations"  # Fixed: was "llm_responses" but table is actually "generations"

    id = Column(String, primary_key=True, index=True)
    generation_id = Column(
        String, ForeignKey("response_generations.id"), nullable=False
    )  # Parent generation job
    task_id = Column(
        String, nullable=True
    )  # Associated task ID (nullable, no FK to match API model)
    model_id = Column(String, nullable=False)  # Model used for generation
    # prompt_id removed - prompts table dropped in issue #759
    # Prompt functionality now in generation_structure field
    case_data = Column(Text, nullable=False)  # Input case data
    response_content = Column(Text, nullable=False)  # Generated response
    usage_stats = Column(JSON, nullable=True)  # Token usage and costs
    # Additional response metadata
    response_metadata = Column(JSON, nullable=True)
    status = Column(
        String, default="completed", nullable=False
    )  # completed, failed, parse_failed, parse_failed_max_retries
    error_message = Column(Text, nullable=True)  # Error message if failed
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Parsing support for LLM response structure
    parsed_annotation = Column(JSONB, nullable=True)  # Structured Label Studio format
    parse_status = Column(
        String, default="pending"
    )  # "pending", "success", "failed", "validation_error"
    parse_error = Column(Text, nullable=True)  # Error message for debugging
    parse_metadata = Column(JSON, nullable=True)  # {retry_count: int, last_attempt: datetime, ...}

    # Label config versioning (tracks which schema version was used for parsing)
    label_config_version = Column(String(50), nullable=True)  # e.g., "v1", "v2"
    label_config_snapshot = Column(Text, nullable=True)  # Exact schema at parse time

    # Relationships
    # generation = relationship("ResponseGeneration")  # Removed to match API model

    def __repr__(self):
        return f"<LLMResponse(id={self.id}, generation_id={self.generation_id}, model_id={self.model_id})>"


# Alias for API compatibility - tasks.py imports Generation from models
Generation = LLMResponse


class EvaluationRun(Base):
    """Project-level evaluation run record"""

    __tablename__ = "evaluation_runs"

    id = Column(String, primary_key=True, index=True)
    task_id = Column(String, ForeignKey("tasks.id"), nullable=True)  # Associated task ID (legacy)
    project_id = Column(String, nullable=True, index=True)  # Project ID (new system)
    model_id = Column(String, nullable=False)  # Model that was evaluated
    evaluation_type_ids = Column(JSON, nullable=False)  # List of evaluation type IDs used
    metrics = Column(JSON, nullable=False)  # Evaluation metrics as JSON
    # Additional evaluation metadata
    eval_metadata = Column(JSON, nullable=True)
    status = Column(
        String, default="completed", nullable=False
    )  # pending, running, completed, failed
    error_message = Column(Text, nullable=True)  # Error message if failed
    # Number of samples evaluated
    samples_evaluated = Column(Integer, nullable=True)
    # Flag indicating if per-sample results are available
    has_sample_results = Column(Boolean, default=False, nullable=False)
    created_by = Column(String, nullable=False)  # User who ran the evaluation
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    # task relationship - references API's Task model from project_models
    task_evaluations = relationship(
        "TaskEvaluation", back_populates="evaluation_run", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<EvaluationRun(id={self.id}, project_id={self.project_id}, model_id={self.model_id})>"


class EvaluationRunMetric(Base):
    """Individual evaluation metric results"""

    __tablename__ = "evaluation_run_metrics"

    id = Column(String, primary_key=True, index=True)
    evaluation_id = Column(String, ForeignKey("evaluation_runs.id"), nullable=False)
    evaluation_type_id = Column(String, ForeignKey("evaluation_types.id"), nullable=False)
    value = Column(Float, nullable=False)  # The metric value
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    evaluation_run = relationship("EvaluationRun")
    evaluation_type = relationship("EvaluationType")

    def __repr__(self):
        return f"<EvaluationRunMetric(evaluation_id={self.evaluation_id}, type={self.evaluation_type_id}, value={self.value})>"


class TaskEvaluation(Base):
    """Per-task evaluation results for drill-down analysis"""

    __tablename__ = "task_evaluations"

    id = Column(String, primary_key=True, index=True)
    evaluation_id = Column(
        String, ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id = Column(String, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    generation_id = Column(String, nullable=True)  # No FK constraint for workers compatibility
    annotation_id = Column(String, nullable=True, index=True)  # No FK constraint for workers compatibility

    # Field-level results
    field_name = Column(String, nullable=False, index=True)
    answer_type = Column(String, nullable=False)

    # Ground truth and prediction (stored as JSON for flexibility)
    ground_truth = Column(JSON, nullable=False)
    prediction = Column(JSON, nullable=False)

    # Computed metrics for this sample
    metrics = Column(JSON, nullable=False)

    # Pass/fail status
    passed = Column(Boolean, nullable=False, index=True)
    confidence_score = Column(Float, nullable=True)

    # Metadata
    error_message = Column(Text, nullable=True)
    processing_time_ms = Column(Integer, nullable=True)
    # Prompt provenance for LLM judge evaluations
    judge_prompts_used = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    evaluation_run = relationship("EvaluationRun", back_populates="task_evaluations")

    def __repr__(self):
        return f"<TaskEvaluation(id={self.id}, evaluation_id={self.evaluation_id}, task_id={self.task_id}, passed={self.passed})>"


# Backward-compatibility aliases (old names -> new names)
Evaluation = EvaluationRun
EvaluationMetric = EvaluationRunMetric
EvaluationSampleResult = TaskEvaluation


class LLMModel(Base):
    """LLM model definitions stored in database"""

    __tablename__ = "llm_models"

    id = Column(String, primary_key=True, index=True)  # e.g., "gpt-4", "claude-3-sonnet"
    name = Column(String, nullable=False)  # Human-readable name
    description = Column(Text, nullable=True)  # Description of the model
    provider = Column(String, nullable=False)  # e.g., "openai", "anthropic", "huggingface"
    model_type = Column(String, nullable=False)  # e.g., "chat", "completion", "embedding"
    capabilities = Column(
        JSON, nullable=False
    )  # List of capabilities like ["text_generation", "reasoning"]
    # JSON schema for model configuration
    config_schema = Column(JSON, nullable=True)
    # Default configuration parameters
    default_config = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<LLMModel(id={self.id}, name={self.name}, provider={self.provider})>"


# TaskEvaluationConfig removed - old task system cleanup
class Prompt(Base):
    """Prompts for tasks - system, instruction, and evaluation prompts"""

    __tablename__ = "prompts"

    id = Column(String, primary_key=True, index=True)
    task_id = Column(String, ForeignKey("tasks.id"), nullable=False)
    prompt_name = Column(String, nullable=False)  # Name/title of the prompt
    prompt_text = Column(Text, nullable=False)  # The actual prompt text
    prompt_type = Column(
        String, nullable=False, default="evaluation"
    )  # evaluation, instruction, system
    evaluation_type_ids = Column(
        JSON, nullable=True
    )  # Which evaluation types this prompt applies to
    # Language of the prompt
    language = Column(String, nullable=False, default="de")
    is_default = Column(
        Boolean, default=False, nullable=False
    )  # Whether this is the default prompt for the task
    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    # task relationship - references API's Task model from project_models
    creator = relationship("User")

    def __repr__(self):
        return f"<Prompt(id={self.id}, task_id={self.task_id}, prompt_name={self.prompt_name})>"


# Note: GenerationConfig class removed in migration 411540fa6c40 (using JSONB in projects.generation_config instead)


class UserColumnPreferences(Base):
    """User column preferences for LLM interactions table per task"""

    __tablename__ = "user_column_preferences"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    task_id = Column(String, ForeignKey("tasks.id"), nullable=False)
    # JSON object with column visibility settings
    column_settings = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User")
    # task relationship - references API's Task model from project_models

    # Unique constraint to ensure one preference per user per task
    __table_args__ = (
        sa.UniqueConstraint("user_id", "task_id", name="unique_user_task_preferences"),
    )

    def __repr__(self):
        return (
            f"<UserColumnPreferences(id={self.id}, user_id={self.user_id}, task_id={self.task_id})>"
        )


class NotificationType(str, Enum):
    """Types of notifications in the system"""

    TASK_CREATED = "task_created"
    TASK_COMPLETED = "task_completed"
    LLM_GENERATION_COMPLETED = "llm_generation_completed"
    LLM_GENERATION_FAILED = "llm_generation_failed"
    EVALUATION_COMPLETED = "evaluation_completed"
    EVALUATION_FAILED = "evaluation_failed"
    ANNOTATION_COMPLETED = "annotation_completed"
    DATA_UPLOAD_COMPLETED = "data_upload_completed"
    ORGANIZATION_INVITATION_SENT = "organization_invitation_sent"
    ORGANIZATION_INVITATION_ACCEPTED = "organization_invitation_accepted"
    MEMBER_JOINED = "member_joined"
    SYSTEM_ALERT = "system_alert"
    ERROR_OCCURRED = "error_occurred"

    # Phase 3A: Extended notification types
    MODEL_API_KEY_INVALID = "model_api_key_invalid"
    LONG_RUNNING_TASK_UPDATE = "long_running_task_update"
    SYSTEM_MAINTENANCE = "system_maintenance"
    SECURITY_ALERT = "security_alert"
    API_QUOTA_WARNING = "api_quota_warning"
    PERFORMANCE_ALERT = "performance_alert"


class Notification(Base):
    """User notification model"""

    __tablename__ = "notifications"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=True)
    type = Column(SQLEnum(NotificationType), nullable=False)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    data = Column(JSON, nullable=True)  # Additional context data (task_id, etc.)
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User")
    organization = relationship("Organization")

    def __repr__(self):
        return f"<Notification(id={self.id}, type={self.type}, user_id={self.user_id}, is_read={self.is_read})>"


class UserNotificationPreference(Base):
    """User preferences for different notification types"""

    __tablename__ = "user_notification_preferences"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    notification_type = Column(SQLEnum(NotificationType), nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User")

    # Unique constraint to ensure one preference per user per notification type
    __table_args__ = (
        sa.UniqueConstraint(
            "user_id", "notification_type", name="unique_user_notification_preference"
        ),
    )

    def __repr__(self):
        return f"<UserNotificationPreference(user_id={self.user_id}, type={self.notification_type}, enabled={self.enabled})>"


class SyncStatus(str, Enum):
    """Annotation sync status options"""

    SYNCED = "synced"
    PENDING = "pending"
    FAILED = "failed"
    CONFLICT = "conflict"


class AnnotationStatus(str, Enum):
    """Annotation status options"""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


# Annotation model removed - Workers should use the API's Annotation model from project_models
# to avoid SQLAlchemy metadata conflicts when both services are loaded.


class HumanEvaluationConfig(Base):
    """Configuration for human evaluation of LLM responses"""

    __tablename__ = "human_evaluation_configs"

    id = Column(String, primary_key=True, index=True)
    task_id = Column(String, ForeignKey("tasks.id"), nullable=False, unique=True)
    evaluation_project_id = Column(
        String, nullable=True
    )  # External project ID for evaluation (deprecated)
    evaluator_count = Column(Integer, default=3, nullable=False)  # Target number of evaluators
    randomization_seed = Column(Integer, nullable=True)  # For reproducible response ordering
    blinding_enabled = Column(
        Boolean, default=True, nullable=False
    )  # Whether to anonymize model names
    include_human_responses = Column(
        Boolean, default=False, nullable=False
    )  # Mix in human responses
    status = Column(String, default="pending", nullable=False)  # pending, active, completed
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    # task relationship - references API's Task model from project_models

    def __repr__(self):
        return (
            f"<HumanEvaluationConfig(id={self.id}, task_id={self.task_id}, status={self.status})>"
        )


class HumanEvaluationResult(Base):
    """Individual human evaluation result for an LLM response"""

    __tablename__ = "human_evaluation_results"

    id = Column(String, primary_key=True, index=True)
    config_id = Column(String, ForeignKey("human_evaluation_configs.id"), nullable=False)
    task_id = Column(String, ForeignKey("tasks.id"), nullable=False)
    response_id = Column(String, nullable=False)  # Anonymized response identifier
    evaluator_id = Column(String, nullable=False)  # Anonymous evaluator identifier

    # Likert scale ratings (1-5)
    correctness_score = Column(Integer, nullable=False)  # How accurate and factually correct
    completeness_score = Column(Integer, nullable=False)  # How thoroughly addresses question
    style_score = Column(Integer, nullable=False)  # How clear, well-written, professional
    usability_score = Column(Integer, nullable=False)  # How useful and actionable

    # Optional feedback
    comments = Column(Text, nullable=True)

    # Evaluation metadata
    evaluation_time_seconds = Column(Float, nullable=True)  # Time spent evaluating
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    config = relationship("HumanEvaluationConfig")
    # task relationship - references API's Task model from project_models

    # Unique constraint to prevent duplicate evaluations
    __table_args__ = (
        sa.UniqueConstraint(
            "config_id",
            "response_id",
            "evaluator_id",
            name="unique_evaluation_per_response_evaluator",
        ),
    )

    def __repr__(self):
        return f"<HumanEvaluationResult(id={self.id}, response_id={self.response_id}, evaluator_id={self.evaluator_id})>"


class HumanEvaluationMapping(Base):
    """Mapping between anonymized response IDs and actual model responses for human evaluation"""

    __tablename__ = "human_evaluation_mappings"

    id = Column(String, primary_key=True, index=True)
    config_id = Column(String, ForeignKey("human_evaluation_configs.id"), nullable=False)
    anonymous_response_id = Column(String, nullable=False)  # ID shown to evaluators
    actual_response_id = Column(
        String, nullable=True
    )  # Actual LLMResponse.id (null for human responses)
    model_id = Column(String, nullable=True)  # Actual model ID (null for human responses)
    anonymous_model_name = Column(
        String, nullable=False
    )  # Name shown to evaluators (Model_A, Human_Expert, etc.)
    response_text = Column(Text, nullable=False)  # The response text being evaluated
    response_type = Column(String, nullable=False)  # "llm" or "human"
    question_data = Column(JSON, nullable=False)  # Associated question/prompt data
    display_order = Column(Integer, nullable=False)  # Order for consistent display
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    config = relationship("HumanEvaluationConfig")

    # Unique constraints
    __table_args__ = (
        sa.UniqueConstraint(
            "config_id",
            "anonymous_response_id",
            name="unique_anonymous_response_per_config",
        ),
        sa.UniqueConstraint("config_id", "display_order", name="unique_display_order_per_config"),
    )

    def __repr__(self):
        return f"<HumanEvaluationMapping(id={self.id}, anonymous_id={self.anonymous_response_id}, model={self.anonymous_model_name})>"


# Note: IgnoredEnterpriseProject class removed in migration 411540fa6c40 (legacy enterprise feature)


class ProjectReport(Base):
    """
    Project report model for publishing evaluation results.

    Reports are automatically created when projects are created and progressively
    populated as the project advances (data import, annotation, generation, evaluation).
    """

    __tablename__ = "project_reports"

    id = Column(String, primary_key=True, index=True)
    project_id = Column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Report content (editable sections)
    content = Column(JSONB, nullable=False)

    # Publication status
    is_published = Column(Boolean, default=False, nullable=False, index=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    published_by = Column(String, ForeignKey("users.id"), nullable=True)

    # Audit fields
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<ProjectReport(id={self.id}, project_id={self.project_id}, is_published={self.is_published})>"
