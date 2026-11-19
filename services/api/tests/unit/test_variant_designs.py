"""The pure rules of variant designs (``shared/variant_designs.py``).

Synthetic, hand-computed examples: a party-swap design (two roles times two
print orders per case, a between-case difficulty, a system factor that is
not stored per task), a per-slot design, span invariance, the content hash.
"""

import copy
import json

import pytest

import variant_designs as vd
from variant_design_guard import FLAT_META_COLUMN, VariantDesignError, error_from_db, lift_flat_meta

CLAIMANT = "Alma Reyes"
RESPONDENT = "Bodo Lind"


def swap_spec():
    return {
        "schema_version": 1,
        "title": "Party swap",
        "unit": {"name": "case"},
        "factors": [
            {"name": "role", "type": "nominal", "levels": ["claimant", "respondent"]},
            {
                "name": "order",
                "type": "nominal",
                "levels": ["claimant_first", "respondent_first"],
                "role": "counterbalanced",
            },
            {"name": "difficulty", "type": "numeric", "varies": "between_units", "minimum": 0},
            {"name": "reasoning", "type": "boolean", "source": "system"},
        ],
        "outcomes": [
            {
                "name": "share",
                "by_factor": {
                    "factor": "role",
                    "controls": {"claimant": "share_claimant", "respondent": "share_respondent"},
                },
            }
        ],
        "gold": [{"name": "fair_low", "path": "reference.low"}],
        "invariance": {"fields": ["facts"], "free": ["reference"]},
    }


def swap_task(unit, role, order, difficulty=10, *, facts=None):
    focus = CLAIMANT if role == "claimant" else RESPONDENT
    other = RESPONDENT if role == "claimant" else CLAIMANT
    if facts is None:
        first, second = (focus, other) if order == "claimant_first" else (other, focus)
        facts = f"The claim of {first} against {second} concerns a fence."
    spans = []
    for name in (CLAIMANT, RESPONDENT):
        at = facts.find(name)
        if at >= 0:
            spans.append([at, at + len(name)])
    variant = {
        "design": "swap",
        "unit": unit,
        "factors": {"role": role, "order": order, "difficulty": difficulty},
        "spans": {"facts": sorted(spans)},
        "provenance": {"generator": "unit-test"},
    }
    data = {"facts": facts, "reference": {"low": 40 + difficulty}}
    return data, variant


def records(spec=None, units=("c1", "c2")):
    out = []
    for u_index, unit in enumerate(units):
        for role in ("claimant", "respondent"):
            for order in ("claimant_first", "respondent_first"):
                data, variant = swap_task(unit, role, order, difficulty=10 * (u_index + 1))
                out.append(vd.TaskRecord(id=f"{unit}-{role}-{order}", data=data, variant=variant))
    return out


@pytest.fixture
def view():
    spec = swap_spec()
    assert vd.validate_spec(spec) == []
    return vd.DesignView.build("swap", spec)


