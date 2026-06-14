"""Behavioral coverage for worker task handlers + helpers in tasks.py.

Targets uncovered handler/helper logic that the existing
``test_tasks_deep_coverage.py`` (generation + run_evaluation + single-sample),
``test_evaluation_fanout.py`` (signature/source contracts + bulk-upsert), and
``test_tasks_utils.py`` (label config / synthetic data / cleanup) do NOT cover:

- Pure transform helpers: ``_get_insensitive``, ``_immediate_eval_metadata``,
  ``_llm_judge_columns_from_result``, ``_build_multidim_judge_row_metrics``,
  ``_row_is_terminal_error``, ``_normalize_field_key``,
  ``_classify_cell_failure`` (timeout / content_policy / quota / 429 buckets),
  ``extract_label_config_fields`` (malformed XML + tag filtering).
- Redis-backed poison-cell counter ``_record_cell_attempt`` (success + fallback).
- SQL counter helpers ``_record_cell_failure_reason`` /
  ``_bump_evaluation_counters`` (param shape + zero-guard short-circuit).
- ``_bulk_upsert_task_evaluations`` empty-rows guard + RETURNING-driven counts.
- ``get_supported_metrics`` task (success/all/error).
- ``auto_submit_expired_timer`` (no-DB, session-not-found, already-completed,
  korrektur expiry, existing-annotation skip, draft auto-submit + is_labeled
  flip, exception/rollback).
- ``finalize_evaluation_run`` early-return branches (not found, already terminal).

Mirrors the existing workers-test idioms exactly:
- ``MagicMock`` db sessions with chained ``query().filter().first()`` returns,
  the ``_FakeSession``/``_FakeQuery`` model-keyed pattern from
  ``test_import_task.py``, and ``patch.object(tasks_module, "SessionLocal", ...)``.
- Worker code is sync (no event loop); celery tasks are called DIRECTLY
  (``bind=True`` tasks auto-inject ``self``).
"""

import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

import tasks as tasks_module
from tasks import (
    _build_multidim_judge_row_metrics,
    _bulk_upsert_task_evaluations,
    _bump_evaluation_counters,
    _classify_cell_failure,
    _get_insensitive,
    _immediate_eval_metadata,
    _llm_judge_columns_from_result,
    _normalize_field_key,
    _record_cell_attempt,
    _record_cell_failure_reason,
    _row_is_terminal_error,
    auto_submit_expired_timer,
    extract_label_config_fields,
    finalize_evaluation_run,
    get_supported_metrics,
)


# ===========================================================================
# _get_insensitive
# ===========================================================================


class TestGetInsensitive:
    def test_exact_match_preferred(self):
        assert _get_insensitive({"Answer": "x", "answer": "y"}, "Answer") == "x"

    def test_case_insensitive_fallback(self):
        assert _get_insensitive({"ANSWER": "v"}, "answer") == "v"

    def test_missing_returns_default(self):
        assert _get_insensitive({"foo": 1}, "bar") == ""
        assert _get_insensitive({"foo": 1}, "bar", default="d") == "d"


# ===========================================================================
# _immediate_eval_metadata
# ===========================================================================


class TestImmediateEvalMetadata:
    def test_shape(self):
        out = _immediate_eval_metadata()
        assert out["metrics"] == {"llm_judge_falloesung": True}
        em = out["eval_metadata"]
        assert em["evaluation_type"] == "llm_judge"
        cfg = em["evaluation_configs"][0]
        assert cfg["id"] == "immediate_llm_judge_falloesung"
        assert cfg["metric"] == "llm_judge_falloesung"
        assert cfg["enabled"] is True


# ===========================================================================
# _llm_judge_columns_from_result
# ===========================================================================


