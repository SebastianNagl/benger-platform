"""Text-pattern codes: format, matching rules, task literals and hashes.

The reference fixture (``codes_reference.json``) holds invented answers and
an invented pattern set coded by hand; the set applied to the answers must
give exactly those codes. A second, deliberately plain reference coder
(``re.search`` and ``re.findall`` per pattern, the way analysis scripts code
answers) checks every static code of the same texts.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys

import pytest

workers_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

from analysis.text_patterns import (  # noqa: E402
    PatternSetError,
    TEXT_PATTERN_FORMAT_VERSION,
    compile_pattern_set,
    normalize_pattern_set,
    pattern_set_hash,
    validate_pattern_set,
)

HERE = os.path.dirname(os.path.abspath(__file__))


def _reference():
    with open(os.path.join(HERE, "codes_reference.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _same(actual, expected):
    if expected is None:
        return actual is None or (isinstance(actual, float) and math.isnan(actual))
    if isinstance(expected, str):
        return actual == expected
    return isinstance(actual, float) and actual == float(expected)


def _set(**codes):
    return {"name": "t", "version": "1", "codes": codes}


class TestReferenceCoding:
    def test_the_set_reproduces_the_hand_coding(self):
        ref = _reference()
        compiled = compile_pattern_set(ref["pattern_set"])
        mismatches = []
        for case in ref["cases"]:
            got = compiled.codes(case["text"], case["task_data"])
            assert set(got) == set(case["expected"])
            for code, expected in case["expected"].items():
                if not _same(got[code], expected):
                    mismatches.append((case["id"], code, got[code], expected))
        assert mismatches == []

    def test_static_codes_match_a_plain_reference_coder(self):
        ref = _reference()
        doc = ref["pattern_set"]
        compiled = compile_pattern_set(doc)
        for case in ref["cases"]:
            text = case["text"]
            if text is None:
                continue
            for cid, code in doc["codes"].items():
                patterns = code.get("patterns") or []
                if any("{{" in p for p in patterns) or code["mode"] == "first":
                    continue
                flags = re.I if "IGNORECASE" in code.get("flags", doc["flags"]) else 0
                if code["mode"] == "any":
                    plain = float(any(re.search(p, text, flags) for p in patterns))
                elif code["mode"] == "all":
                    plain = float(all(re.search(p, text, flags) for p in patterns))
                else:
                    plain = float(sum(len(re.findall(p, text, flags)) for p in patterns))
                assert compiled.code(cid, text, case["task_data"]) == plain, (case["id"], cid)

    def test_frame_measures_carry_the_reference_codes(self):
        """The same set as an analysis measure (by pattern_sets id and
        inline), on the full answer, gives the hand codes per row."""
        from analysis.frame import build_frame
        from analysis.observations import observations_from_records
        from analysis.spec import normalize_spec

        ref = _reference()
        records = []
        for i, case in enumerate(ref["cases"]):
            records.append({
                "generation_id": f"g{i}", "task_id": f"t{i}", "model_id": "m",
                "design": "d", "unit": f"u{i}", "factors": {},
                "fields": {}, "task_data": case["task_data"], "answer_text": case["text"],
            })
        spec = normalize_spec({
            "spec_version": 1, "name": "codes", "inputs": {"designs": ["d"]},
            "pattern_sets": {"signals": ref["pattern_set"]},
            "measures": {
                "n_norms": {"kind": "text_pattern", "set": "signals", "code": "n_norms"},
                "verdict": {"kind": "text_pattern", "set": ref["pattern_set"], "code": "verdict"},
                "own_ref": {"kind": "text_pattern", "set": "signals", "code": "own_ref", "input": "answer"},
                "own_ref_pct": {"kind": "expression", "expr": "100 * own_ref"},
            },
            "estimands": [{"id": "rate", "estimator": "mean_rate", "outcome": "own_ref_pct"}],
        })
        built = build_frame(observations_from_records(records), spec)
        by_unit = {row.unit: row for row in built.frame.itertuples()}
        for i, case in enumerate(ref["cases"]):
            row = by_unit[f"u{i}"]
            assert _same(row.n_norms, case["expected"]["n_norms"]), case["id"]
            assert _same(row.verdict, case["expected"]["verdict"]), case["id"]
            assert _same(row.own_ref, case["expected"]["own_ref"]), case["id"]
            expected_pct = case["expected"]["own_ref"]
            assert _same(row.own_ref_pct, None if expected_pct is None else 100 * expected_pct)
        assert str(built.frame["verdict"].dtype) == "object"
        records_by_measure = {c["measure"]: c for c in built.codes}
        assert records_by_measure["n_norms"]["hash"] != records_by_measure["own_ref"]["hash"]
        assert records_by_measure["n_norms"]["set_hash"] == records_by_measure["verdict"]["set_hash"]
        assert records_by_measure["n_norms"]["ref"] == "legal_signals@1:n_norms"
        assert records_by_measure["own_ref"]["missing"] == 2  # no answer, no case reference


class TestMatching:
    def test_modes(self):
        s = compile_pattern_set(_set(
            a={"mode": "any", "patterns": ["x", "y"]},
            b={"mode": "all", "patterns": ["x", "y"]},
            c={"mode": "count", "patterns": ["x", "xx"]},
        ))
        assert s.codes("x xx") == {"a": 1.0, "b": 0.0, "c": 4.0}  # x, x, x then xx once
        assert s.codes("y x") == {"a": 1.0, "b": 1.0, "c": 1.0}

    def test_flags_and_code_override(self):
        s = compile_pattern_set({
            "name": "t", "version": "1", "flags": ["IGNORECASE"],
            "codes": {
                "ci": {"mode": "any", "patterns": ["abc"]},
                "cs": {"mode": "any", "patterns": ["abc"], "flags": []},
                "dot": {"mode": "any", "patterns": ["a.c"], "flags": ["DOTALL"]},
            },
        })
        assert s.codes("ABC") == {"ci": 1.0, "cs": 0.0, "dot": 0.0}
        assert s.codes("a\nc")["dot"] == 1.0

    def test_first_takes_rules_in_order_and_the_default(self):
        s = compile_pattern_set(_set(side={"mode": "first", "rules": [
            {"value": "P", "patterns": ["claimant"]},
            {"value": "D", "patterns": ["respondent"]},
        ]}))
        assert s.code("side", "the respondent, then the claimant") == "P"
        assert s.code("side", "the respondent") == "D"
        assert s.code("side", "nobody") is None
        assert s.evaluate("side", "nobody") == (None, "coded")
        assert s.evaluate("side", None) == (None, "no_text")

    def test_literals_escape_and_alternate(self):
        s = compile_pattern_set(_set(
            lit={"mode": "count", "patterns": ["{{task.ref}}"]},
            sp={"mode": "any", "patterns": ["{{task.ref|spaces}}"]},
            ws={"mode": "any", "patterns": ["{{task.ref|whitespace}}"]},
            idx={"mode": "any", "patterns": ["{{task.refs.1}}"]},
        ))
        data = {"ref": "a.b (1)", "refs": ["zz", "q+"]}
        assert s.code("lit", "a.b (1) and axb (1)", data) == 1.0  # the dot is literal
        assert s.code("sp", "a . b(1)", data) == 1.0
        assert s.code("sp", "a.\nb(1)", data) == 0.0  # only spaces are skipped
        assert s.code("ws", "a.\nb\t(1)", data) == 1.0
        assert s.code("idx", "q+", data) == 1.0 and s.code("idx", "qq", data) == 0.0
        assert s.evaluate("lit", "x", {"ref": ""}) [1] == "unresolved"
        assert s.evaluate("lit", "x", {"ref": [None, {}]})[1] == "unresolved"
        assert s.code("lit", "7 and 7", {"ref": 7}) == 2.0
        assert s.code("lit", "x", {"ref": ["y", "x"]}) == 1.0

    def test_unicode_normalization(self):
        decomposed = "Müller"
        plain = compile_pattern_set(_set(n={"mode": "any", "patterns": ["Müller"]}))
        nfc = compile_pattern_set({**_set(n={"mode": "any", "patterns": ["Müller"]}), "normalize": "NFC"})
        assert plain.code("n", decomposed) == 0.0
        assert nfc.code("n", decomposed) == 1.0

    def test_missing_text_is_missing_and_empty_text_is_coded(self):
        s = compile_pattern_set(_set(a={"mode": "any", "patterns": ["x"]}))
        assert math.isnan(s.code("a", None)) and s.code("a", "") == 0.0
        assert math.isnan(s.code("a", 5))


class TestValidationAndHash:
    @pytest.mark.parametrize(
        "doc, needle",
        [
            ({"name": "t", "version": "1", "codes": {}}, "should be non-empty"),
            (_set(a={"mode": "any", "patterns": ["("]}), "does not compile"),
            (_set(a={"mode": "any", "patterns": ["{{case.x}}"]}), "starts a placeholder"),
            (_set(a={"mode": "any", "patterns": ["{{task.x|upper}}"]}), "unknown literal transform"),
            (_set(a={"mode": "first", "rules": [{"value": "P", "patterns": ["x"]}, {"value": "P", "patterns": ["y"]}]}), "repeat"),
            (_set(a={"mode": "sometimes", "patterns": ["x"]}), "/codes/a"),
            ({"name": "bad name", "version": "1", "codes": {"a": {"mode": "any", "patterns": ["x"]}}}, "/name"),
        ],
    )
    def test_invalid_sets_are_refused(self, doc, needle):
        with pytest.raises(PatternSetError) as err:
            validate_pattern_set(doc)
        assert any(needle in e for e in err.value.errors), err.value.errors

    def test_escaped_braces_are_plain_regex(self):
        s = compile_pattern_set(_set(a={"mode": "any", "patterns": [r"\{\{x\}\}"]}))
        assert s.code("a", "{{x}}") == 1.0

    def test_hash_covers_matching_content_only(self):
        base = _set(a={"mode": "any", "patterns": ["x"]})
        h = pattern_set_hash(normalize_pattern_set(base))
        assert len(h) == 64
        described = {**base, "description": "words", "codes": {"a": {**base["codes"]["a"], "description": "more"}}}
        assert pattern_set_hash(normalize_pattern_set(described)) == h
        assert pattern_set_hash(normalize_pattern_set({**base, "flags": []})) == h
        for changed in (
            {**base, "version": "2"},
            {**base, "flags": ["IGNORECASE"]},
            {**base, "normalize": "NFC"},
            _set(a={"mode": "any", "patterns": ["y"]}),
            _set(a={"mode": "count", "patterns": ["x"]}),
        ):
            assert pattern_set_hash(normalize_pattern_set(changed)) != h
        flags_ab = normalize_pattern_set({**base, "flags": ["MULTILINE", "IGNORECASE"]})
        flags_ba = normalize_pattern_set({**base, "flags": ["IGNORECASE", "MULTILINE"]})
        assert pattern_set_hash(flags_ab) == pattern_set_hash(flags_ba)
        assert TEXT_PATTERN_FORMAT_VERSION == 1

    def test_describe_names_the_version(self):
        s = compile_pattern_set(_set(a={"mode": "any", "patterns": ["x"]}))
        assert s.describe() == {"name": "t", "version": "1", "ref": "t@1", "hash": s.hash}
