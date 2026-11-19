"""Coding validation: seeded samples, code identity and agreement.

The toy coding project below has ten answers, an automatic code and one or
two human coders; every number is computed by hand in the comments:

    item       1  2  3  4  5  6  7  8  9  10
    automatic  P  P  P  D  D  D  N  N  P  D
    coder A    P  P  D  D  D  N  N  N  P  P
    coder B    P  P  D  D  N  N  N  N  P  D

Automatic against coder A: 7 of 10 agree (po = 0.7). Marginals automatic
P 4, D 4, N 2; coder A P 4, D 3, N 3; pe = (16 + 12 + 6) / 100 = 0.34;
kappa = (0.7 - 0.34) / 0.66 = 6/11.
"""

from __future__ import annotations

import hashlib
import os
import sys

import pytest

workers_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

from analysis.codes import code_identity, confirmatory_code_measures  # noqa: E402
from analysis.coding import (  # noqa: E402
    MISSING_LABEL,
    CodingError,
    code_label,
    draw_sample,
    normalize_validation_code,
    sample_hash,
    sample_rank,
    validation_metrics,
)
from analysis.spec import normalize_spec  # noqa: E402

AUTO = list("PPPDDDNNPD")
CODER_A = list("PPDDDNNNPP")
CODER_B = list("PPDDNNNNPD")


def _items(*coders, auto=AUTO):
    items = []
    for i in range(len(auto)):
        human = {name: codes[i] for name, codes in coders}
        items.append({"task_id": f"t{i + 1}", "automatic": auto[i], "human": human})
    return items


class TestAgreement:
    def test_one_coder_kappa_is_six_elevenths(self):
        m = validation_metrics(_items(("a", CODER_A)))
        main = m["automatic_vs_reference"]
        assert m["compared"] == 10 and m["ties"] == 0 and m["categories"] == ["D", "N", "P"]
        assert main["observed_agreement"] == pytest.approx(0.7, abs=1e-15)
        assert main["expected_agreement"] == pytest.approx(0.34, abs=1e-15)
        assert main["kappa"] == pytest.approx(6 / 11, abs=1e-15)
        assert m["automatic_vs_coders"]["a"]["kappa"] == pytest.approx(6 / 11, abs=1e-15)
        assert main["confusion"] == {
            "P": {"P": 3, "D": 1, "N": 0},
            "D": {"P": 1, "D": 2, "N": 0},
            "N": {"P": 0, "D": 1, "N": 2},
        }
        per = main["per_category"]
        # P: 3 of 4 predicted are right, 3 of 4 reference P found
        assert (per["P"]["precision"], per["P"]["recall"], per["P"]["f1"]) == (0.75, 0.75, 0.75)
        # D: 2 of 4 predicted, 2 of 3 found; F1 = 2 * 1/2 * 2/3 / (7/6) = 4/7
        assert per["D"]["precision"] == 0.5
        assert per["D"]["recall"] == pytest.approx(2 / 3, abs=1e-15)
        assert per["D"]["f1"] == pytest.approx(4 / 7, abs=1e-15)
        # N: 2 of 2 predicted, 2 of 3 found; F1 = 0.8
        assert per["N"]["precision"] == 1.0 and per["N"]["f1"] == pytest.approx(0.8, abs=1e-15)
        assert m["between_coders"] is None

    def test_two_coders_use_the_majority_and_drop_ties(self):
        """Items 5 and 10 tie (A and B differ), so 8 items compare: 6 agree,
        po = 0.75; reference P 3, D 2, N 3; automatic P 4, D 2, N 2;
        pe = (12 + 4 + 6) / 64; kappa = (13/32) / (21/32) = 13/21. Between
        the coders: 8 of 10 agree, pe = (12 + 9 + 12) / 100, Cohen's kappa
        = 0.47 / 0.67 = 47/67; Fleiss' kappa with pooled marginals P .35,
        D .3, N .35: (0.8 - 0.335) / 0.665 = 93/133."""
        m = validation_metrics(_items(("a", CODER_A), ("b", CODER_B)))
        main = m["automatic_vs_reference"]
        assert m["ties"] == 2 and m["compared"] == 8
        assert main["observed_agreement"] == pytest.approx(0.75, abs=1e-15)
        assert main["kappa"] == pytest.approx(13 / 21, abs=1e-15)
        between = m["between_coders"]
        assert between["coders"] == 2 and between["items"] == 10
        assert between["pairwise"]["a__b"]["kappa"] == pytest.approx(47 / 67, abs=1e-15)
        assert between["fleiss_kappa"] == pytest.approx(93 / 133, abs=1e-12)
        assert between["percent_agreement"] == 0.8
        assert m["automatic_vs_coders"]["a"]["kappa"] == pytest.approx(6 / 11, abs=1e-15)

    def test_missing_automatic_codes(self):
        items = _items(("a", CODER_A)) + [{"task_id": "t11", "automatic": None, "human": {"a": "P"}}]
        counted = validation_metrics(items)
        assert counted["missing_automatic"] == 1 and counted["compared"] == 11
        assert MISSING_LABEL in counted["categories"]
        assert counted["automatic_vs_reference"]["observed_agreement"] == pytest.approx(7 / 11, abs=1e-15)
        excluded = validation_metrics(items, missing="exclude")
        assert excluded["compared"] == 10
        assert excluded["automatic_vs_reference"]["kappa"] == pytest.approx(6 / 11, abs=1e-15)
        with pytest.raises(CodingError):
            validation_metrics(items, missing="zero")

    def test_items_without_human_codes_are_counted_not_compared(self):
        items = _items(("a", CODER_A)) + [{"task_id": "t12", "automatic": "P", "human": {}}]
        m = validation_metrics(items)
        assert m["no_human_code"] == 1 and m["compared"] == 10

    def test_code_labels(self):
        assert code_label(1.0) == "1" and code_label(True) == "true" and code_label(["P"]) == "P"
        assert code_label(["P", "D"]) is None and code_label(float("nan")) is None and code_label("") is None
        assert code_label("plaintiff", {"plaintiff": "P"}) == "P"


