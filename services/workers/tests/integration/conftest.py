"""Worker-orchestration integration test harness.

Drives the REAL Celery chord pipeline (`run_evaluation` → per-cell
sub-tasks → `finalize_evaluation_run`) and the real generation loop
(`generate_llm_responses`) end-to-end against the real test Postgres,
asserting correctness / idempotency / cancel / resume.

Design B — committed setup + FK-safe delete cleanup (chosen)
============================================================
The chord entrypoints fan out into MANY independent sessions (one per
cell sub-task + the finalize callback + judge reconciliation), each
opening ``tasks.SessionLocal()`` and doing its own begin/commit/close.

We FIRST tried Design A (one shared connection + re-arming SAVEPOINT, with
``tasks.SessionLocal`` monkeypatched to bind to it — the pattern the API
suite uses). It works for the single-session generation loop but is
**non-deterministically broken** for the multi-session eval chord: each
sub-task session's commit()/close() cycle churns the connection's
transaction state, and the per-savepoint re-arm collides with sibling
sessions on the same connection — runs flip between "2 rows persisted"
and "0 rows persisted" between invocations. (Observed live: identical
runs producing ``samples_evaluated=2, metrics 0.5`` one run and
``failed, 0 samples`` the next.) Multiple concurrent ORM sessions on one
externally-managed connection is simply not a supported isolation model.

Design B sidesteps it entirely:

1. Run Celery EAGER (``task_always_eager``) so signatures execute inline.
2. Drive a **REAL** ``celery.chord`` against a **real Redis result
   backend** (the ``test-redis`` compose service). The chord
   synchronization barrier needs a result backend even under eager, and
   ``task_store_eager_result=True`` makes eager sub-task results land in
   it — so ``chord(header)(callback)`` fan-out + auto-fire of the
   ``finalize_evaluation_run`` callback runs exactly as it does in prod,
   with NO in-process shim. (See "Why the backend must be repointed at
   IMPORT time" below for the one non-obvious bit.)
3. Do NOT patch ``tasks.SessionLocal`` — every sub-task uses the REAL
   docker engine/session, commits to the real test DB, and those commits
   are visible to the test's own real session (after ``expire_all()``).
4. The test session (``db_conn``) commits its setup rows so the sub-task
   sessions see them. A per-test registry tracks created Projects / Users /
   LLMModels / EvaluationRuns; teardown deletes them in FK-safe order
   (children first), so nothing leaks between tests on the shared DB.

Trade-off vs A: no SAVEPOINT isolation, so cleanup is explicit deletes
keyed off the tracked roots (Project cascade handles tasks / annotations /
generations / task_evaluations / judge_runs; EvaluationRun cascade handles
its own children; Users / LLMModels deleted last). Unique per-row UUIDs
keep tests independent even if a cleanup ever missed a row.

Why the backend must be repointed at IMPORT time
=================================================
``services/workers/.env`` (mounted into the runner) sets
``CELERY_BROKER_URL``/``CELERY_RESULT_BACKEND`` to the **dev** host
``redis:6379`` (with a password), which is unresolvable on the test
network. ``tasks.py`` calls ``load_dotenv()`` then, at import time, does
``app.conf.broker_url = os.getenv("CELERY_BROKER_URL", ...)``.

Celery's ``Settings`` is a layered ChainMap. A direct ``conf.attr =``
assignment after the conf is finalized lands in a layer **above**
``conf.changes`` and is un-overridable: a later ``conf.update(...)`` or
``conf.changes[...] = ...`` is silently shadowed (verified — that is the
"backend unreachable" wall the prior harness hit and why it shimmed the
chord). The only lever that works is to make the *import-time*
assignment read the right value: we set ``CELERY_BROKER_URL`` /
``CELERY_RESULT_BACKEND`` to the reachable ``test-redis`` URL **before**
``import tasks`` below, so the un-overridable layer is correct from the
start. ``load_dotenv()`` doesn't override an already-set env var, so our
value wins over ``.env``.
"""

import os
import uuid
from datetime import datetime, timezone

