"""
Behavioral integration tests for routers/evaluations/config.py.

These tests exercise the uncovered branches of the evaluation-configuration
sub-router (mounted at prefix ``/api/evaluations`` — see
``routers/evaluations/__init__.py``):

  * GET  /api/evaluations/projects/{id}/evaluation-config
  * PUT  /api/evaluations/projects/{id}/evaluation-config
  * GET  /api/evaluations/projects/{id}/detect-answer-types
  * GET  /api/evaluations/projects/{id}/field-types

Every test calls the endpoint via the ``client`` fixture and asserts the exact
status code + response JSON, and — wherever the endpoint persists a config row
— re-reads ``Project.evaluation_config`` from ``test_db`` to assert the stored
state. No route-registration / decorator / source-structure assertions.

Access model recap (from app/core/authorization.check_project_access and
routers/projects/helpers.check_project_accessible):
  * superadmin (test_users[0], "admin") -> always allowed
  * a private project's creator is the only non-superadmin allowed when the
    request carries ``X-Organization-Context: private`` (or the project is
    private) -> used to produce deterministic 403s for non-creators.
"""

import uuid

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
    """Create a Project (optionally assigned to an org) and commit it."""
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


# =====================================================================
# GET /evaluation-config
# =====================================================================


class TestGetEvaluationConfig:
    def test_project_not_found_returns_404(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            "/api/evaluations/projects/does-not-exist/evaluation-config",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_access_denied_returns_403(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        # Private project created by the contributor; the annotator is neither
        # superadmin nor creator -> check_project_access returns False -> 403.
        project = _make_project(
            test_db, test_users[1], test_org, is_private=True
        )
        resp = client.get(
            f"/api/evaluations/projects/{project.id}/evaluation-config",
            headers={
                **auth_headers["annotator"],
                "X-Organization-Context": "private",
            },
        )
        assert resp.status_code == 403
        assert "permission" in resp.json()["detail"].lower()

    def test_no_label_config_returns_empty_structure(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org, label_config=None)

        resp = client.get(
            f"/api/evaluations/projects/{project.id}/evaluation-config",
            headers=_org_headers(auth_headers, "admin", test_org),
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
        test_db.expire_all()
        refreshed = test_db.query(Project).filter(Project.id == project.id).first()
        assert refreshed.evaluation_config is None

    def test_first_load_generates_and_persists_config(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _make_project(
            test_db, test_users[0], test_org, label_config_version="v1"
        )
        assert project.evaluation_config is None

        resp = client.get(
            f"/api/evaluations/projects/{project.id}/evaluation-config",
            headers=_org_headers(auth_headers, "admin", test_org),
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

        # Generated config is persisted to the DB (db.commit on line ~168).
        test_db.expire_all()
        stored = (
            test_db.query(Project).filter(Project.id == project.id).first()
        ).evaluation_config
        assert stored is not None
        assert stored["label_config_version"] == "v1"
        assert "answer" in stored["available_methods"]

    def test_force_regenerate_rebuilds_config(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        stale = {
            "detected_answer_types": [],
            "available_methods": {},
            "selected_methods": {},
            "label_config_version": "v1",
            "stale_marker": True,
        }
        project = _make_project(
            test_db,
            test_users[0],
            test_org,
            label_config_version="v1",
            evaluation_config=stale,
        )

        resp = client.get(
            f"/api/evaluations/projects/{project.id}/evaluation-config"
            "?force_regenerate=true",
            headers=_org_headers(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        # Regeneration repopulates available_methods from the live label_config.
        assert "answer" in body["available_methods"]
        # Existing extra keys are preserved through regeneration.
        assert body.get("stale_marker") is True

        test_db.expire_all()
        stored = (
            test_db.query(Project).filter(Project.id == project.id).first()
        ).evaluation_config
        assert "answer" in stored["available_methods"]

    def test_legacy_config_without_version_gets_stamped(
        self, client, test_db, test_users, auth_headers, test_org
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
        project = _make_project(
            test_db,
            test_users[0],
            test_org,
            label_config_version="v7",
            evaluation_config=legacy,
        )

        resp = client.get(
            f"/api/evaluations/projects/{project.id}/evaluation-config",
            headers=_org_headers(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        # The version is stamped in place; user selections are preserved (no
        # regeneration because existing_config_version was None, not mismatched).
        assert body["label_config_version"] == "v7"
        assert body["selected_methods"] == {
            "answer": {"automated": ["exact_match"], "human": []}
        }

        test_db.expire_all()
        stored = (
            test_db.query(Project).filter(Project.id == project.id).first()
        ).evaluation_config
        assert stored["label_config_version"] == "v7"
        assert stored["selected_methods"] == {
            "answer": {"automated": ["exact_match"], "human": []}
        }

    def test_legacy_config_derives_evaluation_configs(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        # Has selected_methods but no evaluation_configs -> lazy migration
        # derives evaluation_configs (lines ~181-188).
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
        project = _make_project(
            test_db,
            test_users[0],
            test_org,
            label_config_version="v3",
            evaluation_config=legacy,
        )

        resp = client.get(
            f"/api/evaluations/projects/{project.id}/evaluation-config",
            headers=_org_headers(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        derived = body.get("evaluation_configs")
        assert isinstance(derived, list) and len(derived) == 1
        assert derived[0]["metric"] == "exact_match"
        assert derived[0]["id"] == "answer_exact_match"
        assert derived[0]["prediction_fields"] == ["answer"]

        test_db.expire_all()
        stored = (
            test_db.query(Project).filter(Project.id == project.id).first()
        ).evaluation_config
        assert stored["evaluation_configs"][0]["metric"] == "exact_match"


# =====================================================================
# PUT /evaluation-config
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
# GET /detect-answer-types
# =====================================================================


class TestDetectAnswerTypes:
    def test_project_not_found_returns_404(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            "/api/evaluations/projects/missing/detect-answer-types",
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
        resp = client.get(
            f"/api/evaluations/projects/{project.id}/detect-answer-types",
            headers={
                **auth_headers["annotator"],
                "X-Organization-Context": "private",
            },
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Access denied"

    def test_no_label_config_returns_message(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org, label_config=None)
        resp = client.get(
            f"/api/evaluations/projects/{project.id}/detect-answer-types",
            headers=_org_headers(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == project.id
        assert body["detected_types"] == []
        assert body["message"] == "No label configuration found"

    def test_detects_answer_types_from_label_config(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"/api/evaluations/projects/{project.id}/detect-answer-types",
            headers=_org_headers(auth_headers, "admin", test_org),
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
# GET /field-types
# =====================================================================


class TestFieldTypes:
    def test_project_not_found_returns_404(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            "/api/evaluations/projects/missing/field-types",
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
        resp = client.get(
            f"/api/evaluations/projects/{project.id}/field-types",
            headers={
                **auth_headers["annotator"],
                "X-Organization-Context": "private",
            },
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Access denied"

    def test_no_label_config_returns_empty_field_types(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org, label_config=None)
        resp = client.get(
            f"/api/evaluations/projects/{project.id}/field-types",
            headers=_org_headers(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == project.id
        assert body["field_types"] == {}

    def test_field_types_built_from_label_config(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        resp = client.get(
            f"/api/evaluations/projects/{project.id}/field-types",
            headers=_org_headers(auth_headers, "admin", test_org),
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
