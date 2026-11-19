"""Codes end to end in the test database.

A source project holds eight invented answers to variant tasks. A coding
project shows all eight; one human coder codes the control ``side`` and a
judge system's generations on the coding project code it too. Validations
of a text pattern code, an overlay's coder plugin and the judge run through
``tasks.run_code_validation``; analysis runs then read the codes, and a
confirmatory family needs the matching validation.

Hand computation (the seeded toy coding project)::

    answer     1  2  3  4  5     6     7  8
    pattern    P  D  P  D  none  P     D  none
    human      P  D  P  P  none  none  D  D
    judge      P  D  D  P  none  none  D  D

Pattern (and coder, which codes the same here) against the human: 5 of 8
agree, po = 0.625; both sides P 3, D 3, none 2, so pe = 22/64; kappa =
(9/32) / (21/32) = 3/7. Judge against the human: 7 of 8 agree, judge P 2,
D 4, none 2, pe = 22/64; kappa = (17/32) / (21/32) = 17/21.
"""

from __future__ import annotations

import json
import os
import sys
import types
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "analysis"))

import extension_registry  # noqa: E402
import overlay_coder_fixture  # noqa: E402
import tasks  # noqa: E402
from analysis.coders import coder_registry, load_overlay_coders  # noqa: E402
from analysis.spec import normalize_spec, spec_hash  # noqa: E402
from analysis.version import ENGINE_VERSION, SPEC_VERSION  # noqa: E402
from core_version import CORE_API_VERSION  # noqa: E402

ANSWERS = [
    "The claimant caused it.",
    "The respondent caused it.",
    "Both, but mainly the claimant.",
    "The respondent, perhaps.",
    "Unclear.",
    "The claimant and the respondent share it.",
    "The respondent.",
    "No fault.",
]
HUMAN = ["P", "D", "P", "P", "none", "none", "D", "D"]
JUDGE = ["P", "D", "D", "P", "none", "none", "D", "D"]
SCHEME = (
    '<View><Text name="answer" value="$answer"/>'
    '<Choices name="side" toName="answer"><Choice value="P"/><Choice value="D"/><Choice value="none"/></Choices>'
    "</View>"
)
PATTERN_SET = {
    "name": "blame",
    "version": "1",
    "flags": ["IGNORECASE"],
    "codes": {
        "side": {
            "mode": "first",
            "default": "none",
            "rules": [
                {"value": "P", "patterns": [r"\bclaimant\b"]},
                {"value": "D", "patterns": [r"\brespondent\b"]},
            ],
        }
    },
}
OVERLAY = "benger_codes_overlay_e2e"


def _choice(value):
    return [{"from_name": "side", "to_name": "answer", "type": "choices", "value": {"choices": [value]}}]