# ── Repoint Celery broker/backend at the reachable test Redis BEFORE
# importing `tasks` (see module docstring "Why the backend must be
# repointed at IMPORT time"). The root `tests/conftest.py` already does
# this first (it loads before this one), so these setdefaults are normally
# no-ops; they're kept here as defense-in-depth so the eval-chord harness
# still works if this file is ever collected without the root conftest.
# `tasks.py`'s import-time `app.conf.broker_url = os.getenv("CELERY_BROKER_URL",
# ...)` reads these; a runtime override would be silently shadowed by
# Celery's config layering.
_TEST_REDIS = os.environ.get("REDIS_URL") or os.environ.get("REDIS_URI") \
    or "redis://test-redis:6379"
os.environ.setdefault("CELERY_BROKER_URL", f"{_TEST_REDIS}/2")
os.environ.setdefault("CELERY_RESULT_BACKEND", f"{_TEST_REDIS}/1")

import pytest
from sqlalchemy import create_engine, text

# Import the task module + the (workers) database module. Because /shared
# is first on sys.path and `models.py` does `from database import Base`,
# `database.Base`, `database.engine` and `tasks.SessionLocal` all bind to
# the SAME workers `database.py` pointed at the test DB.
import tasks
import database
from database import Base


# Register the models on the metadata before create_all. `models` first
# (User, EvaluationRun, ...), then `project_models` (references User via
# relationships) — reverse order raises "failed to locate a name 'User'".
import models  # noqa: F401
import project_models  # noqa: F401
import report_models  # noqa: F401


SENTINEL = "00000000-0000-0000-0000-000000000000"


def _build_engine():
    """Engine bound to the test DB. Prefer the module's own engine (already
    pointed at DATABASE_URI in the docker runner); fall back to building one
    from DATABASE_URI / DATABASE_URL for bare host runs."""
    if getattr(database, "engine", None) is not None:
        return database.engine
    db_url = os.environ.get("DATABASE_URI") or os.environ.get("DATABASE_URL")
    if not db_url:
        pytest.skip("No DATABASE_URI/DATABASE_URL set for integration DB")
    return create_engine(db_url, pool_pre_ping=True)


@pytest.fixture(scope="session", autouse=True)
def _eager_celery():
    """Run Celery inline so chord()/signature() execute in-process, with a
    REAL Redis result backend so a real `chord(header)(callback)` works.

    Saves prior values on the REAL app object and restores them on teardown
    so other (non-eager) test files in the same session aren't affected.

    `task_store_eager_result=True` is the key: under `task_always_eager`,
    an EagerResult only lands in the result backend (and thus satisfies the
    chord's synchronization barrier so the callback auto-fires) when this
    flag is on. The broker/result_backend already point at the reachable
    `test-redis` because conftest set CELERY_BROKER_URL/CELERY_RESULT_BACKEND
    before `import tasks` (see module docstring) — so NO runtime repoint is
    needed here (and would be silently shadowed if attempted).
    """
    conf = tasks.app.conf
    prior = {
        "task_always_eager": conf.task_always_eager,
        "task_eager_propagates": conf.task_eager_propagates,
        "task_store_eager_result": conf.task_store_eager_result,
    }
    conf.task_always_eager = True
    conf.task_eager_propagates = True
    conf.task_store_eager_result = True
    try:
        yield
    finally:
        for k, v in prior.items():
            setattr(conf, k, v)


@pytest.fixture(autouse=True)
def _stub_notifications(request, monkeypatch):
    """No-op the notification side effect for chord-driving tests.

    This is the ONE side effect we stub. `finalize_evaluation_run` (and the
    `run_evaluation` failure arm) call `NotificationService.create_notification`,
    whose email-enqueue does `current_app.send_task(..., queue="emails")`.
    Even with the broker now pointed at the reachable `test-redis`, that
    `send_task` enqueues a real `emails` task that no consumer drains, and
    `create_notification` writes Notification rows we don't assert on and
    don't track for FK-safe cleanup. Stubbing it keeps the test focused on
    the orchestration DB state. Everything else — the chord barrier, the
    poison-cell Redis counter, the progress pub/sub — runs against the real
    test-redis, exactly as in prod. Only active for tests that pull `db_conn`.
    """
    if "db_conn" not in request.fixturenames:
        return

    def _noop(*args, **kwargs):
        return []

    monkeypatch.setattr(tasks.NotificationService, "create_notification", _noop)


