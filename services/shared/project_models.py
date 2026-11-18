"""
Database models for BenGER project and task management

Clean, functional naming without verbose or branded terms.
"""

import sqlalchemy as sa
from sqlalchemy import BigInteger, JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import DATABASE_URL, Base

# Same rule as models.py: JSON only on a SQLite test engine.
if DATABASE_URL.startswith("sqlite"):
    from sqlalchemy import JSON as JSONB
else:
    from sqlalchemy.dialects.postgresql import JSONB


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
    # Whether the solver sees the per-step detail of their grading (step
    # scores, reasons, evidence, the filled sheet) after submitting. NULL =
    # follow ``annotator_full_visibility_after_submit`` (the reference
    # reveal); True/False decide it on its own, so an exam can show the
    # grading steps while the reference stays hidden. Read it through
    # ``solution_reveal.step_detail_revealed`` (migration 116).
    annotator_step_detail_after_submit = Column(Boolean, nullable=True)

    # Whether annotators may paste text copied outside BenGER into the
    # annotation interface. Default True; False makes the labeling UI reject
    # pastes and drops whose text was not copied inside the app (mig 123).
    allow_external_paste = Column(
        Boolean, default=True, server_default=sa.true(), nullable=False
    )
    # Whether annotators may hand in their answer as a file (the overlay's
    # solution upload, itself behind a feature flag). Default True; False
    # hides the upload for the writer, uploads on someone's behalf stay
    # possible (mig 124).
    allow_solution_upload = Column(
        Boolean, default=True, server_default=sa.true(), nullable=False
    )

    # Handwritten solution uploads (photos, scans) transcribed by a vision
    # model (mig 125). ``handwriting_ocr_enabled`` switches them on for the
    # project; ``handwriting_ocr_model`` overrides the model, NULL = the
    # organization's default (``organizations.settings.handwriting_ocr_model``,
    # see ``shared/org_ocr.py``). The OCR flow itself is an extended feature.
    handwriting_ocr_enabled = Column(
        Boolean, default=False, server_default=sa.false(), nullable=False
    )
    handwriting_ocr_model = Column(String(255), nullable=True)

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
    # Enabled by default for all new projects so timed exams get an automatic
    # append-only recovery history out of the box (opt out via ProjectUpdate).
    # Existing projects keep whatever they were set to; only the default for
    # future inserts changes (see migration 075).
    restorable_checkpoints_enabled = Column(
        Boolean, default=True, server_default="true", nullable=False
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
    generation_config = Column(JSON, nullable=True)

    # LLM Model IDs for generation (Issue #XXX - Model Selection Persistence)
    llm_model_ids = Column(JSON, nullable=True)

    # Evaluation configuration (Issue #483)
    evaluation_config = Column(JSON, nullable=True)

    # Visibility
    is_private = Column(Boolean, default=False, nullable=False, index=True)
    is_public = Column(Boolean, default=False, nullable=False, server_default="false")
    public_role = Column(String(32), nullable=True)

    # Project kind / origin (extended-edition student experience). Both are
    # free-form nullable strings — NOT Postgres ENUMs — so the community
    # edition ships a forward-compatible schema and an extended overlay can
    # introduce new kinds without an ALTER TYPE. `kind` distinguishes a
    # student exam ("exam") or flashcard collection ("flashcard_collection") from a plain
    # benchmark project (NULL). `origin` marks student-generated projects
    # ("student") so they can be excluded from public leaderboards while
    # remaining benchmarkable in the expert view. Write-once at creation.
    kind = Column(String(32), nullable=True, index=True)
    origin = Column(String(32), nullable=True, index=True)
    # User-chosen emoji shown in lists / headers / discover (migration 092).
    icon = Column(String(16), nullable=True)
    # Soft delete (migration 093): a stamped project is invisible to EVERYONE
    # except superadmins (restore/purge from the deleted view). Data in every
    # cascading table survives until an explicit superadmin purge.
    # Partial index (deleted_at IS NOT NULL) created by migration 093.
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Feature visibility — controls which configuration cards render on the
    # project detail page. Hides the card; underlying data is preserved and
    # the relevant API endpoints stay open. Defaults preserve back-compat for
    # existing projects.
    enable_annotation = Column(Boolean, default=True, server_default="true", nullable=False)
    enable_generation = Column(Boolean, default=True, server_default="true", nullable=False)
    enable_evaluation = Column(Boolean, default=True, server_default="true", nullable=False)
    enable_prompts = Column(Boolean, default=True, server_default="true", nullable=False)

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

    # Safe Exam Browser (migration 109). When ``seb_required`` is true, exam
    # content reads and exam writes by non-editors must come from SEB with an
    # accepted Config Key (see /shared/seb.py and enforce_seb in
    # routers/projects/helpers.py). ``seb_config`` holds the settings the
    # extended edition builds the .seb file from plus the accepted keys:
    # ``generated_config_key``, ``extra_config_keys`` and
    # ``browser_exam_keys`` (list of {"key", "label"}; empty = BEK unchecked).
    seb_required = Column(Boolean, default=False, server_default="false", nullable=False)
    seb_config = Column(JSONB, nullable=True)

    # Exam tools (Hilfsmittel) the writers may use in the exam interface:
    # calculator, calendar, law texts, ... (migration 127; shape in
    # /shared/exam_tools.py). NULL = never chosen, the interfaces keep their
    # built-in defaults. Written only by the extended edition's endpoint.
    exam_tools = Column(JSONB, nullable=True)

    # Check step for grading sheets (migration 137). When true, a task rubric
    # becomes active only after a person confirmed it
    # (``task_rubrics.review_state = 'confirmed'``); every activation goes
    # through ``task_rubric_service.activate_task_rubric``, which enforces it.
    # Set server-side by the extended edition (new exams), read-only to
    # ordinary clients. False keeps the behaviour of every existing project.
    rubric_review_required = Column(
        Boolean, default=False, server_default="false", nullable=False
    )

    # Creation-wizard draft (migration 141): a real project the wizard
    # creates for an unfinished exam so its tasks and grading sheets exist
    # (and can be checked) before "Create". A draft is private, has no
    # organization rows and is kept out of every list and count by
    # ``project_listable()``; its target scope, wizard state and expiry live
    # in ``project_wizard_drafts``. The finish route clears the flag and
    # applies the visibility in one transaction.
    is_wizard_draft = Column(
        Boolean, default=False, server_default="false", nullable=False
    )

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
        # The caller's drafts (the wizard's "unfinished projects" list) and
        # the stale-draft sweep; only draft rows are indexed.
        sa.Index(
            "ix_projects_wizard_draft",
            "created_by",
            postgresql_where=sa.text("is_wizard_draft"),
        ),
    )

    def __repr__(self):
        return f"<Project(id={self.id}, title={self.title})>"


