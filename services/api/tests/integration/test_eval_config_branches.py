"""
Behavioral integration tests for routers/evaluations/config.py.

These tests exercise the uncovered branches of the evaluation-configuration
sub-router (mounted at prefix ``/api/evaluations`` — see
``routers/evaluations/__init__.py``):

  * GET  /api/evaluations/projects/{id}/evaluation-config
  * PUT  /api/evaluations/projects/{id}/evaluation-config
  * GET  /api/evaluations/projects/{id}/detect-answer-types
  * GET  /api/evaluations/projects/{id}/field-types

The three GET handlers were migrated to the async DB lane
(``Depends(get_async_db)`` + ``await db.execute(select(...))``). The sync
``client`` fixture only overrides ``get_db`` — the async handlers run against a
separate ``get_async_db`` session, so a project seeded inside the sync
``test_db`` transaction is invisible to them. Those tests now seed rows via
``async_test_db`` and drive the surface through ``async_test_client``, asserting
the same status codes + response JSON and re-reading
``Project.evaluation_config`` from ``async_test_db`` to assert stored state.

The PUT handler stays SYNC, so its tests keep the original ``client`` /
``test_db`` / ``auth_headers`` / ``test_org`` pattern unchanged.

Access model recap (from app/core/authorization.check_project_access and
routers/projects/helpers.check_project_accessible):
  * superadmin -> always allowed.
  * the access-control denial branch is exercised by patching the async access
    helper the handler calls (``auth_service.check_project_access_async`` for
    GET /evaluation-config; ``check_project_accessible_async`` for
    detect-answer-types / field-types) to return False, the same lever the
    real org/private check pulls for a non-creator non-superadmin.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select

from main import app
from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from models import User
from project_models import Project, ProjectOrganization

# A binary <Choices> control. The Ja/Nein two-choice pair is detected as the
# BINARY answer type (services/evaluation/config.py::_detect_type_from_tag),
# with name="answer", tag="choices", to_name="text".
BINARY_LABEL_CONFIG = (
    '<View>'
    '<Text name="text" value="$text"/>'
    '<Choices name="answer" toName="text">'
    '<Choice value="Ja"/><Choice value="Nein"/>'
    '</Choices>'
    '</View>'
)


def _uid():
    return str(uuid.uuid4())


def _make_project(
    db,
    creator,
    org=None,
    *,
    label_config=BINARY_LABEL_CONFIG,
    label_config_version=None,
    evaluation_config=None,
    is_private=False,
):
    """Create a Project (optionally assigned to an org) and commit it (sync)."""
    pid = _uid()
    project = Project(
        id=pid,
        title=f"P-{pid[:6]}",
        created_by=creator.id,
        label_config=label_config,
        label_config_version=label_config_version,
        evaluation_config=evaluation_config,
        is_private=is_private,
    )
    db.add(project)
    db.flush()
    if org is not None:
        db.add(
            ProjectOrganization(
                id=_uid(),
                project_id=pid,
                organization_id=org.id,
                assigned_by=creator.id,
            )
        )
        db.flush()
    db.commit()
    return project


def _org_headers(auth_headers, role, org):
    return {**auth_headers[role], "X-Organization-Context": org.id}


# ---------------------------------------------------------------------------
# Async helpers for the migrated GET endpoints
# ---------------------------------------------------------------------------


@contextmanager
def _as_user(db_user: User):
    auth_user = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


async def _seed_user(db, *, is_superadmin=True):
    u = User(
        id=_uid(),
        username=f"ecb-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Eval Config Branch User",
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _seed_project(
    db,
    creator,
    *,
    label_config=BINARY_LABEL_CONFIG,
    label_config_version=None,
    evaluation_config=None,
    is_private=False,
):
    project = Project(
        id=_uid(),
        title=f"P-{uuid.uuid4().hex[:6]}",
        created_by=creator.id,
        label_config=label_config,
        label_config_version=label_config_version,
        evaluation_config=evaluation_config,
        is_private=is_private,
    )
    db.add(project)
    await db.commit()
    return project


async def _reload_eval_config(db, project_id):
    """Re-read the stored evaluation_config from the async session."""
    db.expire_all()
    result = await db.execute(select(Project).where(Project.id == project_id))
    return result.scalar_one().evaluation_config


# =====================================================================
# GET /evaluation-config  (async)
# =====================================================================


class TestGetEvaluationConfig:
    @pytest.mark.asyncio
    async def test_project_not_found_returns_404(self, async_test_client, async_test_db):
        user = await _seed_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get(
                "/api/evaluations/projects/does-not-exist/evaluation-config"
            )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_access_denied_returns_403(self, async_test_client, async_test_db):
        # A non-superadmin, non-creator user: the async access helper returns
        # False -> 403.
        creator = await _seed_user(async_test_db)
        viewer = await _seed_user(async_test_db, is_superadmin=False)
        project = await _seed_project(async_test_db, creator, is_private=True)

        with _as_user(viewer), patch(
            "routers.evaluations.config.auth_service.check_project_access_async",
            return_value=False,
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{project.id}/evaluation-config"
            )
        assert resp.status_code == 403
        assert "permission" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_no_label_config_returns_empty_structure(
        self, async_test_client, async_test_db
    ):
        user = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, user, label_config=None)

        with _as_user(user):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{project.id}/evaluation-config"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body == {
            "detected_answer_types": [],
            "available_methods": {},
            "selected_methods": {},
            "last_updated": None,
        }
        # Empty-structure path must NOT persist anything onto the project.
        assert await _reload_eval_config(async_test_db, project.id) is None

    @pytest.mark.asyncio
    async def test_first_load_generates_and_persists_config(
        self, async_test_client, async_test_db
    ):
        user = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, user, label_config_version="v1")
        assert project.evaluation_config is None

        with _as_user(user):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{project.id}/evaluation-config"
            )
        assert resp.status_code == 200
        body = resp.json()
        # The generated config exposes the detector output for the binary field.
        assert "detected_answer_types" in body
        assert "available_methods" in body
        assert body["label_config_version"] == "v1"
        detected_names = {d["name"] for d in body["detected_answer_types"]}
        assert "answer" in detected_names
        assert "answer" in body["available_methods"]

        # Generated config is persisted to the DB.
        stored = await _reload_eval_config(async_test_db, project.id)
        assert stored is not None
        assert stored["label_config_version"] == "v1"
        assert "answer" in stored["available_methods"]

    @pytest.mark.asyncio
    async def test_force_regenerate_rebuilds_config(
        self, async_test_client, async_test_db
    ):
        stale = {
            "detected_answer_types": [],
            "available_methods": {},
            "selected_methods": {},
            "label_config_version": "v1",
            "stale_marker": True,
        }
        user = await _seed_user(async_test_db)
        project = await _seed_project(
            async_test_db,
            user,
            label_config_version="v1",
            evaluation_config=stale,
        )

        with _as_user(user):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{project.id}/evaluation-config"
                "?force_regenerate=true"
            )
        assert resp.status_code == 200
        body = resp.json()
        # Regeneration repopulates available_methods from the live label_config.
        assert "answer" in body["available_methods"]
        # Existing extra keys are preserved through regeneration.
        assert body.get("stale_marker") is True

        stored = await _reload_eval_config(async_test_db, project.id)
        assert "answer" in stored["available_methods"]

    @pytest.mark.asyncio
    async def test_legacy_config_without_version_gets_stamped(
        self, async_test_client, async_test_db
    ):
        # Pre-version config: has selections but no label_config_version.
        legacy = {
            "detected_answer_types": [
                {"name": "answer", "type": "binary", "to_name": "text"}
            ],
            "available_methods": {
                "answer": {
                    "type": "binary",
                    "available_metrics": ["exact_match"],
                    "available_human": [],
                }
            },
            "selected_methods": {"answer": {"automated": ["exact_match"], "human": []}},
            "evaluation_configs": [{"id": "x", "metric": "exact_match"}],
        }
        user = await _seed_user(async_test_db)
        project = await _seed_project(
            async_test_db,
            user,
            label_config_version="v7",
            evaluation_config=legacy,
        )

        with _as_user(user):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{project.id}/evaluation-config"
            )
        assert resp.status_code == 200
        body = resp.json()
        # The version is stamped in place; user selections are preserved (no
        # regeneration because existing_config_version was None, not mismatched).
        assert body["label_config_version"] == "v7"
        assert body["selected_methods"] == {
            "answer": {"automated": ["exact_match"], "human": []}
        }

        stored = await _reload_eval_config(async_test_db, project.id)
        assert stored["label_config_version"] == "v7"
        assert stored["selected_methods"] == {
            "answer": {"automated": ["exact_match"], "human": []}
        }

    @pytest.mark.asyncio
    async def test_legacy_config_derives_evaluation_configs(
        self, async_test_client, async_test_db
    ):
        # Has selected_methods but no evaluation_configs -> lazy migration
        # derives evaluation_configs.
        legacy = {
            "detected_answer_types": [
                {"name": "answer", "type": "binary", "to_name": "text"}
            ],
            "available_methods": {
                "answer": {"type": "binary", "available_metrics": ["exact_match"]}
            },
            "selected_methods": {
                "answer": {
                    "automated": ["exact_match"],
                    "field_mapping": {
                        "prediction_field": "answer",
                        "reference_field": "answer",
                    },
                }
            },
            "label_config_version": "v3",
        }
        user = await _seed_user(async_test_db)
        project = await _seed_project(
            async_test_db,
            user,
            label_config_version="v3",
            evaluation_config=legacy,
        )

        with _as_user(user):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{project.id}/evaluation-config"
            )
        assert resp.status_code == 200
        body = resp.json()
        derived = body.get("evaluation_configs")
        assert isinstance(derived, list) and len(derived) == 1
        assert derived[0]["metric"] == "exact_match"
        assert derived[0]["id"] == "answer_exact_match"
        assert derived[0]["prediction_fields"] == ["answer"]

        stored = await _reload_eval_config(async_test_db, project.id)
        assert stored["evaluation_configs"][0]["metric"] == "exact_match"


# =====================================================================
# PUT /evaluation-config  (sync handler — unchanged)
# =====================================================================


class TestUpdateEvaluationConfig:
    def test_project_not_found_returns_404(self, client, test_db, test_users, auth_headers):
        resp = client.put(
            "/api/evaluations/projects/missing/evaluation-config",
            json={"selected_methods": {}},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_access_denied_returns_403(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _make_project(
            test_db, test_users[1], test_org, is_private=True
        )
        resp = client.put(
            f"/api/evaluations/projects/{project.id}/evaluation-config",
            json={"selected_methods": {}},
            headers={
                **auth_headers["annotator"],
                "X-Organization-Context": "private",
            },
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Access denied"

    def test_valid_update_persists_config(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _make_project(
            test_db, test_users[0], test_org, label_config_version="v5"
        )
        config = {
            "detected_answer_types": [
                {"name": "answer", "type": "binary", "to_name": "text"}
            ],
            "available_methods": {
                "answer": {
                    "type": "binary",
                    "available_metrics": ["exact_match", "f1"],
                    "available_human": ["likert"],
                    "tag": "choices",
                }
            },
            "selected_methods": {
                "answer": {"automated": ["exact_match"], "human": ["likert"]}
            },
        }
        resp = client.put(
            f"/api/evaluations/projects/{project.id}/evaluation-config",
            json=config,
            headers=_org_headers(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["message"] == "Evaluation configuration updated successfully"
        # Endpoint stamps the project's current label_config_version onto config.
        assert body["config"]["label_config_version"] == "v5"

        test_db.expire_all()
        stored = (
            test_db.query(Project).filter(Project.id == project.id).first()
        ).evaluation_config
        assert stored["selected_methods"] == {
            "answer": {"automated": ["exact_match"], "human": ["likert"]}
        }
        assert stored["label_config_version"] == "v5"

    def test_field_not_in_available_methods_returns_400(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        config = {
            "available_methods": {
                "answer": {"available_metrics": ["exact_match"], "available_human": []}
            },
            "selected_methods": {
                "ghost_field": {"automated": ["exact_match"]}
            },
        }
        resp = client.put(
            f"/api/evaluations/projects/{project.id}/evaluation-config",
            json=config,
            headers=_org_headers(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 400
        assert "ghost_field" in resp.json()["detail"]

    def test_unavailable_metric_returns_400(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        config = {
            "available_methods": {
                "answer": {"available_metrics": ["exact_match"], "available_human": []}
            },
            "selected_methods": {
                "answer": {"automated": ["nonexistent_metric"]}
            },
        }
        resp = client.put(
            f"/api/evaluations/projects/{project.id}/evaluation-config",
            json=config,
            headers=_org_headers(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 400
        assert "nonexistent_metric" in resp.json()["detail"]

    def test_unavailable_human_method_returns_400(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        config = {
            "available_methods": {
                "answer": {
                    "available_metrics": ["exact_match"],
                    "available_human": ["likert"],
                }
            },
            "selected_methods": {
                "answer": {"automated": [], "human": ["nonexistent_human"]}
            },
        }
        resp = client.put(
            f"/api/evaluations/projects/{project.id}/evaluation-config",
            json=config,
            headers=_org_headers(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 400
        assert "nonexistent_human" in resp.json()["detail"]

    def test_runs_per_task_out_of_range_returns_422(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        resp = client.put(
            f"/api/evaluations/projects/{project.id}/evaluation-config",
            json={"runs_per_task": 99},
            headers=_org_headers(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 422
        assert "runs_per_task" in resp.json()["detail"]

    def test_runs_per_task_wrong_type_returns_422(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        resp = client.put(
            f"/api/evaluations/projects/{project.id}/evaluation-config",
            json={"runs_per_task": "five"},
            headers=_org_headers(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 422
        assert "runs_per_task" in resp.json()["detail"]

    def test_runs_per_task_valid_persists(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        resp = client.put(
            f"/api/evaluations/projects/{project.id}/evaluation-config",
            json={"runs_per_task": 3},
            headers=_org_headers(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        test_db.expire_all()
        stored = (
            test_db.query(Project).filter(Project.id == project.id).first()
        ).evaluation_config
        assert stored["runs_per_task"] == 3

    def test_judges_not_a_list_returns_422(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        config = {
            "evaluation_configs": [
                {"metric": "llm_judge_classic", "metric_parameters": {"judges": "gpt-4"}}
            ]
        }
        resp = client.put(
            f"/api/evaluations/projects/{project.id}/evaluation-config",
            json=config,
            headers=_org_headers(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 422
        assert "non-empty list" in resp.json()["detail"]

    def test_judges_empty_list_returns_422(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        config = {
            "evaluation_configs": [
                {"metric": "llm_judge_classic", "metric_parameters": {"judges": []}}
            ]
        }
        resp = client.put(
            f"/api/evaluations/projects/{project.id}/evaluation-config",
            json=config,
            headers=_org_headers(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 422
        assert "non-empty list" in resp.json()["detail"]

    def test_judge_entry_not_a_dict_returns_422(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        config = {
            "evaluation_configs": [
                {
                    "metric": "llm_judge_classic",
                    "metric_parameters": {"judges": ["gpt-4"]},
                }
            ]
        }
        resp = client.put(
            f"/api/evaluations/projects/{project.id}/evaluation-config",
            json=config,
            headers=_org_headers(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 422
        assert "judge_model_id" in resp.json()["detail"]

    def test_judge_missing_model_id_returns_422(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        config = {
            "evaluation_configs": [
                {
                    "metric": "llm_judge_classic",
                    "metric_parameters": {"judges": [{"judge_model_id": "", "runs": 1}]},
                }
            ]
        }
        resp = client.put(
            f"/api/evaluations/projects/{project.id}/evaluation-config",
            json=config,
            headers=_org_headers(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 422
        assert "judge_model_id" in resp.json()["detail"]

    def test_judge_runs_out_of_range_returns_422(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        config = {
            "evaluation_configs": [
                {
                    "metric": "llm_judge_classic",
                    "metric_parameters": {
                        "judges": [{"judge_model_id": "gpt-4", "runs": 99}]
                    },
                }
            ]
        }
        resp = client.put(
            f"/api/evaluations/projects/{project.id}/evaluation-config",
            json=config,
            headers=_org_headers(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 422
        assert "runs" in resp.json()["detail"]

    def test_valid_judges_persists(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        config = {
            "evaluation_configs": [
                {
                    "id": "answer_judge",
                    "metric": "llm_judge_classic",
                    "metric_parameters": {
                        "judges": [{"judge_model_id": "gpt-4", "runs": 2}]
                    },
                }
            ]
        }
        resp = client.put(
            f"/api/evaluations/projects/{project.id}/evaluation-config",
            json=config,
            headers=_org_headers(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        test_db.expire_all()
        stored = (
            test_db.query(Project).filter(Project.id == project.id).first()
        ).evaluation_config
        judges = stored["evaluation_configs"][0]["metric_parameters"]["judges"]
        assert judges == [{"judge_model_id": "gpt-4", "runs": 2}]

    def test_falloesung_wrong_score_scale_returns_422(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        config = {
            "evaluation_configs": [
                {
                    "metric": "llm_judge_falloesung",
                    "metric_parameters": {
                        "judges": [{"judge_model_id": "gpt-4", "runs": 1}],
                        "score_scale": "1-5",
                    },
                }
            ]
        }
        resp = client.put(
            f"/api/evaluations/projects/{project.id}/evaluation-config",
            json=config,
            headers=_org_headers(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "0-100" in detail and "llm_judge_falloesung" in detail

    def test_falloesung_correct_score_scale_persists(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        config = {
            "evaluation_configs": [
                {
                    "metric": "llm_judge_falloesung",
                    "metric_parameters": {
                        "judges": [{"judge_model_id": "gpt-4", "runs": 1}],
                        "score_scale": "0-100",
                    },
                }
            ]
        }
        resp = client.put(
            f"/api/evaluations/projects/{project.id}/evaluation-config",
            json=config,
            headers=_org_headers(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        test_db.expire_all()
        stored = (
            test_db.query(Project).filter(Project.id == project.id).first()
        ).evaluation_config
        mp = stored["evaluation_configs"][0]["metric_parameters"]
        assert mp["score_scale"] == "0-100"


# =====================================================================
# GET /detect-answer-types  (async)
# =====================================================================


class TestDetectAnswerTypes:
    @pytest.mark.asyncio
    async def test_project_not_found_returns_404(self, async_test_client, async_test_db):
        user = await _seed_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get(
                "/api/evaluations/projects/missing/detect-answer-types"
            )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_access_denied_returns_403(self, async_test_client, async_test_db):
        creator = await _seed_user(async_test_db)
        viewer = await _seed_user(async_test_db, is_superadmin=False)
        project = await _seed_project(async_test_db, creator, is_private=True)

        with _as_user(viewer), patch(
            "routers.evaluations.config.check_project_accessible_async",
            return_value=False,
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{project.id}/detect-answer-types"
            )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Access denied"

    @pytest.mark.asyncio
    async def test_no_label_config_returns_message(
        self, async_test_client, async_test_db
    ):
        user = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, user, label_config=None)
        with _as_user(user):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{project.id}/detect-answer-types"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == project.id
        assert body["detected_types"] == []
        assert body["message"] == "No label configuration found"

    @pytest.mark.asyncio
    async def test_detects_answer_types_from_label_config(
        self, async_test_client, async_test_db
    ):
        user = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, user)
        with _as_user(user):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{project.id}/detect-answer-types"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == project.id
        names = {d["name"] for d in body["detected_types"]}
        assert "answer" in names
        assert "answer" in body["available_methods"]
        # The Ja/Nein two-choice control is detected as binary.
        answer_type = next(d for d in body["detected_types"] if d["name"] == "answer")
        assert answer_type["type"] == "binary"


# =====================================================================
# GET /field-types  (async)
# =====================================================================


class TestFieldTypes:
    @pytest.mark.asyncio
    async def test_project_not_found_returns_404(self, async_test_client, async_test_db):
        user = await _seed_user(async_test_db)
        await async_test_db.commit()
        with _as_user(user):
            resp = await async_test_client.get(
                "/api/evaluations/projects/missing/field-types"
            )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_access_denied_returns_403(self, async_test_client, async_test_db):
        creator = await _seed_user(async_test_db)
        viewer = await _seed_user(async_test_db, is_superadmin=False)
        project = await _seed_project(async_test_db, creator, is_private=True)

        with _as_user(viewer), patch(
            "routers.evaluations.config.check_project_accessible_async",
            return_value=False,
        ):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{project.id}/field-types"
            )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Access denied"

    @pytest.mark.asyncio
    async def test_no_label_config_returns_empty_field_types(
        self, async_test_client, async_test_db
    ):
        user = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, user, label_config=None)
        with _as_user(user):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{project.id}/field-types"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == project.id
        assert body["field_types"] == {}

    @pytest.mark.asyncio
    async def test_field_types_built_from_label_config(
        self, async_test_client, async_test_db
    ):
        user = await _seed_user(async_test_db)
        project = await _seed_project(async_test_db, user)
        with _as_user(user):
            resp = await async_test_client.get(
                f"/api/evaluations/projects/{project.id}/field-types"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == project.id
        assert "answer" in body["field_types"]
        field = body["field_types"]["answer"]
        # FieldTypeInfo response model: type, tag, recommended_criteria.
        assert field["type"] == "binary"
        assert "tag" in field
        assert isinstance(field["recommended_criteria"], list)