class TestLLMJudgeColumnsFromResult:
    def test_none_or_non_dict_returns_empty(self):
        assert _llm_judge_columns_from_result(None) == {}
        assert _llm_judge_columns_from_result("not a dict") == {}

    def test_missing_call_metadata_yields_all_null_columns(self):
        # No _call_metadata KEY → `result.get(...) or {}` is still a dict, so
        # the helper emits the column kwargs with every value None/False (the
        # TaskEvaluation row writes NULLs for the academic-rigor columns).
        # (A non-dict _call_metadata is the only path that returns {}.)
        assert _llm_judge_columns_from_result({"value": 0.5}) == {
            "seed": None,
            "finish_reason": None,
            "truncated": False,
            "refusal": False,
            "error_type": None,
            "latency_ms": None,
            "input_tokens": None,
            "output_tokens": None,
            "raw_output": None,
        }

    def test_non_dict_call_metadata_returns_empty(self):
        assert _llm_judge_columns_from_result({"_call_metadata": "oops"}) == {}

    def test_full_extraction_and_bool_coercion(self):
        result = {
            "_call_metadata": {
                "seed": 42,
                "finish_reason": "stop",
                "truncated": 1,        # truthy non-bool → coerced to True
                "refusal": 0,          # falsy → False
                "error_type": "none",
                "response_time_ms": 123,
                "input_tokens": 10,
                "output_tokens": 20,
            },
            "_raw_output": "<judge text>",
        }
        cols = _llm_judge_columns_from_result(result)
        assert cols["seed"] == 42
        assert cols["finish_reason"] == "stop"
        assert cols["truncated"] is True
        assert cols["refusal"] is False
        assert cols["error_type"] == "none"
        assert cols["latency_ms"] == 123
        assert cols["input_tokens"] == 10
        assert cols["output_tokens"] == 20
        assert cols["raw_output"] == "<judge text>"

    def test_defaults_when_call_metadata_empty(self):
        cols = _llm_judge_columns_from_result({"_call_metadata": {}})
        # Missing keys default; bool flags default False.
        assert cols["truncated"] is False
        assert cols["refusal"] is False
        assert cols["seed"] is None
        assert cols["raw_output"] is None


# ===========================================================================
# _build_multidim_judge_row_metrics
# ===========================================================================


class TestBuildMultidimJudgeRowMetrics:
    def test_none_multidim_is_terminal_error_row(self):
        metrics, value = _build_multidim_judge_row_metrics(None, "llm_judge", None)
        assert value is None
        entry = metrics["llm_judge"]
        assert entry["value"] is None
        assert entry["error"]  # carries a default error message
        # Must read as a terminal error so missing-only doesn't re-run it.
        assert _row_is_terminal_error(metrics) is True

    def test_error_field_uses_explicit_message(self):
        metrics, value = _build_multidim_judge_row_metrics(
            {"error": True, "error_message": "judge boom", "_raw_output": "r"},
            "llm_judge",
            None,
        )
        assert value is None
        assert metrics["llm_judge"]["error"] == "judge boom"
        assert metrics["llm_judge"]["details"]["raw_output"] == "r"

    def test_error_msg_arg_wins_over_internal(self):
        metrics, _ = _build_multidim_judge_row_metrics(
            {"error": True, "error_message": "internal"},
            "llm_judge",
            "explicit override",
        )
        assert metrics["llm_judge"]["error"] == "explicit override"

    def test_success_normalizes_total_over_max(self):
        multidim = {
            "scores": {"clarity": 3},
            "total_score": 6.0,
            "total_max": 8.0,
            "overall_assessment": "ok",
            "_call_metadata": {"seed": 1},
            "_raw_output": "raw",
        }
        metrics, value = _build_multidim_judge_row_metrics(multidim, "llm_judge", None)
        assert value == pytest.approx(0.75)
        entry = metrics["llm_judge"]
        assert entry["value"] == pytest.approx(0.75)
        assert entry["error"] is None
        assert entry["details"]["total_score"] == 6.0
        assert entry["details"]["total_max"] == 8.0
        assert metrics["raw_score"] == pytest.approx(0.75)

    def test_zero_total_max_normalizes_to_zero(self):
        multidim = {"scores": {"x": 0}, "total_score": 0, "total_max": 0}
        metrics, value = _build_multidim_judge_row_metrics(multidim, "llm_judge", None)
        assert value == 0.0
        assert metrics["llm_judge"]["value"] == 0.0


# ===========================================================================
# _row_is_terminal_error
# ===========================================================================


class TestRowIsTerminalError:
    def test_empty_or_none_is_not_terminal(self):
        assert _row_is_terminal_error(None) is False
        assert _row_is_terminal_error({}) is False

    def test_dict_with_error_is_terminal(self):
        assert _row_is_terminal_error(
            {"llm_judge": {"value": None, "error": "boom"}}
        ) is True

    def test_dict_without_error_is_not_terminal(self):
        assert _row_is_terminal_error(
            {"rouge": {"value": 0.5, "error": None}}
        ) is False

    def test_top_level_error_key_is_ignored(self):
        # The bare "error" key is skipped by the loop; a numeric metric with
        # no nested error is not terminal.
        assert _row_is_terminal_error({"error": "ignored", "rouge": 0.5}) is False


