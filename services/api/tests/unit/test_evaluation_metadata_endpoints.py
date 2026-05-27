"""
Unit tests for routers/evaluations/metadata.py to increase branch coverage.
Covers evaluated-models, configured-methods, evaluation-history, significance,
and statistics endpoints.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from auth_module.models import User
from database import get_db
from auth_module.dependencies import require_user


def _make_user(is_superadmin=True, user_id="user-123"):
    return User(
        id=user_id,
        username="testuser",
        email="test@example.com",
        name="Test User",
        hashed_password="hashed",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )


def _mock_db():
    mock_db = Mock(spec=Session)
    mock_q = MagicMock()
    mock_q.filter.return_value = mock_q
    mock_q.join.return_value = mock_q
    mock_q.outerjoin.return_value = mock_q
    mock_q.group_by.return_value = mock_q
    mock_q.order_by.return_value = mock_q
    mock_q.distinct.return_value = mock_q
    mock_q.first.return_value = None
    mock_q.all.return_value = []
    mock_q.count.return_value = 0
    mock_db.query.return_value = mock_q
    return mock_db


def _setup_overrides(user=None, mock_db=None):
    if user is None:
        user = _make_user()
    if mock_db is None:
        mock_db = _mock_db()
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: mock_db
    return user, mock_db


# ---------------------------------------------------------------------------
# Evaluated Models
# ---------------------------------------------------------------------------


class TestEvaluatedModels:
    def test_project_not_found(self):
        client = TestClient(app)
        user, mock_db = _setup_overrides()
        try:
            resp = client.get("/api/evaluations/projects/nonexistent/evaluated-models")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_project_access_denied(self):
        client = TestClient(app)
        user, mock_db = _setup_overrides(user=_make_user(is_superadmin=False))

        project = Mock()
        project.id = "p-1"
        project.generation_config = None

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.join.return_value = mock_q
        mock_q.distinct.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.all.return_value = []
        mock_db.query.return_value = mock_q

        try:
            with patch("routers.evaluations.metadata.check_project_accessible", return_value=False):
                resp = client.get("/api/evaluations/projects/p-1/evaluated-models")
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_no_models_returns_empty(self):
        client = TestClient(app)
        user, mock_db = _setup_overrides()

        project = Mock()
        project.id = "p-1"
        project.generation_config = None

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.join.return_value = mock_q
        mock_q.distinct.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.all.return_value = []
        mock_q.order_by.return_value = mock_q
        mock_db.query.return_value = mock_q

        try:
            with patch("routers.evaluations.metadata.check_project_accessible", return_value=True):
                resp = client.get("/api/evaluations/projects/p-1/evaluated-models")
                assert resp.status_code == 200
                assert resp.json() == []
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Configured Methods
# ---------------------------------------------------------------------------


class TestConfiguredMethods:
    def test_project_not_found(self):
        client = TestClient(app)
        user, mock_db = _setup_overrides()
        try:
            resp = client.get("/api/evaluations/projects/nonexistent/configured-methods")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_no_eval_config(self):
        client = TestClient(app)
        user, mock_db = _setup_overrides()

        project = Mock()
        project.id = "p-1"
        project.evaluation_config = None

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.all.return_value = []
        mock_db.query.return_value = mock_q

        try:
            with patch("routers.evaluations.metadata.check_project_accessible", return_value=True):
                resp = client.get("/api/evaluations/projects/p-1/configured-methods")
                assert resp.status_code == 200
                assert resp.json()["fields"] == []
        finally:
            app.dependency_overrides.clear()

    def test_with_selected_methods(self):
        client = TestClient(app)
        user, mock_db = _setup_overrides()

        project = Mock()
        project.id = "p-1"
        project.evaluation_config = {
            "selected_methods": {
                "answer": {
                    "automated": ["rouge_l", {"name": "llm_judge_custom", "parameters": {"criteria": "accuracy"}}],
                    "human": ["likert_scale"],
                    "field_mapping": {"prediction_field": "answer", "reference_field": "answer"},
                }
            },
            "available_methods": {
                "answer": {"type": "text", "to_name": "answer"}
            },
        }

        eval_run = Mock()
        eval_run.id = "eval-1"
        eval_run.status = "completed"
        eval_run.metrics = {"rouge_l": 0.75}
        eval_run.completed_at = datetime.now(timezone.utc)

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.all.return_value = [eval_run]
        mock_db.query.return_value = mock_q

        try:
            with patch("routers.evaluations.metadata.check_project_accessible", return_value=True):
                resp = client.get("/api/evaluations/projects/p-1/configured-methods")
                assert resp.status_code == 200
                data = resp.json()
                assert len(data["fields"]) == 1
                assert data["fields"][0]["field_name"] == "answer"
        finally:
            app.dependency_overrides.clear()

    def test_empty_selected_methods(self):
        client = TestClient(app)
        user, mock_db = _setup_overrides()

        project = Mock()
        project.id = "p-1"
        project.evaluation_config = {"selected_methods": {}}

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_db.query.return_value = mock_q

        try:
            with patch("routers.evaluations.metadata.check_project_accessible", return_value=True):
                resp = client.get("/api/evaluations/projects/p-1/configured-methods")
                assert resp.status_code == 200
                assert resp.json()["fields"] == []
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Evaluation History
# ---------------------------------------------------------------------------


class TestEvaluationHistory:
    def test_project_not_found(self):
        client = TestClient(app)
        user, mock_db = _setup_overrides()
        try:
            resp = client.get(
                "/api/evaluations/projects/nonexistent/evaluation-history?model_ids=m1&metrics=accuracy"
            )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_access_denied(self):
        client = TestClient(app)
        user, mock_db = _setup_overrides(user=_make_user(is_superadmin=False))

        project = Mock()
        project.id = "p-1"
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_db.query.return_value = mock_q

        try:
            with patch("routers.evaluations.metadata.check_project_accessible", return_value=False):
                resp = client.get(
                    "/api/evaluations/projects/p-1/evaluation-history?model_ids=m1&metrics=accuracy"
                )
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_with_empty_results_returns_empty_series(self):
        """Issue #111: /evaluation-history now returns ``{series: [...]}``.

        The unit-test fixtures here mock ``db.query`` to a chainable
        MagicMock returning an empty list, so we assert the new shape
        without seeding rows. Real per-row aggregation is covered by the
        integration tests against a real Postgres.
        """
        client = TestClient(app)
        user, mock_db = _setup_overrides()

        project = Mock()
        project.id = "p-1"
        project.evaluation_config = None

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.join.return_value = mock_q
        mock_q.outerjoin.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.all.return_value = []
        mock_db.query.return_value = mock_q

        try:
            with patch("routers.evaluations.metadata.check_project_accessible", return_value=True):
                resp = client.get(
                    "/api/evaluations/projects/p-1/evaluation-history?model_ids=gpt-4&metrics=accuracy"
                )
                assert resp.status_code == 200
                data = resp.json()
                assert "series" in data
                assert data["series"] == []
        finally:
            app.dependency_overrides.clear()

    def test_with_date_filters(self):
        client = TestClient(app)
        user, mock_db = _setup_overrides()

        project = Mock()
        project.id = "p-1"
        project.evaluation_config = None

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.join.return_value = mock_q
        mock_q.outerjoin.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.all.return_value = []
        mock_db.query.return_value = mock_q

        try:
            with patch("routers.evaluations.metadata.check_project_accessible", return_value=True):
                resp = client.get(
                    "/api/evaluations/projects/p-1/evaluation-history"
                    "?model_ids=gpt-4&metrics=accuracy"
                    "&start_date=2025-01-01T00:00:00"
                    "&end_date=2025-12-31T23:59:59"
                )
                assert resp.status_code == 200
                assert resp.json() == {"series": []}
        finally:
            app.dependency_overrides.clear()

    def test_with_evaluation_config_ids_filter(self):
        """Issue #111: ``evaluation_config_ids`` is accepted as a Query param."""
        client = TestClient(app)
        user, mock_db = _setup_overrides()

        project = Mock()
        project.id = "p-1"
        project.evaluation_config = None

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.join.return_value = mock_q
        mock_q.outerjoin.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.all.return_value = []
        mock_db.query.return_value = mock_q

        try:
            with patch("routers.evaluations.metadata.check_project_accessible", return_value=True):
                resp = client.get(
                    "/api/evaluations/projects/p-1/evaluation-history"
                    "?model_ids=gpt-4&metrics=accuracy"
                    "&evaluation_config_ids=cfgA&evaluation_config_ids=cfgB"
                )
                assert resp.status_code == 200
                assert resp.json() == {"series": []}
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Significance Tests
# ---------------------------------------------------------------------------


