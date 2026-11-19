"""Analysis runs end to end: tasks with ``meta.variant`` and generations in the
test database, ``tasks.run_analysis`` (eager), the stored frame and estimates.
"""

from __future__ import annotations

import json
import math
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "analysis"))

import tasks  # noqa: E402
from analysis.frame import build_frame, frame_hash, from_parquet  # noqa: E402
from analysis.observations import observations_from_records  # noqa: E402
from analysis.runner import run_spec  # noqa: E402
from analysis.spec import normalize_spec, spec_hash  # noqa: E402
from analysis.version import ENGINE_VERSION, SPEC_VERSION  # noqa: E402
from analysis_synthetic import role_swap_design, role_swap_records, role_swap_spec  # noqa: E402

UNITS = 12


def _results(fields):
    out = []
    if "share_p" in fields:
        out.append({"from_name": "share_p", "type": "number", "value": {"number": fields["share_p"]}})
    if "credible" in fields:
        out.append({"from_name": "credible", "type": "choices", "value": {"choices": [fields["credible"]]}})
    return out


@pytest.fixture()
def seeded(db_conn, make_project, make_user):
    """A project holding the synthetic design: one task per variant, one
    generation per task and system, plus a task outside any design and a
    failed generation."""
    from models import Generation, ResponseGeneration
    from project_models import Task
    from variant_design_guard import new_design_row

    user = make_user()
    project = make_project(created_by=user.id)
    db_conn.add(new_design_row(project.id, "role_swap", role_swap_design(), created_by=user.id))
    db_conn.commit()
    records = role_swap_records(units=UNITS)
    task_ids = {}
    rows = []
    inner = 0
    for rec in records:
        if rec["task_id"] not in task_ids:
            inner += 1
            tid = str(uuid.uuid4())
            task_ids[rec["task_id"]] = tid
            rows.append(Task(id=tid, project_id=project.id, data=rec["task_data"],
                             meta={"variant": rec["variant"], "tags": ["x"]}, inner_id=inner))
    outside = Task(id=str(uuid.uuid4()), project_id=project.id, data={"text": "x"}, meta={"tags": []}, inner_id=inner + 1)
    rows.append(outside)
    db_conn.add_all(rows)
    db_conn.commit()
    gens = []
    for rec in records:
        rg = ResponseGeneration(id=str(uuid.uuid4()), project_id=project.id, task_id=task_ids[rec["task_id"]],
                                model_id=rec["model_id"], status="completed", created_by=user.id, structure_key="default")
        parsed = _results(rec["fields"])
        gens.append(rg)
        gens.append(Generation(
            id=str(uuid.uuid4()), generation_id=rg.id, task_id=rg.task_id, model_id=rec["model_id"],
            case_data="{}", response_content="...", status="completed",
            parsed_annotation=parsed, parse_status="success" if rec["parse_ok"] else "failed",
            response_metadata=json.dumps({"provider": "test"}), finish_reason="stop",
        ))
    for task_id, status in ((outside.id, "completed"), (task_ids[records[0]["task_id"]], "failed")):
        rg = ResponseGeneration(id=str(uuid.uuid4()), project_id=project.id, task_id=task_id, model_id="sys_a",
                                status=status, created_by=user.id, structure_key="default")
        gens.append(rg)
        gens.append(Generation(id=str(uuid.uuid4()), generation_id=rg.id, task_id=task_id, model_id="sys_a",
                               case_data="{}", response_content="", status=status, run_index=1,
                               parsed_annotation=[], parse_status="failed"))
    db_conn.add_all(gens)
    db_conn.commit()
    return project, user, records


def _new_run(db_conn, project, user, spec=None):
    from models import AnalysisRun

    spec = spec or role_swap_spec()
    normalized = normalize_spec(spec)
    run = AnalysisRun(project_id=project.id, created_by=user.id, name="it", spec=spec,
                      normalized_spec=normalized, spec_hash=spec_hash(normalized),
                      spec_version=SPEC_VERSION, engine_version=ENGINE_VERSION)
    db_conn.add(run)
    db_conn.commit()
    return run


def _reload(db_conn, run_id):
    from models import AnalysisEstimate, AnalysisRun

    db_conn.expire_all()
    run = db_conn.query(AnalysisRun).filter(AnalysisRun.id == run_id).one()
    estimates = (
        db_conn.query(AnalysisEstimate).filter(AnalysisEstimate.run_id == run_id)
        .order_by(AnalysisEstimate.position).all()
    )
    return run, estimates


