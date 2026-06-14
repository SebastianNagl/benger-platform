"""Integration tests for uncovered branches of the evaluation results &
status routers.

Targets:
- ``services/api/routers/evaluations/results.py`` (mounted at
  ``/api/evaluations`` via routers/evaluations/__init__.py)
- ``services/api/routers/evaluations/status.py`` (same prefix)

The existing suites (``test_evaluation_results_deep.py``,
``test_coverage_eval_results_deep3.py``) already cover the happy paths and
the simple 404s. This file fills in the branches those leave uncovered:

results.py
  * GET /{evaluation_id}/samples ........ 403 access-denied, empty-page
    (``has_next`` False), pagination tail.
  * GET /{evaluation_id}/metrics/{m}/distribution ... 403, the
    "No samples found" 404 (zero rows) vs "Metric not found" 404 (rows
    but no such key), and the >=4-values real-quantile quartile path.
  * GET /{evaluation_id}/confusion-matrix ... 403, the 400 "No valid
    ground truth/prediction pairs" guard (rows present, gt/pred NULL).
  * GET /{evaluation_id}/results/by-task-model ... 403, the
    ``include_history=True`` mean-aggregation branch, the annotation
    synthetic-``annotator:`` branch, the empty-result shape.
  * GET /projects/{project_id}/results/by-task-model ... 404 project,
    403, ``evaluation_ids`` filter, ``metric`` filter, the
    ``include_history=True`` mean branch, ``deduplication_summary`` with a
    non-zero suppressed_run_count, and the no-completed-evals
    ``_build_all_tasks_response`` shape.
  * GET /sample-result ... task 404, 403, no-results empty message,
    generation-based results, the ``annotator:`` resolution branch, the
    ``generation_id`` cohesion filter, and the ``include_history=False``
    per-field dedup.

status.py
  * GET /evaluation/status/{id} ... the 403 access-denied branch.
  * GET / (list) ... org-scoped contributor vs superadmin-sees-all, and
    the empty-accessible short-circuit.
  * GET /evaluation-types ... combined category+task_type filter, and
    GET /evaluation-types/{id} the is_active=False 404 branch.

Each test calls the endpoint via ``client`` and asserts the HTTP status +
response JSON; data-shaping tests also assert the seeded DB rows that drive
the branch. Seeding mirrors the FK-valid idioms of
``test_coverage_eval_results_deep3.py`` (ResponseGeneration parent +
Generation child, EvaluationJudgeRun parent for every TaskEvaluation, the
uq_task_evaluations_cell distinct-subject rule).

MinIO byte-streaming export endpoints are deliberately out of scope — only
the Postgres-backed JSON export branch is touched (and that only lightly,
since it is already covered elsewhere).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from models import (
    EvaluationJudgeRun,
    EvaluationRun,
    EvaluationType,
    Generation,
    LLMModel,
    ResponseGeneration,
    TaskEvaluation,
)
from project_models import (
    Annotation,
    Project,
    ProjectOrganization,
    Task,
)

BASE = "/api/evaluations"


# ---------------------------------------------------------------------------
# Seeding helpers (mirror test_coverage_eval_results_deep3.py exactly)
# ---------------------------------------------------------------------------


def _uid() -> str:
    return str(uuid.uuid4())


def _setup_project(db, admin, org, *, num_tasks=3, is_private=False, link_org=True):
    """Create a project owned by ``admin`` with ``num_tasks`` tasks, linked to
    ``org`` (so org-context members pass the access check). Set is_private=True
    + link_org=False to build the 403 fixture (a private project a
    non-creator non-superadmin cannot reach)."""
    pid = _uid()
    p = Project(
        id=pid,
        title=f"Eval Branch {pid[:6]}",
        created_by=admin.id,
        is_private=is_private,
        label_config=(
            '<View><Text name="text" value="$text"/>'
            '<Choices name="answer" toName="text">'
            '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>'
        ),
    )
    db.add(p)
    db.flush()

    if link_org:
        db.add(ProjectOrganization(
            id=_uid(), project_id=pid,
            organization_id=org.id, assigned_by=admin.id,
        ))
        db.flush()

    tasks = []
    for i in range(num_tasks):
        t = Task(
            id=_uid(), project_id=pid,
            data={"text": f"Eval task #{i}", "content": f"Content {i}"},
            inner_id=i + 1, created_by=admin.id,
        )
        db.add(t)
        tasks.append(t)
    db.flush()
    return p, tasks


def _make_eval_run(db, project, admin_id="admin-test-id", *, status="completed",
                   metrics=None, eval_metadata=None, model_id="gpt-4"):
    er = EvaluationRun(
        id=_uid(),
        project_id=project.id,
        model_id=model_id,
        evaluation_type_ids=["accuracy", "f1"],
        status=status,
        metrics=metrics or {"accuracy": 0.85, "f1": 0.82},
        samples_evaluated=10,
        eval_metadata=eval_metadata or {"type": "automated"},
        created_by=admin_id,
    )
    db.add(er)
    db.flush()
    # Migration 043 made TaskEvaluation.judge_run_id NOT NULL: every
    # TaskEvaluation needs a parent judge run. Catch-all shape.
    judge_run = EvaluationJudgeRun(
        id=_uid(),
        evaluation_id=er.id,
        judge_model_id=None,
        run_index=0,
        status="completed",
    )
    db.add(judge_run)
    db.flush()
    er._test_judge_run = judge_run
    return er


def _add_judge_run(db, eval_run, run_index=1):
    """Add a SECOND judge run to an existing eval run. Lets two
    TaskEvaluations share the same (generation_id, field_name) cell without
    tripping uq_task_evaluations_cell (049): the index keys on judge_run_id
    too, so distinct judge runs keep both rows alive while the endpoint's
    (generation_id, field_name) dedup still treats them as one cell."""
    jr = EvaluationJudgeRun(
        id=_uid(),
        evaluation_id=eval_run.id,
        judge_model_id=None,
        run_index=run_index,
        status="completed",
    )
    db.add(jr)
    db.flush()
    return jr


def _make_generation(db, task, *, model_id="gpt-4", created_at=None,
                     response_generation=None):
    """A minimal FK-valid generation (ResponseGeneration parent + Generation
    child). When ``response_generation`` is supplied the Generation hangs off
    it (lets multiple Generations share one ResponseGeneration id, which is
    what the /sample-result ``generation_id`` filter keys on)."""
    if response_generation is None:
        rg = ResponseGeneration(
            id=_uid(),
            project_id=task.project_id,
            task_id=task.id,
            model_id=model_id,
            status="completed",
            created_by=task.created_by,
        )
        db.add(rg)
        db.flush()
    else:
        rg = response_generation
    gen_kwargs = dict(
        id=_uid(),
        generation_id=rg.id,
        task_id=task.id,
        model_id=model_id,
        run_index=0,
        case_data="{}",
        response_content="x",
        status="completed",
        parse_status="success",
    )
    # created_at is NOT NULL with a server_default; only set it when a caller
    # needs a specific value (window-function ordering tests), otherwise let
    # the DB default fire — passing None explicitly would insert NULL.
    if created_at is not None:
        gen_kwargs["created_at"] = created_at
    gen = Generation(**gen_kwargs)
    db.add(gen)
    db.flush()
    return gen, rg


def _make_task_evaluation(db, eval_run, task, *, metrics=None, generation=None,
                          annotation=None, field_name="answer",
                          ground_truth=None, prediction=None, passed=True,
                          created_at=None, answer_type="choices", judge_run=None):
    """uq_task_evaluations_cell keys a row on its scored subject
    (generation_id / annotation_id / created_by), so a real row always has a
    generation OR an annotation. Synthesize a distinct generation when none is
    supplied, otherwise two rows in the same run+field collapse to one cell."""
    if generation is None and annotation is None:
        generation, _ = _make_generation(db, task)
    te_kwargs = dict(
        id=_uid(),
        evaluation_id=eval_run.id,
        judge_run_id=(judge_run or eval_run._test_judge_run).id,
        task_id=task.id,
        generation_id=generation.id if generation else None,
        annotation_id=annotation.id if annotation else None,
        field_name=field_name,
        answer_type=answer_type,
        metrics=metrics if metrics is not None else {"score": 0.9},
        passed=passed,
        ground_truth=ground_truth if ground_truth is not None else {"value": "Ja"},
        prediction=prediction if prediction is not None else {"value": "Ja"},
    )
    # created_at is NOT NULL with a server_default; only set it when a caller
    # needs a specific ordering value, else let the DB default fire.
    if created_at is not None:
        te_kwargs["created_at"] = created_at
    te = TaskEvaluation(**te_kwargs)
    db.add(te)
    db.flush()
    return te


def _make_annotation(db, task, project, user_id):
    ann = Annotation(
        id=_uid(), task_id=task.id, project_id=project.id,
        completed_by=user_id,
        result=[{"from_name": "answer", "to_name": "text", "type": "choices",
                 "value": {"choices": ["Ja"]}}],
        was_cancelled=False,
    )
    db.add(ann)
    db.flush()
    return ann


def _make_llm_model(db, model_id, name=None):
    if db.query(LLMModel).filter(LLMModel.id == model_id).first():
        return
    db.add(LLMModel(
        id=model_id, name=name or model_id, provider="openai",
        model_type="chat", capabilities=["text_generation"], is_active=True,
    ))
    db.flush()


def _h(auth_headers, org):
    """Admin auth + this org's context header (mirrors the deep suites)."""
    return {**auth_headers["admin"], "X-Organization-Context": org.id}


