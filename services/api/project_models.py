"""
Database models for BenGER project and task management

Clean, functional naming without verbose or branded terms.
"""

# Import compatibility
import os

import sqlalchemy as sa
from sqlalchemy import BigInteger, JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text

if "sqlite" in os.environ.get("DATABASE_URL", "sqlite:///:memory:").lower():
    from sqlalchemy import JSON as JSONB
else:
    from sqlalchemy.dialects.postgresql import JSONB

from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class Project(Base):
    """
    Project model - container for annotation work
    """

    __tablename__ = "projects"

    # Core fields
    id = Column(String, primary_key=True, index=True)
    title = Column(String(255), nullable=False)  # Primary name field
    description = Column(Text, nullable=True)
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    # Note: organizations linked via project_organizations junction table

    # Configuration
    label_config = Column(Text, nullable=True)  # XML/JSON configuration for annotation interface
    label_config_version = Column(
        String(50), nullable=True
    )  # Current schema version (e.g., "v1", "v2")
    label_config_history = Column(
        JSONB, nullable=True
    )  # Version history with timestamps and descriptions
    # Note: generation_structure column removed in migration 002_add_prompt_structures (Issue #762)
    # Prompt structures now stored in generation_config.prompt_structures JSONB field
    expert_instruction = Column(Text, nullable=True)  # Instructions for annotators
    show_instruction = Column(Boolean, default=True, nullable=False)
    instructions_always_visible = Column(Boolean, default=False, nullable=False)
    conditional_instructions = Column(JSONB, nullable=True)  # [{id, content, weight}]
    show_skip_button = Column(Boolean, default=True, nullable=False)
    enable_empty_annotation = Column(Boolean, default=True, nullable=False)
    # Note: show_annotation_history and show_ground_truth_first columns removed in migration 411540fa6c40
    # Note: show_overlap_first, overlap_cohort_percentage, color columns removed in migration 95726e4be27e

    # Annotation settings
    maximum_annotations = Column(Integer, default=1, nullable=False)
    min_annotations_per_task = Column(Integer, default=1, nullable=False)
    assignment_mode = Column(String(50), default="open", nullable=True)
    randomize_task_order = Column(Boolean, default=False, server_default="false", nullable=False)

    # Review settings
    review_enabled = Column(Boolean, default=False, nullable=False)
    review_mode = Column(
        String(50), default="in_place", nullable=False
    )  # in_place, independent, both
    allow_self_review = Column(Boolean, default=False, nullable=False)

    # Korrektur settings (formerly "Feedback")
    korrektur_enabled = Column(Boolean, default=False, nullable=False)
    korrektur_config = Column(JSONB, nullable=True)  # [{value: str, background: str}]

    # UI behavior
    show_submit_button = Column(Boolean, default=True, nullable=False)
    require_comment_on_skip = Column(Boolean, default=False, nullable=False)
    require_confirm_before_submit = Column(Boolean, default=False, nullable=False)
    skip_queue = Column(String, default="requeue_for_others", server_default="requeue_for_others", nullable=False)
    # Note: sampling column removed in migration 95726e4be27e

    # Immediate evaluation feedback (Issue #998)
    immediate_evaluation_enabled = Column(Boolean, default=False, nullable=False)

    # Annotation time limit (Issue #1043)
    annotation_time_limit_enabled = Column(Boolean, default=False, nullable=False)
    annotation_time_limit_seconds = Column(
        Integer, nullable=True
    )  # Time limit in seconds, null when disabled

    # Strict timer mode (Issue #1205)
    strict_timer_enabled = Column(Boolean, default=False, nullable=False)

    # Post-annotation questionnaire (Issue #1208)
    questionnaire_enabled = Column(Boolean, default=False, nullable=False)
    questionnaire_config = Column(Text, nullable=True)  # Label Studio XML for questionnaire

    # Additional database columns
    # Note: Legacy Label Studio columns removed in migration 411540fa6c40:
    # show_collab_predictions, evaluate_predictions_automatically, config_has_control_tags,
    # skip_queue, reveal_preannotations_interactively, task_data_login, task_data_password,
    # control_weights, parsed_label_config

    # Generation configuration (Issue #482)
    generation_config = Column(JSONB, nullable=True)

    # LLM Model IDs for generation (Issue #XXX - Model Selection Persistence)
    llm_model_ids = Column(JSON, nullable=True)

    # Evaluation configuration (Issue #483)
    evaluation_config = Column(JSONB, nullable=True)

    # Visibility
    is_private = Column(Boolean, default=False, nullable=False, index=True)
    is_public = Column(Boolean, default=False, nullable=False, server_default="false")
    public_role = Column(String(32), nullable=True)

    # Feature visibility — controls which configuration cards render on the
    # project detail page. Hides the card; underlying data is preserved and
    # the relevant API endpoints stay open. Defaults preserve back-compat for
    # existing projects.
    enable_annotation = Column(Boolean, default=True, server_default="true", nullable=False)
    enable_generation = Column(Boolean, default=True, server_default="true", nullable=False)
    enable_evaluation = Column(Boolean, default=True, server_default="true", nullable=False)

    # Status
    is_published = Column(Boolean, default=False, nullable=False)
    is_archived = Column(Boolean, default=False, nullable=False, index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])
    # Organizations linked via project_organizations junction table
    project_organizations = relationship(
        "ProjectOrganization", back_populates="project", cascade="all, delete-orphan"
    )
    organizations = relationship("Organization", secondary="project_organizations", viewonly=True)
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")
    annotations = relationship("Annotation", back_populates="project")

    # Visibility invariants — mirrored in alembic migration 035 so the
    # constraints + partial index exist whether the schema is built from
    # Base.metadata or from migrations. Same names as the migration.
    __table_args__ = (
        sa.CheckConstraint(
            "NOT (is_private AND is_public)",
            name="ck_projects_visibility_exclusive",
        ),
        sa.CheckConstraint(
            "public_role IS NULL OR public_role IN ('ANNOTATOR', 'CONTRIBUTOR')",
            name="ck_projects_public_role_valid",
        ),
        sa.CheckConstraint(
            "NOT is_public OR public_role IS NOT NULL",
            name="ck_projects_public_role_required_when_public",
        ),
        sa.Index(
            "ix_projects_is_public",
            "is_public",
            postgresql_where=sa.text("is_public = true"),
        ),
    )

    def __repr__(self):
        return f"<Project(id={self.id}, title={self.title})>"


