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

    # When True, annotators reviewing their own submitted work in "Meine
    # Aufgaben" see ALL task fields after submission (incl. the reference
    # solution / Musterlösung and raw ground_truth) so they can compare and
    # learn. When False (default) the post-submission view is filtered to only
    # the fields the annotator saw while labeling — protecting the reference
    # from being leaked to peers who still have to sit the same exam.
    annotator_full_visibility_after_submit = Column(
        Boolean, default=False, server_default="false", nullable=False
    )

    # Annotation time limit (Issue #1043)
    annotation_time_limit_enabled = Column(Boolean, default=False, nullable=False)
    annotation_time_limit_seconds = Column(
        Integer, nullable=True
    )  # Time limit in seconds, null when disabled

    # Strict timer mode (Issue #1205)
    strict_timer_enabled = Column(Boolean, default=False, nullable=False)

    # Restorable draft checkpoints (opt-in): when enabled, periodic draft
    # snapshots are stored as an append-only history (see TaskDraftCheckpoint)
    # and are NOT deleted on submit, so an annotator can restore an earlier
    # checkpoint. The interval is fixed at 5 min in the UI today but stored
    # here so it can be made configurable later without a schema change.
    restorable_checkpoints_enabled = Column(
        Boolean, default=False, server_default="false", nullable=False
    )
    checkpoint_interval_seconds = Column(
        Integer, default=300, server_default="300", nullable=False
    )

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

    # Project kind / origin (extended-edition student experience). Both are
    # free-form nullable strings — NOT Postgres ENUMs — so the community
    # edition ships a forward-compatible schema and an extended overlay can
    # introduce new kinds without an ALTER TYPE. `kind` distinguishes a
    # student exam ("exam") or flashcard deck ("flashcard_deck") from a plain
    # benchmark project (NULL). `origin` marks student-generated projects
    # ("student") so they can be excluded from public leaderboards while
    # remaining benchmarkable in the expert view. Write-once at creation.
    kind = Column(String(32), nullable=True, index=True)
    origin = Column(String(32), nullable=True, index=True)

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

    # Access window (timed availability). When set, the project is only writable
    # (annotate / generate / evaluate) between window_start_at and window_end_at,
    # and its task data is hidden before window_start_at — for the *access group*
    # only. Owners + org admins/contributors (anyone who can edit the project)
    # are always exempt, so a teacher can set up before and review after. Both
    # NULL ⇒ no window ⇒ always open (fully back-compatible). The upcoming/open/
    # closed state is DERIVED from these timestamps, never persisted — see
    # project_window_state() in routers/projects/helpers.py. This generalizes the
    # is_archived annotator read-only carve-out to a time window.
    window_start_at = Column(DateTime(timezone=True), nullable=True, index=True)
    window_end_at = Column(DateTime(timezone=True), nullable=True, index=True)

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
        sa.CheckConstraint(
            "window_start_at IS NULL OR window_end_at IS NULL "
            "OR window_end_at > window_start_at",
            name="ck_projects_window_bounds",
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

    # One active (non-cancelled) annotation per (task, user). This is the
    # DB-level guarantee against duplicate submissions: a strict-timer task has
    # two concurrent writers — the client auto-submit (POST /annotations) and
    # the server-side timer worker (tasks.auto_submit_expired_timer) — and an
    # advisory lock alone proved fragile (the worker task name is registered by
    # both platform and the extended overlay, so which implementation wins, and
    # whether it holds the lock, is non-deterministic). This partial unique
    # index rejects the second INSERT regardless; both writers catch the
    # IntegrityError and fall back to update-in-place / skip. Partial on
    # `was_cancelled = false` so a withdrawn annotation never blocks a resubmit.
    __table_args__ = (
        sa.Index(
            "uq_annotations_active_task_user",
            "task_id",
            "completed_by",
            unique=True,
            postgresql_where=sa.text("was_cancelled = false"),
        ),
    )

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
    reviewed_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
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


class TimerSession(Base):
    """Server-side timer tracking — annotation sessions (issue #1205) and
    korrektur sessions (issue #30 PR 3).

    Decoupled from TaskAssignment to support open-mode projects where no
    assignment records exist. Each record represents one user starting to
    work on one (task, target) — for annotation `target_type='task'` and
    `target_id=NULL`; for korrektur `target_type` in {'annotation',
    'generation'} and `target_id` points at the row being graded.

    Renamed from `annotation_timer_sessions` in migration 050. The legacy
    `AnnotationTimerSession` symbol is preserved as an alias below so the
    extended worker and any external imports keep working through the
    transition.
    """

    __tablename__ = "timer_sessions"

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

    # Polymorphic target (issue #30 PR 3).
    # 'task' for annotation flows (target_id NULL); 'annotation' or
    # 'generation' for korrektur flows (target_id points at the row).
    target_type = Column(String, nullable=False, server_default="task")
    target_id = Column(String, nullable=True)

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
        # Wider uniqueness — see migration 050. The COALESCE-on-target_id
        # expression-index is created in SQL (not declared here) so a NULL
        # target_id still de-dups against the literal 'task' rows.
        sa.Index("ix_timer_session_project_user", "project_id", "user_id"),
    )


