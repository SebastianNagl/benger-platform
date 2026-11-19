"""
The report's Analyses section (shared/report_snapshot.py: parse_analyses_section,
exhibit_selects, _build_analyses_section; routers/reports.py).

Seeds a synthetic project with completed analysis runs whose estimates cover
three estimands, listed and ``terms`` contrasts, a joint test, two families
and three scopes (pooled, an open system and a private BYOM system), plus runs a report must not show (pending,
cross-project, reading another project's lookup table, another project's
run). Then checks that exhibit filters select exactly the intended rows,
that a published report keeps its numbers when the live data changes, that
cross-project runs are neither offered nor copied nor publishable, that a
run in which a hidden model may appear is member-only (left out of every
public payload, never published as public), and the save validation.
"""

import copy
import math
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, update

from models import AnalysisEstimate, AnalysisRun
from project_models import Annotation, Project, Task
from report_models import ProjectReport
from report_service import REASON_ANALYSIS_RUNS, can_publish_report
from report_snapshot import (
    build_report_snapshot,
    estimate_systems,
    exhibit_selects,
    parse_analyses_section,
    snapshot_sha256,
)
from tests.integration.test_report_snapshot_public import _as_user, _user

# The feature is behind a platform flag (off by default in the suite).
pytestmark = pytest.mark.flags_on("variant_experiments")

OPEN = "open-model@p1"
SECRET = "custom-secret-model@p2"
OTHER = "other-model@p3"


def _uid() -> str:
    return str(uuid.uuid4())


async def _project(db, creator, *, title="Analyses Bench"):
    project = Project(id=_uid(), title=title, description="seeded", created_by=creator.id,
                      label_config='<View><Text name="text" value="$text"/></View>')
    db.add(project)
    await db.flush()
    task = Task(id=_uid(), project_id=project.id, data={"text": "case"}, created_by=creator.id, inner_id=1)
    db.add(task)
    await db.flush()
    report = ProjectReport(
        id=_uid(), project_id=project.id, created_by=creator.id, is_published=False,
        content={"sections": {"project_info": {"title": title, "description": "d", "status": "completed",
                                               "editable": True, "visible": True}},
                 "metadata": {"sections_completed": ["project_info"], "can_publish": False}},
    )
    db.add(report)
    await db.flush()
    return project, task, report


PUBLIC_MODELS = ["open-model", "other-model"]


def _run(project_id, creator_id, *, name="main", status="completed", spec=None, warnings=None, fits=None,
         models=PUBLIC_MODELS):
    spec = spec if spec is not None else {"inputs": {"designs": ["framing"]}}
    resolved = None if models is None else {"projects": [], "lookups": [], "models": models}
    return AnalysisRun(
        id=_uid(), project_id=project_id, created_by=creator_id, name=name, status=status,
        spec=spec, normalized_spec=spec, spec_hash="a" * 64, spec_version=1, engine_version="1.1.0",
        frame_hash="b" * 64, frame_sha256="c" * 64, frame_rows=48, estimates_count=0,
        library_versions={"numpy": "2.0.0"}, lockfile_sha256="d" * 64, seed=11, warnings=warnings, fits=fits,
        resolved_inputs=resolved,
        completed_at=datetime(2026, 11, 1, tzinfo=timezone.utc) if status == "completed" else None,
    )


def _adjustment(family, p):
    return {"family": family, "method": "holm", "group": [], "size": 4, "p_adjusted": p}


# The main run's normalized spec and fits. ``model_gap`` has a contrast with
# a neutral label that weights the private system and a joint test whose
# parameter pattern matches both systems of its fit. The frontend test of
# the same rule (services/frontend/src/lib/reports/__tests__/analyses.test.ts)
# uses the same spec, fits, rows and cases.
SPEC = {
    "inputs": {"designs": ["framing"]},
    "estimands": [
        {"id": "framing_effect", "contrasts": [
            {"id": "loaded_vs_neutral", "kind": "linear", "weights": {"framing[loaded]": 1}},
            {"id": "order_effect", "kind": "linear", "weights": {"order[second]": 1}},
        ]},
        {"id": "length_effect", "contrasts": "terms"},
        {"id": "model_gap",
         "contrasts": [{"id": "secret_vs_ref", "kind": "linear", "weights": {f"system[{SECRET}]": 1}}],
         "joint_tests": [{"id": "any_system", "parameters": ["system[*]"]}]},
    ],
}
# The fits record the reference of their system dummies: OTHER for
# model_gap, SECRET for length_effect, whose terms contrasts are therefore
# measured against the private system.
FITS = [{"estimand": "model_gap", "scope": "pooled",
         "parameters": ["(intercept)", f"system[{OPEN}]", f"system[{SECRET}]"], "references": {"system": OTHER}},
        {"estimand": "length_effect", "scope": "pooled",
         "parameters": ["(intercept)", f"system[{OPEN}]", f"system[{OTHER}]"], "references": {"system": SECRET}}]