class Task(Base):
    """
    Task model - individual item to annotate
    """

    __tablename__ = "tasks"

    # Core fields
    id = Column(String, primary_key=True, index=True)
    project_id = Column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Data fields
    data = Column(JSONB, nullable=False)  # The actual data to annotate
    meta = Column(JSONB, nullable=True)  # Optional metadata

    # User tracking
    created_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assigned_to = Column(
        String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Annotation tracking
    is_labeled = Column(Boolean, default=False, nullable=False, index=True)
    total_annotations = Column(Integer, default=0, nullable=False)
    cancelled_annotations = Column(Integer, default=0, nullable=False)

    # Comment tracking
    comment_count = Column(Integer, default=0, nullable=False)
    unresolved_comment_count = Column(Integer, default=0, nullable=False)
    last_comment_updated_at = Column(DateTime(timezone=True), nullable=True)
    comment_authors = Column(JSONB, nullable=True)

    # Korrektur tracking (formerly "feedback")
    korrektur_count = Column(Integer, default=0, nullable=False)
    unresolved_korrektur_count = Column(Integer, default=0, nullable=False)

    # Additional fields
    file_upload_id = Column(String, nullable=True)
    inner_id = Column(Integer, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    project = relationship("Project", back_populates="tasks")
    annotations = relationship("Annotation", back_populates="task", cascade="all, delete-orphan")
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])
    assigned_user = relationship("User", foreign_keys=[assigned_to])

    def __repr__(self):
        return f"<Task(id={self.id}, project_id={self.project_id}, is_labeled={self.is_labeled})>"


