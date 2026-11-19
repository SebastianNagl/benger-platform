"""
The validations behind the report's analyses (shared/report_snapshot.py:
_analysis_code_validations, public_snapshot, apply_section_visibility).

Seeds a synthetic project with a coding project, two completed code
validations (a text pattern code and a judge code of a private BYOM model)
and analysis runs whose ``codes`` accepted them, then checks that the
snapshot copies exactly the stored kappa and per-category metrics, lists
each validation once with the runs and measures reading it, leaves out
codes without a validation, copies a validation's detail only when the
author building the snapshot can open its coding project, keeps
member-only validations out of the public view and honours the report's
``show_code_validations`` switch.
"""

import copy
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from analysis.coding import validation_metrics
from models import CodeValidation, CodingProject
from project_models import Project
from report_models import ProjectReport
from report_snapshot import apply_section_visibility, build_report_snapshot, public_snapshot
from routers.projects.helpers import check_project_accessible
from tests.integration.test_report_analyses import _estimate, _project, _run, _set_analyses
from tests.integration.test_report_snapshot_public import _as_user, _user

# The feature is behind a platform flag (off by default in the suite).
pytestmark = pytest.mark.flags_on("variant_experiments")

# Ten coded items: the automatic code agrees with the single human coder on
# seven, one item has no automatic code (counted as the "(missing)"
# category) and one has two coders who tie (no reference).
ITEMS = (
    [{"task_id": f"t{i}", "automatic": "P", "human": {"u1": "P"}} for i in range(4)]
    + [{"task_id": f"t{i}", "automatic": "D", "human": {"u1": "D"}} for i in range(4, 7)]
    + [{"task_id": "t7", "automatic": "P", "human": {"u1": "D"}}]
    + [{"task_id": "t8", "automatic": None, "human": {"u1": "P"}}]
    + [{"task_id": "t9", "automatic": "P", "human": {"u1": "P", "u2": "D"}}]
)
PATTERN_HASH = "e" * 64
JUDGE_HASH = "f" * 64
SECRET_JUDGE = "custom-judge-model"


def _uid():
    return str(uuid.uuid4())


async def _coding(db, source, creator):
    coding = Project(id=_uid(), title="Coding: side", created_by=creator.id, is_private=True,
                     label_config='<View><Text name="answer" value="$answer"/></View>')
    db.add(coding)
    await db.flush()
    db.add(CodingProject(project_id=coding.id, source_project_id=source.id, answer_source="answer",
                         context_fields=[], sample={"seed": 1, "size": 10}, coding_version=1,
                         created_by=creator.id))
    await db.flush()
    return coding


def _validation(coding, source, creator, *, name, kind, ref, code_hash, identity):
    metrics = validation_metrics(ITEMS)
    main = metrics["automatic_vs_reference"]
    return CodeValidation(
        id=_uid(), project_id=coding.id, source_project_id=source.id, created_by=creator.id, name=name,
        status="completed", control="side", code={"kind": kind}, normalized_code={"kind": kind},
        code_kind=kind, code_ref=ref, code_version="1", code_hash=code_hash, identity=identity,
        options={"missing": "category", "value_map": {}}, coding_version=1, metrics=metrics, items=ITEMS,
        n_items=len(ITEMS), n_compared=metrics["compared"], kappa=main["kappa"],
        observed_agreement=main["observed_agreement"], warnings=[],
        completed_at=datetime(2026, 11, 2, tzinfo=timezone.utc),
    )


def _record(measure, v, *, kind, ref, code_hash, **extra):
    """A run's code record with the validation it accepted, as
    ``check_code_validations`` writes it."""
    return {"measure": measure, "kind": kind, "ref": ref, "version": "1", "hash": code_hash, "missing": 1,
            "rows": 10, **extra,
            "validation": {"id": v.id, "coding_project_id": v.project_id, "control": v.control,
                           "kappa": v.kappa, "observed_agreement": v.observed_agreement,
                           "compared": v.n_compared, "completed_at": v.completed_at.isoformat()}}