def test_run_reads_the_design_and_stores_frame_and_estimates(db_conn, seeded):
    project, user, records = seeded
    run = _new_run(db_conn, project, user)
    out = tasks.run_analysis.apply(args=[run.id]).get()
    assert out["status"] == "completed"
    run, estimates = _reload(db_conn, run.id)
    assert run.status == "completed" and run.error_message is None
    assert run.frame_rows == len(records)
    assert run.frame_counts["variant_tasks"] == UNITS * 4
    assert run.frame_counts["failed_generations"] == 1
    assert run.frame_counts["observations"] == len(records)
    assert run.estimates_count == len(estimates) > 20
    assert run.engine_version == ENGINE_VERSION
    assert set(run.library_versions) == {"python", "numpy", "pandas", "scipy", "statsmodels", "pyarrow"}
    assert run.resolved_inputs == {"projects": [], "lookups": [],
                                   "models": sorted({r["model_id"] for r in records})}
    assert run.lockfile_sha256 is None or len(run.lockfile_sha256) == 64
    assert run.started_at is not None and run.completed_at is not None
    assert run.timings["total_s"] >= 0 and run.fits

    # the stored snapshot is the frame the estimates came from
    from storage.object_storage import object_storage

    assert run.frame_object_key.startswith("analysis/")
    path = os.path.join(object_storage.local_storage_path, run.frame_object_key)
    with open(path, "rb") as fh:
        data = fh.read()
    import hashlib

    assert hashlib.sha256(data).hexdigest() == run.frame_sha256 and len(data) == run.frame_bytes
    frame = from_parquet(data)
    assert frame_hash(frame) == run.frame_hash
    assert set(frame["structure_key"]) == {"default"} and set(frame["retried"]) == {0.0}

    # the database path gives the estimates of the fixture path (rows differ
    # only in their ids, so only the summation order can differ)
    spec = normalize_spec(role_swap_spec())
    reference = run_spec(build_frame(observations_from_records(records), spec).frame, spec).estimates
    assert [e.estimand_id for e in estimates] == [r["estimand_id"] for r in reference]
    for stored, ref in zip(estimates, reference):
        assert stored.status == ref["status"] and stored.scope == ref["scope"]
        for name in ("estimate", "std_error", "p_value", "ci_lower", "p_adjusted"):
            a, b = getattr(stored, name), ref[name]
            assert (a is None and b is None) or math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-15), (name, a, b)
        assert stored.tost == ref["tost"] or stored.tost[0]["equivalent"] == ref["tost"][0]["equivalent"]


def test_reruns_are_bit_identical_and_redelivery_is_a_no_op(db_conn, seeded):
    project, user, _ = seeded
    first = _new_run(db_conn, project, user)
    second = _new_run(db_conn, project, user)
    tasks.run_analysis.apply(args=[first.id]).get()
    tasks.run_analysis.apply(args=[second.id]).get()
    r1, e1 = _reload(db_conn, first.id)
    r2, e2 = _reload(db_conn, second.id)
    assert r1.frame_hash == r2.frame_hash and r1.spec_hash == r2.spec_hash
    fields = ("estimate", "std_error", "p_value", "ci_lower", "ci_upper", "p_adjusted")
    for a, b in zip(e1, e2):
        for name in fields:
            va, vb = getattr(a, name), getattr(b, name)
            assert (va is None and vb is None) or va.hex() == vb.hex()
    completed_at = r1.completed_at
    assert tasks.run_analysis.apply(args=[first.id]).get()["status"] == "skipped"
    r1_again, e1_again = _reload(db_conn, first.id)
    assert r1_again.completed_at == completed_at and len(e1_again) == len(e1)


def test_a_run_left_running_is_recomputed(db_conn, seeded):
    from models import AnalysisEstimate

    project, user, _ = seeded
    run = _new_run(db_conn, project, user)
    run.status = "running"
    db_conn.add(AnalysisEstimate(run_id=run.id, position=999, estimand_id="stale", estimator="fe_ols",
                                 outcome="y", scope="pooled", status="ok"))
    db_conn.commit()
    assert tasks.run_analysis.apply(args=[run.id]).get()["status"] == "completed"
    run, estimates = _reload(db_conn, run.id)
    assert run.status == "completed" and all(e.estimand_id != "stale" for e in estimates)


