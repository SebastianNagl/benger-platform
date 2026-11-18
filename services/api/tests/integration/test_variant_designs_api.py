"""Variant designs through the API (CORE 2.57).

Routes under ``/api/projects/{id}/variant-designs`` (CRUD, export and import
of a design, checks, freeze), the meta and data write routes against a
design (invalid assignments 422, a duplicate cell 409, frozen designs 409),
and the canary: ``meta.variant`` never reaches a blinded caller or a v1
task read. Synthetic content only.
"""

import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import Organization, OrganizationMembership, OrganizationRole, User
from project_models import Project, ProjectOrganization, Task

pytestmark = pytest.mark.asyncio

CANARY = "CANARY-VARIANT-7f3a"
CONFIG = (
    '<View><Text name="facts_view" value="$facts"/>'
    '<TextArea name="answer" toName="facts_view"/></View>'
)
NAMES = {"claimant": "Alma Reyes", "respondent": "Bodo Lind"}

SPEC = {
    "schema_version": 1,
    "title": "Party swap",
    "unit": {"name": "case"},
    "factors": [
        {"name": "role", "type": "nominal", "levels": ["claimant", "respondent"]},
        {"name": "level", "type": "numeric", "varies": "between_units"},
    ],
    "gold": [{"name": "reference", "path": "reference"}],
    "invariance": {"fields": ["facts"], "free": ["reference"]},
}


def _uid() -> str:
    return str(uuid.uuid4())


def task_payload(unit: str, role: str, level: int = 1, *, facts=None, design="swap"):
    name = NAMES[role]
    facts = facts if facts is not None else f"{name} asks for the fence to be moved."
    at = facts.find(name)
    variant = {
        "design": design,
        "unit": unit,
        "factors": {"role": role, "level": level},
        "spans": {"facts": [[at, at + len(name)]] if at >= 0 else []},
        "provenance": {"generator": CANARY},
    }
    return {"facts": facts, "reference": 50 + level}, {"variant": variant, "tags": ["t"]}


