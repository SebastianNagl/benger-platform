"""
Mutation-kill tests for the evaluation-config resolution layer
(services/evaluation/config.py).

This module decides WHICH metrics run for WHICH answer type and how a
project's metric-config is validated / normalized / defaulted. A bug here
silently computes the wrong metric set for a benchmark, drops a metric, or
inverts the project-config-vs-defaults precedence. None of those surface as
crashes, so they are exactly the class of fault a mutation test must pin.

Every assertion below is an EXACT set / value, hand-reasoned from the source
(the literal ANSWER_TYPE_TO_METRICS table, the {**defaults, **user} merge in
normalize_metric_selection, and the get_metric_defaults dict). A flipped
mapping, a dropped/added metric, an inverted precedence, or a broken
default therefore fails a specific test rather than passing silently.

Pure functions are called directly — no DB is needed for any of this layer.
The only stateful seam is register_extended_metrics(), which mutates a
module-global; those tests save/restore the global so they never leak into
sibling tests.
"""

import copy

import pytest

# The public symbols are imported via the compatibility shim
# (evaluation_config -> services.evaluation.config), matching the existing
# tests/unit/test_evaluation_config.py import style. The canonical module
# (services.evaluation.config) is imported separately as `cfg` so the isolation
# fixture can reach the real `_extended_metrics` module-global that
# register_extended_metrics() mutates — `from x import *` does NOT re-export
# underscore-prefixed names, so the shim has no `_extended_metrics` attribute.
import services.evaluation.config as cfg
from services.evaluation.config import (
    ANSWER_TYPE_TO_METRICS,
    AnswerType,
    get_metric_defaults,
    get_metric_parameters,
    get_metrics_for_answer_type,
    get_selected_metrics_for_field,
    normalize_metric_selection,
    normalize_selected_methods,
    register_extended_metrics,
    validate_metric_selection,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_extended_metrics():
    """Save/restore the module-global _extended_metrics registry.

    register_extended_metrics() mutates a process-global. Without this guard a
    registration in one test would bleed into get_metrics_for_answer_type() for
    every later test (and every other test file in the same worker), so we deep
    -copy it out and restore it afterward.
    """
    saved = copy.deepcopy(cfg._extended_metrics)
    cfg._extended_metrics.clear()
    cfg._extended_metrics.update(saved)
    try:
        yield cfg._extended_metrics
    finally:
        cfg._extended_metrics.clear()
        cfg._extended_metrics.update(saved)


# ---------------------------------------------------------------------------
# 1. ANSWER-TYPE -> METRICS: the exact resolved set per answer type.
#    A wrong answer-type->metric mapping is the headline failure: the wrong
#    metrics get computed for a benchmark. These pin every entry of the
#    ANSWER_TYPE_TO_METRICS table down to the exact membership (order-
#    independent set equality + length, so neither a drop nor a dup hides).
# ---------------------------------------------------------------------------

# Hand-transcribed from the literal table in config.py (lines 39-186).
EXPECTED_METRICS = {
    AnswerType.BINARY: {
        "exact_match",
        "accuracy",
        "precision",
        "recall",
        "f1",
        "cohen_kappa",
        "llm_judge_classic",
        "llm_judge_custom",
    },
    AnswerType.SINGLE_CHOICE: {
        "exact_match",
        "accuracy",
        "precision",
        "recall",
        "f1",
        "confusion_matrix",
        "cohen_kappa",
        "llm_judge_classic",
        "llm_judge_custom",
    },
    AnswerType.MULTIPLE_CHOICE: {
        "jaccard",
        "hamming_loss",
        "subset_accuracy",
        "precision",
        "recall",
        "f1",
        "llm_judge_classic",
        "llm_judge_custom",
    },
    AnswerType.NUMERIC: {
        "mae",
        "rmse",
        "mape",
        "r2",
        "correlation",
        "llm_judge_classic",
        "llm_judge_custom",
    },
    AnswerType.RATING: {
        "mae",
        "rmse",
        "correlation",
        "cohen_kappa",
        "weighted_kappa",
        "llm_judge_classic",
        "llm_judge_custom",
    },
    AnswerType.RANKING: {
        "spearman_correlation",
        "kendall_tau",
        "ndcg",
        "llm_judge_classic",
        "llm_judge_custom",
    },
    AnswerType.SHORT_TEXT: {
        "exact_match",
        "bleu",
        "rouge",
        "edit_distance",
        "chrf",
        "moverscore",
        "semantic_similarity",
        "llm_judge_classic",
        "llm_judge_custom",
    },
    AnswerType.LONG_TEXT: {
        "bleu",
        "rouge",
        "meteor",
        "chrf",
        "bertscore",
        "moverscore",
        "factcc",
        "qags",
        "semantic_similarity",
        "coherence",
        "llm_judge_classic",
        "llm_judge_custom",
    },
    AnswerType.STRUCTURED_TEXT: {
        "json_accuracy",
        "schema_validation",
        "field_accuracy",
        "semantic_similarity",
        "llm_judge_classic",
        "llm_judge_custom",
    },
    AnswerType.SPAN_SELECTION: {
        "span_exact_match",
        "iou",
        "partial_match",
        "boundary_accuracy",
        "llm_judge_classic",
        "llm_judge_custom",
    },
    AnswerType.TAXONOMY: {
        "hierarchical_f1",
        "path_accuracy",
        "lca_accuracy",
        "llm_judge_classic",
        "llm_judge_custom",
    },
    AnswerType.CUSTOM: {
        "exact_match",
        "accuracy",
        "precision",
        "recall",
        "f1",
        "cohen_kappa",
        "jaccard",
        "hamming_loss",
        "subset_accuracy",
        "confusion_matrix",
        "mae",
        "rmse",
        "mape",
        "r2",
        "correlation",
        "weighted_kappa",
        "spearman_correlation",
        "kendall_tau",
        "ndcg",
        "bleu",
        "rouge",
        "meteor",
        "chrf",
        "bertscore",
        "moverscore",
        "factcc",
        "qags",
        "semantic_similarity",
        "edit_distance",
        "coherence",
        "json_accuracy",
        "schema_validation",
        "token_f1",
        "span_exact_match",
        "iou",
        "map",
        "hierarchical_f1",
        "llm_judge_classic",
        "llm_judge_custom",
    },
}


@pytest.mark.parametrize("answer_type", list(AnswerType))
def test_every_answer_type_resolves_exact_metric_set(answer_type):
    """get_metrics_for_answer_type returns EXACTLY the documented set.

    Kills: any mutation that drops, adds, or swaps a metric for an answer type
    (e.g. moving "f1" out of BINARY, or "confusion_matrix" leaking into
    MULTIPLE_CHOICE). Set-equality + length catches both removals and dups.
    """
    resolved = get_metrics_for_answer_type(answer_type)
    expected = EXPECTED_METRICS[answer_type]

    assert set(resolved) == expected, (
        f"{answer_type.value}: metric set mismatch.\n"
        f"  missing: {expected - set(resolved)}\n"
        f"  unexpected: {set(resolved) - expected}"
    )
    # No accidental duplicates from a base+extended concat bug.
    assert len(resolved) == len(set(resolved)), (
        f"{answer_type.value}: duplicate metrics: {resolved}"
    )
    # With no extended metrics registered, the resolved list IS the base table.
    assert list(resolved) == ANSWER_TYPE_TO_METRICS[answer_type]


def test_answer_type_table_is_complete():
    """Every AnswerType enum member has a metrics entry (no silent gap)."""
    for at in AnswerType:
        assert at in ANSWER_TYPE_TO_METRICS, f"{at.value} missing from table"
        assert ANSWER_TYPE_TO_METRICS[at], f"{at.value} has empty metric list"


def test_llm_judges_present_for_every_answer_type():
    """Both LLM judges must be offered for every answer type (the universal
    fallback evaluators). Kills a mutation dropping a judge from any row."""
    for at in AnswerType:
        metrics = set(get_metrics_for_answer_type(at))
        assert "llm_judge_classic" in metrics, at.value
        assert "llm_judge_custom" in metrics, at.value


def test_classification_vs_multilabel_metric_separation():
    """SINGLE_CHOICE is confusion-matrix classification; MULTIPLE_CHOICE is
    multi-label (jaccard/hamming). Pin the boundary so a mapping swap fails:
    confusion_matrix must NOT be in MULTIPLE_CHOICE, jaccard must NOT be in
    SINGLE_CHOICE."""
    single = set(get_metrics_for_answer_type(AnswerType.SINGLE_CHOICE))
    multi = set(get_metrics_for_answer_type(AnswerType.MULTIPLE_CHOICE))

    assert "confusion_matrix" in single
    assert "confusion_matrix" not in multi
    assert {"jaccard", "hamming_loss", "subset_accuracy"} <= multi
    assert "jaccard" not in single


def test_custom_is_superset_of_concrete_metric_types():
    """CUSTOM ("unknown type, show everything") must contain the deterministic
    metrics of every concrete type. Pins that the catch-all stays a superset —
    a dropped metric from CUSTOM would hide it from custom-control benchmarks."""
    custom = set(get_metrics_for_answer_type(AnswerType.CUSTOM))
    for at in AnswerType:
        if at is AnswerType.CUSTOM:
            continue
        for metric in get_metrics_for_answer_type(at):
            # field_accuracy / partial_match / boundary_accuracy / path_accuracy
            # / lca_accuracy are concrete-type-only and intentionally NOT in the
            # CUSTOM grab-bag, so only assert the ones CUSTOM advertises.
            if metric in custom or metric in {
                "field_accuracy",
                "partial_match",
                "boundary_accuracy",
                "path_accuracy",
                "lca_accuracy",
            }:
                continue
            pytest.fail(f"CUSTOM missing {metric} (offered by {at.value})")


# ---------------------------------------------------------------------------
# 2. VALIDATION: validate_metric_selection accepts in-set metrics, rejects
#    out-of-set ones, and treats an unknown answer type as CUSTOM (the
#    documented fallback). These pin the exact accept/reject boundary.
# ---------------------------------------------------------------------------


def test_validate_accepts_metric_in_answer_type_set():
    assert validate_metric_selection("binary", "exact_match") is True
    assert validate_metric_selection("long_text", "bertscore") is True
    assert validate_metric_selection("numeric", "mae") is True


def test_validate_rejects_metric_not_in_answer_type_set():
    # bertscore is a long-text metric; it is NOT valid for binary.
    assert validate_metric_selection("binary", "bertscore") is False
    # confusion_matrix is single-choice only, not multiple_choice.
    assert validate_metric_selection("multiple_choice", "confusion_matrix") is False
    # A wholly made-up metric is never valid.
    assert validate_metric_selection("numeric", "not_a_real_metric") is False


def test_validate_unknown_answer_type_falls_back_to_custom():
    """An unrecognized answer-type string is treated as CUSTOM (the most
    permissive set), per the except ValueError branch. So a metric that is in
    CUSTOM validates True even under a bogus answer-type string, and one that
    is in NO set (field_accuracy is structured-text-only, not in CUSTOM)
    validates False."""
    assert validate_metric_selection("totally_made_up_type", "bleu") is True
    assert validate_metric_selection("totally_made_up_type", "exact_match") is True
    # field_accuracy is NOT in the CUSTOM set, so the CUSTOM fallback rejects it.
    assert "field_accuracy" not in set(get_metrics_for_answer_type(AnswerType.CUSTOM))
    assert validate_metric_selection("totally_made_up_type", "field_accuracy") is False


def test_validate_is_consistent_with_resolution():
    """validate_metric_selection must agree with get_metrics_for_answer_type
    for every (answer_type, metric) pair — they are two views of one table."""
    for at in AnswerType:
        allowed = set(get_metrics_for_answer_type(at))
        for metric in allowed:
            assert validate_metric_selection(at.value, metric) is True, (at.value, metric)
        # A metric known to be outside this set must validate False.
        outsider = "definitely_not_in_any_set_xyz"
        assert validate_metric_selection(at.value, outsider) is False


# ---------------------------------------------------------------------------
# 3. DEFAULTS: get_metric_defaults returns the documented parameter blocks for
#    the four parameterized metrics and {} for everything else.
# ---------------------------------------------------------------------------


def test_metric_defaults_exact_values():
    assert get_metric_defaults("bleu") == {
        "max_order": 4,
        "weights": [0.25, 0.25, 0.25, 0.25],
        "smoothing": "method1",
    }
    assert get_metric_defaults("rouge") == {"variant": "rougeL", "use_stemmer": True}
    assert get_metric_defaults("meteor") == {"alpha": 0.9, "beta": 3.0, "gamma": 0.5}
    assert get_metric_defaults("chrf") == {"char_order": 6, "word_order": 0, "beta": 2}


def test_metric_defaults_empty_for_unparameterized_metric():
    """A metric with no default block returns {} (not None, not a default
    borrowed from another metric)."""
    assert get_metric_defaults("exact_match") == {}
    assert get_metric_defaults("f1") == {}
    assert get_metric_defaults("does_not_exist") == {}


def test_metric_defaults_returns_fresh_mapping_per_metric():
    """Distinct metrics must not share the same defaults object identity, and
    bleu/rouge defaults must differ (pins that the dict keys aren't swapped)."""
    assert get_metric_defaults("bleu") != get_metric_defaults("rouge")
    assert get_metric_defaults("bleu")["max_order"] == 4


# ---------------------------------------------------------------------------
# 4. NORMALIZATION + PRECEDENCE: normalize_metric_selection turns either a bare
#    string or an advanced dict into {"name", "parameters"} with user params
#    overriding defaults ({**defaults, **user_params}) and defaults filling the
#    gaps. This is the project-config-vs-defaults precedence seam.
# ---------------------------------------------------------------------------


def test_normalize_string_form_uses_defaults():
    """A bare metric name expands to name + the full default parameter block."""
    assert normalize_metric_selection("bleu") == {
        "name": "bleu",
        "parameters": {
            "max_order": 4,
            "weights": [0.25, 0.25, 0.25, 0.25],
            "smoothing": "method1",
        },
    }


def test_normalize_string_form_unparameterized_metric():
    assert normalize_metric_selection("exact_match") == {
        "name": "exact_match",
        "parameters": {},
    }


def test_normalize_advanced_form_user_param_overrides_default():
    """PRECEDENCE: a user-supplied parameter WINS over the default, and unset
    parameters fall back to the default. Kills a merge-order flip
    ({**user, **defaults}) that would let defaults clobber the user value."""
    result = normalize_metric_selection({"name": "bleu", "parameters": {"max_order": 2}})
    assert result["name"] == "bleu"
    # Override took effect...
    assert result["parameters"]["max_order"] == 2
    # ...while untouched params kept their defaults.
    assert result["parameters"]["weights"] == [0.25, 0.25, 0.25, 0.25]
    assert result["parameters"]["smoothing"] == "method1"


def test_normalize_advanced_form_adds_unknown_param_alongside_defaults():
    """A user param with no matching default is preserved and merged in."""
    result = normalize_metric_selection(
        {"name": "rouge", "parameters": {"variant": "rouge1", "custom_flag": True}}
    )
    assert result["parameters"]["variant"] == "rouge1"  # override
    assert result["parameters"]["use_stemmer"] is True  # default preserved
    assert result["parameters"]["custom_flag"] is True  # net-new user param


def test_normalize_advanced_form_no_params_yields_defaults():
    """An advanced form with an empty/absent parameters block is equivalent to
    the bare-string form: it gets the full default block."""
    assert normalize_metric_selection({"name": "meteor"}) == {
        "name": "meteor",
        "parameters": {"alpha": 0.9, "beta": 3.0, "gamma": 0.5},
    }
    assert normalize_metric_selection({"name": "meteor", "parameters": {}}) == {
        "name": "meteor",
        "parameters": {"alpha": 0.9, "beta": 3.0, "gamma": 0.5},
    }


def test_normalize_is_idempotent_on_already_normalized_input():
    """Re-normalizing an already-normalized selection yields the same result
    (the merged params are a no-op the second time). Pins idempotence of the
    precedence merge."""
    once = normalize_metric_selection("bleu")
    twice = normalize_metric_selection(once)
    assert once == twice


# ---------------------------------------------------------------------------
# 5. normalize_selected_methods: per-field normalization across the three
#    accepted shapes (list, dict-with-"metrics", legacy dict-with-"automated").
#    Every configured metric must survive normalization (completeness).
# ---------------------------------------------------------------------------


def test_normalize_selected_methods_list_form():
    out = normalize_selected_methods({"field1": ["bleu", "exact_match"]})
    names = [m["name"] for m in out["field1"]["metrics"]]
    assert names == ["bleu", "exact_match"]
    # bleu carries its defaults through; exact_match gets {}.
    assert out["field1"]["metrics"][0]["parameters"]["max_order"] == 4
    assert out["field1"]["metrics"][1]["parameters"] == {}


def test_normalize_selected_methods_dict_metrics_key():
    out = normalize_selected_methods({"f": {"metrics": ["rouge"]}})
    assert out["f"]["metrics"][0]["name"] == "rouge"
    assert out["f"]["metrics"][0]["parameters"]["variant"] == "rougeL"


def test_normalize_selected_methods_legacy_automated_key():
    """Legacy configs store the list under "automated"; it must still be read
    when "metrics" is absent (selections.get("metrics", selections.get("automated", [])))."""
    out = normalize_selected_methods({"f": {"automated": ["bleu"]}})
    assert [m["name"] for m in out["f"]["metrics"]] == ["bleu"]


def test_normalize_selected_methods_metrics_key_wins_over_automated():
    """When BOTH keys exist, "metrics" takes precedence over "automated"."""
    out = normalize_selected_methods(
        {"f": {"metrics": ["rouge"], "automated": ["bleu"]}}
    )
    assert [m["name"] for m in out["f"]["metrics"]] == ["rouge"]


def test_normalize_selected_methods_completeness():
    """COMPLETENESS: every configured metric across every field appears exactly
    once in the normalized output. Kills any drop in the per-field loop."""
    selected = {
        "fieldA": ["bleu", "rouge", "exact_match"],
        "fieldB": {"metrics": ["mae", "rmse"]},
        "fieldC": {"automated": ["accuracy"]},
    }
    out = normalize_selected_methods(selected)
    assert {m["name"] for m in out["fieldA"]["metrics"]} == {"bleu", "rouge", "exact_match"}
    assert {m["name"] for m in out["fieldB"]["metrics"]} == {"mae", "rmse"}
    assert {m["name"] for m in out["fieldC"]["metrics"]} == {"accuracy"}


def test_normalize_selected_methods_malformed_field_yields_empty():
    """A non-list/non-dict field value (e.g. a stray string) normalizes to an
    empty metric list rather than raising or fabricating a metric."""
    out = normalize_selected_methods({"weird": "not_a_structure"})
    assert out["weird"] == {"metrics": []}
    # dict with a non-list "metrics" also collapses to empty.
    out2 = normalize_selected_methods({"weird": {"metrics": "oops"}})
    assert out2["weird"] == {"metrics": []}


# ---------------------------------------------------------------------------
# 6. READBACK: get_selected_metrics_for_field and get_metric_parameters read
#    a stored config back. Pin default-fallthrough + format tolerance.
# ---------------------------------------------------------------------------


def test_get_selected_metrics_for_field_list_and_dict_formats():
    list_cfg = {"selected_methods": {"f": ["bleu", "rouge"]}}
    assert get_selected_metrics_for_field(list_cfg, "f") == ["bleu", "rouge"]

    dict_cfg = {"selected_methods": {"f": {"metrics": ["mae"]}}}
    assert get_selected_metrics_for_field(dict_cfg, "f") == ["mae"]


def test_get_selected_metrics_for_field_missing_returns_empty():
    assert get_selected_metrics_for_field({}, "f") == []
    assert get_selected_metrics_for_field(None, "f") == []
    assert get_selected_metrics_for_field({"selected_methods": {}}, "absent") == []


def test_get_metric_parameters_returns_configured_then_default():
    """Configured parameters win; an unconfigured metric falls back to the
    metric's defaults (NOT to {} and NOT to another metric's defaults)."""
    cfg_with_params = {
        "selected_methods": {
            "f": [{"name": "bleu", "parameters": {"max_order": 2}}]
        }
    }
    assert get_metric_parameters(cfg_with_params, "f", "bleu") == {"max_order": 2}
    # A metric not present in the field falls back to its own defaults.
    assert get_metric_parameters(cfg_with_params, "f", "rouge") == get_metric_defaults("rouge")
    # No config at all -> defaults for the requested metric.
    assert get_metric_parameters({}, "f", "chrf") == get_metric_defaults("chrf")


def test_get_metric_parameters_string_metric_uses_defaults():
    """A field listing a metric as a bare string (no per-metric params) returns
    that metric's defaults."""
    cfg_str = {"selected_methods": {"f": ["meteor"]}}
    assert get_metric_parameters(cfg_str, "f", "meteor") == get_metric_defaults("meteor")


# ---------------------------------------------------------------------------
# 7. EXTENDED MERGE (open-core seam): register_extended_metrics adds metrics to
#    an answer type WITHOUT dropping any core metric. Isolated via the
#    save/restore fixture so the global never leaks.
# ---------------------------------------------------------------------------


def test_extended_metrics_merge_appends_without_dropping_core(isolated_extended_metrics):
    core_long_text = list(get_metrics_for_answer_type(AnswerType.LONG_TEXT))

    register_extended_metrics("long_text", ["llm_judge_falloesung", "korrektur_falloesung"])

    merged = get_metrics_for_answer_type(AnswerType.LONG_TEXT)
    # Core metrics all preserved, in their original order, at the front.
    assert merged[: len(core_long_text)] == core_long_text
    # Extended metrics appended.
    assert "llm_judge_falloesung" in merged
    assert "korrektur_falloesung" in merged
    # Nothing from core was dropped.
    assert set(core_long_text) <= set(merged)
    assert len(merged) == len(core_long_text) + 2


def test_extended_metrics_isolated_to_their_answer_type(isolated_extended_metrics):
    """Registering for long_text must not change any OTHER answer type's set."""
    before_short = set(get_metrics_for_answer_type(AnswerType.SHORT_TEXT))
    register_extended_metrics("long_text", ["llm_judge_falloesung"])
    after_short = set(get_metrics_for_answer_type(AnswerType.SHORT_TEXT))
    assert before_short == after_short


def test_extended_metrics_validate_after_registration(isolated_extended_metrics):
    """A freshly-registered extended metric must then validate True for its
    answer type (the validation path reads the same merged set)."""
    assert validate_metric_selection("long_text", "llm_judge_falloesung") is False
    register_extended_metrics("long_text", ["llm_judge_falloesung"])
    assert validate_metric_selection("long_text", "llm_judge_falloesung") is True


def test_extended_metrics_accumulate_across_calls(isolated_extended_metrics):
    """Two registrations for the same answer type both stick (extend, not
    replace)."""
    register_extended_metrics("taxonomy", ["ext_one"])
    register_extended_metrics("taxonomy", ["ext_two"])
    merged = get_metrics_for_answer_type(AnswerType.TAXONOMY)
    assert "ext_one" in merged
    assert "ext_two" in merged


def test_no_extended_metrics_leak_into_clean_resolution(isolated_extended_metrics):
    """Inside an isolated context with the registry cleared, resolution equals
    the pure base table — confirming the fixture truly isolates and that the
    base path is extended-free."""
    isolated_extended_metrics.clear()
    for at in AnswerType:
        assert list(get_metrics_for_answer_type(at)) == ANSWER_TYPE_TO_METRICS[at]


# ---------------------------------------------------------------------------
# 8. IDEMPOTENCE: resolving the same answer type twice yields identical output,
#    and the resolution does not mutate the underlying table.
# ---------------------------------------------------------------------------


def test_resolution_is_idempotent_and_non_mutating():
    for at in AnswerType:
        snapshot = list(ANSWER_TYPE_TO_METRICS[at])
        first = get_metrics_for_answer_type(at)
        second = get_metrics_for_answer_type(at)
        assert first == second
        # Resolving must not mutate the source-of-truth table.
        assert ANSWER_TYPE_TO_METRICS[at] == snapshot
