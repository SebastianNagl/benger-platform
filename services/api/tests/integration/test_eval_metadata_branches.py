"""Behavioral integration tests for the uncovered branches of
``routers/evaluations/metadata.py`` (mounted at prefix ``/api/evaluations`` —
see ``routers/evaluations/__init__.py`` + ``main.py``).

Endpoints under test::

  GET  /api/evaluations/projects/{project_id}/evaluated-models
  GET  /api/evaluations/projects/{project_id}/configured-methods
  GET  /api/evaluations/projects/{project_id}/evaluation-history
  GET  /api/evaluations/significance/{project_id}
  POST /api/evaluations/projects/{project_id}/statistics

This suite complements the existing ``test_evaluation_metadata_deep.py``
(which accepts ``status_code in (200, 400, 422)`` for most statistics /
history / significance tests and never exercises a 403). Here every test
calls the endpoint via the ``client`` fixture and asserts the exact status
code + concrete response JSON, and — wherever the seeded graph drives a
counted / aggregated value — re-reads the persisted rows from ``test_db`` to
prove the response reflects real DB state.

Access model recap (routers/projects/helpers.check_project_accessible):
  * superadmin (test_users[0], "admin") -> always allowed
  * a PRIVATE project's creator is the only non-superadmin allowed; a private
    project created by the contributor and hit by the annotator with
    ``X-Organization-Context: private`` -> deterministic 403.

MinIO byte-streaming endpoints (export/import) are out of scope — this router
has none.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone

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


# ---------------------------------------------------------------------------
# Seeding helpers
# ---------------------------------------------------------------------------


def _uid():
    return str(uuid.uuid4())


def _h(auth_headers, org, role="admin"):
    """admin headers scoped to the given org context."""
    return {**auth_headers[role], "X-Organization-Context": org.id}


# A binary <Choices> control (Ja/Nein) — detected as the BINARY answer type by
# the answer-type detector, name="answer", to_name="text".
BINARY_LABEL_CONFIG = (
    '<View>'
    '<Text name="text" value="$text"/>'
    '<Choices name="answer" toName="text">'
    '<Choice value="Ja"/><Choice value="Nein"/>'
    '</Choices>'
    '</View>'
)


def _make_project(
    db,
    creator,
    org=None,
    *,
    label_config=BINARY_LABEL_CONFIG,
    evaluation_config=None,
    generation_config=None,
    is_private=False,
    num_tasks=0,
):
    """Create a Project (optionally org-linked, optionally with N tasks)."""
    project = Project(
        id=_uid(),
        title=f"meta-branch-{uuid.uuid4().hex[:6]}",
        created_by=creator.id,
        label_config=label_config,
        evaluation_config=evaluation_config,
        generation_config=generation_config,
        is_private=is_private,
    )
    db.add(project)
    db.flush()
    if org is not None:
        db.add(ProjectOrganization(
            id=_uid(),
            project_id=project.id,
            organization_id=org.id,
            assigned_by=creator.id,
        ))
        db.flush()
    tasks = []
    for i in range(num_tasks):
        t = Task(
            id=_uid(),
            project_id=project.id,
            inner_id=i + 1,
            data={"text": f"text #{i}"},
            created_by=creator.id,
        )
        db.add(t)
        tasks.append(t)
    db.flush()
    db.commit()
    return project, tasks


def _seed_model_eval(
    db,
    project,
    creator,
    model_id,
    tasks,
    *,
    metric_name="accuracy",
    per_task_values,
    config_id=None,
    run_metrics=None,
    created_at=None,
    completed_at=None,
):
    """Seed a completed EvaluationRun + Generations + per-sample TaskEvaluations
    for ``model_id`` over ``tasks``. Returns (eval_run, judge_run, generations).

    Each TaskEvaluation row carries ``metrics={metric_name: value}`` so the
    sample-level aggregations (statistics / significance / history) have real
    numbers to read. ``config_id`` populates the discrete
    ``evaluation_config_id`` column used by the issue-#111 scoping filters.
    """
    ts = created_at or datetime.now(timezone.utc)
    rg = ResponseGeneration(
        id=_uid(),
        project_id=project.id,
        model_id=model_id,
        status="completed",
        created_by=creator.id,
        started_at=ts,
        completed_at=ts,
    )
    db.add(rg)
    db.flush()

    gens = []
    for i, t in enumerate(tasks):
        gen = Generation(
            id=_uid(),
            generation_id=rg.id,
            task_id=t.id,
            model_id=model_id,
            run_index=i,
            case_data=json.dumps(t.data),
            response_content=f"answer from {model_id} #{i}",
            label_config_version="v1",
            status="completed",
            parse_status="success",
        )
        db.add(gen)
        gens.append(gen)
    db.flush()

    er = EvaluationRun(
        id=_uid(),
        project_id=project.id,
        model_id=model_id,
        evaluation_type_ids=[metric_name],
        metrics=run_metrics if run_metrics is not None else {metric_name: per_task_values[0]},
        status="completed",
        samples_evaluated=len(tasks),
        has_sample_results=True,
        created_by=creator.id,
        created_at=ts,
        completed_at=completed_at or ts,
    )
    db.add(er)
    db.flush()

    # Migration 043 made TaskEvaluation.judge_run_id NOT NULL — use the
    # catch-all (judge_model_id=None) judge-run shape for deterministic metrics.
    judge_run = EvaluationJudgeRun(
        id=_uid(),
        evaluation_id=er.id,
        judge_model_id=None,
        run_index=0,
        status="completed",
    )
    db.add(judge_run)
    db.flush()

    for i, t in enumerate(tasks):
        te = TaskEvaluation(
            id=_uid(),
            evaluation_id=er.id,
            judge_run_id=judge_run.id,
            task_id=t.id,
            generation_id=gens[i].id,
            field_name="answer",
            evaluation_config_id=config_id,
            answer_type="choices",
            ground_truth={"value": "Ja"},
            prediction={"value": "Ja"},
            metrics={metric_name: per_task_values[i]},
            passed=per_task_values[i] > 0.5,
        )
        db.add(te)
    db.flush()
    return er, judge_run, gens


# ===========================================================================
# Shared 403 access-denied path (one per endpoint)
# ===========================================================================


@pytest.mark.integration
class TestAccessDenied:
    """Every metadata endpoint runs check_project_accessible after the 404
    guard. A private project created by the contributor and hit by the
    annotator (neither superadmin nor creator) with the private context yields
    a deterministic 403 — the branch the deep suite never reaches."""

    def _private_project(self, db, test_users, test_org):
        # creator = contributor (test_users[1]); requester = annotator.
        project, _ = _make_project(
            db, test_users[1], test_org, is_private=True, num_tasks=1
        )
        return project

    def _annotator_private_headers(self, auth_headers):
        return {
            **auth_headers["annotator"],
            "X-Organization-Context": "private",
        }

    def test_evaluated_models_403(self, client, test_db, test_users, auth_headers, test_org):
        project = self._private_project(test_db, test_users, test_org)
        resp = client.get(
            f"{BASE}/projects/{project.id}/evaluated-models",
            headers=self._annotator_private_headers(auth_headers),
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"] == "Access denied"

    def test_configured_methods_403(self, client, test_db, test_users, auth_headers, test_org):
        project = self._private_project(test_db, test_users, test_org)
        resp = client.get(
            f"{BASE}/projects/{project.id}/configured-methods",
            headers=self._annotator_private_headers(auth_headers),
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"] == "Access denied"

    def test_evaluation_history_403(self, client, test_db, test_users, auth_headers, test_org):
        project = self._private_project(test_db, test_users, test_org)
        resp = client.get(
            f"{BASE}/projects/{project.id}/evaluation-history"
            "?model_ids=gpt-4o&metrics=accuracy",
            headers=self._annotator_private_headers(auth_headers),
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"] == "Access denied"

    def test_significance_403(self, client, test_db, test_users, auth_headers, test_org):
        project = self._private_project(test_db, test_users, test_org)
        resp = client.get(
            f"{BASE}/significance/{project.id}"
            "?model_ids=gpt-4o&model_ids=claude-3-sonnet&metrics=accuracy",
            headers=self._annotator_private_headers(auth_headers),
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"] == "Access denied"

    def test_statistics_403(self, client, test_db, test_users, auth_headers, test_org):
        project = self._private_project(test_db, test_users, test_org)
        resp = client.post(
            f"{BASE}/projects/{project.id}/statistics",
            json={"metrics": ["accuracy"], "aggregation": "model"},
            headers=self._annotator_private_headers(auth_headers),
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"] == "Access denied"


# ===========================================================================
# GET /evaluated-models — include_configured flags + empty + config-only model
# ===========================================================================


@pytest.mark.integration
class TestEvaluatedModels:
    def test_empty_project_returns_empty_list(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """No generations / evaluations / annotations and no configured models
        → ``all_model_ids`` empty → early ``return []`` (line ~383)."""
        project, _ = _make_project(test_db, test_users[0], test_org, num_tasks=2)
        resp = client.get(
            f"{BASE}/projects/{project.id}/evaluated-models",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == []

    def test_include_configured_surfaces_config_only_model(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """include_configured=True pulls models from generation_config that have
        no results yet. The config-only model must appear with is_configured
        True, has_generations/has_results False, and a NULL average_score
        (the ``None if include_configured`` branch), and must sort AFTER the
        evaluated model (configured-with-results first)."""
        gen_config = {"selected_configuration": {"models": ["gpt-4o", "config-only-model"]}}
        project, tasks = _make_project(
            test_db, test_users[0], test_org,
            generation_config=gen_config, num_tasks=4,
        )
        _seed_model_eval(
            test_db, project, test_users[0], "gpt-4o", tasks,
            per_task_values=[0.8, 0.82, 0.84, 0.86],
        )
        test_db.commit()

        resp = client.get(
            f"{BASE}/projects/{project.id}/evaluated-models?include_configured=true",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        by_id = {m["model_id"]: m for m in body}
        assert "gpt-4o" in by_id
        assert "config-only-model" in by_id

        evaluated = by_id["gpt-4o"]
        assert evaluated["is_configured"] is True
        assert evaluated["has_generations"] is True
        assert evaluated["has_results"] is True
        assert evaluated["evaluation_count"] >= 1
        assert evaluated["average_score"] is not None

        config_only = by_id["config-only-model"]
        assert config_only["is_configured"] is True
        assert config_only["has_generations"] is False
        assert config_only["has_results"] is False
        # include_configured + no scores → average_score is None (not 0.0).
        assert config_only["average_score"] is None
        # Configured-with-results sorts before configured-without-results.
        assert body.index(evaluated) < body.index(config_only)

    def test_evaluated_model_average_matches_seeded_run_metrics(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """Without include_configured, average_score is the mean of the run's
        ``metrics`` numeric values. Seed a single run whose metrics dict has
        one value so the average is deterministic, then assert it round-trips."""
        project, tasks = _make_project(test_db, test_users[0], test_org, num_tasks=3)
        _seed_model_eval(
            test_db, project, test_users[0], "claude-3-sonnet", tasks,
            per_task_values=[0.5, 0.5, 0.5],
            run_metrics={"accuracy": 0.7},
        )
        test_db.commit()

        # DB-state: exactly one completed EvaluationRun for the model.
        runs = (
            test_db.query(EvaluationRun)
            .filter(
                EvaluationRun.project_id == project.id,
                EvaluationRun.model_id == "claude-3-sonnet",
            )
            .all()
        )
        assert len(runs) == 1
        assert runs[0].metrics == {"accuracy": 0.7}

        resp = client.get(
            f"{BASE}/projects/{project.id}/evaluated-models",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        row = next(m for m in resp.json() if m["model_id"] == "claude-3-sonnet")
        assert row["provider"] == "Anthropic"
        assert row["average_score"] == 0.7
        assert row["total_samples"] == 3


# ===========================================================================
# GET /configured-methods — fields shape, has_results, suffix-noise, human
# ===========================================================================


@pytest.mark.integration
class TestConfiguredMethods:
    def test_no_evaluation_config_returns_empty_fields(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """Project with evaluation_config=None → ``{project_id, fields: []}``."""
        project, _ = _make_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"{BASE}/projects/{project.id}/configured-methods",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"project_id": project.id, "fields": []}

    def test_no_selected_methods_returns_empty_fields(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """evaluation_config present but no ``selected_methods`` → empty fields."""
        project, _ = _make_project(
            test_db, test_users[0], test_org,
            evaluation_config={"available_methods": {"answer": {"type": "binary"}}},
        )
        resp = client.get(
            f"{BASE}/projects/{project.id}/configured-methods",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["fields"] == []

    def test_has_results_counts_scored_taskevaluations(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """The result map counts scored TaskEvaluation rows per metric key
        (jsonb_object_keys over TaskEvaluation.metrics). We seed 3 rows whose
        metrics carry an ``accuracy`` key plus a ``_details`` sidekey that must
        be filtered out of the dropdown. ``accuracy`` should show
        result_count=3 / has_results True; the configured-but-unscored ``f1``
        shows result_count=0 / has_results False."""
        eval_config = {
            "selected_methods": {
                "answer": {"automated": ["accuracy", "f1"], "human": []}
            },
            "available_methods": {"answer": {"type": "binary", "to_name": "text"}},
        }
        project, tasks = _make_project(
            test_db, test_users[0], test_org,
            evaluation_config=eval_config, num_tasks=3,
        )
        # Seed an eval whose per-sample metrics carry accuracy + a noise sidekey.
        er, judge_run, gens = _seed_model_eval(
            test_db, project, test_users[0], "gpt-4o", tasks,
            per_task_values=[0.9, 0.9, 0.9],
        )
        # Overwrite metrics so each row also has the _details suffix-noise key.
        for te in (
            test_db.query(TaskEvaluation)
            .filter(TaskEvaluation.evaluation_id == er.id)
            .all()
        ):
            te.metrics = {"accuracy": 0.9, "accuracy_details": {"raw": 1}}
        test_db.commit()

        # DB-state: 3 scored rows, all carrying the accuracy key.
        rows = (
            test_db.query(TaskEvaluation)
            .filter(TaskEvaluation.evaluation_id == er.id)
            .all()
        )
        assert len(rows) == 3
        assert all("accuracy" in r.metrics for r in rows)

        resp = client.get(
            f"{BASE}/projects/{project.id}/configured-methods",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["project_id"] == project.id
        field = next(f for f in body["fields"] if f["field_name"] == "answer")
        methods = {m["method_name"]: m for m in field["automated_methods"]}

        assert methods["accuracy"]["has_results"] is True
        assert methods["accuracy"]["result_count"] == 3
        assert methods["accuracy"]["last_run"] is not None
        assert methods["accuracy"]["is_configured"] is True

        assert methods["f1"]["has_results"] is False
        assert methods["f1"]["result_count"] == 0
        assert methods["f1"]["last_run"] is None

        # The _details suffix-noise key must NOT surface as its own method.
        assert "accuracy_details" not in methods

    def test_llm_judge_method_type_and_human_method(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """An ``llm_judge_*`` automated method is typed 'llm-judge'; a human
        method surfaces under human_methods with method_type 'human'. Neither
        has scored rows → has_results False / result_count 0."""
        eval_config = {
            "selected_methods": {
                "answer": {
                    "automated": [{"name": "llm_judge_classic", "parameters": {"x": 1}}],
                    "human": ["likert"],
                }
            },
            "available_methods": {"answer": {"type": "binary", "to_name": "text"}},
        }
        project, _ = _make_project(
            test_db, test_users[0], test_org, evaluation_config=eval_config,
        )
        resp = client.get(
            f"{BASE}/projects/{project.id}/configured-methods",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        field = next(
            f for f in resp.json()["fields"] if f["field_name"] == "answer"
        )
        auto = field["automated_methods"][0]
        assert auto["method_name"] == "llm_judge_classic"
        assert auto["method_type"] == "llm-judge"
        assert auto["parameters"] == {"x": 1}
        assert auto["has_results"] is False
        assert auto["result_count"] == 0

        human = field["human_methods"][0]
        assert human["method_name"] == "likert"
        assert human["method_type"] == "human"
        assert human["has_results"] is False


# ===========================================================================
# GET /evaluation-history — required metrics, series content, config scoping
# ===========================================================================


@pytest.mark.integration
class TestEvaluationHistory:
    def test_missing_metrics_param_returns_422(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """``metrics`` is a required query param → omitting it is a 422."""
        project, _ = _make_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"{BASE}/projects/{project.id}/evaluation-history?model_ids=gpt-4o",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 422, resp.text

    def test_series_buckets_per_day_and_resolves_display_name(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """One model, one config id, two days of samples → one series whose
        display_name resolves from the project's evaluation_configs lookup and
        whose data has one point per day, each carrying the per-day mean and a
        sample_count matching the seeded rows."""
        cfg_id = "cfg-bleu-3"
        eval_config = {
            "evaluation_configs": [
                {"id": cfg_id, "metric": "accuracy", "display_name": "BLEU (3-gram)"}
            ]
        }
        project, tasks = _make_project(
            test_db, test_users[0], test_org,
            evaluation_config=eval_config, num_tasks=2,
        )
        day1 = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
        day2 = datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc)
        _seed_model_eval(
            test_db, project, test_users[0], "gpt-4o", tasks,
            per_task_values=[0.80, 0.90], config_id=cfg_id,
            created_at=day1,
        )
        _seed_model_eval(
            test_db, project, test_users[0], "gpt-4o", tasks,
            per_task_values=[0.60, 0.60], config_id=cfg_id,
            created_at=day2,
        )
        test_db.commit()

        resp = client.get(
            f"{BASE}/projects/{project.id}/evaluation-history"
            "?model_ids=gpt-4o&metrics=accuracy",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        series = resp.json()["series"]
        assert len(series) == 1
        s = series[0]
        assert s["metric"] == "accuracy"
        assert s["evaluation_config_id"] == cfg_id
        assert s["display_name"] == "BLEU (3-gram)"

        points = {p["date"]: p for p in s["data"]}
        assert set(points) == {"2026-05-01", "2026-05-03"}
        # day1 mean of [0.80, 0.90] = 0.85; day2 mean of [0.60, 0.60] = 0.60.
        assert points["2026-05-01"]["value"] == 0.85
        assert points["2026-05-01"]["sample_count"] == 2
        assert points["2026-05-03"]["value"] == 0.60
        # Data points are sorted ascending by date.
        assert [p["date"] for p in s["data"]] == ["2026-05-01", "2026-05-03"]

    def test_evaluation_config_ids_filter_scopes_series(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """Two configs of the same metric produce two series; passing
        ``evaluation_config_ids`` for only one scopes the response to that
        config's series."""
        eval_config = {
            "evaluation_configs": [
                {"id": "cfg-a", "metric": "accuracy", "display_name": "Config A"},
                {"id": "cfg-b", "metric": "accuracy", "display_name": "Config B"},
            ]
        }
        project, tasks = _make_project(
            test_db, test_users[0], test_org,
            evaluation_config=eval_config, num_tasks=2,
        )
        _seed_model_eval(
            test_db, project, test_users[0], "gpt-4o", tasks,
            per_task_values=[0.7, 0.7], config_id="cfg-a",
        )
        _seed_model_eval(
            test_db, project, test_users[0], "gpt-4o", tasks,
            per_task_values=[0.4, 0.4], config_id="cfg-b",
        )
        test_db.commit()

        # Unscoped: both configs' series present.
        resp_all = client.get(
            f"{BASE}/projects/{project.id}/evaluation-history"
            "?model_ids=gpt-4o&metrics=accuracy",
            headers=_h(auth_headers, test_org),
        )
        assert resp_all.status_code == 200, resp_all.text
        all_cfg_ids = {s["evaluation_config_id"] for s in resp_all.json()["series"]}
        assert all_cfg_ids == {"cfg-a", "cfg-b"}

        # Scoped to cfg-a only.
        resp_scoped = client.get(
            f"{BASE}/projects/{project.id}/evaluation-history"
            "?model_ids=gpt-4o&metrics=accuracy&evaluation_config_ids=cfg-a",
            headers=_h(auth_headers, test_org),
        )
        assert resp_scoped.status_code == 200, resp_scoped.text
        scoped = resp_scoped.json()["series"]
        assert len(scoped) == 1
        assert scoped[0]["evaluation_config_id"] == "cfg-a"
        assert scoped[0]["display_name"] == "Config A"

    def test_end_date_filter_excludes_later_runs(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """An ``end_date`` earlier than a run's created_at excludes it. Seed two
        days; cap end_date at day1 → only day1 survives."""
        project, tasks = _make_project(test_db, test_users[0], test_org, num_tasks=2)
        day1 = datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc)
        day2 = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
        _seed_model_eval(
            test_db, project, test_users[0], "gpt-4o", tasks,
            per_task_values=[0.5, 0.5], created_at=day1,
        )
        _seed_model_eval(
            test_db, project, test_users[0], "gpt-4o", tasks,
            per_task_values=[0.9, 0.9], created_at=day2,
        )
        test_db.commit()

        resp = client.get(
            f"{BASE}/projects/{project.id}/evaluation-history"
            "?model_ids=gpt-4o&metrics=accuracy&end_date=2026-05-15T00:00:00",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        series = resp.json()["series"]
        assert len(series) == 1
        dates = {p["date"] for p in series[0]["data"]}
        assert dates == {"2026-05-01"}


# ===========================================================================
# GET /significance/{project_id} — default branch, real comparison, config scope
# ===========================================================================


@pytest.mark.integration
class TestSignificance:
    def test_insufficient_samples_default_comparison(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """When a model has <2 scored samples the comparison short-circuits to
        the default {p_value: 1.0, significant: False, effect_size: 0.0,
        stars: ""} entry — no t-test is run."""
        project, tasks = _make_project(test_db, test_users[0], test_org, num_tasks=1)
        # gpt-4o: 1 sample; claude: 1 sample → both <2.
        _seed_model_eval(
            test_db, project, test_users[0], "gpt-4o", tasks,
            per_task_values=[0.8], run_metrics={"accuracy": 0.8},
        )
        _seed_model_eval(
            test_db, project, test_users[0], "claude-3-sonnet", tasks,
            per_task_values=[0.6], run_metrics={"accuracy": 0.6},
        )
        test_db.commit()

        resp = client.get(
            f"{BASE}/significance/{project.id}"
            "?model_ids=gpt-4o&model_ids=claude-3-sonnet&metrics=accuracy"
            # Scope to a non-matching config so the run-level direct fallback is
            # skipped — guarantees each model keeps <2 samples and hits the
            # short-circuit default rather than the t-test branch.
            "&evaluation_config_ids=no-such-config",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        comparisons = resp.json()["comparisons"]
        assert len(comparisons) == 1
        c = comparisons[0]
        assert c["model_a"] == "gpt-4o"
        assert c["model_b"] == "claude-3-sonnet"
        assert c["metric"] == "accuracy"
        assert c["p_value"] == 1.0
        assert c["significant"] is False
        assert c["effect_size"] == 0.0
        assert c["stars"] == ""

    def test_two_models_real_ttest_comparison(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """With ≥2 samples per model, the real Welch t-test runs: a clearly
        separated pair (all-high vs all-low) is flagged significant with a
        p_value < 0.05 and a non-empty star string. Scoping to the seeded config
        keeps the comparison config-local (no run-level fallback)."""
        cfg_id = "cfg-acc"
        eval_config = {"evaluation_configs": [{"id": cfg_id, "metric": "accuracy"}]}
        project, tasks = _make_project(
            test_db, test_users[0], test_org,
            evaluation_config=eval_config, num_tasks=5,
        )
        _seed_model_eval(
            test_db, project, test_users[0], "gpt-4o", tasks,
            per_task_values=[0.95, 0.96, 0.97, 0.94, 0.95], config_id=cfg_id,
        )
        _seed_model_eval(
            test_db, project, test_users[0], "claude-3-sonnet", tasks,
            per_task_values=[0.10, 0.12, 0.09, 0.11, 0.08], config_id=cfg_id,
        )
        test_db.commit()

        resp = client.get(
            f"{BASE}/significance/{project.id}"
            "?model_ids=gpt-4o&model_ids=claude-3-sonnet&metrics=accuracy"
            f"&evaluation_config_ids={cfg_id}",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        comparisons = resp.json()["comparisons"]
        assert len(comparisons) == 1
        c = comparisons[0]
        assert c["p_value"] < 0.05
        assert c["significant"] is True
        assert c["stars"] != ""
        # Large separation → non-trivial effect size.
        assert abs(c["effect_size"]) > 0.0


# ===========================================================================
# POST /statistics — 404 no-evals, compare_models warning, field display, sample
# ===========================================================================


@pytest.mark.integration
class TestStatistics:
    def test_no_completed_evaluations_returns_404(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """A project that exists + is accessible but has zero completed
        EvaluationRuns → 404 'No completed evaluations found for this project'."""
        project, _ = _make_project(test_db, test_users[0], test_org, num_tasks=2)
        resp = client.post(
            f"{BASE}/projects/{project.id}/statistics",
            json={"metrics": ["accuracy"], "aggregation": "model"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404, resp.text
        assert "No completed evaluations" in resp.json()["detail"]

    def test_model_aggregation_stats_round_trip(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """Model aggregation surfaces per-model MetricStatistics whose ``n``
        equals the number of seeded samples and whose ``mean`` matches the
        seeded values. Two models → no single-model warning."""
        project, tasks = _make_project(test_db, test_users[0], test_org, num_tasks=4)
        _seed_model_eval(
            test_db, project, test_users[0], "gpt-4o", tasks,
            per_task_values=[0.6, 0.6, 0.6, 0.6],
        )
        _seed_model_eval(
            test_db, project, test_users[0], "claude-3-sonnet", tasks,
            per_task_values=[0.2, 0.2, 0.2, 0.2],
        )
        test_db.commit()

        resp = client.post(
            f"{BASE}/projects/{project.id}/statistics",
            json={"metrics": ["accuracy"], "aggregation": "model", "methods": ["ci"]},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["aggregation"] == "model"
        by_model = body["by_model"]
        assert set(by_model) == {"gpt-4o", "claude-3-sonnet"}
        gpt = by_model["gpt-4o"]["metrics"]["accuracy"]
        assert gpt["n"] == 4
        assert gpt["mean"] == 0.6
        assert by_model["gpt-4o"]["sample_count"] == 4
        # Two models present → the single-model warning is absent.
        warnings = body.get("warnings") or []
        assert "Only one model has data; pairwise comparisons not possible" not in warnings

    def test_compare_models_missing_emits_warning(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """compare_models naming only absent models → all sample rows filter
        out → the 'No data found for specified models' warning fires."""
        project, tasks = _make_project(test_db, test_users[0], test_org, num_tasks=3)
        _seed_model_eval(
            test_db, project, test_users[0], "gpt-4o", tasks,
            per_task_values=[0.5, 0.5, 0.5],
        )
        test_db.commit()

        resp = client.post(
            f"{BASE}/projects/{project.id}/statistics",
            json={
                "metrics": ["accuracy"],
                "aggregation": "model",
                "compare_models": ["nonexistent-model"],
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        warnings = resp.json().get("warnings") or []
        assert any(
            "No data found for specified models" in w for w in warnings
        ), warnings

    def test_field_aggregation_resolves_display_name(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """field aggregation builds by_field keyed on the raw field_name and
        resolves display_name from the project's evaluation_configs lookup via
        the discrete evaluation_config_id column. Carries the parsed cfg id and
        sample_count from the seeded rows."""
        cfg_id = "cfg-field-1"
        eval_config = {
            "evaluation_configs": [
                {"id": cfg_id, "metric": "accuracy", "display_name": "Antwort-Feld"}
            ]
        }
        project, tasks = _make_project(
            test_db, test_users[0], test_org,
            evaluation_config=eval_config, num_tasks=3,
        )
        _seed_model_eval(
            test_db, project, test_users[0], "gpt-4o", tasks,
            per_task_values=[0.7, 0.8, 0.9], config_id=cfg_id,
        )
        test_db.commit()

        resp = client.post(
            f"{BASE}/projects/{project.id}/statistics",
            json={"metrics": ["accuracy"], "aggregation": "field", "methods": ["ci"]},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        by_field = resp.json()["by_field"]
        assert "answer" in by_field
        field = by_field["answer"]
        assert field["evaluation_config_id"] == cfg_id
        assert field["display_name"] == "Antwort-Feld"
        assert field["sample_count"] == 3
        assert field["metrics"]["accuracy"]["n"] == 3

    def test_sample_aggregation_returns_raw_scores(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """sample aggregation returns one RawScore per (sample, metric) carrying
        the model_id, evaluation_config_id and value. Count equals the number
        of seeded TaskEvaluation rows."""
        cfg_id = "cfg-sample"
        eval_config = {"evaluation_configs": [{"id": cfg_id, "metric": "accuracy"}]}
        project, tasks = _make_project(
            test_db, test_users[0], test_org,
            evaluation_config=eval_config, num_tasks=3,
        )
        _seed_model_eval(
            test_db, project, test_users[0], "gpt-4o", tasks,
            per_task_values=[0.3, 0.6, 0.9], config_id=cfg_id,
        )
        test_db.commit()

        resp = client.post(
            f"{BASE}/projects/{project.id}/statistics",
            json={"metrics": ["accuracy"], "aggregation": "sample", "methods": ["ci"]},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        raw = resp.json()["raw_scores"]
        assert raw is not None
        accuracy_scores = [r for r in raw if r["metric"] == "accuracy"]
        assert len(accuracy_scores) == 3
        for r in accuracy_scores:
            assert r["model_id"] == "gpt-4o"
            assert r["evaluation_config_id"] == cfg_id
        assert sorted(round(r["value"], 1) for r in accuracy_scores) == [0.3, 0.6, 0.9]

    def test_multi_run_aggregate_present_for_single_run(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """The multi-run block emits one ``runs_by_model_metric`` entry keyed
        ``model|config|metric`` even for a single judge-run, with n_runs=1 and
        a mean_of_means matching the seeded per-sample mean. config_id is the
        seeded value (not the 'unknown' sentinel) since rows carry it."""
        cfg_id = "cfg-multirun"
        eval_config = {"evaluation_configs": [{"id": cfg_id, "metric": "accuracy"}]}
        project, tasks = _make_project(
            test_db, test_users[0], test_org,
            evaluation_config=eval_config, num_tasks=4,
        )
        _seed_model_eval(
            test_db, project, test_users[0], "gpt-4o", tasks,
            per_task_values=[0.4, 0.5, 0.6, 0.5], config_id=cfg_id,
        )
        test_db.commit()

        resp = client.post(
            f"{BASE}/projects/{project.id}/statistics",
            json={"metrics": ["accuracy"], "aggregation": "model", "methods": ["ci"]},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        runs = body.get("runs_by_model_metric")
        assert runs is not None
        key = f"gpt-4o|{cfg_id}|accuracy"
        assert key in runs, runs
        agg = runs[key]
        assert agg["n_runs"] == 1
        # mean of [0.4,0.5,0.6,0.5] = 0.5; single run → CI bounds collapse.
        assert agg["mean_of_means"] == 0.5
        assert agg["ci_lower"] is None
        assert agg["ci_upper"] is None

    def test_evaluation_config_ids_filter_scopes_statistics(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """Passing evaluation_config_ids restricts the sample query to that
        config; a model evaluated only under a different config drops out of
        by_model entirely."""
        eval_config = {
            "evaluation_configs": [
                {"id": "cfg-x", "metric": "accuracy"},
                {"id": "cfg-y", "metric": "accuracy"},
            ]
        }
        project, tasks = _make_project(
            test_db, test_users[0], test_org,
            evaluation_config=eval_config, num_tasks=3,
        )
        _seed_model_eval(
            test_db, project, test_users[0], "gpt-4o", tasks,
            per_task_values=[0.8, 0.8, 0.8], config_id="cfg-x",
        )
        _seed_model_eval(
            test_db, project, test_users[0], "claude-3-sonnet", tasks,
            per_task_values=[0.2, 0.2, 0.2], config_id="cfg-y",
        )
        test_db.commit()

        resp = client.post(
            f"{BASE}/projects/{project.id}/statistics",
            json={
                "metrics": ["accuracy"],
                "aggregation": "model",
                "methods": ["ci"],
                "evaluation_config_ids": ["cfg-x"],
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        by_model = resp.json()["by_model"]
        # Only the cfg-x model survives the scope filter.
        assert "gpt-4o" in by_model
        assert "claude-3-sonnet" not in by_model
        assert by_model["gpt-4o"]["metrics"]["accuracy"]["mean"] == 0.8