class TestSignificanceTests:
    def test_project_not_found(self):
        client = TestClient(app)
        user, mock_db = _setup_overrides()
        try:
            resp = client.get(
                "/api/evaluations/significance/nonexistent?model_ids=m1&model_ids=m2&metrics=accuracy"
            )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_scipy_not_available(self):
        client = TestClient(app)
        user, mock_db = _setup_overrides()

        project = Mock()
        project.id = "p-1"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.join.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.all.return_value = []
        mock_db.query.return_value = mock_q

        try:
            with patch("routers.evaluations.metadata.check_project_accessible", return_value=True), \
                 patch("routers.leaderboards.STATS_AVAILABLE", False):
                resp = client.get(
                    "/api/evaluations/significance/p-1?model_ids=m1&model_ids=m2&metrics=accuracy"
                )
                assert resp.status_code == 200
                assert "not available" in resp.json().get("message", "")
        finally:
            app.dependency_overrides.clear()

    def test_insufficient_data(self):
        client = TestClient(app)
        user, mock_db = _setup_overrides()

        project = Mock()
        project.id = "p-1"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.join.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.all.return_value = []
        mock_db.query.return_value = mock_q

        try:
            with patch("routers.evaluations.metadata.check_project_accessible", return_value=True), \
                 patch("routers.leaderboards.STATS_AVAILABLE", True):
                resp = client.get(
                    "/api/evaluations/significance/p-1?model_ids=m1&model_ids=m2&metrics=accuracy"
                )
                assert resp.status_code == 200
                comps = resp.json()["comparisons"]
                assert len(comps) == 1
                assert comps[0]["significant"] == False  # noqa: E712
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


