"""
Report snapshot + public visibility (routers/reports.py, shared/report_snapshot.py).

Seeds a small benchmark-shaped project on the async test DB: two catalog
models (one official, one private BYOM), an annotator with a pseudonym, one
completed evaluation run whose task_evaluations carry BOTH metric shapes the
platform has stored over time (nested ``{value, details}`` and the legacy
flat siblings), audit keys that must never become metrics, and a judge
config on the project. Then drives the snapshot builder and the public /
visibility / refresh HTTP surface.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from auth_module.dependencies import optional_user, require_user
from auth_module.models import User as AuthUser
from main import app
from models import (
    EvaluationJudgeRun,
    EvaluationRun,
    Generation,
    LLMModel,
    Organization,
    OrganizationMembership,
    ResponseGeneration,
    TaskEvaluation,
    User,
)
from project_models import Annotation, Project, ProjectOrganization, Task
from report_models import ProjectReport
from report_snapshot import build_report_snapshot


def _uid() -> str:
    return str(uuid.uuid4())


def _auth(db_user: User) -> AuthUser:
    return AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )


@contextmanager
def _as_user(db_user):
    """Override both auth dependencies; ``None`` = anonymous visitor."""
    auth_user = _auth(db_user) if db_user is not None else None
    app.dependency_overrides[require_user] = lambda: auth_user
    app.dependency_overrides[optional_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)
        app.dependency_overrides.pop(optional_user, None)


async def _user(db, *, is_superadmin=False, pseudonym=None, use_pseudonym=True, name="Report User"):
    u = User(
        id=_uid(),
        username=f"u-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name=name,
        pseudonym=pseudonym,
        use_pseudonym=use_pseudonym,
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _seed_benchmark(db, creator: User, annotator: User, *, org: Organization = None):
    """Project with 2 tasks, 2 models (official + private custom), one completed
    run, evaluations in both metric shapes, one human submission."""
    project = Project(
        id=_uid(),
        title="Snapshot Bench",
        description="seeded",
        created_by=creator.id,
        label_config='<View><Text name="text" value="$text"/></View>',
        evaluation_config={
            "evaluation_configs": [
                {
                    "id": "cfg-judge",
                    "metric": "llm_judge_falloesung",
                    "display_name": "Notenpunkte (Abo-Modell)",
                    "metric_parameters": {"judge_model": "judge-model"},
                    "enabled": True,
                }
            ]
        },
    )
    db.add(project)
    await db.flush()
    if org is not None:
        db.add(ProjectOrganization(id=_uid(), project_id=project.id, organization_id=org.id, assigned_by=creator.id))
        await db.flush()

    tasks = []
    for i in range(2):
        t = Task(id=_uid(), project_id=project.id, data={"text": f"case {i}"}, created_by=creator.id, inner_id=i + 1)
        db.add(t)
        tasks.append(t)
    await db.flush()

    for mid, name, official, public in (
        ("official-model", "Official Model", True, False),
        ("custom-private", "Private Endpoint", False, False),
        ("judge-model", "Judge Model", True, False),
    ):
        db.add(LLMModel(
            id=mid, name=name, provider="openai", model_type="chat", capabilities=[], is_active=True,
            is_official=official, is_public=public, is_private=not official,
            # custom (BYOM) rows must carry their endpoint (check constraint)
            base_url=None if official else "https://example.invalid/v1",
            endpoint_model_name=None if official else "private-endpoint",
        ))
    await db.flush()

    gens = {}
    for mid in ("official-model", "custom-private"):
        for t in tasks:
            # one parent run per (task, model): generations are unique per (run, run_index)
            rg = ResponseGeneration(id=_uid(), project_id=project.id, task_id=t.id, model_id=mid, status="completed",
                                    created_by=creator.id, started_at=datetime.now(timezone.utc),
                                    completed_at=datetime.now(timezone.utc))
            db.add(rg)
            await db.flush()
            g = Generation(id=_uid(), generation_id=rg.id, task_id=t.id, model_id=mid, case_data="x", response_content="y")
            db.add(g)
            gens[(mid, t.id)] = g
    await db.flush()

    ann = Annotation(
        id=_uid(), task_id=tasks[0].id, project_id=project.id, completed_by=annotator.id,
        result=[{"from_name": "answer", "to_name": "text", "type": "textarea", "value": {"text": ["x"]}}],
        was_cancelled=False,
    )
    db.add(ann)
    await db.flush()

    er = EvaluationRun(
        id=_uid(), project_id=project.id, model_id="official-model", evaluation_type_ids=["llm_judge_falloesung"],
        metrics={}, status="completed", samples_evaluated=3, eval_metadata={}, created_by=creator.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(er)
    await db.flush()
    jr = EvaluationJudgeRun(id=_uid(), evaluation_id=er.id, judge_model_id="judge-model", run_index=0, status="completed")
    db.add(jr)
    await db.flush()

    def te(evaluation_config_id="cfg-judge", field_name="loesung", **kw):
        return TaskEvaluation(
            id=_uid(), evaluation_id=er.id, judge_run_id=jr.id, field_name=field_name, answer_type="long_text",
            ground_truth={"value": "ref"}, prediction={"value": "pred"}, passed=True,
            evaluation_config_id=evaluation_config_id, **kw,
        )

    nested = lambda v, gp, passed: {  # noqa: E731
        "llm_judge_falloesung": {"value": v, "method": "llm_judge_falloesung", "error": None,
                                  "details": {"raw_score": v * 100, "grade_points": gp, "passed": passed, "judge_response": "…"}},
        "raw_score": v * 100,
        "llm_judge_lexam_response": "should be ignored",
    }
    db.add(te(task_id=tasks[0].id, generation_id=gens[("official-model", tasks[0].id)].id, metrics=nested(0.9, 14, True)))
    db.add(te(task_id=tasks[1].id, generation_id=gens[("official-model", tasks[1].id)].id, metrics=nested(0.7, 10, True)))
    db.add(te(task_id=tasks[0].id, generation_id=gens[("custom-private", tasks[0].id)].id, metrics=nested(0.5, 4, False)))
    # legacy flat shape for the human submission
    db.add(te(task_id=tasks[0].id, generation_id=None, annotation_id=ann.id,
              metrics={"llm_judge_falloesung": 0.6, "llm_judge_falloesung_raw": 60.0,
                       "llm_judge_falloesung_grade_points": 7.0, "llm_judge_falloesung_passed": 1.0,
                       "llm_judge_falloesung_details": {"score": 60}}))
    # a bare-number lexical metric on a generation
    db.add(te(task_id=tasks[1].id, generation_id=gens[("official-model", tasks[1].id)].id, metrics={"bleu": 0.25}, evaluation_config_id="cfg-bleu", field_name="answer"))
    await db.flush()

    report = ProjectReport(
        id=_uid(), project_id=project.id, created_by=creator.id, is_published=False,
        content={"sections": {"project_info": {"title": "t", "description": "d", "status": "completed", "editable": True, "visible": True}},
                 "metadata": {"sections_completed": ["project_info"], "can_publish": False}},
    )
    db.add(report)
    await db.flush()
    return project, report


# ---------------------------------------------------------------------------
# builder
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_snapshot_builder_normalizes_shapes_and_hides_private_models(async_test_db):
    admin = await _user(async_test_db, is_superadmin=True)
    ann = await _user(async_test_db, pseudonym="KindAlly", name="Real Name")
    project, _ = await _seed_benchmark(async_test_db, admin, ann)

    snap = await async_test_db.run_sync(build_report_snapshot, project.id)

    assert snap["statistics"] == {"task_count": 2, "annotation_count": 1, "participant_count": 1, "model_count": 1, "evaluation_count": 5}
    ids = {m["id"] for m in snap["methods"]}
    assert {"llm_judge_falloesung", "llm_judge_falloesung_grade_points", "llm_judge_falloesung_passed", "bleu"} <= ids
    assert "raw_score" not in ids and "llm_judge_lexam_response" not in ids and "llm_judge_falloesung_raw" not in ids
    assert snap["primary_metric"] == "llm_judge_falloesung"
    assert snap["primary_config_id"] == "cfg-judge"
    assert snap["grade_metric"] == "llm_judge_falloesung_grade_points"

    subjects = {(r["subject"]["id"], r["config_id"]): r for r in snap["series"]}
    assert ("custom-private", "cfg-judge") not in subjects, "private BYOM must not leak"
    model_row = subjects[("official-model", "cfg-judge")]
    assert model_row["subject"]["label"] == "Official Model"
    assert model_row["metrics"]["llm_judge_falloesung"]["n"] == 2
    assert model_row["metrics"]["llm_judge_falloesung"]["mean"] == pytest.approx(80.0)   # 0-100 scale
    assert model_row["metrics"]["llm_judge_falloesung_grade_points"]["mean"] == pytest.approx(12.0)
    assert model_row["metrics"]["llm_judge_falloesung"]["pass_rate"] == pytest.approx(1.0)
    human_row = subjects[(f"annotator:{ann.id}", "cfg-judge")]
    assert human_row["subject"] == {"id": f"annotator:{ann.id}", "kind": "human", "label": "KindAlly"}
    assert human_row["metrics"]["llm_judge_falloesung"]["mean"] == pytest.approx(60.0)
    assert human_row["metrics"]["llm_judge_falloesung_grade_points"]["mean"] == pytest.approx(7.0)
    assert subjects[("official-model", "cfg-bleu")]["metrics"]["bleu"]["mean"] == pytest.approx(0.25)

    cfg = {c["id"]: c for c in snap["configs"]}
    assert cfg["cfg-judge"]["judge_label"] == "Judge Model" and cfg["cfg-judge"]["name"] == "Notenpunkte (Abo-Modell)"
    assert cfg["cfg-judge"]["n"] == 3  # 2 model + 1 human visible samples

    grade = next(d for d in snap["distributions"] if d["metric"] == "llm_judge_falloesung_grade_points")
    assert grade["bins"] == list(range(19))
    assert grade["by_kind"]["model"][14] == 1 and grade["by_kind"]["model"][10] == 1 and sum(grade["by_kind"]["model"]) == 2
    assert grade["by_kind"]["human"][7] == 1
    assert "custom-private" not in grade["by_subject"]
    assert snap["participants"] == [{"id": ann.id, "label": "KindAlly", "annotation_count": 1}]
    assert [m["id"] for m in snap["models"]] == ["official-model"]


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_publish_public_freezes_snapshot_and_anonymous_can_read(async_test_client, async_test_db):
    admin = await _user(async_test_db, is_superadmin=True)
    ann = await _user(async_test_db, pseudonym="Otter")
    project, report = await _seed_benchmark(async_test_db, admin, ann)

    with _as_user(admin):
        r = await async_test_client.put(f"/api/projects/{project.id}/report/publish", json={"is_public": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_published"] is True and body["is_public"] is True
    assert body["content"]["snapshot"]["primary_metric"] == "llm_judge_falloesung"

    with _as_user(None):
        listing = await async_test_client.get("/api/reports")
        data = await async_test_client.get(f"/api/reports/{report.id}/data")
    assert listing.status_code == 200
    assert [i["id"] for i in listing.json()] == [report.id]
    assert listing.json()[0]["visibility"] == "public"
    assert data.status_code == 200
    assert data.json()["snapshot"]["statistics"]["task_count"] == 2
    assert data.json()["report"]["is_public"] is True


@pytest.mark.asyncio
async def test_org_report_stays_hidden_from_anonymous_and_strangers(async_test_client, async_test_db):
    admin = await _user(async_test_db, is_superadmin=True)
    ann = await _user(async_test_db)
    member = await _user(async_test_db)
    stranger = await _user(async_test_db)
    org = Organization(id=_uid(), name="Org", display_name="Org", slug=f"org-{_uid()[:6]}", created_at=datetime.now(timezone.utc))
    async_test_db.add(org)
    await async_test_db.flush()
    async_test_db.add(OrganizationMembership(id=_uid(), user_id=member.id, organization_id=org.id, role="ANNOTATOR", is_active=True, joined_at=datetime.now(timezone.utc)))
    await async_test_db.flush()
    project, report = await _seed_benchmark(async_test_db, admin, ann, org=org)

    with _as_user(admin):
        r = await async_test_client.put(f"/api/projects/{project.id}/report/publish")
    assert r.status_code == 200 and r.json()["is_public"] is False

    with _as_user(None):
        assert (await async_test_client.get("/api/reports")).json() == []
        assert (await async_test_client.get(f"/api/reports/{report.id}/data")).status_code == 401
    with _as_user(stranger):
        assert [i["id"] for i in (await async_test_client.get("/api/reports")).json()] == []
        assert (await async_test_client.get(f"/api/reports/{report.id}/data")).status_code == 403
    with _as_user(member):
        items = (await async_test_client.get("/api/reports")).json()
        assert [i["id"] for i in items] == [report.id] and items[0]["visibility"] == "organizations"
        assert (await async_test_client.get(f"/api/reports/{report.id}/data")).status_code == 200

    # flip to public → strangers and anonymous may read
    with _as_user(admin):
        v = await async_test_client.put(f"/api/projects/{project.id}/report/visibility", json={"is_public": True})
    assert v.status_code == 200 and v.json()["is_public"] is True
    with _as_user(stranger):
        assert (await async_test_client.get(f"/api/reports/{report.id}/data")).status_code == 200
    # unpublish clears public too
    with _as_user(admin):
        u = await async_test_client.put(f"/api/projects/{project.id}/report/unpublish")
    assert u.json()["is_public"] is False
    with _as_user(None):
        assert (await async_test_client.get(f"/api/reports/{report.id}/data")).status_code == 401


@pytest.mark.asyncio
async def test_visibility_requires_published_and_superadmin(async_test_client, async_test_db):
    admin = await _user(async_test_db, is_superadmin=True)
    plain = await _user(async_test_db)
    ann = await _user(async_test_db)
    project, _ = await _seed_benchmark(async_test_db, admin, ann)
    with _as_user(plain):
        assert (await async_test_client.put(f"/api/projects/{project.id}/report/visibility", json={"is_public": True})).status_code == 403
        assert (await async_test_client.post(f"/api/projects/{project.id}/report/refresh")).status_code == 403
    with _as_user(admin):
        assert (await async_test_client.put(f"/api/projects/{project.id}/report/visibility", json={"is_public": True})).status_code == 400


@pytest.mark.asyncio
async def test_refresh_and_update_keep_snapshot(async_test_client, async_test_db):
    admin = await _user(async_test_db, is_superadmin=True)
    ann = await _user(async_test_db)
    project, report = await _seed_benchmark(async_test_db, admin, ann)

    with _as_user(admin):
        # draft view computes the snapshot once
        d = await async_test_client.get(f"/api/reports/{report.id}/data")
        assert d.status_code == 200 and d.json()["snapshot"]["primary_metric"] == "llm_judge_falloesung"
        # editor saves prose without the snapshot → snapshot survives
        content = d.json()["report"]["content"]
        content.pop("snapshot", None)
        content["sections"]["project_info"]["custom_title"] = "Edited"
        u = await async_test_client.post(f"/api/projects/{project.id}/report", json={"content": content})
        assert u.status_code == 200, u.text
        assert u.json()["content"]["snapshot"]["primary_metric"] == "llm_judge_falloesung"
        assert u.json()["content"]["sections"]["project_info"]["custom_title"] == "Edited"
        # explicit refresh recomputes
        r = await async_test_client.post(f"/api/projects/{project.id}/report/refresh")
        assert r.status_code == 200 and r.json()["content"]["snapshot"]["generated_at"]
