"""Method groups and research data (``services/shared/evaluation_methods.py``)."""

import pytest

from evaluation_methods import build_method_selection, project_configs, teacher_current_rows

pytestmark = pytest.mark.unit

A = {"id": "judge-a", "metric": "llm_judge_custom", "display_name": "Score (model A)"}
B = {"id": "judge-b", "metric": "llm_judge_custom", "display_name": "Score (model B)"}
C = {"id": "bleu-1", "metric": "bleu", "display_name": "BLEU"}


def test_without_groups_every_config_is_official():
    sel = build_method_selection([A, B, C])
    assert sel.groups == {}
    assert all(sel.is_official(c["id"]) for c in (A, B, C))
    assert sel.default_research_config_ids() == set()
    assert sel.method_key("judge-a") == "judge-a"


def test_group_first_config_is_the_default_official():
    sel = build_method_selection(
        [A, B, C], {"groups": {"score": {"config_ids": ["judge-a", "judge-b"]}}}
    )
    assert sel.groups == {"score": ["judge-a", "judge-b"]}
    assert sel.is_official("judge-a") and not sel.is_official("judge-b")
    assert sel.is_official("bleu-1")
    assert sel.default_research_config_ids() == {"judge-b"}
    assert sel.method_key("judge-b") == "group:score"


def test_official_answer_and_label_reach_the_public_shape():
    sel = build_method_selection(
        [A, B],
        {
            "groups": {"score": {"config_ids": ["judge-a", "judge-b"], "label": "Score"}},
            "official": {"score": "judge-b"},
        },
    )
    assert sel.official_config("score") == "judge-b"
    public = sel.to_public({"judge-a": "Score (model A)", "judge-b": "Score (model B)"})
    assert public["groups"] == [
        {
            "key": "score",
            "method_key": "group:score",
            "label": "Score",
            "config_ids": ["judge-a", "judge-b"],
            "default_official_config_id": "judge-b",
        }
    ]
    assert public["research_config_ids"] == ["judge-a"]


def test_static_config_fields_do_not_group():
    sel = build_method_selection(
        [
            dict(A, method_group="score", method_official=True),
            dict(B, method_group="score"),
            dict(C, research_only=True),
        ]
    )
    assert sel.groups == {}
    assert sel.research_only == set()
    assert all(sel.is_official(c["id"]) for c in (A, B, C))


def test_research_only_answer():
    sel = build_method_selection([A, C], {"research_only": ["bleu-1"]})
    assert not sel.is_official("bleu-1")
    assert sel.default_research_config_ids() == {"bleu-1"}


def test_hook_answer_groups_and_per_user_official():
    answer = {
        "groups": {"score": {"config_ids": ["judge-b", "judge-a", "unknown"], "label": "Score"}},
        "official": {"score": "judge-b"},
        "official_by_user": {"u-free": {"score": "judge-a"}, "u-bad": {"score": "unknown"}},
        "research_only": ["bleu-1", "nope"],
    }
    sel = build_method_selection([A, B, C], answer)
    # Members keep the configs' own order; unknown ids are dropped.
    assert sel.groups == {"score": ["judge-a", "judge-b"]}
    assert sel.labels == {"score": "Score"}
    assert sel.is_official("judge-b") and not sel.is_official("judge-a")
    assert sel.is_official("judge-a", "u-free") and not sel.is_official("judge-b", "u-free")
    # An answer naming an unknown config falls back to the default.
    assert sel.is_official("judge-b", "u-bad")
    assert sel.research_only == {"bleu-1"}


def test_a_config_belongs_to_one_group_and_one_config_is_no_group():
    sel = build_method_selection(
        [A, B, C],
        {
            "groups": {
                "first": {"config_ids": ["judge-a", "judge-b"]},
                "second": {"config_ids": ["judge-b", "bleu-1"]},
            }
        },
    )
    # "second" keeps only bleu-1, which is no group.
    assert sel.groups == {"first": ["judge-a", "judge-b"]}
    assert sel.is_official("bleu-1")


def test_disabled_configs_and_junk_are_ignored():
    sel = build_method_selection(
        [A, dict(B, enabled=False), "junk", {"metric": "x"}],
        {"groups": {"g": {"config_ids": ["judge-a", "judge-b"]}}},
    )
    assert sel.config_ids == ["judge-a"]
    assert sel.groups == {}


def test_an_answer_that_is_not_a_dict_groups_nothing():
    sel = build_method_selection([A, B], "not a dict")
    assert sel.groups == {} and sel.research_only == set()


def test_project_configs():
    class P:
        evaluation_config = {"evaluation_configs": [A, dict(B, enabled=False)]}

    assert [c["id"] for c in project_configs(P())] == ["judge-a"]
    assert project_configs(object()) == []


