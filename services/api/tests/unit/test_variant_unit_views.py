"""The unit view of a variant design shaped from rows (``variant_unit_views``,
no database): texts with their declared spans, gold values, the answers of
one system, the unit's check and the caps. The queries are covered by
tests/integration/test_variant_units_api.py. Invented content only."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import variant_unit_views as units
from ai_services.request_capture import request_sha256

RECORD = {"version": 1, "requests": [{"body": {"model": "sim-a", "messages": []}}]}

SPEC = {
    "schema_version": 1,
    "unit": {"name": "case"},
    "factors": [
        {"name": "party", "type": "nominal", "levels": ["A", "B"]},
        {"name": "level", "type": "numeric", "varies": "between_units"},
    ],
    "gold": [
        {"name": "fault", "path": "bench.fault"},
        {"name": "extra", "path": "bench.missing", "required": False},
    ],
    "invariance": {"fields": ["case"], "free": ["note"]},
}
SYS = "sim-a@aaaaaaaaaaaa"


def task(task_id, party, name, *, note="n"):
    text = f"Tenant {name} paid."
    return (
        task_id,
        1 if party == "A" else 2,
        {"case": text, "note": note, "bench": {"fault": 40}, "other": 1},
        {
            "variant": {
                "design": "swap",
                "unit": "u1",
                "factors": {"party": party, "level": 40},
                "spans": {"case": [[7, 7 + len(name)]]},
            }
        },
    )


def gen(
    gen_id,
    task_id,
    *,
    model="sim-a",
    system=SYS,
    run=0,
    record=False,
    metadata="json",
    record_type=None,
    first_request=None,
    sha=None,
):
    meta = {"system": {"key": system}} if system else None
    return SimpleNamespace(
        id=gen_id,
        generation_id=f"p-{gen_id}",
        task_id=task_id,
        model_id=model,
        run_index=run,
        status="completed",
        response_content='{"share": 40}',
        parsed_annotation=[{"from_name": "share", "type": "number", "value": {"number": 40}}],
        parse_status="success",
        refusal=False,
        truncated=False,
        finish_reason="stop",
        retried=False,
        response_metadata=json.dumps(meta) if metadata == "json" and meta else meta,
        request_sha256=request_sha256(RECORD) if record else sha,
        record_type="object" if record else record_type,
        first_request=RECORD["requests"][0] if record else first_request,
        created_at=datetime(2026, 11, 19, tzinfo=timezone.utc),
        structure_key="default",
    )


def design(spec=SPEC):
    return SimpleNamespace(
        key="swap", version=1, status="frozen", content_hash="c", frozen_at=None, spec=spec
    )


def test_unit_view_shapes_tasks_spans_gold_answers_and_check():
    rows = [task("ta", "A", "Ada"), task("tb", "B", "Bea")]
    gens = [
        gen("g1", "ta", record=True),
        gen("g2", "ta", run=1, metadata="dict"),
        gen("g3", "tb", model="sim-b", system=None),
        gen("g4", "elsewhere"),
    ]
    view = units.shape_unit_view("p", design(), rows, gens, "u1", SYS)
    assert view["systems"] == [SYS, "sim-b"]
    assert view["check"]["ok"] is True and view["check"]["task_count"] == 2
    assert view["tasks_truncated"] is False
    assert [t["generations_truncated"] for t in view["tasks"]] == [False, False]
    assert view["design"]["unit_name"] == "case"
    assert [f["name"] for f in view["design"]["factors"]] == ["party", "level"]
    ta = view["tasks"][0]
    assert ta["factors"] == {"party": "A", "level": 40}
    assert ta["texts"] == [
        {"path": "case", "kind": "spanned", "text": "Tenant Ada paid.", "truncated": False, "spans": [[7, 10]]},
        {"path": "note", "kind": "free", "text": "n", "truncated": False, "spans": []},
        {"path": "bench.fault", "kind": "fixed", "text": "40", "truncated": False, "spans": []},
        {"path": "other", "kind": "fixed", "text": "1", "truncated": False, "spans": []},
    ]
    assert ta["slots"] == []
    assert ta["gold"] == [
        {"name": "fault", "path": "bench.fault", "value": 40},
        {"name": "extra", "path": "bench.missing", "value": None},
    ]
    assert [(g["id"], g["run_index"], g["has_request_record"], g["fields"]) for g in ta["generations"]] == [
        ("g1", 0, True, {"share": 40}),
        ("g2", 1, False, {"share": 40}),
    ]
    assert ta["generations"][0]["created_at"] == "2026-11-19T00:00:00+00:00"
    # The other system's answer is filtered out; by model id it is chosen.
    assert view["tasks"][1]["generations"] == []
    by_model = units.shape_unit_view("p", design(), rows, gens, "u1", "sim-b")
    assert [g["id"] for g in by_model["tasks"][1]["generations"]] == ["g3"]


def test_unit_view_gives_each_answer_the_hash_check_of_the_request_route():
    """Each answer carries the state the request route reports for it: a
    tampered or non-object record is a mismatch, only a hash without any
    record is not checkable."""
    digest = request_sha256(RECORD)
    first = RECORD["requests"][0]
    gens = [
        gen("ok", "ta", record=True),
        gen("changed", "ta", record_type="object", first_request={"body": {"model": "x"}}, sha=digest),
        gen("emptied", "ta", record_type="object", first_request=None, sha=digest),
        gen("listed", "ta", record_type="array", sha=digest),
        gen("sql_null", "ta", sha=digest),
        gen("json_null", "ta", record_type="null", sha=digest),
        gen("unhashed", "ta", record_type="object", first_request=first),
    ]
    view = units.shape_unit_view("p", design(), [task("ta", "A", "Ada")], gens, "u1")
    states = {g["id"]: (g["hash_check"], g["has_request_record"]) for g in view["tasks"][0]["generations"]}
    assert states == {
        "ok": ("verified", True),
        "changed": ("mismatch", True),
        "emptied": ("mismatch", True),
        "listed": ("mismatch", False),
        "sql_null": ("record_missing", False),
        "json_null": ("record_missing", False),
        "unhashed": ("no_hash", True),
    }


def test_hash_check_pins_well_formed_hashes_and_flags_malformed_requests():
    """The hash of a well-formed record is the SHA-256 of its first request's
    body in canonical JSON (sorted keys, no whitespace); the constant is that
    digest of '{"messages":[],"model":"sim-a"}' taken with sha256sum. A
    record whose requests are not a list starting with an object has no
    hash and is a mismatch, never an error."""
    from ai_services.request_capture import hash_check

    known = "6e1e489a9e44a8a43d7f8971ba5d576844010e11ac9c43057a135a88e69e071e"
    assert request_sha256(RECORD) == known
    assert hash_check(RECORD, known) == ("verified", known)
    for malformed in [
            {"requests": [1]},
            {"requests": [None]},
            {"requests": "x"},
            {"requests": {"0": {"body": {"model": "sim-model"}}}},
        ]:
        assert request_sha256(malformed) is None
        assert hash_check(malformed, known) == ("mismatch", None)


def test_unit_view_reports_the_unit_check_and_caps_what_it_returns(monkeypatch):
    rows = [
        task("ta", "A", "Ada", note="x"),
        task("tb", "B", "Bea", note="y"),
        ("bad", None, {"case": "?"}, None),
    ]
    monkeypatch.setattr(units, "MAX_UNIT_TASKS", 2)
    monkeypatch.setattr(units, "MAX_RUNS_PER_TASK", 1)
    monkeypatch.setattr(units, "MAX_TEXT", 8)
    view = units.shape_unit_view("p", design(), rows, [gen("g1", "ta"), gen("g2", "ta", run=1)], "u1")
    assert view["tasks_truncated"] is True and len(view["tasks"]) == 2
    assert [g["id"] for g in view["tasks"][0]["generations"]] == ["g1"]
    assert [t["generations_truncated"] for t in view["tasks"]] == [True, False]
    assert view["tasks"][0]["generations"][0]["response_truncated"] is True
    case = view["tasks"][0]["texts"][0]
    assert case["text"] == "Tenant A" and case["truncated"] is True and case["spans"] == [[7, 8]]
    # Without a free path the differing note breaks invariance.
    strict = dict(SPEC, invariance={"fields": ["case"]})
    view = units.shape_unit_view("p", design(strict), rows[:2], [], "u1")
    assert view["check"]["ok"] is False
    assert view["check"]["invariance"]["problems"][0]["kind"] == "value_differs"
    # A task without a variant assignment is reported, not dropped.
    view = units.shape_unit_view("p", design(), [rows[2]], [], "u1")
    assert view["tasks"][0]["factors"] == {} and view["check"]["assignments"]["ok"] is False
    # Leaves beyond the cap are left out, the varying ones kept first.
    monkeypatch.setattr(units, "MAX_LEAVES", 1)
    view = units.shape_unit_view("p", design(), rows[:1], [], "u1")
    assert [t["path"] for t in view["tasks"][0]["texts"]] == ["case"]


def test_unit_view_lists_the_slots_of_a_task():
    spec = {
        "schema_version": 1,
        "unit": {"name": "roster"},
        "factors": [{"name": "kind", "type": "nominal", "levels": ["a", "b"], "varies": "between_units"}],
        "slots": {"count": 2, "index_base": 0, "factors": [{"name": "pos", "type": "numeric"}]},
    }
    row = (
        "t1",
        1,
        {"case": "Roster one"},
        {
            "variant": {
                "design": "swap",
                "unit": "u1",
                "factors": {"kind": "a"},
                "slots": [{"index": 1, "factors": {"pos": 2}}, {"index": 0, "factors": {"pos": 1}}],
            }
        },
    )
    view = units.shape_unit_view("p", design(spec), [row], [], "u1")
    (task,) = view["tasks"]
    assert task["slots"] == [{"index": 0, "factors": {"pos": 1}}, {"index": 1, "factors": {"pos": 2}}]
    assert task["texts"] == [
        {"path": "case", "kind": "fixed", "text": "Roster one", "truncated": False, "spans": []}
    ]