def test_a_spec_problem_fails_the_run_with_its_message(db_conn, seeded):
    project, user, _ = seeded
    spec = role_swap_spec()
    spec["measures"]["broken"] = {"kind": "expression", "expr": "no_such_column * 2"}
    run = _new_run(db_conn, project, user, spec)
    assert tasks.run_analysis.apply(args=[run.id]).get()["status"] == "failed"
    run, estimates = _reload(db_conn, run.id)
    assert run.status == "failed" and "unknown column(s) no_such_column" in run.error_message
    assert estimates == [] and run.completed_at is not None


def test_an_internal_error_does_not_leak_its_text(db_conn, seeded, monkeypatch):
    import analysis.runner

    project, user, _ = seeded
    run = _new_run(db_conn, project, user)

    def boom(*args, **kwargs):
        raise RuntimeError("INSERT INTO secret_table VALUES (...)")

    monkeypatch.setattr(analysis.runner, "run_spec", boom)
    assert tasks.run_analysis.apply(args=[run.id]).get()["status"] == "failed"
    run, _ = _reload(db_conn, run.id)
    assert "secret" not in run.error_message and run.id in run.error_message


def test_an_error_outside_the_body_still_fails_the_run(db_conn, seeded, monkeypatch):
    import analysis_jobs.service as service

    project, user, _ = seeded
    run = _new_run(db_conn, project, user)

    def broken_claim(db, run_id):
        raise ImportError("stale worker")

    monkeypatch.setattr(service, "_claim", broken_claim)
    assert tasks.run_analysis.apply(args=[run.id]).get()["status"] == "failed"
    run, _ = _reload(db_conn, run.id)
    assert run.status == "failed" and "internal error" in run.error_message


def test_a_failure_after_the_upload_deletes_the_frame(db_conn, seeded, monkeypatch):
    import analysis_jobs.service as service
    from storage.object_storage import object_storage

    project, user, _ = seeded
    run = _new_run(db_conn, project, user)
    uploaded = []

    class RecordingStorage:
        def upload_file(self, *args, **kwargs):
            stored = object_storage.upload_file(*args, **kwargs)
            uploaded.append(stored["file_key"])
            return stored

        def delete_file(self, key):
            return object_storage.delete_file(key)

    def broken_versions():
        raise RuntimeError("version probe failed")

    monkeypatch.setattr(service, "library_versions", broken_versions)
    assert service.run_analysis_impl(run.id, storage=RecordingStorage())["status"] == "failed"
    run, estimates = _reload(db_conn, run.id)
    assert run.status == "failed" and run.frame_object_key is None and estimates == []
    assert len(uploaded) == 1
    assert not os.path.exists(os.path.join(object_storage.local_storage_path, uploaded[0]))


def test_inputs_filter_systems_and_structures(db_conn, seeded):
    from analysis.db_source import iter_observations

    project, _, _ = seeded
    counts = {}
    obs = list(iter_observations(db_conn, project.id, {"designs": ["role_swap"], "systems": ["sys_b"]}, counts))
    assert obs and {o.system for o in obs} == {"sys_b"}
    assert counts["variant_tasks"] == UNITS * 4
    assert counts["failed_generations"] == 0
    counts = {}
    list(iter_observations(db_conn, project.id, {"designs": ["role_swap"], "systems": ["sys_a"]}, counts))
    assert counts["failed_generations"] == 1
    assert list(iter_observations(db_conn, project.id, {"designs": ["role_swap"], "structures": ["other"]})) == []
    assert list(iter_observations(db_conn, project.id, {"designs": ["no_such_design"]})) == []


def _record_system_keys(db_conn, project, keys, as_text=True):
    """Give the completed ``sys_a`` generations of the design a recorded
    system block, alternating over ``keys`` (two parameter profiles of one
    model); the other systems keep answers without one (generated before
    2.56). ``as_text`` stores the metadata as JSON text, as the generation
    worker does; otherwise as a JSON object."""
    from models import Generation
    from project_models import Task

    gens = (
        db_conn.query(Generation).join(Task, Task.id == Generation.task_id)
        .filter(Task.project_id == project.id, Generation.model_id == "sys_a", Generation.status == "completed")
        .order_by(Generation.id).all()
    )
    for i, gen in enumerate(gens):
        metadata = {"provider": "test", "system": {"key": keys[i % len(keys)], "model_id": "sys_a"}}
        gen.response_metadata = json.dumps(metadata) if as_text else metadata
    db_conn.commit()