@pytest.fixture()
def coded(db_conn, make_project, make_user):
    from models import CodingProject, Generation, ResponseGeneration
    from project_models import Annotation, Task
    from variant_design_guard import new_design_row

    owner = make_user()
    coder = make_user(name="Human Coder")
    source = make_project(created_by=owner.id, title="Source")
    db_conn.add(new_design_row(source.id, "d", {
        "schema_version": 1, "title": "Codes", "unit": {"name": "case"},
        "factors": [{"name": "swap", "type": "numeric", "minimum": 0, "maximum": 1, "varies": "between_units"}],
    }, created_by=owner.id))
    db_conn.commit()
    coding = make_project(created_by=owner.id, title="Coding", label_config=SCHEME)
    rows, gens, coding_tasks = [], [], []
    for i, text in enumerate(ANSWERS):
        tid = str(uuid.uuid4())
        rows.append(Task(id=tid, project_id=source.id, data={"text": f"case {i}"}, inner_id=i + 1,
                         meta={"benger_variant": {"design": "d", "unit": f"u{i}", "factors": {"swap": 0}}}))
        rg = ResponseGeneration(id=str(uuid.uuid4()), project_id=source.id, task_id=tid, model_id="sys_a",
                                status="completed", created_by=owner.id, structure_key="default")
        gid = str(uuid.uuid4())
        gens += [rg, Generation(id=gid, generation_id=rg.id, task_id=tid, model_id="sys_a", case_data="{}",
                                response_content=text, status="completed", parsed_annotation=[],
                                parse_status="success", response_metadata=json.dumps({"provider": "test"}))]
        coding_tasks.append(Task(
            id=str(uuid.uuid4()), project_id=coding.id, data={"answer": text}, inner_id=i + 1,
            meta={"coding": {"source_project_id": source.id, "source_task_id": tid,
                             "source_generation_id": gid, "answer_source": "answer",
                             "sample_seed": 1, "sample_rank": f"{i:064x}"}},
        ))
    db_conn.add_all(rows + coding_tasks)
    db_conn.commit()
    db_conn.add_all(gens)
    db_conn.add(CodingProject(project_id=coding.id, source_project_id=source.id, answer_source="answer",
                              context_fields=[], sample={"seed": 1, "size": None, "drawn": 8},
                              coding_version=1, created_by=owner.id))
    judge = []
    for task, human, jv in zip(coding_tasks, HUMAN, JUDGE):
        db_conn.add(Annotation(id=str(uuid.uuid4()), task_id=task.id, project_id=coding.id,
                               completed_by=coder.id, result=_choice(human)))
        rg = ResponseGeneration(id=str(uuid.uuid4()), project_id=coding.id, task_id=task.id, model_id="judge-m",
                                status="completed", created_by=owner.id, structure_key="judge")
        judge += [rg, Generation(id=str(uuid.uuid4()), generation_id=rg.id, task_id=task.id, model_id="judge-m",
                                 case_data="{}", response_content=jv, status="completed",
                                 parsed_annotation=_choice(jv), parse_status="success")]
    # a cancelled annotation and another system's answer do not count
    db_conn.add(Annotation(id=str(uuid.uuid4()), task_id=coding_tasks[0].id, project_id=coding.id,
                           completed_by=owner.id, result=_choice("D"), was_cancelled=True))
    other = ResponseGeneration(id=str(uuid.uuid4()), project_id=coding.id, task_id=coding_tasks[0].id,
                               model_id="other-m", status="completed", created_by=owner.id, structure_key="judge")
    judge += [other, Generation(id=str(uuid.uuid4()), generation_id=other.id, task_id=coding_tasks[0].id,
                                model_id="other-m", case_data="{}", response_content="D", status="completed",
                                parsed_annotation=_choice("D"), parse_status="success")]
    db_conn.commit()
    db_conn.add_all(judge)
    db_conn.commit()
    return {"source": source, "coding": coding, "owner": owner, "coder": coder}


def _validation(db_conn, ctx, code, control="side", **options):
    from analysis.coding import normalize_validation_code
    from models import CodeValidation

    normalized = normalize_validation_code(code, coding_project_id=ctx["coding"].id, answer_source="answer")
    if normalized["kind"] == "judge_code":
        normalized.setdefault("field", control)
    v = CodeValidation(project_id=ctx["coding"].id, source_project_id=ctx["source"].id,
                       created_by=ctx["owner"].id, name="v", control=control, code=code,
                       normalized_code=normalized, code_kind=normalized["kind"],
                       options={"missing": "category", "value_map": {}, **options}, coding_version=1)
    db_conn.add(v)
    db_conn.commit()
    assert tasks.run_code_validation.apply(args=[v.id]).get()["status"] in ("completed", "failed")
    db_conn.expire_all()
    return db_conn.query(CodeValidation).filter(CodeValidation.id == v.id).one()


def _run(db_conn, ctx, spec):
    from models import AnalysisRun

    normalized = normalize_spec(spec)
    run = AnalysisRun(project_id=ctx["source"].id, created_by=ctx["owner"].id, name="codes", spec=spec,
                      normalized_spec=normalized, spec_hash=spec_hash(normalized),
                      spec_version=SPEC_VERSION, engine_version=ENGINE_VERSION)
    db_conn.add(run)
    db_conn.commit()
    tasks.run_analysis.apply(args=[run.id]).get()
    db_conn.expire_all()
    return db_conn.query(AnalysisRun).filter(AnalysisRun.id == run.id).one()


def _spec(measures, family=True):
    spec = {
        "spec_version": 1, "name": "codes", "inputs": {"designs": ["d"]},
        "measures": {**measures, "blames_p": {"kind": "expression", "expr": "100 * (side == 'P')"}},
        "estimands": [{"id": "rate", "estimator": "mean_rate", "outcome": "blames_p"}],
    }
    if family:
        spec["families"] = [{"id": "main", "method": "holm", "members": [{"estimand": "rate"}]}]
    return spec