# ===========================================================================
# results.py — GET /{evaluation_id}/samples : uncovered branches
# ===========================================================================


@pytest.mark.integration
class TestSamplesBranches:
    def test_samples_access_denied_403(self, client, test_db, test_users, auth_headers, test_org):
        """The evaluation exists (passes the 404 guard) but its project is a
        private project owned by admin — a non-creator non-superadmin with org
        context hits the 403 'Access denied' branch."""
        p, tasks = _setup_project(
            test_db, test_users[0], test_org, is_private=True, link_org=False,
        )
        er = _make_eval_run(test_db, p)
        _make_task_evaluation(test_db, er, tasks[0])
        test_db.commit()

        resp = client.get(
            f"{BASE}/{er.id}/samples",
            headers={**auth_headers["annotator"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"] == "Access denied"

    def test_samples_last_page_has_next_false(self, client, test_db, test_users, auth_headers, test_org):
        """page_size that exactly drains the rows on the last page → has_next
        is False (the ``(offset + page_size) < total`` branch evaluated
        False)."""
        p, tasks = _setup_project(test_db, test_users[0], test_org, num_tasks=3)
        er = _make_eval_run(test_db, p)
        for t in tasks:
            _make_task_evaluation(test_db, er, t)
        test_db.commit()

        # 3 rows, page 2 size 2 → 1 row, offset 2, (2+2)=4 !< 3 → has_next False
        resp = client.get(
            f"{BASE}/{er.id}/samples?page=2&page_size=2",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 3
        assert body["page"] == 2
        assert len(body["items"]) == 1
        assert body["has_next"] is False

    def test_samples_page_past_end_empty_items(self, client, test_db, test_users, auth_headers, test_org):
        """A page beyond the data returns an empty item list but still a 200
        with the correct total (offset past the end)."""
        p, tasks = _setup_project(test_db, test_users[0], test_org, num_tasks=2)
        er = _make_eval_run(test_db, p)
        for t in tasks:
            _make_task_evaluation(test_db, er, t)
        test_db.commit()

        resp = client.get(
            f"{BASE}/{er.id}/samples?page=5&page_size=10",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 2
        assert body["items"] == []
        assert body["has_next"] is False


# ===========================================================================
# results.py — GET /{evaluation_id}/metrics/{metric}/distribution
# ===========================================================================


@pytest.mark.integration
class TestDistributionBranches:
    def test_distribution_access_denied_403(self, client, test_db, test_users, auth_headers, test_org):
        p, tasks = _setup_project(
            test_db, test_users[0], test_org, is_private=True, link_org=False,
        )
        er = _make_eval_run(test_db, p)
        _make_task_evaluation(test_db, er, tasks[0], metrics={"score": 0.5})
        test_db.commit()

        resp = client.get(
            f"{BASE}/{er.id}/metrics/score/distribution",
            headers={**auth_headers["contributor"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"] == "Access denied"

    def test_distribution_no_samples_at_all_404(self, client, test_db, test_users, auth_headers, test_org):
        """An eval run with zero TaskEvaluation rows hits the 'No samples found
        for this evaluation' 404 — a DIFFERENT branch from the metric-missing
        404 (which requires rows to exist)."""
        p, tasks = _setup_project(test_db, test_users[0], test_org)
        er = _make_eval_run(test_db, p)
        test_db.commit()

        # DB-state: no task_evaluations for this run.
        assert (
            test_db.query(TaskEvaluation)
            .filter(TaskEvaluation.evaluation_id == er.id)
            .count()
        ) == 0

        resp = client.get(
            f"{BASE}/{er.id}/metrics/score/distribution",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404, resp.text
        assert "No samples found for this evaluation" in resp.json()["detail"]

    def test_distribution_metric_missing_from_present_samples_404(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """Rows exist (so the no-samples guard passes) but none carry the
        requested metric key → the 'Metric ... not found in samples' 404."""
        p, tasks = _setup_project(test_db, test_users[0], test_org, num_tasks=2)
        er = _make_eval_run(test_db, p)
        for t in tasks:
            _make_task_evaluation(test_db, er, t, metrics={"accuracy": 0.7})
        test_db.commit()

        resp = client.get(
            f"{BASE}/{er.id}/metrics/bleu/distribution",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404, resp.text
        assert "bleu" in resp.json()["detail"]
        assert "not found in samples" in resp.json()["detail"]

    def test_distribution_quartiles_with_four_plus_values(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """With >=4 distinct values the q1/q3 take the real
        ``statistics.quantiles`` branch (not the len<4 fallback to
        min/max), and q1 <= median <= q3 holds. Also pins mean/min/max."""
        p, tasks = _setup_project(test_db, test_users[0], test_org, num_tasks=5)
        er = _make_eval_run(test_db, p)
        vals = [0.1, 0.3, 0.5, 0.7, 0.9]
        for t, v in zip(tasks, vals):
            _make_task_evaluation(test_db, er, t, metrics={"score": v})
        test_db.commit()

        resp = client.get(
            f"{BASE}/{er.id}/metrics/score/distribution",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["metric_name"] == "score"
        assert body["min"] == pytest.approx(0.1)
        assert body["max"] == pytest.approx(0.9)
        assert body["mean"] == pytest.approx(0.5)
        assert body["median"] == pytest.approx(0.5)
        q = body["quartiles"]
        # >=4 values → real quantiles, monotone and strictly inside (min,max).
        assert q["q1"] < q["q2"] < q["q3"]
        assert q["q1"] > body["min"]
        assert q["q3"] < body["max"]
        assert len(body["histogram"]) == 10


# ===========================================================================
# results.py — GET /{evaluation_id}/confusion-matrix
# ===========================================================================


@pytest.mark.integration
class TestConfusionMatrixBranches:
    def test_confusion_matrix_access_denied_403(self, client, test_db, test_users, auth_headers, test_org):
        p, tasks = _setup_project(
            test_db, test_users[0], test_org, is_private=True, link_org=False,
        )
        er = _make_eval_run(test_db, p)
        _make_task_evaluation(
            test_db, er, tasks[0], field_name="answer",
            ground_truth={"value": "ja"}, prediction={"value": "ja"},
        )
        test_db.commit()

        resp = client.get(
            f"{BASE}/{er.id}/confusion-matrix?field_name=answer",
            headers={**auth_headers["annotator"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"] == "Access denied"

    def test_confusion_matrix_no_valid_pairs_400(self, client, test_db, test_users, auth_headers, test_org):
        """Samples exist for the field (so the no-samples 404 passes) but their
        ground_truth/prediction values are NULL → the
        'No valid ground truth/prediction pairs found' 400 guard. We supply a
        JSON object WITHOUT a 'value' key so ``.get('value')`` is None."""
        p, tasks = _setup_project(test_db, test_users[0], test_org, num_tasks=2)
        er = _make_eval_run(test_db, p)
        for t in tasks:
            _make_task_evaluation(
                test_db, er, t, field_name="answer",
                ground_truth={"other": "x"}, prediction={"other": "y"},
            )
        test_db.commit()

        # DB-state: rows exist for the field, but no value subkey.
        rows = (
            test_db.query(TaskEvaluation)
            .filter(
                TaskEvaluation.evaluation_id == er.id,
                TaskEvaluation.field_name == "answer",
            )
            .all()
        )
        assert len(rows) == 2
        assert all("value" not in (r.ground_truth or {}) for r in rows)

        resp = client.get(
            f"{BASE}/{er.id}/confusion-matrix?field_name=answer",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 400, resp.text
        assert "No valid ground truth/prediction pairs" in resp.json()["detail"]

    def test_confusion_matrix_perfect_diagonal_accuracy_one(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """All predictions correct → accuracy 1.0 and per-class precision/recall
        of 1.0 for every label (exercises the TP/FP/FN arithmetic loop)."""
        p, tasks = _setup_project(test_db, test_users[0], test_org, num_tasks=4)
        er = _make_eval_run(test_db, p)
        pairs = [("ja", "ja"), ("ja", "ja"), ("nein", "nein"), ("nein", "nein")]
        for t, (gt, pred) in zip(tasks, pairs):
            _make_task_evaluation(
                test_db, er, t, field_name="answer",
                ground_truth={"value": gt}, prediction={"value": pred},
            )
        test_db.commit()

        resp = client.get(
            f"{BASE}/{er.id}/confusion-matrix?field_name=answer",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["accuracy"] == pytest.approx(1.0)
        assert sorted(body["labels"]) == ["ja", "nein"]
        for label in body["labels"]:
            assert body["precision_per_class"][label] == pytest.approx(1.0)
            assert body["recall_per_class"][label] == pytest.approx(1.0)
            assert body["f1_per_class"][label] == pytest.approx(1.0)

    def test_confusion_matrix_missing_field_name_422(self, client, test_db, test_users, auth_headers, test_org):
        """field_name is a required query param (``Query(...)``) — omitting it
        is a 422 before any DB access."""
        p, tasks = _setup_project(test_db, test_users[0], test_org)
        er = _make_eval_run(test_db, p)
        test_db.commit()

        resp = client.get(
            f"{BASE}/{er.id}/confusion-matrix",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 422, resp.text


# ===========================================================================
# results.py — GET /{evaluation_id}/results/by-task-model (eval-level)
# ===========================================================================


@pytest.mark.integration
class TestEvalByTaskModelBranches:
    def test_access_denied_403(self, client, test_db, test_users, auth_headers, test_org):
        p, tasks = _setup_project(
            test_db, test_users[0], test_org, is_private=True, link_org=False,
        )
        er = _make_eval_run(test_db, p)
        test_db.commit()

        resp = client.get(
            f"{BASE}/{er.id}/results/by-task-model",
            headers={**auth_headers["contributor"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"] == "Access denied"

    def test_include_history_means_multiple_generations(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """include_history=True averages every historical generation row for a
        (task, model) cell. Two generations for one task/model with scores 0.4
        and 0.8 → the cell mean is 0.6 (the aggregate_mean branch)."""
        _make_llm_model(test_db, "gpt-hist", "GPT Hist")
        p, tasks = _setup_project(test_db, test_users[0], test_org, num_tasks=1)
        er = _make_eval_run(test_db, p, model_id="gpt-hist")
        task = tasks[0]
        gen1, _ = _make_generation(test_db, task, model_id="gpt-hist")
        gen2, _ = _make_generation(test_db, task, model_id="gpt-hist")
        _make_task_evaluation(test_db, er, task, generation=gen1, metrics={"score": 0.4})
        _make_task_evaluation(test_db, er, task, generation=gen2, metrics={"score": 0.8})
        test_db.commit()

        resp = client.get(
            f"{BASE}/{er.id}/results/by-task-model?include_history=true",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "gpt-hist" in body["models"]
        # Cell shows the mean of 0.4 and 0.8.
        cell = next(t for t in body["tasks"] if t["task_id"] == task.id)
        assert cell["scores"]["gpt-hist"] == pytest.approx(0.6)
        assert body["summary"]["gpt-hist"]["avg"] == pytest.approx(0.6)

    def test_annotation_results_synthetic_annotator_model(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """Annotation-based TaskEvaluations (generation_id NULL, annotation_id
        set) surface as a synthetic ``annotator:<display>`` model. The display
        falls back to the user's ``name`` (Test Admin)."""
        p, tasks = _setup_project(test_db, test_users[0], test_org, num_tasks=1)
        er = _make_eval_run(test_db, p)
        ann = _make_annotation(test_db, tasks[0], p, test_users[0].id)
        _make_task_evaluation(test_db, er, tasks[0], annotation=ann, metrics={"score": 0.75})
        test_db.commit()

        resp = client.get(
            f"{BASE}/{er.id}/results/by-task-model",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        annot_models = [m for m in body["models"] if m.startswith("annotator:")]
        assert len(annot_models) == 1
        synth = annot_models[0]
        # Display resolves through name ("Test Admin") since use_pseudonym is off.
        assert synth == "annotator:Test Admin"
        assert body["model_names"][synth] == "Annotator: Test Admin"
        assert body["summary"][synth]["avg"] == pytest.approx(0.75)

    def test_empty_result_shape(self, client, test_db, test_users, auth_headers, test_org):
        """An eval run with no task_evaluations and no annotations returns the
        documented empty envelope (early-return branch)."""
        p, tasks = _setup_project(test_db, test_users[0], test_org)
        er = _make_eval_run(test_db, p)
        test_db.commit()

        resp = client.get(
            f"{BASE}/{er.id}/results/by-task-model",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body == {
            "evaluation_id": er.id,
            "models": [],
            "model_names": {},
            "tasks": [],
            "summary": {},
        }


# ===========================================================================
# results.py — GET /projects/{project_id}/results/by-task-model
# ===========================================================================


@pytest.mark.integration
class TestProjectByTaskModelBranches:
    def test_project_not_found_404(self, client, test_db, test_users, auth_headers):
        """An unknown project_id hits the first guard (the project lookup) for a
        superadmin too — 404 'Project ... not found'."""
        resp = client.get(
            f"{BASE}/projects/does-not-exist-{uuid.uuid4().hex}/results/by-task-model",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404, resp.text
        assert "not found" in resp.json()["detail"]

    def test_access_denied_403(self, client, test_db, test_users, auth_headers, test_org):
        p, tasks = _setup_project(
            test_db, test_users[0], test_org, is_private=True, link_org=False,
        )
        test_db.commit()

        resp = client.get(
            f"{BASE}/projects/{p.id}/results/by-task-model",
            headers={**auth_headers["annotator"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"] == "Access denied"

    def test_no_completed_evals_builds_all_tasks(self, client, test_db, test_users, auth_headers, test_org):
        """A project whose only eval run is ``failed`` (excluded by the
        status filter) yields no completed_eval_ids → the early return that
        still lists every project task via _build_all_tasks_response, with
        empty scores and the data-availability fields present."""
        p, tasks = _setup_project(test_db, test_users[0], test_org, num_tasks=3)
        _make_eval_run(test_db, p, status="failed")
        test_db.commit()

        resp = client.get(
            f"{BASE}/projects/{p.id}/results/by-task-model",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["models"] == []
        assert body["summary"] == {}
        assert {t["task_id"] for t in body["tasks"]} == {t.id for t in tasks}
        for t in body["tasks"]:
            assert t["scores"] == {}
            assert "has_annotation" in t
            assert "generation_models" in t
            assert "annotator_columns" in t

    def test_evaluation_ids_filter_scopes_results(self, client, test_db, test_users, auth_headers, test_org):
        """The ``evaluation_ids`` query restricts which runs feed the matrix.
        Two completed runs on the same task/model with different scores; asking
        for only run A surfaces A's score, not B's."""
        _make_llm_model(test_db, "gpt-filter", "GPT Filter")
        p, tasks = _setup_project(test_db, test_users[0], test_org, num_tasks=1)
        task = tasks[0]
        # Run A: score 0.2 on an older generation.
        er_a = _make_eval_run(test_db, p, model_id="gpt-filter")
        gen_a, _ = _make_generation(
            test_db, task, model_id="gpt-filter",
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        _make_task_evaluation(test_db, er_a, task, generation=gen_a, metrics={"score": 0.2})
        # Run B: score 0.9 on a newer generation.
        er_b = _make_eval_run(test_db, p, model_id="gpt-filter")
        gen_b, _ = _make_generation(
            test_db, task, model_id="gpt-filter",
            created_at=datetime.now(timezone.utc),
        )
        _make_task_evaluation(test_db, er_b, task, generation=gen_b, metrics={"score": 0.9})
        test_db.commit()

        # include_history=true so we average ALL rows of the filtered run
        # rather than latest-gen-only (which would dedup to one gen).
        resp = client.get(
            f"{BASE}/projects/{p.id}/results/by-task-model"
            f"?evaluation_ids={er_a.id}&include_history=true",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        cell = next(t for t in body["tasks"] if t["task_id"] == task.id)
        # Only run A is in scope → 0.2, run B's 0.9 is excluded.
        assert cell["scores"].get("gpt-filter") == pytest.approx(0.2)

    def test_metric_filter_selects_key(self, client, test_db, test_users, auth_headers, test_org):
        """When a run bundles two metrics in one row, ``metric=`` keeps only
        rows carrying that key. A row with both 'bleu' and 'rouge' is returned
        for metric=bleu and the score is the bleu value (primary-score
        extraction over the lite-projected metrics)."""
        _make_llm_model(test_db, "gpt-metric", "GPT Metric")
        p, tasks = _setup_project(test_db, test_users[0], test_org, num_tasks=1)
        task = tasks[0]
        er = _make_eval_run(test_db, p, model_id="gpt-metric")
        gen, _ = _make_generation(test_db, task, model_id="gpt-metric")
        _make_task_evaluation(
            test_db, er, task, generation=gen,
            metrics={"bleu": 0.42},
        )
        test_db.commit()

        resp = client.get(
            f"{BASE}/projects/{p.id}/results/by-task-model?metric=bleu",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        cell = next(t for t in body["tasks"] if t["task_id"] == task.id)
        assert cell["scores"].get("gpt-metric") == pytest.approx(0.42)

        # A metric absent from every row → no score for that cell.
        resp2 = client.get(
            f"{BASE}/projects/{p.id}/results/by-task-model?metric=does_not_exist",
            headers=_h(auth_headers, test_org),
        )
        assert resp2.status_code == 200, resp2.text
        body2 = resp2.json()
        cell2 = next(t for t in body2["tasks"] if t["task_id"] == task.id)
        assert cell2["scores"] == {}

    def test_deduplication_summary_counts_suppressed(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """Two TaskEvaluation rows for the SAME (generation_id, field_name)
        differing only by created_at → the latest wins and the older is
        suppressed; deduplication_summary.suppressed_run_count reflects it."""
        _make_llm_model(test_db, "gpt-dedup", "GPT Dedup")
        p, tasks = _setup_project(test_db, test_users[0], test_org, num_tasks=1)
        task = tasks[0]
        er = _make_eval_run(test_db, p, model_id="gpt-dedup")
        gen, _ = _make_generation(test_db, task, model_id="gpt-dedup")
        # Same gen + same field, two evals → one is suppressed by latest-wins.
        # They sit under two different judge runs so uq_task_evaluations_cell
        # (049, which keys on judge_run_id) lets both rows persist; the
        # endpoint's (generation_id, field_name) partition still collapses
        # them to one cell, suppressing the older.
        jr2 = _add_judge_run(test_db, er)
        _make_task_evaluation(
            test_db, er, task, generation=gen, field_name="answer",
            metrics={"score": 0.3},
            created_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        _make_task_evaluation(
            test_db, er, task, generation=gen, field_name="answer",
            metrics={"score": 0.7}, judge_run=jr2,
            created_at=datetime.now(timezone.utc),
        )
        test_db.commit()

        resp = client.get(
            f"{BASE}/projects/{p.id}/results/by-task-model",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        dedup = body["deduplication_summary"]
        assert dedup["scope"] == "(generation_id, field_name)"
        assert dedup["policy"] == "latest_wins_by_created_at_desc"
        assert dedup["suppressed_run_count"] == 1
        # Cell shows the latest (0.7), not the suppressed 0.3.
        cell = next(t for t in body["tasks"] if t["task_id"] == task.id)
        assert cell["scores"].get("gpt-dedup") == pytest.approx(0.7)

    def test_include_history_means_project_level(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """include_history=True at the project level averages the per-cell
        rows. Two generations for one (task, model), scores 0.2 and 0.6 →
        cell mean 0.4."""
        _make_llm_model(test_db, "gpt-phist", "GPT PHist")
        p, tasks = _setup_project(test_db, test_users[0], test_org, num_tasks=1)
        task = tasks[0]
        er = _make_eval_run(test_db, p, model_id="gpt-phist")
        gen1, _ = _make_generation(test_db, task, model_id="gpt-phist")
        gen2, _ = _make_generation(test_db, task, model_id="gpt-phist")
        _make_task_evaluation(test_db, er, task, generation=gen1, metrics={"score": 0.2})
        _make_task_evaluation(test_db, er, task, generation=gen2, metrics={"score": 0.6})
        test_db.commit()

        resp = client.get(
            f"{BASE}/projects/{p.id}/results/by-task-model?include_history=true",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        cell = next(t for t in body["tasks"] if t["task_id"] == task.id)
        assert cell["scores"].get("gpt-phist") == pytest.approx(0.4)


# ===========================================================================
# results.py — GET /sample-result  (entirely uncovered)
# ===========================================================================


@pytest.mark.integration
class TestSampleResultBranches:
    def test_task_not_found_404(self, client, test_db, test_users, auth_headers, test_org):
        resp = client.get(
            f"{BASE}/sample-result?task_id=nonexistent-{uuid.uuid4().hex}&model_id=gpt-4",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404, resp.text
        assert "not found" in resp.json()["detail"]

    def test_access_denied_403(self, client, test_db, test_users, auth_headers, test_org):
        p, tasks = _setup_project(
            test_db, test_users[0], test_org, is_private=True, link_org=False,
        )
        test_db.commit()

        resp = client.get(
            f"{BASE}/sample-result?task_id={tasks[0].id}&model_id=gpt-4",
            headers={**auth_headers["contributor"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"] == "Access denied"

    def test_no_results_returns_empty_message(self, client, test_db, test_users, auth_headers, test_org):
        """Task is accessible but has no evaluations for the model → the
        empty-results envelope with the explanatory message."""
        p, tasks = _setup_project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.get(
            f"{BASE}/sample-result?task_id={tasks[0].id}&model_id=gpt-4",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["task_id"] == tasks[0].id
        assert body["model_id"] == "gpt-4"
        assert body["results"] == []
        assert "No evaluation results" in body["message"]

    def test_generation_based_results(self, client, test_db, test_users, auth_headers, test_org):
        """A generation-based TaskEvaluation for the task+model is returned with
        full detail (metrics, ground_truth, prediction, evaluation_context)."""
        p, tasks = _setup_project(test_db, test_users[0], test_org, num_tasks=1)
        task = tasks[0]
        er = _make_eval_run(test_db, p, model_id="gpt-4",
                            eval_metadata={"evaluation_type": "llm_judge"})
        gen, _ = _make_generation(test_db, task, model_id="gpt-4")
        _make_task_evaluation(
            test_db, er, task, generation=gen, field_name="answer",
            metrics={"score": 0.66}, passed=True,
        )
        test_db.commit()

        resp = client.get(
            f"{BASE}/sample-result?task_id={task.id}&model_id=gpt-4",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_count"] == 1
        row = body["results"][0]
        assert row["field_name"] == "answer"
        assert row["metrics"] == {"score": 0.66}
        assert row["passed"] is True
        assert row["evaluation_context"]["status"] == "completed"
        assert row["evaluation_context"]["evaluation_type"] == "llm_judge"

    def test_generation_id_filter_cohesion(self, client, test_db, test_users, auth_headers, test_org):
        """The ``generation_id`` param filters on Generation.generation_id (the
        FK back to ResponseGeneration), not TaskEvaluation.generation_id. Two
        ResponseGeneration parents for the same task/model; filtering by one
        parent id returns only its evaluation."""
        p, tasks = _setup_project(test_db, test_users[0], test_org, num_tasks=1)
        task = tasks[0]
        er = _make_eval_run(test_db, p, model_id="gpt-4")
        # Two distinct ResponseGeneration parents, each with one child Generation.
        gen_a, rg_a = _make_generation(test_db, task, model_id="gpt-4")
        gen_b, rg_b = _make_generation(test_db, task, model_id="gpt-4")
        _make_task_evaluation(test_db, er, task, generation=gen_a,
                              field_name="answer", metrics={"score": 0.11})
        _make_task_evaluation(test_db, er, task, generation=gen_b,
                              field_name="comment", metrics={"score": 0.99})
        test_db.commit()

        # Filter to parent rg_a → only gen_a's eval (score 0.11) comes back.
        resp = client.get(
            f"{BASE}/sample-result?task_id={task.id}&model_id=gpt-4"
            f"&generation_id={rg_a.id}",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_count"] == 1
        assert body["results"][0]["metrics"] == {"score": 0.11}

    def test_include_history_false_dedups_per_field(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """include_history=false keeps only the latest row per field_name.
        Two evals on the same field (different generations) collapse to one;
        a second field survives → 2 rows total, latest per field."""
        p, tasks = _setup_project(test_db, test_users[0], test_org, num_tasks=1)
        task = tasks[0]
        er = _make_eval_run(test_db, p, model_id="gpt-4")
        gen1, _ = _make_generation(test_db, task, model_id="gpt-4")
        gen2, _ = _make_generation(test_db, task, model_id="gpt-4")
        gen3, _ = _make_generation(test_db, task, model_id="gpt-4")
        # Two rows on field "answer" (older + newer) + one row on "comment".
        _make_task_evaluation(
            test_db, er, task, generation=gen1, field_name="answer",
            metrics={"score": 0.1},
            created_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        _make_task_evaluation(
            test_db, er, task, generation=gen2, field_name="answer",
            metrics={"score": 0.5},
            created_at=datetime.now(timezone.utc),
        )
        _make_task_evaluation(
            test_db, er, task, generation=gen3, field_name="comment",
            metrics={"score": 0.9},
        )
        test_db.commit()

        # history on → all 3 rows.
        resp_all = client.get(
            f"{BASE}/sample-result?task_id={task.id}&model_id=gpt-4&include_history=true",
            headers=_h(auth_headers, test_org),
        )
        assert resp_all.status_code == 200, resp_all.text
        assert resp_all.json()["total_count"] == 3

        # history off → one per field (2 fields). The "answer" survivor is the
        # latest (0.5), not 0.1.
        resp_dedup = client.get(
            f"{BASE}/sample-result?task_id={task.id}&model_id=gpt-4&include_history=false",
            headers=_h(auth_headers, test_org),
        )
        assert resp_dedup.status_code == 200, resp_dedup.text
        body = resp_dedup.json()
        assert body["total_count"] == 2
        by_field = {r["field_name"]: r["metrics"]["score"] for r in body["results"]}
        assert by_field == {"answer": 0.5, "comment": 0.9}

    def test_annotator_model_resolution(self, client, test_db, test_users, auth_headers, test_org):
        """A ``model_id`` of ``annotator:<display>`` resolves the user back
        through the pseudonym→name→username precedence and returns the
        annotation-based evaluation rows for that user."""
        p, tasks = _setup_project(test_db, test_users[0], test_org, num_tasks=1)
        task = tasks[0]
        er = _make_eval_run(test_db, p)
        ann = _make_annotation(test_db, task, p, test_users[0].id)
        _make_task_evaluation(
            test_db, er, task, annotation=ann, field_name="answer",
            metrics={"score": 0.55},
        )
        test_db.commit()

        # admin's display name is "Test Admin" (use_pseudonym off → name wins).
        resp = client.get(
            f"{BASE}/sample-result?task_id={task.id}&model_id=annotator:Test Admin",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_count"] == 1
        assert body["results"][0]["metrics"] == {"score": 0.55}

    def test_annotator_unknown_display_empty(self, client, test_db, test_users, auth_headers, test_org):
        """An ``annotator:<display>`` that matches no user resolves to no rows
        → the empty envelope (the ``user is None`` → sample_results = []
        branch)."""
        p, tasks = _setup_project(test_db, test_users[0], test_org, num_tasks=1)
        test_db.commit()

        resp = client.get(
            f"{BASE}/sample-result?task_id={tasks[0].id}"
            f"&model_id=annotator:Nobody {uuid.uuid4().hex}",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["results"] == []

    def test_missing_required_query_params_422(self, client, test_db, test_users, auth_headers, test_org):
        """task_id and model_id are required (``Query(...)``) — omitting model_id
        is a 422."""
        p, tasks = _setup_project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.get(
            f"{BASE}/sample-result?task_id={tasks[0].id}",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 422, resp.text


# ===========================================================================
# status.py — GET /evaluation/status/{id} : 403 branch
# ===========================================================================


@pytest.mark.integration
class TestStatusBranches:
    def test_status_access_denied_403(self, client, test_db, test_users, auth_headers, test_org):
        """The run exists (passes 404) but its private project is not the
        requester's → 403 with the status-specific message."""
        p, tasks = _setup_project(
            test_db, test_users[0], test_org, is_private=True, link_org=False,
        )
        er = _make_eval_run(test_db, p, status="running")
        test_db.commit()

        resp = client.get(
            f"{BASE}/evaluation/status/{er.id}",
            headers={**auth_headers["annotator"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 403, resp.text
        assert "don't have access" in resp.json()["detail"]

    def test_status_message_from_error_message(self, client, test_db, test_users, auth_headers, test_org):
        """A failed run surfaces its error_message as the status message
        (the ``error_message or 'Evaluation status'`` branch, error side)."""
        p, tasks = _setup_project(test_db, test_users[0], test_org)
        er = _make_eval_run(test_db, p, status="failed")
        er.error_message = "boom: judge timed out"
        test_db.add(er)
        test_db.commit()

        resp = client.get(
            f"{BASE}/evaluation/status/{er.id}",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "failed"
        assert body["message"] == "boom: judge timed out"

    def test_status_default_message_when_no_error(self, client, test_db, test_users, auth_headers, test_org):
        """A run without an error_message uses the literal fallback string."""
        p, tasks = _setup_project(test_db, test_users[0], test_org)
        er = _make_eval_run(test_db, p, status="completed")
        test_db.commit()

        resp = client.get(
            f"{BASE}/evaluation/status/{er.id}",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["message"] == "Evaluation status"


# ===========================================================================
# status.py — GET /  (list) : org-scoping branches
# ===========================================================================


@pytest.mark.integration
class TestListEvaluationsBranches:
    def test_superadmin_sees_all(self, client, test_db, test_users, auth_headers, test_org):
        """A superadmin's accessible_ids is None (see-everything) so the
        project-id filter is skipped — the run is present without any org
        header."""
        p, tasks = _setup_project(test_db, test_users[0], test_org)
        er = _make_eval_run(test_db, p)
        test_db.commit()

        resp = client.get(f"{BASE}/", headers=auth_headers["admin"])
        assert resp.status_code == 200, resp.text
        ids = {row["id"] for row in resp.json()}
        assert er.id in ids

    def test_contributor_scoped_to_org_projects(self, client, test_db, test_users, auth_headers, test_org):
        """A non-superadmin sees runs for projects in their accessible set. The
        contributor is an org member, the project is linked to the org → the
        run appears under the org context."""
        p, tasks = _setup_project(test_db, test_users[0], test_org)
        er = _make_eval_run(test_db, p)
        test_db.commit()

        resp = client.get(
            f"{BASE}/",
            headers={**auth_headers["contributor"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200, resp.text
        ids = {row["id"] for row in resp.json()}
        assert er.id in ids

    def test_contributor_excluded_from_inaccessible_private(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """A run on a private project the contributor cannot access is filtered
        OUT of their list (the accessible_ids restriction in action)."""
        # Private project owned by admin, not linked to any org → contributor
        # has no path to it.
        p_priv, _ = _setup_project(
            test_db, test_users[0], test_org, is_private=True, link_org=False,
        )
        er_priv = _make_eval_run(test_db, p_priv)
        test_db.commit()

        resp = client.get(
            f"{BASE}/",
            headers={**auth_headers["contributor"], "X-Organization-Context": test_org.id},
        )
        assert resp.status_code == 200, resp.text
        ids = {row["id"] for row in resp.json()}
        assert er_priv.id not in ids


# ===========================================================================
# status.py — GET /evaluation-types  &  /evaluation-types/{id}
# ===========================================================================


@pytest.mark.integration
class TestEvaluationTypesBranches:
    def test_combined_category_and_task_type_filter(
        self, client, test_db, test_users, auth_headers, test_evaluation_types
    ):
        """Both filters applied together: category=classification AND
        task_type_id=text_classification. The result is the intersection — only
        classification types applicable to text_classification."""
        resp = client.get(
            f"{BASE}/evaluation-types"
            "?category=classification&task_type_id=text_classification",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        returned = {d["id"] for d in data}
        # accuracy/f1/precision/recall are classification + text_classification;
        # exact_match (qa) and token_f1 (qa) must be excluded.
        assert "exact_match" not in returned
        assert "token_f1" not in returned
        for d in data:
            assert d["category"] == "classification"
        assert "accuracy" in returned

    def test_inactive_type_returns_404(self, client, test_db, test_users, auth_headers):
        """GET /evaluation-types/{id} filters on is_active — an inactive type is
        a 404 even though the row exists."""
        et = EvaluationType(
            id=f"inactive-{uuid.uuid4().hex[:8]}",
            name="Inactive Metric",
            description="deactivated",
            category="classification",
            higher_is_better=True,
            value_range={"min": 0, "max": 1},
            applicable_project_types=["text_classification"],
            is_active=False,
        )
        test_db.add(et)
        test_db.commit()

        # DB-state: the row exists but is inactive.
        row = test_db.query(EvaluationType).filter(EvaluationType.id == et.id).first()
        assert row is not None
        assert row.is_active is False

        resp = client.get(
            f"{BASE}/evaluation-types/{et.id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404, resp.text
        assert et.id in resp.json()["detail"]

    def test_active_type_excludes_inactive_from_list(
        self, client, test_db, test_users, auth_headers, test_evaluation_types
    ):
        """The list endpoint filters is_active=True — an inactive row never
        appears."""
        et = EvaluationType(
            id=f"hidden-{uuid.uuid4().hex[:8]}",
            name="Hidden Metric",
            category="qa",
            higher_is_better=True,
            applicable_project_types=["qa_reasoning"],
            is_active=False,
        )
        test_db.add(et)
        test_db.commit()

        resp = client.get(
            f"{BASE}/evaluation-types",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200, resp.text
        ids = {d["id"] for d in resp.json()}
        assert et.id not in ids