class TestStatistics:
    def test_project_not_found(self):
        client = TestClient(app)
        user, mock_db = _setup_overrides()
        try:
            resp = client.post(
                "/api/evaluations/projects/nonexistent/statistics",
                json={"metrics": ["accuracy"]},
            )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_no_evaluations(self):
        client = TestClient(app)
        user, mock_db = _setup_overrides()

        project = Mock()
        project.id = "p-1"

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_q.all.return_value = []
        mock_db.query.return_value = mock_q

        try:
            with patch("routers.evaluations.metadata.check_project_accessible", return_value=True):
                resp = client.post(
                    "/api/evaluations/projects/p-1/statistics",
                    json={"metrics": ["accuracy"]},
                )
                assert resp.status_code == 404
                assert "No completed evaluations" in resp.json()["detail"]
        finally:
            app.dependency_overrides.clear()

    def test_access_denied(self):
        client = TestClient(app)
        user, mock_db = _setup_overrides(user=_make_user(is_superadmin=False))

        project = Mock()
        project.id = "p-1"
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = project
        mock_db.query.return_value = mock_q

        try:
            with patch("routers.evaluations.metadata.check_project_accessible", return_value=False):
                resp = client.post(
                    "/api/evaluations/projects/p-1/statistics",
                    json={"metrics": ["accuracy"]},
                )
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Issue #111 — per-config integration tests (real DB)
# ---------------------------------------------------------------------------

# These tests seed real ``TaskEvaluation`` rows with distinct
# ``evaluation_config_id`` values so the new ``/statistics``,
# ``/significance``, and ``/evaluation-history`` per-config plumbing is
# exercised end-to-end. They live in the unit module by historical
# convention, but use the same real-Postgres fixtures the other unit
# tests already pull in (``test_db``, ``test_users``, ``test_org``,
# ``auth_headers``, ``client``).


