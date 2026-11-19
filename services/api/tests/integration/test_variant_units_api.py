"""The units of a variant design through the API (CORE 2.68).

``GET /api/projects/{id}/variant-designs/{key}/units`` pages through a
design's units, ``GET .../units/{unit}`` shows one unit: its tasks with the
declared spans, gold values and the answers of one system, and the unit's
check. Both need full read access to the task content, like the frame
download of an analysis run. Synthetic content only.
"""

import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from ai_services.request_capture import build_request_record, request_sha256
from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import (
    Generation,
    Organization,
    OrganizationMembership,
    OrganizationRole,
    ResponseGeneration,
    User,
)
from project_models import Project, ProjectOrganization, Task

pytestmark = pytest.mark.asyncio

CONFIG = (
    '<View><Text name="facts_view" value="$facts"/>'
    '<Number name="share" toName="facts_view"/></View>'
)
NAMES = {"first": "Ida Brook", "second": "Olaf Penn"}
SPEC = {
    "schema_version": 1,
    "title": "Name swap",
    "unit": {"name": "case"},
    "factors": [
        {"name": "party", "type": "nominal", "levels": ["first", "second"]},
        {"name": "level", "type": "numeric", "varies": "between_units"},
    ],
    "gold": [{"name": "reference", "path": "reference"}],
    "invariance": {"fields": ["facts"], "free": ["reference"]},
}


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(user: dict):
    app.dependency_overrides[require_user] = lambda: AuthUser(
        id=user["id"],
        username=user["username"],
        email=user["email"],
        name=user["name"],
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=user["created_at"],
    )
    try:
        yield
    finally:
        app.dependency_overrides.pop(require_user, None)


def _plain(u: User) -> dict:
    """The user as plain values: a refused request rolls the shared test
    session back, which expires ORM rows."""
    return {k: getattr(u, k) for k in ("id", "username", "email", "name", "created_at")}


async def _user(db, name: str) -> User:
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


def _facts(party: str) -> tuple:
    name = NAMES[party]
    text = f"The tenant {name} asks for the deposit back."
    at = text.index(name)
    return text, [[at, at + len(name)]]


def _record(party: str) -> dict:
    return build_request_record(
        [
            {
                "provider": "openai",
                "api": "chat.completions",
                "capture": "http_body",
                "body": {
                    "model": "sim-model",
                    "messages": [{"role": "user", "content": _facts(party)[0]}],
                },
            }
        ]
    )


@pytest_asyncio.fixture(scope="function")
async def world(async_test_db, async_test_client):
    db = async_test_db
    admin = await _user(db, "vu-admin")
    contributor = await _user(db, "vu-contrib")
    annotator = await _user(db, "vu-anno")
    org = Organization(
        id=_uid(),
        name="VU Org",
        slug=f"vu-org-{_uid()[:8]}",
        display_name="VU Org",
        created_at=datetime.now(timezone.utc),
    )
    db.add(org)
    await db.flush()
    for user, role in (
        (admin, OrganizationRole.ORG_ADMIN),
        (contributor, OrganizationRole.CONTRIBUTOR),
        (annotator, OrganizationRole.ANNOTATOR),
    ):
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
    project = Project(
        id=_uid(),
        title=f"VU Project {_uid()[:6]}",
        label_config=CONFIG,
        created_by=admin.id,
        is_published=True,
        assignment_mode="open",
    )
    db.add(project)
    await db.flush()
    db.add(ProjectOrganization(id=_uid(), project_id=project.id, organization_id=org.id, assigned_by=admin.id))
    await db.commit()
    pid = project.id

    admin, contributor, annotator = _plain(admin), _plain(contributor), _plain(annotator)
    with _as_user(admin):
        resp = await async_test_client.post(
            f"/api/projects/{pid}/variant-designs", json={"key": "swap", "spec": SPEC}
        )
    assert resp.status_code == 201, resp.text

    tasks = {}
    inner = 0
    for i, unit in enumerate(("u1", "u2", "u3")):
        for party in ("first", "second"):
            inner += 1
            text, spans = _facts(party)
            task_id = _uid()
            db.add(
                Task(
                    id=task_id,
                    project_id=pid,
                    inner_id=inner,
                    data={"facts": text, "reference": 40 + i},
                    meta={
                        "variant": {
                            "design": "swap",
                            "unit": unit,
                            "factors": {"party": party, "level": i + 1},
                            "spans": {"facts": spans},
                        }
                    },
                )
            )
            tasks[(unit, party)] = task_id
    await db.commit()

    for party in ("first", "second"):
        for model, system in (("sim-model", "sim-model@aaaaaa"), ("sim-other", None)):
            rg = ResponseGeneration(
                id=_uid(),
                project_id=pid,
                task_id=tasks[("u1", party)],
                model_id=model,
                status="completed",
                created_by=admin["id"],
                structure_key="default",
            )
            db.add(rg)
            await db.flush()
            record = _record(party) if system else None
            db.add(
                Generation(
                    id=f"gen-{party}-{model}-{_uid()[:6]}",
                    generation_id=rg.id,
                    task_id=rg.task_id,
                    model_id=model,
                    run_index=0,
                    case_data="{}",
                    response_content='{"share": 40}',
                    status="completed",
                    parse_status="success",
                    parsed_annotation=[{"from_name": "share", "type": "number", "value": {"number": 40}}],
                    response_metadata=json.dumps({"system": {"key": system}}) if system else None,
                    request_record=record,
                    request_sha256=request_sha256(record) if record else None,
                )
            )
    await db.commit()
    return {
        "admin": admin,
        "contributor": contributor,
        "annotator": annotator,
        "project": pid,
        "tasks": tasks,
    }


