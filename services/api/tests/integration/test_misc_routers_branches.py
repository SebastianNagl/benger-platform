"""Behavioral integration tests for several smaller platform API routers.

Seeds real rows via ``test_db`` and asserts HTTP status + response JSON +
persisted DB state against Postgres. Existing unit suites cover these
routers with Mock sessions; this module exercises the real query/commit
paths the mocks cannot.

Routers / endpoints covered:

- ``services/api/routers/prompt_structures.py``
  (``/api/projects/{pid}/generation-config/structures``):
    * ``PUT /{key}`` create → persisted into ``generation_config.prompt_structures``.
    * key-validation 400 (bad chars / too long).
    * 404 project, 403 outsider-org-context.
    * ``GET ""`` list + ``GET /{key}`` get + ``GET /{key}`` 404 missing.
    * ``PUT ""`` set-active validation (unknown key 400) + persisted active list.
    * ``DELETE /{key}`` 404 missing, and delete that also drops the key from
      ``active_structures``.

- ``services/api/routers/dashboard.py`` (``/api/dashboard/stats``):
    * the empty-``project_summaries`` live-fallback path: seeded tasks /
      annotations / generations are counted by ``_live_dashboard_counts``.
    * the no-accessible-projects all-zeros short-circuit.

- ``services/api/routers/file_uploads.py`` (``/api/files``):
    * ``GET /`` empty + ``task_id`` filter + ownership scoping.
    * ``GET /{id}/download`` 404 for an unknown / not-owned file (reached
      before any object-storage call).
    * ``DELETE /{id}`` 404 unknown, persisted delete for an owned record
      with no storage_key (no MinIO call).

- ``services/api/routers/evaluations/status.py`` (``/api/evaluations``):
    * ``GET /evaluation/status/{id}`` 404 + 403 + happy path.
    * ``GET /`` org-scoped list (superadmin sees all; the empty-accessible
      short-circuit).
    * ``GET /evaluation-types`` combined category filter, and
      ``GET /evaluation-types/{id}`` is_active=False 404.

MinIO byte-streaming (upload + presigned download success) is out of scope.
"""

from __future__ import annotations

import uuid

import pytest

from models import EvaluationRun, EvaluationType, Generation, Organization, ResponseGeneration, UploadedData
from project_models import Annotation, Project, ProjectOrganization, Task


def _uid() -> str:
    return str(uuid.uuid4())


def _make_project(db, creator, org=None, *, is_private=False):
    p = Project(
        id=_uid(),
        title=f"Misc Branch {uuid.uuid4().hex[:6]}",
        created_by=creator.id,
        is_private=is_private,
        label_config='<View><Text name="text" value="$text"/></View>',
    )
    db.add(p)
    db.flush()
    if org is not None:
        db.add(
            ProjectOrganization(
                id=_uid(),
                project_id=p.id,
                organization_id=org.id,
                assigned_by=creator.id,
            )
        )
        db.flush()
    return p


def _ctx(auth_headers, role, org):
    return {**auth_headers[role], "X-Organization-Context": org.id}


# ===========================================================================
# prompt_structures.py
# ===========================================================================

_STRUCT_BASE = "/api/projects/{pid}/generation-config/structures"


def _struct_payload(name="My Structure"):
    return {
        "name": name,
        "description": "branch coverage structure",
        "system_prompt": "You are a helpful legal assistant.",
        "instruction_prompt": "Answer the question: {question}",
    }