class TestSpec:
    def test_valid_spec_has_no_problems(self):
        assert vd.validate_spec(swap_spec()) == []

    def test_schema_problems_carry_a_path(self):
        spec = swap_spec()
        spec["factors"][0]["type"] = "category"
        problems = vd.validate_spec(spec)
        assert problems and problems[0]["path"].startswith("/spec/factors/0")

    @pytest.mark.parametrize(
        "mutate, message",
        [
            (lambda s: s["factors"][0].pop("levels"), "needs levels"),
            (lambda s: s["factors"][1]["levels"].append(3.5), None),
            (lambda s: s["factors"].append({"name": "role", "type": "boolean"}), "already used"),
            (lambda s: s["factors"][2].update(levels=[1, True]), "not a numeric level"),
            (lambda s: s["factors"][3].update(varies="between_units"), "only task factors"),
            (lambda s: s["factors"][0].update(baseline="judge"), "not one of the levels"),
            (
                lambda s: s["outcomes"][0]["by_factor"]["controls"].pop("respondent"),
                "one control per level",
            ),
            (lambda s: s["outcomes"].append({"name": "x", "control": "x_{idx}"}), "needs per_slot"),
            (lambda s: s["invariance"].update(free=["facts"]), "overlaps"),
        ],
    )
    def test_semantic_rules(self, mutate, message):
        spec = swap_spec()
        mutate(spec)
        problems = vd.validate_spec(spec)
        if message is None:
            assert problems == []  # a number is a valid nominal level
        else:
            assert any(message in p["message"] for p in problems), problems

    def test_bounded_numeric_factor_with_a_text_level_is_a_problem(self):
        spec = swap_spec()
        spec["factors"].append(
            {"name": "lvl", "type": "numeric", "levels": ["high"], "minimum": 0}
        )
        index = len(spec["factors"]) - 1
        problems = vd.validate_spec(spec)
        assert {"path": f"/spec/factors/{index}/levels/0", "message": "not a numeric level"} in problems

    def test_cells_must_name_exactly_the_within_unit_task_factors(self):
        spec = swap_spec()
        spec["cells"] = [{"role": "claimant", "order": "claimant_first"}, {"role": "claimant"}]
        problems = vd.validate_spec(spec)
        assert [p["path"] for p in problems] == ["/spec/cells/1"]

    def test_design_keys(self):
        assert vd.validate_design_key("party-swap_v2.1") == []
        for bad in ("", "-x", "a b", "x" * 101, None, 7):
            assert vd.validate_design_key(bad), bad

    def test_expected_cells_are_the_product_of_within_unit_task_factors(self, view):
        assert view.within == ["role", "order"]
        assert view.between == ["difficulty"]
        assert len(view.expected_cells) == 4


class TestTaskVariant:
    def test_valid_assignment(self, view):
        data, variant = swap_task("c1", "claimant", "claimant_first")
        assert vd.validate_task_variant(view, variant, data) == []

    def test_unknown_level_and_type(self, view):
        data, variant = swap_task("c1", "judge", "claimant_first")
        variant["factors"]["difficulty"] = True  # a boolean is not a number
        paths = {p["path"] for p in vd.validate_task_variant(view, variant, data)}
        assert paths == {"/meta/benger_variant/factors/role", "/meta/benger_variant/factors/difficulty"}

    def test_factors_must_be_exactly_the_task_factors(self, view):
        data, variant = swap_task("c1", "claimant", "claimant_first")
        variant["factors"]["reasoning"] = True  # a system factor is not stored per task
        problems = vd.validate_task_variant(view, variant, data)
        assert "unknown reasoning" in problems[0]["message"]

    def test_schema_rejects_unknown_keys(self, view):
        data, variant = swap_task("c1", "claimant", "claimant_first")
        variant["twin_of"] = "c1-respondent"
        problems = vd.validate_task_variant(view, variant, data)
        assert problems[0]["path"] == "/meta/benger_variant"

    def test_spans_must_lie_in_declared_text_fields(self, view):
        data, variant = swap_task("c1", "claimant", "claimant_first")
        variant["spans"]["reference.low"] = [[0, 1]]
        variant["spans"]["facts"].append([0, 9999])
        messages = [p["message"] for p in vd.validate_task_variant(view, variant, data)]
        assert any("do not declare this path" in m for m in messages)
        assert any("outside the text" in m for m in messages)

    def test_missing_gold(self, view):
        data, variant = swap_task("c1", "claimant", "claimant_first")
        del data["reference"]
        problems = vd.validate_task_variant(view, variant, data)
        assert problems == [{"path": "/data/reference/low", "message": "gold 'fair_low' is missing"}]

    def test_listed_cells_restrict_the_assignment(self):
        spec = swap_spec()
        spec["cells"] = [
            {"role": "claimant", "order": "claimant_first"},
            {"role": "respondent", "order": "respondent_first"},
        ]
        view = vd.DesignView.build("swap", spec)
        data, variant = swap_task("c1", "claimant", "respondent_first")
        problems = vd.validate_task_variant(view, variant, data)
        assert problems[0]["message"] == "is not one of the design's cells"