# ===========================================================================
# _normalize_field_key
# ===========================================================================


class TestNormalizeFieldKey:
    def test_none_passthrough(self):
        assert _normalize_field_key(None, is_annotation=False) is None

    def test_bare_legacy_name_unchanged(self):
        assert _normalize_field_key("loesung", is_annotation=True) == "loesung"

    def test_pipe_format_passthrough_when_already_prefixed(self):
        assert (
            _normalize_field_key("cfg|human:pred|ref", is_annotation=True)
            == "cfg|human:pred|ref"
        )

    def test_colon_legacy_converted_to_pipe(self):
        assert (
            _normalize_field_key("cfg:pred:ref", is_annotation=False)
            == "cfg|pred|ref"
        )

    def test_annotation_gets_human_prefix(self):
        assert (
            _normalize_field_key("cfg|pred|ref", is_annotation=True)
            == "cfg|human:pred|ref"
        )

    def test_model_prefix_not_double_prefixed(self):
        assert (
            _normalize_field_key("cfg|model:pred|ref", is_annotation=True)
            == "cfg|model:pred|ref"
        )

    def test_wrong_part_count_unchanged(self):
        assert (
            _normalize_field_key("a|b|c|d", is_annotation=True) == "a|b|c|d"
        )


# ===========================================================================
# _classify_cell_failure  (existing fanout test covers rate_limit/other;
# these pin the remaining buckets + message-driven paths)
# ===========================================================================


class TestClassifyCellFailureExtraBuckets:
    def test_timeout_by_class_suffix(self):
        class ReadTimeout(Exception):
            pass

        assert _classify_cell_failure(ReadTimeout("...")) == "timeout"
        assert _classify_cell_failure(TimeoutError("...")) == "timeout"

    def test_rate_limit_by_message_and_429(self):
        assert _classify_cell_failure(Exception("HTTP 429 Too Many Requests")) == "rate_limit"
        assert _classify_cell_failure(Exception("rate limit reached")) == "rate_limit"
        assert _classify_cell_failure(Exception("rate_limit exceeded")) == "rate_limit"

    def test_content_policy_by_message(self):
        assert _classify_cell_failure(Exception("content policy violation")) == "content_policy"
        assert _classify_cell_failure(Exception("content filter triggered")) == "content_policy"

    def test_quota_exceeded_by_message(self):
        assert _classify_cell_failure(Exception("quota exceeded for org")) == "quota_exceeded"
        assert _classify_cell_failure(Exception("monthly quota limit hit")) == "quota_exceeded"

    def test_unknown_message_is_other(self):
        assert _classify_cell_failure(Exception("disk full")) == "other"


# ===========================================================================
# extract_label_config_fields  (malformed XML + tag filtering branches)
# ===========================================================================


class TestExtractLabelConfigFieldsBranches:
    def test_collects_only_annotation_output_tags(self):
        cfg = """
        <View>
          <Header value="ignored"/>
          <Text name="passage" value="$text"/>
          <TextArea name="answer"/>
          <Choices name="label"><Choice value="a"/></Choices>
          <Rating name="quality"/>
          <Number name="score"/>
        </View>
        """
        fields = extract_label_config_fields(cfg)
        assert fields == ["answer", "label", "quality", "score"]

    def test_element_without_name_skipped(self):
        cfg = '<View><TextArea/><TextArea name="x"/></View>'
        assert extract_label_config_fields(cfg) == ["x"]

    def test_malformed_xml_returns_empty_without_raising(self):
        assert extract_label_config_fields("<View><not closed") == []

    def test_empty_string_returns_empty(self):
        assert extract_label_config_fields("") == []


# ===========================================================================
# _record_cell_attempt  (Redis-backed counter + fallback)
# ===========================================================================


