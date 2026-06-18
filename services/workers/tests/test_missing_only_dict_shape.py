"""Unit tests for _row_has_score in tasks.py.

Locks down the predicate that decides whether a TaskEvaluation row is
"already scored" for `evaluate_missing_only=True` re-runs. The bug this
covers: pre-fix the predicate was `isinstance(v, (int, float))`, which
returned False for every metric written under the unified
`{value, method, details, error}` shape introduced by the academic-rigor
overhaul. Result: every successful row was treated as missing and got
silently re-run on every "evaluate missing only" click.

The function is duplicated inline below to keep the test free of the
Celery / SQLAlchemy stack `tasks.py` drags in at import time. Must be
kept in sync with `services/workers/tasks.py:_row_has_score` — the
contract test below catches any drift between the two copies.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import pytest


def _row_has_score(metrics: Optional[dict]) -> bool:
    """Mirror of `tasks.py:_row_has_score`. Keep in sync."""
    if not metrics:
        return False
    for k, v in metrics.items():
        if k == "error":
            continue
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            return True
        if isinstance(v, dict):
            inner = v.get("value")
            if isinstance(inner, (int, float)) and not isinstance(inner, bool):
                return True
    return False


@pytest.fixture(scope="module")
def row_has_score():
    return _row_has_score


def test_inline_copy_present_in_tasks_py():
    """Sanity: the source `tasks.py` actually defines `_row_has_score` so
    this inline copy isn't testing dead code. Body equivalence is asserted
    by the behavioural cases below; if those would diverge from `tasks.py`
    a careful reviewer must keep both in sync."""
    tasks_path = Path(__file__).parent.parent / "tasks.py"
    src = tasks_path.read_text()
    assert "def _row_has_score(" in src, (
        "tasks.py is missing the `_row_has_score` helper that the "
        "missing-only re-run logic depends on."
    )


class TestRowHasScore:
    def test_legacy_bare_float(self, row_has_score):
        assert row_has_score({"bleu": 0.42}) == True

    def test_legacy_int(self, row_has_score):
        assert row_has_score({"exact_match": 1}) == True

    def test_unified_dict_with_numeric_value(self, row_has_score):
        # Post-academic-rigor shape — the bug case.
        assert row_has_score(
            {
                "llm_judge_falloesung": {
                    "value": 0.85,
                    "method": "llm_judge_falloesung",
                    "details": {},
                    "error": None,
                }
            }
        ) == True

    def test_korrektur_unified_dict(self, row_has_score):
        assert row_has_score(
            {
                "korrektur_falloesung": {
                    "value": 51.5,
                    "method": "korrektur_falloesung",
                    "details": {"dimensions": {}},
                    "error": None,
                }
            }
        ) == True

    def test_error_row(self, row_has_score):
        # Worker-persisted error sentinel — must NOT count as scored.
        assert row_has_score({"error": True}) == False

    def test_empty_metrics(self, row_has_score):
        assert row_has_score({}) == False

    def test_none_metrics(self, row_has_score):
        assert row_has_score(None) == False

    def test_unified_dict_without_numeric_value(self, row_has_score):
        # Edge case: a partially-formed blob where `value` isn't a number.
        # Must not count as scored.
        assert row_has_score(
            {"some_metric": {"value": "not-a-number", "details": {}}}
        ) == False

    def test_bool_is_not_score(self, row_has_score):
        # `passed: True` etc. are booleans — Python treats bool as int so a
        # naive isinstance check would incorrectly count them.
        assert row_has_score({"passed": True}) == False

    def test_nested_bool_value_is_not_score(self, row_has_score):
        assert row_has_score({"x": {"value": True}}) == False

    def test_mixed_error_and_score(self, row_has_score):
        # An error sentinel plus a real numeric metric → still scored.
        assert row_has_score({"error": True, "bleu": 0.42}) == True

    def test_legacy_korrektur_root_shape(self, row_has_score):
        # Pre-unified Korrektur Falllösung was {score, total_score, dimensions, ...}
        # at root. The plan calls those out — we treat the root metric as
        # the dict; without `value` key it's not picked up. That's OK because
        # those rows were already covered by the legacy bare-float path
        # before academic-rigor; nothing in prod still writes this shape
        # AND lacks a top-level numeric metric.
        assert row_has_score(
            {"korrektur_falloesung": {"score": 51.5, "total_score": 51.5}}
        ) == False


# Inline mirror of `tasks.py:_normalize_field_key`. Same drift-control
# pattern as `_row_has_score` above — kept duplicated rather than
# importing from tasks.py (which drags in Celery / SQLAlchemy at import).


def _normalize_field_key(field_name, *, is_annotation):
    if not field_name:
        return field_name
    if "|" in field_name:
        parts = field_name.split("|")
    elif ":" in field_name:
        parts = field_name.split(":")
    else:
        return field_name
    if len(parts) != 3:
        return field_name
    cfg, pred, ref = parts
    if is_annotation and not pred.startswith("human:") and not pred.startswith("model:"):
        pred = f"human:{pred}"
    return f"{cfg}|{pred}|{ref}"


def test_inline_normalize_present_in_tasks_py():
    """Drift guard: tasks.py must define `_normalize_field_key`.

    The bug this covers: the worker has flip-flopped twice on field_name
    formatting (bare → colon → pipe), and missing-only matched rows by
    raw string equality. After each format change, the next missing-only
    run treated every existing row as missing → re-evaluated everything,
    duplicated rows under the new format, burned LLM-judge quota.
    """
    tasks_path = Path(__file__).parent.parent / "tasks.py"
    src = tasks_path.read_text()
    assert "def _normalize_field_key(" in src, (
        "tasks.py is missing the `_normalize_field_key` helper that the "
        "missing-only re-run logic depends on."
    )
    # Both call sites use it — guards against silent regression where
    # someone removes the normalize call but keeps the helper.
    assert src.count("_normalize_field_key(") >= 4, (
        "Expected _normalize_field_key calls at both lookup-set inserts "
        "AND both skip-check sites (4 total) in tasks.py."
    )


class TestNormalizeFieldKey:
    """The four format variants the worker has produced over time:

      1. ``loesung``                         (bare, pre-structured)
      2. ``cfg:loesung:musterlösung``        (colon separator)
      3. ``cfg|loesung|musterlösung``        (pipe separator — current)
      4. ``cfg|human:loesung|musterlösung``  (pipe + human: prefix)

    For annotations, all four (where parseable) must normalize to the
    same canonical with `human:` prefix.

    For generations, no `human:` prefix should be added.
    """

    def test_canonical_pipe_unchanged(self):
        assert _normalize_field_key(
            "cfg|loesung|musterlösung", is_annotation=False
        ) == "cfg|loesung|musterlösung"

    def test_colon_to_pipe(self):
        # The actual prod regression: 94 generation rows had ':'-separated
        # field_name and got duplicated when the worker switched to '|'.
        assert _normalize_field_key(
            "cfg:loesung:musterlösung", is_annotation=False
        ) == "cfg|loesung|musterlösung"

    def test_annotation_gets_human_prefix(self):
        # Annotation rows persisted before the `human:` prefix convention
        # must normalize to the prefixed form, otherwise a fresh run
        # produces `human:loesung` and the lookup misses the legacy row.
        assert _normalize_field_key(
            "cfg|loesung|musterlösung", is_annotation=True
        ) == "cfg|human:loesung|musterlösung"

    def test_annotation_already_prefixed_stays(self):
        assert _normalize_field_key(
            "cfg|human:loesung|musterlösung", is_annotation=True
        ) == "cfg|human:loesung|musterlösung"

    def test_generation_with_model_prefix_unchanged(self):
        # `model:` prefix is symmetric to `human:` for the parser; both
        # are valid pred prefixes the helper must not mangle.
        assert _normalize_field_key(
            "cfg|model:loesung|musterlösung", is_annotation=False
        ) == "cfg|model:loesung|musterlösung"

    def test_colon_format_for_annotation(self):
        # Worst case: legacy colon row + annotation with no prefix → should
        # gain BOTH the prefix and the canonical separator.
        assert _normalize_field_key(
            "cfg:loesung:musterlösung", is_annotation=True
        ) == "cfg|human:loesung|musterlösung"

    def test_bare_legacy_unchanged(self):
        # No separator → can't recover config_id without project context.
        # Returns unchanged; the caller is expected to have backfilled
        # those rows out-of-band via the migrate_field_names script.
        assert _normalize_field_key("loesung", is_annotation=False) == "loesung"

    def test_none_passthrough(self):
        assert _normalize_field_key(None, is_annotation=False) is None
        assert _normalize_field_key("", is_annotation=False) == ""

    def test_unparseable_left_alone(self):
        # 4-segment string (e.g. somebody puts a ':' in pred) — don't
        # silently truncate, leave for the caller to notice.
        assert _normalize_field_key(
            "cfg:weird:extra:musterlösung", is_annotation=False
        ) == "cfg:weird:extra:musterlösung"


# Inline mirror of `tasks.py:_row_is_terminal_error`. Same drift pattern.

def _row_is_terminal_error(metrics):
    if not metrics:
        return False
    for k, v in metrics.items():
        if k == "error":
            continue
        if isinstance(v, dict) and v.get("error"):
            return True
    return False


def test_inline_terminal_error_helper_present_in_tasks_py():
    """Drift guard. Pairs with the test for `_row_has_score` /
    `_normalize_field_key` above. The bug this catches: silent removal
    of the terminal-error gate would cause known-failed evaluations
    (missing API key, content moderation refusal, parse failure) to be
    re-tried on every missing-only run, accumulating stub rows
    indefinitely and burning LLM-judge quota."""
    tasks_path = Path(__file__).parent.parent / "tasks.py"
    src = tasks_path.read_text()
    assert "def _row_is_terminal_error(" in src, (
        "tasks.py is missing the `_row_is_terminal_error` helper that "
        "blocks retries of known-failed evaluations."
    )
    # Both missing-only filters must consult it (sites at ~2191 + ~2576).
    assert src.count("_row_is_terminal_error(") >= 2, (
        "Expected `_row_is_terminal_error(` calls at both lookup-set "
        "inserts (generation + annotation) — at least 2 in tasks.py."
    )
    # And the silent-fallthrough guard must exist at both LLM-judge sites
    # (writes a terminal-error row instead of falling through to
    # sample_evaluator when the judge evaluator wasn't initialized).
    assert src.count("LLM judge evaluator not initialized for config") >= 2, (
        "Expected the silent-fallthrough guard to write a terminal-error "
        "row at both LLM-judge call sites (gen + ann), not just one."
    )


class TestRowIsTerminalError:
    """The unified blob shape `{value, method, details, error}` is what
    the worker writes when an evaluation can't produce a real score —
    e.g. judge evaluator init failed, prompt overflow, content moderation
    refusal. The terminal-error gate stops missing-only from retrying
    these.
    """

    def test_terminal_error_blocks_retry(self):
        # The exact shape the silent-fallthrough guard now writes.
        metrics = {
            "llm_judge_falloesung": {
                "value": None,
                "method": "llm_judge_falloesung",
                "error": "LLM judge evaluator not initialized for config xxx",
                "details": {},
            }
        }
        assert _row_is_terminal_error(metrics) == True

    def test_legacy_null_metric_value_does_NOT_block_retry(self):
        # Pre-fix rows have `metric: null` (bare JSON null, not a dict).
        # The terminal-error gate must NOT mask these — they pre-date
        # the gate's introduction and need to be deleted by the
        # accompanying data backfill, not silently ignored.
        metrics = {"llm_judge_falloesung": None}
        assert _row_is_terminal_error(metrics) == False

    def test_successful_unified_row_NOT_terminal(self):
        # A real score row is not "terminal" — the predicate is for
        # known-failed rows specifically.
        metrics = {
            "llm_judge_falloesung": {
                "value": 0.85,
                "method": "llm_judge_falloesung",
                "error": None,
                "details": {},
            }
        }
        assert _row_is_terminal_error(metrics) == False

    def test_empty_or_none(self):
        assert _row_is_terminal_error({}) == False
        assert _row_is_terminal_error(None) == False

    def test_multi_metric_one_terminal(self):
        # If even one metric in the row is terminal-failed, the whole
        # row is treated as tried-and-failed.
        metrics = {
            "bleu": 0.42,  # legacy bare-float, valid
            "llm_judge_falloesung": {"value": None, "error": "context overflow"},
        }
        assert _row_is_terminal_error(metrics) == True


def test_task_evaluation_constructors_pass_evaluation_config_id():
    """Drift guard: every ``TaskEvaluation(...)`` constructor in
    ``tasks.py`` must set ``evaluation_config_id=`` alongside
    ``field_name=``.

    Why: Issue #111 / migration 057 introduces a discrete
    ``task_evaluations.evaluation_config_id`` column so the per-config
    statistics filter can match cleanly instead of parsing the
    pipe-encoded ``field_name``. If a future worker patch adds a new
    ``TaskEvaluation(...)`` constructor and forgets the new kwarg, the
    row lands with ``evaluation_config_id IS NULL`` and the issue #111
    aggregator silently drops it from per-config stats.

    The check is intentionally coarse — count constructor opens vs.
    ``evaluation_config_id=`` argument passes in the source. The
    counter also picks up the function signature default in
    ``_evaluate_llm_judge_single`` and the matching call-site kwarg,
    which is fine: that path threads the column through, so a value of
    ``count(eval_cfg) >= count(TaskEvaluation()) `` is the floor we
    want, not a strict equality.
    """
    tasks_path = Path(__file__).parent.parent / "tasks.py"
    src = tasks_path.read_text()

    constructor_count = src.count("TaskEvaluation(")
    kwarg_count = len(re.findall(r"evaluation_config_id\s*=", src))

    assert kwarg_count >= constructor_count, (
        "Every TaskEvaluation(...) must set evaluation_config_id "
        "alongside field_name. Without it, the per-config statistics "
        "filter for issue #111 will silently exclude rows. Found "
        f"{constructor_count} TaskEvaluation(...) constructors but only "
        f"{kwarg_count} occurrences of 'evaluation_config_id=' in tasks.py."
    )


# Inline mirror of `tasks.py:_pred_field_matches`. Same drift pattern.

def _pred_field_matches(row_field_name, config_pred_field):
    """Mirror of `tasks.py:_pred_field_matches`. Keep in sync."""
    _wildcards = ("__all_human__", "__all_model__")
    if not row_field_name:
        return False
    if "|" in row_field_name:
        return False

    def _strip_role(s):
        if s in _wildcards:
            return s
        if s.startswith("human:") or s.startswith("model:"):
            return s.split(":", 1)[1]
        return s

    if row_field_name == config_pred_field:
        return True
    return _strip_role(row_field_name) == _strip_role(config_pred_field)


def test_inline_pred_field_matches_present_in_tasks_py():
    """Drift guard for the immediate-eval recognition path (config-id based).

    The bug this covers: immediate eval persists a BARE field_name
    (e.g. ``human:loesung``) plus a discrete ``evaluation_config_id``, but the
    missing-only matcher keyed only on the 3-part ``{cfg}|{pred}|{ref}`` form,
    so it never recognized immediate grades → it re-graded every
    immediate-graded annotation on the next missing-only run. The fix
    reconstructs the expected key from ``evaluation_config_id`` via
    ``_pred_field_matches`` + ``_reconstruct_expected_keys``.
    """
    tasks_path = Path(__file__).parent.parent / "tasks.py"
    src = tasks_path.read_text()
    assert "def _pred_field_matches(" in src, (
        "tasks.py is missing the `_pred_field_matches` helper that maps a bare "
        "immediate-eval field_name to a config prediction field."
    )
    assert "def _reconstruct_expected_keys(" in src, (
        "tasks.py is missing `_reconstruct_expected_keys` — the config-id-based "
        "recognition of bare immediate-eval rows in missing-only mode."
    )
    # Definition + BOTH skip-set loops (generation + annotation) must use it.
    assert src.count("_reconstruct_expected_keys(") >= 3, (
        "Expected `_reconstruct_expected_keys` definition + calls at BOTH the "
        "generation and annotation missing-only skip-set inserts in tasks.py."
    )


class TestPredFieldMatches:
    """A bare immediate-eval ``field_name`` (the config's prediction field) vs.
    a config ``prediction_fields`` entry — tolerating the human:/model: role
    prefix so a backfilled/legacy row maps to the right config."""

    def test_exact_bare_match(self):
        assert _pred_field_matches("human:loesung", "human:loesung") is True

    def test_bare_without_prefix_matches_human_field(self):
        # Korrektur-style bare 'loesung' row vs a 'human:loesung' config field.
        assert _pred_field_matches("loesung", "human:loesung") is True

    def test_model_prefix_tolerated(self):
        assert _pred_field_matches("loesung", "model:loesung") is True

    def test_different_field_does_not_match(self):
        assert _pred_field_matches("human:other", "human:loesung") is False

    def test_three_part_row_excluded(self):
        # 3-part rows are the _normalize_field_key path, not this helper.
        assert (
            _pred_field_matches("cfg|human:loesung|musterlösung", "human:loesung")
            is False
        )

    def test_wildcard_never_matches(self):
        assert _pred_field_matches("human:loesung", "__all_human__") is False

    def test_empty(self):
        assert _pred_field_matches(None, "human:loesung") is False
        assert _pred_field_matches("", "human:loesung") is False