@pytest.mark.parametrize("as_text", [True, False], ids=["json_text", "json_object"])
def test_the_system_is_the_recorded_system_key_with_the_model_id_as_fallback(db_conn, seeded, as_text):
    project, user, _ = seeded
    _record_system_keys(db_conn, project, ["sys_a@aaaaaaaaaaaa"], as_text=as_text)
    run = _new_run(db_conn, project, user)
    assert tasks.run_analysis.apply(args=[run.id]).get()["status"] == "completed"
    run, _ = _reload(db_conn, run.id)
    from storage.object_storage import object_storage

    with open(os.path.join(object_storage.local_storage_path, run.frame_object_key), "rb") as fh:
        frame = from_parquet(fh.read())
    pairs = set(zip(frame["system"], frame["model_id"]))
    assert pairs == {("sys_a@aaaaaaaaaaaa", "sys_a"), ("sys_b", "sys_b"), ("sys_c", "sys_c")}


def test_inputs_systems_select_by_system_key_or_by_model_id(db_conn, seeded):
    from analysis.db_source import iter_observations

    project, _, _ = seeded
    first, second = "sys_a@aaaaaaaaaaaa", "sys_a@bbbbbbbbbbbb"
    _record_system_keys(db_conn, project, [first, second])
    inputs = {"designs": ["role_swap"]}
    everything = list(iter_observations(db_conn, project.id, inputs))
    assert {o.system for o in everything} == {first, second, "sys_b", "sys_c"}

    by_key = list(iter_observations(db_conn, project.id, {**inputs, "systems": [first]}))
    assert by_key and {(o.system, o.model_id) for o in by_key} == {(first, "sys_a")}
    by_model = list(iter_observations(db_conn, project.id, {**inputs, "systems": ["sys_a"]}))
    assert {o.system for o in by_model} == {first, second}
    assert len(by_model) == sum(o.model_id == "sys_a" for o in everything)
    fallback = list(iter_observations(db_conn, project.id, {**inputs, "systems": ["sys_b"]}))
    assert fallback and {(o.system, o.model_id) for o in fallback} == {("sys_b", "sys_b")}


def test_unreadable_metadata_falls_back_to_the_model_id(db_conn, seeded):
    from analysis.db_source import iter_observations
    from models import Generation
    from project_models import Task

    project, _, _ = seeded
    inputs = {"designs": ["role_swap"], "systems": ["sys_a"]}
    before = list(iter_observations(db_conn, project.id, inputs))
    gens = (
        db_conn.query(Generation).join(Task, Task.id == Generation.task_id)
        .filter(Task.project_id == project.id, Generation.model_id == "sys_a", Generation.status == "completed")
        .order_by(Generation.id).all()
    )
    shapes = ["not json", json.dumps(["sys_a@aaaaaaaaaaaa"]), json.dumps({"system": "sys_a@aaaaaaaaaaaa"}), None]
    for i, gen in enumerate(gens):
        gen.response_metadata = shapes[i % len(shapes)]
    db_conn.commit()
    observed = list(iter_observations(db_conn, project.id, inputs))
    assert before and [o.generation_id for o in observed] == [o.generation_id for o in before]
    assert {o.system for o in observed} == {"sys_a"}


def test_retried_is_the_generations_format_retry_flag(db_conn, seeded):
    from analysis.db_source import iter_observations
    from models import Generation

    project, _, _ = seeded
    inputs = {"designs": ["role_swap"]}
    before = list(iter_observations(db_conn, project.id, inputs))
    assert before and all(o.retried is False for o in before)
    first = db_conn.query(Generation).filter(Generation.id == before[0].generation_id).one()
    first.retried = True
    first.first_response_content = "first answer"
    db_conn.commit()
    observed = list(iter_observations(db_conn, project.id, inputs))
    assert {o.generation_id for o in observed if o.retried} == {first.id}
    assert all(o.retried is False for o in observed if o.generation_id != first.id)


def test_missing_run_is_skipped():
    assert tasks.run_analysis.apply(args=[str(uuid.uuid4())]).get()["status"] == "skipped"


# --------------------------------------------------------------------------
# slot frames, stored lookup tables and cross-project frames
# --------------------------------------------------------------------------


