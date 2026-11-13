"""The typed contract of the project import API: map targets checked at
request time, coded job errors, the documented schema, and the merge
preview (a dry run of the merge that writes nothing).

The worker side of a merge is covered in
``tests/routers/projects/test_export_import_roundtrip.py``.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import Generation, ImportJob, JobStatus, LLMModel, ResponseGeneration, User
from project_models import Project, Task


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user: User):
    app.dependency_overrides[require_user] = lambda: AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    try:
        yield
    finally:
        app.dependency_overrides.pop(require_user, None)


def _user(**kw) -> User:
    return User(
        id=_uid(),
        username=f"ic-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Contract",
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
        **kw,
    )


def _model(model_id: str, name: str) -> LLMModel:
    return LLMModel(
        id=model_id,
        name=name,
        provider="custom",
        model_type="chat",
        capabilities=["text_generation"],
        is_official=False,
        is_public=True,
        base_url="http://gpu.example.org:40001/v1",
        endpoint_model_name=model_id,
    )


@pytest.mark.integration
class TestModelIdMapTargets:
    """Defect 2: an unknown map target used to be accepted with 202."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("project_scoped", [True, False])
    async def test_unknown_target_400_and_no_job(
        self, async_test_client, async_test_db, project_scoped
    ):
        from sqlalchemy import select

        user = _user(is_superadmin=True)
        async_test_db.add(user)
        await async_test_db.flush()
        if project_scoped:
            project = Project(
                id=_uid(), title="Map target", created_by=user.id,
                label_config='<View><Text name="text" value="$text"/></View>',
            )
            async_test_db.add(project)
            url = f"/api/projects/{project.id}/imports"
            body = {
                "object_key": f"imports/2026/11/{project.id}/x.ndjson",
                "mode": "merge",
                "model_id_map": {"custom-a": "does-not-exist"},
            }
        else:
            url = "/api/projects/project-imports"
            body = {
                "object_key": f"imports/2026/11/{user.id}/x.ndjson",
                "model_id_map": {"custom-a": "does-not-exist"},
            }
        await async_test_db.commit()

        with _as_user(user), patch(
            "routers.projects.import_export.send_task_safe",
            return_value=MagicMock(id="celery"),
        ) as mock_send:
            resp = await async_test_client.post(url, json=body)
        assert resp.status_code == 400, resp.text
        detail = resp.json()["detail"]
        assert detail["code"] == "unknown_model_id_map_target"
        assert detail["model_ids"] == ["does-not-exist"]
        mock_send.assert_not_called()
        jobs = (
            await async_test_db.execute(
                select(ImportJob).where(ImportJob.requested_by == user.id)
            )
        ).scalars().all()
        assert jobs == []


