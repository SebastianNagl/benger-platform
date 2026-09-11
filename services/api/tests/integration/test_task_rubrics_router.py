"""Integration tests for the task-rubrics router: stateless parse, create,
edit (in place vs clone-on-edit), activate / archive and the legacy list shape.

Async pattern (see tests/routers/test_grading_feedback.py): seed via
``async_test_db``, drive the real ASGI app via ``async_test_client`` and
override ``require_user`` with ``_as_user`` so no JWT round-trip is needed.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from models import EvaluationJudgeRun, EvaluationRun, TaskEvaluation, User
from project_models import Project, Task, TaskRubric
from services.rubric_import import MAX_RUBRIC_FILE_BYTES
from tests.fixtures.rubric_files import colleague_sample_xlsx


@contextmanager
def _as_user(db_user):
    from auth_module.dependencies import require_user
    from auth_module.models import User as AuthUser
    from main import app

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


async def _make_user(db, *, superadmin=False) -> User:
    u = User(
        id=str(uuid.uuid4()),
        username=f"tr-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        name="Rubric Tester",
        is_superadmin=superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_project(db, owner, *, title="Polizeirecht Übungsklausur") -> Project:
    p = Project(
        id=str(uuid.uuid4()),
        title=title,
        created_by=owner.id,
        is_private=True,
        kind="exam",
        origin="student",
    )
    db.add(p)
    await db.flush()
    return p


async def _make_task(db, project, *, inner_id=1) -> Task:
    t = Task(
        id=str(uuid.uuid4()),
        project_id=project.id,
        data={"sachverhalt": "S", "musterloesung": "M"},
        inner_id=inner_id,
    )
    db.add(t)
    await db.flush()
    return t


def _structure():
    return {
        "version": 1,
        "nodes": [
            {"id": "x1", "level": 0, "kind": "section", "label": "A.", "title": "Zulässigkeit", "note": "insgesamt 70 BE"},
            {"id": "x2", "level": 1, "kind": "step", "label": "I.", "title": "Eröffnung des Verwaltungsrechtswegs", "max_score": 70, "key": "client-key"},
            {"id": "x3", "level": 0, "kind": "section", "label": "B.", "title": "Begründetheit"},
            {"id": "x4", "level": 1, "kind": "step", "label": "I.", "title": "Obersatz", "max_score": 2.5, "emphasis": "schwerpunkt", "hints": ["Vergangenheitsform!"]},
        ],
    }


SCALE_72 = {
    "unit": "BE",
    "thresholds": [8, 15, 22, 29, 32, 35, 38, 41, 44, 47, 50, 53, 56, 59, 62, 65, 68, 71],
    "rounding": "floor",
    "pass_grade": 4,
}


async def _seed_rubric(db, project, task, *, status="candidate", source="llm", structure=None, metadata=None):
    r = TaskRubric(
        id=str(uuid.uuid4()),
        task_id=task.id,
        project_id=project.id,
        title="Vorhandener Bogen",
        criteria={"s01_alt": {"name": "Alt", "rubric": "r", "max_score": 100}},
        total_points=100.0,
        structure=structure,
        source=source,
        status=status,
        generator_model_id="gpt-5.4" if source != "human" else None,
        generation_metadata=metadata,
    )
    db.add(r)
    await db.flush()
    return r


async def _seed_grading(db, project, task, rubric, owner):
    run = EvaluationRun(
        id=str(uuid.uuid4()), project_id=project.id, model_id="immediate",
        evaluation_type_ids=[], metrics={}, created_by=owner.id,
    )
    db.add(run)
    await db.flush()
    jr = EvaluationJudgeRun(id=str(uuid.uuid4()), evaluation_id=run.id, judge_model_id="gpt-5-mini")
    db.add(jr)
    await db.flush()
    te = TaskEvaluation(
        id=str(uuid.uuid4()), evaluation_id=run.id, judge_run_id=jr.id, task_id=task.id,
        field_name="loesung", answer_type="long_text", ground_truth="M", prediction="P",
        metrics={
            "llm_judge_rubric": {
                "value": 0.8, "method": "llm_judge_rubric", "error": None,
                "details": {"rubric_id": rubric.id, "scores": {}, "total_score": 80, "total_max": 100},
            },
            "raw_score": 0.8,
        },
        passed=True,
    )
    db.add(te)
    await db.flush()
    return te


async def _reload_rubric(db, rubric_id):
    return (await db.execute(select(TaskRubric).where(TaskRubric.id == rubric_id))).scalar_one()


# ---------------------------------------------------------------------------
# parse
# ---------------------------------------------------------------------------


class TestParse:
    @pytest.mark.asyncio
    async def test_parse_xlsx_returns_structure_scale_and_rendering(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        with _as_user(user):
            resp = await async_test_client.post(
                "/api/task-rubrics/parse",
                files={"file": ("Korrekturbogen.xlsx", colleague_sample_xlsx(), "application/octet-stream")},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["source_format"] == "xlsx"
        assert body["total_points"] == 100
        assert body["grade_scale"]["thresholds"][:4] == [10, 20, 30, 40]
        assert body["title"] == "Korrekturbogen"
        assert body["structure"]["version"] == 1 and len(body["structure"]["nodes"]) == 27
        assert set(body["criteria"]) == {n["key"] for n in body["structure"]["nodes"] if n["kind"] == "step"}
        assert body["rendered_text"].startswith("BEWERTUNGSBOGEN: Korrekturbogen (insgesamt 100 BE")
        assert "NOTENSCHLÜSSEL" in body["rendered_text"]
        assert {w["code"] for w in body["warnings"]} >= {"subtotal_mismatch", "empty_section"}

    @pytest.mark.asyncio
    async def test_parse_unsupported_type_422(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        with _as_user(user):
            resp = await async_test_client.post(
                "/api/task-rubrics/parse", files={"file": ("bogen.pdf", b"%PDF-1.4", "application/pdf")}
            )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "unsupported_type"
        assert resp.json()["detail"]["warnings"] == []

    @pytest.mark.asyncio
    async def test_parse_corrupt_422(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        with _as_user(user):
            resp = await async_test_client.post(
                "/api/task-rubrics/parse", files={"file": ("bogen.xlsx", b"not a zip", "application/octet-stream")}
            )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "corrupt_file"

    @pytest.mark.asyncio
    async def test_parse_oversize_413(self, async_test_client, async_test_db):
        user = await _make_user(async_test_db)
        with _as_user(user):
            resp = await async_test_client.post(
                "/api/task-rubrics/parse",
                files={"file": ("bogen.xlsx", b"x" * (MAX_RUBRIC_FILE_BYTES + 1), "application/octet-stream")},
            )
        assert resp.status_code == 413

    @pytest.mark.asyncio
    async def test_parse_requires_authentication(self, async_test_client):
        resp = await async_test_client.post(
            "/api/task-rubrics/parse", files={"file": ("bogen.xlsx", b"x", "application/octet-stream")}
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


class TestCreate:
    @pytest.mark.asyncio
    async def test_create_candidate_from_structure(self, async_test_client, async_test_db):
        owner = await _make_user(async_test_db)
        project = await _make_project(async_test_db, owner)
        task = await _make_task(async_test_db, project)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/task-rubrics",
                json={"task_id": task.id, "title": " Korrekturbogen ", "structure": _structure(), "grade_scale": SCALE_72},
            )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["source"] == "human" and body["status"] == "candidate"
        assert body["total_points"] == 72.5
        assert body["title"] == "Korrekturbogen"
        assert body["created_by"] == owner.id
        steps = [n for n in body["structure"]["nodes"] if n["kind"] == "step"]
        # keys regenerated server-side (client key ignored), ids normalized
        assert [s["key"] for s in steps] == ["s01_eroeffnung_des_verwaltungsrechtswegs", "s02_obersatz"]
        assert [n["id"] for n in body["structure"]["nodes"]] == ["n1", "n2", "n3", "n4"]
        # JSONB does not keep key order (the sNN_ ordinal prefix is the sort key)
        assert set(body["criteria"]) == {"s01_eroeffnung_des_verwaltungsrechtswegs", "s02_obersatz"}
        assert body["criteria"]["s02_obersatz"]["max_score"] == 2.5
        assert "Schwerpunkt der Klausur" in body["criteria"]["s02_obersatz"]["rubric"]
        assert body["grade_scale"] == SCALE_72

        rubric = await _reload_rubric(async_test_db, body["id"])
        assert rubric.total_points == 72.5 and rubric.status == "candidate"
        # not activated → no task-data mirror
        await async_test_db.refresh(task)
        assert "bewertungsbogen" not in (task.data or {})

    @pytest.mark.asyncio
    async def test_create_and_activate_demotes_and_mirrors(self, async_test_client, async_test_db):
        owner = await _make_user(async_test_db)
        project = await _make_project(async_test_db, owner)
        task = await _make_task(async_test_db, project)
        previous = await _seed_rubric(async_test_db, project, task, status="active")
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/task-rubrics",
                json={"task_id": task.id, "title": "Neu", "structure": _structure(), "activate": True},
            )
        assert resp.status_code == 201, resp.text
        assert resp.json()["status"] == "active"
        assert resp.json()["grade_scale"] is None
        assert (await _reload_rubric(async_test_db, previous.id)).status == "candidate"
        await async_test_db.refresh(task)
        mirror = task.data["bewertungsbogen"]
        assert mirror.startswith("BEWERTUNGSBOGEN: Neu (insgesamt 72.5 BE; halbe BE zulässig)")
        assert "[Schlüssel: s02_obersatz]" in mirror
        assert "NOTENSCHLÜSSEL" in mirror  # the mirror carries the (default) scale
        assert task.data["sachverhalt"] == "S"

    @pytest.mark.asyncio
    async def test_create_invalid_structure_422(self, async_test_client, async_test_db):
        owner = await _make_user(async_test_db)
        project = await _make_project(async_test_db, owner)
        task = await _make_task(async_test_db, project)
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/task-rubrics",
                json={"task_id": task.id, "structure": {"version": 1, "nodes": [
                    {"id": "a", "level": 0, "kind": "step", "title": "x", "max_score": 0.25},
                ]}},
            )
        assert resp.status_code == 422
        assert resp.json()["detail"].startswith("Invalid Bewertungsbogen: ")
        assert "multiple of 0.5" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_scale_above_total_422(self, async_test_client, async_test_db):
        owner = await _make_user(async_test_db)
        project = await _make_project(async_test_db, owner)
        task = await _make_task(async_test_db, project)
        await async_test_db.commit()
        too_high = {**SCALE_72, "thresholds": SCALE_72["thresholds"][:-1] + [90]}
        with _as_user(owner):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/task-rubrics",
                json={"task_id": task.id, "structure": _structure(), "grade_scale": too_high},
            )
        assert resp.status_code == 422
        assert "exceeds the total" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_task_from_other_project_404(self, async_test_client, async_test_db):
        owner = await _make_user(async_test_db)
        project = await _make_project(async_test_db, owner)
        other = await _make_project(async_test_db, owner, title="Other")
        foreign_task = await _make_task(async_test_db, other)
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/task-rubrics",
                json={"task_id": foreign_task.id, "structure": _structure()},
            )
        assert resp.status_code == 404
        with _as_user(owner):
            resp = await async_test_client.post(
                "/api/projects/does-not-exist/task-rubrics",
                json={"task_id": foreign_task.id, "structure": _structure()},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_by_viewer_403(self, async_test_client, async_test_db):
        owner = await _make_user(async_test_db)
        viewer = await _make_user(async_test_db)
        project = await _make_project(async_test_db, owner)
        task = await _make_task(async_test_db, project)
        await async_test_db.commit()
        with _as_user(viewer):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/task-rubrics",
                json={"task_id": task.id, "structure": _structure()},
            )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# edit
# ---------------------------------------------------------------------------


class TestUpdate:
    @pytest.mark.asyncio
    async def test_edit_unreferenced_rubric_in_place(self, async_test_client, async_test_db):
        owner = await _make_user(async_test_db)
        project = await _make_project(async_test_db, owner)
        task = await _make_task(async_test_db, project)
        rubric = await _seed_rubric(
            async_test_db, project, task, status="active", source="llm",
            metadata={"rendered_text": "BEWERTUNGSBOGEN (100 Rohpunkte)", "contract_version": 3},
        )
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.put(
                f"/api/projects/{project.id}/task-rubrics/{rubric.id}",
                json={"structure": _structure(), "title": "Bearbeitet"},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == rubric.id and body["replaced_rubric_id"] is None
        assert body["source"] == "llm_edited"
        assert body["total_points"] == 72.5
        assert set(body["criteria"]) == {"s01_eroeffnung_des_verwaltungsrechtswegs", "s02_obersatz"}
        assert "rendered_text" not in body["generation_metadata"]
        assert body["generation_metadata"]["rendered_text_invalidated_by_edit"] is True
        assert body["generation_metadata"]["contract_version"] == 3
        assert body["title"] == "Bearbeitet"
        await async_test_db.refresh(task)
        assert task.data["bewertungsbogen"].startswith("BEWERTUNGSBOGEN: Bearbeitet")

    @pytest.mark.asyncio
    async def test_edit_referenced_rubric_clones(self, async_test_client, async_test_db):
        owner = await _make_user(async_test_db)
        project = await _make_project(async_test_db, owner)
        task = await _make_task(async_test_db, project)
        rubric = await _seed_rubric(async_test_db, project, task, status="active", source="llm",
                                    metadata={"rendered_text": "R", "contract_version": 3})
        grading = await _seed_grading(async_test_db, project, task, rubric, owner)
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.put(
                f"/api/projects/{project.id}/task-rubrics/{rubric.id}",
                json={"structure": _structure(), "grade_scale": SCALE_72},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] != rubric.id
        assert body["replaced_rubric_id"] == rubric.id
        assert body["status"] == "active" and body["source"] == "llm_edited"
        assert body["generation_metadata"] == {"cloned_from": rubric.id, "contract_version": 3}
        assert body["generator_model_id"] == "gpt-5.4"
        assert body["grade_scale"] == SCALE_72 and body["total_points"] == 72.5
        assert body["created_by"] == owner.id

        old = await _reload_rubric(async_test_db, rubric.id)
        assert old.status == "archived"
        assert old.generation_metadata["superseded_by"] == body["id"]
        assert old.generation_metadata["rendered_text"] == "R"  # untouched
        assert old.criteria == {"s01_alt": {"name": "Alt", "rubric": "r", "max_score": 100}}
        # the grading row still points at the old instrument
        await async_test_db.refresh(grading)
        assert grading.metrics["llm_judge_rubric"]["details"]["rubric_id"] == rubric.id
        # exactly one active rubric on the task, and the mirror follows the clone
        active = (await async_test_db.execute(
            select(TaskRubric).where(TaskRubric.task_id == task.id, TaskRubric.status == "active")
        )).scalars().all()
        assert [r.id for r in active] == [body["id"]]
        await async_test_db.refresh(task)
        assert "[Schlüssel: s02_obersatz]" in task.data["bewertungsbogen"]
        assert "8 BE" in task.data["bewertungsbogen"]  # custom scale rendered in the mirror

    @pytest.mark.asyncio
    async def test_noop_edit_of_referenced_rubric_does_not_clone(self, async_test_client, async_test_db):
        owner = await _make_user(async_test_db)
        project = await _make_project(async_test_db, owner)
        task = await _make_task(async_test_db, project)
        rubric = await _seed_rubric(async_test_db, project, task, status="active", source="human")
        await _seed_grading(async_test_db, project, task, rubric, owner)
        await async_test_db.commit()

        with _as_user(owner):
            first = await async_test_client.put(
                f"/api/projects/{project.id}/task-rubrics/{rubric.id}", json={"structure": _structure()},
            )
            assert first.status_code == 200 and first.json()["id"] != rubric.id  # legacy → clone
            clone_id = first.json()["id"]
            await _seed_grading(async_test_db, project, task, await _reload_rubric(async_test_db, clone_id), owner)
            await async_test_db.commit()
            second = await async_test_client.put(
                f"/api/projects/{project.id}/task-rubrics/{clone_id}",
                json={"structure": _structure(), "title": "Nur Titel"},
            )
        assert second.status_code == 200, second.text
        assert second.json()["id"] == clone_id and second.json()["replaced_rubric_id"] is None
        assert second.json()["title"] == "Nur Titel"

    @pytest.mark.asyncio
    async def test_grade_scale_null_clears_and_omitted_keeps(self, async_test_client, async_test_db):
        owner = await _make_user(async_test_db)
        project = await _make_project(async_test_db, owner)
        task = await _make_task(async_test_db, project)
        await async_test_db.commit()
        with _as_user(owner):
            created = await async_test_client.post(
                f"/api/projects/{project.id}/task-rubrics",
                json={"task_id": task.id, "structure": _structure(), "grade_scale": SCALE_72},
            )
            rid = created.json()["id"]
            kept = await async_test_client.put(
                f"/api/projects/{project.id}/task-rubrics/{rid}", json={"title": "T"}
            )
            assert kept.json()["grade_scale"] == SCALE_72
            cleared = await async_test_client.put(
                f"/api/projects/{project.id}/task-rubrics/{rid}", json={"grade_scale": None}
            )
        assert cleared.status_code == 200
        assert cleared.json()["grade_scale"] is None
        assert (await _reload_rubric(async_test_db, rid)).grade_scale is None

    @pytest.mark.asyncio
    async def test_edit_validation_errors(self, async_test_client, async_test_db):
        owner = await _make_user(async_test_db)
        project = await _make_project(async_test_db, owner)
        task = await _make_task(async_test_db, project)
        rubric = await _seed_rubric(async_test_db, project, task)
        await async_test_db.commit()
        with _as_user(owner):
            bad = await async_test_client.put(
                f"/api/projects/{project.id}/task-rubrics/{rubric.id}",
                json={"structure": {"version": 1, "nodes": []}},
            )
            null = await async_test_client.put(
                f"/api/projects/{project.id}/task-rubrics/{rubric.id}", json={"structure": None}
            )
            missing = await async_test_client.put(
                f"/api/projects/{project.id}/task-rubrics/{uuid.uuid4()}", json={"title": "x"}
            )
        assert bad.status_code == 422 and "Invalid Bewertungsbogen" in bad.json()["detail"]
        assert null.status_code == 422 and "structure cannot be null" in null.json()["detail"]
        assert missing.status_code == 404


# ---------------------------------------------------------------------------
# activate / archive / list
# ---------------------------------------------------------------------------


class TestActivateArchiveList:
    @pytest.mark.asyncio
    async def test_activate_switches_active_and_archive_removes_mirror(self, async_test_client, async_test_db):
        owner = await _make_user(async_test_db)
        project = await _make_project(async_test_db, owner)
        task = await _make_task(async_test_db, project)
        first = await _seed_rubric(async_test_db, project, task, status="active")
        second = await _seed_rubric(async_test_db, project, task, status="candidate", source="human")
        await async_test_db.commit()

        with _as_user(owner):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/task-rubrics/{second.id}/activate"
            )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {
            "id": second.id, "task_id": task.id, "status": "active", "source": "human", "title": "Vorhandener Bogen",
        }
        assert (await _reload_rubric(async_test_db, first.id)).status == "candidate"
        await async_test_db.refresh(task)
        assert "[Schlüssel: s01_alt]" in task.data["bewertungsbogen"]

        with _as_user(owner):
            resp = await async_test_client.post(
                f"/api/projects/{project.id}/task-rubrics/{second.id}/archive"
            )
        assert resp.status_code == 200 and resp.json()["status"] == "archived"
        await async_test_db.refresh(task)
        assert "bewertungsbogen" not in task.data

    @pytest.mark.asyncio
    async def test_writes_gated_for_viewers(self, async_test_client, async_test_db):
        owner = await _make_user(async_test_db)
        viewer = await _make_user(async_test_db)
        project = await _make_project(async_test_db, owner)
        task = await _make_task(async_test_db, project)
        rubric = await _seed_rubric(async_test_db, project, task)
        await async_test_db.commit()
        with _as_user(viewer):
            activate = await async_test_client.post(f"/api/projects/{project.id}/task-rubrics/{rubric.id}/activate")
            edit = await async_test_client.put(f"/api/projects/{project.id}/task-rubrics/{rubric.id}", json={"title": "x"})
        assert activate.status_code == 403 and edit.status_code == 403

    @pytest.mark.asyncio
    async def test_list_includes_legacy_rows_with_null_structure(self, async_test_client, async_test_db):
        owner = await _make_user(async_test_db, superadmin=True)
        project = await _make_project(async_test_db, owner)
        task = await _make_task(async_test_db, project)
        legacy = await _seed_rubric(async_test_db, project, task)
        await async_test_db.commit()
        with _as_user(owner):
            resp = await async_test_client.get(f"/api/projects/{project.id}/task-rubrics", params={"task_id": task.id})
        assert resp.status_code == 200, resp.text
        (row,) = resp.json()
        assert row["id"] == legacy.id
        assert row["structure"] is None and row["grade_scale"] is None
        assert row["total_points"] == 100.0