def _seed_docket_project(db_conn, make_project, user, records):
    """A project with the docket design: one task per docket, the per-slot
    answers as Label Studio results under indexed names (risk_0 ...)."""
    from estimator_synthetic import docket_design
    from models import Generation, ResponseGeneration
    from project_models import Task
    from variant_design_guard import new_design_row

    project = make_project(created_by=user.id)
    db_conn.add(new_design_row(project.id, "docket", docket_design(), created_by=user.id))
    db_conn.commit()
    task_ids = {}
    for i, rec in enumerate(records):
        if rec["task_id"] not in task_ids:
            task_ids[rec["task_id"]] = str(uuid.uuid4())
            db_conn.add(Task(id=task_ids[rec["task_id"]], project_id=project.id, data={"cases": [{}] * 6},
                             meta={"variant": rec["variant"]}, inner_id=len(task_ids)))
    db_conn.commit()
    for rec in records:
        rg = ResponseGeneration(id=str(uuid.uuid4()), project_id=project.id, task_id=task_ids[rec["task_id"]],
                                model_id=rec["model_id"], status="completed", created_by=user.id, structure_key="default")
        results = [{"from_name": name, "type": "number", "value": {"number": value}} for name, value in rec["fields"].items()]
        db_conn.add(rg)
        db_conn.add(Generation(
            id=str(uuid.uuid4()), generation_id=rg.id, task_id=rg.task_id, model_id=rec["model_id"],
            case_data="{}", response_content="...", status="completed", parsed_annotation=results,
            parse_status="success", finish_reason="stop",
        ))
    db_conn.commit()
    return project


def test_a_slot_frame_with_a_stored_lookup_across_two_projects(db_conn, make_project, make_user):
    from analysis.lookups import validate_table
    from estimator_synthetic import SECOND_PROJECT_SEED, congruence_lookup, docket_records
    from models import AnalysisLookupTable

    user = make_user()
    first_records = docket_records(dockets=30, controls=0)
    second_records = docket_records(dockets=20, controls=0, seed=SECOND_PROJECT_SEED)
    first = _seed_docket_project(db_conn, make_project, user, first_records)
    second = _seed_docket_project(db_conn, make_project, user, second_records)
    rows = congruence_lookup()
    table = validate_table({"name": "congruence", "columns": list(rows[0]), "rows": rows})
    db_conn.add(AnalysisLookupTable(project_id=first.id, name="congruence", version=1, columns=table["columns"],
                                    rows=table["rows"], row_count=table["row_count"], content_hash=table["content_hash"]))
    db_conn.commit()
    lookup = {"keys": {"system": "model", "fact": "fact", "group": "group"}, "columns": {"cong": "cong"}, "fill": {"cong": 0}}
    spec = {
        "spec_version": 1,
        "name": "slots",
        "inputs": {"designs": ["docket"], "projects": [{"project_id": second.id, "designs": ["docket"]}]},
        "frame": {"unit": "slot"},
        "lookups": [{"id": "cong", "table": {"name": "congruence", "version": 1, "content_hash": table["content_hash"]}, **lookup}],
        "measures": {
            "rank": {"kind": "field", "field": "rank_{idx}"},
            "risk": {"kind": "field", "field": "risk_{idx}"},
            "rank_valid": {"kind": "slot_aggregate", "field": "rank_{idx}", "function": "is_ranking"},
        },
        "estimands": [
            {"id": "pl", "estimator": "plackett_luce", "outcome": "rank", "subset": "rank_valid == 1",
             "terms": [{"dummies": "group", "reference": "ref"}], "vcov": {"type": "cluster", "by": ["unit"]},
             "scopes": ["pooled", {"by": ["project_id"]}]},
            {"id": "ols", "estimator": "fe_ols", "outcome": "risk", "terms": ["cong"],
             "fixed_effects": [["project_id", "unit", "system"]], "vcov": {"type": "cluster", "by": [["project_id", "unit"]]}},
        ],
    }
    run = _new_run(db_conn, first, user, spec)
    out = tasks.run_analysis.apply(args=[run.id]).get()
    assert out["status"] == "completed", out
    run, estimates = _reload(db_conn, run.id)
    assert run.status == "completed", run.error_message
    assert run.frame_rows == 6 * 3 * (30 + 20)
    assert run.frame_counts["projects"] == 2 and run.frame_counts["variant_tasks"] == 50
    assert run.resolved_inputs == {
        "projects": [second.id],
        "lookups": [{"id": "cong", "project_id": first.id, "name": "congruence", "version": 1,
                     "content_hash": table["content_hash"], "row_count": len(rows)}],
        "models": sorted({r["model_id"] for r in first_records + second_records}),
    }

    # the same analysis on the records in memory
    memory_spec = normalize_spec({**spec, "lookups": [{"id": "cong", "rows": rows, **lookup}]})
    records = [dict(r, project_id=first.id) for r in first_records] + [
        dict(r, project_id=second.id, generation_id="b" + r["generation_id"], task_id="b" + r["task_id"])
        for r in second_records
    ]
    built = build_frame(observations_from_records(records), memory_spec, home_project=first.id)
    expected = run_spec(built.frame, memory_spec).estimates
    assert [(e.estimand_id, e.contrast_id) for e in estimates] == [(x["estimand_id"], x["contrast_id"]) for x in expected]
    scopes = {e.scope for e in estimates}
    assert f"project_id={first.id}" in scopes and f"project_id={second.id}" in scopes
    for row, ref in zip(estimates, expected):
        assert row.status == ref["status"] == "ok"
        assert math.isclose(row.estimate, ref["estimate"], rel_tol=1e-9)
        assert math.isclose(row.std_error, ref["std_error"], rel_tol=1e-9)