# Position -> (estimand, contrast, scope values, families, kind). Families
# are the estimate's first ``family`` plus every ``adjustments`` membership.
# Involved systems: none for 0, 3, 5; OPEN for 1, 4, 6; SECRET for 2; the
# ``terms`` contrasts against the SECRET reference involve OTHER and SECRET
# (7) or OPEN and SECRET (8); the neutral-label contrast 9 involves SECRET
# (through its weights only) and the OTHER reference; the joint test 10
# involves OPEN, SECRET and OTHER.
ROWS = [
    (0, "framing_effect", "loaded_vs_neutral", None, ["primary"], "linear"),
    (1, "framing_effect", "loaded_vs_neutral", {"system": OPEN}, ["primary"], "linear"),
    (2, "framing_effect", "loaded_vs_neutral", {"system": SECRET}, ["primary"], "linear"),
    (3, "framing_effect", "order_effect", None, ["primary", "secondary"], "linear"),
    (4, "framing_effect", "order_effect", {"system": OPEN}, ["secondary"], "linear"),
    (5, "length_effect", "long_vs_short", None, [], "linear"),
    (6, "length_effect", "long_vs_short", {"system": OPEN}, ["secondary"], "linear"),
    (7, "length_effect", f"system[{OTHER}]", None, [], "linear"),
    (8, "length_effect", f"system[{OPEN}]", None, [], "linear"),
    (9, "model_gap", "secret_vs_ref", None, [], "linear"),
    (10, "model_gap", "any_system", None, [], "wald"),
]


def _scope(scope_values):
    return "pooled" if scope_values is None else ",".join(f"{k}={v}" for k, v in scope_values.items())


def _estimate(run_id, position, estimand, contrast, scope_values, families, kind):
    return AnalysisEstimate(
        run_id=run_id, position=position, estimand_id=estimand, contrast_id=contrast, estimator="ols",
        kind=kind, outcome="score", scope=_scope(scope_values), scope_values=scope_values, status="ok",
        estimate=0.1 * (position + 1), std_error=0.05, statistic=2.0, df=40, p_value=0.04,
        null_value=0.0, ci_level=0.95, ci_lower=0.1 * position - 0.05, ci_upper=0.1 * position + 0.25,
        tost=[{"lower": -0.2, "upper": 0.2, "level": 0.9, "ci_lower": 0.0, "ci_upper": 0.3,
               "p_lower": 0.01, "p_upper": 0.2, "p_tost": 0.2, "equivalent": False}],
        family=families[0] if families else None,
        p_adjusted=0.08 if families else None,
        adjustments=[_adjustment(f, 0.08) for f in families] or None,
        n_obs=40, n_clusters=[8], k_params=3,
    )


async def _seed_runs(db, project, admin, *, other_project_id=None):
    main = _run(project.id, admin.id, spec=SPEC, fits=FITS, models=PUBLIC_MODELS + ["custom-secret-model"],
                warnings=["fit converged", f"system {SECRET} has one cluster", "model_gap [pooled]: one cluster"])
    pending = _run(project.id, admin.id, name="pending", status="pending")
    cross = _run(project.id, admin.id, name="cross",
                 spec={"inputs": {"designs": ["framing"], "projects": [{"project_id": _uid(), "designs": ["x"]}]}})
    lookup = _run(project.id, admin.id, name="lookup",
                  spec={"inputs": {"designs": ["framing"]},
                        "lookups": [{"table": {"name": "gold", "version": 1, "project_id": _uid()}}]})
    own_lookup = _run(project.id, admin.id, name="own lookup",
                      spec={"inputs": {"designs": ["framing"]},
                            "lookups": [{"table": {"name": "gold", "version": 1, "project_id": project.id}}]})
    db.add_all([main, pending, cross, lookup, own_lookup])
    await db.flush()
    for row in ROWS:
        db.add(_estimate(main.id, *row))
    main.estimates_count = len(ROWS)
    await db.flush()
    return {"main": main, "pending": pending, "cross": cross, "lookup": lookup, "own_lookup": own_lookup}


async def _public_run(db, project, admin, *, name="open"):
    """A run of public models only: the rows of ROWS without the private
    system."""
    run = _run(project.id, admin.id, name=name, spec=SPEC)
    db.add(run)
    await db.flush()
    rows = [r for r in ROWS if r[0] != 2]
    for row in rows:
        db.add(_estimate(run.id, *row))
    run.estimates_count = len(rows)
    await db.flush()
    return run


def _section(run_id, exhibits, **run):
    return {"visible": True, "custom_text": "Intro", "runs": [{"run_id": run_id, "exhibits": exhibits, **run}]}


async def _snapshot(db, project_id, analyses, **kw):
    return await db.run_sync(lambda s: build_report_snapshot(s, project_id, analyses=analyses, **kw))


async def _set_analyses(db, report, analyses):
    content = copy.deepcopy(report.content)
    content["sections"]["analyses"] = analyses
    report.content = content
    await db.flush()


# ---------------------------------------------------------------------------
# filters
# ---------------------------------------------------------------------------

def _row_dict(position, estimand, contrast, scope_values, families, kind):
    return {"position": position, "estimand_id": estimand, "contrast_id": contrast, "kind": kind,
            "scope": _scope(scope_values), "scope_values": scope_values,
            "family": families[0] if families else None,
            "adjustments": [_adjustment(f, 0.1) for f in families] or None}


