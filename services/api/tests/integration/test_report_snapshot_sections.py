"""
Report snapshot sections beyond the metric evaluation (shared/report_snapshot.py)
and the generalised publish rule (shared/report_service.can_publish_report).

Seeds one synthetic project per kind the report has to cover:

* annotation only: tasks and annotations, nothing else;
* generation and evaluation: the benchmark of test_report_snapshot_public
  (one official and one private BYOM model, a judge config) plus generation
  outcomes (refusal, truncation, retry, parse failure, request records,
  prompt structures);
* human evaluation: Likert ratings and preference comparisons of the
  generations, including ones of the hidden private model;
* data and reproducibility: a variant design with its tasks, completed imports
  (one a no-op repeat, one merge preview), and analysis runs (completed single
  project, completed cross-project, pending).

Then checks every section, that hidden models stay hidden everywhere, that
``snapshot_sha256`` is stable across rebuilds of unchanged data and changes
with the data, and the publish rule over HTTP.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from models import (
    AnalysisRun,
    Generation,
    HumanEvaluationDimension,
    HumanEvaluationSession,
    ImportJob,
    ImportJobTask,
    LikertScaleEvaluation,
    PreferenceRanking,
    ResponseGeneration,
)
from project_models import Annotation, Project, Task
from report_models import ProjectReport
from report_snapshot import build_report_snapshot, canonical_snapshot_json, snapshot_sha256
from tests.integration.test_report_snapshot_public import _as_user, _seed_benchmark, _user


def _uid() -> str:
    return str(uuid.uuid4())


async def _project(db, creator, *, title="Section Bench", tasks=2, report=True):
    project = Project(
        id=_uid(), title=title, description="seeded", created_by=creator.id,
        label_config='<View><Text name="text" value="$text"/></View>', label_config_version="v3",
    )
    db.add(project)
    await db.flush()
    rows = []
    for i in range(tasks):
        t = Task(id=_uid(), project_id=project.id, data={"text": f"case {i}"}, created_by=creator.id, inner_id=i + 1)
        db.add(t)
        rows.append(t)
    await db.flush()
    rep = None
    if report:
        rep = ProjectReport(
            id=_uid(), project_id=project.id, created_by=creator.id, is_published=False,
            # The draft shape report_service.create_report_draft writes: every
            # section present, only project_info completed.
            content={"sections": {"project_info": {"title": title, "description": "d", "status": "completed",
                                                   "editable": True, "visible": True},
                                  **{name: {"status": "pending", "editable": True, "visible": True}
                                     for name in ("data", "annotations", "generation", "evaluation")}},
                     "metadata": {"sections_completed": ["project_info"], "can_publish": False}},
        )
        db.add(rep)
        await db.flush()
    return project, rows, rep


async def _snapshot(db, project_id, **kw):
    return await db.run_sync(lambda s: build_report_snapshot(s, project_id, **kw))


def _empty_human(snap):
    return snap["human_evaluations"]["likert"]["dimensions"] == [] and snap["human_evaluations"]["preference"]["comparisons"] == 0


# ---------------------------------------------------------------------------
# annotation only
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_annotation_only_project_has_data_annotation_and_reproducibility_only(async_test_db):
    admin = await _user(async_test_db, is_superadmin=True)
    ann = await _user(async_test_db, pseudonym="Heron")
    project, tasks, _ = await _project(async_test_db, admin, tasks=3)
    for t in tasks[:2]:
        async_test_db.add(Annotation(id=_uid(), task_id=t.id, project_id=project.id, completed_by=ann.id,
                                     result=[{"type": "choices", "value": {"choices": ["x"]}}], was_cancelled=False))
    await async_test_db.flush()

    snap = await _snapshot(async_test_db, project.id)

    assert snap["statistics"]["annotation_count"] == 2
    assert snap["data"] == {"task_count": 3, "variant_designs": [], "imports": [], "import_count": 0, "imports_truncated": False}
    assert snap["generation"]["models"] == [] and snap["generation"]["totals"]["generations"] == 0
    assert snap["generation"]["totals"]["refusal_rate"] is None
    assert _empty_human(snap)
    assert snap["series"] == [] and snap["methods"] == []
    repro = snap["reproducibility"]
    assert repro["label_config"]["version"] == "v3"
    assert len(repro["label_config"]["sha256"]) == 64
    assert repro["models"] == [] and repro["evaluation_configs"] == [] and repro["analysis_runs"] == []
    assert set(repro["platform"]) == {"app_version", "core_api_version"}
    assert repro["snapshot_sha256"] == snapshot_sha256(snap)


@pytest.mark.asyncio
async def test_publish_rule_over_http(async_test_client, async_test_db):
    """An annotation-only project can publish; one with tasks but no result
    cannot, and neither can one without tasks."""
    admin = await _user(async_test_db, is_superadmin=True)
    ann = await _user(async_test_db)

    annotated, tasks, _ = await _project(async_test_db, admin, title="Annotated")
    async_test_db.add(Annotation(id=_uid(), task_id=tasks[0].id, project_id=annotated.id, completed_by=ann.id,
                                 result=[], was_cancelled=False))
    bare, _, _ = await _project(async_test_db, admin, title="Bare")
    empty, _, _ = await _project(async_test_db, admin, title="Empty", tasks=0)
    await async_test_db.flush()

    with _as_user(admin):
        ok = await async_test_client.put(f"/api/projects/{annotated.id}/report/publish", json={"is_public": True})
        no_results = await async_test_client.put(f"/api/projects/{bare.id}/report/publish")
        no_tasks = await async_test_client.put(f"/api/projects/{empty.id}/report/publish")
        view = await async_test_client.get(f"/api/projects/{bare.id}/report")

    assert ok.status_code == 200, ok.text
    snap = ok.json()["content"]["snapshot"]
    assert snap["reproducibility"]["snapshot_sha256"] == snapshot_sha256(snap)
    assert no_results.status_code == 400
    assert "annotations, generations, evaluations or analyses" in no_results.json()["detail"]
    assert no_tasks.status_code == 400 and "tasks" in no_tasks.json()["detail"]
    assert view.json()["can_publish"] is False
    assert view.json()["can_publish_reason"] == "Project must have annotations, generations, evaluations or analyses"

    # An anonymous reader gets the new sections from the frozen snapshot.
    with _as_user(None):
        data = await async_test_client.get(f"/api/reports/{ok.json()['id']}/data")
    assert data.status_code == 200
    assert set(data.json()["snapshot"]) >= {"data", "generation", "human_evaluations", "reproducibility"}


# ---------------------------------------------------------------------------
# generation and evaluation
# ---------------------------------------------------------------------------

async def _add_generation_outcomes(db, project, admin):
    """Generation outcomes on top of _seed_benchmark: per official-model
    generation one refusal, one retry, parse statuses and a request record;
    one failed generation; prompt structures on the parent jobs."""
    project.generation_config = {"prompt_structures": {"plain": {"system_prompt": "s", "instruction_prompt": "i"}}}
    gens = (await db.execute(
        select(Generation).join(ResponseGeneration, ResponseGeneration.id == Generation.generation_id)
        .where(ResponseGeneration.project_id == project.id).order_by(Generation.task_id)
    )).scalars().all()
    official = [g for g in gens if g.model_id == "official-model"]
    private = [g for g in gens if g.model_id == "custom-private"]
    official[0].refusal = True
    official[0].parse_status = "failed"
    official[1].retried = True
    official[1].parse_status = "success"
    official[1].request_sha256 = "a" * 64
    for g in private:
        g.refusal = True
    for g in gens:
        rg = await db.get(ResponseGeneration, g.generation_id)
        rg.structure_key = "plain"
    # A failed third run of the official model on the first task.
    rg = await db.get(ResponseGeneration, official[0].generation_id)
    db.add(Generation(id=_uid(), generation_id=rg.id, task_id=official[0].task_id, model_id="official-model",
                      case_data="x", response_content="", status="failed", run_index=2))
    await db.flush()
    return official, private


@pytest.mark.asyncio
async def test_generation_section_rates_and_hidden_models(async_test_db):
    admin = await _user(async_test_db, is_superadmin=True)
    ann = await _user(async_test_db)
    project, _ = await _seed_benchmark(async_test_db, admin, ann)
    await _add_generation_outcomes(async_test_db, project, admin)

    snap = await _snapshot(async_test_db, project.id)

    gen = snap["generation"]
    assert [m["model_id"] for m in gen["models"]] == ["official-model"]
    m = gen["models"][0]
    assert m["label"] == "Official Model" and m["provider"] == "openai"
    assert (m["generations"], m["completed"], m["failed"], m["tasks"]) == (3, 2, 1, 2)
    assert m["runs_per_task"] == pytest.approx(1.5)
    assert m["max_runs_per_task"] == 3
    assert m["refusal_rate"] == pytest.approx(0.5)      # 1 of 2 completed
    assert m["retry_rate"] == pytest.approx(0.5)
    assert m["truncation_rate"] == 0
    assert m["parse_attempted"] == 2 and m["parse_failure_rate"] == pytest.approx(0.5)
    assert m["request_record_share"] == pytest.approx(1 / 3)
    assert m["structures"] == [{"key": "plain", "generations": 3}]
    # The private model's refusals are not in the totals.
    assert gen["totals"]["generations"] == 3 and gen["totals"]["refusal_rate"] == pytest.approx(0.5)

    repro = snap["reproducibility"]
    assert [x["id"] for x in repro["models"]] == ["official-model"]
    assert repro["prompt_structures"][0]["key"] == "plain"
    assert len(repro["prompt_structures"][0]["definition_sha256"]) == 64
    cfgs = {c["id"]: c for c in repro["evaluation_configs"]}
    assert cfgs["cfg-judge"]["metric"] == "llm_judge_falloesung"
    assert cfgs["cfg-judge"]["name"] == "Notenpunkte (Abo-Modell)"
    assert cfgs["cfg-judge"]["judge_runs"][0]["judge_model"] == "judge-model"
    # 2 official-model rows and 1 human row; the private model's row is not counted.
    assert [r["samples"] for r in cfgs["cfg-judge"]["judge_runs"]] == [3]
    assert sum(r["samples"] for c in repro["evaluation_configs"] for r in c["judge_runs"]) == sum(
        c["n"] for c in snap["configs"]
    )

    body = json.dumps(snap)
    assert "custom-private" not in body and "Private Endpoint" not in body


@pytest.mark.asyncio
async def test_include_private_models_shows_them_everywhere(async_test_db):
    admin = await _user(async_test_db, is_superadmin=True)
    ann = await _user(async_test_db)
    project, _ = await _seed_benchmark(async_test_db, admin, ann)
    await _add_generation_outcomes(async_test_db, project, admin)

    snap = await _snapshot(async_test_db, project.id, include_private_models=True)

    assert {m["model_id"] for m in snap["generation"]["models"]} == {"official-model", "custom-private"}
    private = next(m for m in snap["generation"]["models"] if m["model_id"] == "custom-private")
    assert private["refusal_rate"] == 1.0


# ---------------------------------------------------------------------------
# human evaluation
# ---------------------------------------------------------------------------

async def _seed_human_evaluation(db, project, evaluator_a, evaluator_b):
    gens = (await db.execute(
        select(Generation).join(ResponseGeneration, ResponseGeneration.id == Generation.generation_id)
        .where(ResponseGeneration.project_id == project.id)
    )).scalars().all()
    by_model = {}
    for g in gens:
        by_model.setdefault(g.model_id, []).append(g)
    official, private = by_model["official-model"], by_model["custom-private"]

    db.add(HumanEvaluationDimension(id=_uid(), project_id=project.id, dimension_name="clarity",
                                    description="How clear the answer is", display_order=2))
    db.add(HumanEvaluationDimension(id=_uid(), project_id=project.id, dimension_name="accuracy",
                                    description=None, display_order=1))
    likert = HumanEvaluationSession(id=_uid(), project_id=project.id, evaluator_id=evaluator_a.id,
                                    session_type="likert", status="completed")
    likert_b = HumanEvaluationSession(id=_uid(), project_id=project.id, evaluator_id=evaluator_b.id,
                                      session_type="likert", status="completed")
    pref = HumanEvaluationSession(id=_uid(), project_id=project.id, evaluator_id=evaluator_a.id,
                                  session_type="preference", status="completed")
    idle = HumanEvaluationSession(id=_uid(), project_id=project.id, evaluator_id=evaluator_b.id,
                                  session_type="preference", status="active")
    db.add_all([likert, likert_b, pref, idle])
    await db.flush()

    def rate(session, gen, dim, rating):
        db.add(LikertScaleEvaluation(id=_uid(), session_id=session.id, task_id=gen.task_id,
                                     response_id=gen.id, dimension=dim, rating=rating))

    rate(likert, official[0], "accuracy", 4)
    rate(likert, official[1], "accuracy", 5)
    rate(likert_b, official[0], "accuracy", 3)
    rate(likert, official[0], "clarity", 2)
    # Ratings of the hidden model's answers must not move any number.
    rate(likert, private[0], "accuracy", 1)
    rate(likert_b, private[0], "clarity", 1)

    # A third, catalog-less visible model for the preference pairs.
    rg = ResponseGeneration(id=_uid(), project_id=project.id, task_id=official[0].task_id, model_id="open-model",
                            status="completed", created_by=evaluator_a.id)
    db.add(rg)
    await db.flush()
    other = Generation(id=_uid(), generation_id=rg.id, task_id=official[0].task_id, model_id="open-model",
                       case_data="x", response_content="z")
    db.add(other)
    await db.flush()

    def compare(a, b, winner):
        db.add(PreferenceRanking(id=_uid(), session_id=pref.id, task_id=a.task_id,
                                 response_a_id=a.id, response_b_id=b.id, winner=winner))

    compare(official[0], other, "a")
    compare(other, official[0], "b")
    compare(official[0], other, "tie")
    compare(official[0], private[0], "b")   # with the hidden model: dropped whole
    await db.flush()


@pytest.mark.asyncio
async def test_human_evaluation_section(async_test_db):
    admin = await _user(async_test_db, is_superadmin=True)
    ann = await _user(async_test_db)
    ev_a = await _user(async_test_db)
    ev_b = await _user(async_test_db)
    project, _ = await _seed_benchmark(async_test_db, admin, ann)
    await _seed_human_evaluation(async_test_db, project, ev_a, ev_b)

    snap = await _snapshot(async_test_db, project.id)
    likert = snap["human_evaluations"]["likert"]
    assert likert["scale"] == [1, 2, 3, 4, 5]
    assert likert["evaluator_count"] == 2
    assert [d["dimension"] for d in likert["dimensions"]] == ["accuracy", "clarity"]   # display order
    acc, clarity = likert["dimensions"]
    assert acc["n"] == 3 and acc["mean"] == pytest.approx(4.0) and acc["std"] == pytest.approx(1.0)
    assert acc["distribution"] == [0, 0, 1, 1, 1]
    assert acc["by_model"] == [{"model_id": "official-model", "label": "Official Model", "n": 3,
                                "mean": pytest.approx(4.0), "std": pytest.approx(1.0)}]
    assert clarity["description"] == "How clear the answer is"
    assert clarity["n"] == 1 and clarity["std"] is None
    assert likert["rating_count"] == 4

    pref = snap["human_evaluations"]["preference"]
    assert pref["evaluator_count"] == 1          # the idle session rated nothing
    assert pref["comparisons"] == 3 and pref["ties"] == 1
    models = {m["model_id"]: m for m in pref["models"]}
    assert set(models) == {"official-model", "open-model"}
    assert (models["official-model"]["wins"], models["official-model"]["losses"], models["official-model"]["ties"]) == (2, 0, 1)
    assert models["official-model"]["win_rate"] == pytest.approx(2 / 3)
    assert models["open-model"]["comparisons"] == 3 and models["open-model"]["wins"] == 0
    assert pref["pairs"] == [{"model_a": "official-model", "label_a": "Official Model",
                              "model_b": "open-model", "label_b": "open-model",
                              "a_wins": 2, "b_wins": 0, "ties": 1}]
    assert "custom-private" not in json.dumps(snap)
    # It has a generation in the project, so it is one of the report's models.
    assert "open-model" in [m["id"] for m in snap["models"]]


# ---------------------------------------------------------------------------
# data and reproducibility
# ---------------------------------------------------------------------------

_DESIGN_SPEC = {
    "schema_version": 1,
    "title": "Synthetic framing design",
    "unit": {"name": "case"},
    "factors": [
        {"name": "framing", "type": "nominal", "levels": ["neutral", "loaded"], "role": "manipulated"},
        {"name": "order", "type": "ordinal", "levels": [1, 2], "role": "counterbalanced"},
    ],
}


async def _seed_data(db, project, admin):
    from variant_design_guard import new_design_row

    design = new_design_row(project.id, "framing", _DESIGN_SPEC, created_by=admin.id,
                            provenance={"generator": "synthetic", "version": "1"})
    db.add(design)
    await db.flush()
    for u in range(2):
        for framing in ("neutral", "loaded"):
            for order in (1, 2):
                db.add(Task(id=_uid(), project_id=project.id, created_by=admin.id,
                            inner_id=100 + u * 10 + (framing == "loaded") * 2 + order,
                            data={"text": f"unit {u} {framing} {order}"},
                            meta={"variant": {"design": "framing", "unit": f"u{u}",
                                              "factors": {"framing": framing, "order": order}}}))
    await db.flush()

    t0 = datetime(2026, 11, 1, tzinfo=timezone.utc)
    first = ImportJob(id=_uid(), project_id=project.id, requested_by=admin.id, format="nested", status="completed",
                      object_key="imports/x/data.json", payload_sha256="b" * 64, idempotency_key="c" * 64,
                      source_manifest={"version": 1, "payload": {"sha256": "b" * 64, "byte_size": 1234},
                                       "source": {"kind": "upload", "object_key": "imports/x/data.json", "filename": "data.json"},
                                       "target": {"project_id": project.id}, "import": {"mode": "nested"},
                                       "declared": {"files": [{"name": "cases.csv", "sha256": "d" * 64}]}},
                      created_at=t0, updated_at=t0)
    db.add(first)
    await db.flush()
    repeat = ImportJob(id=_uid(), project_id=project.id, requested_by=admin.id, format="nested", status="completed",
                       object_key="imports/y/data.json", payload_sha256="b" * 64, duplicate_of_job_id=first.id,
                       source_manifest={"version": 1, "payload": {"sha256": "b" * 64, "byte_size": 1234},
                                        "import": {"mode": "nested"}},
                       created_at=t0 + timedelta(hours=1), updated_at=t0 + timedelta(hours=1))
    preview = ImportJob(id=_uid(), project_id=project.id, requested_by=admin.id, format="nested", status="completed",
                        object_key="imports/z/data.json", payload_sha256="e" * 64,
                        source_manifest={"import": {"mode": "merge_preview"}},
                        created_at=t0 + timedelta(hours=2), updated_at=t0 + timedelta(hours=2))
    failed = ImportJob(id=_uid(), project_id=project.id, requested_by=admin.id, status="failed",
                       object_key="imports/w/data.json", created_at=t0, updated_at=t0)
    db.add_all([repeat, preview, failed])
    await db.flush()
    tasks = (await db.execute(select(Task.id).where(Task.project_id == project.id))).scalars().all()
    for tid in tasks[:2]:
        db.add(ImportJobTask(import_job_id=first.id, task_id=tid))

    def run(status, *, projects=None, name="run"):
        inputs = {"projects": projects} if projects is not None else {}
        return AnalysisRun(
            id=_uid(), project_id=project.id, created_by=admin.id, name=name, status=status,
            spec={"inputs": inputs}, normalized_spec={"inputs": inputs}, spec_hash="f" * 64, spec_version=1,
            engine_version="1.1.0", frame_hash="1" * 64, frame_sha256="2" * 64, frame_rows=16,
            library_versions={"numpy": "2.0.0"}, lockfile_sha256="3" * 64, seed=7, estimates_count=4,
            completed_at=t0 if status == "completed" else None,
        )

    db.add_all([
        run("completed", name="single"),
        run("completed", name="cross", projects=[{"project_id": _uid(), "designs": ["framing"]}]),
        run("pending", name="pending"),
    ])
    await db.flush()


@pytest.mark.asyncio
async def test_data_section_designs_and_import_provenance(async_test_db):
    admin = await _user(async_test_db, is_superadmin=True)
    project, _, _ = await _project(async_test_db, admin, tasks=1)
    await _seed_data(async_test_db, project, admin)

    snap = await _snapshot(async_test_db, project.id)
    data = snap["data"]
    assert data["task_count"] == 9
    [design] = data["variant_designs"]
    assert design["key"] == "framing" and design["status"] == "draft" and design["content_hash"] is None
    assert (design["task_count"], design["unit_count"], design["cell_count"]) == (8, 2, 4)
    assert design["title"] == "Synthetic framing design" and design["unit"] == "case"
    assert [f["name"] for f in design["factors"]] == ["framing", "order"]
    assert design["factors"][0]["levels"] == ["neutral", "loaded"] and design["factors"][0]["level_count"] == 2
    assert design["factors"][1]["role"] == "counterbalanced"
    assert len(design["spec_sha256"]) == 64
    assert design["provenance"]["content"] == {"generator": "synthetic", "version": "1"}

    assert data["import_count"] == 2 and data["imports_truncated"] is False
    first, repeat = data["imports"]
    assert first["payload_sha256"] == "b" * 64 and first["byte_size"] == 1234 and first["mode"] == "nested"
    assert first["task_count"] == 2 and first["no_op"] is False
    assert first["declared_manifest"]["content"] == {"files": [{"name": "cases.csv", "sha256": "d" * 64}]}
    assert repeat["no_op"] is True and repeat["declared_manifest"] is None
    # Where the payload was stored is not part of a report.
    assert "imports/x/data.json" not in json.dumps(snap)

    repro = snap["reproducibility"]
    assert repro["variant_designs"] == [{"key": "framing", "version": 1, "status": "draft",
                                         "content_hash": None, "spec_sha256": design["spec_sha256"]}]
    assert [i["payload_sha256"] for i in repro["imports"]] == ["b" * 64, "b" * 64]
    [run] = repro["analysis_runs"]
    assert run["name"] == "single"
    assert (run["spec_hash"], run["frame_sha256"], run["lockfile_sha256"]) == ("f" * 64, "2" * 64, "3" * 64)
    assert run["engine_version"] == "1.1.0" and run["library_versions"] == {"numpy": "2.0.0"} and run["seed"] == 7


@pytest.mark.asyncio
async def test_oversized_declared_manifest_keeps_only_its_hash(async_test_db):
    from report_snapshot import MAX_FREE_JSON_BYTES

    admin = await _user(async_test_db, is_superadmin=True)
    project, _, _ = await _project(async_test_db, admin, tasks=1)
    async_test_db.add(ImportJob(id=_uid(), project_id=project.id, requested_by=admin.id, status="completed",
                                object_key="k", payload_sha256="b" * 64,
                                source_manifest={"import": {"mode": "nested"},
                                                 "declared": {"blob": "x" * (MAX_FREE_JSON_BYTES + 1)}}))
    await async_test_db.flush()
    snap = await _snapshot(async_test_db, project.id)
    manifest = snap["data"]["imports"][0]["declared_manifest"]
    assert manifest["truncated"] is True and "content" not in manifest and len(manifest["sha256"]) == 64


# ---------------------------------------------------------------------------
# snapshot_sha256
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_snapshot_sha256_is_stable_across_rebuilds_and_tracks_the_data(async_test_db, monkeypatch):
    admin = await _user(async_test_db, is_superadmin=True)
    ann = await _user(async_test_db, pseudonym="Wren")
    ev = await _user(async_test_db)
    project, _ = await _seed_benchmark(async_test_db, admin, ann)
    await _add_generation_outcomes(async_test_db, project, admin)
    await _seed_human_evaluation(async_test_db, project, ev, ann)
    await _seed_data(async_test_db, project, admin)

    monkeypatch.setenv("BENGER_APP_VERSION", "v20261101-aaaa-bbbb")
    first = await _snapshot(async_test_db, project.id, now=datetime(2026, 11, 1, tzinfo=timezone.utc))
    # Another time and another build: same data, same hash.
    monkeypatch.setenv("BENGER_APP_VERSION", "v20261119-cccc-dddd")
    second = await _snapshot(async_test_db, project.id, now=datetime(2026, 11, 19, tzinfo=timezone.utc))

    h = first["reproducibility"]["snapshot_sha256"]
    assert len(h) == 64
    assert second["reproducibility"]["snapshot_sha256"] == h
    assert first["generated_at"] != second["generated_at"]
    assert first["reproducibility"]["platform"]["app_version"] == "v20261101-aaaa-bbbb"
    assert canonical_snapshot_json(first) == canonical_snapshot_json(second)

    # Changed data, changed hash.
    t = (await async_test_db.execute(select(Task).where(Task.project_id == project.id))).scalars().first()
    async_test_db.add(Annotation(id=_uid(), task_id=t.id, project_id=project.id, completed_by=ev.id,
                                 result=[], was_cancelled=False))
    await async_test_db.flush()
    third = await _snapshot(async_test_db, project.id)
    assert third["reproducibility"]["snapshot_sha256"] != h


def test_hash_ignores_float_noise_and_int_float_spelling():
    base = {"generated_at": "x", "statistics": {"mean": 0.1 + 0.2, "n": 2.0},
            "reproducibility": {"platform": {"app_version": "a"}, "snapshot_sha256": None}}
    same = {"generated_at": "y", "statistics": {"mean": 0.3, "n": 2},
            "reproducibility": {"platform": {"app_version": "b"}, "snapshot_sha256": "old"}}
    other = {"generated_at": "y", "statistics": {"mean": 0.31, "n": 2},
             "reproducibility": {"platform": {"app_version": "b"}}}
    assert snapshot_sha256(base) == snapshot_sha256(same)
    assert snapshot_sha256(base) != snapshot_sha256(other)


# ---------------------------------------------------------------------------
# who authors a report (routers/reports.can_edit_report)
# ---------------------------------------------------------------------------

async def _org_with(db, members):
    from models import Organization, OrganizationMembership

    org = Organization(id=_uid(), name=f"Org {_uid()[:6]}", display_name="Org", slug=f"org-{_uid()[:8]}",
                       created_at=datetime.now(timezone.utc))
    db.add(org)
    await db.flush()
    for user, role in members:
        db.add(OrganizationMembership(id=_uid(), user_id=user.id, organization_id=org.id, role=role,
                                      is_active=True, joined_at=datetime.now(timezone.utc)))
    await db.flush()
    return org


async def _authoring_round(client, project_id):
    """Edit, publish, switch visibility, refresh and unpublish; status codes."""
    get = await client.get(f"/api/projects/{project_id}/report")
    codes = {"get": get.status_code}
    content = get.json()["content"] if get.status_code == 200 else {"sections": {}, "metadata": {}}
    codes["update"] = (await client.post(f"/api/projects/{project_id}/report", json={"content": content})).status_code
    codes["publish"] = (await client.put(f"/api/projects/{project_id}/report/publish")).status_code
    codes["visibility"] = (await client.put(f"/api/projects/{project_id}/report/visibility",
                                            json={"is_public": True})).status_code
    codes["refresh"] = (await client.post(f"/api/projects/{project_id}/report/refresh")).status_code
    codes["unpublish"] = (await client.put(f"/api/projects/{project_id}/report/unpublish")).status_code
    return codes, get


_ALLOWED = {"get": 200, "update": 200, "publish": 200, "visibility": 200, "refresh": 200, "unpublish": 200}


@pytest.mark.asyncio
@pytest.mark.parametrize("who", ["owner", "org_admin", "superadmin"])
async def test_report_authors_edit_publish_and_unpublish(async_test_client, async_test_db, who):
    owner = await _user(async_test_db)
    org_admin = await _user(async_test_db)
    superadmin = await _user(async_test_db, is_superadmin=True)
    ann = await _user(async_test_db)
    org = await _org_with(async_test_db, [(owner, "CONTRIBUTOR"), (org_admin, "ORG_ADMIN"), (ann, "ANNOTATOR")])
    project, report = await _seed_benchmark(async_test_db, owner, ann, org=org)
    # The draft is created on first view by an author.
    await async_test_db.delete(report)
    await async_test_db.flush()

    actor = {"owner": owner, "org_admin": org_admin, "superadmin": superadmin}[who]
    with _as_user(actor):
        codes, get = await _authoring_round(async_test_client, project.id)
        data = await async_test_client.get(f"/api/reports/{get.json()['id']}/data")
    assert codes == _ALLOWED, codes
    assert get.json()["can_edit"] is True
    assert data.status_code == 200 and data.json()["report"]["can_edit"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("who", ["contributor", "annotator", "other_org_admin"])
async def test_non_authors_cannot_edit_or_publish(async_test_client, async_test_db, who):
    owner = await _user(async_test_db)
    contributor = await _user(async_test_db)
    annotator = await _user(async_test_db)
    other_admin = await _user(async_test_db)
    org = await _org_with(async_test_db, [(owner, "ORG_ADMIN"), (contributor, "CONTRIBUTOR"), (annotator, "ANNOTATOR")])
    await _org_with(async_test_db, [(other_admin, "ORG_ADMIN")])
    project, report = await _seed_benchmark(async_test_db, owner, annotator, org=org)
    actor = {"contributor": contributor, "annotator": annotator, "other_org_admin": other_admin}[who]

    with _as_user(actor):
        codes, _ = await _authoring_round(async_test_client, project.id)
        draft = await async_test_client.get(f"/api/reports/{report.id}/data")
    assert codes == {"get": 403, "update": 403, "publish": 403, "visibility": 403, "refresh": 403, "unpublish": 403}
    assert draft.status_code == 403

    # Once the owner published it, members read it but still cannot author it.
    with _as_user(owner):
        assert (await async_test_client.put(f"/api/projects/{project.id}/report/publish")).status_code == 200
    with _as_user(actor):
        view = await async_test_client.get(f"/api/projects/{project.id}/report")
        unpublish = await async_test_client.put(f"/api/projects/{project.id}/report/unpublish")
    if who == "other_org_admin":
        assert view.status_code == 403
    else:
        assert view.status_code == 200 and view.json()["can_edit"] is False
    assert unpublish.status_code == 403


# ---------------------------------------------------------------------------
# hidden models in the report's content (not only its snapshot)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_content_sections_leave_hidden_models_out(async_test_db):
    """The report service writes per-model values into content.sections, which
    a public report serves whole; it listed private custom models."""
    from models import EvaluationRun
    from report_service import _resolve_per_model_metrics, create_or_update_report_from_existing_data, get_report_models

    admin = await _user(async_test_db, is_superadmin=True)
    ann = await _user(async_test_db)
    project, _ = await _seed_benchmark(async_test_db, admin, ann)

    def _work(sync_db):
        run_ids = [r.id for r in sync_db.query(EvaluationRun.id).filter(EvaluationRun.project_id == project.id)]
        report = create_or_update_report_from_existing_data(sync_db, project.id, admin.id)
        return get_report_models(sync_db, project.id), _resolve_per_model_metrics(sync_db, run_ids), report.content

    models, metrics, content = await async_test_db.run_sync(_work)
    assert models == ["official-model"]
    assert "custom-private" not in metrics and "official-model" in metrics
    assert "custom-private" not in json.dumps(content)


@pytest.mark.asyncio
async def test_readers_never_get_the_legacy_per_model_fields(async_test_client, async_test_db):
    """A report written before that fix still holds them; only its authors
    get them back."""
    admin = await _user(async_test_db, is_superadmin=True)
    ann = await _user(async_test_db)
    project, report = await _seed_benchmark(async_test_db, admin, ann)
    report.content = {
        **report.content,
        "sections": {
            **report.content["sections"],
            "generation": {"status": "completed", "visible": True, "models": ["official-model", "custom-private"]},
            "evaluation": {"status": "completed", "visible": True, "metrics": {"custom-private": {"bleu": 0.1}},
                           "conclusions": "kept"},
        },
    }
    await async_test_db.flush()

    with _as_user(admin):
        assert (await async_test_client.put(f"/api/projects/{project.id}/report/publish",
                                            json={"is_public": True})).status_code == 200
        own = await async_test_client.get(f"/api/reports/{report.id}/data")
    with _as_user(None):
        anon = await async_test_client.get(f"/api/reports/{report.id}/data")

    assert anon.status_code == 200
    assert "custom-private" not in anon.text
    sections = anon.json()["report"]["content"]["sections"]
    assert sections["evaluation"]["conclusions"] == "kept"
    assert "metrics" not in sections["evaluation"] and "models" not in sections["generation"]
    assert own.json()["report"]["content"]["sections"]["generation"]["models"] == ["official-model", "custom-private"]


# ---------------------------------------------------------------------------
# the snapshot is server-owned (POST /projects/{id}/report)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_posted_snapshot_is_ignored(async_test_client, async_test_db):
    owner = await _user(async_test_db)
    ann = await _user(async_test_db)
    project, report = await _seed_benchmark(async_test_db, owner, ann)
    forged = {"statistics": {"task_count": 999}, "series": [],
              "reproducibility": {"snapshot_sha256": "0" * 64}}

    with _as_user(owner):
        # No snapshot stored yet: a posted one is not stored either.
        content = (await async_test_client.get(f"/api/projects/{project.id}/report")).json()["content"]
        first = await async_test_client.post(f"/api/projects/{project.id}/report",
                                             json={"content": {**content, "snapshot": forged}})
        assert first.status_code == 200 and first.json()["content"]["snapshot"] is None

        stored = (await async_test_client.post(f"/api/projects/{project.id}/report/refresh")).json()
        stored_snapshot = stored["content"]["snapshot"]
        updated = await async_test_client.post(
            f"/api/projects/{project.id}/report",
            json={"content": {**stored["content"], "snapshot": forged,
                              "sections": {**stored["content"]["sections"], "data": {"custom_text": "edited"}}}},
        )
        # A body without a snapshot keeps the stored one too.
        omitted = await async_test_client.post(
            f"/api/projects/{project.id}/report",
            json={"content": {k: v for k, v in stored["content"].items() if k != "snapshot"}},
        )

    assert updated.status_code == 200
    assert updated.json()["content"]["sections"]["data"]["custom_text"] == "edited"
    assert updated.json()["content"]["snapshot"] == stored_snapshot
    assert omitted.json()["content"]["snapshot"] == stored_snapshot
    await async_test_db.refresh(report)
    assert report.content["snapshot"] == stored_snapshot
    assert stored_snapshot["reproducibility"]["snapshot_sha256"] != "0" * 64


# ---------------------------------------------------------------------------
# what a reader outside the project gets (report_snapshot.public_snapshot)
# ---------------------------------------------------------------------------

_JUDGE_PROMPT = "SYNTHETIC-JUDGE-PROMPT: grade the answer"
_RUBRIC_TEXT = "SYNTHETIC-RUBRIC-CRITERION: names the legal basis"


async def _seed_private_judge_and_parameters(db, project):
    """Parameters on the benchmark's judge run, plus a second, multi-judge
    config judged by a hidden (private custom) judge model and a visible one.
    The parameter snapshots have the worker's shape: the config's
    ``metric_parameters`` as is (``judge_model`` or the ``judges`` list) plus
    ``_param_provenance`` (workers/tasks.py, _get_or_create_judge_run_for_config)."""
    from models import EvaluationJudgeRun, LLMModel, TaskEvaluation

    jr = (await db.execute(select(EvaluationJudgeRun).where(EvaluationJudgeRun.judge_model_id == "judge-model")
                           .join(TaskEvaluation, TaskEvaluation.judge_run_id == EvaluationJudgeRun.id)
                           .where(TaskEvaluation.evaluation_config_id == "cfg-judge"))).scalars().first()
    jr.metric_parameters_snapshot = {"judge_model": "judge-model", "custom_prompt": _JUDGE_PROMPT,
                                     "rubric": [_RUBRIC_TEXT], "temperature": 0,
                                     "_param_provenance": {"temperature": {"value": 0, "source": "config"}}}
    db.add(LLMModel(id="custom-judge-secret", name="Secret Judge", provider="openai", model_type="chat",
                    capabilities=[], is_active=True, is_official=False, is_public=False, is_private=True,
                    base_url="https://example.invalid/v1", endpoint_model_name="secret-judge"))
    await db.flush()
    multi_judge = {"judges": [{"judge_model_id": "custom-judge-secret", "runs": 1},
                              {"judge_model_id": "judge-model", "runs": 1}],
                   "custom_prompt": _JUDGE_PROMPT,
                   "_param_provenance": {"temperature": {"value": 0, "source": "config"}}}
    hidden_run = EvaluationJudgeRun(id=_uid(), evaluation_id=jr.evaluation_id, judge_model_id="custom-judge-secret",
                                    run_index=1, status="completed", metric_parameters_snapshot=multi_judge)
    sibling_run = EvaluationJudgeRun(id=_uid(), evaluation_id=jr.evaluation_id, judge_model_id="judge-model",
                                     run_index=2, status="completed", metric_parameters_snapshot=multi_judge)
    db.add_all([hidden_run, sibling_run])
    await db.flush()
    gens = (await db.execute(select(Generation).join(ResponseGeneration, ResponseGeneration.id == Generation.generation_id)
                             .where(ResponseGeneration.project_id == project.id,
                                    Generation.model_id == "official-model")
                             .order_by(Generation.task_id))).scalars().all()
    # The hidden judge graded more, so it is the config's dominant judge.
    for run, gen in ((hidden_run, gens[0]), (hidden_run, gens[1]), (sibling_run, gens[0])):
        db.add(TaskEvaluation(id=_uid(), evaluation_id=jr.evaluation_id, judge_run_id=run.id, task_id=gen.task_id,
                              generation_id=gen.id, field_name="loesung", answer_type="long_text",
                              ground_truth={"value": "ref"}, prediction={"value": "pred"}, passed=True,
                              evaluation_config_id="cfg-private-judge",
                              metrics={"llm_judge_falloesung": {"value": 0.8, "details": {}}}))
    await db.flush()


def _judge_runs(snapshot):
    return {c["id"]: c["judge_runs"] for c in snapshot["reproducibility"]["evaluation_configs"]}


@pytest.mark.asyncio
async def test_public_readers_get_hashes_members_get_parameters(async_test_client, async_test_db):
    owner = await _user(async_test_db)
    member = await _user(async_test_db)
    outsider = await _user(async_test_db)
    org = await _org_with(async_test_db, [(owner, "CONTRIBUTOR"), (member, "ANNOTATOR")])
    project, report = await _seed_benchmark(async_test_db, owner, member, org=org)
    await _seed_data(async_test_db, project, owner)
    await _seed_private_judge_and_parameters(async_test_db, project)

    with _as_user(owner):
        published = await async_test_client.put(f"/api/projects/{project.id}/report/publish", json={"is_public": True})
    assert published.status_code == 200
    with _as_user(None):
        anon = await async_test_client.get(f"/api/reports/{report.id}/data")
    with _as_user(outsider):
        outside = await async_test_client.get(f"/api/reports/{report.id}/data")
    with _as_user(member):
        inside = await async_test_client.get(f"/api/reports/{report.id}/data")
        inside_project = await async_test_client.get(f"/api/projects/{project.id}/report")

    assert {anon.status_code, outside.status_code, inside.status_code, inside_project.status_code} == {200}
    full = inside.json()["snapshot"]

    # A hidden judge is named nowhere, for any reader.
    for response in (anon, outside, inside, inside_project, published):
        assert "custom-judge-secret" not in response.text and "Secret Judge" not in response.text
    assert next(c for c in full["configs"] if c["id"] == "cfg-private-judge")["judge_model"] is None
    private_runs = _judge_runs(full)["cfg-private-judge"]
    assert [(r["judge_model"], r["samples"]) for r in private_runs] == [(None, 2), ("judge-model", 1)]
    # Parameters naming the hidden judge keep only their hash, also in the
    # visible sibling run of the same multi-judge config.
    assert [r["parameters"] for r in private_runs] == [None, None]
    assert all(len(r["parameters_sha256"]) == 64 for r in private_runs)

    # Members see the full parameters and manifest bodies.
    [visible_run] = _judge_runs(full)["cfg-judge"]
    assert visible_run["judge_model"] == "judge-model"
    assert visible_run["parameters"]["custom_prompt"] == _JUDGE_PROMPT
    assert full["data"]["imports"][0]["declared_manifest"]["content"] == {"files": [{"name": "cases.csv", "sha256": "d" * 64}]}
    assert full["data"]["variant_designs"][0]["provenance"]["content"] == {"generator": "synthetic", "version": "1"}
    assert inside_project.json()["content"]["snapshot"] == full

    for response in (anon, outside):
        body = response.json()
        assert _JUDGE_PROMPT not in response.text and _RUBRIC_TEXT not in response.text
        assert '"generator"' not in response.text and "cases.csv" not in response.text
        for snapshot in (body["snapshot"], body["report"]["content"]["snapshot"]):
            runs = _judge_runs(snapshot)
            assert runs["cfg-judge"] == [{k: v for k, v in visible_run.items() if k != "parameters"}]
            assert len(runs["cfg-judge"][0]["parameters_sha256"]) == 64
            manifest = snapshot["data"]["imports"][0]["declared_manifest"]
            assert manifest == {"sha256": full["data"]["imports"][0]["declared_manifest"]["sha256"]}
            provenance = snapshot["data"]["variant_designs"][0]["provenance"]
            assert provenance == {"sha256": full["data"]["variant_designs"][0]["provenance"]["sha256"]}
            assert snapshot["reproducibility"]["snapshot_sha256"] == full["reproducibility"]["snapshot_sha256"]
            assert snapshot["series"] == full["series"]

    # The stored snapshot stays whole.
    await async_test_db.refresh(report)
    assert report.content["snapshot"] == full