def _seed_two_config_project(test_db, test_users, test_org):
    """Build a project with two evaluation_configs sharing ``metric=bleu``.

    Seeds two ``EvaluationRun`` + ``EvaluationJudgeRun`` + per-task
    ``TaskEvaluation`` rows per model (cfgA + cfgB), so the per-config
    filter has data on both sides. Returns the project, both config ids,
    and the seeded model ids.
    """
    import uuid as _uuid
    import json as _json
    from datetime import datetime as _dt, timezone as _tz
    from models import (
        EvaluationJudgeRun,
        EvaluationRun,
        Generation,
        ResponseGeneration,
        TaskEvaluation,
    )
    from project_models import Project, ProjectOrganization, Task

    admin = test_users[0]
    cfg_a_id = f"cfgA-{_uuid.uuid4().hex[:6]}"
    cfg_b_id = f"cfgB-{_uuid.uuid4().hex[:6]}"
    project = Project(
        id=str(_uuid.uuid4()),
        title=f"Issue111 {_uuid.uuid4().hex[:6]}",
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/></View>',
        evaluation_config={
            "evaluation_configs": [
                {"id": cfg_a_id, "metric": "bleu", "display_name": "BLEU strict"},
                {"id": cfg_b_id, "metric": "bleu", "display_name": "BLEU relaxed"},
            ],
        },
        generation_config={
            "selected_configuration": {"models": ["gpt-4o", "claude-3-sonnet"]},
        },
    )
    test_db.add(project)
    test_db.flush()
    test_db.add(ProjectOrganization(
        id=str(_uuid.uuid4()), project_id=project.id,
        organization_id=test_org.id, assigned_by=admin.id,
    ))
    test_db.flush()

    tasks = []
    for i in range(4):
        t = Task(
            id=str(_uuid.uuid4()), project_id=project.id,
            data={"text": f"Task {i}"}, inner_id=i + 1, created_by=admin.id,
        )
        test_db.add(t)
        tasks.append(t)
    test_db.flush()

    models = ["gpt-4o", "claude-3-sonnet"]
    for model_id in models:
        rg = ResponseGeneration(
            id=str(_uuid.uuid4()), project_id=project.id,
            model_id=model_id, status="completed", created_by=admin.id,
            started_at=_dt.now(_tz.utc), completed_at=_dt.now(_tz.utc),
        )
        test_db.add(rg)
        test_db.flush()
        gens = []
        for i, t in enumerate(tasks):
            g = Generation(
                id=str(_uuid.uuid4()), generation_id=rg.id, task_id=t.id,
                model_id=model_id, run_index=i,
                case_data=_json.dumps(t.data), response_content=f"r-{i}",
                label_config_version="v1", status="completed",
                parse_status="success",
            )
            test_db.add(g)
            gens.append(g)
        test_db.flush()

        # One EvaluationRun + JudgeRun pair per model — both configs land
        # under the same run so the multi-run aggregator has to bucket on
        # ``evaluation_config_id`` itself rather than relying on run_id.
        er = EvaluationRun(
            id=str(_uuid.uuid4()), project_id=project.id, model_id=model_id,
            evaluation_type_ids=["bleu"],
            metrics={"bleu": 0.7},
            status="completed", samples_evaluated=len(tasks) * 2,
            has_sample_results=True, created_by=admin.id,
            created_at=_dt.now(_tz.utc), completed_at=_dt.now(_tz.utc),
        )
        test_db.add(er)
        test_db.flush()
        jr = EvaluationJudgeRun(
            id=str(_uuid.uuid4()), evaluation_id=er.id, judge_model_id=None,
            run_index=0, status="completed",
        )
        test_db.add(jr)
        test_db.flush()
        # Two TaskEvaluation rows per task — one per config — so the
        # per-config filter excludes exactly half the data on each side.
        # cfgA scores deliberately higher than cfgB so model-level means
        # split cleanly when filtered.
        for cfg_id, base in ((cfg_a_id, 0.8), (cfg_b_id, 0.4)):
            for i, t in enumerate(tasks):
                te = TaskEvaluation(
                    id=str(_uuid.uuid4()), evaluation_id=er.id,
                    judge_run_id=jr.id, task_id=t.id,
                    generation_id=gens[i].id,
                    field_name=f"{cfg_id}|answer|answer",
                    evaluation_config_id=cfg_id,
                    answer_type="text",
                    ground_truth={"value": "ref"},
                    prediction={"value": f"hyp-{i}"},
                    metrics={"bleu": round(base + i * 0.01, 4)},
                    passed=True,
                )
                test_db.add(te)
    test_db.commit()
    return {
        "project": project,
        "cfg_a_id": cfg_a_id,
        "cfg_b_id": cfg_b_id,
        "model_ids": models,
    }


def _h(auth_headers, test_org):
    h = dict(auth_headers["admin"])
    h["X-Organization-Context"] = test_org.id
    return h