@pytest.mark.parametrize("filters,expected", [
    ({}, list(range(11))),
    ({"estimands": ["length_effect"]}, [5, 6, 7, 8]),
    ({"contrasts": ["order_effect"]}, [3, 4]),
    ({"estimands": ["framing_effect"], "contrasts": ["long_vs_short"]}, []),
    # A family matches any membership, not only the first one.
    ({"families": ["secondary"]}, [3, 4, 6]),
    ({"families": ["primary", "secondary"]}, [0, 1, 2, 3, 4, 6]),
    # A systems filter keeps the estimates whose involved systems are all
    # listed: no pooled estimate involving no system, no contrast of another
    # system against the reference (7), none of OPEN against the SECRET
    # reference (8), no joint test over both (10).
    ({"systems": [OPEN]}, [1, 4, 6]),
    ({"systems": [OPEN, SECRET]}, [1, 2, 4, 6, 8]),
    ({"systems": [OPEN, SECRET, OTHER]}, [1, 2, 4, 6, 7, 8, 9, 10]),
    ({"systems": ["nobody"]}, []),
    ({"estimands": ["framing_effect"], "systems": [OPEN], "families": ["primary"]}, [1]),
    ({"estimands": ["model_gap"]}, [9, 10]),
])
def test_exhibit_selects_exactly_the_filtered_rows(filters, expected):
    rows = [_row_dict(*r) for r in ROWS]
    assert [r["position"] for r in rows if exhibit_selects(r, filters, estimate_systems(r, SPEC, FITS))] == expected


def test_exhibit_selects_model_id_scope_as_system():
    row = {"position": 0, "estimand_id": "e", "contrast_id": "c", "scope_values": {"model_id": "m1"}}
    systems = estimate_systems(row, {})
    assert systems == {"m1"}
    assert exhibit_selects(row, {"systems": ["m1"]}, systems) is True
    assert exhibit_selects(row, {"systems": ["m2"]}, systems) is False


FIT = {"estimand": "e", "scope": "pooled", "parameters": [], "references": {}}


@pytest.mark.parametrize("estimand,fits,row,expected", [
    # Joint test rows name their weight keys, also inside an interaction.
    ({"id": "e", "contrasts": [], "joint_tests": [{"id": "j", "rows": [{"system[a@1]": 1}, {"x[1]:system[b@2]": 1}]}]},
     None, {"contrast_id": "j", "kind": "wald"}, {"a@1", "b@2"}),
    # A joint test over listed contrasts takes their weights.
    ({"id": "e", "contrasts": [{"id": "c1", "weights": {"model_id[m]": 1}}],
      "joint_tests": [{"id": "j", "contrasts": ["c1"]}]},
     None, {"contrast_id": "j", "kind": "wald"}, {"m"}),
    # A literal parameter pattern counts even without a matching fit.
    ({"id": "e", "contrasts": "terms", "joint_tests": [{"id": "j", "parameters": ["system[a@1]"]}]},
     None, {"contrast_id": "j", "kind": "wald"}, {"a@1"}),
    # Ratio numerator and denominator, and the levels of a marginal effect.
    ({"id": "e", "contrasts": [{"id": "r", "kind": "ratio", "numerator": {"weights": {"system[a@1]": 1}},
                                "denominator": {"weights": {"system[b@2]": 1}}}]},
     None, {"contrast_id": "r", "kind": "ratio"}, {"a@1", "b@2"}),
    ({"id": "e", "contrasts": [{"id": "m", "kind": "ame", "column": "system", "level": "a@1", "reference": "b@2"}]},
     None, {"contrast_id": "m", "kind": "ame"}, {"a@1", "b@2"}),
    ({"id": "e", "contrasts": [{"id": "m", "kind": "ame", "column": "framing", "level": "x", "reference": "y"}]},
     None, {"contrast_id": "m", "kind": "ame"}, set()),
    # A paired treatment over the system column involves both of its levels.
    ({"id": "e", "treatment": {"factor": "system", "level": "a@1", "reference": "b@2"}, "contrasts": "terms"},
     None, {"contrast_id": "(difference)", "kind": "linear"}, {"a@1", "b@2"}),
    # A system parameter is measured against the reference its fit recorded,
    # also inside an interaction; the recorded one wins over the declared.
    ({"id": "e", "contrasts": "terms", "terms": [{"dummies": "system", "reference": "d@9"}]},
     [{**FIT, "references": {"system": "r@0"}}], {"contrast_id": "system[a@1]", "kind": "linear"}, {"a@1", "r@0"}),
    ({"id": "e", "contrasts": "terms"},
     [{**FIT, "references": {"system": "r@0", "framing": "neutral"}}],
     {"contrast_id": "framing[loaded]:system[a@1]", "kind": "linear"}, {"a@1", "r@0"}),
    # A parameter of another factor brings no system reference along.
    ({"id": "e", "contrasts": "terms"},
     [{**FIT, "references": {"system": "r@0", "framing": "neutral"}}],
     {"contrast_id": "framing[loaded]", "kind": "linear"}, set()),
    # A run whose fits record no references: the declared reference, also of
    # an interaction, and none when the spec declares none.
    ({"id": "e", "contrasts": "terms", "terms": [{"interact": [{"dummies": "system", "reference": "d@9"}, "x"]}]},
     [{"estimand": "e", "scope": "pooled", "parameters": []}],
     {"contrast_id": "system[a@1]:x", "kind": "linear"}, {"a@1", "d@9"}),
    ({"id": "e", "contrasts": "terms", "terms": [{"dummies": "system"}]},
     None, {"contrast_id": "system[a@1]", "kind": "linear"}, {"a@1"}),
    # Bradley-Terry strengths are systems only when the fit says the players are.
    ({"id": "e", "estimator": "bradley_terry", "contrasts": "terms"},
     [{**FIT, "references": {"strength": "r@0"}, "players_are_systems": True}],
     {"contrast_id": "strength[a@1]", "kind": "linear"}, {"a@1", "r@0"}),
    ({"id": "e", "estimator": "bradley_terry", "contrasts": "terms"},
     [{**FIT, "references": {"strength": "r@0"}, "players_are_systems": False}],
     {"contrast_id": "strength[a@1]", "kind": "linear"}, set()),
])
def test_estimate_systems_reads_the_spec(estimand, fits, row, expected):
    estimate = {"estimand_id": "e", "scope": "pooled", "scope_values": None, **row}
    assert estimate_systems(estimate, {"estimands": [estimand]}, fits) == expected