@pytest.mark.integration
class TestJobErrorCode:
    """Defect 10: the code of a refused import was only inside the text."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "message,status,code",
        [
            ("409: merge_task_mismatch: Of the 5 tasks ...", 409, "merge_task_mismatch"),
            ("409: merge_unknown_models: 1 model id(s) ...", 409, "merge_unknown_models"),
            ("400: Invalid JSON format", 400, None),
            ("Instance <ImportJob> is not bound to a Session", None, None),
        ],
    )
    async def test_status_carries_error_code(
        self, async_test_client, async_test_db, message, status, code
    ):
        user = _user()
        async_test_db.add(user)
        await async_test_db.flush()
        job = ImportJob(
            id=_uid(),
            project_id=None,
            requested_by=user.id,
            object_key=f"imports/2026/11/{user.id}/x.ndjson",
            status=JobStatus.FAILED.value,
            progress=0,
            error_message=message,
        )
        async_test_db.add(job)
        await async_test_db.commit()

        with _as_user(user):
            resp = await async_test_client.get(f"/api/projects/project-imports/{job.id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["error_message"] == message
        assert body["error_status"] == status
        assert body["error_code"] == code


def test_import_bodies_are_typed_in_the_openapi_schema():
    schema = app.openapi()
    paths = schema["paths"]
    for path, model in (
        ("/api/projects/project-imports", "FullImportJobRequest"),
        ("/api/projects/{project_id}/imports", "ProjectImportJobRequest"),
    ):
        post = paths[path]["post"]
        ref = post["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        assert ref.endswith(f"/{model}")
        for status in ("400", "403", "404"):
            assert status in post["responses"], (path, status)
        # A malformed body answers 400 (Coded400Route), never 422.
        assert "422" not in post["responses"], path
        assert "x-benger-coded-400" not in post, path
    props = schema["components"]["schemas"]["FullImportJobRequest"]["properties"]
    assert {"object_key", "model_id_map", "organization_id", "organization_group_id"} <= set(props)
    status_props = schema["components"]["schemas"]["ImportJobStatus"]["properties"]
    assert {"error_code", "error_status", "result", "project_id"} <= set(status_props)


def test_the_full_api_reference_spec_lists_no_422_for_the_import_bodies():
    """GET /api/v1/reference/openapi.json, the spec access-key clients read,
    documents the same 400 contract as /openapi.json."""
    from routers.v1.reference import build_reference_openapi

    paths = build_reference_openapi(app, platform_only=True)["paths"]
    for path in (
        "/api/projects/project-imports",
        "/api/projects/{project_id}/imports",
    ):
        post = paths[path]["post"]
        assert "400" in post["responses"], path
        assert "422" not in post["responses"], path
        assert "x-benger-coded-400" not in post, path


def _seed_preview_project(db):
    """A project with one task and one generation of a model unknown here,
    exported, after which the generation is removed again: merging that
    export would add it back."""
    from routers.projects._export_stream import stream_export_ndjson

    user = _user(is_superadmin=True)
    db.add(user)
    db.flush()
    project = Project(
        id=_uid(), title="Preview", created_by=user.id,
        label_config='<View><Text name="text" value="$text"/></View>',
    )
    db.add(project)
    db.flush()
    task = Task(id=_uid(), project_id=project.id, inner_id=1, data={"text": "Q"}, created_by=user.id)
    db.add(task)
    db.flush()
    job = ResponseGeneration(
        id=_uid(), project_id=project.id, task_id=task.id, model_id="custom-elsewhere",
        status="completed", created_by=user.id,
    )
    db.add(job)
    db.flush()
    gen = Generation(
        id=_uid(), generation_id=job.id, task_id=task.id, model_id="custom-elsewhere",
        case_data="{}", response_content="An answer", status="completed",
    )
    db.add(gen)
    db.commit()
    export = "".join(stream_export_ndjson(db, project.id)).encode("utf-8")
    db.delete(gen)
    db.delete(job)
    db.add(_model("custom-here", "Same model here"))
    db.commit()
    return user, project, export


@pytest.mark.integration
class TestMergePreview:
    """Recommendation 2: a dry run of the merge that names every model id of
    the file and whether it exists here, for the merge dialog's model map.
    It runs as a dry-run merge job on the import worker."""

    def _preview(self, db, project, export, user, model_id_map=None):
        import io

        from routers.projects._import_stream import run_merge_import

        return run_merge_import(
            db, project.id, io.BytesIO(export), user.id,
            model_id_map=model_id_map, dry_run=True,
        )["statistics"]

    def test_lists_unknown_models_and_writes_nothing(self, test_db):
        user, project, export = _seed_preview_project(test_db)
        stats = self._preview(test_db, project, export, user)
        assert stats["dry_run"] is True
        assert stats["matched_tasks"] == 1
        assert stats["added_counts"]["generations"] == 1
        assert stats["unknown_models"] == ["custom-elsewhere"]
        (model,) = stats["models"]
        assert model["source_model_id"] == "custom-elsewhere"
        assert model["known"] is False and model["rows_added"] == 1
        assert {"id": "custom-here", "name": "Same model here", "is_custom": True} in stats[
            "available_models"
        ]
        test_db.expire_all()
        assert test_db.query(Generation).filter(Generation.task_id.in_(
            [t.id for t in test_db.query(Task).filter(Task.project_id == project.id)]
        )).count() == 0

    def test_a_mapped_model_is_known(self, test_db):
        user, project, export = _seed_preview_project(test_db)
        stats = self._preview(
            test_db, project, export, user, {"custom-elsewhere": "custom-here"}
        )
        assert stats["unknown_models"] == []
        (model,) = stats["models"]
        assert model == {
            "source_model_id": "custom-elsewhere",
            "model_id": "custom-here",
            "mapped": True,
            "known": True,
            "name": "Same model here",
            "rows_added": 1,
            "rows_present": 0,
        }

    def test_unrelated_file_is_a_coded_409(self, test_db):
        from routers.projects._import_stream import ImportValidationError

        user, project, export = _seed_preview_project(test_db)
        other = Project(id=_uid(), title="Other", created_by=user.id)
        test_db.add(other)
        test_db.add(Task(id=_uid(), project_id=other.id, inner_id=1, data={"text": "Else"}))
        test_db.commit()
        with pytest.raises(ImportValidationError) as raised:
            self._preview(test_db, other, export, user)
        assert raised.value.status_code == 409
        assert raised.value.code == "merge_task_mismatch"


@pytest.mark.integration
class TestDryRunJob:
    """POST .../imports with dry_run enqueues the merge preview on the import
    worker instead of running it on the API."""

    async def _post(self, client, db, body):
        user = _user(is_superadmin=True)
        db.add(user)
        await db.flush()
        project = Project(
            id=_uid(), title="Dry run", created_by=user.id,
            label_config='<View><Text name="text" value="$text"/></View>',
        )
        db.add(project)
        await db.commit()
        with _as_user(user), patch(
            "routers.projects.import_export.send_task_safe",
            return_value=MagicMock(id="celery"),
        ) as mock_send:
            resp = await client.post(
                f"/api/projects/{project.id}/imports",
                json={"object_key": f"imports/2026/11/{project.id}/copy.ndjson", **body},
            )
        return resp, mock_send

    @pytest.mark.asyncio
    async def test_dry_run_enqueues_a_merge_preview(self, async_test_client, async_test_db):
        resp, mock_send = await self._post(
            async_test_client, async_test_db, {"mode": "merge", "dry_run": True}
        )
        assert resp.status_code == 202, resp.text
        assert mock_send.call_args.args[0] == "tasks.import_project"
        assert mock_send.call_args.kwargs["kwargs"] == {"mode": "merge", "dry_run": True}

    @pytest.mark.asyncio
    async def test_dry_run_needs_merge_mode(self, async_test_client, async_test_db):
        resp, mock_send = await self._post(
            async_test_client, async_test_db, {"dry_run": True}
        )
        assert resp.status_code == 400, resp.text
        assert "dry_run" in resp.json()["detail"]
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_malformed_dry_run_is_a_400(self, async_test_client, async_test_db):
        resp, mock_send = await self._post(
            async_test_client, async_test_db, {"mode": "merge", "dry_run": "maybe"}
        )
        assert resp.status_code == 400, resp.text
        assert "dry_run" in resp.json()["detail"]
        mock_send.assert_not_called()
