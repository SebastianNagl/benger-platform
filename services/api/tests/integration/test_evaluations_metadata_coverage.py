"""Complement behavioral tests for the evaluation metadata router.

Target: ``services/api/routers/evaluations/metadata.py`` (mounted at prefix
``/api/evaluations`` via ``routers/evaluations/__init__.py``). All handlers use
the SYNC DB lane (``Depends(get_db)``).

This file is the COMPLEMENT of the existing
``tests/integration/test_evaluation_metadata_coverage.py`` and
``tests/integration/test_eval_metadata_branches.py``. Those cover the happy
paths (model/sample/field/overall aggregation, ttest/cohens_d/cliffs_delta/
correlation present, the 403/404/422 guards, history series, significance
pairwise). This file fills the still-uncovered arms:

  GET  /projects/{id}/evaluated-models ... the 404 missing-project guard; the
                                           include_configured config-only model
                                           with NO results (average_score None,
                                           has_results False).
  GET  /projects/{id}/configured-methods . the 404 missing-project guard.
  GET  /significance/{id} ................ the evaluation_config_ids scope filter
                                           branch (direct-evaluations fallback is
                                           skipped when set).
  POST /projects/{id}/statistics ......... the evaluation_config_ids scope filter
                                           (per-config sample subset, fallback
                                           skipped); the FIELD aggregation with
                                           an encoded "cfg|pred|ref" field_name
                                           parsed into structured fields +
                                           display_name; the multi-run aggregate
                                           block (>=2 judge runs → variance +
                                           per_run_means; >=2 distinct
                                           judge_model_ids → inter-judge
                                           agreement); the correlation
                                           insufficient-data warning; the
                                           bootstrap permutation method; the
                                           annotation-based result merge.
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


def _uid():
    return str(uuid.uuid4())


def _h(auth_headers, org):
    return {**auth_headers["admin"], "X-Organization-Context": org.id}


def _project(db, admin, org, *, evaluation_config=None, generation_config=None):
    p = Project(
        id=_uid(),
        title=f"MetaC {uuid.uuid4().hex[:6]}",
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/>'
        '<Choices name="answer" toName="text">'
        '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>',
        evaluation_config=evaluation_config,
        generation_config=generation_config,
    )
    db.add(p)
    db.flush()
    db.add(ProjectOrganization(
        id=_uid(), project_id=p.id,
        organization_id=org.id, assigned_by=admin.id,
    ))
    db.flush()
    return p


def _task(db, project, admin_id, inner_id=1):
    t = Task(
        id=_uid(), project_id=project.id,
        data={"text": f"t{inner_id}"}, inner_id=inner_id, created_by=admin_id,
    )
    db.add(t)
    db.flush()
    return t


def _eval_run(db, project, admin_id, *, model_id="gpt-4o", metrics=None,
              eval_types=None):
    er = EvaluationRun(
        id=_uid(), project_id=project.id, model_id=model_id,
        evaluation_type_ids=eval_types or ["accuracy"],
        metrics=metrics or {}, status="completed", samples_evaluated=0,
        has_sample_results=True, created_by=admin_id,
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(er)
    db.flush()
    return er


def _judge_run(db, er, *, judge_model_id=None, run_index=0):
    jr = EvaluationJudgeRun(
        id=_uid(), evaluation_id=er.id, judge_model_id=judge_model_id,
        run_index=run_index, status="completed",
    )
    db.add(jr)
    db.flush()
    return jr


def _generation(db, project, task, admin_id, *, model_id="gpt-4o"):
    rg = ResponseGeneration(
        id=_uid(), project_id=project.id, model_id=model_id,
        status="completed", created_by=admin_id,
    )
    db.add(rg)
    db.flush()
    gen = Generation(
        id=_uid(), generation_id=rg.id, task_id=task.id, model_id=model_id,
        run_index=0, case_data=json.dumps(task.data), response_content="r",
        status="completed", parse_status="success",
    )
    db.add(gen)
    db.flush()
    return gen


def _task_eval(db, er, jr, task, *, generation=None, annotation=None,
               field_name="answer", metrics=None, cfg_id=None):
    te = TaskEvaluation(
        id=_uid(), evaluation_id=er.id, judge_run_id=jr.id, task_id=task.id,
        generation_id=generation.id if generation else None,
        annotation_id=annotation.id if annotation else None,
        field_name=field_name, evaluation_config_id=cfg_id,
        answer_type="choices", ground_truth={"value": "Ja"},
        prediction={"value": "Ja"},
        metrics=metrics if metrics is not None else {"accuracy": 0.9},
        passed=True,
    )
    db.add(te)
    db.flush()
    return te


# ===================================================================
# GET /projects/{id}/evaluated-models — 404 + config-only no-result model
# ===================================================================


@pytest.mark.integration
class TestEvaluatedModelsComplement:
    def test_missing_project_404(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            f"{BASE}/projects/missing-{uuid.uuid4().hex}/evaluated-models",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404, resp.text
        assert "not found" in resp.json()["detail"]

    def test_include_configured_surfaces_unevaluated_model_with_null_score(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """include_configured=true surfaces a model listed in
        generation_config.selected_configuration.models that has NO generations
        and NO evaluations: average_score None, has_results False,
        is_configured True."""
        p = _project(
            test_db, test_users[0], test_org,
            generation_config={
                "selected_configuration": {"models": ["config-only-model"]}
            },
        )
        test_db.commit()

        resp = client.get(
            f"{BASE}/projects/{p.id}/evaluated-models?include_configured=true",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        models = {m["model_id"]: m for m in resp.json()}
        assert "config-only-model" in models
        co = models["config-only-model"]
        assert co["is_configured"] is True
        assert co["has_generations"] is False
        assert co["has_results"] is False
        assert co["average_score"] is None


# ===================================================================
# GET /projects/{id}/configured-methods — 404
# ===================================================================


@pytest.mark.integration
class TestConfiguredMethodsComplement:
    def test_missing_project_404(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            f"{BASE}/projects/missing-{uuid.uuid4().hex}/configured-methods",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404, resp.text
        assert "not found" in resp.json()["detail"]


# ===================================================================
# GET /significance/{id} — evaluation_config_ids scope branch
# ===================================================================


@pytest.mark.integration
class TestSignificanceConfigScope:
    def test_config_scoped_significance_skips_direct_fallback(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """With evaluation_config_ids set, only TaskEvaluation rows tagged with
        that config are scored, and the run-level direct-evaluations fallback is
        skipped (run metrics can't be re-scoped per config). The matching config
        has >=2 samples per model so a real comparison is produced."""
        p = _project(test_db, test_users[0], test_org)
        # Direct run-level metrics that WOULD be picked up by the fallback —
        # must be ignored when the config filter is set.
        er = _eval_run(
            test_db, p, test_users[0].id, model_id="gpt-4o",
            metrics={"accuracy": 0.99},
        )
        jr = _judge_run(test_db, er)
        # Two tasks per model, tagged with cfg-A; a second model too.
        _inner = 0
        for model_id, vals in (("gpt-4o", [0.8, 0.82]), ("claude-3", [0.6, 0.62])):
            for v in vals:
                _inner += 1
                t = _task(test_db, p, test_users[0].id, inner_id=_inner)
                gen = _generation(test_db, p, t, test_users[0].id, model_id=model_id)
                _task_eval(test_db, er, jr, t, generation=gen,
                           metrics={"accuracy": v}, cfg_id="cfg-A")
        test_db.commit()

        resp = client.get(
            f"{BASE}/significance/{p.id}"
            "?model_ids=gpt-4o&model_ids=claude-3&metrics=accuracy"
            "&evaluation_config_ids=cfg-A",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["comparisons"]) == 1
        comp = body["comparisons"][0]
        assert comp["metric"] == "accuracy"
        # A real comparison (not the insufficient-data 1.0/False stub) — both
        # models had 2 samples in cfg-A.
        assert {comp["model_a"], comp["model_b"]} == {"gpt-4o", "claude-3"}


# ===================================================================
# POST /projects/{id}/statistics — uncovered arms
# ===================================================================


@pytest.mark.integration
class TestStatisticsComplement:
    def test_config_scoped_statistics_subsets_samples(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """evaluation_config_ids restricts sample-level rows to the matching
        config. Rows tagged cfg-B are excluded when only cfg-A is requested."""
        p = _project(test_db, test_users[0], test_org)
        er = _eval_run(test_db, p, test_users[0].id)
        jr = _judge_run(test_db, er)
        # cfg-A rows (accuracy ~0.9), cfg-B rows (accuracy ~0.1).
        for i in range(4):
            t = _task(test_db, p, test_users[0].id, inner_id=i + 1)
            gen = _generation(test_db, p, t, test_users[0].id)
            _task_eval(test_db, er, jr, t, generation=gen,
                       metrics={"accuracy": 0.9}, cfg_id="cfg-A")
        for i in range(4):
            t = _task(test_db, p, test_users[0].id, inner_id=100 + i)
            gen = _generation(test_db, p, t, test_users[0].id)
            _task_eval(test_db, er, jr, t, generation=gen,
                       metrics={"accuracy": 0.1}, cfg_id="cfg-B")
        test_db.commit()

        resp = client.post(
            f"{BASE}/projects/{p.id}/statistics",
            json={
                "metrics": ["accuracy"],
                "aggregation": "overall",
                "methods": ["ci"],
                "evaluation_config_ids": ["cfg-A"],
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        stats = body["metrics"]["accuracy"]
        # Only the 4 cfg-A rows (all 0.9) counted → mean ~0.9, n == 4.
        assert stats["n"] == 4
        assert stats["mean"] == pytest.approx(0.9, abs=1e-6)

    def test_field_aggregation_parses_encoded_field_name(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """Field aggregation parses the worker's encoded
        ``"{cfg_id}|{pred}|{ref}"`` field_name into discrete prediction/
        reference fields and resolves display_name from the project's
        evaluation_configs."""
        encoded = "cfg-xyz|__response__|musterloesung"
        p = _project(
            test_db, test_users[0], test_org,
            evaluation_config={
                "evaluation_configs": [
                    {"id": "cfg-xyz", "display_name": "BLEU vs Musterlösung"}
                ]
            },
        )
        er = _eval_run(test_db, p, test_users[0].id)
        jr = _judge_run(test_db, er)
        for i in range(3):
            t = _task(test_db, p, test_users[0].id, inner_id=i + 1)
            gen = _generation(test_db, p, t, test_users[0].id)
            _task_eval(test_db, er, jr, t, generation=gen,
                       field_name=encoded, metrics={"bleu": 0.5 + i * 0.1},
                       cfg_id="cfg-xyz")
        test_db.commit()

        resp = client.post(
            f"{BASE}/projects/{p.id}/statistics",
            json={"metrics": ["bleu"], "aggregation": "field", "methods": ["ci"]},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert encoded in body["by_field"]
        fs = body["by_field"][encoded]
        assert fs["evaluation_config_id"] == "cfg-xyz"
        assert fs["prediction_field"] == "__response__"
        assert fs["reference_field"] == "musterloesung"
        assert fs["display_name"] == "BLEU vs Musterlösung"
        assert "bleu" in fs["metrics"]

    def test_multirun_variance_and_per_run_means(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """Two judge runs over the same task/model produce a runs_by_model_metric
        entry (n_runs=2, std_of_means) and a per_run_means_by_model_metric entry
        with one PerRunMean per run."""
        p = _project(test_db, test_users[0], test_org)
        er = _eval_run(test_db, p, test_users[0].id)
        jr1 = _judge_run(test_db, er, judge_model_id="judge-x", run_index=0)
        jr2 = _judge_run(test_db, er, judge_model_id="judge-x", run_index=1)
        # Same task graded across two runs with different scores → cross-run
        # variance is defined.
        t = _task(test_db, p, test_users[0].id, inner_id=1)
        gen = _generation(test_db, p, t, test_users[0].id)
        _task_eval(test_db, er, jr1, t, generation=gen,
                   metrics={"llm_judge_grade": 10.0}, cfg_id="cfg-run")
        _task_eval(test_db, er, jr2, t, generation=gen,
                   metrics={"llm_judge_grade": 14.0}, cfg_id="cfg-run")
        test_db.commit()

        resp = client.post(
            f"{BASE}/projects/{p.id}/statistics",
            json={"metrics": ["llm_judge_grade"], "aggregation": "model",
                  "methods": ["ci"]},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        runs = body.get("runs_by_model_metric") or {}
        key = "gpt-4o|cfg-run|llm_judge_grade"
        assert key in runs, runs
        assert runs[key]["n_runs"] == 2
        per_run = body.get("per_run_means_by_model_metric") or {}
        assert key in per_run
        assert len(per_run[key]) == 2
        run_indices = sorted(e["run_index"] for e in per_run[key])
        assert run_indices == [0, 1]

    def test_multirun_inter_judge_agreement(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """Two distinct judge_model_ids grading the same items produce a
        judge_agreement_by_model_metric entry with n_judges=2."""
        p = _project(test_db, test_users[0], test_org)
        er = _eval_run(test_db, p, test_users[0].id)
        jr_a = _judge_run(test_db, er, judge_model_id="judge-a", run_index=0)
        jr_b = _judge_run(test_db, er, judge_model_id="judge-b", run_index=0)
        # Two tasks, each scored by both judges.
        for i in range(2):
            t = _task(test_db, p, test_users[0].id, inner_id=i + 1)
            gen = _generation(test_db, p, t, test_users[0].id)
            _task_eval(test_db, er, jr_a, t, generation=gen,
                       metrics={"llm_judge_grade": 8.0 + i}, cfg_id="cfg-ag")
            _task_eval(test_db, er, jr_b, t, generation=gen,
                       metrics={"llm_judge_grade": 9.0 + i}, cfg_id="cfg-ag")
        test_db.commit()

        resp = client.post(
            f"{BASE}/projects/{p.id}/statistics",
            json={"metrics": ["llm_judge_grade"], "aggregation": "model",
                  "methods": ["ci"]},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        agreement = body.get("judge_agreement_by_model_metric") or {}
        key = "gpt-4o|cfg-ag|llm_judge_grade"
        assert key in agreement, agreement
        assert agreement[key]["n_judges"] == 2
        assert agreement[key]["n_items"] >= 1

    def test_correlation_insufficient_data_warning(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """With only 2 samples for the requested metrics (<3 needed), the
        correlation method emits the insufficient-data warning rather than a
        matrix."""
        p = _project(test_db, test_users[0], test_org)
        er = _eval_run(test_db, p, test_users[0].id)
        jr = _judge_run(test_db, er)
        for i in range(2):
            t = _task(test_db, p, test_users[0].id, inner_id=i + 1)
            gen = _generation(test_db, p, t, test_users[0].id)
            _task_eval(test_db, er, jr, t, generation=gen,
                       metrics={"accuracy": 0.8, "f1": 0.7})
        test_db.commit()

        resp = client.post(
            f"{BASE}/projects/{p.id}/statistics",
            json={"metrics": ["accuracy", "f1"], "aggregation": "overall",
                  "methods": ["correlation"]},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body.get("correlations") is None
        warnings = body.get("warnings") or []
        assert any("correlation" in w.lower() for w in warnings)

    def test_bootstrap_permutation_method(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """The bootstrap method runs the permutation test and populates
        bootstrap_p / bootstrap_significant on each pairwise comparison."""
        p = _project(test_db, test_users[0], test_org)
        er = _eval_run(test_db, p, test_users[0].id)
        jr = _judge_run(test_db, er)
        # Two clearly-separated models with several samples each.
        _inner = 0
        for model_id, base in (("gpt-4o", 0.9), ("claude-3", 0.2)):
            for i in range(5):
                _inner += 1
                t = _task(test_db, p, test_users[0].id, inner_id=_inner)
                gen = _generation(test_db, p, t, test_users[0].id, model_id=model_id)
                _task_eval(test_db, er, jr, t, generation=gen,
                           metrics={"accuracy": base + i * 0.01})
        test_db.commit()

        resp = client.post(
            f"{BASE}/projects/{p.id}/statistics",
            json={"metrics": ["accuracy"], "aggregation": "model",
                  "methods": ["bootstrap"]},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        comps = body.get("pairwise_comparisons") or []
        assert len(comps) >= 1
        comp = comps[0]
        assert comp["bootstrap_p"] is not None
        assert comp["bootstrap_significant"] is not None

    def test_annotation_based_results_merge_into_statistics(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """Annotation-side TaskEvaluations (generation_id NULL, annotation_id
        set) merge into the per-model stats under an ``annotator:<name>`` model
        id."""
        p = _project(test_db, test_users[0], test_org)
        er = _eval_run(test_db, p, test_users[0].id, model_id="human")
        jr = _judge_run(test_db, er)
        for i in range(3):
            t = _task(test_db, p, test_users[0].id, inner_id=i + 1)
            ann = Annotation(
                id=_uid(), task_id=t.id, project_id=p.id,
                completed_by=test_users[0].id,
                result=[{"from_name": "answer", "to_name": "text",
                         "type": "choices", "value": {"choices": ["Ja"]}}],
                was_cancelled=False,
            )
            test_db.add(ann)
            test_db.flush()
            _task_eval(test_db, er, jr, t, annotation=ann,
                       metrics={"accuracy": 1.0})
        test_db.commit()

        resp = client.post(
            f"{BASE}/projects/{p.id}/statistics",
            json={"metrics": ["accuracy"], "aggregation": "model",
                  "methods": ["ci"]},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        by_model = body.get("by_model") or {}
        annotator_keys = [k for k in by_model if k.startswith("annotator:")]
        assert annotator_keys, by_model