class ProjectWizardDraft(Base):
    """The wizard side of a draft project (migration 141).

    One row per project with ``is_wizard_draft = true``: where the finished
    project will live (``target_organization_id`` / ``target_group_id``,
    validated with the create rules and applied by the finish route), the
    serializable wizard state with its optimistic-concurrency version, and
    ``touched_at``, from which the stale-draft sweep counts the retention.
    Kept after the finish route (``finished_at`` set, ``state`` cleared) so a
    repeated finish with the same ``client_key`` is recognized; cascades with
    the project.
    """

    __tablename__ = "project_wizard_drafts"

    project_id = Column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    created_by = Column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # Generated by the wizard when it mounts: a repeated create with the same
    # key returns the existing draft, and a repeated finish is recognized.
    client_key = Column(String(64), nullable=False)
    target_organization_id = Column(
        String, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    # SET NULL, unlike the attachment's group key: deleting a group or an
    # organization must never be blocked by somebody's unfinished draft.
    target_group_id = Column(
        String, ForeignKey("organization_groups.id", ondelete="SET NULL"), nullable=True
    )
    state = Column(JSONB, nullable=True)
    state_version = Column(Integer, nullable=False, default=1, server_default="1")
    step_id = Column(String(64), nullable=True)
    touched_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        sa.UniqueConstraint(
            "created_by", "client_key", name="uq_project_wizard_drafts_client_key"
        ),
        sa.Index("ix_project_wizard_drafts_touched_at", "touched_at"),
    )

    def __repr__(self):
        return f"<ProjectWizardDraft(project_id={self.project_id})>"


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

    # Data fields. data/meta (like projects.generation_config/evaluation_config,
    # comment_authors and data_exports.filters) are plain json in the database,
    # not jsonb: jsonb would reorder the keys of imported task data. Cast to
    # JSONB in a query that needs jsonb operators.
    data = Column(JSON, nullable=False)  # The actual data to annotate
    meta = Column(JSON, nullable=True)  # Optional metadata
    # Id of the task this row was imported from, kept across repeated imports
    # (the original's id, not an intermediate copy's); NULL for tasks created
    # here. A merge import matches exported tasks to this project's by it
    # (migration 130).
    source_task_id = Column(String, nullable=True)

    # The task's place in a variant design, derived by the database from
    # ``meta.variant`` (``design``, ``unit``, ``factors``) on every write: the
    # trigger of :data:`TASKS_VARIANT_DDL` (migration 142) overwrites whatever
    # a writer sends, so ``meta.variant`` stays the single source of truth.
    # ``uq_tasks_variant_cell`` allows one task per cell and unit (the jsonb
    # cell compares regardless of key order); ``fk_tasks_variant_design``
    # makes the design exist. Never write these columns.
    variant_design = Column(
        String(100), nullable=True, server_default=sa.FetchedValue(),
        server_onupdate=sa.FetchedValue(),
    )
    variant_unit = Column(
        Text, nullable=True, server_default=sa.FetchedValue(),
        server_onupdate=sa.FetchedValue(),
    )
    variant_cell = Column(
        JSONB, nullable=True, server_default=sa.FetchedValue(),
        server_onupdate=sa.FetchedValue(),
    )

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
    comment_authors = Column(JSON, nullable=True)

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

    __table_args__ = (
        sa.Index(
            "uq_tasks_variant_cell",
            "project_id",
            "variant_design",
            "variant_unit",
            "variant_cell",
            unique=True,
            postgresql_where=sa.text("variant_design IS NOT NULL"),
        ),
        # Not deferrable: a deferred key would leave a pending trigger event
        # for every task a transaction inserts, and a later ALTER TABLE tasks
        # in that transaction would fail. The unit of work does not order the
        # two tables, so a writer flushes a new design before its tasks (the
        # importers do). NO ACTION is checked at the end of each statement,
        # so a project's delete cascades through both tables.
        sa.ForeignKeyConstraint(
            ["project_id", "variant_design"],
            ["variant_designs.project_id", "variant_designs.key"],
            name="fk_tasks_variant_design",
        ),
    )

    def __repr__(self):
        return f"<Task(id={self.id}, project_id={self.project_id}, is_labeled={self.is_labeled})>"


class VariantDesign(Base):
    """The declared design of a variant experiment in a project (CORE 2.56).

    ``spec`` follows ``schemas/variant_design.schema.json`` (factors with
    typed levels and roles, the unit, slots, outcome, gold and invariance
    bindings; see ``variant_designs``). Each task's place in the design is
    ``task.meta.variant`` with ``design`` = :attr:`key`.

    ``version`` counts the spec edits of a draft. Freezing (``status
    'frozen'``) runs the balance and invariance checks, records
    ``content_hash`` (spec plus every task's data and assignment) and makes
    the tasks' ``data`` and ``meta.variant`` read-only: the trigger of
    :data:`TASKS_VARIANT_DDL` refuses such edits and new tasks in the design.
    A frozen design is never thawed; a changed experiment is a new design.
    """

    __tablename__ = "variant_designs"

    id = Column(String, primary_key=True)  # uuid4 str
    project_id = Column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key = Column(String(100), nullable=False)
    version = Column(Integer, nullable=False, default=1, server_default="1")
    spec = Column(JSONB, nullable=False)
    status = Column(String(16), nullable=False, default="draft", server_default="draft")
    content_hash = Column(String(64), nullable=True)
    frozen_at = Column(DateTime(timezone=True), nullable=True)
    frozen_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # Who or what made the design (generator name and version, code hashes,
    # source commit); free-form.
    provenance = Column(JSONB, nullable=True)
    created_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        sa.UniqueConstraint("project_id", "key", name="uq_variant_designs_project_key"),
        sa.CheckConstraint("status IN ('draft', 'frozen')", name="ck_variant_designs_status"),
        sa.CheckConstraint(
            "(status = 'frozen') = (content_hash IS NOT NULL AND frozen_at IS NOT NULL)",
            name="ck_variant_designs_frozen_hash",
        ),
    )