def test_parse_normalizes_and_reports_every_problem():
    parsed = parse_analyses_section({
        "runs": [{"run_id": "r1", "title": "", "exhibits": [
            {"id": "f1", "type": "forest", "filters": {"systems": ["b", "a", "b"], "families": []}},
            {"id": "t1", "type": "table", "band": 2},
        ]}],
    }, strict=True)
    assert parsed["visible"] is True and parsed["custom_text"] is None
    [run] = parsed["runs"]
    assert run["title"] is None
    forest, table = run["exhibits"]
    assert forest["filters"] == {"systems": ["a", "b"]} and forest["band"] == 0
    assert table["band"] is None and table["filters"] == {}

    with pytest.raises(ValueError) as err:
        parse_analyses_section({"visible": "yes", "runs": [
            {"run_id": "r1", "exhibits": [{"id": "bad id", "type": "profile", "filters": {"models": ["x"]}}]},
            {"run_id": "r1", "exhibits": []},
            {"run_id": "r2", "exhibits": [{"id": "a", "type": "table"}, {"id": "a", "type": "forest"}]},
        ]}, strict=True)
    errors = err.value.errors
    assert any("analyses.visible" in e for e in errors)
    assert any("exhibits[0].id" in e for e in errors)
    assert any("exhibits[0].type" in e for e in errors)
    assert any("filters.models" in e for e in errors)
    assert any("listed twice" in e for e in errors)
    assert any("used twice" in e for e in errors)

    # Reading stored content leaves out what does not parse.
    lenient = parse_analyses_section({"runs": [
        {"run_id": "r1", "exhibits": [{"id": "x", "type": "profile"}, {"id": "y", "type": "table"}]},
        "junk",
    ]})
    assert [[e["id"] for e in r["exhibits"]] for r in lenient["runs"]] == [["y"]]
    assert parse_analyses_section(None)["runs"] == [] and parse_analyses_section("x")["runs"] == []


# ---------------------------------------------------------------------------
# snapshot
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_snapshot_copies_run_metadata_and_selected_estimates(async_test_db):
    admin = await _user(async_test_db, is_superadmin=True)
    project, _, _ = await _project(async_test_db, admin)
    runs = await _seed_runs(async_test_db, project, admin)
    main = runs["main"]

    snap = await _snapshot(async_test_db, project.id, _section(main.id, [
        {"id": "forest-primary", "type": "forest", "filters": {"families": ["primary"]}, "band": None},
        {"id": "table-length", "type": "table", "filters": {"estimands": ["length_effect"], "systems": [OPEN]}},
        {"id": "table-none", "type": "table", "filters": {"contrasts": ["no_such_contrast"]}},
    ]))

    [run] = snap["analyses"]["runs"]
    assert snap["analyses"]["omitted"] == []
    assert (run["id"], run["name"], run["spec_hash"], run["engine_version"]) == (main.id, "main", "a" * 64, "1.1.0")
    assert (run["frame_hash"], run["frame_sha256"], run["frame_rows"], run["estimates_count"]) == ("b" * 64, "c" * 64, 48, 11)
    assert run["completed_at"].startswith("2026-11-01") and run["truncated"] is False
    forest, length, empty = run["exhibits"]
    assert forest == {"id": "forest-primary", "type": "forest", "filters": {"families": ["primary"]},
                      "band": None, "row_count": 4, "positions": [0, 1, 2, 3]}
    assert length["positions"] == [6] and length["band"] is None and length["row_count"] == 1
    assert empty["positions"] == [] and empty["row_count"] == 0
    # The run carries the union of its exhibits' estimates, in engine order,
    # with every engine field and no database row id.
    assert [e["position"] for e in run["estimates"]] == [0, 1, 2, 3, 6]
    first = run["estimates"][0]
    assert "id" not in first and "run_id" not in first
    assert (first["estimand_id"], first["contrast_id"], first["estimate"]) == ("framing_effect", "loaded_vs_neutral", 0.1)
    assert first["tost"][0]["upper"] == 0.2 and first["adjustments"][0]["family"] == "primary"
    assert run["families"] == [{"family": "primary", "method": "holm", "size": 4},
                               {"family": "secondary", "method": "holm", "size": 4}]
    # The stored snapshot is whole: a private model is in this run, so it is
    # member-only rather than filtered.
    assert run["member_only"] is True
    assert run["warnings"] == ["fit converged", f"system {SECRET} has one cluster", "model_gap [pooled]: one cluster"]
    assert snap["reproducibility"]["snapshot_sha256"] == snapshot_sha256(snap)