@pytest.mark.integration
class TestPromptStructuresCreateAndValidate:
    def test_create_structure_persists(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.put(
            _STRUCT_BASE.format(pid=project.id) + "/basic",
            json=_struct_payload(),
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["key"] == "basic"
        assert body["name"] == "My Structure"

        test_db.expire_all()
        refreshed = test_db.query(Project).filter(Project.id == project.id).first()
        structures = refreshed.generation_config["prompt_structures"]
        assert "basic" in structures
        assert structures["basic"]["name"] == "My Structure"

    def test_invalid_key_too_long_400(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        """A key longer than 50 chars fails validate_structure_key with a 400
        (the length guard, no URL-encoding ambiguity)."""
        project = _make_project(test_db, test_users[0], test_org)
        test_db.commit()

        long_key = "a" * 60
        resp = client.put(
            _STRUCT_BASE.format(pid=project.id) + f"/{long_key}",
            json=_struct_payload(),
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 400
        assert "1-50 characters" in resp.json()["detail"]

    def test_invalid_key_chars_400(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        test_db.commit()

        # '.' is not in [a-zA-Z0-9_-]; needs no URL-encoding and stays a single
        # path segment, so it reaches validate_structure_key → 400.
        resp = client.put(
            _STRUCT_BASE.format(pid=project.id) + "/bad.key",
            json=_struct_payload(),
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 400
        assert "alphanumeric" in resp.json()["detail"]

    def test_project_not_found_404(
        self, client, auth_headers, test_org
    ):
        missing = _uid()
        resp = client.put(
            _STRUCT_BASE.format(pid=missing) + "/basic",
            json=_struct_payload(),
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 404
        assert missing in resp.json()["detail"]

    def test_outsider_org_context_403(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        other_org = Organization(
            id=_uid(),
            name="Outsider Struct Org",
            slug=f"outsider-struct-{uuid.uuid4().hex[:6]}",
            display_name="Outsider Struct Org",
        )
        test_db.add(other_org)
        test_db.flush()
        project = _make_project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.put(
            _STRUCT_BASE.format(pid=project.id) + "/basic",
            json=_struct_payload(),
            headers={
                **auth_headers["contributor"],
                "X-Organization-Context": other_org.id,
            },
        )
        assert resp.status_code == 403
        assert "permission" in resp.json()["detail"]


@pytest.mark.integration
class TestPromptStructuresReadDeleteActivate:
    def _seed_structure(self, client, auth_headers, project, org, key="basic"):
        resp = client.put(
            _STRUCT_BASE.format(pid=project.id) + f"/{key}",
            json=_struct_payload(name=f"Struct {key}"),
            headers=_ctx(auth_headers, "admin", org),
        )
        assert resp.status_code == 200

    def test_list_and_get_structure(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        test_db.commit()
        self._seed_structure(client, auth_headers, project, test_org, key="alpha")

        list_resp = client.get(
            _STRUCT_BASE.format(pid=project.id),
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert list_resp.status_code == 200
        assert "alpha" in list_resp.json()
        assert list_resp.json()["alpha"]["key"] == "alpha"

        get_resp = client.get(
            _STRUCT_BASE.format(pid=project.id) + "/alpha",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "Struct alpha"

    def test_get_missing_structure_404(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.get(
            _STRUCT_BASE.format(pid=project.id) + "/nope",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 404
        assert "nope" in resp.json()["detail"]

    def test_set_active_unknown_key_400(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.put(
            _STRUCT_BASE.format(pid=project.id),
            json=["ghost"],
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 400
        assert "does not exist" in resp.json()["detail"]

    def test_set_active_persists(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        test_db.commit()
        self._seed_structure(client, auth_headers, project, test_org, key="alpha")

        resp = client.put(
            _STRUCT_BASE.format(pid=project.id),
            json=["alpha"],
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        assert resp.json()["active_structures"] == ["alpha"]

        test_db.expire_all()
        refreshed = test_db.query(Project).filter(Project.id == project.id).first()
        active = refreshed.generation_config["selected_configuration"]["active_structures"]
        assert active == ["alpha"]

    def test_delete_missing_structure_404(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.delete(
            _STRUCT_BASE.format(pid=project.id) + "/ghost",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 404
        assert "ghost" in resp.json()["detail"]

    def test_delete_drops_from_active(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        test_db.commit()
        self._seed_structure(client, auth_headers, project, test_org, key="alpha")
        # Mark it active.
        client.put(
            _STRUCT_BASE.format(pid=project.id),
            json=["alpha"],
            headers=_ctx(auth_headers, "admin", test_org),
        )

        resp = client.delete(
            _STRUCT_BASE.format(pid=project.id) + "/alpha",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        assert "deleted successfully" in resp.json()["message"]

        test_db.expire_all()
        refreshed = test_db.query(Project).filter(Project.id == project.id).first()
        gc = refreshed.generation_config
        assert "alpha" not in gc.get("prompt_structures", {})
        assert "alpha" not in gc["selected_configuration"]["active_structures"]


# ===========================================================================
# dashboard.py
# ===========================================================================


@pytest.mark.integration
class TestDashboardStats:
    def test_live_fallback_counts_real_rows(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        """With an empty project_summaries table, /stats falls back to the
        live counters. Seed a task + a real annotation + a parsed generation
        and assert each surfaces."""
        project = _make_project(test_db, test_users[0], test_org)
        task = Task(
            id=_uid(),
            project_id=project.id,
            inner_id=1,
            data={"text": "dash task"},
            created_by=test_users[0].id,
        )
        test_db.add(task)
        test_db.flush()

        # Real (non-cancelled, non-empty result) annotation.
        test_db.add(
            Annotation(
                id=_uid(),
                task_id=task.id,
                project_id=project.id,
                completed_by=test_users[0].id,
                result=[{"value": "x"}],
                was_cancelled=False,
            )
        )
        # Parsed generation (parse_status == "success") under a parent.
        rg = ResponseGeneration(
            id=_uid(),
            project_id=project.id,
            task_id=task.id,
            model_id="gpt-4",
            status="completed",
            created_by=test_users[0].id,
        )
        test_db.add(rg)
        test_db.flush()
        test_db.add(
            Generation(
                id=_uid(),
                generation_id=rg.id,
                task_id=task.id,
                model_id="gpt-4",
                case_data="{}",
                response_content="answer",
                status="completed",
                parse_status="success",
            )
        )
        test_db.commit()

        resp = client.get(
            "/api/dashboard/stats",
            headers={
                **auth_headers["admin"],
                "X-Organization-Context": test_org.id,
            },
        )
        assert resp.status_code == 200
        stats = resp.json()
        assert stats["project_count"] >= 1
        assert stats["task_count"] >= 1
        assert stats["annotation_count"] >= 1
        assert stats["projects_with_generations"] >= 1

    def test_no_accessible_projects_all_zero(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        """A non-superadmin in private context with no own private projects
        has an empty accessible set → the all-zeros short-circuit."""
        resp = client.get(
            "/api/dashboard/stats",
            headers={
                **auth_headers["annotator"],
                "X-Organization-Context": "private",
            },
        )
        assert resp.status_code == 200
        stats = resp.json()
        assert stats["project_count"] == 0
        assert stats["task_count"] == 0
        assert stats["annotation_count"] == 0
        assert stats["projects_with_generations"] == 0
        assert stats["projects_with_evaluations"] == 0


# ===========================================================================
# file_uploads.py
# ===========================================================================


def _make_upload(db, owner_id, *, task_id=None, storage_key=None, name="f.txt"):
    rec = UploadedData(
        id=_uid(),
        name=name,
        original_filename=name,
        file_path="legacy/path",
        size=10,
        format="txt",
        task_id=task_id,
        uploaded_by=owner_id,
        storage_key=storage_key,
        storage_url="http://example/url" if storage_key is None else None,
        storage_type="local",
    )
    db.add(rec)
    db.flush()
    return rec


@pytest.mark.integration
class TestFileUploadsList:
    def test_empty_list(self, client, auth_headers, test_users):
        resp = client.get("/api/files/", headers=auth_headers["admin"])
        assert resp.status_code == 200
        assert resp.json() == []

    def test_lists_only_own_files_and_task_filter(
        self, client, auth_headers, test_db, test_users
    ):
        admin = test_users[0]
        # admin's files: one with a task_id, one without.
        f_task = _make_upload(test_db, admin.id, task_id="task-xyz", name="a.txt")
        _make_upload(test_db, admin.id, task_id=None, name="b.txt")
        # contributor's file should never appear for admin.
        _make_upload(test_db, test_users[1].id, name="other.txt")
        test_db.commit()

        # No filter → admin's two files only.
        resp = client.get("/api/files/", headers=auth_headers["admin"])
        assert resp.status_code == 200
        ids = {r["id"] for r in resp.json()}
        assert f_task.id in ids
        assert len(resp.json()) == 2

        # task_id filter narrows to the one tagged file.
        resp2 = client.get("/api/files/?task_id=task-xyz", headers=auth_headers["admin"])
        assert resp2.status_code == 200
        assert {r["id"] for r in resp2.json()} == {f_task.id}
        assert resp2.json()[0]["task_id"] == "task-xyz"


@pytest.mark.integration
class TestFileUploadsDownloadDelete:
    def test_download_unknown_file_404(self, client, auth_headers):
        resp = client.get(
            f"/api/files/{_uid()}/download",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "File not found"

    def test_download_not_owned_404(
        self, client, auth_headers, test_db, test_users
    ):
        """A file owned by another user is invisible (the ownership filter
        excludes it) → 404."""
        rec = _make_upload(test_db, test_users[1].id, storage_key=None)
        test_db.commit()

        resp = client.get(
            f"/api/files/{rec.id}/download",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404

    def test_delete_unknown_file_404(self, client, auth_headers):
        resp = client.delete(
            f"/api/files/{_uid()}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "File not found"

    def test_delete_owned_record_persists(
        self, client, auth_headers, test_db, test_users
    ):
        """A record with no storage_key deletes cleanly (no MinIO call)."""
        rec = _make_upload(test_db, test_users[0].id, storage_key=None)
        test_db.commit()
        rec_id = rec.id

        resp = client.delete(
            f"/api/files/{rec_id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        assert "deleted successfully" in resp.json()["message"]

        test_db.expire_all()
        gone = test_db.query(UploadedData).filter(UploadedData.id == rec_id).first()
        assert gone is None


# ===========================================================================
# evaluations/status.py
# ===========================================================================

_EVAL_BASE = "/api/evaluations"


def _make_eval_run(db, project, creator, *, status="completed", model_id="gpt-4", metrics=None):
    er = EvaluationRun(
        id=_uid(),
        project_id=project.id,
        model_id=model_id,
        evaluation_type_ids=["accuracy"],
        metrics=metrics if metrics is not None else {"accuracy": 0.9},
        status=status,
        samples_evaluated=7,
        eval_metadata={"type": "automated"},
        created_by=creator.id,
    )
    db.add(er)
    db.flush()
    return er


@pytest.mark.integration
class TestEvaluationStatusEndpoint:
    def test_status_not_found_404(self, client, auth_headers, test_org):
        missing = _uid()
        resp = client.get(
            f"{_EVAL_BASE}/evaluation/status/{missing}",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 404
        assert missing in resp.json()["detail"]

    def test_status_inaccessible_project_403(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        other_org = Organization(
            id=_uid(),
            name="Outsider Status Org",
            slug=f"outsider-status-{uuid.uuid4().hex[:6]}",
            display_name="Outsider Status Org",
        )
        test_db.add(other_org)
        test_db.flush()
        hidden = _make_project(test_db, test_users[0], other_org)
        er = _make_eval_run(test_db, hidden, test_users[0])
        test_db.commit()

        resp = client.get(
            f"{_EVAL_BASE}/evaluation/status/{er.id}",
            headers={
                **auth_headers["contributor"],
                "X-Organization-Context": other_org.id,
            },
        )
        assert resp.status_code == 403
        assert "access" in resp.json()["detail"].lower()

    def test_status_happy_path(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        er = _make_eval_run(
            test_db, project, test_users[0], status="failed",
        )
        er.error_message = "boom"
        test_db.commit()

        resp = client.get(
            f"{_EVAL_BASE}/evaluation/status/{er.id}",
            headers=_ctx(auth_headers, "admin", test_org),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == er.id
        assert body["status"] == "failed"
        assert body["message"] == "boom"


@pytest.mark.integration
class TestEvaluationListEndpoint:
    def test_superadmin_sees_run(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        project = _make_project(test_db, test_users[0], test_org)
        er = _make_eval_run(test_db, project, test_users[0])
        test_db.commit()

        resp = client.get(
            f"{_EVAL_BASE}/",
            headers={
                **auth_headers["admin"],
                "X-Organization-Context": test_org.id,
            },
        )
        assert resp.status_code == 200
        ids = {r["id"] for r in resp.json()}
        assert er.id in ids
        match = next(r for r in resp.json() if r["id"] == er.id)
        assert match["project_id"] == project.id
        assert match["samples_evaluated"] == 7

    def test_empty_accessible_returns_empty_list(
        self, client, auth_headers, test_db, test_users, test_org
    ):
        """A non-superadmin in private context with no own private projects
        gets the empty-accessible short-circuit (empty list)."""
        # Seed a run in an org project so something exists but is out of scope.
        project = _make_project(test_db, test_users[0], test_org)
        _make_eval_run(test_db, project, test_users[0])
        test_db.commit()

        resp = client.get(
            f"{_EVAL_BASE}/",
            headers={
                **auth_headers["annotator"],
                "X-Organization-Context": "private",
            },
        )
        assert resp.status_code == 200
        assert resp.json() == []


@pytest.mark.integration
class TestEvaluationTypesEndpoint:
    def test_filter_by_category(
        self, client, auth_headers, test_db, test_users
    ):
        # Two active types in different categories.
        test_db.add(
            EvaluationType(
                id=f"cat-a-{uuid.uuid4().hex[:6]}",
                name="Cat A Metric",
                category="classification",
                higher_is_better=True,
                is_active=True,
                applicable_project_types=["text_classification"],
            )
        )
        target_id = f"cat-b-{uuid.uuid4().hex[:6]}"
        test_db.add(
            EvaluationType(
                id=target_id,
                name="Cat B Metric",
                category="qa_branch_unique",
                higher_is_better=True,
                is_active=True,
                applicable_project_types=["qa_reasoning"],
            )
        )
        test_db.commit()

        resp = client.get(
            f"{_EVAL_BASE}/evaluation-types?category=qa_branch_unique",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        ids = {t["id"] for t in resp.json()}
        assert ids == {target_id}

    def test_get_inactive_type_404(
        self, client, auth_headers, test_db, test_users
    ):
        inactive_id = f"inactive-{uuid.uuid4().hex[:6]}"
        test_db.add(
            EvaluationType(
                id=inactive_id,
                name="Inactive Metric",
                category="classification",
                higher_is_better=True,
                is_active=False,
                applicable_project_types=[],
            )
        )
        test_db.commit()

        resp = client.get(
            f"{_EVAL_BASE}/evaluation-types/{inactive_id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404
        assert inactive_id in resp.json()["detail"]

    def test_get_active_type_happy_path(
        self, client, auth_headers, test_db, test_users
    ):
        active_id = f"active-{uuid.uuid4().hex[:6]}"
        test_db.add(
            EvaluationType(
                id=active_id,
                name="Active Metric",
                category="classification",
                higher_is_better=False,
                is_active=True,
                value_range={"min": 0, "max": 1},
                applicable_project_types=["text_classification"],
            )
        )
        test_db.commit()

        resp = client.get(
            f"{_EVAL_BASE}/evaluation-types/{active_id}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == active_id
        assert body["higher_is_better"] is False
        assert body["value_range"] == {"min": 0, "max": 1}
