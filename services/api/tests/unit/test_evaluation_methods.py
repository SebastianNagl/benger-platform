"""Method groups and research data (``services/shared/evaluation_methods.py``)."""

import pytest

from evaluation_methods import build_method_selection, project_configs

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
