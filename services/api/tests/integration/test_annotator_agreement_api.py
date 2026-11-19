"""Annotator agreement on a seeded project with overlap.

Covers ``GET /api/evaluations/projects/{id}/annotator-agreement`` and the
``annotator_agreement`` key of the report snapshot. The labels are the
three-annotator example of ``tests/unit/test_annotator_agreement.py``:
Fleiss' kappa 1/3, Cohen's kappa 1/2, 1/5 and 1/2, percent agreement 1/2.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from auth_module.dependencies import optional_user, require_user
from auth_module.models import User as AuthUser
from main import app
from models import User
from project_models import Annotation, Project, Task
from report_snapshot import build_report_snapshot

LABELS = {
    0: ("x", "x", "x"),
    1: ("x", "x", "y"),
    2: ("y", "y", "y"),
    3: ("x", "y", "y"),
}


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user):
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
    app.dependency_overrides[optional_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)
        app.dependency_overrides.pop(optional_user, None)


async def _user(db, *, pseudonym=None, is_superadmin=False):
    u = User(
        id=_uid(),
        username=f"u-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Real Name",
        pseudonym=pseudonym,
        use_pseudonym=True,
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _project(db, creator, n_tasks):
    project = Project(
        id=_uid(),
        title="Agreement Bench",
        created_by=creator.id,
        label_config=(
            '<View><Text name="text" value="$text"/>'
            '<Choices name="label" toName="text"><Choice value="x"/><Choice value="y"/></Choices>'
            '<TextArea name="comment" toName="text"/></View>'
        ),
    )
    db.add(project)
    await db.flush()
    tasks = []
    for i in range(n_tasks):
        t = Task(id=_uid(), project_id=project.id, data={"text": f"case {i}"}, created_by=creator.id, inner_id=i + 1)
        db.add(t)
        tasks.append(t)
    await db.flush()
    return project, tasks


def _annotation(project, task, user, label, *, cancelled=False):
    return Annotation(
        id=_uid(),
        task_id=task.id,
        project_id=project.id,
        completed_by=user.id,
        result=[
            {"from_name": "label", "to_name": "text", "type": "choices", "value": {"choices": [label]}},
            {"from_name": "comment", "to_name": "text", "type": "textarea", "value": {"text": ["free text"]}},
        ],
        was_cancelled=cancelled,
    )


async def _seed_overlap(db):
    admin = await _user(db, is_superadmin=True)
    annotators = [await _user(db, pseudonym=p) for p in ("Ash", "Birch", "Cedar")]
    project, tasks = await _project(db, admin, 5)
    for i, labels in LABELS.items():
        for user, label in zip(annotators, labels):
            db.add(_annotation(project, tasks[i], user, label))
    # One task with a single annotator, and a withdrawn second annotation on
    # it: neither makes the task comparable.
    db.add(_annotation(project, tasks[4], annotators[0], "y"))
    db.add(_annotation(project, tasks[4], annotators[1], "x", cancelled=True))
    await db.flush()
    return admin, project


@pytest.mark.asyncio
async def test_agreement_route_equals_hand_computed_kappa(async_test_client, async_test_db):
    admin, project = await _seed_overlap(async_test_db)

    with _as_user(admin):
        r = await async_test_client.get(f"/api/evaluations/projects/{project.id}/annotator-agreement")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["available"] is True
    assert body["overlap_task_count"] == 4
    assert body["annotator_count"] == 3
    assert body["unsupported_controls"] == [{"control": "comment", "type": "textarea"}]
    (label,) = body["controls"]
    assert label["control"] == "label"
    assert label["n_items"] == 4
    assert label["fleiss_kappa"] == pytest.approx(1 / 3, abs=1e-4)
    assert label["percent_agreement"] == pytest.approx(0.5)
    assert label["cohens_kappa_mean"] == pytest.approx(0.4, abs=1e-4)
    pairs = {(p["annotator_a"], p["annotator_b"]): p["cohens_kappa"] for p in label["pairs"]}
    kappas = {frozenset(k): v for k, v in pairs.items()}
    assert kappas[frozenset({"Ash", "Birch"})] == pytest.approx(0.5, abs=1e-4)
    assert kappas[frozenset({"Ash", "Cedar"})] == pytest.approx(0.2, abs=1e-4)
    assert kappas[frozenset({"Birch", "Cedar"})] == pytest.approx(0.5, abs=1e-4)
    assert "Real Name" not in r.text


@pytest.mark.asyncio
async def test_agreement_is_unavailable_without_two_annotators(async_test_client, async_test_db):
    admin = await _user(async_test_db, is_superadmin=True)
    a, b = await _user(async_test_db, pseudonym="Ash"), await _user(async_test_db, pseudonym="Birch")
    project, tasks = await _project(async_test_db, admin, 2)
    async_test_db.add(_annotation(project, tasks[0], a, "x"))
    async_test_db.add(_annotation(project, tasks[1], b, "x"))
    await async_test_db.flush()

    with _as_user(admin):
        r = await async_test_client.get(f"/api/evaluations/projects/{project.id}/annotator-agreement")
    assert r.status_code == 200
    assert r.json() == {
        "available": False,
        "overlap_task_count": 0,
        "annotator_count": 0,
        "controls": [],
        "unsupported_controls": [],
    }
    snap = await async_test_db.run_sync(build_report_snapshot, project.id)
    assert snap["annotator_agreement"] is None


@pytest.mark.asyncio
async def test_agreement_route_checks_project_access(async_test_client, async_test_db):
    admin, project = await _seed_overlap(async_test_db)
    stranger = await _user(async_test_db, pseudonym="Stranger")

    with _as_user(stranger):
        r = await async_test_client.get(f"/api/evaluations/projects/{project.id}/annotator-agreement")
    assert r.status_code == 403
    with _as_user(admin):
        r = await async_test_client.get(f"/api/evaluations/projects/{_uid()}/annotator-agreement")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_report_snapshot_carries_agreement(async_test_db):
    _admin, project = await _seed_overlap(async_test_db)

    snap = await async_test_db.run_sync(build_report_snapshot, project.id)
    agreement = snap["annotator_agreement"]
    assert agreement["overlap_task_count"] == 4
    (label,) = agreement["controls"]
    assert label["fleiss_kappa"] == pytest.approx(1 / 3, abs=1e-4)
    assert {p["annotator_a"] for p in label["pairs"]} | {p["annotator_b"] for p in label["pairs"]} == {
        "Ash",
        "Birch",
        "Cedar",
    }
