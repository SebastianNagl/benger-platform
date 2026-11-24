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


def test_static_group_first_config_is_the_default_official():
    sel = build_method_selection(
        [dict(A, method_group="score"), dict(B, method_group="score"), C]
    )
    assert sel.groups == {"score": ["judge-a", "judge-b"]}
    assert sel.is_official("judge-a") and not sel.is_official("judge-b")
    assert sel.is_official("bleu-1")
    assert sel.default_research_config_ids() == {"judge-b"}
    assert sel.method_key("judge-b") == "group:score"


def test_static_official_flag_and_label():
    sel = build_method_selection(
        [
            dict(A, method_group="score", method_label="Score"),
            dict(B, method_group="score", method_official=True),
        ]
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


def test_research_only_flag():
    sel = build_method_selection([A, dict(C, research_only=True)])
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


def test_hook_group_takes_configs_over_from_static_groups():
    sel = build_method_selection(
        [dict(A, method_group="old"), dict(B, method_group="old"), C],
        {"groups": {"new": {"config_ids": ["judge-b", "bleu-1"]}}},
    )
    # "old" keeps one config, which is no group any more.
    assert sel.groups == {"new": ["judge-b", "bleu-1"]}
    assert sel.is_official("judge-a")


def test_disabled_configs_and_junk_are_ignored():
    sel = build_method_selection(
        [dict(A, method_group="g"), dict(B, method_group="g", enabled=False), "junk", {"metric": "x"}],
        "not a dict",
    )
    assert sel.config_ids == ["judge-a"]
    assert sel.groups == {}


def test_project_configs():
    class P:
        evaluation_config = {"evaluation_configs": [A, dict(B, enabled=False)]}

    assert [c["id"] for c in project_configs(P())] == ["judge-a"]
    assert project_configs(object()) == []