# Runs of public models only, each with one place a private model may hide.
HIDDEN = "custom-secret-model"
MEMBER_ONLY_CASES = {
    "public": dict(fits=[{"estimand": "e", "scope": "pooled", "parameters": [f"system[{OPEN}]"],
                          "references": {"system": "other-model@p3"}}]),
    "hidden system": dict(models=PUBLIC_MODELS + [HIDDEN]),
    "hidden reference": dict(fits=[{"estimand": "e", "scope": "pooled", "parameters": [f"system[{OPEN}]"],
                                    "references": {"system": SECRET}}]),
    "hidden player": dict(fits=[{"estimand": "bt", "scope": "pooled", "parameters": ["strength[open-model@p1]"],
                                 "references": {"strength": "ref"}, "players": ["ref", OPEN, SECRET],
                                 "players_are_systems": False}]),
    "neutral-label contrast": dict(fits=[{"estimand": "e", "scope": "pooled",
                                          "parameters": ["(intercept)", f"framing[loaded]:system[{SECRET}]"]}]),
    "hidden scope": dict(scope={"opponent": SECRET}),
    "models not recorded": dict(models=None),
}


@pytest.mark.asyncio
async def test_a_run_is_member_only_when_a_hidden_model_may_appear_in_it(async_test_client, async_test_db):
    admin = await _user(async_test_db, is_superadmin=True)
    project, _, _ = await _project(async_test_db, admin)
    for name, case in MEMBER_ONLY_CASES.items():
        run = _run(project.id, admin.id, name=name, fits=case.get("fits"), models=case.get("models", PUBLIC_MODELS))
        async_test_db.add(run)
        await async_test_db.flush()
        async_test_db.add(_estimate(run.id, 0, "e", "c", case.get("scope"), [], "linear"))
    await async_test_db.flush()

    with _as_user(admin):
        offered = (await async_test_client.get(f"/api/projects/{project.id}/report/analysis-runs")).json()["items"]
    assert {r["name"]: r["member_only"] for r in offered} == {
        "public": False, "hidden system": True, "hidden reference": True, "hidden player": True,
        "neutral-label contrast": True, "hidden scope": True, "models not recorded": True,
    }


@pytest.mark.asyncio
async def test_member_only_runs_are_left_out_of_public_payloads(async_test_client, async_test_db):
    admin = await _user(async_test_db, is_superadmin=True)
    project, _, report = await _project(async_test_db, admin)
    main = (await _seed_runs(async_test_db, project, admin))["main"]
    public = await _public_run(async_test_db, project, admin)
    analyses = {"runs": [{"run_id": main.id, "title": f"How {SECRET} did", "text": f"{SECRET} leads.",
                          "exhibits": [{"id": "all", "type": "table", "caption": f"Rows of {SECRET}",
                                        "filters": {"systems": [SECRET]}}]},
                         {"run_id": public.id, "title": "Open models", "exhibits": [{"id": "all", "type": "table"}]}]}
    await _set_analyses(async_test_db, report, analyses)

    with _as_user(admin):
        # A report holding a member-only run cannot be published as public...
        refused = await async_test_client.put(f"/api/projects/{project.id}/report/publish", json={"is_public": True})
        assert refused.status_code == 400
        assert refused.json()["detail"] == (
            "A public report cannot show an analysis run in which a private model may appear")
        # ...nor switched to public once published for the organizations.
        published = await async_test_client.put(f"/api/projects/{project.id}/report/publish")
        assert published.status_code == 200, published.text
        switched = await async_test_client.put(f"/api/projects/{project.id}/report/visibility",
                                               json={"is_public": True})
        assert switched.status_code == 400
    row = (await async_test_db.execute(select(ProjectReport).where(ProjectReport.id == report.id))).scalar_one()
    await async_test_db.refresh(row)
    assert row.is_public is False

    # A report already public (made so before the run was added) withholds
    # the member-only run from every public payload; members see all.
    row.is_public = True
    await async_test_db.flush()
    with _as_user(None):
        anonymous = (await async_test_client.get(f"/api/reports/{report.id}/data")).json()
    with _as_user(admin):
        author = (await async_test_client.get(f"/api/reports/{report.id}/data")).json()
    public_runs = anonymous["snapshot"]["analyses"]["runs"]
    assert [r["id"] for r in public_runs] == [public.id]
    assert "custom-secret-model" not in str(anonymous["snapshot"]["analyses"])
    # Nothing of the member-only run reaches the public reader: neither its
    # numbers nor the author's title, text, captions and filters naming the
    # private model.
    assert "custom-secret-model" not in str(anonymous)
    assert [r["run_id"] for r in anonymous["report"]["content"]["sections"]["analyses"]["runs"]] == [public.id]
    assert [r["run_id"] for r in author["report"]["content"]["sections"]["analyses"]["runs"]] == [main.id, public.id]
    # The public run is served unchanged.
    stored = {r["id"]: r for r in author["snapshot"]["analyses"]["runs"]}
    assert public_runs[0] == stored[public.id] and stored[public.id]["member_only"] is False
    assert stored[main.id]["member_only"] is True
    assert [e["position"] for e in stored[main.id]["estimates"]] == [2]


