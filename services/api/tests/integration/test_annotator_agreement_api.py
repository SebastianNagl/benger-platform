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

import routers.reports as reports_router
from auth_module.dependencies import optional_user, require_user
from auth_module.models import User as AuthUser
from main import app
from models import User
from project_models import Annotation, Project, Task
from report_models import ProjectReport
from report_snapshot import build_report_snapshot

# The feature is behind a platform flag (off by default in the suite).
pytestmark = pytest.mark.flags_on("variant_experiments")

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
    """Override both auth dependencies; ``None`` = anonymous visitor."""
    auth_user = None if db_user is None else AuthUser(
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


@pytest.fixture
def publishable(monkeypatch):
    """The seeded project has no generations or evaluations; publishing's
    precondition is not what these tests are about."""
    monkeypatch.setattr(reports_router, "can_publish_report", lambda _db, _pid: (True, "ok"))


async def _report(db, project, admin, *, show_participants):
    report = ProjectReport(
        id=_uid(),
        project_id=project.id,
        content={
            "sections": {
                "project_info": {"title": project.title, "visible": True},
                "data": {"visible": True},
                "annotations": {"visible": True, "show_participants": show_participants},
                "generation": {"visible": True},
                "evaluation": {"visible": True},
            },
            "metadata": {},
        },
        is_published=False,
        created_by=admin.id,
    )
    db.add(report)
    await db.flush()
    return report


def _pair_names(agreement):
    return {n for c in agreement["controls"] for p in c["pairs"] for n in (p["annotator_a"], p["annotator_b"])}


@pytest.mark.asyncio
@pytest.mark.parametrize("show_participants", [True, False])
async def test_report_agreement_pairs_follow_show_participants(
    async_test_client, async_test_db, publishable, show_participants
):
    admin, project = await _seed_overlap(async_test_db)
    report = await _report(async_test_db, project, admin, show_participants=show_participants)
    expected_names = {"Ash", "Birch", "Cedar"} if show_participants else set()

    with _as_user(admin):
        draft = await async_test_client.get(f"/api/reports/{report.id}/data")
        published = await async_test_client.put(f"/api/projects/{project.id}/report/publish", json={"is_public": True})
        refreshed = await async_test_client.post(f"/api/projects/{project.id}/report/refresh")
    with _as_user(None):
        public = await async_test_client.get(f"/api/reports/{report.id}/data")

    for r in (draft, published, refreshed, public):
        assert r.status_code == 200, r.text
    payloads = [
        draft.json()["snapshot"],
        draft.json()["report"]["content"]["snapshot"],
        published.json()["content"]["snapshot"],
        refreshed.json()["content"]["snapshot"],
        public.json()["snapshot"],
        public.json()["report"]["content"]["snapshot"],
    ]
    for snap in payloads:
        agreement = snap["annotator_agreement"]
        (label,) = agreement["controls"]
        assert label["fleiss_kappa"] == pytest.approx(1 / 3, abs=1e-4)
        assert label["cohens_kappa_mean"] == pytest.approx(0.4, abs=1e-4)
        assert label["percent_agreement"] == pytest.approx(0.5)
        assert agreement["annotator_count"] == 3
        assert _pair_names(agreement) == expected_names
    await async_test_db.refresh(report)
    assert _pair_names(report.content["snapshot"]["annotator_agreement"]) == {"Ash", "Birch", "Cedar"}


@pytest.mark.asyncio
async def test_participant_switch_hides_and_restores_frozen_per_person_data(
    async_test_client, async_test_db, publishable
):
    admin, project = await _seed_overlap(async_test_db)
    report = await _report(async_test_db, project, admin, show_participants=True)
    all_names = {"Ash", "Birch", "Cedar"}

    async def save(show_participants):
        with _as_user(admin):
            editor = await async_test_client.get(f"/api/projects/{project.id}/report")
            content = editor.json()["content"]
            content["sections"]["annotations"]["show_participants"] = show_participants
            return await async_test_client.post(f"/api/projects/{project.id}/report", json={"content": content})

    async def served():
        """(snapshot, annotations section) of every read path, and the public body."""
        with _as_user(admin):
            editor = await async_test_client.get(f"/api/projects/{project.id}/report")
            visibility = await async_test_client.put(
                f"/api/projects/{project.id}/report/visibility", json={"is_public": True}
            )
        with _as_user(None):
            public = await async_test_client.get(f"/api/reports/{report.id}/data")
        for r in (editor, visibility, public):
            assert r.status_code == 200, r.text
        pairs = [
            (body["content"]["snapshot"], body["content"]["sections"]["annotations"])
            for body in (editor.json(), visibility.json(), public.json()["report"])
        ]
        pairs.append((public.json()["snapshot"], public.json()["report"]["content"]["sections"]["annotations"]))
        return pairs, public.text

    with _as_user(admin):
        published = await async_test_client.put(f"/api/projects/{project.id}/report/publish", json={"is_public": True})
    frozen = published.json()["content"]["snapshot"]
    frozen_at = frozen["generated_at"]
    assert _pair_names(frozen["annotator_agreement"]) == all_names
    assert {p["label"] for p in frozen["participants"]} == all_names
    section_participants = [
        {"id": p["id"], "name": p["label"], "count": p["annotation_count"]} for p in frozen["participants"]
    ]
    report.content = {
        **report.content,
        "sections": {
            **report.content["sections"],
            "annotations": {**report.content["sections"]["annotations"], "participants": section_participants},
        },
    }
    await async_test_db.flush()

    hidden = await save(False)
    assert hidden.status_code == 200, hidden.text
    views, public_text = await served()
    views.append((hidden.json()["content"]["snapshot"], hidden.json()["content"]["sections"]["annotations"]))
    for snap, annotations in views:
        assert snap["annotator_agreement"]["controls"][0]["fleiss_kappa"] == pytest.approx(1 / 3, abs=1e-4)
        assert snap["statistics"]["participant_count"] == 3
        assert _pair_names(snap["annotator_agreement"]) == set()
        assert snap["participants"] == []
        assert annotations["participants"] == []
    for p in frozen["participants"]:
        assert p["id"] not in public_text
        assert f'"{p["label"]}"' not in public_text

    shown = await save(True)
    assert shown.status_code == 200, shown.text
    views, _ = await served()
    views.append((shown.json()["content"]["snapshot"], shown.json()["content"]["sections"]["annotations"]))
    for snap, annotations in views:
        assert snap["generated_at"] == frozen_at
        assert _pair_names(snap["annotator_agreement"]) == all_names
        assert snap["participants"] == frozen["participants"]
        assert annotations["participants"] == section_participants


@pytest.mark.asyncio
async def test_agreement_switch_withholds_and_restores_frozen_agreement(
    async_test_client, async_test_db, publishable
):
    admin, project = await _seed_overlap(async_test_db)
    report = await _report(async_test_db, project, admin, show_participants=True)

    async def save(show_agreement):
        with _as_user(admin):
            editor = await async_test_client.get(f"/api/projects/{project.id}/report")
            content = editor.json()["content"]
            content["sections"]["annotations"]["show_agreement"] = show_agreement
            return await async_test_client.post(f"/api/projects/{project.id}/report", json={"content": content})

    async def served(saved):
        with _as_user(admin):
            editor = await async_test_client.get(f"/api/projects/{project.id}/report")
            draft = await async_test_client.get(f"/api/reports/{report.id}/data")
        with _as_user(None):
            public = await async_test_client.get(f"/api/reports/{report.id}/data")
        for r in (saved, editor, draft, public):
            assert r.status_code == 200, r.text
        return [
            saved.json()["content"]["snapshot"],
            editor.json()["content"]["snapshot"],
            draft.json()["snapshot"],
            draft.json()["report"]["content"]["snapshot"],
            public.json()["snapshot"],
            public.json()["report"]["content"]["snapshot"],
        ], public.text

    with _as_user(admin):
        published = await async_test_client.put(f"/api/projects/{project.id}/report/publish", json={"is_public": True})
    frozen = published.json()["content"]["snapshot"]
    assert frozen["annotator_agreement"]["controls"][0]["fleiss_kappa"] == pytest.approx(1 / 3, abs=1e-4)

    snaps, public_text = await served(await save(False))
    for snap in snaps:
        assert snap["annotator_agreement"] is None
        assert {p["label"] for p in snap["participants"]} == {"Ash", "Birch", "Cedar"}
    assert "fleiss_kappa" not in public_text
    assert "cohens_kappa" not in public_text
    await async_test_db.refresh(report)
    assert report.content["snapshot"]["annotator_agreement"] == frozen["annotator_agreement"]

    snaps, _ = await served(await save(True))
    for snap in snaps:
        assert snap["generated_at"] == frozen["generated_at"]
        assert snap["annotator_agreement"] == frozen["annotator_agreement"]