def test_a_missing_lookup_table_fails_the_run(db_conn, seeded):
    project, user, _ = seeded
    spec = role_swap_spec()
    spec["lookups"] = [{"id": "x", "table": {"name": "nope", "version": 1}, "keys": {"unit": "u"}, "columns": {"c": "c"}}]
    run = _new_run(db_conn, project, user, spec)
    tasks.run_analysis.apply(args=[run.id]).get()
    run, _ = _reload(db_conn, run.id)
    assert run.status == "failed" and "'nope' version 1 does not exist" in run.error_message


def _cross_project_spec(other_id, *, via_lookup=False):
    spec = role_swap_spec()
    if via_lookup:
        spec["lookups"] = [{"id": "x", "table": {"name": "codes", "version": 1, "project_id": other_id},
                            "keys": {"unit": "u"}, "columns": {"c": "c"}}]
    else:
        spec["inputs"] = {**spec["inputs"], "projects": [{"project_id": other_id, "designs": ["role_swap"]}]}
    return spec


@pytest.mark.parametrize("purged", [True, False], ids=["purged", "soft_deleted"])
@pytest.mark.parametrize("via_lookup", [False, True], ids=["input_project", "lookup_owner"])
def test_a_run_whose_input_project_is_gone_fails(db_conn, seeded, make_project, purged, via_lookup):
    from datetime import datetime, timezone

    import analysis_jobs.service as service
    from project_purge import purge_project_data

    project, user, _ = seeded
    other = make_project(created_by=user.id)
    run = _new_run(db_conn, project, user, _cross_project_spec(other.id, via_lookup=via_lookup))
    other.deleted_at = datetime.now(timezone.utc)
    db_conn.commit()
    if purged:
        purge_project_data(db_conn, other.id)
        db_conn.commit()
    uploads = []

    class RecordingStorage:
        def upload_file(self, *args, **kwargs):
            uploads.append(args)
            raise AssertionError("no frame may be stored")

    assert service.run_analysis_impl(run.id, storage=RecordingStorage())["status"] == "failed"
    run, estimates = _reload(db_conn, run.id)
    assert run.status == "failed" and run.error_message == f"input project {other.id} was deleted; the run cannot read it"
    assert run.frame_object_key is None and estimates == [] and uploads == []


def test_an_input_project_deleted_during_the_run_fails_it_and_leaves_no_frame(db_conn, seeded, make_project, monkeypatch):
    from datetime import datetime, timezone

    import analysis_jobs.service as service
    import analysis.runner as runner
    from project_models import Project
    from storage.object_storage import object_storage

    project, user, _ = seeded
    other = make_project(created_by=user.id)
    run = _new_run(db_conn, project, user, _cross_project_spec(other.id))
    real_run_spec = runner.run_spec

    def run_spec_then_delete(frame, spec):
        result = real_run_spec(frame, spec)
        db_conn.query(Project).filter(Project.id == other.id).update({"deleted_at": datetime.now(timezone.utc)})
        db_conn.commit()
        return result

    monkeypatch.setattr(runner, "run_spec", run_spec_then_delete)
    uploaded = []

    class RecordingStorage:
        def upload_file(self, *args, **kwargs):
            stored = object_storage.upload_file(*args, **kwargs)
            uploaded.append(stored["file_key"])
            return stored

        def delete_file(self, key):
            return object_storage.delete_file(key)

    assert service.run_analysis_impl(run.id, storage=RecordingStorage())["status"] == "failed"
    run, estimates = _reload(db_conn, run.id)
    assert run.status == "failed" and f"input project {other.id} was deleted" in run.error_message
    assert run.frame_object_key is None and estimates == []
    assert len(uploaded) == 1
    assert not os.path.exists(os.path.join(object_storage.local_storage_path, uploaded[0]))