@pytest.mark.asyncio
async def test_member_only_runs_are_left_out_of_the_public_reproducibility_list(async_test_client, async_test_db):
    # The reproducibility list names every run of the project, also runs the
    # Analyses section does not show; a member-only run's name and hashes
    # stay inside the project even when the author named it after the
    # private model.
    admin = await _user(async_test_db, is_superadmin=True)
    project, _, report = await _project(async_test_db, admin)
    hidden = _run(project.id, admin.id, name=f"{SECRET} only", models=["custom-secret-model"])
    async_test_db.add(hidden)
    await async_test_db.flush()
    public = await _public_run(async_test_db, project, admin)
    await _set_analyses(async_test_db, report, {"runs": [
        {"run_id": public.id, "title": "Open models", "exhibits": [{"id": "all", "type": "table"}]}]})

    with _as_user(admin):
        published = await async_test_client.put(f"/api/projects/{project.id}/report/publish",
                                                json={"is_public": True})
        assert published.status_code == 200, published.text
        author = (await async_test_client.get(f"/api/reports/{report.id}/data")).json()
    with _as_user(None):
        anonymous = (await async_test_client.get(f"/api/reports/{report.id}/data")).json()

    stored = {r["name"]: r["member_only"] for r in author["snapshot"]["reproducibility"]["analysis_runs"]}
    assert stored == {f"{SECRET} only": True, "open": False}
    public_list = anonymous["snapshot"]["reproducibility"]["analysis_runs"]
    assert [r["id"] for r in public_list] == [public.id]
    assert "custom-secret-model" not in str(anonymous)
    assert hidden.id not in str(anonymous)
    # The stored snapshot and its hash stay whole.
    assert anonymous["snapshot"]["reproducibility"]["snapshot_sha256"] == (
        author["snapshot"]["reproducibility"]["snapshot_sha256"])


@pytest.mark.asyncio
async def test_cross_project_runs_are_not_offered_copied_or_publishable(async_test_client, async_test_db):
    admin = await _user(async_test_db, is_superadmin=True)
    project, _, report = await _project(async_test_db, admin)
    runs = await _seed_runs(async_test_db, project, admin)
    other, _, _ = await _project(async_test_db, admin, title="Other")
    foreign = _run(other.id, admin.id, name="foreign")
    async_test_db.add(foreign)
    await async_test_db.flush()

    with _as_user(admin):
        offered = await async_test_client.get(f"/api/projects/{project.id}/report/analysis-runs")
    assert offered.status_code == 200, offered.text
    # Completed runs that read no further project; a lookup table of the
    # project itself does not make a run cross-project.
    assert {r["name"] for r in offered.json()["items"]} == {"main", "own lookup"}
    item = next(r for r in offered.json()["items"] if r["name"] == "main")
    assert item["spec_hash"] == "a" * 64 and item["estimates_count"] == 11 and item["completed_at"]
    assert item["member_only"] is True

    # The reproducibility appendix follows the same rule.
    snap = await _snapshot(async_test_db, project.id, None)
    assert {r["name"] for r in snap["reproducibility"]["analysis_runs"]} == {"main", "own lookup"}

    analyses = {"runs": [{"run_id": runs[k].id, "exhibits": [{"id": "t", "type": "table"}]}
                         for k in ("cross", "lookup", "pending", "main")]
                + [{"run_id": foreign.id, "exhibits": []}]}
    snap = await _snapshot(async_test_db, project.id, analyses)
    assert [r["id"] for r in snap["analyses"]["runs"]] == [runs["main"].id]
    assert snap["analyses"]["omitted"] == [
        {"run_id": runs["cross"].id, "reason": "reads_other_projects"},
        {"run_id": runs["lookup"].id, "reason": "reads_other_projects"},
        {"run_id": runs["pending"].id, "reason": "not_completed"},
        # Another project's run is not found, so ids cannot be probed.
        {"run_id": foreign.id, "reason": "not_found"},
    ]

    await _set_analyses(async_test_db, report, analyses)
    assert await async_test_db.run_sync(lambda s: can_publish_report(s, project.id)) == (False, REASON_ANALYSIS_RUNS)
    with _as_user(admin):
        refused = await async_test_client.put(f"/api/projects/{project.id}/report/publish")
    assert refused.status_code == 400 and "Analyses section" in refused.json()["detail"]

    await _set_analyses(async_test_db, report, _section(runs["main"].id, []))
    assert await async_test_db.run_sync(lambda s: can_publish_report(s, project.id)) == (True, "All requirements met")


