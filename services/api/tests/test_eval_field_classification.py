"""Pure-unit tests for `services/shared/eval_field_classification.py`.

The classifier is the single source of truth for whether a prediction-field
on an eval config refers to the human/annotation side or the LLM/generation
side. The worker (``services/workers/tasks.py``) and the cost endpoint
(``services/api/routers/cost_estimate.py``) both delegate here. These tests
lock the contract so a future change in either consumer can't drift away
from the agreed behavior — including the ``llm_judge_falloesung``
backward-compat rule that motivated the refactor.

No DB touched. Module is on sys.path because services/shared/ is mounted
into the api container's PYTHONPATH (same as seeds/llm_models_loader)."""

from __future__ import annotations

import pytest

from eval_field_classification import (
    classify_pred_fields,
    register_classifier_rule,
)


# ---------------------------------------------------------------------------
# Default classifier (no metric / no rule)
# ---------------------------------------------------------------------------


def test_empty_field_list_returns_two_empty_lists():
    assert classify_pred_fields("any_metric", []) == ([], [])


def test_default_split_only_explicit_human_prefix_counts():
    human, llm = classify_pred_fields("some_metric", ["human:angabe", "loesung", "model:foo"])
    assert human == ["human:angabe"]
    assert llm == ["loesung", "model:foo"]


def test_all_human_wildcard_counts_as_human():
    human, llm = classify_pred_fields("some_metric", ["__all_human__", "loesung"])
    assert human == ["__all_human__"]
    assert llm == ["loesung"]


def test_no_metric_no_rule_unprefixed_stays_llm():
    """Without a registered rule, unprefixed fields default to LLM. This is
    the safety net that ensures unknown metrics don't accidentally get the
    falloesung-style backward-compat behavior."""
    human, llm = classify_pred_fields(None, ["loesung", "answer"])
    assert human == []
    assert llm == ["loesung", "answer"]


# ---------------------------------------------------------------------------
# llm_judge_falloesung backward-compat rule (built-in)
# ---------------------------------------------------------------------------


def test_falloesung_unprefixed_fields_routed_to_human_side():
    human, llm = classify_pred_fields("llm_judge_falloesung", ["loesung", "argumentation"])
    assert human == ["loesung", "argumentation"]
    assert llm == []


def test_falloesung_does_not_re_classify_when_explicit_human_present():
    """The backward-compat path only fires when the default split returned
    zero explicit human fields — once any ``human:`` prefix appears, we
    trust the author's intent and don't second-guess the rest."""
    human, llm = classify_pred_fields(
        "llm_judge_falloesung", ["human:angabe", "loesung", "extra"]
    )
    assert human == ["human:angabe"]
    assert llm == ["loesung", "extra"]


def test_falloesung_excludes_model_prefix_from_compat():
    human, llm = classify_pred_fields(
        "llm_judge_falloesung", ["loesung", "model:gpt5"]
    )
    assert human == ["loesung"]
    assert llm == ["model:gpt5"]


def test_falloesung_excludes_all_model_wildcard_from_compat():
    human, llm = classify_pred_fields("llm_judge_falloesung", ["loesung", "__all_model__"])
    assert human == ["loesung"]
    assert llm == ["__all_model__"]


# ---------------------------------------------------------------------------
# Extension API
# ---------------------------------------------------------------------------


def test_register_custom_rule_is_consulted(monkeypatch):
    """Newly-registered metric rules should be picked up the next time
    classify_pred_fields runs against that metric. This is what extended
    will use when shipping new judge metrics with their own conventions."""

    def _every_field_is_human(fields):
        return list(fields), []

    register_classifier_rule("test_custom_metric", _every_field_is_human)
    try:
        human, llm = classify_pred_fields("test_custom_metric", ["a", "b"])
        assert human == ["a", "b"]
        assert llm == []
    finally:
        # Clean up so other tests aren't polluted.
        from eval_field_classification import _RULES
        _RULES.pop("test_custom_metric", None)


def test_register_is_idempotent_replaces_rule():
    """Re-registering the same metric replaces the prior rule — keeps
    the API reload-safe in dev (extended's __init__.py runs once per
    container start, but a hot-reload could re-import it)."""
    from eval_field_classification import _RULES

    register_classifier_rule("idempotency_test", lambda fields: ([], list(fields)))
    register_classifier_rule("idempotency_test", lambda fields: (list(fields), []))
    try:
        human, llm = classify_pred_fields("idempotency_test", ["x"])
        assert human == ["x"]
        assert llm == []
    finally:
        _RULES.pop("idempotency_test", None)


def test_unregistered_metric_falls_through_to_default():
    human, llm = classify_pred_fields("unknown_metric_no_rule", ["unprefixed"])
    assert human == []
    assert llm == ["unprefixed"]


# ---------------------------------------------------------------------------
# Partition invariant
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "metric,fields",
    [
        ("llm_judge_falloesung", ["a", "b", "human:c", "model:d"]),
        ("other_metric", ["a", "b", "human:c", "model:d"]),
        (None, ["a", "human:b"]),
        ("llm_judge_falloesung", []),
    ],
)
def test_human_and_llm_lists_partition_input(metric, fields):
    """Every input field must appear in exactly one output list — never
    both, never neither. Guards against off-by-one bugs in future
    rules."""
    human, llm = classify_pred_fields(metric, fields)
    assert sorted(human + llm) == sorted(fields)
    assert set(human).isdisjoint(set(llm))
