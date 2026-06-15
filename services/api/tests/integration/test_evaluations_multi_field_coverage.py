"""Complement behavioral tests for the multi-field evaluation-run router.

Target: ``services/api/routers/evaluations/multi_field.py`` (mounted at prefix
``/api/evaluations`` via ``routers/evaluations/__init__.py``). All handlers use
the SYNC DB lane (``Depends(get_db)``).

This file is the COMPLEMENT of ``tests/integration/test_eval_multifield_branches.py``
and ``tests/integration/test_evaluation_cancel_idempotency.py``. Those cover the
404/403/400 guards on /run, the all-human ongoing short-circuit, the basic LLM
dispatch, the cancel auth branches, available-fields extraction, and the result
parsing. This file fills the still-uncovered arms:

  POST /run ........................ the top-level ``seed`` propagation into each
                                     config's metric_parameters + the
                                     eval_metadata._top_level_seed snapshot; the
                                     celery dispatch FAILURE path (send_task
                                     raises → run flipped to 'failed' → 500).
  POST /projects/{id}/runs/cancel-all  the happy path: multiple in-flight runs
                                     flipped to 'cancelled', task_evaluations
                                     preserved, in-flight judge_runs failed.
  GET  /projects/{id}/available-fields  the no-generations / no-parsed_annotation
                                     path (model_response_fields empty) and the
                                     evaluation_config detected_answer_types
                                     reference-field extraction.
  GET  /run/results/project/{id} ... the legacy ``:``-separator metric-key
                                     backward-compat parsing branch.
  GET  /run/results/{id} ........... the scope block resolution
                                     (_resolve_scope_block) when the run was
                                     dispatched with annotator_user_ids /
                                     model_ids / task_ids → ``scope`` is non-null
                                     and annotator user ids resolve to displays.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from models import (
    EvaluationJudgeRun,
    EvaluationRun,
    Generation,
    ResponseGeneration,
    TaskEvaluation,
)
from project_models import Annotation, Project, ProjectOrganization, Task

BASE = "/api/evaluations"
CELERY_TARGET = "routers.evaluations.helpers.celery_app.send_task"


def _uid() -> str:
    return str(uuid.uuid4())


def _h(auth_headers, org, role="admin"):
    return {**auth_headers[role], "X-Organization-Context": org.id}


def _setup_project(db, admin, org, *, num_tasks=2, link_org=True,
                   label_config=None, evaluation_config=None):
    pid = _uid()
    p = Project(
        id=pid,
        title=f"MFC {pid[:6]}",
        created_by=admin.id,
        label_config=label_config if label_config is not None else (
            '<View><Text name="text" value="$text"/>'
            '<Choices name="answer" toName="text">'
            '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>'
        ),
        evaluation_config=evaluation_config,
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
            data={"text": f"task {i}", "musterloesung": f"ml {i}"},
            inner_id=i + 1, created_by=admin.id,
        )
        db.add(t)
        tasks.append(t)
    db.flush()
    return p, tasks


def _make_eval_run(db, project, admin_id, *, status="running", metrics=None,
                   eval_metadata=None, model_id="gpt-4", samples=10):
    er = EvaluationRun(
        id=_uid(), project_id=project.id, model_id=model_id,
        evaluation_type_ids=["accuracy"], status=status,
        metrics=metrics or {}, samples_evaluated=samples,
        eval_metadata=eval_metadata if eval_metadata is not None
        else {"evaluation_type": "evaluation"},
        created_by=admin_id, created_at=datetime.now(timezone.utc),
    )
    db.add(er)
    db.flush()
    jr = EvaluationJudgeRun(
        id=_uid(), evaluation_id=er.id, judge_model_id=None,
        run_index=0, status="running",
    )
    db.add(jr)
    db.flush()
    er._test_judge_run = jr
    return er


def _make_generation(db, task, *, model_id="gpt-4", parsed_annotation=None):
    rg = ResponseGeneration(
        id=_uid(), project_id=task.project_id, task_id=task.id,
        model_id=model_id, status="completed", created_by=task.created_by,
    )
    db.add(rg)
    db.flush()
    gen = Generation(
        id=_uid(), generation_id=rg.id, task_id=task.id, model_id=model_id,
        run_index=0, case_data="{}", response_content="resp",
        status="completed", parse_status="success",
        parsed_annotation=parsed_annotation,
    )
    db.add(gen)
    db.flush()
    return gen, rg


def _make_task_evaluation(db, eval_run, task, *, judge_run=None, metrics=None):
    gen, _ = _make_generation(db, task)
    te = TaskEvaluation(
        id=_uid(), evaluation_id=eval_run.id,
        judge_run_id=(judge_run or eval_run._test_judge_run).id,
        task_id=task.id, generation_id=gen.id, annotation_id=None,
        field_name="answer", answer_type="choices",
        metrics=metrics if metrics is not None else {"score": 0.9},
        passed=True, ground_truth={"value": "Ja"}, prediction={"value": "Ja"},
    )
    db.add(te)
    db.flush()
    return te


def _config(metric="bleu", cfg_id="c1", enabled=True):
    return {
        "id": cfg_id,
        "metric": metric,
        "prediction_fields": ["__response__"],
        "reference_fields": ["musterloesung"],
        "enabled": enabled,
    }


# ===========================================================================
# POST /run — seed propagation + dispatch failure
# ===========================================================================


@pytest.mark.integration
class TestRunSeedAndFailure:
    def test_top_level_seed_propagates_into_configs(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """A top-level ``seed`` is injected into each LLM config's
        metric_parameters (when not already pinned) and snapshotted under
        eval_metadata._top_level_seed."""
        p, _ = _setup_project(test_db, test_users[0], test_org)
        test_db.commit()

        stub_task = type("T", (), {"id": "celery-seed-stub"})()
        with patch(CELERY_TARGET, return_value=stub_task):
            resp = client.post(
                f"{BASE}/run",
                json={
                    "project_id": p.id,
                    "evaluation_configs": [_config(metric="bleu")],
                    "seed": 4242,
                    "force_rerun": True,
                },
                headers=_h(auth_headers, test_org),
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "started"

        run = test_db.query(EvaluationRun).filter_by(id=body["evaluation_id"]).one()
        assert run.eval_metadata["_top_level_seed"] == 4242
        cfg = run.eval_metadata["evaluation_configs"][0]
        assert cfg["metric_parameters"]["seed"] == 4242

    def test_per_config_seed_wins_over_top_level(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """A config that already pins its own metric_parameters.seed keeps it;
        the run-level seed does not override it (per-config wins)."""
        p, _ = _setup_project(test_db, test_users[0], test_org)
        test_db.commit()

        cfg = _config(metric="bleu")
        cfg["metric_parameters"] = {"seed": 7}
        stub_task = type("T", (), {"id": "celery-seed-stub2"})()
        with patch(CELERY_TARGET, return_value=stub_task):
            resp = client.post(
                f"{BASE}/run",
                json={
                    "project_id": p.id,
                    "evaluation_configs": [cfg],
                    "seed": 999,
                    "force_rerun": True,
                },
                headers=_h(auth_headers, test_org),
            )
        assert resp.status_code == 200, resp.text
        run = test_db.query(EvaluationRun).filter_by(
            id=resp.json()["evaluation_id"]
        ).one()
        stored_cfg = run.eval_metadata["evaluation_configs"][0]
        assert stored_cfg["metric_parameters"]["seed"] == 7

    def test_dispatch_failure_flips_run_to_failed_and_500s(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """When celery send_task raises, the inner handler sets the run to
        'failed' with an error_message and re-raises → the endpoint returns 500.
        (The outer rollback means no 'pending' run survives.)"""
        p, _ = _setup_project(test_db, test_users[0], test_org)
        test_db.commit()

        with patch(CELERY_TARGET, side_effect=RuntimeError("broker down")):
            resp = client.post(
                f"{BASE}/run",
                json={
                    "project_id": p.id,
                    "evaluation_configs": [_config(metric="bleu")],
                    "force_rerun": True,
                },
                headers=_h(auth_headers, test_org),
            )
        assert resp.status_code == 500, resp.text
        assert "Failed to start evaluation" in resp.json()["detail"]
        # No run for this project ended up 'pending' (rolled back).
        test_db.expire_all()
        pending = (
            test_db.query(EvaluationRun)
            .filter(EvaluationRun.project_id == p.id,
                    EvaluationRun.status == "pending")
            .count()
        )
        assert pending == 0


# ===========================================================================
# POST /projects/{id}/runs/cancel-all — happy path
# ===========================================================================


@pytest.mark.integration
class TestCancelAllHappyPath:
    def test_cancel_all_missing_project_404(
        self, client, test_db, test_users, auth_headers
    ):
        resp = client.post(
            f"{BASE}/projects/missing-{uuid.uuid4().hex}/runs/cancel-all",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404, resp.text
        assert "not found" in resp.json()["detail"]

    def test_cancel_all_flips_runs_and_preserves_task_evals(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """Two in-flight runs are both cancelled; their TaskEvaluation rows are
        preserved and the in-flight judge_runs are failed."""
        p, tasks = _setup_project(test_db, test_users[0], test_org, num_tasks=1)
        er1 = _make_eval_run(test_db, p, test_users[0].id, status="running")
        er2 = _make_eval_run(test_db, p, test_users[0].id, status="pending")
        _make_task_evaluation(test_db, er1, tasks[0])
        test_db.commit()

        resp = client.post(
            f"{BASE}/projects/{p.id}/runs/cancel-all",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert set(body["cancelled_run_ids"]) == {er1.id, er2.id}
        assert body["preserved_task_evaluation_count"] >= 1

        test_db.expire_all()
        for er in (er1, er2):
            assert test_db.query(EvaluationRun).filter_by(id=er.id).one().status == "cancelled"
        # The running judge_run under er1 was flipped to failed.
        jr1 = test_db.query(EvaluationJudgeRun).filter_by(id=er1._test_judge_run.id).one()
        assert jr1.status == "failed"


# ===========================================================================
# GET /projects/{id}/available-fields — no-generation + config refs
# ===========================================================================


@pytest.mark.integration
class TestAvailableFieldsComplement:
    def test_no_generations_yields_empty_model_fields(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """A project with tasks but NO successful generations returns empty
        model_response_fields while still surfacing human + reference fields."""
        p, _ = _setup_project(test_db, test_users[0], test_org, num_tasks=1)
        test_db.commit()

        resp = client.get(
            f"{BASE}/projects/{p.id}/available-fields",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["model_response_fields"] == []
        # Human field from label_config; reference fields from task.data.
        assert "answer" in body["human_annotation_fields"]
        assert "text" in body["reference_fields"]
        assert "musterloesung" in body["reference_fields"]

    def test_evaluation_config_detected_answer_types_reference_fields(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """detected_answer_types[*].to_name in evaluation_config contributes
        reference fields."""
        p, _ = _setup_project(
            test_db, test_users[0], test_org, num_tasks=1,
            evaluation_config={
                "detected_answer_types": [
                    {"to_name": "gutachten_ref"},
                    {"to_name": ""},  # empty → skipped
                ]
            },
        )
        test_db.commit()

        resp = client.get(
            f"{BASE}/projects/{p.id}/available-fields",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "gutachten_ref" in body["reference_fields"]


# ===========================================================================
# GET /run/results/project/{id} — legacy ":"-separator key parsing
# ===========================================================================


@pytest.mark.integration
class TestProjectResultsLegacyKeys:
    def test_project_with_no_runs_returns_empty(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """A project with zero EvaluationRun rows returns an empty list and
        total_count 0 (the no-evaluations early path)."""
        p, _ = _setup_project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.get(
            f"{BASE}/run/results/project/{p.id}",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_count"] == 0
        assert body["evaluations"] == []

    def test_legacy_colon_separated_metric_keys_parse(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """A run whose metrics use the legacy ``cfg:pred:ref:metric`` colon
        format (single token, no pipe) parses via the backward-compat branch."""
        p, _ = _setup_project(test_db, test_users[0], test_org)
        er = _make_eval_run(
            test_db, p, test_users[0].id, status="completed",
            metrics={"cfgL:predA:refB:bleu": 0.33},
            eval_metadata={
                "evaluation_type": "evaluation",
                "evaluation_configs": [{"id": "cfgL", "metric": "bleu"}],
            },
        )
        test_db.commit()

        resp = client.get(
            f"{BASE}/run/results/project/{p.id}",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_count"] == 1
        cfg = body["evaluations"][0]["results_by_config"]["cfgL"]
        combo = cfg["field_results"][0]
        assert combo["prediction_field"] == "predA"
        assert combo["reference_field"] == "refB"
        assert combo["scores"]["bleu"] == pytest.approx(0.33)


# ===========================================================================
# GET /run/results/{id} — scope block resolution
# ===========================================================================


@pytest.mark.integration
class TestRunResultsScope:
    def test_scope_block_resolves_annotator_displays(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """A run dispatched with annotator_user_ids / model_ids / task_ids
        surfaces a non-null ``scope`` block; annotator ids resolve to display
        names via the pseudonym rule."""
        p, tasks = _setup_project(test_db, test_users[0], test_org, num_tasks=1)
        # users[1] is the contributor; resolve to their name.
        annotator = test_users[1]
        er = _make_eval_run(
            test_db, p, test_users[0].id, status="completed",
            metrics={"cfgS|__response__|musterloesung|bleu": 0.5},
            eval_metadata={
                "evaluation_type": "evaluation",
                "evaluation_configs": [{"id": "cfgS", "metric": "bleu"}],
                "task_ids": [tasks[0].id],
                "model_ids": ["gpt-4"],
                "annotator_user_ids": [annotator.id],
            },
        )
        test_db.commit()

        resp = client.get(
            f"{BASE}/run/results/{er.id}",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        scope = body["scope"]
        assert scope is not None
        assert scope["task_ids"] == [tasks[0].id]
        assert scope["model_ids"] == ["gpt-4"]
        assert len(scope["annotators"]) == 1
        ann_entry = scope["annotators"][0]
        assert ann_entry["user_id"] == annotator.id
        # Display resolves to the user's name (no pseudonym set).
        assert ann_entry["display"] == annotator.name

    def test_judges_by_config_keeps_worker_count_when_present(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """When a judges_by_config entry already carries a non-zero
        samples_evaluated (the worker wrote it), the endpoint keeps it as-is
        rather than overwriting with the SQL count (the else arm of the
        prefer-worker-count branch)."""
        p, tasks = _setup_project(test_db, test_users[0], test_org, num_tasks=1)
        er = _make_eval_run(
            test_db, p, test_users[0].id, status="completed",
            metrics={"cfgW|__response__|musterloesung|llm_judge_classic": 0.7},
            eval_metadata={
                "evaluation_type": "evaluation",
                "evaluation_configs": [{"id": "cfgW", "metric": "llm_judge_classic"}],
            },
        )
        jr = er._test_judge_run
        # One actual TaskEvaluation under the judge run (SQL count would be 1).
        _make_task_evaluation(test_db, er, tasks[0], metrics={"llm_judge_classic": 0.7})
        # But the worker already recorded samples_evaluated=42 → kept as-is.
        er.eval_metadata = {
            **er.eval_metadata,
            "judges_by_config": {
                "cfgW": [{"judge_run_id": jr.id, "samples_evaluated": 42}],
            },
        }
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(er, "eval_metadata")
        test_db.commit()

        resp = client.get(
            f"{BASE}/run/results/{er.id}",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        entry = resp.json()["eval_metadata"]["judges_by_config"]["cfgW"][0]
        assert entry["samples_evaluated"] == 42

    def test_scope_block_unknown_annotator_id_falls_back_to_prefix(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """An annotator_user_id with no matching User row falls back to the
        first 8 chars of the id as the display."""
        p, _ = _setup_project(test_db, test_users[0], test_org)
        ghost_id = "ghostuser-" + uuid.uuid4().hex
        er = _make_eval_run(
            test_db, p, test_users[0].id, status="completed",
            metrics={},
            eval_metadata={
                "evaluation_type": "evaluation",
                "evaluation_configs": [],
                "annotator_user_ids": [ghost_id],
            },
        )
        test_db.commit()

        resp = client.get(
            f"{BASE}/run/results/{er.id}",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        scope = resp.json()["scope"]
        assert scope is not None
        assert scope["annotators"][0]["user_id"] == ghost_id
        assert scope["annotators"][0]["display"] == ghost_id[:8]