class Annotation(Base):
    """
    Annotation model - human annotations on tasks
    """

    __tablename__ = "annotations"

    # Core fields
    id = Column(String, primary_key=True, index=True)
    task_id = Column(
        String,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id = Column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    completed_by = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    # Annotation data
    result = Column(JSONB, nullable=False)
    draft = Column(JSONB, nullable=True)

    # Status
    was_cancelled = Column(Boolean, default=False, nullable=False)
    ground_truth = Column(Boolean, default=False, nullable=False)

    # Metrics
    lead_time = Column(Float, nullable=True)  # Time in seconds
    auto_submitted = Column(
        Boolean, default=False, nullable=False
    )  # Timer-expired auto-submit (Issue #1205)
    # Enhanced timing (Issue #1208)
    active_duration_ms = Column(BigInteger, nullable=True)  # Time tab was visible
    focused_duration_ms = Column(BigInteger, nullable=True)  # Time with user interaction
    tab_switches = Column(Integer, default=0, nullable=False)  # Visibility change count
    instruction_variant = Column(String, nullable=True)  # ID of shown instruction variant
    ai_assisted = Column(Boolean, default=False, nullable=False)  # Denormalized from variant ai_allowed (Issue #1272)
    prediction_scores = Column(JSONB, nullable=True)

    # Review
    reviewed_by = Column(String, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_result = Column(String, nullable=True)  # approved, rejected, fixed
    review_annotation = Column(JSONB, nullable=True)  # Reviewer's independent annotation
    review_comment = Column(Text, nullable=True)  # Reviewer's feedback text

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    task = relationship("Task", back_populates="annotations")
    project = relationship("Project", back_populates="annotations")
    annotator = relationship("User", foreign_keys=[completed_by])
    reviewer = relationship("User", foreign_keys=[reviewed_by])

    def __repr__(self):
        return (
            f"<Annotation(id={self.id}, task_id={self.task_id}, completed_by={self.completed_by})>"
        )


class SkippedTask(Base):
    """
    Track skipped tasks with optional comments
    Used when annotators skip tasks that are difficult or problematic
    """

    __tablename__ = "skipped_tasks"

    # Core fields
    id = Column(String, primary_key=True, index=True)
    task_id = Column(
        String,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id = Column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    skipped_by = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    # Skip details
    comment = Column(Text, nullable=True)  # Optional reason for skipping

    # Timestamps
    skipped_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    task = relationship("Task", backref="skips")
    project = relationship("Project", backref="skipped_tasks")
    user = relationship("User", foreign_keys=[skipped_by])

    def __repr__(self):
        return f"<SkippedTask(id={self.id}, task_id={self.task_id}, skipped_by={self.skipped_by})>"


# Import/Export models


class DataImport(Base):
    """
    Track data imports into projects
    """

    __tablename__ = "data_imports"

    id = Column(String, primary_key=True, index=True)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    imported_by = Column(String, ForeignKey("users.id"), nullable=False)

    # Import details
    file_name = Column(String, nullable=True)
    file_format = Column(String, nullable=False)  # json, csv, tsv, txt
    total_items = Column(Integer, nullable=False)
    imported_items = Column(Integer, nullable=False)
    failed_items = Column(Integer, default=0, nullable=False)

    # Status
    status = Column(String, nullable=False)  # pending, processing, completed, failed
    error_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    project = relationship("Project")
    importer = relationship("User")

    def __repr__(self):
        return f"<DataImport(id={self.id}, project_id={self.project_id}, status={self.status})>"


class DataExport(Base):
    """
    Track data exports from projects
    """

    __tablename__ = "data_exports"

    id = Column(String, primary_key=True, index=True)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    exported_by = Column(String, ForeignKey("users.id"), nullable=False)

    # Export details
    export_format = Column(String, nullable=False)  # json, csv, tsv, coco, conll
    filters = Column(JSONB, nullable=True)
    total_items = Column(Integer, nullable=False)

    # File info
    file_name = Column(String, nullable=False)
    file_url = Column(Text, nullable=True)
    file_size = Column(Integer, nullable=True)

    # Status
    status = Column(String, nullable=False)  # pending, processing, completed, failed
    error_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    project = relationship("Project")
    exporter = relationship("User")

    def __repr__(self):
        return (
            f"<DataExport(id={self.id}, project_id={self.project_id}, format={self.export_format})>"
        )


class ProjectOrganization(Base):
    """
    Many-to-many relationship between projects and organizations
    """

    __tablename__ = "project_organizations"

    id = Column(String, primary_key=True, index=True)
    project_id = Column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id = Column(
        String,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assigned_by = Column(String, ForeignKey("users.id"), nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    project = relationship("Project", back_populates="project_organizations")
    organization = relationship("Organization")
    assigner = relationship("User")

    # Unique constraint
    __table_args__ = (
        sa.UniqueConstraint("project_id", "organization_id", name="unique_project_organization"),
    )

    def __repr__(self):
        return f"<ProjectOrganization(project_id={self.project_id}, org_id={self.organization_id})>"


class ProjectMember(Base):
    """
    Project-specific member assignments
    """

    __tablename__ = "project_members"

    id = Column(String, primary_key=True, index=True)
    project_id = Column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(50), nullable=False, default="ANNOTATOR")
    assigned_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    project = relationship("Project", backref="project_members")
    user = relationship("User", foreign_keys=[user_id])
    assigned_by_user = relationship("User", foreign_keys=[assigned_by])

    # Unique constraint
    __table_args__ = (sa.UniqueConstraint("project_id", "user_id", name="unique_project_member"),)

    def __repr__(self):
        return f"<ProjectMember(project_id={self.project_id}, user_id={self.user_id}, role={self.role})>"


class TaskAssignment(Base):
    """
    Task-level assignment for workload distribution
    """

    __tablename__ = "task_assignments"

    id = Column(String, primary_key=True, index=True)
    task_id = Column(String, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    assigned_by = Column(String, ForeignKey("users.id"), nullable=False)

    # Polymorphic target — what this assignment is *for*. Default 'task'
    # preserves the original "assign a whole task" semantic. New values
    # 'annotation' / 'generation' (used by Korrektur) carry a target_id
    # pointing at the specific item to grade. No FK because the column is
    # polymorphic; integrity is enforced by the application layer.
    target_type = Column(String(50), default="task", server_default="task", nullable=False)
    target_id = Column(String, nullable=True)

    # Assignment metadata
    status = Column(String(50), default="assigned", nullable=False)
    priority = Column(Integer, default=0, nullable=False)
    due_date = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)

    # Timestamps
    assigned_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    task = relationship("Task", backref="assignments")
    user = relationship("User", foreign_keys=[user_id], backref="task_assignments")
    assigned_by_user = relationship("User", foreign_keys=[assigned_by])

    # Uniqueness: at most one task-level assignment per (task, user) AND
    # at most one item-level assignment per (task, user, target_type, target_id).
    # Postgres partial unique indexes split the two semantics cleanly.
    __table_args__ = (
        sa.Index(
            "uniq_task_level_assignment",
            "task_id",
            "user_id",
            unique=True,
            postgresql_where=sa.text("target_type = 'task'"),
        ),
        sa.Index(
            "uniq_item_level_assignment",
            "task_id",
            "user_id",
            "target_type",
            "target_id",
            unique=True,
            postgresql_where=sa.text("target_type <> 'task'"),
        ),
        sa.Index("ix_task_assignment_status", "status"),
        sa.Index("ix_task_assignment_priority", "priority"),
        sa.Index(
            "ix_task_assignment_item_lookup",
            "task_id",
            "target_type",
            "target_id",
            "user_id",
        ),
    )

    def __repr__(self):
        return f"<TaskAssignment(task_id={self.task_id}, user_id={self.user_id}, status={self.status})>"


class AnnotationTimerSession(Base):
    """
    Server-side timer tracking for annotation sessions (Issue #1205).

    Decoupled from TaskAssignment to support open-mode projects
    where no assignment records exist. Each record represents
    one user starting to work on one task.
    """

    __tablename__ = "annotation_timer_sessions"

    id = Column(String, primary_key=True, index=True)
    task_id = Column(String, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Timer tracking
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    time_limit_seconds = Column(Integer, nullable=False)
    is_strict = Column(Boolean, default=False, nullable=False)

    # Completion tracking
    completed_at = Column(DateTime(timezone=True), nullable=True)
    auto_submitted = Column(Boolean, default=False, nullable=False)

    # Draft data for server-side auto-submit
    draft_result = Column(JSONB, nullable=True)

    # Relationships
    task = relationship("Task", backref="timer_sessions")
    project = relationship("Project", backref="timer_sessions")
    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        sa.UniqueConstraint("task_id", "user_id", name="unique_timer_session"),
        sa.Index("ix_timer_session_project_user", "project_id", "user_id"),
    )


class TaskDraft(Base):
    """Server-side draft storage for annotation auto-save.

    Stores periodic draft snapshots for ALL projects (not just timer projects).
    Upserted every 30s when the user is actively annotating.
    Deleted when the annotation is submitted.
    """

    __tablename__ = "task_drafts"

    id = Column(String, primary_key=True, index=True)
    task_id = Column(String, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    draft_result = Column(JSONB, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        sa.UniqueConstraint("task_id", "user_id", name="unique_task_draft"),
        sa.Index("ix_task_drafts_project_user", "project_id", "user_id"),
    )


class PostAnnotationResponse(Base):
    """
    Post-annotation questionnaire response (Issue #1208).

    Stores structured feedback (Likert scales, choices) collected
    from annotators after each annotation submission.
    """

    __tablename__ = "post_annotation_responses"

    id = Column(String, primary_key=True, index=True)
    annotation_id = Column(
        String,
        ForeignKey("annotations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_id = Column(
        String,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id = Column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Questionnaire result in Label Studio format
    result = Column(JSONB, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    annotation = relationship("Annotation", backref="questionnaire_responses")
    task = relationship("Task", backref="questionnaire_responses")
    project = relationship("Project", backref="questionnaire_responses")
    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        sa.Index("ix_par_user_project", "user_id", "project_id"),
    )

    def __repr__(self):
        return f"<PostAnnotationResponse(id={self.id}, annotation_id={self.annotation_id})>"


class KorrekturComment(Base):
    """
    Korrektur comment on annotations, generations, or evaluations.

    Supports text highlights (anchored to character offsets in source text)
    and general comments. Threaded via parent_id (1-level deep replies).
    Aligns with Label Studio's flat comment model with resolution tracking.
    """

    __tablename__ = "korrektur_comments"

    # Core fields
    id = Column(String, primary_key=True, index=True)
    project_id = Column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id = Column(
        String,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Target (polymorphic: annotation, generation, or evaluation)
    target_type = Column(String(20), nullable=False)  # annotation, generation, evaluation
    target_id = Column(String, nullable=False)

    # Threading
    parent_id = Column(
        String,
        ForeignKey("korrektur_comments.id", ondelete="CASCADE"),
        nullable=True,
    )

    # Comment content
    text = Column(Text, nullable=False)

    # Highlight (optional — null for general comments)
    highlight_start = Column(Integer, nullable=True)
    highlight_end = Column(Integer, nullable=True)
    highlight_text = Column(Text, nullable=True)
    highlight_label = Column(String, nullable=True)

    # Resolution tracking
    is_resolved = Column(Boolean, default=False, nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(String, ForeignKey("users.id"), nullable=True)

    # Audit
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    project = relationship("Project")
    task = relationship("Task")
    parent = relationship("KorrekturComment", remote_side="KorrekturComment.id", backref="replies")
    author = relationship("User", foreign_keys=[created_by])
    resolver = relationship("User", foreign_keys=[resolved_by])

    __table_args__ = (
        sa.Index("ix_korrektur_comments_project_task", "project_id", "task_id"),
        sa.Index("ix_korrektur_comments_target", "target_type", "target_id"),
        sa.Index("ix_korrektur_comments_parent", "parent_id"),
        sa.Index("ix_korrektur_comments_created_by", "created_by"),
    )

    def __repr__(self):
        return f"<KorrekturComment(id={self.id}, target_type={self.target_type}, target_id={self.target_id})>"