@pytest.mark.asyncio
async def test_published_report_keeps_its_analyses_when_live_data_changes(async_test_client, async_test_db):
    admin = await _user(async_test_db, is_superadmin=True)
    project, task, report = await _project(async_test_db, admin)
    main = await _public_run(async_test_db, project, admin, name="main")
    analyses = _section(main.id, [{"id": "forest", "type": "forest", "filters": {"contrasts": ["loaded_vs_neutral"]}},
                                  {"id": "table", "type": "table", "filters": {"estimands": ["length_effect"]}}],
                        title="Framing", text="What the run shows.")

    with _as_user(admin):
        saved = await async_test_client.post(f"/api/projects/{project.id}/report",
                                             json={"content": {**report.content,
                                                               "sections": {**report.content["sections"],
                                                                            "analyses": analyses}}})
        assert saved.status_code == 200, saved.text
        published = await async_test_client.put(f"/api/projects/{project.id}/report/publish", json={"is_public": True})
        assert published.status_code == 200, published.text
        before = (await async_test_client.get(f"/api/reports/{report.id}/data")).json()

    assert [r["id"] for r in before["snapshot"]["analyses"]["runs"]] == [main.id]

    # The live data changes: the project's data, the stored estimates (runs
    # are immutable, but the copy must not depend on it) and a new run.
    async_test_db.add(Task(id=_uid(), project_id=project.id, data={"text": "new"}, created_by=admin.id, inner_id=2))
    async_test_db.add(Annotation(id=_uid(), task_id=task.id, project_id=project.id, completed_by=admin.id,
                                 result=[], was_cancelled=False))
    await async_test_db.execute(update(AnalysisEstimate).where(AnalysisEstimate.run_id == main.id)
                                .values(estimate=99.0, ci_lower=98.0, ci_upper=100.0))
    await async_test_db.execute(AnalysisEstimate.__table__.delete().where(AnalysisEstimate.position == 5))
    async_test_db.add(_run(project.id, admin.id, name="later"))
    await async_test_db.flush()

    with _as_user(None):
        after = (await async_test_client.get(f"/api/reports/{report.id}/data")).json()
    with _as_user(admin):
        after_author = (await async_test_client.get(f"/api/reports/{report.id}/data")).json()

    assert after["snapshot"]["analyses"]["runs"] == before["snapshot"]["analyses"]["runs"]
    assert after_author["snapshot"] == before["snapshot"]
    assert after["report"]["content"]["sections"]["analyses"]["runs"][0]["title"] == "Framing"
    # A refresh takes the live numbers.
    with _as_user(admin):
        refreshed = (await async_test_client.post(f"/api/projects/{project.id}/report/refresh")).json()
    run = refreshed["content"]["snapshot"]["analyses"]["runs"][0]
    assert {e["estimate"] for e in run["estimates"]} == {99.0}
    assert 5 not in [e["position"] for e in run["estimates"]]


@pytest.mark.asyncio
async def test_public_view_leaves_out_omitted_runs(async_test_client, async_test_db):
    admin = await _user(async_test_db, is_superadmin=True)
    project, _, report = await _project(async_test_db, admin)
    runs = await _seed_runs(async_test_db, project, admin)
    runs["main"] = await _public_run(async_test_db, project, admin)
    await _set_analyses(async_test_db, report, {"runs": [{"run_id": runs["main"].id, "exhibits": []},
                                                         {"run_id": runs["pending"].id, "exhibits": []}]})
    snap = await _snapshot(async_test_db, project.id, report.content["sections"]["analyses"])
    report.content = {**report.content, "snapshot": snap}
    report.is_published = True
    report.is_public = True
    report.published_at = datetime.utcnow()
    await async_test_db.flush()

    with _as_user(None):
        public = (await async_test_client.get(f"/api/reports/{report.id}/data")).json()
    with _as_user(admin):
        author = (await async_test_client.get(f"/api/reports/{report.id}/data")).json()
    assert "omitted" not in public["snapshot"]["analyses"]
    assert [r["id"] for r in public["snapshot"]["analyses"]["runs"]] == [runs["main"].id]
    assert author["snapshot"]["analyses"]["omitted"] == [{"run_id": runs["pending"].id, "reason": "not_completed"}]


@pytest.mark.asyncio
async def test_runs_are_truncated_beyond_the_limit(async_test_db, monkeypatch):
    import report_snapshot

    monkeypatch.setattr(report_snapshot, "MAX_REPORT_ESTIMATES_PER_RUN", 3)
    admin = await _user(async_test_db, is_superadmin=True)
    project, _, _ = await _project(async_test_db, admin)
    main = (await _seed_runs(async_test_db, project, admin))["main"]
    snap = await _snapshot(async_test_db, project.id, _section(main.id, [
        {"id": "a", "type": "table", "filters": {"estimands": ["length_effect"]}},
        {"id": "b", "type": "table", "filters": {"contrasts": ["loaded_vs_neutral"]}},
    ]))
    [run] = snap["analyses"]["runs"]
    assert run["truncated"] is True
    assert [e["position"] for e in run["estimates"]] == [0, 1, 2]
    a, b = run["exhibits"]
    assert (a["row_count"], a["positions"]) == (4, [])
    assert (b["row_count"], b["positions"]) == (3, [0, 1, 2])