async def _seed(db, *, owner=None, coder=None):
    """``owner`` creates the source project (and so authors its report),
    ``coder`` the private coding project; both default to a superadmin."""
    admin = await _user(db, is_superadmin=True)
    project, _, report = await _project(db, owner or admin, title="Coded Bench")
    coding = await _coding(db, project, coder or admin)
    pattern = _validation(coding, project, admin, name="blame pattern", kind="text_pattern",
                          ref="blame@1:claimant", code_hash=PATTERN_HASH,
                          identity={"kind": "text_pattern", "ref": "blame@1:claimant", "hash": PATTERN_HASH})
    judge = _validation(coding, project, admin, name="judge side", kind="judge_code",
                        ref=f"{SECRET_JUDGE}@s1:side", code_hash=JUDGE_HASH,
                        identity={"kind": "judge_code", "system": f"{SECRET_JUDGE}@s1", "field": "side",
                                  "hash": JUDGE_HASH})
    db.add_all([pattern, judge])
    await db.flush()
    first = _run(project.id, admin.id, name="first")
    second = _run(project.id, admin.id, name="second")
    plain = _run(project.id, admin.id, name="no codes")
    first.codes = [
        _record("blames_claimant", pattern, kind="text_pattern", ref="blame@1:claimant", code_hash=PATTERN_HASH),
        _record("judge_side", judge, kind="judge_code", ref=f"{SECRET_JUDGE}@s1:side", code_hash=JUDGE_HASH,
                system=f"{SECRET_JUDGE}@s1"),
        # An exploratory code without a validation is not listed.
        {"measure": "mentions_court", "kind": "text_pattern", "ref": "court@1:any", "version": "1",
         "hash": "0" * 64, "missing": 0, "rows": 10},
    ]
    second.codes = [
        _record("claimant_again", pattern, kind="text_pattern", ref="blame@1:claimant", code_hash=PATTERN_HASH),
    ]
    db.add_all([first, second, plain])
    await db.flush()
    for run in (first, second, plain):
        db.add(_estimate(run.id, 0, "effect", "c", None, [], "linear"))
        run.estimates_count = 1
    await db.flush()
    return {"admin": admin, "project": project, "report": report, "pattern": pattern, "judge": judge,
            "first": first, "second": second, "plain": plain}


def _analyses(*runs):
    return {"visible": True, "runs": [{"run_id": r.id, "exhibits": [{"id": "all", "type": "table"}]} for r in runs]}


async def _snapshot(db, project_id, analyses, author):
    return await db.run_sync(lambda s: build_report_snapshot(
        s, project_id, analyses=analyses, can_open_project=lambda pid: check_project_accessible(s, author, pid)))


@pytest.mark.asyncio
async def test_snapshot_copies_the_stored_validations_behind_the_runs(async_test_db):
    w = await _seed(async_test_db)
    snap = await _snapshot(async_test_db, w["project"].id, _analyses(w["first"], w["second"], w["plain"]), w["admin"])
    validations = snap["analyses"]["code_validations"]

    assert [v["id"] for v in validations] == [w["pattern"].id, w["judge"].id]
    pattern = validations[0]
    stored = w["pattern"]
    main = stored.metrics["automatic_vs_reference"]
    # The numbers are the stored ones, not recomputed.
    assert pattern["kappa"] == stored.kappa == main["kappa"]
    assert pattern["observed_agreement"] == stored.observed_agreement
    assert pattern["compared"] == stored.n_compared == 9
    assert pattern["agreement"] == {k: main[k] for k in ("n", "kappa", "observed_agreement", "expected_agreement")}
    assert pattern["per_category"] == main["per_category"]
    assert pattern["confusion"] == main["confusion"]
    assert pattern["categories"] == stored.metrics["categories"] == ["(missing)", "D", "P"]
    assert pattern["counts"] == {"items": 10, "compared": 9, "ties": 1, "no_human_code": 0,
                                 "missing_automatic": 1, "missing": "category"}
    between = stored.metrics["between_coders"]
    assert pattern["between_coders"] == {"coders": 2, "items": 1, "fleiss_kappa": between["fleiss_kappa"],
                                         "percent_agreement": between["percent_agreement"]}
    # P: four agreeing items, one automatic P against a human D, one
    # missing automatic code against a human P.
    assert pattern["per_category"]["P"]["precision"] == pytest.approx(4 / 5)
    assert pattern["per_category"]["P"]["recall"] == pytest.approx(4 / 5)
    assert {k: pattern[k] for k in ("name", "control", "code_kind", "code_ref", "code_version", "code_hash",
                                    "detail", "member_only")} == {
        "name": "blame pattern", "control": "side", "code_kind": "text_pattern", "code_ref": "blame@1:claimant",
        "code_version": "1", "code_hash": PATTERN_HASH, "detail": True, "member_only": False,
    }
    assert pattern["used_by"] == [{"run_id": w["first"].id, "measure": "blames_claimant"},
                                  {"run_id": w["second"].id, "measure": "claimant_again"}]
    # The per-coder rows name coders and are not copied.
    assert "automatic_vs_coders" not in str(pattern) and "u1" not in str(pattern)
    # A judge code of a hidden (private BYOM) model is member-only.
    assert validations[1]["member_only"] is True
    assert validations[1]["used_by"] == [{"run_id": w["first"].id, "measure": "judge_side"}]

    # Without runs that read codes there is nothing to list.
    plain = await _snapshot(async_test_db, w["project"].id, _analyses(w["plain"]), w["admin"])
    assert plain["analyses"]["code_validations"] == []
    empty = await _snapshot(async_test_db, w["project"].id, None, w["admin"])
    assert empty["analyses"]["code_validations"] == []


@pytest.mark.asyncio
async def test_a_validation_whose_row_is_gone_keeps_what_the_run_accepted(async_test_db):
    w = await _seed(async_test_db)
    await async_test_db.delete(w["judge"])
    await async_test_db.delete(w["pattern"])
    await async_test_db.flush()
    snap = await _snapshot(async_test_db, w["project"].id, _analyses(w["second"]), w["admin"])
    (only,) = snap["analyses"]["code_validations"]
    assert only["detail"] is False and only["kappa"] == w["pattern"].kappa and only["compared"] == 9
    assert "per_category" not in only and only["name"] is None