@pytest.fixture()
def overlay(monkeypatch):
    pkg = types.ModuleType(OVERLAY)
    pkg.__file__ = f"/fake/{OVERLAY}/__init__.py"
    pkg.COMPATIBLE_CORE_VERSIONS = [CORE_API_VERSION]
    workers = types.ModuleType(f"{OVERLAY}.workers")
    workers.register_coders = overlay_coder_fixture.register_coders
    pkg.workers = workers
    monkeypatch.setitem(sys.modules, OVERLAY, pkg)
    monkeypatch.setitem(sys.modules, workers.__name__, workers)
    monkeypatch.setenv("BENGER_EXTENSIONS", OVERLAY)
    extension_registry.reset()
    coder_registry.unregister("first_blamed")
    load_overlay_coders(force=True)
    yield
    coder_registry.unregister("first_blamed")
    extension_registry.reset()


def test_text_pattern_validation_kappa_is_three_sevenths(db_conn, coded):
    v = _validation(db_conn, coded, {"kind": "text_pattern", "set": PATTERN_SET, "code": "side"})
    assert v.status == "completed", v.error_message
    assert v.kappa == pytest.approx(3 / 7, abs=1e-15)
    assert v.observed_agreement == pytest.approx(0.625, abs=1e-15)
    assert v.n_items == 8 and v.n_compared == 8
    assert v.code_ref == "blame@1:side" and v.code_version == "1" and len(v.code_hash) == 64
    assert [i["automatic"] for i in v.items] == ["P", "D", "P", "D", "none", "P", "D", "none"]
    assert v.metrics["automatic_vs_reference"]["expected_agreement"] == pytest.approx(22 / 64, abs=1e-15)
    assert list(v.metrics["automatic_vs_coders"].values())[0]["kappa"] == pytest.approx(3 / 7, abs=1e-15)


def test_judge_validation_kappa_is_seventeen_twentyfirsts(db_conn, coded):
    v = _validation(db_conn, coded, {"kind": "judge_code", "system": "judge-m", "structure": "judge"})
    assert v.status == "completed", v.error_message
    assert v.kappa == pytest.approx(17 / 21, abs=1e-15)
    assert v.identity["coding"]["matched"] == 8 and v.identity["coding"]["ambiguous"] == 0


def test_overlay_coder_validation_records_its_hash(db_conn, coded, overlay):
    v = _validation(db_conn, coded, {"kind": "coder", "coder": "first_blamed", "output": "side",
                                     "parameters": {"default": "none"}})
    assert v.status == "completed", v.error_message
    assert v.kappa == pytest.approx(3 / 7, abs=1e-15)
    entry = coder_registry.get("first_blamed")
    assert v.identity["code_hash"] == entry.code_hash and v.identity["owner"] == OVERLAY
    assert v.code_ref == "first_blamed@2:side"


def test_an_unknown_coder_fails_the_validation_with_its_message(db_conn, coded):
    v = _validation(db_conn, coded, {"kind": "coder", "coder": "never_registered", "output": "side"})
    assert v.status == "failed" and "no coder 'never_registered'" in v.error_message


def test_a_confirmatory_family_needs_the_matching_validation(db_conn, coded):
    measure = {"kind": "text_pattern", "set": PATTERN_SET, "code": "side"}
    failed = _run(db_conn, coded, _spec({"side": measure}))
    assert failed.status == "failed" and "names no validation" in failed.error_message

    exploratory = _spec({"side": measure})
    exploratory["families"][0]["exploratory"] = True
    exploratory["families"][0]["method"] = "bh"
    assert _run(db_conn, coded, exploratory).status == "completed"

    judge_v = _validation(db_conn, coded, {"kind": "judge_code", "system": "judge-m", "structure": "judge"})
    wrong = _run(db_conn, coded, _spec({"side": {**measure, "validation": judge_v.id}}))
    assert wrong.status == "failed" and "validated another code" in wrong.error_message

    v = _validation(db_conn, coded, {"kind": "text_pattern", "set": PATTERN_SET, "code": "side"})
    ok = _run(db_conn, coded, _spec({"side": {**measure, "validation": v.id}}))
    assert ok.status == "completed", ok.error_message
    record = ok.codes[0]
    assert record["measure"] == "side" and record["hash"] == v.code_hash
    assert record["validation"]["id"] == v.id
    assert record["validation"]["kappa"] == pytest.approx(3 / 7, abs=1e-15)
    assert record["confirmatory_estimands"] == ["rate"]
    assert ok.frame_counts["observations"] == 8


