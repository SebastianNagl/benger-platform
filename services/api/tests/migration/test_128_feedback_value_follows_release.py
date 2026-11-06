"""Data migration 128: a feedback row's value follows its release."""

from __future__ import annotations

import importlib.util
import os
import uuid
from contextlib import contextmanager

from sqlalchemy.orm import Session

MIGRATION_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "alembic",
        "versions",
        "128_feedback_value_follows_release.py",
    )
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_128", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


@contextmanager
def _op_context(connection):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    ctx = MigrationContext.configure(connection)
    with Operations.context(ctx):
        yield


def _feedback(value, review=None):
    details = {"feedback_only": True, "grade": {"note": 13.5, "sur": 20}}
    if review is not None:
        details["review"] = review
    return {"llm_judge_feedback": {"value": value, "method": "llm_judge_feedback", "details": details}}


def test_revision_chains_after_127():
    mig = _load_migration()
    assert mig.revision == "128_feedback_value_follows_release"
    assert mig.down_revision == "127_exam_tools"


def test_upgrade_brings_stored_rows_into_shape(test_db: Session):
    from models import EvaluationJudgeRun, EvaluationRun, TaskEvaluation
    from project_models import Project, Task

    org_free_id = uuid.uuid4().hex
    project = Project(id=org_free_id, title="mig 128", created_by=_any_user_id(test_db))
    test_db.add(project)
    test_db.flush()
    task = Task(id=uuid.uuid4().hex, project_id=project.id, data={}, inner_id=1)
    test_db.add(task)
    test_db.flush()

    def run(metrics):
        r = EvaluationRun(
            id=uuid.uuid4().hex,
            project_id=project.id,
            model_id="m",
            evaluation_type_ids=[],
            metrics=metrics,
            status="completed",
            created_by=project.created_by,
        )
        test_db.add(r)
        test_db.flush()
        return r

    def row(run_, metrics):
        judge_run = EvaluationJudgeRun(id=uuid.uuid4().hex, evaluation_id=run_.id)
        test_db.add(judge_run)
        test_db.flush()
        te = TaskEvaluation(
            id=uuid.uuid4().hex,
            evaluation_id=run_.id,
            task_id=task.id,
            field_name="f",
            answer_type="long_text",
            ground_truth={},
            prediction={},
            metrics=metrics,
            passed=True,
            judge_run_id=judge_run.id,
        )
        test_db.add(te)
        test_db.flush()
        return te

    draft_run = run({"f|llm_judge_feedback": 0.675, "f|bleu": 0.5})
    draft = row(draft_run, _feedback(0.675))
    written_draft = row(run({}), _feedback(0.675, {"status": "draft"}))
    corrected_run = run({"f|llm_judge_feedback": 0.675})
    corrected = row(
        corrected_run,
        _feedback(0.675, {"status": "released", "grade": {"note": 16.0, "sur": 20}}),
    )
    auto = row(run({}), _feedback(0.675, {"status": "released", "auto": True}))
    other = row(run({}), {"llm_judge_falloesung": {"value": 0.5, "details": {}}})
    test_db.commit()

    mig = _load_migration()
    conn = test_db.get_bind()
    with _op_context(conn):
        mig.upgrade()
        mig.upgrade()  # safe to repeat
    test_db.expire_all()

    def value(te):
        return test_db.get(TaskEvaluation, te.id).metrics["llm_judge_feedback"]["value"]

    assert value(draft) is None
    assert value(written_draft) is None
    assert value(corrected) == 16.0 / 20
    assert value(auto) == 0.675
    assert test_db.get(TaskEvaluation, draft.id).metrics["llm_judge_feedback"]["details"]["grade"]["note"] == 13.5
    assert test_db.get(TaskEvaluation, other.id).metrics["llm_judge_falloesung"]["value"] == 0.5
    assert test_db.get(EvaluationRun, draft_run.id).metrics == {"f|bleu": 0.5}
    assert test_db.get(EvaluationRun, corrected_run.id).metrics == {"f|llm_judge_feedback": 0.675}


def _any_user_id(db) -> str:
    from models import User

    user = User(
        id=uuid.uuid4().hex,
        username=f"mig128-{uuid.uuid4().hex[:8]}",
        email=f"mig128-{uuid.uuid4().hex[:8]}@example.test",
        name="mig 128",
        hashed_password="x",
    )
    db.add(user)
    db.flush()
    return user.id