@contextmanager
def _as_user(user: dict):
    auth_user = AuthUser(
        id=user["id"],
        username=user["username"],
        email=user["email"],
        name=user["name"],
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=user["created_at"],
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


class _Api:
    """The test client; after a refused request it rolls the shared test
    session back, as a real request's session would be discarded."""

    def __init__(self, client, db):
        self.client, self.db = client, db

    async def __call__(self, method: str, url: str, **kwargs):
        resp = await getattr(self.client, method)(url, **kwargs)
        if resp.status_code >= 400:
            await self.db.rollback()
        return resp


class _Ids(dict):
    __getattr__ = dict.__getitem__


def _user_dict(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "email": u.email,
        "name": u.name,
        "created_at": u.created_at,
    }


async def _seed_user(db, name: str) -> User:
    u = User(
        id=_uid(),
        username=f"{name}-{_uid()[:8]}@test.com",
        email=f"{name}-{_uid()[:8]}@test.com",
        name=name,
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


@pytest_asyncio.fixture(scope="function")
async def world(async_test_db):
    db = async_test_db
    admin = await _seed_user(db, "vd-admin")
    annotator = await _seed_user(db, "vd-anno")
    org = Organization(
        id=_uid(),
        name="VD Org",
        slug=f"vd-org-{_uid()[:8]}",
        display_name="VD Org",
        created_at=datetime.now(timezone.utc),
    )
    db.add(org)
    await db.flush()
    for user, role in ((admin, OrganizationRole.ORG_ADMIN), (annotator, OrganizationRole.ANNOTATOR)):
        db.add(
            OrganizationMembership(
                id=_uid(),
                user_id=user.id,
                organization_id=org.id,
                role=role,
                is_active=True,
                joined_at=datetime.now(timezone.utc),
            )
        )
    projects = []
    for title in ("VD Project", "VD Other"):
        project = Project(
            id=_uid(),
            title=f"{title} {_uid()[:6]}",
            label_config=CONFIG,
            created_by=admin.id,
            is_published=True,
            assignment_mode="open",
        )
        db.add(project)
        await db.flush()
        db.add(
            ProjectOrganization(
                id=_uid(), project_id=project.id, organization_id=org.id, assigned_by=admin.id
            )
        )
        projects.append(_Ids(id=project.id))
    await db.commit()
    return {
        "admin": _user_dict(admin),
        "annotator": _user_dict(annotator),
        "project": projects[0],
        "other": projects[1],
    }


@pytest.fixture
def api(async_test_client, async_test_db):
    return _Api(async_test_client, async_test_db)


async def _create_design(client, world, key="swap", spec=None, project=None):
    project = project or world["project"]
    with _as_user(world["admin"]):
        resp = await client.post(
            f"/api/projects/{project.id}/variant-designs",
            json={"key": key, "spec": spec or SPEC, "provenance": {"tool": "test"}},
        )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _add_tasks(db, project, units=("u1", "u2"), **kwargs):
    """Tasks of the design (ORM inserts, so the flush guard runs); returned
    as plain values that survive a session rollback."""
    tasks = []
    inner = (await db.execute(select(Task.inner_id).where(Task.project_id == project.id))).scalars().all()
    n = max(inner or [0])
    for i, unit in enumerate(units):
        for role in ("claimant", "respondent"):
            n += 1
            data, meta = task_payload(unit, role, level=i + 1, **kwargs)
            task_id = _uid()
            db.add(Task(id=task_id, project_id=project.id, inner_id=n, data=data, meta=meta))
            tasks.append(_Ids(id=task_id, data=json.loads(json.dumps(data)), meta=json.loads(json.dumps(meta))))
    await db.commit()
    return tasks


def _detail(resp):
    return resp.json()["detail"]


class TestDesignRoutes:
    async def test_create_list_get_export(self, api, async_test_client, async_test_db, world):
        created = await _create_design(async_test_client, world)
        assert created["status"] == "draft" and created["version"] == 1
        assert created["content_hash"] is None and len(created["spec_sha256"]) == 64
        await _add_tasks(async_test_db, world["project"])
        pid = world["project"].id
        with _as_user(world["admin"]):
            listing = await api("get", f"/api/projects/{pid}/variant-designs")
            one = await api("get", f"/api/projects/{pid}/variant-designs/swap")
            doc = await api("get", f"/api/projects/{pid}/variant-designs/swap/export")
        assert listing.status_code == 200, listing.text
        assert [(d["key"], d["task_count"]) for d in listing.json()["items"]] == [("swap", 4)]
        assert one.json()["task_count"] == 4
        assert doc.json()["format"] == "benger.variant_design.v1"
        assert doc.json()["spec"] == SPEC

    async def test_import_of_an_export_document(self, api, async_test_client, world):
        await _create_design(async_test_client, world)
        pid, other = world["project"].id, world["other"].id
        with _as_user(world["admin"]):
            doc = (await api("get", f"/api/projects/{pid}/variant-designs/swap/export")).json()
            imported = await api("post", f"/api/projects/{other}/variant-designs/import", json=doc)
            again = await api("post", f"/api/projects/{other}/variant-designs/import", json=doc)
            wrong = await api("post",
                f"/api/projects/{other}/variant-designs/import", json={**doc, "format": "x"}
            )
        assert imported.status_code == 201, imported.text
        assert imported.json()["spec"] == SPEC and imported.json()["project_id"] == other
        assert again.status_code == 409 and _detail(again)["code"] == "variant_design_exists"
        assert wrong.status_code == 422

    async def test_invalid_spec_and_key(self, api, async_test_client, world):
        pid = world["project"].id
        bad = json.loads(json.dumps(SPEC))
        bad["factors"][0].pop("levels")
        with _as_user(world["admin"]):
            r1 = await api("post",
                f"/api/projects/{pid}/variant-designs", json={"key": "swap", "spec": bad}
            )
            r2 = await api("post",
                f"/api/projects/{pid}/variant-designs", json={"key": "bad key", "spec": SPEC}
            )
        assert r1.status_code == 422
        assert _detail(r1)["code"] == "variant_design_invalid"
        assert any("needs levels" in p["message"] for p in _detail(r1)["problems"])
        assert r2.status_code == 422 and _detail(r2)["problems"][0]["path"] == "/key"

    async def test_update_spec_versions_and_guards_existing_tasks(
        self, api, async_test_client, async_test_db, world
    ):
        await _create_design(async_test_client, world)
        await _add_tasks(async_test_db, world["project"])
        url = f"/api/projects/{world['project'].id}/variant-designs/swap"
        wider = json.loads(json.dumps(SPEC))
        wider["factors"][0]["levels"].append("witness")
        narrower = json.loads(json.dumps(SPEC))
        narrower["factors"][0]["levels"] = ["claimant"]
        with _as_user(world["admin"]):
            ok = await api("put", url, json={"spec": wider, "expected_version": 1})
            stale = await api("put", url, json={"spec": SPEC, "expected_version": 1})
            misfit = await api("put", url, json={"spec": narrower})
        assert ok.status_code == 200, ok.text
        assert ok.json()["version"] == 2 and ok.json()["provenance"] == {"tool": "test"}
        assert stale.status_code == 409 and _detail(stale)["code"] == "variant_design_version_conflict"
        assert misfit.status_code == 422
        assert _detail(misfit)["code"] == "variant_design_tasks_misfit"
        assert len(_detail(misfit)["problems"]) == 2  # the two respondent tasks

    async def test_update_spec_derives_the_cells_again(
        self, api, async_test_client, async_test_db, world
    ):
        await _create_design(async_test_client, world)
        tasks = await _add_tasks(async_test_db, world["project"])
        url = f"/api/projects/{world['project'].id}/variant-designs/swap"
        within = json.loads(json.dumps(SPEC))
        within["factors"][1] = {"name": "level", "type": "numeric", "levels": [1, 2]}
        no_cell = json.loads(json.dumps(SPEC))
        no_cell["factors"][0]["varies"] = "between_units"
        with _as_user(world["admin"]):
            ok = await api("put", url, json={"spec": within})
        assert ok.status_code == 200, ok.text
        cell = (
            await async_test_db.execute(
                text("SELECT variant_cell FROM tasks WHERE id = :id"), {"id": tasks[0].id}
            )
        ).scalar_one()
        assert cell == {"role": "claimant", "level": 1}
        with _as_user(world["admin"]):
            shared = await api("put", url, json={"spec": no_cell})
            after = await api("get", url)
        assert shared.status_code == 409, shared.text
        assert _detail(shared)["code"] == "variant_cell_duplicate"
        assert after.json()["version"] == 2

    async def test_delete_draft_only_when_unused(self, api, async_test_client, async_test_db, world):
        await _create_design(async_test_client, world)
        await _create_design(async_test_client, world, key="unused")
        await _add_tasks(async_test_db, world["project"])
        base = f"/api/projects/{world['project'].id}/variant-designs"
        with _as_user(world["admin"]):
            in_use = await api("delete", f"{base}/swap")
            gone = await api("delete", f"{base}/unused")
            missing = await api("get", f"{base}/unused")
        assert in_use.status_code == 409 and _detail(in_use)["task_count"] == 4
        assert gone.status_code == 204
        assert missing.status_code == 404

    async def test_blinded_caller_cannot_read_or_write_designs(self, api, async_test_client, world):
        await _create_design(async_test_client, world)
        base = f"/api/projects/{world['project'].id}/variant-designs"
        with _as_user(world["annotator"]):
            listing = await api("get", base)
            one = await api("get", f"{base}/swap")
            create = await api("post", base, json={"key": "x", "spec": SPEC})
        assert listing.status_code == 403
        assert one.status_code == 403
        assert create.status_code == 403


class TestChecksAndFreeze:
    async def test_check_reports_and_freeze_locks(self, api, async_test_client, async_test_db, world):
        await _create_design(async_test_client, world)
        tasks = await _add_tasks(async_test_db, world["project"])
        pid = world["project"].id
        base = f"/api/projects/{pid}/variant-designs/swap"
        with _as_user(world["admin"]):
            check = await api("post", f"{base}/check")
            frozen = await api("post", f"{base}/freeze")
            twice = await api("post", f"{base}/freeze")
            data_edit = await api("put",
                f"/api/projects/{pid}/tasks/{tasks[0].id}", json={"data": {"facts": "changed"}}
            )
            variant_edit = await api("patch",
                f"/api/projects/tasks/{tasks[0].id}/metadata",
                json={"variant": {**tasks[0].meta["variant"], "unit": "u9"}},
            )
            tags_edit = await api("patch",
                f"/api/projects/tasks/{tasks[0].id}/metadata", json={"tags": ["kept"]}
            )
            delete = await api("post",
                f"/api/projects/{pid}/tasks/bulk-delete", json={"task_ids": [tasks[1].id]}
            )
            spec_edit = await api("put", base, json={"spec": SPEC})
            drop = await api("delete", base)
        assert check.status_code == 200, check.text
        assert check.json()["report"]["ok"] is True
        assert frozen.status_code == 200, frozen.text
        design = frozen.json()["design"]
        assert design["status"] == "frozen"
        assert design["content_hash"] == check.json()["content_hash"]
        assert design["frozen_by"] == world["admin"]["id"]
        assert twice.status_code == 409
        assert data_edit.status_code == 409, data_edit.text
        assert _detail(data_edit)["code"] == "variant_design_frozen"
        assert variant_edit.status_code == 409, variant_edit.text
        assert tags_edit.status_code == 200, tags_edit.text
        assert tags_edit.json()["meta"]["variant"] == tasks[0].meta["variant"]
        assert delete.status_code == 409
        assert spec_edit.status_code == 409
        assert drop.status_code == 409

    async def test_locked_reads_see_the_committed_design(
        self, async_test_client, async_test_db, world
    ):
        from project_models import VariantDesign
        from variant_design_guard import VariantDesignError, freeze_design, update_design_spec

        await _create_design(async_test_client, world)
        pid = world["project"].id
        db = async_test_db

        async def _held_then_changed(sql):
            held = (
                await db.execute(
                    select(VariantDesign).where(
                        VariantDesign.project_id == pid, VariantDesign.key == "swap"
                    )
                )
            ).scalar_one()
            await db.execute(text(sql), {"p": pid})
            return held

        held = await _held_then_changed(
            "UPDATE variant_designs SET version = 5 WHERE project_id = :p AND key = 'swap'"
        )
        assert held.version == 1
        with pytest.raises(VariantDesignError) as stale:
            await db.run_sync(
                lambda s: update_design_spec(s, pid, "swap", SPEC, expected_version=1)
            )
        assert (stale.value.status_code, stale.value.code) == (409, "variant_design_version_conflict")
        await db.rollback()

        held = await _held_then_changed(
            "UPDATE variant_designs SET status = 'frozen', content_hash = repeat('0', 64), "
            "frozen_at = now() WHERE project_id = :p AND key = 'swap'"
        )
        assert held.status == "draft"
        for work in (
            lambda s: update_design_spec(s, pid, "swap", SPEC),
            lambda s: freeze_design(s, pid, "swap", None),
        ):
            with pytest.raises(VariantDesignError) as frozen:
                await db.run_sync(work)
            assert (frozen.value.status_code, frozen.value.code) == (409, "variant_design_frozen")
        await db.rollback()

    async def test_flush_guard_reads_the_committed_spec(
        self, async_test_client, async_test_db, world
    ):
        from project_models import VariantDesign
        from variant_design_guard import VariantDesignError

        await _create_design(async_test_client, world)
        pid = world["project"].id
        narrower = json.loads(json.dumps(SPEC))
        narrower["factors"][0]["levels"] = ["claimant"]
        db = async_test_db
        held = (
            await db.execute(
                select(VariantDesign).where(VariantDesign.project_id == pid, VariantDesign.key == "swap")
            )
        ).scalar_one()
        await db.execute(
            text("UPDATE variant_designs SET spec = CAST(:s AS jsonb) WHERE project_id = :p"),
            {"s": json.dumps(narrower), "p": pid},
        )
        data, meta = task_payload("u1", "respondent")
        db.add(Task(id=_uid(), project_id=pid, inner_id=98, data=data, meta=meta))
        with pytest.raises(VariantDesignError) as exc:
            await db.flush()
        assert exc.value.status_code == 422
        assert held.spec["factors"][0]["levels"] == ["claimant", "respondent"]
        await db.rollback()

    async def test_frozen_design_takes_no_new_tasks(self, api, async_test_client, async_test_db, world):
        await _create_design(async_test_client, world)
        await _add_tasks(async_test_db, world["project"])
        with _as_user(world["admin"]):
            resp = await api("post",
                f"/api/projects/{world['project'].id}/variant-designs/swap/freeze"
            )
        assert resp.status_code == 200, resp.text
        data, meta = task_payload("u3", "claimant")
        async_test_db.add(Task(id=_uid(), project_id=world["project"].id, inner_id=99, data=data, meta=meta))
        from variant_design_guard import VariantDesignError

        with pytest.raises(VariantDesignError) as exc:
            await async_test_db.commit()
        assert exc.value.status_code == 409
        await async_test_db.rollback()

    async def test_injected_out_of_span_difference_blocks_freeze(
        self, api, async_test_client, async_test_db, world
    ):
        await _create_design(async_test_client, world)
        tasks = await _add_tasks(async_test_db, world["project"])
        # The respondent twin of u1 also changes a word outside its span.
        await async_test_db.execute(
            text("UPDATE tasks SET data = CAST(:d AS json) WHERE id = :id"),
            {
                "d": json.dumps(
                    {"facts": f"{NAMES['respondent']} asks for the gate to be moved.", "reference": 51}
                ),
                "id": tasks[1].id,
            },
        )
        await async_test_db.commit()
        base = f"/api/projects/{world['project'].id}/variant-designs/swap"
        with _as_user(world["admin"]):
            check = await api("post", f"{base}/check")
            freeze = await api("post", f"{base}/freeze")
            after = await api("get", base)
        report = check.json()["report"]
        assert report["ok"] is False
        assert report["invariance"]["problem_count"] == 1
        problem = report["invariance"]["problems"][0]
        assert (problem["unit"], problem["path"], problem["kind"]) == ("u1", "facts", "differs_outside_spans")
        assert freeze.status_code == 409
        assert _detail(freeze)["code"] == "variant_design_checks_failed"
        assert _detail(freeze)["report"]["invariance"]["ok"] is False
        assert after.json()["status"] == "draft"


class TestWritePaths:
    async def test_metadata_patch_rejects_invalid_assignments(
        self, api, async_test_client, async_test_db, world
    ):
        await _create_design(async_test_client, world)
        tasks = await _add_tasks(async_test_db, world["project"])
        good = tasks[0].meta["variant"]
        cases = {
            "unknown level": {**good, "factors": {"role": "judge", "level": 1}},
            "unknown design": {**good, "design": "nope"},
            "not an object": "swap",
            "missing unit": {k: v for k, v in good.items() if k != "unit"},
        }
        for label, variant in cases.items():
            with _as_user(world["admin"]):
                single = await api("patch",
                    f"/api/projects/tasks/{tasks[0].id}/metadata", json={"variant": variant}
                )
                bulk = await api("patch",
                    "/api/projects/tasks/bulk-metadata",
                    json={"task_ids": [tasks[2].id], "metadata": {"variant": variant}},
                )
            assert single.status_code == 422, (label, single.text)
            assert bulk.status_code == 422, (label, bulk.text)
            assert _detail(single)["code"].startswith("variant_")

    async def test_duplicate_cell_is_refused_also_with_reordered_keys(
        self, api, async_test_client, async_test_db, world
    ):
        await _create_design(async_test_client, world)
        tasks = await _add_tasks(async_test_db, world["project"])
        twin = tasks[1].meta["variant"]
        # Move the respondent task onto the claimant cell, keys reordered.
        clash = {**twin, "factors": {"level": 1, "role": "claimant"}}
        clash["spans"] = tasks[0].meta["variant"]["spans"]
        with _as_user(world["admin"]):
            resp = await api("patch",
                f"/api/projects/tasks/{tasks[1].id}/metadata",
                json={"variant": clash},
            )
        assert resp.status_code == 409, resp.text
        assert _detail(resp)["code"] == "variant_cell_duplicate"
        # The same through a raw insert (no ORM guard on the way).
        data, meta = task_payload("u1", "claimant")
        meta["variant"]["factors"] = {"level": 1, "role": "claimant"}
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError) as exc:
            await async_test_db.execute(
                text(
                    "INSERT INTO tasks (id, project_id, data, meta, inner_id, is_labeled, "
                    "total_annotations, cancelled_annotations, comment_count, "
                    "unresolved_comment_count, korrektur_count, unresolved_korrektur_count) "
                    "VALUES (:id, :p, CAST(:d AS json), CAST(:m AS json), 50, false, 0, 0, 0, 0, 0, 0)"
                ),
                {"id": _uid(), "p": world["project"].id, "d": json.dumps(data), "m": json.dumps(meta)},
            )
        assert "uq_tasks_variant_cell" in str(exc.value)
        await async_test_db.rollback()

    async def test_a_between_unit_factor_does_not_make_a_new_cell(
        self, api, async_test_client, async_test_db, world
    ):
        await _create_design(async_test_client, world)
        tasks = await _add_tasks(async_test_db, world["project"])
        cell = (
            await async_test_db.execute(
                text("SELECT variant_cell FROM tasks WHERE id = :id"), {"id": tasks[0].id}
            )
        ).scalar_one()
        assert cell == {"role": "claimant"}
        twin = tasks[1].meta["variant"]
        for factors in ({"role": "claimant", "level": 2}, {"level": 2, "role": "claimant"}):
            clash = {**twin, "factors": factors, "spans": tasks[0].meta["variant"]["spans"]}
            with _as_user(world["admin"]):
                resp = await api(
                    "patch",
                    f"/api/projects/tasks/{tasks[1].id}/metadata",
                    json={"variant": clash},
                )
            assert resp.status_code == 409, (factors, resp.text)
            assert _detail(resp)["code"] == "variant_cell_duplicate"

    async def test_data_edit_that_breaks_a_span_is_refused(
        self, api, async_test_client, async_test_db, world
    ):
        await _create_design(async_test_client, world)
        tasks = await _add_tasks(async_test_db, world["project"])
        with _as_user(world["admin"]):
            resp = await api("put",
                f"/api/projects/{world['project'].id}/tasks/{tasks[0].id}",
                json={"data": {"facts": "short"}},
            )
        assert resp.status_code == 422, resp.text
        assert "outside the text" in json.dumps(_detail(resp))

    async def test_derived_columns_follow_meta(self, api, async_test_client, async_test_db, world):
        await _create_design(async_test_client, world)
        tasks = await _add_tasks(async_test_db, world["project"])
        row = (
            await async_test_db.execute(
                text("SELECT variant_design, variant_unit, variant_cell FROM tasks WHERE id = :id"),
                {"id": tasks[0].id},
            )
        ).one()
        assert row == ("swap", "u1", {"role": "claimant"})
        # Writing the columns directly is overwritten by the trigger.
        await async_test_db.execute(
            text("UPDATE tasks SET variant_unit = 'forged' WHERE id = :id"), {"id": tasks[0].id}
        )
        unit = (
            await async_test_db.execute(
                text("SELECT variant_unit FROM tasks WHERE id = :id"), {"id": tasks[0].id}
            )
        ).scalar_one()
        assert unit == "u1"
        with _as_user(world["admin"]):
            resp = await api("patch",
                f"/api/projects/tasks/{tasks[0].id}/metadata?merge=false", json={"tags": []}
            )
        assert resp.status_code == 200, resp.text
        cleared = (
            await async_test_db.execute(
                text("SELECT variant_design FROM tasks WHERE id = :id"), {"id": tasks[0].id}
            )
        ).scalar_one()
        assert cleared is None

    async def test_design_key_must_exist(self, api, async_test_client, async_test_db, world):
        """The foreign key, for writes that bypass the ORM guard."""
        data, meta = task_payload("u1", "claimant", design="ghost")
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError) as exc:
            await async_test_db.execute(
                text(
                    "INSERT INTO tasks (id, project_id, data, meta, inner_id, is_labeled, "
                    "total_annotations, cancelled_annotations, comment_count, "
                    "unresolved_comment_count, korrektur_count, unresolved_korrektur_count) "
                    "VALUES (:id, :p, CAST(:d AS json), CAST(:m AS json), 51, false, 0, 0, 0, 0, 0, 0)"
                ),
                {"id": _uid(), "p": world["project"].id, "d": json.dumps(data), "m": json.dumps(meta)},
            )
        assert "fk_tasks_variant_design" in str(exc.value)
        await async_test_db.rollback()