@pytest.mark.asyncio
async def test_public_view_and_the_switch_withhold_validations(async_test_client, async_test_db):
    w = await _seed(async_test_db)
    snap = await _snapshot(async_test_db, w["project"].id, _analyses(w["first"], w["second"]), w["admin"])
    public = public_snapshot(snap)
    assert [v["id"] for v in public["analyses"]["code_validations"]] == [w["pattern"].id]
    assert SECRET_JUDGE not in str(public["analyses"])
    # Every run here is public, so used_by keeps both.
    assert len(public["analyses"]["code_validations"][0]["used_by"]) == 2

    # A validation only member-only runs read stays inside the project.
    member = copy.deepcopy(snap)
    for run in member["analyses"]["runs"]:
        run["member_only"] = run["id"] == w["second"].id
    for v in member["analyses"]["code_validations"]:
        v["member_only"] = v["id"] != w["pattern"].id
    shown = public_snapshot(member)
    assert [u["run_id"] for u in shown["analyses"]["code_validations"][0]["used_by"]] == [w["first"].id]

    off = apply_section_visibility(snap, {"annotations": {"show_code_validations": False}})
    assert off["analyses"]["code_validations"] == [] and off["analyses"]["runs"] == snap["analyses"]["runs"]
    on = apply_section_visibility(snap, {"annotations": {}})
    assert on["analyses"]["code_validations"] == snap["analyses"]["code_validations"]

    # Through the API: the author sees both, an anonymous reader of the
    # public report only the public one, and none with the switch off.
    report = w["report"]
    await _set_analyses(async_test_db, report, _analyses(w["first"], w["second"]))
    with _as_user(w["admin"]):
        published = await async_test_client.put(f"/api/projects/{w['project'].id}/report/publish")
        assert published.status_code == 200, published.text
    row = (await async_test_db.execute(select(ProjectReport).where(ProjectReport.id == report.id))).scalar_one()
    await async_test_db.refresh(row)
    row.is_public = True
    await async_test_db.flush()
    with _as_user(w["admin"]):
        author = (await async_test_client.get(f"/api/reports/{report.id}/data")).json()
    with _as_user(None):
        anonymous = (await async_test_client.get(f"/api/reports/{report.id}/data")).json()
    assert len(author["snapshot"]["analyses"]["code_validations"]) == 2
    assert [v["id"] for v in anonymous["snapshot"]["analyses"]["code_validations"]] == [w["pattern"].id]
    assert SECRET_JUDGE not in str(anonymous)

    content = copy.deepcopy(row.content)
    content["sections"]["annotations"] = {"show_code_validations": False}
    row.content = content
    await async_test_db.flush()
    with _as_user(None):
        hidden = (await async_test_client.get(f"/api/reports/{report.id}/data")).json()
    assert hidden["snapshot"]["analyses"]["code_validations"] == []


@pytest.mark.asyncio
async def test_detail_only_from_a_coding_project_the_author_can_open(async_test_client, async_test_db):
    author = await _user(async_test_db)
    coder = await _user(async_test_db)
    w = await _seed(async_test_db, owner=author, coder=coder)
    stored = w["pattern"]
    analyses = _analyses(w["second"])

    # The coder created the private coding project and gets its detail.
    (opened,) = (await _snapshot(async_test_db, w["project"].id, analyses, coder))["analyses"]["code_validations"]
    assert opened["detail"] is True and opened["name"] == "blame pattern"
    assert opened["per_category"] == stored.metrics["automatic_vs_reference"]["per_category"]

    # The report's author cannot open it (GET /api/code-validations/{id}
    # answers 404) and gets only what the run recorded.
    with _as_user(author):
        assert (await async_test_client.get(f"/api/code-validations/{stored.id}")).status_code == 404
    (closed,) = (await _snapshot(async_test_db, w["project"].id, analyses, author))["analyses"]["code_validations"]
    assert closed["detail"] is False and closed["name"] is None
    assert closed["kappa"] == stored.kappa and closed["compared"] == 9 and closed["code_hash"] == PATTERN_HASH
    assert not {"per_category", "confusion", "categories", "between_coders", "agreement"} & set(closed)

    # Published by that author and read anonymously as a public report.
    report = w["report"]
    await _set_analyses(async_test_db, report, analyses)
    with _as_user(author):
        published = await async_test_client.put(f"/api/projects/{w['project'].id}/report/publish")
        assert published.status_code == 200, published.text
    row = (await async_test_db.execute(select(ProjectReport).where(ProjectReport.id == report.id))).scalar_one()
    await async_test_db.refresh(row)
    row.is_public = True
    await async_test_db.flush()
    with _as_user(None):
        anonymous = (await async_test_client.get(f"/api/reports/{report.id}/data")).json()
    (served,) = anonymous["snapshot"]["analyses"]["code_validations"]
    assert served["detail"] is False and served["kappa"] == stored.kappa
    assert "blame pattern" not in str(anonymous) and "per_category" not in served