# Back-compat alias — existing imports of `AnnotationTimerSession` keep
# working without churn. New code should import `TimerSession` directly.
AnnotationTimerSession = TimerSession


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


class TaskDraftCheckpoint(Base):
    """Append-only restorable draft checkpoints (opt-in per project).

    Unlike ``TaskDraft`` (a single overwrite-in-place row, deleted on submit),
    this stores a HISTORY of periodic snapshots: one row per checkpoint, never
    overwritten and NOT deleted on submit, so an annotator can restore an
    earlier checkpoint. Written only when the project's
    ``restorable_checkpoints_enabled`` is true; retention is bounded by a cap
    enforced at the write endpoint.
    """

    __tablename__ = "task_draft_checkpoints"

    id = Column(String, primary_key=True, index=True)
    task_id = Column(String, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    draft_result = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        sa.Index(
            "ix_task_draft_checkpoints_task_user_created",
            "task_id",
            "user_id",
            "created_at",
        ),
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
    resolved_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

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


class FlashcardSrsState(Base):
    """Per-user spaced-repetition (SM-2) state for one flashcard task.

    Each deck is a project and each card is a task; SRS state is a per-user
    sidecar so a deck stays benchmarkable in the expert view while every
    student carries their own schedule. Platform owns the table (persistence);
    the SM-2 algorithm that mutates it lives in the extended worker. This is a
    mutable *snapshot* of the current scheduling state — the append-only
    ``flashcard_reviews`` table carries the history for retention charts.
    """

    __tablename__ = "flashcard_srs_state"

    id = Column(String, primary_key=True, index=True)
    task_id = Column(
        String, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    project_id = Column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )

    # SM-2 scheduling fields
    ease_factor = Column(Float, default=2.5, server_default="2.5", nullable=False)
    interval_days = Column(Float, default=0, server_default="0", nullable=False)
    due_at = Column(DateTime(timezone=True), nullable=True)
    reps = Column(Integer, default=0, server_default="0", nullable=False)
    lapses = Column(Integer, default=0, server_default="0", nullable=False)
    learning_step = Column(Integer, default=0, server_default="0", nullable=False)
    # state: "new" | "learning" | "review" | "relearning"
    state = Column(String(16), default="new", server_default="new", nullable=False)
    # last_rating: "again" | "hard" | "good" | "easy"
    last_rating = Column(String(8), nullable=True)
    last_reviewed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    task = relationship("Task")
    user = relationship("User")
    project = relationship("Project")

    __table_args__ = (
        sa.UniqueConstraint("task_id", "user_id", name="uq_flashcard_srs_task_user"),
        # Hot path: "what's due for this user right now".
        sa.Index("ix_flashcard_srs_user_due", "user_id", "due_at"),
        sa.Index("ix_flashcard_srs_project", "project_id"),
    )

    def __repr__(self):
        return f"<FlashcardSrsState(task_id={self.task_id}, user_id={self.user_id}, state={self.state})>"


class FlashcardReview(Base):
    """Append-only log of every flashcard review (one row per review event).

    Distinct from ``FlashcardSrsState`` (a mutable snapshot): this table never
    updates a row, so it preserves the full per-card history needed for
    retention/score-over-time charts and keeps the door open for a future FSRS
    optimizer (which requires the complete review log). Graded-mode answers and
    judge scores live here — never in Annotation/TaskEvaluation, which would
    pollute benchmarking data and the human leaderboards.
    """

    __tablename__ = "flashcard_reviews"

    id = Column(String, primary_key=True, index=True)
    task_id = Column(
        String, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    project_id = Column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )

    # "quick" (self-rated) | "graded" (judge-scored)
    mode = Column(String(8), nullable=False)
    # Final rating that drove the schedule: again | hard | good | easy
    rating = Column(String(8), nullable=False)
    # Graded mode only: the short-answer judge score (0..1) + the typed answer.
    judge_score = Column(Float, nullable=True)
    answer_text = Column(Text, nullable=True)
    # Scheduling result snapshot (for charts without re-deriving from state).
    interval_days_after = Column(Float, nullable=True)
    ease_factor_after = Column(Float, nullable=True)

    reviewed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    task = relationship("Task")
    user = relationship("User")
    project = relationship("Project")

    __table_args__ = (
        sa.Index("ix_flashcard_reviews_user_reviewed", "user_id", "reviewed_at"),
        sa.Index("ix_flashcard_reviews_project", "project_id"),
        sa.Index("ix_flashcard_reviews_task", "task_id"),
    )

    def __repr__(self):
        return f"<FlashcardReview(task_id={self.task_id}, user_id={self.user_id}, mode={self.mode}, rating={self.rating})>"


class FlashcardSrsSettings(Base):
    """Per-user, per-collection daily study limits (Anki-style caps).

    The SRS sidecar is per-user, so the daily caps are too: each student paces
    themselves on a shared deck. ``new_per_day`` caps how many never-seen cards
    are introduced per day; ``review_per_day`` caps review cards shown per day
    and — Anki-faithfully — also gates new cards once the review budget is spent.
    ``NULL`` on either means "use the system default" (see the constants in
    ``routers/projects/srs.py``). Platform owns the table (persistence + the
    generic limit application in the read endpoints); only the student-facing
    settings UI is extended.
    """

    __tablename__ = "flashcard_srs_settings"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    project_id = Column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )

    # NULL => fall back to the system default cap.
    new_per_day = Column(Integer, nullable=True)
    review_per_day = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User")
    project = relationship("Project")

    __table_args__ = (
        sa.UniqueConstraint(
            "user_id", "project_id", name="uq_flashcard_srs_settings_user_project"
        ),
        sa.Index(
            "ix_flashcard_srs_settings_user_project", "user_id", "project_id"
        ),
    )

    def __repr__(self):
        return f"<FlashcardSrsSettings(user_id={self.user_id}, project_id={self.project_id})>"