class TestCanary:
    """``meta.variant`` never reaches a system under test or a blinded
    annotator: not in v1 task reads (any caller), not in blinded task reads."""

    async def _world_with_tasks(self, client, db, world):
        await _create_design(client, world)
        return await _add_tasks(db, world["project"])

    async def test_v1_task_reads_never_carry_the_assignment(
        self, api, async_test_client, async_test_db, world
    ):
        tasks = await self._world_with_tasks(async_test_client, async_test_db, world)
        pid = world["project"].id
        for who in ("admin", "annotator"):
            with _as_user(world[who]):
                listing = await api("get", f"/api/v1/projects/{pid}/tasks")
                one = await api("get", f"/api/v1/projects/{pid}/tasks/{tasks[0].id}")
            assert listing.status_code == 200, listing.text
            assert one.status_code == 200, one.text
            for body in (listing.text, one.text):
                assert CANARY not in body and '"variant"' not in body
        # The editor still gets the rest of the meta.
        assert one.json()["meta"] == {"tags": ["t"]}

    async def test_blinded_task_reads_never_carry_the_assignment(
        self, api, async_test_client, async_test_db, world
    ):
        tasks = await self._world_with_tasks(async_test_client, async_test_db, world)
        pid = world["project"].id
        with _as_user(world["annotator"]):
            responses = [
                await api("get", f"/api/projects/{pid}/tasks"),
                await api("get", f"/api/projects/{pid}/next"),
                await api("get", f"/api/projects/tasks/{tasks[0].id}"),
                await api("get", "/api/data/", params={"project_ids": [pid]}),
            ]
        for resp in responses:
            assert resp.status_code == 200, resp.text
            assert CANARY not in resp.text and '"variant"' not in resp.text
        # Editors see it (they own the design).
        with _as_user(world["admin"]):
            editor = await api("get", f"/api/projects/tasks/{tasks[0].id}")
        assert editor.json()["meta"]["variant"]["provenance"]["generator"] == CANARY
