"""
Database models for BenGER project and task management

Clean, functional naming without verbose or branded terms.
"""

# Import compatibility
import os

import sqlalchemy as sa
from sqlalchemy import JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text

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
    label_config_version = Column(String(50), nullable=True)  # Version tracking for label config
    label_config_history = Column(
        JSONB, nullable=True, server_default='{}'
    )  # History of label config changes
    # Note: generation_structure column removed in migration 002_add_prompt_structures (Issue #762)
    # Prompt structures now stored in generation_config.prompt_structures JSONB field
    expert_instruction = Column(Text, nullable=True)  # Instructions for annotators
    show_instruction = Column(Boolean, default=True, nullable=False)
    show_skip_button = Column(Boolean, default=True, nullable=False)
    enable_empty_annotation = Column(Boolean, default=True, nullable=False)
    # Note: show_annotation_history and show_ground_truth_first columns removed in migration 411540fa6c40
    # Note: show_overlap_first, overlap_cohort_percentage, color columns removed in migration 95726e4be27e

    # Annotation settings
    maximum_annotations = Column(Integer, default=1, nullable=False)
    min_annotations_per_task = Column(Integer, default=1, nullable=False)
    assignment_mode = Column(String(50), default="open", nullable=True)

    # UI behavior
    show_submit_button = Column(Boolean, default=True, nullable=False)
    require_comment_on_skip = Column(Boolean, default=False, nullable=False)
    require_confirm_before_submit = Column(Boolean, default=False, nullable=False)
    # Note: sampling column removed in migration 95726e4be27e

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
    auto_submitted = Column(Boolean, default=False, nullable=False)
    prediction_scores = Column(JSONB, nullable=True)

    # Review
    reviewed_by = Column(String, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_result = Column(String, nullable=True)  # approved, rejected, fixed

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


class AnnotationTimerSession(Base):
    """Server-side timer tracking for annotation sessions (Issue #1205)."""

    __tablename__ = "annotation_timer_sessions"

    id = Column(String, primary_key=True, index=True)
    task_id = Column(String, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    time_limit_seconds = Column(Integer, nullable=False)
    is_strict = Column(Boolean, default=False, nullable=False)

    completed_at = Column(DateTime(timezone=True), nullable=True)
    auto_submitted = Column(Boolean, default=False, nullable=False)
    draft_result = Column(JSONB, nullable=True)

    __table_args__ = (
        sa.UniqueConstraint("task_id", "user_id", name="unique_timer_session"),
    )


class TaskDraft(Base):
    """Server-side draft storage for annotation auto-save."""

    __tablename__ = "task_drafts"

    id = Column(String, primary_key=True, index=True)
    task_id = Column(String, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    draft_result = Column(JSONB, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        sa.UniqueConstraint("task_id", "user_id", name="unique_task_draft"),
    )


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

    # Unique constraint
    __table_args__ = (
        sa.UniqueConstraint("task_id", "user_id", name="unique_task_assignment"),
        sa.Index("ix_task_assignment_status", "status"),
        sa.Index("ix_task_assignment_priority", "priority"),
    )

    def __repr__(self):
        return f"<TaskAssignment(task_id={self.task_id}, user_id={self.user_id}, status={self.status})>"