# --------------------------------------------------------------------------- #
# teacher_current_rows: the score a teacher view shows per method and subject.
# --------------------------------------------------------------------------- #
D = {"id": "judge-d", "metric": "llm_judge_custom", "display_name": "Score (model D)"}
GROUPED = {"groups": {"score": {"config_ids": ["judge-a", "judge-b", "judge-d"]}}}


def _row(row_id, config_id, *, annotation="ann-1", generation=None, score=0.5):
    return {
        "id": row_id,
        "task_id": "task-1",
        "annotation_id": None if generation else annotation,
        "generation_id": generation,
        "evaluation_config_id": config_id,
        "field_name": f"{config_id}|human:loesung|task.musterloesung",
        "metrics": {"llm_judge_custom": score} if score is not None else {"error": "boom"},
    }


def test_teacher_rows_without_a_group_keep_every_config():
    sel = build_method_selection([A, B, C])
    rows = [_row("r-a", "judge-a"), _row("r-b", "judge-b"), _row("r-c", "bleu-1", score=None)]
    assert teacher_current_rows(sel, rows, {"ann-1": "u-1"}) == {
        "r-a": None, "r-b": None, "r-c": None,
    }


def test_teacher_rows_take_the_official_config_when_it_has_a_score():
    sel = build_method_selection([A, B, D, C], GROUPED)
    rows = [_row("r-a", "judge-a"), _row("r-b", "judge-b"), _row("r-c", "bleu-1")]
    assert teacher_current_rows(sel, rows, {"ann-1": "u-1"}) == {"r-a": None, "r-c": None}


def test_teacher_rows_fall_back_to_another_config_of_the_group():
    # The per-account answer makes judge-a official for u-1, but judge-a
    # graded only u-1's other answer (ann-2): judge-b stands in on ann-1.
    answer = dict(GROUPED, official_by_user={"u-1": {"score": "judge-a"}})
    sel = build_method_selection([A, B, D], answer)
    rows = [
        _row("r-b1", "judge-b", annotation="ann-1"),
        _row("r-a2", "judge-a", annotation="ann-2"),
        _row("r-b2", "judge-b", annotation="ann-2"),
    ]
    assert teacher_current_rows(sel, rows, {"ann-1": "u-1", "ann-2": "u-1"}) == {
        "r-b1": "judge-a",
        "r-a2": None,
    }


def test_teacher_rows_fall_back_in_group_order_and_over_a_failed_official():
    sel = build_method_selection([A, B, D], dict(GROUPED, official={"score": "judge-d"}))
    rows = [
        _row("r-d", "judge-d", score=None),  # the official grading failed
        _row("r-b", "judge-b"),
        _row("r-a", "judge-a"),
    ]
    # judge-a comes first in the group's config order.
    assert teacher_current_rows(sel, rows, {}) == {"r-a": "judge-d"}


def test_teacher_rows_keep_the_official_failure_when_no_config_has_a_score():
    sel = build_method_selection([A, B, D], GROUPED)
    rows = [_row("r-a", "judge-a", score=None), _row("r-b", "judge-b", score=None)]
    assert teacher_current_rows(sel, rows, {"ann-1": "u-1"}) == {"r-a": None}
    # No row of any config of the group: nothing to show.
    assert teacher_current_rows(sel, [], {}) == {}


def test_teacher_rows_never_take_a_research_only_config():
    answer = dict(GROUPED, research_only=["judge-b"])
    sel = build_method_selection([A, B, D], answer)
    rows = [_row("r-b", "judge-b"), _row("r-d", "judge-d")]
    assert teacher_current_rows(sel, rows, {}) == {"r-d": "judge-a"}


def test_teacher_rows_decide_per_subject_and_use_the_default_for_generations():
    answer = dict(GROUPED, official_by_user={"u-2": {"score": "judge-b"}})
    sel = build_method_selection([A, B, D], answer)
    rows = [
        _row("g-a", "judge-a", generation="gen-1"),
        _row("g-b", "judge-b", generation="gen-1"),
        _row("g2-b", "judge-b", generation="gen-2"),
        _row("u2-a", "judge-a", annotation="ann-2"),
        _row("u2-b", "judge-b", annotation="ann-2"),
    ]
    assert teacher_current_rows(sel, rows, {"ann-2": "u-2"}) == {
        "g-a": None,
        "g2-b": "judge-a",
        "u2-b": None,
    }


def test_teacher_rows_accept_a_custom_score_test():
    sel = build_method_selection([A, B, D], GROUPED)
    rows = [_row("r-a", "judge-a", score=0.0), _row("r-b", "judge-b", score=0.7)]
    shown = teacher_current_rows(
        sel, rows, {}, has_score=lambda r: (r["metrics"].get("llm_judge_custom") or 0) > 0
    )
    assert shown == {"r-b": "judge-a"}