# The derived variant columns of ``tasks`` and the frozen-design guard.
# Migration 142 runs the same statements (kept verbatim there; a migration
# never imports the models); a schema built with ``Base.metadata.create_all``
# (the test databases) gets them through the ``after_create`` listener below.
#
# The trigger takes a share lock on the design row, so a freeze (which locks
# the row for update before it reads the tasks) and a task write never
# interleave: the write either lands before the freeze reads, or sees the
# frozen status and fails. The error message starts with
# ``variant_design_frozen`` (SQLSTATE 23001), which the API maps to 409.
TASKS_VARIANT_FUNCTION = """
CREATE OR REPLACE FUNCTION tasks_variant_sync() RETURNS trigger AS $fn$
DECLARE
    new_meta jsonb := NEW.meta::jsonb;
    new_variant jsonb;
    old_variant jsonb;
    design_status text;
BEGIN
    IF jsonb_typeof(new_meta) = 'object' AND jsonb_typeof(new_meta -> 'variant') = 'object' THEN
        new_variant := new_meta -> 'variant';
        NEW.variant_design := new_variant ->> 'design';
        NEW.variant_unit := new_variant ->> 'unit';
        NEW.variant_cell := new_variant -> 'factors';
    ELSE
        NEW.variant_design := NULL;
        NEW.variant_unit := NULL;
        NEW.variant_cell := NULL;
    END IF;

    IF TG_OP = 'UPDATE' AND OLD.variant_design IS NOT NULL THEN
        SELECT d.status INTO design_status FROM variant_designs d
         WHERE d.project_id = OLD.project_id AND d.key = OLD.variant_design
           FOR SHARE;
        IF design_status = 'frozen' THEN
            IF jsonb_typeof(OLD.meta::jsonb) = 'object' THEN
                old_variant := OLD.meta::jsonb -> 'variant';
            END IF;
            IF NEW.project_id IS DISTINCT FROM OLD.project_id
               OR NEW.data::jsonb IS DISTINCT FROM OLD.data::jsonb
               OR new_variant IS DISTINCT FROM old_variant THEN
                RAISE EXCEPTION USING ERRCODE = 'restrict_violation',
                    MESSAGE = 'variant_design_frozen: task ' || OLD.id
                        || ' belongs to the frozen variant design ' || OLD.variant_design
                        || '; its data and meta.variant are read-only';
            END IF;
            RETURN NEW;
        END IF;
    END IF;

    IF NEW.variant_design IS NOT NULL AND (
        TG_OP = 'INSERT'
        OR NEW.variant_design IS DISTINCT FROM OLD.variant_design
        OR NEW.project_id IS DISTINCT FROM OLD.project_id
    ) THEN
        SELECT d.status INTO design_status FROM variant_designs d
         WHERE d.project_id = NEW.project_id AND d.key = NEW.variant_design
           FOR SHARE;
        IF design_status = 'frozen' THEN
            RAISE EXCEPTION USING ERRCODE = 'restrict_violation',
                MESSAGE = 'variant_design_frozen: the variant design ' || NEW.variant_design
                    || ' is frozen and takes no new tasks';
        END IF;
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql
"""
TASKS_VARIANT_TRIGGER = """
CREATE OR REPLACE TRIGGER trg_tasks_variant_sync
BEFORE INSERT OR UPDATE OF meta, data, project_id, variant_design, variant_unit, variant_cell
ON tasks
FOR EACH ROW EXECUTE FUNCTION tasks_variant_sync()
"""
TASKS_VARIANT_DDL = (TASKS_VARIANT_FUNCTION, TASKS_VARIANT_TRIGGER)
for _statement in TASKS_VARIANT_DDL:
    sa.event.listen(
        Task.__table__,
        "after_create",
        sa.DDL(_statement).execute_if(dialect="postgresql"),
    )
del _statement


@sa.event.listens_for(sa.orm.Session, "before_flush")
def _validate_task_variants_before_flush(session, flush_context, instances):
    """Validate ``meta.variant`` of every task this flush writes against its
    design (every ORM write path: imports, PATCH routes, wizard drafts, ...).
    Raises ``variant_design_guard.VariantDesignError``."""
    from variant_design_guard import check_session_tasks

    check_session_tasks(session)