async def _get(client, db, user, url, **params):
    with _as_user(user):
        resp = await client.get(url, params=params or None)
    if resp.status_code >= 400:
        await db.rollback()
    return resp


class TestUnitList:
    async def test_lists_units_with_task_counts_paged(self, async_test_client, async_test_db, world):
        base = f"/api/projects/{world['project']}/variant-designs/swap/units"
        full = await _get(async_test_client, async_test_db, world["admin"], base)
        assert full.status_code == 200, full.text
        assert full.json()["items"] == [
            {"unit": "u1", "task_count": 2},
            {"unit": "u2", "task_count": 2},
            {"unit": "u3", "task_count": 2},
        ]
        assert full.json()["total"] == 3
        page = await _get(async_test_client, async_test_db, world["admin"], base, limit=1, offset=1)
        assert [i["unit"] for i in page.json()["items"]] == ["u2"]
        assert (page.json()["total"], page.json()["limit"], page.json()["offset"]) == (3, 1, 1)

    async def test_unknown_design_is_404(self, async_test_client, async_test_db, world):
        resp = await _get(
            async_test_client,
            async_test_db,
            world["admin"],
            f"/api/projects/{world['project']}/variant-designs/nope/units",
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "variant_design_not_found"


class TestUnitView:
    async def test_shows_spans_gold_answers_and_the_unit_check(
        self, async_test_client, async_test_db, world
    ):
        url = f"/api/projects/{world['project']}/variant-designs/swap/units/u1"
        resp = await _get(
            async_test_client, async_test_db, world["contributor"], url, system="sim-model@aaaaaa"
        )
        assert resp.status_code == 200, resp.text
        view = resp.json()
        assert view["unit"] == "u1" and view["system"] == "sim-model@aaaaaa"
        assert view["systems"] == ["sim-model@aaaaaa", "sim-other"]
        assert view["design"]["key"] == "swap" and view["design"]["unit_name"] == "case"
        assert view["check"]["ok"] is True and view["check"]["task_count"] == 2
        first, second = view["tasks"]
        assert first["factors"] == {"party": "first", "level": 1}
        text, spans = _facts("first")
        assert first["texts"] == [
            {"path": "facts", "kind": "spanned", "text": text, "truncated": False, "spans": spans},
            {"path": "reference", "kind": "free", "text": "40", "truncated": False, "spans": []},
        ]
        assert first["slots"] == []
        assert text[spans[0][0] : spans[0][1]] == NAMES["first"]
        assert first["gold"] == [{"name": "reference", "path": "reference", "value": 40}]
        (answer,) = first["generations"]
        assert answer["system_key"] == "sim-model@aaaaaa" and answer["fields"] == {"share": 40}
        assert answer["has_request_record"] is True
        assert answer["request_sha256"] == request_sha256(_record("first"))
        assert [g["model_id"] for g in second["generations"]] == ["sim-model"]

        # By model id, the system without a recorded key.
        other = await _get(async_test_client, async_test_db, world["admin"], url, system="sim-other")
        assert [g["model_id"] for g in other.json()["tasks"][0]["generations"]] == ["sim-other"]
        assert other.json()["tasks"][0]["generations"][0]["has_request_record"] is False
        # Without a system, every answer.
        every = await _get(async_test_client, async_test_db, world["admin"], url)
        assert len(every.json()["tasks"][0]["generations"]) == 2

    async def test_the_request_of_an_answer_has_a_matching_hash(
        self, async_test_client, async_test_db, world
    ):
        url = f"/api/projects/{world['project']}/variant-designs/swap/units/u1"
        view = (
            await _get(async_test_client, async_test_db, world["admin"], url, system="sim-model")
        ).json()
        trial = view["tasks"][0]["generations"][0]["id"]
        req = await _get(async_test_client, async_test_db, world["admin"], f"/api/runs/trials/{trial}/request")
        assert req.status_code == 200, req.text
        assert req.json()["hash_matches"] is True

    async def test_unknown_unit_is_404(self, async_test_client, async_test_db, world):
        resp = await _get(
            async_test_client,
            async_test_db,
            world["admin"],
            f"/api/projects/{world['project']}/variant-designs/swap/units/nope",
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "variant_unit_not_found"


class TestAccess:
    async def test_viewers_without_full_content_rights_get_403(
        self, async_test_client, async_test_db, world
    ):
        base = f"/api/projects/{world['project']}/variant-designs/swap/units"
        for url in (base, f"{base}/u1"):
            resp = await _get(async_test_client, async_test_db, world["annotator"], url)
            assert resp.status_code == 403, (url, resp.text)
            assert resp.json()["detail"]["code"] == "variant_unit_forbidden"
            assert "tasks" not in resp.json() and "items" not in resp.json()

    async def test_outsiders_get_no_unit(self, async_test_client, async_test_db, world):
        outsider = _plain(await _user(async_test_db, "vu-out"))
        await async_test_db.commit()
        resp = await _get(
            async_test_client,
            async_test_db,
            outsider,
            f"/api/projects/{world['project']}/variant-designs/swap/units/u1",
        )
        assert resp.status_code in (403, 404)
        assert "tasks" not in resp.json()