class TestComputeStatisticsPerConfig:
    """Issue #111: per-config plumbing in POST /statistics."""

    def test_raw_scores_carry_evaluation_config_id(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        data = _seed_two_config_project(test_db, test_users, test_org)
        resp = client.post(
            f"/api/evaluations/projects/{data['project'].id}/statistics",
            json={"metrics": ["bleu"], "aggregation": "sample"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        raw = body.get("raw_scores") or []
        # We seeded 2 models × 4 tasks × 2 configs = 16 rows.
        assert len(raw) == 16
        cfg_ids = {r.get("evaluation_config_id") for r in raw}
        assert cfg_ids == {data["cfg_a_id"], data["cfg_b_id"]}

    def test_evaluation_config_ids_filter_excludes_other(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        data = _seed_two_config_project(test_db, test_users, test_org)
        resp = client.post(
            f"/api/evaluations/projects/{data['project'].id}/statistics",
            json={
                "metrics": ["bleu"],
                "aggregation": "sample",
                "evaluation_config_ids": [data["cfg_a_id"]],
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        raw = resp.json().get("raw_scores") or []
        assert len(raw) == 8  # 2 models × 4 tasks × 1 config
        assert {r["evaluation_config_id"] for r in raw} == {data["cfg_a_id"]}

    def test_by_field_carries_structured_fields(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        data = _seed_two_config_project(test_db, test_users, test_org)
        resp = client.post(
            f"/api/evaluations/projects/{data['project'].id}/statistics",
            json={"metrics": ["bleu"], "aggregation": "field"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        by_field = resp.json().get("by_field") or {}
        # Outer key remains the raw field_name. Two distinct field_names
        # for two configs.
        assert len(by_field) == 2
        for field_name, fs in by_field.items():
            assert fs["evaluation_config_id"] in (data["cfg_a_id"], data["cfg_b_id"])
            assert fs["prediction_field"] == "answer"
            assert fs["reference_field"] == "answer"
            assert fs["display_name"] in ("BLEU strict", "BLEU relaxed")

    def test_runs_by_model_metric_keyed_with_config_id(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        data = _seed_two_config_project(test_db, test_users, test_org)
        resp = client.post(
            f"/api/evaluations/projects/{data['project'].id}/statistics",
            json={"metrics": ["bleu"], "aggregation": "model"},
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        runs = resp.json().get("runs_by_model_metric") or {}
        # Re-keyed to "model|config|metric" — two distinct buckets per
        # model so the same metric type with different configs surfaces
        # separately for RQ5 / inter-judge analysis.
        expected = {
            f"{m}|{cfg}|bleu"
            for m in data["model_ids"]
            for cfg in (data["cfg_a_id"], data["cfg_b_id"])
        }
        assert expected.issubset(set(runs.keys()))


class TestSignificanceTestsPerConfig:
    """Issue #111: ``evaluation_config_ids`` Query param on /significance."""

    def test_evaluation_config_filter_excludes_other(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        data = _seed_two_config_project(test_db, test_users, test_org)
        # cfgA score base 0.8, cfgB score base 0.4 — so filtering to cfgB
        # should compare the two models on the lower-band scores only.
        resp = client.get(
            f"/api/evaluations/significance/{data['project'].id}"
            f"?model_ids={data['model_ids'][0]}&model_ids={data['model_ids'][1]}"
            f"&metrics=bleu&evaluation_config_ids={data['cfg_b_id']}",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        comps = resp.json().get("comparisons") or []
        # The two models share the same scores per cfg in this seed
        # (deterministic, model-agnostic). Just assert we got the one
        # pair × one metric row back, scoped by cfgB. Detailed numeric
        # assertions live in the existing significance tests.
        assert len(comps) == 1
        assert comps[0]["metric"] == "bleu"


class TestEvaluationHistoryPerConfig:
    """Issue #111: ``/evaluation-history`` returns one series per
    (metric, evaluation_config_id) pair."""

    def test_series_split_per_config(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        data = _seed_two_config_project(test_db, test_users, test_org)
        resp = client.get(
            f"/api/evaluations/projects/{data['project'].id}/evaluation-history"
            f"?model_ids={data['model_ids'][0]}&model_ids={data['model_ids'][1]}"
            "&metrics=bleu",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        series = body.get("series") or []
        # One series per (metric, evaluation_config_id) — bleu × {cfgA, cfgB}.
        assert len(series) == 2
        cfg_ids = {s["evaluation_config_id"] for s in series}
        assert cfg_ids == {data["cfg_a_id"], data["cfg_b_id"]}
        display_names = {s["display_name"] for s in series}
        assert display_names == {"BLEU strict", "BLEU relaxed"}
        for s in series:
            assert s["metric"] == "bleu"
            assert isinstance(s["data"], list)
            for point in s["data"]:
                assert "date" in point
                assert "model_id" in point
                assert "value" in point
                assert "sample_count" in point