@pytest.mark.asyncio
async def test_non_finite_numbers_are_stored_as_null(async_test_client, async_test_db):
    admin = await _user(async_test_db, is_superadmin=True)
    project, _, report = await _project(async_test_db, admin)
    main = (await _seed_runs(async_test_db, project, admin))["main"]
    await async_test_db.execute(update(AnalysisEstimate).where(AnalysisEstimate.run_id == main.id,
                                                               AnalysisEstimate.position == 0)
                                .values(p_value=float("nan"), statistic=float("inf")))
    await _set_analyses(async_test_db, report, _section(main.id, [{"id": "t", "type": "table"}]))
    await async_test_db.flush()
    with _as_user(admin):
        published = await async_test_client.put(f"/api/projects/{project.id}/report/publish")
    assert published.status_code == 200, published.text
    first = published.json()["content"]["snapshot"]["analyses"]["runs"][0]["estimates"][0]
    assert first["p_value"] is None and first["statistic"] is None
    assert not any(isinstance(v, float) and math.isnan(v) for v in first.values())


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_save_validates_and_normalizes_the_section(async_test_client, async_test_db):
    admin = await _user(async_test_db, is_superadmin=True)
    project, _, report = await _project(async_test_db, admin)

    def body(analyses):
        return {"content": {**report.content, "sections": {**report.content["sections"], "analyses": analyses}}}

    with _as_user(admin):
        bad = await async_test_client.post(f"/api/projects/{project.id}/report",
                                           json=body({"runs": [{"run_id": "r", "exhibits": [{"id": "x", "type": "pie"}]}]}))
        good = await async_test_client.post(f"/api/projects/{project.id}/report",
                                            json=body({"runs": [{"run_id": "r", "exhibits": [
                                                {"id": "x", "type": "forest", "filters": {"systems": ["b", "a"]}}]}]}))
    assert bad.status_code == 422
    assert bad.json()["detail"]["code"] == "invalid_report_analyses"
    assert any("exhibits[0].type" in e for e in bad.json()["detail"]["errors"])
    assert good.status_code == 200, good.text
    stored = good.json()["content"]["sections"]["analyses"]
    assert stored["runs"][0]["exhibits"][0] == {"id": "x", "type": "forest", "title": None, "caption": None,
                                                "filters": {"systems": ["a", "b"]}, "band": 0}
    row = (await async_test_db.execute(select(ProjectReport).where(ProjectReport.id == report.id))).scalar_one()
    await async_test_db.refresh(row)
    assert row.content["sections"]["analyses"] == stored


@pytest.mark.asyncio
async def test_only_report_authors_list_runs(async_test_client, async_test_db):
    admin = await _user(async_test_db, is_superadmin=True)
    stranger = await _user(async_test_db)
    project, _, _ = await _project(async_test_db, admin)
    with _as_user(stranger):
        denied = await async_test_client.get(f"/api/projects/{project.id}/report/analysis-runs")
    assert denied.status_code == 403


# ---------------------------------------------------------------------------
# with variant_experiments off (the platform before the Analyses section)
# ---------------------------------------------------------------------------


@pytest.mark.flags_off("variant_experiments")
@pytest.mark.asyncio
async def test_off_the_run_list_is_not_found_and_snapshots_have_no_analyses(async_test_client, async_test_db):
    admin = await _user(async_test_db, is_superadmin=True)
    project, _, report = await _project(async_test_db, admin)
    runs = await _seed_runs(async_test_db, project, admin)
    with _as_user(admin):
        listed = await async_test_client.get(f"/api/projects/{project.id}/report/analysis-runs")
    assert listed.status_code == 404
    assert listed.json()["detail"] == {"code": "feature_disabled", "flag": "variant_experiments"}

    snap = await _snapshot(async_test_db, project.id, _section(runs["main"].id, [{"id": "t", "type": "table"}]))
    assert "analyses" not in snap and "reproducibility" not in snap

    # A stored section naming runs the report could not show does not block
    # publishing while the section is not part of the report.
    await _set_analyses(async_test_db, report, {"runs": [{"run_id": runs["cross"].id, "exhibits": []}]})
    ok, reason = await async_test_db.run_sync(lambda s: can_publish_report(s, project.id))
    assert reason != REASON_ANALYSIS_RUNS


@pytest.mark.flags_off("variant_experiments")
@pytest.mark.asyncio
async def test_off_saving_neither_adds_nor_changes_the_section(async_test_client, async_test_db):
    admin = await _user(async_test_db, is_superadmin=True)
    project, _, report = await _project(async_test_db, admin)

    def body(analyses):
        return {"content": {**report.content, "sections": {**report.content["sections"], "analyses": analyses}}}

    with _as_user(admin):
        added = await async_test_client.post(
            f"/api/projects/{project.id}/report", json=body({"runs": [{"run_id": "r", "exhibits": [{"id": "x", "type": "pie"}]}]})
        )
    assert added.status_code == 200, added.text
    row = (await async_test_db.execute(select(ProjectReport).where(ProjectReport.id == report.id))).scalar_one()
    await async_test_db.refresh(row)
    assert "analyses" not in row.content["sections"]

    stored = {"visible": True, "custom_text": "kept", "runs": []}
    await _set_analyses(async_test_db, row, stored)
    with _as_user(admin):
        changed = await async_test_client.post(
            f"/api/projects/{project.id}/report", json=body({"visible": False, "custom_text": "new", "runs": []})
        )
        without = {k: v for k, v in row.content["sections"].items() if k != "analyses"}
        dropped = await async_test_client.post(
            f"/api/projects/{project.id}/report", json={"content": {**row.content, "sections": without}}
        )
    assert changed.status_code == 200 and dropped.status_code == 200
    await async_test_db.refresh(row)
    assert row.content["sections"]["analyses"] == stored
    # Nor is it served while the flag is off for everybody.
    assert "analyses" not in dropped.json()["content"]["sections"]