class ProjectShareLink(Base):
    """A password-protected share link for a project (student exam sharing).

    The owner mints a link with a bcrypt-hashed password; an invitee (who must
    have a BenGER account) joins by entering the password, which creates a
    ``ProjectShareMember`` row. Lifecycle: ``expires_at`` / ``max_uses`` /
    ``revoked_at`` gate JOIN only; member eviction gates ongoing access.
    Password is hashed via the platform bcrypt helper — never md5/FIPS.
    """

    __tablename__ = "project_share_links"

    id = Column(String, primary_key=True, index=True)
    token = Column(String(64), nullable=False, unique=True, index=True)
    project_id = Column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    created_by = Column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    password_hash = Column(String, nullable=False)

    expires_at = Column(DateTime(timezone=True), nullable=True)
    max_uses = Column(Integer, nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    # When true, the share surfaces in the global discovery directory so other
    # students can find it and join with the password (issue #35). Opt-in:
    # owners who only paste the link out-of-band leave it false.
    is_listed = Column(
        Boolean, default=False, server_default="false", nullable=False, index=True
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    project = relationship("Project")
    creator = relationship("User", foreign_keys=[created_by])
    members = relationship(
        "ProjectShareMember", back_populates="share_link", cascade="all, delete-orphan"
    )

    __table_args__ = (
        sa.Index("ix_project_share_links_project", "project_id"),
        sa.Index("ix_project_share_links_created_by", "created_by"),
    )

    def __repr__(self):
        return f"<ProjectShareLink(id={self.id}, project_id={self.project_id})>"


class ProjectShareMember(Base):
    """Membership of a user in a shared project, captured at join time.

    GDPR: ``gdpr_consent_at`` (+ ``consent_version``) records consent to share
    identifiable performance data with the owner/cohort; roster and cohort
    leaderboard reads gate on it. Scores are NOT denormalized here — best/last
    are computed from ``task_evaluations`` at read time to avoid drift on
    re-grades. ``attempts`` is a cheap counter for the roster.
    """

    __tablename__ = "project_share_members"

    id = Column(String, primary_key=True, index=True)
    share_link_id = Column(
        String, ForeignKey("project_share_links.id", ondelete="CASCADE"), nullable=False
    )
    project_id = Column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    attempts = Column(Integer, default=0, server_default="0", nullable=False)
    gdpr_consent_at = Column(DateTime(timezone=True), nullable=True)
    consent_version = Column(String(16), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    share_link = relationship("ProjectShareLink", back_populates="members")
    project = relationship("Project")
    user = relationship("User")

    __table_args__ = (
        sa.UniqueConstraint("share_link_id", "user_id", name="uq_project_share_member"),
        sa.Index("ix_project_share_members_project", "project_id"),
        sa.Index("ix_project_share_members_user", "user_id"),
    )

    def __repr__(self):
        return f"<ProjectShareMember(share_link_id={self.share_link_id}, user_id={self.user_id})>"


class MarketplaceListing(Base):
    """A vendor's published, priced offering of a project (exam or deck).

    Surfaces the project in the global student discovery directory with a
    price. At most one listing per project. ``published`` gates visibility; a
    listing may only be published while the owning vendor org has a
    ``VendorAccount`` with ``charges_enabled`` (enforced in the listing router,
    not the schema). Persistence only — the Stripe Connect checkout that turns a
    listing into an entitlement lives in ``benger_extended``.
    """

    __tablename__ = "marketplace_listings"

    id = Column(String, primary_key=True, index=True)
    project_id = Column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    vendor_org_id = Column(
        String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # Denormalized from the project for a cheap discover filter / badge.
    kind = Column(String(32), nullable=True)
    price_cents = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False, default="eur")
    published = Column(
        Boolean, default=False, server_default="false", nullable=False, index=True
    )
    description = Column(Text, nullable=True)
    # Vendor human grading (optional add-on). ``grading_mode`` declares how the
    # exam is graded: ``ai`` (instant LLM judge only), ``human`` (a vendor
    # corrector grades it), or ``both``. When human/both, the vendor offers a
    # separately-priced human-grading add-on at ``human_grading_price_cents``
    # granting ``human_grading_quantity`` graded-submission credits per purchase.
    grading_mode = Column(
        String(16), nullable=False, default="ai", server_default="ai"
    )
    human_grading_price_cents = Column(Integer, nullable=True)
    human_grading_quantity = Column(
        Integer, nullable=False, default=1, server_default="1"
    )
    created_by = Column(
        String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    project = relationship("Project")
    vendor_org = relationship("Organization")

    __table_args__ = (
        sa.UniqueConstraint("project_id", name="uq_marketplace_listing_project"),
        sa.Index("ix_marketplace_listings_vendor_org", "vendor_org_id"),
    )

    def __repr__(self):
        return (
            f"<MarketplaceListing(id={self.id}, project_id={self.project_id}, "
            f"published={self.published})>"
        )


class MarketplaceEntitlement(Base):
    """A student's permanent access grant to a vendor marketplace item.

    The access row for purchased or vendor-unlocked items. Mirrors the narrow
    *participant* tier a consented ``ProjectShareMember`` grants — it is checked
    by ``get_entitlement_access_async`` alongside share access and NEVER routes
    through ``check_project_accessible`` (so the Musterlösung and other
    students' attempts stay gated exactly as for share members). At most one
    entitlement per (user, project), which makes purchase/grant idempotent.
    ``source`` is ``purchase`` (paid via Stripe Connect) or ``vendor_grant``
    (free unlock by vendor staff). ``revoked_at`` supports manual revocation —
    refunds are manual in v1.
    """

    __tablename__ = "marketplace_entitlements"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    project_id = Column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    listing_id = Column(
        String, ForeignKey("marketplace_listings.id", ondelete="SET NULL"), nullable=True
    )
    # purchase | vendor_grant
    source = Column(String(16), nullable=False)
    order_id = Column(
        String, ForeignKey("marketplace_orders.id", ondelete="SET NULL"), nullable=True
    )
    # Vendor staff who granted a free unlock (NULL for purchases).
    granted_by = Column(
        String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    granted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    project = relationship("Project")
    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        sa.UniqueConstraint(
            "user_id", "project_id", name="uq_marketplace_entitlement_user_project"
        ),
        sa.Index("ix_marketplace_entitlements_user", "user_id"),
        sa.Index("ix_marketplace_entitlements_project", "project_id"),
    )

    def __repr__(self):
        return (
            f"<MarketplaceEntitlement(id={self.id}, user_id={self.user_id}, "
            f"project_id={self.project_id}, source={self.source})>"
        )


class MarketplaceGradingCredit(Base):
    """A student's human-grading wallet for a vendor exam (one per user+project).

    Buying the human-grading add-on increments ``total_credits`` by the
    listing's ``human_grading_quantity``; requesting a human grade on an attempt
    increments ``used_credits``. ``total_credits - used_credits`` is what's
    available. Persistence only — the credit-grant (on the paid Connect webhook)
    and consumption decisions live in ``benger_extended``. ``revoked_at``
    supports manual revocation.
    """

    __tablename__ = "marketplace_grading_credits"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    project_id = Column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    vendor_org_id = Column(
        String, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    listing_id = Column(
        String, ForeignKey("marketplace_listings.id", ondelete="SET NULL"), nullable=True
    )
    total_credits = Column(Integer, nullable=False, default=0, server_default="0")
    used_credits = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", foreign_keys=[user_id])
    project = relationship("Project")

    __table_args__ = (
        sa.UniqueConstraint(
            "user_id", "project_id", name="uq_marketplace_grading_credit_user_project"
        ),
        sa.Index("ix_marketplace_grading_credits_user", "user_id"),
        sa.Index("ix_marketplace_grading_credits_project", "project_id"),
    )

    def __repr__(self):
        return (
            f"<MarketplaceGradingCredit(user_id={self.user_id}, "
            f"project_id={self.project_id}, "
            f"available={self.total_credits - self.used_credits})>"
        )


class MarketplaceGradingRequest(Base):
    """A student attempt submitted for vendor human grading (one per attempt).

    Created when a student with an available human-grading credit asks for an
    attempt to be graded — it consumes a credit and becomes the vendor
    correctors' queue item. The corrector grades via the existing korrektur
    falloesung endpoint (writing a ``TaskEvaluation`` keyed by grader); this row
    is then marked ``completed`` and linked to that grade. Persistence only —
    the queue gating + credit consumption live in ``benger_extended``.
    """

    __tablename__ = "marketplace_grading_requests"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    project_id = Column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    annotation_id = Column(
        String, ForeignKey("annotations.id", ondelete="CASCADE"), nullable=False
    )
    vendor_org_id = Column(
        String, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    listing_id = Column(
        String, ForeignKey("marketplace_listings.id", ondelete="SET NULL"), nullable=True
    )
    # pending | completed | cancelled
    status = Column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    assigned_grader_id = Column(
        String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    task_evaluation_id = Column(
        String, ForeignKey("task_evaluations.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", foreign_keys=[user_id])
    project = relationship("Project")

    __table_args__ = (
        sa.UniqueConstraint(
            "annotation_id", name="uq_marketplace_grading_request_annotation"
        ),
        sa.Index("ix_marketplace_grading_requests_vendor_status", "vendor_org_id", "status"),
        sa.Index("ix_marketplace_grading_requests_user", "user_id"),
    )

    def __repr__(self):
        return (
            f"<MarketplaceGradingRequest(id={self.id}, "
            f"annotation_id={self.annotation_id}, status={self.status})>"
        )