class TestRecordCellAttempt:
    def test_returns_incremented_count_and_sets_ttl(self):
        fake_client = MagicMock()
        fake_client.incr.return_value = 2
        with patch.object(tasks_module.redis, "from_url", return_value=fake_client):
            n = _record_cell_attempt("eval-1", "cell-abc")
        assert n == 2
        fake_client.incr.assert_called_once_with(
            "benger:cell_attempts:eval-1:cell-abc"
        )
        fake_client.expire.assert_called_once_with(
            "benger:cell_attempts:eval-1:cell-abc",
            tasks_module._CELL_ATTEMPT_TTL_SECS,
        )

    def test_redis_error_falls_back_to_first_attempt(self):
        with patch.object(
            tasks_module.redis, "from_url", side_effect=RuntimeError("no redis")
        ):
            n = _record_cell_attempt("eval-1", "cell-abc")
        # Fail-open during outage: treat as first attempt (don't bail the cell).
        assert n == 1


# ===========================================================================
# _record_cell_failure_reason  (SQL UPDATE param shape)
# ===========================================================================


class TestRecordCellFailureReason:
    def test_executes_update_with_reason_and_id(self):
        db = MagicMock()
        _record_cell_failure_reason(db, "eval-9", "rate_limit")
        assert db.execute.call_count == 1
        args, _ = db.execute.call_args
        params = args[1]
        assert params == {"evaluation_id": "eval-9", "reason": "rate_limit"}
        sql = str(args[0]).lower()
        assert "failures_by_reason" in sql
        # Guarded by the same terminal-status filter as the counter bump.
        assert "status not in" in sql


# ===========================================================================
# _bump_evaluation_counters  (zero-guard short-circuit + param shape)
# ===========================================================================


class TestBumpEvaluationCounters:
    def test_all_zero_is_noop(self):
        db = MagicMock()
        _bump_evaluation_counters(
            db,
            evaluation_id="e1",
            samples_evaluated=0,
            samples_passed=0,
            samples_failed=0,
        )
        db.execute.assert_not_called()

    def test_nonzero_executes_atomic_update(self):
        db = MagicMock()
        _bump_evaluation_counters(
            db,
            evaluation_id="e1",
            samples_evaluated=3,
            samples_passed=2,
            samples_failed=1,
        )
        assert db.execute.call_count == 1
        args, _ = db.execute.call_args
        params = args[1]
        assert params == {
            "n": 3,
            "p": 2,
            "f": 1,
            "evaluation_id": "e1",
        }
        sql = str(args[0]).lower()
        assert "samples_evaluated = coalesce(samples_evaluated, 0) + :n" in sql
        assert "has_sample_results = true" in sql


# ===========================================================================
# _bulk_upsert_task_evaluations  (empty guard + RETURNING-driven math)
# ===========================================================================


class TestBulkUpsertCounts:
    def test_empty_rows_short_circuits(self):
        db = MagicMock()
        assert _bulk_upsert_task_evaluations(db, []) == (0, 0, 0)
        db.execute.assert_not_called()

    def test_counts_derive_from_returning_passed(self):
        # Two rows land via RETURNING (one passed, one failed); the function
        # must report (inserted=2, passed=1, failed=1) — never the requested
        # row count.
        def fake_execute(stmt):
            result = MagicMock()
            result.fetchall.return_value = [
                types.SimpleNamespace(passed=True),
                types.SimpleNamespace(passed=False),
            ]
            return result

        db = MagicMock()
        db.execute.side_effect = fake_execute
        rows = [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "evaluation_id": "e",
                "field_name": "f|p|r",
                "metrics": {},
                "passed": True,
            }
        ]
        inserted, passed, failed = _bulk_upsert_task_evaluations(db, rows)
        assert (inserted, passed, failed) == (2, 1, 1)


# ===========================================================================
# get_supported_metrics  (task: success specific / success all / error)
# ===========================================================================


class TestGetSupportedMetricsTask:
    def test_specific_task_type(self):
        reg = MagicMock()
        reg.get_supported_metrics.return_value = ["bleu", "rouge"]
        with patch.object(tasks_module, "evaluator_registry", reg):
            out = get_supported_metrics("text_generation")
        assert out["status"] == "success"
        assert out["task_type"] == "text_generation"
        assert out["metrics"] == ["bleu", "rouge"]

    def test_all_task_types(self):
        reg = MagicMock()
        reg.get_supported_task_types.return_value = ["a", "b"]
        reg.get_supported_metrics.side_effect = lambda t: [f"{t}_metric"]
        with patch.object(tasks_module, "evaluator_registry", reg):
            out = get_supported_metrics()
        assert out["status"] == "success"
        assert out["supported_task_types"] == ["a", "b"]
        assert out["metrics_by_task_type"] == {"a": ["a_metric"], "b": ["b_metric"]}

    def test_error_path(self):
        reg = MagicMock()
        reg.get_supported_metrics.side_effect = RuntimeError("registry down")
        with patch.object(tasks_module, "evaluator_registry", reg):
            out = get_supported_metrics("text_generation")
        assert out["status"] == "error"
        assert "registry down" in out["message"]