def test_a_validation_without_compared_items_fails_and_is_refused(db_conn, coded):
    measure = {"kind": "text_pattern", "set": PATTERN_SET, "code": "side"}
    empty = _validation(db_conn, coded, measure, control="uncoded")
    assert empty.status == "failed" and empty.kappa is None
    assert empty.error_message == "no coding task has both a human and a usable reference code"
    refused = _run(db_conn, coded, _spec({"side": {**measure, "validation": empty.id}}))
    assert refused.status == "failed" and "is failed, not completed" in refused.error_message

    v = _validation(db_conn, coded, measure)
    assert v.status == "completed" and v.n_compared == 8
    assert _run(db_conn, coded, _spec({"side": {**measure, "validation": v.id}})).status == "completed"
    v.n_compared, v.kappa = 0, None
    db_conn.commit()
    hollow = _run(db_conn, coded, _spec({"side": {**measure, "validation": v.id}}))
    assert hollow.status == "failed" and "compared 0 item(s) and has no kappa" in hollow.error_message


def test_judge_codes_reach_the_frame_of_the_source_project(db_conn, coded):
    from analysis.frame import from_parquet
    from storage.object_storage import object_storage

    v = _validation(db_conn, coded, {"kind": "judge_code", "system": "judge-m", "structure": "judge"})
    measure = {"kind": "judge_code", "coding_project": coded["coding"].id, "field": "side",
               "system": "judge-m", "structure": "judge", "validation": v.id}
    run = _run(db_conn, coded, _spec({"side": measure}))
    assert run.status == "completed", run.error_message
    with open(os.path.join(object_storage.local_storage_path, run.frame_object_key), "rb") as fh:
        frame = from_parquet(fh.read())
    by_unit = dict(zip(frame["unit"], frame["side"]))
    assert [by_unit[f"u{i}"] for i in range(8)] == JUDGE
    assert run.codes[0]["coding"]["matched"] == 8
    # without a structure the other system's answer on the first task is
    # still no match: the measure names the judge system
    loose_measure = {k: v for k, v in measure.items() if k not in ("structure", "validation")}
    loose = _run(db_conn, coded, _spec({"side": loose_measure}, family=False))
    assert loose.status == "completed", loose.error_message


def test_overlay_coder_measure_records_its_hash_in_the_run(db_conn, coded, overlay):
    measure = {"kind": "coder", "coder": "first_blamed", "output": "side", "parameters": {"default": "none"}}
    run = _run(db_conn, coded, _spec({"side": measure}, family=False))
    assert run.status == "completed", run.error_message
    record = run.codes[0]
    assert record["kind"] == "coder" and record["code_hash"] == coder_registry.get("first_blamed").code_hash
    assert record["owner"] == OVERLAY and record["version"] == "2"
    assert record["missing"] == 0


def test_an_overlay_coder_switched_off_for_the_project_does_not_run(db_conn, coded, overlay, monkeypatch):
    """The workers decide a coder's activation for the row's project and
    creator, not for a context-free system task."""
    import extension_activation

    seen = []

    def active_outside_the_source_and_coding_projects(package, gating="gated"):
        ctx = extension_activation.current_context()
        seen.append((package, ctx.project_id, ctx.user_id))
        return ctx.project_id not in (coded["source"].id, coded["coding"].id)

    monkeypatch.setattr(extension_activation, "package_active", active_outside_the_source_and_coding_projects)
    code = {"kind": "coder", "coder": "first_blamed", "output": "side", "parameters": {"default": "none"}}
    v = _validation(db_conn, coded, code)
    assert v.status == "failed" and "switched off" in v.error_message
    assert (OVERLAY, coded["coding"].id, coded["owner"].id) in seen

    seen.clear()
    run = _run(db_conn, coded, _spec({"side": code}, family=False))
    assert run.status == "failed" and "switched off" in run.error_message
    assert (OVERLAY, coded["source"].id, coded["owner"].id) in seen