class TestSampling:
    def test_rank_is_the_seeded_hash(self):
        assert sample_rank(7, "g1") == hashlib.sha256(b"7:g1").hexdigest()

    def test_the_same_seed_draws_the_same_answers(self):
        ids = [f"g{i}" for i in range(50)]
        a = draw_sample(ids, seed=11, size=10)
        assert a == draw_sample(list(reversed(ids)), seed=11, size=10)
        assert [g for g, _ in a] != [g for g, _ in draw_sample(ids, seed=12, size=10)]
        more = draw_sample(ids + [f"h{i}" for i in range(50)], seed=11)
        kept = [g for g, _ in more if g in {x for x, _ in a}]
        assert kept == [g for g, _ in a]
        assert len(draw_sample(ids, seed=1)) == 50
        assert sample_hash(["b", "a"]) == sample_hash(["a", "b"])


PATTERN_SET = {"name": "s", "version": "1", "codes": {"p": {"mode": "any", "patterns": ["claimant"]}}}


class TestIdentity:
    def test_a_validation_code_has_the_identity_of_its_measure(self):
        code = normalize_validation_code(
            {"kind": "text_pattern", "set": PATTERN_SET, "code": "p"},
            coding_project_id="cp", answer_source="answer",
        )
        spec = normalize_spec({
            "spec_version": 1, "name": "x", "inputs": {"designs": ["d"]},
            "pattern_sets": {"s": PATTERN_SET},
            "measures": {
                "by_ref": {"kind": "text_pattern", "set": "s", "code": "p"},
                "on_field": {"kind": "text_pattern", "set": "s", "code": "p", "input": {"field": "begr"}},
                "judge": {"kind": "judge_code", "coding_project": "cp", "field": "side", "system": "judge-m"},
            },
            "estimands": [{"id": "e", "estimator": "mean_rate", "outcome": "by_ref"}],
        })
        sets = spec["pattern_sets"]
        assert code_identity(code)["hash"] == code_identity(spec["measures"]["by_ref"], pattern_sets=sets)["hash"]
        assert code_identity(code)["hash"] != code_identity(spec["measures"]["on_field"], pattern_sets=sets)["hash"]
        judge = normalize_validation_code({"kind": "judge_code", "system": "judge-m"}, coding_project_id="cp",
                                          answer_source="answer")
        judge["field"] = "side"
        assert code_identity(judge)["hash"] == code_identity(spec["measures"]["judge"])["hash"]
        other = normalize_validation_code({"kind": "judge_code", "system": "judge-m", "run_index": 1},
                                          coding_project_id="cp", answer_source="answer")
        other["field"] = "side"
        assert code_identity(other)["hash"] != code_identity(judge)["hash"]

    @pytest.mark.parametrize(
        "code, needle",
        [
            ("x", "must be an object"),
            ({"kind": "field"}, "/code/kind"),
            ({"kind": "text_pattern", "set": "s", "code": "p"}, "give the pattern set itself"),
            ({"kind": "text_pattern", "set": PATTERN_SET, "code": "q"}, "no code 'q'"),
            ({"kind": "coder", "coder": "c"}, "/code/output"),
            ({"kind": "judge_code"}, "/code/system"),
            ({"kind": "coder", "coder": "c", "output": "o", "input": "answer"}, "unknown key"),
        ],
    )
    def test_invalid_validation_codes(self, code, needle):
        with pytest.raises(CodingError) as err:
            normalize_validation_code(code, coding_project_id="cp", answer_source="answer")
        assert any(needle in e for e in err.value.errors), err.value.errors


class TestConfirmatory:
    def _spec(self, families, **est):
        return normalize_spec({
            "spec_version": 1, "name": "x", "inputs": {"designs": ["d"]},
            "pattern_sets": {"s": PATTERN_SET},
            "measures": {
                "code": {"kind": "text_pattern", "set": "s", "code": "p"},
                "pct": {"kind": "expression", "expr": "100 * code"},
                "other": {"kind": "text_pattern", "set": "s", "code": "p", "input": {"field": "f"}},
                "y": {"kind": "field", "field": "y"},
            },
            "estimands": [
                {"id": "main", "estimator": "mean_rate", "outcome": "pct", **est},
                {"id": "side", "estimator": "mean_rate", "outcome": "other"},
            ],
            "families": families,
        })

    def test_codes_read_by_confirmatory_estimands(self):
        spec = self._spec([{"id": "f", "method": "holm", "members": [{"estimand": "main"}]}])
        assert confirmatory_code_measures(spec) == {"code": ["main"]}

    def test_exploratory_families_and_free_estimands_need_nothing(self):
        assert confirmatory_code_measures(self._spec([
            {"id": "f", "method": "holm", "exploratory": True, "members": [{"estimand": "main"}]}
        ])) == {}
        assert confirmatory_code_measures(self._spec([])) == {}

    def test_subsets_and_terms_count(self):
        spec = self._spec(
            [{"id": "f", "method": "holm", "members": [{"estimand": "main"}]}],
            subset="other == 1",
        )
        assert confirmatory_code_measures(spec) == {"code": ["main"], "other": ["main"]}