# ===========================================================================
# auto_submit_expired_timer
# ===========================================================================


class _TimerFakeQuery:
    """Chainable query stub: filter(...).first() / .count() configurable."""

    def __init__(self, first=None, count=0):
        self._first = first
        self._count = count

    def filter(self, *a, **k):
        return self

    def first(self):
        return self._first

    def count(self):
        return self._count


class _TimerFakeSession:
    """Model-keyed fake session for auto_submit_expired_timer.

    ``by_model`` maps a *class name string* → a ``_TimerFakeQuery`` (or a
    callable returning one, for the call-order-sensitive Annotation lookups).
    """

    def __init__(self, by_model):
        self._by_model = by_model
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False
        self._annotation_calls = 0

    def query(self, model):
        name = getattr(model, "__name__", str(model))
        entry = self._by_model.get(name)
        if callable(entry):
            return entry()
        return entry if entry is not None else _TimerFakeQuery()

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def _patch_timer_session(session):
    return patch.object(tasks_module, "SessionLocal", return_value=session)


def _make_timer_session(**fields):
    defaults = dict(
        id="ts-1",
        task_id="task-1",
        project_id="proj-1",
        user_id="user-1",
        target_type="task",
        target_id=None,
        completed_at=None,
        auto_submitted=False,
        draft_result=None,
        time_limit_seconds=600,
    )
    defaults.update(fields)
    return types.SimpleNamespace(**defaults)