class Annotation(Base):
    """
    Annotation model - human annotations on tasks
    """

    __tablename__ = "annotations"

    # One active (non-cancelled) annotation per (task, user). This is the
    # DB-level guarantee against duplicate submissions: a strict-timer task has
    # two concurrent writers — the client auto-submit (POST /annotations) and
    # the server-side timer worker (tasks.auto_submit_expired_timer, extended) —
    # and an advisory lock alone proved fragile (a writer can bypass it). This
    # partial unique index rejects the second INSERT regardless; both writers
    # catch the
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
    filters = Column(JSON, nullable=True)
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
    # Optional group scope inside the org: NULL = visible to the whole org
    # (pre-groups behavior); set = visible only to that group's members,
    # the org's ORG_ADMINs, the creator, and superadmins. Composite FK with
    # organization_id (see __table_args__) so an attachment can only carry
    # a group of its own org.
    group_id = Column(String, nullable=True, index=True)
    assigned_by = Column(String, ForeignKey("users.id"), nullable=False)
    # How the attachment came about: 'manual' (project create, visibility
    # settings, import) or 'lti' (linking the exam to an LMS activity of a
    # connection of this org). Migration 106.
    attached_via = Column(
        String(16), nullable=False, default="manual", server_default="manual"
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    project = relationship("Project", back_populates="project_organizations")
    organization = relationship("Organization")
    group = relationship(
        "OrganizationGroup",
        primaryjoin="foreign(ProjectOrganization.group_id) == OrganizationGroup.id",
        viewonly=True,
    )
    assigner = relationship("User")

    __table_args__ = (
        # One attachment per (project, org) — an org-attached project is
        # either org-wide or in exactly ONE group of that org (v1 limit).
        sa.UniqueConstraint("project_id", "organization_id", name="unique_project_organization"),
        # The attachment's group must belong to the attachment's org
        # (MATCH SIMPLE: NULL group_id rows are unconstrained). Deliberately
        # NO ondelete action — a direct group delete with live attachments
        # must fail (no silent visibility widening), while org deletion
        # still works because the org→groups and org→project_organizations
        # CASCADEs both resolve before this NO ACTION check runs at
        # end-of-statement.
        sa.ForeignKeyConstraint(
            ["organization_id", "group_id"],
            ["organization_groups.organization_id", "organization_groups.id"],
            name="fk_project_organizations_group_scope",
        ),
        sa.CheckConstraint(
            "attached_via IN ('manual', 'lti')",
            name="ck_project_organizations_attached_via",
        ),
    )

    def __repr__(self):
        return f"<ProjectOrganization(project_id={self.project_id}, org_id={self.organization_id})>"


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

    # Non-strict pause/resume (extended feature; strict sessions never pause).
    # paused_at marks an OPEN pause; total_paused_seconds accumulates closed
    # ones. Effective elapsed = (now - started_at) - total_paused_seconds
    # - (now - paused_at when paused).
    paused_at = Column(DateTime(timezone=True), nullable=True)
    total_paused_seconds = Column(Integer, nullable=False, default=0, server_default="0")

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


class ExamToolNote(Base):
    """A writer's scratch notes for one task from the notes exam tool
    (migration 127). One row per (task, user), overwritten in place; never
    graded and not part of exports. Written by the extended edition."""

    __tablename__ = "exam_tool_notes"

    id = Column(String, primary_key=True, index=True)
    task_id = Column(String, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    text = Column(Text, nullable=False, default="", server_default="")
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        sa.UniqueConstraint("task_id", "user_id", name="uq_exam_tool_notes_task_user"),
    )


class TaskWorkPresence(Base):
    """Whether a user has a task's writing page open right now (migration 117).

    One row per (task, user), overwritten in place; no history. Written by
    the extended edition (heartbeat of the open writing page, closed on
    submit); the platform only owns the table.
    """

    __tablename__ = "task_work_presence"

    id = Column(String, primary_key=True, index=True)
    task_id = Column(String, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # Whether the writing tab was in the foreground at the last touch.
    visible = Column(Boolean, nullable=False, default=True, server_default=sa.true())
    # Set when the user submits the task; the next touch opens a new session.
    ended_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        sa.UniqueConstraint("task_id", "user_id", name="uq_task_work_presence_task_user"),
        sa.Index("ix_task_work_presence_project_seen", "project_id", "last_seen_at"),
        sa.Index("ix_task_work_presence_user_id", "user_id"),
    )


class KorrekturReservation(Base):
    """A grader has one target of a Korrektur queue open right now (migration 119).

    One row per (user, metric, target), refreshed in place by a heartbeat
    while the grading modal is open and deleted on submit or close. A row
    whose ``last_seen_at`` is older than the overlay's TTL counts as gone.
    Written by the extended edition, which uses it to keep a second grader
    away from the last free slot of a capped target; the platform only owns
    the table.
    """

    __tablename__ = "korrektur_reservations"

    id = Column(String, primary_key=True, index=True)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    task_id = Column(String, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    metric = Column(String, nullable=False)
    # 'annotation' or 'generation'; target_id points at that row.
    target_type = Column(String, nullable=False)
    target_id = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        sa.UniqueConstraint(
            "user_id", "metric", "target_type", "target_id",
            name="uq_korrektur_reservation_user_target",
        ),
        sa.Index("ix_korrektur_reservations_project_metric", "project_id", "metric"),
        sa.Index("ix_korrektur_reservations_task_id", "task_id"),
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
    # purchase | vendor_grant | discovered (extended catalog enrollment —
    # soft-revoked by "leave"/unenroll, unlike paid grants)
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


class TaskRubric(Base):
    """Per-task grading rubric (Bewertungsbogen) — an exam-specific 100-point
    step scheme consumed by the ``llm_judge_rubric`` metric and (task-aware)
    korrektur grading.

    Platform owns only the persistence and generic reads; the generation
    workflow (LLM prompting, parsing, renormalization, activation policy)
    lives in the extended worker (``bewertungsbogen_tasks``).

    ``structure`` (migration 100) is the canonical outline of the rubric:
    ``{"version": 1, "nodes": [...]}`` — ordered, depth-first ``section`` and
    ``step`` nodes with labels, hints, Schwerpunkt markers and section notes
    (contract in ``services/shared/rubric_structure.py``). Uploaded,
    AI-drafted and hand-written rubrics all carry one; legacy rows keep
    ``structure = NULL`` and their hand-written criteria.

    ``criteria`` is a ``custom_criteria``-shaped dict
    ``{step_key: {name, description, rubric, max_score}}`` so the multi-dim
    LLM-judge schema builder and the korrektur_custom grading form consume it
    unchanged. When a structure is present the criteria are DERIVED from it
    on every write (``criteria_from_structure``). ``max_score`` and
    ``total_points`` are Bewertungseinheiten in half-point steps (floats;
    ``total_points`` = sum of the step max scores, e.g. 72.5).

    ``grade_scale`` is an optional per-rubric Notenschlüssel (18 thresholds,
    rounding rule, pass grade); NULL means the default Falllösung table
    scaled to ``total_points``.

    Multiple rows per task are expected (candidate rubrics from different
    generator models, clones created when a graded rubric is edited); at most
    ONE row per task has ``status='active'`` — enforced by the partial unique
    index ``ux_task_rubrics_one_active`` (migration 088).
    """

    __tablename__ = "task_rubrics"

    id = Column(String, primary_key=True, index=True)
    task_id = Column(
        String, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id = Column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    title = Column(String, nullable=True)
    criteria = Column(JSONB, nullable=False)
    total_points = Column(Float, nullable=False, default=100, server_default="100")
    # Canonical outline (sections + scored steps); criteria derive from it.
    structure = Column(JSONB, nullable=True)
    # Per-rubric Notenschlüssel; NULL → default table scaled to total_points.
    grade_scale = Column(JSONB, nullable=True)

    # 'llm' (generated), 'llm_edited' (generated, then human-edited), 'human'
    source = Column(String(16), nullable=False, server_default="llm")
    generator_model_id = Column(String, nullable=True)
    # Key into project.generation_config.prompt_structures used to generate
    # this rubric, plus a content hash of that prompt at generation time.
    prompt_key = Column(String, nullable=True)
    prompt_version = Column(String, nullable=True)
    # Provider params, token usage, latency, retry counts — provenance only.
    generation_metadata = Column(JSONB, nullable=True)

    # 'candidate' | 'active' | 'archived'
    status = Column(String(16), nullable=False, server_default="candidate", index=True)

    # Check step (migration 137). ``review_state`` is NULL while no check is
    # recorded, else a short string the overlay's review workflow owns
    # (``'confirmed'``, ``'unusable'``). The platform reads it only for one
    # rule: on a project with ``rubric_review_required`` a sheet is activated
    # only when it is ``'confirmed'`` (``task_rubric_service``).
    review_state = Column(String(16), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    created_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    task = relationship("Task", backref="rubrics")
    project = relationship("Project")

    __table_args__ = (
        sa.Index(
            "ux_task_rubrics_one_active",
            "task_id",
            unique=True,
            postgresql_where=sa.text("status = 'active'"),
        ),
        sa.Index("ix_task_rubrics_task_status", "task_id", "status"),
        sa.Index("ix_task_rubrics_generator", "project_id", "generator_model_id"),
        sa.Index("ix_task_rubrics_project_review_state", "project_id", "review_state"),
    )

    def __repr__(self):
        return (
            f"<TaskRubric(id={self.id}, task_id={self.task_id}, "
            f"status={self.status}, generator={self.generator_model_id})>"
        )


RUBRIC_GENERATION_JOB_ENTRY_POINTS = ("wizard", "bulk", "task", "proposal")
RUBRIC_GENERATION_JOB_STATUSES = ("queued", "running", "completed", "failed", "lost")


class RubricGenerationJob(Base):
    """One Bewertungsbogen generation job (tasks.generate_bewertungsbogen).

    Written by the extended API at dispatch, updated by its status poll and
    by the Celery task wrapper when the job ends; a job no worker finished in
    time is marked ``lost`` by an extended beat sweep. Rows outlive the
    project, task and user (SET NULL) because they are the record of how
    often generation succeeds. Platform owns the table (migration 136) and
    the superadmin read (``GET /api/admin/rubric-generation-jobs``,
    serializer in ``rubric_generation_jobs``); the flow lives in
    ``benger_extended.api.routers.bewertungsbogen`` and
    ``benger_extended.rubric_jobs``.
    """

    __tablename__ = "rubric_generation_jobs"

    id = Column(String, primary_key=True)  # uuid4 str, set by the writer
    # NULL when the dispatch itself failed; the writer upserts on it.
    celery_task_id = Column(String(255), nullable=True, unique=True)
    entry_point = Column(String(16), nullable=False)  # RUBRIC_GENERATION_JOB_ENTRY_POINTS
    status = Column(String(16), nullable=False, default="queued", server_default="queued")

    project_id = Column(String, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    task_id = Column(String, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    # Who started it, and the key/billing organization of the dispatch.
    user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    organization_id = Column(
        String, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    # The sheet it produced.
    rubric_id = Column(String, ForeignKey("task_rubrics.id", ondelete="SET NULL"), nullable=True)
    retry_of = Column(
        String, ForeignKey("rubric_generation_jobs.id", ondelete="SET NULL"), nullable=True
    )

    generator_model_id = Column(String(255), nullable=True)
    prompt_key = Column(String(255), nullable=True)
    contract = Column(String(64), nullable=True)  # requested contract name, e.g. "checklist"
    contract_version = Column(String(64), nullable=True)  # e.g. "checklist-8"
    prompt_sha256 = Column(String(64), nullable=True)
    validator_sha256 = Column(String(64), nullable=True)
    app_version = Column(String(128), nullable=True)  # image tag of the dispatching API

    error_code = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    error_stage = Column(String(32), nullable=True)
    attempts = Column(Integer, nullable=True)
    attempt_errors = Column(JSONB, nullable=True)  # the worker's list, as returned
    fallback = Column(String(64), nullable=True)  # e.g. "weichenstellungen_removed"

    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    # Request parameters that are not columns (exam fact keys given,
    # allocation mode, metered flag, ...). Small; never prompt text or task
    # content.
    details = Column(JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb"))

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Many-to-one only, for the insert order within one flush (a writer may
    # add the sheet and its job record together); deletes stay with the
    # database's SET NULL.
    project = relationship("Project")
    task = relationship("Task")
    rubric = relationship("TaskRubric")

    __table_args__ = (
        sa.CheckConstraint(
            "entry_point IN ('wizard', 'bulk', 'task', 'proposal')",
            name="ck_rubric_generation_jobs_entry_point",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'lost')",
            name="ck_rubric_generation_jobs_status",
        ),
        sa.Index("ix_rubric_generation_jobs_created", "created_at"),
        sa.Index("ix_rubric_generation_jobs_status_created", "status", "created_at"),
        sa.Index("ix_rubric_generation_jobs_project_created", "project_id", "created_at"),
        sa.Index("ix_rubric_generation_jobs_task_created", "task_id", "created_at"),
        sa.Index("ix_rubric_generation_jobs_user_created", "user_id", "created_at"),
        sa.Index("ix_rubric_generation_jobs_org_created", "organization_id", "created_at"),
    )


class TaskRubricReviewEvent(Base):
    """One entry of the edit and check log of a task's grading sheets.

    Append-only: written only by the overlay's review workflow
    (``recorded``, ``edited``, ``confirmed``, ``rejected``, ``reopened``;
    the vocabulary and the JSON shapes of ``provenance``, ``diff``,
    ``checklist``, ``structure_before``/``structure_after`` and ``context``
    are the overlay's), never updated. A ``BEFORE UPDATE`` trigger
    (migration 137, and :data:`TASK_RUBRIC_REVIEW_EVENTS_APPEND_ONLY_DDL`
    on a schema built from the models) refuses every UPDATE except setting
    ``rubric_id`` and/or ``actor_id`` to NULL, which the two ``ON DELETE SET
    NULL`` actions need. DELETE stays allowed (project and task cascades,
    account erasure).
    """

    __tablename__ = "task_rubric_review_events"

    id = Column(String, primary_key=True)  # uuid4 str, set by the writer
    project_id = Column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id = Column(
        String, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # The row the event is about, at the time of the event.
    rubric_id = Column(
        String, ForeignKey("task_rubrics.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    event = Column(String(24), nullable=False)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    provenance = Column(JSONB, nullable=True)
    diff = Column(JSONB, nullable=True)
    checklist = Column(JSONB, nullable=True)
    # 'unchanged' | 'minor_edits' | 'major_edits' | 'unusable'
    verdict = Column(String(16), nullable=True)
    notes = Column(Text, nullable=True)
    structure_before = Column(JSONB, nullable=True)
    structure_after = Column(JSONB, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    app_version = Column(String(128), nullable=True)  # app_version.app_version()
    context = Column(JSONB, nullable=True)

    # Many-to-one only, so the unit of work inserts the project, task and
    # sheet before an event that names them in the same flush (an import
    # adds all of them at once). No collections on the other side: deleting
    # a sheet or a person leaves the event to the database's SET NULL.
    project = relationship("Project")
    task = relationship("Task")
    rubric = relationship("TaskRubric")

    __table_args__ = (
        sa.Index("ix_task_rubric_review_events_project_created", "project_id", "created_at"),
    )


# The append-only rule of ``task_rubric_review_events``. Migration 137 runs
# the same statements (kept verbatim there; a migration never imports the
# models); a schema built with ``Base.metadata.create_all`` (the test
# databases) gets them through the ``after_create`` listener below.
TASK_RUBRIC_REVIEW_EVENTS_APPEND_ONLY_FUNCTION = """
CREATE OR REPLACE FUNCTION task_rubric_review_events_append_only() RETURNS trigger AS $fn$
BEGIN
    IF (to_jsonb(NEW) - 'rubric_id' - 'actor_id') IS DISTINCT FROM (to_jsonb(OLD) - 'rubric_id' - 'actor_id')
       OR (NEW.rubric_id IS DISTINCT FROM OLD.rubric_id AND NEW.rubric_id IS NOT NULL)
       OR (NEW.actor_id IS DISTINCT FROM OLD.actor_id AND NEW.actor_id IS NOT NULL) THEN
        RAISE EXCEPTION 'task_rubric_review_events is append-only'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql
"""
TASK_RUBRIC_REVIEW_EVENTS_APPEND_ONLY_TRIGGER = """
CREATE TRIGGER trg_task_rubric_review_events_append_only
BEFORE UPDATE ON task_rubric_review_events
FOR EACH ROW EXECUTE FUNCTION task_rubric_review_events_append_only()
"""
TASK_RUBRIC_REVIEW_EVENTS_APPEND_ONLY_DDL = (
    TASK_RUBRIC_REVIEW_EVENTS_APPEND_ONLY_FUNCTION,
    TASK_RUBRIC_REVIEW_EVENTS_APPEND_ONLY_TRIGGER,
)
for _statement in TASK_RUBRIC_REVIEW_EVENTS_APPEND_ONLY_DDL:
    sa.event.listen(
        TaskRubricReviewEvent.__table__,
        "after_create",
        sa.DDL(_statement).execute_if(dialect="postgresql"),
    )
del _statement


class GradingFeedback(Base):
    """Solver reaction to ONE grading of ONE own submission: thumbs + optional comment.

    NOT the Korrektur feature ("feedback" was its pre-031 name, see migrations
    027/031; the student UI still labels a human correction "Feedback deiner
    Korrektur"). This is meta-feedback ABOUT a grading: ``grading_source``
    ``'llm'`` (a judge run) or ``'human'`` (Korrektur grade and/or
    Randbemerkungen), plus ``'general'`` for free-text feedback about the exam
    or the platform left from the same panel (no rating, no grading snapshot).
    Mined by operators to tune the judges and the Korrektur workflow.

    One row per (user, annotation, grading_source), enforced by the unique
    index ``uq_grading_feedback_user_annotation_source``; vote flips and
    comment edits upsert in place (``INSERT ... ON CONFLICT``), and a re-graded
    submission re-points the row (run id + snapshot) on the solver's next vote.
    ``judge_model_id`` / ``grade_points`` / ``passed`` snapshot what the solver
    saw at vote time as discrete columns for SQL/CSV slicing; ``context`` keeps
    the long tail (metric keys, task_evaluation ids, judge/grader ids, comment
    count, run status). ``evaluation_run_id`` is SET NULL on run deletion so the
    opinion survives; it is NULL for comment-only human corrections.

    Platform owns persistence + generic reads (``routers/grading_feedback.py``);
    the write path (participant access policy, target validation, snapshot)
    lives in ``benger_extended.api.routers.grading_feedback``. Not part of the
    project export/import round-trip yet.
    """

    __tablename__ = "grading_feedback"

    id = Column(String, primary_key=True, index=True)
    project_id = Column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id = Column(
        String, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    annotation_id = Column(
        String, ForeignKey("annotations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # 'llm' | 'human' | 'general'
    grading_source = Column(String(8), nullable=False)
    evaluation_run_id = Column(
        String, ForeignKey("evaluation_runs.id", ondelete="SET NULL"), nullable=True
    )
    # Snapshot of the grading the solver reacted to (NULL judge for human rows).
    judge_model_id = Column(String, nullable=True)
    grade_points = Column(Float, nullable=True)
    passed = Column(Boolean, nullable=True)

    # 'up' | 'down' | NULL (comment-only)
    rating = Column(String(8), nullable=True)
    comment = Column(Text, nullable=True)
    context = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    project = relationship("Project")
    task = relationship("Task")
    annotation = relationship("Annotation")
    user = relationship("User")

    __table_args__ = (
        sa.Index(
            "uq_grading_feedback_user_annotation_source",
            "user_id",
            "annotation_id",
            "grading_source",
            unique=True,
        ),
        sa.Index("ix_grading_feedback_project_created", "project_id", "created_at"),
        sa.Index("ix_grading_feedback_evaluation_run", "evaluation_run_id"),
        sa.CheckConstraint(
            "grading_source IN ('llm', 'human', 'general')",
            name="ck_grading_feedback_source",
        ),
        sa.CheckConstraint(
            "rating IS NULL OR rating IN ('up', 'down')", name="ck_grading_feedback_rating"
        ),
        sa.CheckConstraint(
            "rating IS NOT NULL OR comment IS NOT NULL", name="ck_grading_feedback_not_empty"
        ),
    )

    def __repr__(self):
        return (
            f"<GradingFeedback(id={self.id}, annotation_id={self.annotation_id}, "
            f"source={self.grading_source}, rating={self.rating})>"
        )


class SubmissionFile(Base):
    """A file a person handed in as their answer to a task.

    The person (``user_id``) or an admin on their behalf (``uploaded_by``)
    uploads a text PDF, Word file, ``.txt`` or ``.md``; its extracted text
    becomes the answer and the original stays in object storage under
    ``storage_key`` so graders can open it. ``annotation_id`` points at the
    submission the upload created or replaced (NULL for a student's own upload,
    which only fills the editor and is submitted the normal way; those are
    found by ``(task_id, user_id)``). ``replaced_result`` keeps the annotation
    result an admin upload overwrote, for the audit trail.

    Platform owns the table (migration 113); who may upload for whom and the
    upload flow live in ``benger_extended.api.routers.submission_uploads``.
    Not part of the project export/import round-trip yet.
    """

    __tablename__ = "submission_files"

    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    task_id = Column(String, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    uploaded_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    annotation_id = Column(
        String, ForeignKey("annotations.id", ondelete="SET NULL"), nullable=True
    )

    storage_key = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    content_type = Column(String, nullable=True)
    size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    # 'pdf' | 'docx' | 'text' (text_extraction.extract_text source_format),
    # 'image' for a handwritten page photo (OCR upload, mig 125)
    source_format = Column(String(16), nullable=False)
    extracted_chars = Column(Integer, nullable=False, default=0, server_default="0")
    replaced_result = Column(JSONB, nullable=True)
    # Handwritten uploads: the OCR job this page belongs to and its position.
    ocr_job_id = Column(
        String, ForeignKey("submission_ocr_jobs.id", ondelete="SET NULL"), nullable=True
    )
    page_index = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        sa.Index("ix_submission_files_task_user", "task_id", "user_id", "created_at"),
        sa.Index("ix_submission_files_project", "project_id"),
        sa.Index("ix_submission_files_ocr_job", "ocr_job_id"),
    )


OCR_JOB_MODES = ("own", "on_behalf", "pending")
OCR_JOB_STATUSES = ("queued", "running", "done", "failed")


class SubmissionOcrJob(Base):
    """One transcription of handwritten solution pages (photos or scans).

    Created by the upload endpoint, filled by an async worker task that sends
    the pages to the project's ``handwriting_ocr_model`` and writes ``text``.

    ``mode``:
    - ``own``: a person uploaded their own pages. The transcript goes back to
      their editor; they check it and ``confirmed_at`` is stamped when they
      accept it. The answer is then submitted the normal way.
    - ``on_behalf``: staff uploaded for a person; the worker stores the text
      as that person's submission (``annotation_id``).
    - ``pending``: staff uploaded for someone without an account yet
      (``user_id`` NULL). The worker only stores the text; it is attached
      when the person joins (:func:`attach_ocr_job_to_user`).

    ``page_keys`` is the ordered list of stored uploads, one entry per file (a
    photo is one page, a PDF may hold several):
    ``{storage_key, original_filename, content_type, size_bytes, sha256}``.
    ``page_count`` counts pages across them. ``submission_files`` rows exist
    only once a user is known.

    Platform owns the table (migration 125); the flow lives in
    ``benger_extended.api.routers.submission_uploads`` and the OCR task in
    ``benger_extended.workers.ocr_tasks``.
    """

    __tablename__ = "submission_ocr_jobs"

    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    task_id = Column(String, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    requested_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    mode = Column(String(16), nullable=False)
    status = Column(String(16), nullable=False, default="queued", server_default="queued")

    page_keys = Column(JSONB, nullable=False, default=list, server_default=sa.text("'[]'::jsonb"))
    page_count = Column(Integer, nullable=False, default=0, server_default="0")
    pages_ocr = Column(Integer, nullable=False, default=0, server_default="0")
    text = Column(Text, nullable=True)

    model_id = Column(String(255), nullable=True)
    billed_org_id = Column(
        String, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    cost_usd = Column(sa.Numeric(12, 6), nullable=True)
    error_code = Column(String(64), nullable=True)
    # Set when the worker saved the transcript itself (staff upload, or the
    # writing time ended before the person could check it).
    annotation_id = Column(
        String, ForeignKey("annotations.id", ondelete="SET NULL"), nullable=True
    )
    auto_persisted = Column(Boolean, nullable=False, default=False, server_default=sa.false())
    confirmed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        sa.CheckConstraint(
            "mode IN ('own', 'on_behalf', 'pending')", name="ck_submission_ocr_jobs_mode"
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed')",
            name="ck_submission_ocr_jobs_status",
        ),
        sa.CheckConstraint(
            "user_id IS NOT NULL OR mode = 'pending'",
            name="ck_submission_ocr_jobs_user_unless_pending",
        ),
        sa.Index("ix_submission_ocr_jobs_task_user", "task_id", "user_id", "created_at"),
        sa.Index("ix_submission_ocr_jobs_project", "project_id"),
    )


def attach_ocr_job_to_user(db, job: "SubmissionOcrJob", user_id: str, *, file_id_factory=None):
    """Give a ``pending`` OCR job its person and create their ``submission_files``.

    Called when someone an admin uploaded pages for joins (extended invitee
    flow). Sets ``user_id``, switches the job to ``on_behalf`` and adds one
    ``SubmissionFile`` per stored upload (``source_format`` from the page's
    content type, ``ocr_job_id`` + ``page_index`` set). Persisting the text as
    an annotation stays with the caller. Idempotent for the same user;
    attaching to a different user raises ``ValueError``. Does not commit.
    Returns the new ``SubmissionFile`` rows.
    """
    import uuid

    if job.user_id is not None:
        if job.user_id != user_id:
            raise ValueError("OCR job already belongs to another user")
        return []
    if job.mode != "pending":
        raise ValueError("only pending OCR jobs can be attached")
    make_id = file_id_factory or (lambda: str(uuid.uuid4()))
    job.user_id = user_id
    job.mode = "on_behalf"
    rows = []
    for index, page in enumerate(job.page_keys or []):
        ctype = page.get("content_type") or ""
        row = SubmissionFile(
            id=make_id(),
            project_id=job.project_id,
            task_id=job.task_id,
            user_id=user_id,
            uploaded_by=job.requested_by,
            storage_key=page["storage_key"],
            original_filename=page.get("original_filename") or f"page-{index + 1}",
            content_type=ctype or None,
            size_bytes=int(page.get("size_bytes") or 0),
            sha256=page.get("sha256") or "",
            source_format="pdf" if ctype == "application/pdf" else "image",
            extracted_chars=0,
            ocr_job_id=job.id,
            page_index=index,
        )
        db.add(row)
        rows.append(row)
    return rows


#: Statuses of a parked upload that still waits for its person.
PENDING_UPLOAD_OPEN_STATUSES = ("extracting", "waiting")


class PendingSubmissionUpload(Base):
    """A solution uploaded for someone who is not on BenGER yet (migration 126).

    An admin uploads the file and enters the person's email; the person is
    invited and the upload waits here until they accept. Then
    ``benger_extended`` (hook ``after_invitation_accepted``) hands it in as
    their submission and fills the ``attached_*`` columns.

    ``status``: ``extracting`` (handwriting OCR still reads the scan,
    ``ocr_job_id``), ``waiting`` (text ready, person not joined yet),
    ``attached``, ``superseded`` (the person handed in their own answer
    first, which wins), ``failed`` (``error_code``), ``cancelled``.

    Platform owns the table; who may park what and the attach logic live in
    ``benger_extended.api.routers.submission_uploads``.
    """

    __tablename__ = "pending_submission_uploads"

    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    task_id = Column(String, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    invitation_id = Column(
        String, ForeignKey("invitations.id", ondelete="SET NULL"), nullable=True
    )
    # Lower-cased.
    email = Column(String, nullable=False)
    invitee_name = Column(String, nullable=True)
    uploaded_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    storage_key = Column(String, nullable=True)
    original_filename = Column(String, nullable=False)
    content_type = Column(String, nullable=True)
    size_bytes = Column(Integer, nullable=False, default=0, server_default="0")
    sha256 = Column(String(64), nullable=True)
    source_format = Column(String(16), nullable=False)
    extracted_text = Column(Text, nullable=True)
    ocr_job_id = Column(
        String, ForeignKey("submission_ocr_jobs.id", ondelete="SET NULL"), nullable=True
    )

    status = Column(String(16), nullable=False, default="waiting", server_default="waiting")
    error_code = Column(String(64), nullable=True)
    attached_user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    attached_annotation_id = Column(
        String, ForeignKey("annotations.id", ondelete="SET NULL"), nullable=True
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    attached_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('extracting','waiting','attached','superseded','failed','cancelled')",
            name="ck_pending_submission_uploads_status",
        ),
        sa.Index(
            "uq_pending_submission_uploads_open",
            "task_id",
            "email",
            unique=True,
            postgresql_where=sa.text("status IN ('extracting','waiting')"),
        ),
        sa.Index("ix_pending_submission_uploads_email", "email"),
        sa.Index("ix_pending_submission_uploads_invitation", "invitation_id"),
        sa.Index("ix_pending_submission_uploads_project", "project_id"),
    )


def project_not_deleted():
    """Soft-delete predicate (migration 093): every visibility query excludes
    stamped projects; superadmin surfaces opt back in explicitly. Lives in
    /shared so api, workers and the extended package share ONE definition."""
    return Project.deleted_at.is_(None)


def project_is_deleted(project) -> bool:
    """Instance twin of :func:`project_not_deleted`."""
    return getattr(project, "deleted_at", None) is not None


def project_listable():
    """Predicate of every list, count and aggregate over projects: alive and
    not a creation-wizard draft (migration 141). A draft is private and has
    no organization rows, so only its creator and superadmins could reach it
    anyway; this keeps it out of their lists too. Per-project reads use
    their own access rules, so the creator still opens the draft."""
    return sa.and_(Project.deleted_at.is_(None), Project.is_wizard_draft.is_(False))


def project_is_wizard_draft(project) -> bool:
    """Instance twin of the draft half of :func:`project_listable`."""
    return bool(getattr(project, "is_wizard_draft", False))