def slot_spec():
    return {
        "schema_version": 1,
        "unit": {"name": "docket"},
        "factors": [{"name": "arrangement", "type": "nominal", "levels": ["a", "b"]}],
        "slots": {
            "count_from": "items",
            "index_base": 1,
            "factors": [{"name": "group", "type": "nominal", "levels": ["x", "y"]}],
        },
        "outcomes": [{"name": "risk", "control": "risk_{idx}", "per_slot": True}],
    }


class TestSlots:
    def test_slots_follow_the_task_list(self):
        view = vd.DesignView.build("dockets", slot_spec())
        data = {"items": ["first", "second"]}
        variant = {
            "design": "dockets",
            "unit": "d1",
            "factors": {"arrangement": "a"},
            "slots": [{"index": 1, "factors": {"group": "x"}}, {"index": 2, "factors": {"group": "y"}}],
        }
        assert vd.validate_task_variant(view, variant, data) == []
        variant["slots"].pop()
        assert vd.validate_task_variant(view, variant, data)[0]["message"] == "must list slots 1..2"

    def test_per_slot_outcome_needs_slots(self):
        spec = slot_spec()
        del spec["slots"]
        assert any("needs the design's slots" in p["message"] for p in vd.validate_spec(spec))


class TestChecks:
    def test_balanced_invariant_design_passes(self, view):
        report, digest = vd.check_design(view, records())
        assert report["ok"], report
        assert report["task_count"] == 8 and report["unit_count"] == 2
        assert report["invariance"]["checked_pairs"] == 12
        assert len(digest) == 64

    def test_missing_cell_fails_balance(self, view):
        report, _ = vd.check_design(view, records()[:-1])
        assert not report["ok"]
        problem = report["balance"]["problems"][0]
        assert problem["unit"] == "c2" and problem["kind"] == "cells_differ"
        assert problem["missing"] == [{"role": "respondent", "order": "respondent_first"}]

    def test_between_units_factor_must_be_constant_in_a_unit(self, view):
        recs = records()
        recs[0].variant["factors"]["difficulty"] = 99
        report, _ = vd.check_design(view, recs)
        kinds = [p["kind"] for p in report["balance"]["problems"]]
        assert kinds == ["between_units_factor_varies"]

    def test_out_of_span_difference_fails_invariance(self, view):
        recs = records()
        data, variant = swap_task("c1", "claimant", "claimant_first")
        data["facts"] = data["facts"].replace("a fence", "a hedge")
        recs[0] = vd.TaskRecord(id=recs[0].id, data=data, variant=variant)
        report, _ = vd.check_design(view, recs)
        assert not report["ok"]
        problems = report["invariance"]["problems"]
        assert {p["kind"] for p in problems} == {"differs_outside_spans"}
        assert all(p["unit"] == "c1" and p["path"] == "facts" for p in problems)
        assert "[[" in problems[0]["excerpt_a"]
        assert report["balance"]["ok"] and report["assignments"]["ok"]

    def test_strict_field_must_be_identical(self, view):
        recs = records()
        recs[0].data["court"] = "North"
        for r in recs[1:4]:
            r.data["court"] = "South"
        report, _ = vd.check_design(view, recs)
        kinds = {p["kind"] for p in report["invariance"]["problems"]}
        assert kinds == {"value_differs"}

    def test_free_fields_may_differ(self, view):
        recs = records()
        recs[0].data["reference"]["low"] = 1
        report, _ = vd.check_design(view, recs)
        assert report["invariance"]["ok"]

    def test_no_tasks_is_not_freezable(self, view):
        report, _ = vd.check_design(view, [])
        assert not report["ok"]
        assert report["assignments"]["problems"][0]["kind"] == "no_tasks"

    def test_invalid_assignments_are_listed(self, view):
        recs = records()
        recs[1].variant["factors"]["role"] = "witness"
        report, _ = vd.check_design(view, recs)
        assert report["assignments"]["problem_count"] == 1
        assert report["assignments"]["problems"][0]["task_id"] == recs[1].id

    def test_feed_requires_grouped_units(self, view):
        check = vd.DesignCheck(view)
        recs = records()
        check.feed(recs[0])
        check.feed(recs[4])
        with pytest.raises(ValueError):
            check.feed(recs[1])