class TestAutoSubmitExpiredTimer:
    def test_no_database_returns_error(self):
        with patch.object(tasks_module, "HAS_DATABASE", False):
            out = auto_submit_expired_timer("ts-1")
        assert out == {"status": "error", "message": "Database not available"}

    def test_session_not_found(self):
        session = _TimerFakeSession({"TimerSession": _TimerFakeQuery(first=None)})
        with patch.object(tasks_module, "HAS_DATABASE", True):
            with _patch_timer_session(session):
                out = auto_submit_expired_timer("ts-1")
        assert out == {"status": "skipped", "reason": "session not found"}
        assert session.closed is True

    def test_already_completed_session(self):
        ts = _make_timer_session(completed_at=object())
        session = _TimerFakeSession({"TimerSession": _TimerFakeQuery(first=ts)})
        with patch.object(tasks_module, "HAS_DATABASE", True):
            with _patch_timer_session(session):
                out = auto_submit_expired_timer("ts-1")
        assert out == {"status": "skipped", "reason": "already completed"}

    def test_korrektur_session_expires_without_grade(self):
        ts = _make_timer_session(target_type="annotation")
        session = _TimerFakeSession({"TimerSession": _TimerFakeQuery(first=ts)})
        with patch.object(tasks_module, "HAS_DATABASE", True):
            with _patch_timer_session(session):
                out = auto_submit_expired_timer("ts-1")
        assert out["status"] == "expired_korrektur"
        assert ts.auto_submitted is True
        assert ts.completed_at is not None
        assert session.commits == 1

    def test_existing_annotation_skips_autosubmit(self):
        ts = _make_timer_session()
        existing = types.SimpleNamespace(id="ann-existing")
        session = _TimerFakeSession({
            "TimerSession": _TimerFakeQuery(first=ts),
            "Annotation": _TimerFakeQuery(first=existing),
        })
        with patch.object(tasks_module, "HAS_DATABASE", True):
            with _patch_timer_session(session):
                out = auto_submit_expired_timer("ts-1")
        assert out == {"status": "skipped", "reason": "annotation already exists"}
        assert ts.auto_submitted is True
        assert session.commits == 1
        # No new annotation row added when the client already submitted.
        assert session.added == []

    def test_autosubmit_from_draft_flips_is_labeled(self):
        ts = _make_timer_session(draft_result=[{"from_name": "answer"}])
        task = types.SimpleNamespace(total_annotations=0, is_labeled=False)
        project = types.SimpleNamespace(min_annotations_per_task=1)

        # Annotation is queried twice: existence check (None) then the
        # non-cancelled count(). Serve different queries by call order.
        ann_calls = {"n": 0}

        def annotation_query():
            ann_calls["n"] += 1
            if ann_calls["n"] == 1:
                return _TimerFakeQuery(first=None)      # no existing annotation
            return _TimerFakeQuery(count=0)             # non-cancelled count (+1 => 1)

        session = _TimerFakeSession({
            "TimerSession": _TimerFakeQuery(first=ts),
            "Annotation": annotation_query,
            "TaskDraft": _TimerFakeQuery(first=None),
            "Task": _TimerFakeQuery(first=task),
            "Project": _TimerFakeQuery(first=project),
        })
        with patch.object(tasks_module, "HAS_DATABASE", True):
            with _patch_timer_session(session):
                out = auto_submit_expired_timer("ts-1")
        assert out["status"] == "submitted"
        assert "annotation_id" in out
        # An Annotation row was created and added.
        assert len(session.added) == 1
        assert session.added[0].auto_submitted is True
        # Counters bumped + threshold reached (count 0 + 1 >= min 1).
        assert task.total_annotations == 1
        assert task.is_labeled is True
        assert ts.completed_at is not None
        assert session.commits == 1

    def test_autosubmit_falls_back_to_taskdraft_when_no_session_draft(self):
        ts = _make_timer_session(draft_result=None)
        draft = types.SimpleNamespace(draft_result=[{"from_name": "x"}])
        task = types.SimpleNamespace(total_annotations=5, is_labeled=False)
        project = types.SimpleNamespace(min_annotations_per_task=99)

        ann_calls = {"n": 0}

        def annotation_query():
            ann_calls["n"] += 1
            if ann_calls["n"] == 1:
                return _TimerFakeQuery(first=None)
            return _TimerFakeQuery(count=0)

        session = _TimerFakeSession({
            "TimerSession": _TimerFakeQuery(first=ts),
            "Annotation": annotation_query,
            "TaskDraft": _TimerFakeQuery(first=draft),
            "Task": _TimerFakeQuery(first=task),
            "Project": _TimerFakeQuery(first=project),
        })
        with patch.object(tasks_module, "HAS_DATABASE", True):
            with _patch_timer_session(session):
                out = auto_submit_expired_timer("ts-1")
        assert out["status"] == "submitted"
        # Draft result from TaskDraft table propagated onto the annotation.
        assert session.added[0].result == [{"from_name": "x"}]
        # Threshold NOT reached (1 < 99) → is_labeled stays False.
        assert task.is_labeled is False
        assert task.total_annotations == 6

    def test_exception_path_rolls_back(self):
        ts = _make_timer_session()

        class _BoomSession(_TimerFakeSession):
            def query(self, model):
                raise RuntimeError("db exploded")

        session = _BoomSession({})
        with patch.object(tasks_module, "HAS_DATABASE", True):
            with _patch_timer_session(session):
                out = auto_submit_expired_timer("ts-1")
        assert out["status"] == "error"
        assert "db exploded" in out["message"]
        assert session.rollbacks == 1
        assert session.closed is True


# ===========================================================================
# finalize_evaluation_run  (chord callback early-return branches)
# ===========================================================================


class _EvalFakeQuery:
    def __init__(self, first=None):
        self._first = first

    def filter(self, *a, **k):
        return self

    def first(self):
        return self._first


class _EvalFakeSession:
    def __init__(self, evaluation):
        self._evaluation = evaluation
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def query(self, model):
        return _EvalFakeQuery(first=self._evaluation)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


class TestFinalizeEvaluationRunEarlyReturns:
    def test_evaluation_not_found(self):
        session = _EvalFakeSession(evaluation=None)
        with patch.object(tasks_module, "SessionLocal", return_value=session):
            out = finalize_evaluation_run(None, "eval-missing")
        assert out == {"status": "skipped", "reason": "evaluation_not_found"}
        assert session.closed is True

    @pytest.mark.parametrize("terminal", ["completed", "failed", "cancelled"])
    def test_already_terminal_is_noop(self, terminal):
        ev = types.SimpleNamespace(id="eval-1", status=terminal)
        session = _EvalFakeSession(evaluation=ev)
        with patch.object(tasks_module, "SessionLocal", return_value=session):
            out = finalize_evaluation_run(None, "eval-1")
        assert out["status"] == "noop"
        assert out["reason"] == "already_terminal"
        assert out["current_status"] == terminal
        # No mutation/commit on a terminal re-entry.
        assert session.commits == 0
        assert session.closed is True
