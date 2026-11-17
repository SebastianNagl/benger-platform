"""What an "evaluation" is in the project tiles, the project list and the
dashboard, and that counting it never reads the metrics blob.

The count is the number of distinct (subject, evaluation config, metric)
cells scored in completed runs of a project, where the subject is the graded
annotation or generation, re-runs of one config collapse, two configs of the
same metric count twice, noise keys (``*_details``, ``raw_score``, the
Notenpunkte twin) and grades of a cancelled annotation do not count. Since
migration 138 the cells come from ``task_evaluation_metric_keys``, a narrow
mirror of ``task_evaluations`` kept by triggers, because de-TOASTing every
metrics blob ran past the API's statement timeout on a 1.36M-row database.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from aggregate_summaries import (
    _eval_cell_counts_stmt,
    count_eval_pairs_by_project,
    read_project_summary,
    recompute_project_summaries,
)
import aggregate_summaries
from metric_filters import metric_key_counts_as_evaluation
from models import (
    EvaluationJudgeRun,
    EvaluationRun,
    Generation,
    ResponseGeneration,
    TaskEvaluation,
    User,
)
from project_models import Annotation, Project, Task
from routers.projects.helpers import calculate_project_stats_batch


def _uid() -> str:
    return str(uuid.uuid4())


class _World:
    def __init__(self, db: Session):
        self.db = db
        self.user = User(
            id=_uid(),
            username=f"evalcount-{_uid()[:8]}",
            email=f"evalcount-{_uid()[:8]}@example.com",
            name="Eval Count",
            hashed_password="x",
            is_active=True,
            email_verified=True,
        )
        db.add(self.user)
        db.flush()
        self._field = 0

    def project(self) -> Project:
        project = Project(id=_uid(), title="eval count", created_by=self.user.id)
        self.db.add(project)
        self.db.flush()
        return project

    def task(self, project: Project) -> Task:
        task = Task(id=_uid(), project_id=project.id, data={"text": "x"}, inner_id=1)
        self.db.add(task)
        self.db.flush()
        return task

    def annotation(self, project: Project, task: Task, *, cancelled=False) -> Annotation:
        ann = Annotation(
            id=_uid(),
            task_id=task.id,
            project_id=project.id,
            completed_by=self.user.id,
            result=[{"value": "x"}],
            was_cancelled=cancelled,
        )
        self.db.add(ann)
        self.db.flush()
        return ann

    def generation(self, project: Project, task: Task) -> Generation:
        parent = ResponseGeneration(
            id=_uid(), project_id=project.id, task_id=task.id, model_id="gpt-4o",
            status="completed", created_by=self.user.id,
        )
        self.db.add(parent)
        self.db.flush()
        gen = Generation(
            id=_uid(), generation_id=parent.id, task_id=task.id, model_id="gpt-4o",
            run_index=0, response_content="r", case_data=json.dumps({}),
            status="completed", parse_status="success",
        )
        self.db.add(gen)
        self.db.flush()
        return gen

    def run(self, project: Project, *, status="completed", created_at=None):
        run = EvaluationRun(
            id=_uid(), project_id=project.id, model_id="gpt-4o",
            evaluation_type_ids=["x"], metrics={}, eval_metadata={}, status=status,
            created_by=self.user.id,
            created_at=created_at or datetime.now(timezone.utc),
        )
        self.db.add(run)
        self.db.flush()
        judge = EvaluationJudgeRun(
            id=_uid(), evaluation_id=run.id, judge_model_id=None, run_index=0,
            status="completed",
        )
        self.db.add(judge)
        self.db.flush()
        return run, judge

    def grade(self, run_judge, task, metrics, *, annotation=None, generation=None, config=None):
        run, judge = run_judge
        self._field += 1
        row = TaskEvaluation(
            id=_uid(), evaluation_id=run.id, judge_run_id=judge.id, task_id=task.id,
            annotation_id=annotation.id if annotation else None,
            generation_id=generation.id if generation else None,
            evaluation_config_id=config, field_name=f"field-{self._field}",
            answer_type="text", ground_truth="x", prediction="x",
            metrics=metrics, passed=True,
        )
        self.db.add(row)
        self.db.flush()
        return row


def _reference_count(db: Session, project_id: str, cutoff=None) -> int:
    """The definition, computed in Python from the rows themselves."""
    cells = set()
    rows = (
        db.query(TaskEvaluation, EvaluationRun)
        .join(EvaluationRun, EvaluationRun.id == TaskEvaluation.evaluation_id)
        .filter(EvaluationRun.project_id == project_id)
        .all()
    )
    for te, run in rows:
        if run.status != "completed":
            continue
        if cutoff is not None and run.created_at < cutoff:
            continue
        subject = te.annotation_id or te.generation_id
        if subject is None or not isinstance(te.metrics, dict):
            continue
        if te.annotation_id is not None:
            ann = db.get(Annotation, te.annotation_id)
            if ann is not None and ann.was_cancelled:
                continue
        for key in te.metrics:
            if metric_key_counts_as_evaluation(key):
                cells.add((subject, te.evaluation_config_id or "", key))
    return len(cells)


@pytest.fixture
def world(test_db: Session):
    w = _World(test_db)
    p = w.project()
    t1, t2, t3 = w.task(p), w.task(p), w.task(p)
    active = w.annotation(p, t1)
    cancelled = w.annotation(p, t2, cancelled=True)
    gen = w.generation(p, t3)
    run = w.run(p)
    rerun = w.run(p)
    failed = w.run(p, status="failed")
    judged = {"value": 0.7, "details": {"grade_points": 12}}

    # One annotation, two judge configs of the same metric: 2 evaluations.
    # The noise keys next to them count nothing.
    w.grade(run, t1, {"llm_judge_custom": judged, "llm_judge_custom_details": {}, "raw_score": 3},
            annotation=active, config="cfg-a")
    w.grade(run, t1, {"llm_judge_custom": judged}, annotation=active, config="cfg-b")
    # A re-run of cfg-a on the same answer is the same evaluation: +0.
    w.grade(rerun, t1, {"llm_judge_custom": judged}, annotation=active, config="cfg-a")
    # Grades of a cancelled annotation do not count: +0.
    w.grade(run, t2, {"llm_judge_custom": judged}, annotation=cancelled, config="cfg-a")
    # A generation scored on two metrics plus the Notenpunkte twin of a
    # third (a second view of one judge call, not an evaluation): +2.
    w.grade(run, t3, {"bleu": 0.5, "rouge": 0.4, "llm_judge_falloesung_grade_points": 12},
            generation=gen)
    # A failed run counts nothing, neither does a non-object metrics blob.
    w.grade(failed, t3, {"meteor": 0.3}, generation=gen)
    w.grade(run, t3, [1, 2], generation=gen, config="cfg-list")

    # A second project, counted on its own.
    q = w.project()
    tq = w.task(q)
    gq = w.generation(q, tq)
    w.grade(w.run(q), tq, {"exact_match": 1.0}, generation=gq)
    test_db.commit()
    return {"w": w, "p": p, "q": q, "t3": t3, "gen": gen, "run": run}


def _mirror(db: Session, task_evaluation_id: str):
    return db.execute(
        text(
            "SELECT evaluation_id, annotation_id, generation_id, evaluation_config_id, "
            "metric_keys FROM task_evaluation_metric_keys WHERE task_evaluation_id = :id"
        ),
        {"id": task_evaluation_id},
    ).mappings().first()


class TestMirrorTriggers:
    def test_insert_and_updates_keep_the_mirror(self, test_db, world):
        w = world["w"]
        row = w.grade(world["run"], world["t3"], {"rouge": 1, "bleu": 2},
                      generation=world["gen"], config="cfg-x")
        mirror = _mirror(test_db, row.id)
        assert mirror["metric_keys"] == ["bleu", "rouge"]
        assert mirror["evaluation_id"] == row.evaluation_id
        assert mirror["generation_id"] == world["gen"].id
        assert mirror["evaluation_config_id"] == "cfg-x"

        test_db.execute(
            text("UPDATE task_evaluations SET metrics = CAST(:m AS jsonb) WHERE id = :id"),
            {"m": json.dumps({"chrf": 1}), "id": row.id},
        )
        assert _mirror(test_db, row.id)["metric_keys"] == ["chrf"]

        row.metrics = "not an object"
        row.evaluation_config_id = "cfg-y"
        test_db.flush()
        mirror = _mirror(test_db, row.id)
        assert mirror["metric_keys"] == []
        assert mirror["evaluation_config_id"] == "cfg-y"

        test_db.delete(row)
        test_db.flush()
        assert _mirror(test_db, row.id) is None

    def test_deleted_annotation_clears_the_subject(self, test_db, world):
        """ON DELETE SET NULL on task_evaluations.annotation_id is an UPDATE
        the trigger mirrors, so the grade stops counting for that answer."""
        w, p = world["w"], world["p"]
        task = w.task(p)
        ann = w.annotation(p, task)
        row = w.grade(world["run"], task, {"exact_match": 1}, annotation=ann)
        assert _mirror(test_db, row.id)["annotation_id"] == ann.id
        test_db.execute(text("DELETE FROM annotations WHERE id = :id"), {"id": ann.id})
        assert _mirror(test_db, row.id)["annotation_id"] is None

    def test_every_task_evaluation_has_its_mirror(self, test_db, world):
        missing = test_db.execute(
            text(
                "SELECT count(*) FROM task_evaluations te WHERE NOT EXISTS (SELECT 1 FROM "
                "task_evaluation_metric_keys k WHERE k.task_evaluation_id = te.id)"
            )
        ).scalar()
        assert missing == 0


class TestCountingSemantics:
    def test_count_matches_the_definition(self, test_db, world):
        p, q = world["p"].id, world["q"].id
        counts = count_eval_pairs_by_project(test_db, [p, q])
        assert counts == {p: 4, q: 1}
        assert counts[p] == _reference_count(test_db, p)
        assert counts[q] == _reference_count(test_db, q)

    def test_projects_without_evaluations_are_zero(self, test_db, world):
        empty = world["w"].project()
        assert count_eval_pairs_by_project(test_db, [empty.id]) == {empty.id: 0}
        assert count_eval_pairs_by_project(test_db, []) == {}

    def test_cutoff_drops_older_runs(self, test_db, world):
        w, p = world["w"], world["p"]
        old = w.run(p, created_at=datetime.now(timezone.utc) - timedelta(days=60))
        w.grade(old, world["t3"], {"chrf": 0.2}, generation=world["gen"])
        test_db.commit()
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        assert count_eval_pairs_by_project(test_db, [p.id])[p.id] == 5
        assert count_eval_pairs_by_project(test_db, [p.id], cutoff)[p.id] == 4
        assert _reference_count(test_db, p.id, cutoff) == 4

    def test_live_fallback_matches_the_refreshed_summary(self, test_db, world):
        p = world["p"].id
        # No summary row yet: the project list counts live.
        assert read_project_summary(test_db, p) is None
        live = calculate_project_stats_batch(test_db, [p])[p]["evaluation_count"]
        recompute_project_summaries(test_db)
        summary = read_project_summary(test_db, p)
        assert summary is not None
        assert live == summary.evaluation_pairs_count == 4
        assert calculate_project_stats_batch(test_db, [p])[p]["evaluation_count"] == 4

    def test_refresh_waits_for_the_backfill(self, test_db, world, monkeypatch):
        monkeypatch.setattr(aggregate_summaries, "_metric_keys_filled", lambda _db: False)
        assert recompute_project_summaries(test_db) == 0
        assert read_project_summary(test_db, world["p"].id) is None


class TestCountingCost:
    """The count must stay cheap at any table size: it reads the narrow
    mirror only, never task_evaluations and its metrics blob."""

    def test_reads_only_the_mirror(self):
        sql = aggregate_summaries._EVAL_CELL_COUNTS_SQL
        assert "task_evaluations" not in sql
        assert "metrics" not in sql.replace("metric_keys", "").replace("metric_key", "")
        assert "jsonb_object_keys" not in sql

    def test_statement_runs_against_the_schema(self, test_db, world):
        stmt, params = _eval_cell_counts_stmt([world["p"].id], None)
        plan = "\n".join(
            r[0] for r in test_db.execute(text(f"EXPLAIN (VERBOSE) {stmt.text}"), params)
        )
        assert "task_evaluation_metric_keys" in plan
        assert "public.task_evaluations " not in plan