@pytest.fixture(scope="session", autouse=True)
def _schema(_eager_celery):
    """Create the full schema + the partial indexes that `create_all` can't
    derive from the models.

    The dockerized test-db is ephemeral (tmpfs, no migration init service),
    so a fresh `run --rm` container against a freshly-started test-db has an
    EMPTY schema. We build it from `Base.metadata` here. The orchestration
    entrypoints don't depend on which path built the schema.

    CRITICAL: the partial unique index `uq_task_evaluations_cell` that backs
    `_bulk_upsert_task_evaluations`' bare `ON CONFLICT DO NOTHING` exists
    ONLY in alembic (migration 049 supersedes 048 — note: 049 adds a 6th
    column `created_by`, so we replicate 049's shape, NOT 048's). The model
    has no `__table_args__` for it, so `create_all()` will NOT create it.
    Without it, the idempotency test silently passes while inserting
    duplicate rows. `IF NOT EXISTS` makes this a safe no-op if a migrated
    schema already carries it.
    """
    engine = _build_engine()
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:  # pragma: no cover - surfaced loudly
        pytest.exit(
            f"Cannot create schema on integration DB "
            f"({os.environ.get('DATABASE_URI') or os.environ.get('DATABASE_URL')}). "
            f"Run 'make test-start' / bring up the test stack first. Error: {e}"
        )

    with engine.begin() as conn:
        # Migration 049 shape: per-grader partial unique index. This is the
        # ON CONFLICT target for task_evaluations cell-dedup.
        conn.execute(
            text(
                f"""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_task_evaluations_cell
                ON task_evaluations (
                    evaluation_id,
                    judge_run_id,
                    COALESCE(generation_id, '{SENTINEL}'),
                    COALESCE(annotation_id, '{SENTINEL}'),
                    field_name,
                    COALESCE(created_by, '{SENTINEL}')
                )
                WHERE evaluation_id IS NOT NULL
                """
            )
        )
        # Migration 041 shape: at most one Generation per (parent, run_index).
        # This one IS declared on the model (__table_args__), so create_all
        # makes it — IF NOT EXISTS keeps this idempotent regardless.
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_generations_parent_run_index
                ON generations (generation_id, run_index)
                """
            )
        )
    yield


class _Cleanup:
    """Registry of test-created root rows, deleted FK-safe in teardown."""

    def __init__(self):
        self.project_ids = []
        self.evaluation_run_ids = []
        self.user_ids = []
        self.model_ids = []

    def run(self, session):
        from models import (
            EvaluationRun,
            Generation,
            LLMModel,
            ResponseGeneration,
            TaskEvaluation,
            User,
        )
        from project_models import Annotation, Project, Task

        # Children first. Project cascade covers most, but we delete
        # explicitly so cleanup is independent of DB-level ON DELETE config.
        if self.project_ids:
            pj = self.project_ids
            tids = [
                t for (t,) in session.query(Task.id)
                .filter(Task.project_id.in_(pj)).all()
            ]
            gids = [
                g for (g,) in session.query(Generation.id)
                .filter(Generation.task_id.in_(tids)).all()
            ] if tids else []
            session.query(TaskEvaluation).filter(
                TaskEvaluation.task_id.in_(tids)
            ).delete(synchronize_session=False) if tids else None
            if gids:
                session.query(Generation).filter(
                    Generation.id.in_(gids)
                ).delete(synchronize_session=False)
            session.query(ResponseGeneration).filter(
                ResponseGeneration.project_id.in_(pj)
            ).delete(synchronize_session=False)
            if tids:
                session.query(Annotation).filter(
                    Annotation.task_id.in_(tids)
                ).delete(synchronize_session=False)
                session.query(Task).filter(
                    Task.id.in_(tids)
                ).delete(synchronize_session=False)

        # EvaluationRun cascade handles its judge_runs + task_evaluations.
        if self.evaluation_run_ids:
            session.query(EvaluationRun).filter(
                EvaluationRun.id.in_(self.evaluation_run_ids)
            ).delete(synchronize_session=False)

        if self.project_ids:
            session.query(Project).filter(
                Project.id.in_(self.project_ids)
            ).delete(synchronize_session=False)

        if self.model_ids:
            session.query(LLMModel).filter(
                LLMModel.id.in_(self.model_ids)
            ).delete(synchronize_session=False)
        if self.user_ids:
            session.query(User).filter(
                User.id.in_(self.user_ids)
            ).delete(synchronize_session=False)
        session.commit()


@pytest.fixture()
def cleanup():
    return _Cleanup()


@pytest.fixture()
def db_conn(_schema, cleanup):
    """A REAL session on the docker engine (Design B).

    Used for both setup and assertions. Setup is committed so the pipeline's
    independent sub-task sessions see it. Teardown deletes every tracked root
    row FK-safe. `expire_on_commit=False` keeps ORM objects usable across the
    commits the factories issue.
    """
    from sqlalchemy.orm import sessionmaker as _sm

    factory = _sm(bind=_build_engine(), autoflush=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        try:
            session.rollback()
        except Exception:
            pass
        try:
            cleanup.run(session)
        finally:
            session.close()


# ---------------------------------------------------------------------------
# Fake AI service (generation loop) — deterministic, no network.
# ---------------------------------------------------------------------------


class FakeAIService:
    """Stand-in for a provider AI service. Sync `generate`, always available.

    Returns the worker's preferred `response_text` shape with `success=True`
    so the generation loop takes the happy path. An optional `on_generate`
    hook lets a test mutate DB state mid-loop (used by the cooperative-cancel
    xfail).
    """

    def __init__(self, response_text="Antwort: Ja", on_generate=None):
        self._response_text = response_text
        self._on_generate = on_generate
        self.calls = 0
        # Audit attributes the worker reads off the service via getattr.
        self._key_resolution_route = "test_key"
        self._provider_name = "OpenAI"
        self._invocation_user_id = None
        self._invocation_organization_id = None

    def is_available(self):
        return True

    def generate(self, prompt=None, system_prompt=None, model_name=None,
                 temperature=None, max_tokens=None, **kwargs):
        self.calls += 1
        if self._on_generate is not None:
            self._on_generate(self.calls)
        return {
            "success": True,
            "response_text": self._response_text,
            "content": self._response_text,
            "prompt_tokens": 3,
            "completion_tokens": 2,
            "total_tokens": 5,
            "cost_usd": 0.0,
            "provider": "OpenAI",
            "temperature": temperature or 0.0,
            "metadata": {},
        }


@pytest.fixture()
def fake_ai_service():
    return FakeAIService()


@pytest.fixture()
def patch_ai_service(monkeypatch, fake_ai_service):
    """Patch the generation loop's AI service factory to return the fake.

    `tasks.user_aware_ai_service.get_ai_service_for_user(db, user_id,
    provider, organization_id=...)` is the single resolution point in
    `generate_llm_responses`.
    """
    def _factory(db, user_id, provider, organization_id=None):
        return fake_ai_service

    monkeypatch.setattr(
        tasks.user_aware_ai_service, "get_ai_service_for_user", _factory
    )
    return fake_ai_service


# ---------------------------------------------------------------------------
# Factories — local to conftest (do NOT import the API fixtures).
# ---------------------------------------------------------------------------


def _uid():
    return str(uuid.uuid4())


@pytest.fixture()
def make_user(db_conn, cleanup):
    from models import User

    def _make(name="Eval User"):
        u = User(
            id=_uid(),
            username=f"user_{uuid.uuid4().hex[:10]}",
            email=f"{uuid.uuid4().hex[:10]}@example.com",
            name=name,
            is_active=True,
        )
        db_conn.add(u)
        db_conn.commit()
        cleanup.user_ids.append(u.id)
        return u

    return _make


@pytest.fixture()
def make_llm_model(db_conn, cleanup):
    from models import LLMModel

    def _make(model_id=None, provider="OpenAI"):
        mid = model_id or f"test-model-{uuid.uuid4().hex[:8]}"
        m = LLMModel(
            id=mid,
            name=f"Test {mid}",
            description="integration test model",
            provider=provider,
            model_type="chat",
            capabilities=["text_generation"],
        )
        db_conn.add(m)
        db_conn.commit()
        cleanup.model_ids.append(m.id)
        return m

    return _make


@pytest.fixture()
def make_project(db_conn, cleanup, make_user):
    from project_models import Project

    def _make(created_by=None, label_config=None, generation_config=None,
              title="Integration Project"):
        if created_by is None:
            created_by = make_user().id
        p = Project(
            id=_uid(),
            title=title,
            created_by=created_by,
            label_config=label_config,
            generation_config=generation_config,
        )
        db_conn.add(p)
        db_conn.commit()
        cleanup.project_ids.append(p.id)
        return p

    return _make


@pytest.fixture()
def make_task(db_conn):
    from project_models import Task

    _counter = {"n": 0}

    def _make(project_id, data, created_by=None):
        _counter["n"] += 1
        t = Task(
            id=_uid(),
            project_id=project_id,
            data=data,
            inner_id=_counter["n"],  # NOT NULL, no default
            created_by=created_by,
        )
        db_conn.add(t)
        db_conn.commit()
        return t

    return _make


@pytest.fixture()
def make_generation(db_conn):
    """Create a parent ResponseGeneration + a child Generation row.

    Returns (response_generation, generation). The child carries
    parse_status="success" so the gen-cell enumerator picks it up even
    without a __all_model__ config.
    """
    from models import Generation, ResponseGeneration

    def _make(project_id, task_id, model_id, created_by, response_content,
              parse_status="success", status="completed", run_index=0,
              runs_requested=1):
        rg = ResponseGeneration(
            id=_uid(),
            project_id=project_id,
            task_id=task_id,
            model_id=model_id,
            status=status,
            runs_requested=runs_requested,
            created_by=created_by,
        )
        db_conn.add(rg)
        db_conn.commit()
        gen = Generation(
            id=_uid(),
            generation_id=rg.id,
            task_id=task_id,
            model_id=model_id,
            case_data="{}",
            response_content=response_content,
            parse_status=parse_status,
            run_index=run_index,
            status="completed",
        )
        db_conn.add(gen)
        db_conn.commit()
        return rg, gen

    return _make


@pytest.fixture()
def make_annotation(db_conn):
    from project_models import Annotation

    def _make(project_id, task_id, completed_by, result, was_cancelled=False):
        a = Annotation(
            id=_uid(),
            task_id=task_id,
            project_id=project_id,
            completed_by=completed_by,
            result=result,
            was_cancelled=was_cancelled,
        )
        db_conn.add(a)
        db_conn.commit()
        return a

    return _make


@pytest.fixture()
def make_evaluation_run(db_conn, cleanup):
    from models import EvaluationRun

    def _make(project_id, created_by, model_id="exact_match_run",
              status="pending", eval_metadata=None):
        er = EvaluationRun(
            id=_uid(),
            project_id=project_id,
            model_id=model_id,
            evaluation_type_ids=[],
            metrics={},
            eval_metadata=eval_metadata if eval_metadata is not None
            else {"triggered_by": created_by},
            status=status,
            created_by=created_by,
        )
        db_conn.add(er)
        db_conn.commit()
        cleanup.evaluation_run_ids.append(er.id)
        return er

    return _make


@pytest.fixture()
def exact_match_config():
    """Build an `exact_match` evaluation config dict.

    `__all_model__` prediction → `gen.response_content` directly (no parse
    needed). `task.<field>` reference → `task.data[field]`. This is the
    deterministic, no-judge, no-network happy path.
    """
    def _make(config_id="cfg1", ref_field="task.expected"):
        return {
            "id": config_id,
            "metric": "exact_match",
            "prediction_fields": ["__all_model__"],
            "reference_fields": [ref_field],
            "metric_parameters": {},
            "enabled": True,
        }

    return _make


@pytest.fixture()
def utcnow():
    return datetime.now(timezone.utc)