class TestSpanDiff:
    def test_identical_and_matching_spans(self):
        a = "X met Alma Reyes at noon."
        b = "X met Bodo Lind at noon."
        assert vd.text_differs_outside_spans(a, [(6, 16)], b, [(6, 15)]) is None

    def test_insertion_at_a_span_edge(self):
        a = "Evidence: none."
        b = "Evidence: a signed letter. none."
        assert vd.text_differs_outside_spans(a, [(10, 10)], b, [(10, 27)]) is None

    def test_difference_outside_spans(self):
        a = "X met Alma Reyes at noon."
        b = "Y met Bodo Lind at noon."
        hit = vd.text_differs_outside_spans(a, [(6, 16)], b, [(6, 15)])
        assert hit == ((0, 1), (0, 1))


class TestContentHash:
    def test_independent_of_key_order_task_order_and_ids(self, view):
        _, digest = vd.check_design(view, records())
        shuffled = []
        for r in reversed(records()):
            shuffled.append(
                vd.TaskRecord(
                    id="other-" + r.id,
                    data=dict(reversed(list(r.data.items()))),
                    variant=dict(reversed(list(r.variant.items()))),
                )
            )
        assert vd.check_design(view, shuffled)[1] == digest

    def test_changes_with_data_spec_and_key(self, view):
        _, digest = vd.check_design(view, records())
        recs = records()
        recs[0].data["facts"] += " "
        assert vd.check_design(view, recs)[1] != digest
        spec = copy.deepcopy(view.spec)
        spec["title"] = "Other"
        assert vd.check_design(vd.DesignView.build("swap", spec), records())[1] != digest
        assert vd.check_design(vd.DesignView.build("swap2", view.spec), records())[1] != digest

    def test_typed_levels(self):
        assert vd.cell_key({"a": 1}) == vd.cell_key({"a": 1.0})
        assert vd.cell_key({"a": 1}) != vd.cell_key({"a": True})
        assert vd.cell_key({"a": "1"}) != vd.cell_key({"a": 1})


class TestFlatRows:
    def test_json_column_becomes_meta_variant(self):
        variant = {"design": "swap", "unit": "c1", "factors": {"role": "claimant"}}
        row = {"facts": "f", FLAT_META_COLUMN: json.dumps(variant)}
        data, meta = lift_flat_meta(row)
        assert data == {"facts": "f"}
        assert meta == {"benger_variant": variant}

    def test_empty_cell_and_missing_column(self):
        assert lift_flat_meta({"facts": "f", FLAT_META_COLUMN: " "}) == ({"facts": "f"}, None)
        row = {"facts": "f"}
        assert lift_flat_meta(row) == (row, None)

    def test_invalid_json_is_refused(self):
        with pytest.raises(VariantDesignError) as exc:
            lift_flat_meta({FLAT_META_COLUMN: "{not json"})
        assert exc.value.status_code == 422


class TestErrorMapping:
    @pytest.mark.parametrize(
        "text, status, code",
        [
            (
                "variant_design_frozen: the variant design swap is frozen and takes no new tasks",
                409,
                "variant_design_frozen",
            ),
            (
                'duplicate key value violates unique constraint "uq_tasks_variant_cell"\n'
                "DETAIL:  Key (project_id, variant_design, variant_unit, variant_cell)=(p, swap, c1, {}) already exists.",
                409,
                "variant_cell_duplicate",
            ),
            (
                'insert or update on table "tasks" violates foreign key constraint '
                '"fk_tasks_variant_design"',
                422,
                "variant_design_unknown",
            ),
            (
                'update or delete on table "variant_designs" violates foreign key constraint '
                '"fk_tasks_variant_design" on table "tasks"',
                409,
                "variant_design_in_use",
            ),
        ],
    )
    def test_database_guard_errors(self, text, status, code):
        mapped = error_from_db(Exception(text))
        assert (mapped.status_code, mapped.code) == (status, code)

    def test_other_errors_pass(self):
        assert error_from_db(Exception('violates unique constraint "uq_other"')) is None
