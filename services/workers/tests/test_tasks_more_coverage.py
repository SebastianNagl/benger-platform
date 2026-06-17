"""Additional behavioral coverage for worker helpers + tasks in tasks.py.

Targets handler/helper logic NOT already exercised by the existing green
suites (``test_tasks_handlers_coverage.py``, ``test_tasks_deep_coverage.py``,
``test_param_resolution.py``, ``test_progress_pubsub.py``,
``test_missing_only_dict_shape.py`` — note the last one tests a *local mirror*
of ``_row_has_score``, not the real function, so the real one is exercised
here):

- ``_row_has_score`` — the REAL tasks.py predicate (bare float / {value: …}
  dict / bool-skip / error-skip branches).
- ``_clamp_temperature_to_constraint`` — the one remaining branch
  test_param_resolution.py doesn't hit: ``temperature`` sub-config not a dict.
- ``cleanup_project_data`` — error path + the TESTING-env redis URL branch.
- ``send_bulk_invitations_task`` — per-invitation apply_async fan-out
  (queued + failed-to-queue counts, progressive countdown).
- ``send_notification_batch_task`` — empty-guard, skip (no user / no email /
  invalid email / channel opt-out), sent/failed counts, return shape.
- ``_reconstruct_judge_evaluators_for_cell`` — non-judge-config skip, success
  entry shape, init-failure (evaluator=None) handling, first-evaluator capture.
- ``_build_sample_evaluator_for_cell`` — the field_key / metric_parameters
  construction (asserted on the captured SampleEvaluator constructor args).
- ``recompute_aggregates`` — redis-lock-not-acquired skip, lock-acquired
  success, inner-exception error, redis-unavailable proceed-without-dedup.
- ``update_report_annotations_async`` — lock-not-acquired follower (pending
  flag set), leader success, compute exception, tail re-enqueue on pending.

Mirrors the existing workers-test idioms exactly: ``MagicMock`` db sessions,
``patch.object(tasks_module, "SessionLocal", …)``, celery tasks called
DIRECTLY (bind=True tasks get a MagicMock ``self``), and a module-state reset
fixture for the lazy redis client (as in test_progress_pubsub.py).
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
    _build_sample_evaluator_for_cell,
    _clamp_temperature_to_constraint,
    _reconstruct_judge_evaluators_for_cell,
    _row_has_score,
    cleanup_project_data,
    recompute_aggregates,
    send_bulk_invitations_task,
    send_notification_batch_task,
    update_report_annotations_async,
)


@pytest.fixture(autouse=True)
def _reset_progress_client():
    """Some helpers cache a lazy redis client on the module; reset it so
    mocks from one test don't leak into the next (idiom from
    test_progress_pubsub.py)."""
    tasks_module._progress_redis_client = None
    yield
    tasks_module._progress_redis_client = None


# ===========================================================================
# _row_has_score  (the REAL tasks.py function — the existing suite only tests
# a local mirror copy in test_missing_only_dict_shape.py)
# ===========================================================================


class TestRowHasScoreReal:
    def test_none_and_empty_are_false(self):
        assert _row_has_score(None) is False
        assert _row_has_score({}) is False

    def test_bare_numeric_value_is_true(self):
        assert _row_has_score({"rouge": 0.5}) is True
        assert _row_has_score({"count": 3}) is True

    def test_bool_value_is_skipped(self):
        # A bare bool must NOT count as a numeric score (it's a flag, not a
        # metric value) — otherwise a {"passed": True} row reads as evaluated.
        assert _row_has_score({"passed": True}) is False
        assert _row_has_score({"flag": False}) is False

    def test_error_key_is_skipped(self):
        # The top-level "error" key is ignored; with no other numeric metric
        # the row is "missing".
        assert _row_has_score({"error": "boom"}) is False

    def test_unified_dict_with_numeric_value_is_true(self):
        assert _row_has_score({"bleu": {"value": 0.8, "error": None}}) is True

    def test_unified_dict_with_none_value_is_false(self):
        assert _row_has_score({"bleu": {"value": None, "error": "x"}}) is False

    def test_unified_dict_with_bool_value_is_false(self):
        # value is a bool inside the dict → still skipped.
        assert _row_has_score({"bleu": {"value": True}}) is False

    def test_mixed_error_plus_real_score_is_true(self):
        assert _row_has_score({"error": "ignored", "rouge": {"value": 0.1}}) is True


# ===========================================================================
# _clamp_temperature_to_constraint — the remaining branch:
# the "temperature" sub-config is present but not a dict.
# ===========================================================================


class TestClampTempConfigNotDict:
    def test_temperature_subconfig_not_a_dict_passes_through(self):
        # `parameter_constraints["temperature"]` is a string, not a dict →
        # treated as "no constraints"; value unchanged, no clamp recorded.
        constraints = {"temperature": "not-a-dict"}
        assert _clamp_temperature_to_constraint(0.42, constraints) == (0.42, None)

    def test_temperature_subconfig_missing_falls_to_range_passthrough(self):
        # No "temperature" key → `.get(...) or {}` yields an empty dict, the
        # supported-default True path with no min/max → unchanged.
        assert _clamp_temperature_to_constraint(0.3, {"max_tokens": {}}) == (0.3, None)


# ===========================================================================
# cleanup_project_data  (redis task — error path + TESTING-env URL branch)
# ===========================================================================


class TestCleanupProjectData:
    def test_success_sums_deleted_keys(self, monkeypatch):
        monkeypatch.setenv("TESTING", "true")
        fake_client = MagicMock()
        fake_client.delete.return_value = 1  # each key deletes one
        with patch.object(tasks_module.redis, "from_url", return_value=fake_client) as from_url:
            out = cleanup_project_data("proj-7")
        assert out == {"status": "success", "project_id": "proj-7", "deleted_keys": 2}
        # TESTING=true → db=1 test redis URL
        from_url.assert_called_once_with("redis://localhost:6379/1")
        # Both the new and legacy key formats are deleted.
        fake_client.delete.assert_any_call("project:proj-7")
        fake_client.delete.assert_any_call("task:proj-7")

    def test_uses_redis_url_env_when_not_testing(self, monkeypatch):
        monkeypatch.delenv("TESTING", raising=False)
        monkeypatch.setenv("REDIS_URL", "redis://custom:6379/5")
        fake_client = MagicMock()
        fake_client.delete.return_value = 0
        with patch.object(tasks_module.redis, "from_url", return_value=fake_client) as from_url:
            out = cleanup_project_data("p1")
        assert out["deleted_keys"] == 0
        from_url.assert_called_once_with("redis://custom:6379/5")

    def test_error_path_returns_error_dict(self, monkeypatch):
        monkeypatch.setenv("TESTING", "true")
        with patch.object(
            tasks_module.redis, "from_url", side_effect=RuntimeError("redis down")
        ):
            out = cleanup_project_data("p2")
        assert out["status"] == "error"
        assert out["project_id"] == "p2"
        assert "redis down" in out["message"]


# ===========================================================================
# send_bulk_invitations_task  (fan-out via apply_async)
# ===========================================================================


class TestSendBulkInvitations:
    def test_empty_list_returns_zeroed_stats(self):
        out = send_bulk_invitations_task([])
        assert out == {"sent": 0, "failed": 0, "total": 0, "results": []}

    def test_queues_each_with_progressive_countdown(self):
        invitations = [
            {
                "invitation_id": "i1",
                "to_email": "a@example.com",
                "inviter_name": "Inviter",
                "organization_name": "Org",
                "invitation_url": "https://x/1",
                "role": "annotator",
            },
            {
                "invitation_id": "i2",
                "to_email": "b@example.com",
                "inviter_name": "Inviter",
                "organization_name": "Org",
                "invitation_url": "https://x/2",
                "role": "contributor",
            },
        ]
        fake_async_result = MagicMock()
        fake_async_result.id = "task-xyz"
        with patch.object(
            tasks_module.send_invitation_email_task,
            "apply_async",
            return_value=fake_async_result,
        ) as apply_async:
            out = send_bulk_invitations_task(invitations)

        assert out["sent"] == 2
        assert out["failed"] == 0
        assert out["total"] == 2
        assert all(r["status"] == "queued" and r["task_id"] == "task-xyz" for r in out["results"])
        # Progressive 2s spacing: idx 0 → 0, idx 1 → 2.
        countdowns = [c.kwargs["countdown"] for c in apply_async.call_args_list]
        assert countdowns == [0, 2]
        # The 6 positional invite fields are forwarded in order.
        first_args = apply_async.call_args_list[0].kwargs["args"]
        assert first_args == ["i1", "a@example.com", "Inviter", "Org", "https://x/1", "annotator"]

    def test_failed_to_queue_counted_separately(self):
        invitations = [
            {"to_email": "a@example.com"},
            {"to_email": "b@example.com"},
        ]
        ok = MagicMock()
        ok.id = "t1"
        with patch.object(
            tasks_module.send_invitation_email_task,
            "apply_async",
            side_effect=[ok, RuntimeError("broker down")],
        ):
            out = send_bulk_invitations_task(invitations)
        assert out["sent"] == 1
        assert out["failed"] == 1
        assert out["total"] == 2
        statuses = {r["email"]: r["status"] for r in out["results"]}
        assert statuses["a@example.com"] == "queued"
        assert statuses["b@example.com"] == "failed"
        failed_entry = next(r for r in out["results"] if r["status"] == "failed")
        assert "broker down" in failed_entry["error"]


# ===========================================================================
# send_notification_batch_task  (DB + SendGrid batch)
# ===========================================================================


class _NotifFakeQuery:
    def __init__(self, first=None):
        self._first = first

    def filter(self, *a, **k):
        return self

    def first(self):
        return self._first


class _NotifFakeSession:
    """Serves the User query by call order so each notification in the batch
    can resolve a different user."""

    def __init__(self, users):
        self._users = list(users)
        self._i = 0
        self.closed = False

    def query(self, model):
        # Only User is queried in this task.
        user = self._users[self._i] if self._i < len(self._users) else None
        self._i += 1
        return _NotifFakeQuery(first=user)

    def close(self):
        self.closed = True


def _user(uid="u1", email="user@example.com"):
    return types.SimpleNamespace(id=uid, email=email, name="Name")


class TestSendNotificationBatch:
    def test_empty_list_short_circuits(self):
        # No DB session created, no "total" key (the early-guard shape).
        out = send_notification_batch_task([])
        assert out == {"sent": 0, "failed": 0, "skipped": 0}

    def test_skips_missing_user_and_missing_email(self):
        session = _NotifFakeSession([None, _user(email=None)])
        data = [{"user_id": "ghost", "type": "x"}, {"user_id": "u2", "type": "x"}]
        with patch.object(tasks_module, "SessionLocal", return_value=session):
            out = send_notification_batch_task(data)
        assert out["skipped"] == 2
        assert out["sent"] == 0
        assert out["failed"] == 0
        assert out["total"] == 2
        assert session.closed is True

    def test_skips_invalid_email(self):
        session = _NotifFakeSession([_user(email="not-an-email")])
        data = [{"user_id": "u1", "type": "x"}]
        with patch.object(tasks_module, "SessionLocal", return_value=session):
            out = send_notification_batch_task(data)
        # "not-an-email" has no @ → invalid → skipped (the inline fallback
        # validator requires both "@" and ".").
        assert out["skipped"] == 1

    def test_channel_opt_out_skips(self):
        if not hasattr(tasks_module.NotificationService, "_user_wants_channel"):
            pytest.skip("real NotificationService not loaded in this env")
        session = _NotifFakeSession([_user()])
        data = [{"user_id": "u1", "type": "project_created"}]
        with patch.object(tasks_module, "SessionLocal", return_value=session), patch.object(
            tasks_module, "HAS_NOTIFICATION_SERVICE", True
        ), patch.object(
            tasks_module.NotificationService, "_user_wants_channel", return_value=False
        ):
            out = send_notification_batch_task(data)
        assert out["skipped"] == 1
        assert out["sent"] == 0

    def test_sent_and_failed_counts(self):
        session = _NotifFakeSession([_user("a"), _user("b")])
        data = [
            {"user_id": "a", "type": "t", "title": "T", "message": "M"},
            {"user_id": "b", "type": "t", "title": "T", "message": "M"},
        ]
        # `from email_service import email_service` resolves to the module
        # conftest force-loaded into sys.modules; patch its instance method.
        # The task wraps the call in `asyncio.run(...)`, so the patched
        # send_notification_email just needs to return a (dummy) awaitable-free
        # value — we patch `asyncio.run` to yield our True/False results and
        # absorb the coroutine arg so no "never awaited" warning fires.
        import email_service as email_service_module

        results = iter([True, False])

        def fake_run(coro):
            # Close the coroutine to avoid a RuntimeWarning, then return the
            # next staged result.
            try:
                coro.close()
            except Exception:
                pass
            return next(results)

        async def _fake_send(**kwargs):
            return True

        with patch.object(tasks_module, "SessionLocal", return_value=session), patch.object(
            tasks_module, "HAS_NOTIFICATION_SERVICE", False
        ), patch.object(
            email_service_module.email_service,
            "send_notification_email",
            side_effect=_fake_send,
        ), patch("asyncio.run", side_effect=fake_run):
            out = send_notification_batch_task(data)
        assert out["sent"] == 1
        assert out["failed"] == 1
        assert out["skipped"] == 0
        assert out["total"] == 2


# ===========================================================================
# _reconstruct_judge_evaluators_for_cell
# ===========================================================================


class TestReconstructJudgeEvaluators:
    def test_non_judge_configs_are_skipped(self):
        configs = [{"id": "c1", "metric": "bleu"}, {"id": "c2", "metric": "rouge"}]
        runs, evaluators = _reconstruct_judge_evaluators_for_cell(
            configs_for_cell=configs,
            judge_run_ids_by_config={},
            triggered_by_user_id="u1",
            organization_id=None,
            db=MagicMock(),
        )
        assert runs == {}
        assert evaluators == {}

    def test_success_builds_entries_and_captures_first_evaluator(self):
        configs = [{"id": "cfg-1", "metric": "llm_judge_classic"}]
        run_ids = {
            "cfg-1": [
                {
                    "judge_model_id": "gpt-x",
                    "run_index": 0,
                    "judge_run_id": "jr-0",
                    "judge_evaluator_kwargs": {"judge_model": "gpt-x", "provider": "openai"},
                },
                {
                    "judge_model_id": "gpt-x",
                    "run_index": 1,
                    "judge_run_id": "jr-1",
                    "judge_evaluator_kwargs": {"judge_model": "gpt-x", "provider": "openai"},
                },
            ]
        }
        sentinel_evaluator = MagicMock(name="evaluator")
        # create_llm_judge_for_user is imported INSIDE the function from
        # ml_evaluation.llm_judge_evaluator — patch it at its source module.
        with patch(
            "ml_evaluation.llm_judge_evaluator.create_llm_judge_for_user",
            return_value=sentinel_evaluator,
        ) as create:
            runs, evaluators = _reconstruct_judge_evaluators_for_cell(
                configs_for_cell=configs,
                judge_run_ids_by_config=run_ids,
                triggered_by_user_id="user-9",
                organization_id="org-3",
                db="db-handle",
            )
        # Two run entries, each carrying the full dict shape.
        assert len(runs["cfg-1"]) == 2
        first = runs["cfg-1"][0]
        assert first["judge_model_id"] == "gpt-x"
        assert first["run_index"] == 0
        assert first["judge_run_id"] == "jr-0"
        assert first["evaluator"] is sentinel_evaluator
        # First initialized evaluator captured into the scalar map.
        assert evaluators["cfg-1"] is sentinel_evaluator
        # Construction kwargs splatted; db / user / org forwarded.
        _, kwargs = create.call_args_list[0]
        assert kwargs["db"] == "db-handle"
        assert kwargs["user_id"] == "user-9"
        assert kwargs["organization_id"] == "org-3"
        assert kwargs["judge_model"] == "gpt-x"
        assert kwargs["provider"] == "openai"

    def test_init_failure_yields_none_evaluator(self):
        configs = [{"id": "cfg-2", "metric": "llm_judge_custom"}]
        run_ids = {
            "cfg-2": [
                {
                    "judge_model_id": "m",
                    "run_index": 0,
                    "judge_run_id": "jr",
                    "judge_evaluator_kwargs": {},
                }
            ]
        }
        with patch(
            "ml_evaluation.llm_judge_evaluator.create_llm_judge_for_user",
            side_effect=RuntimeError("no api key"),
        ):
            runs, evaluators = _reconstruct_judge_evaluators_for_cell(
                configs_for_cell=configs,
                judge_run_ids_by_config=run_ids,
                triggered_by_user_id="u",
                organization_id=None,
                db=MagicMock(),
            )
        assert runs["cfg-2"][0]["evaluator"] is None
        # No evaluator captured when init failed.
        assert "cfg-2" not in evaluators


# ===========================================================================
# _build_sample_evaluator_for_cell
# ===========================================================================


class TestBuildSampleEvaluatorForCell:
    def test_field_key_and_metric_parameters_construction(self):
        configs = [
            {
                "id": "cfg-A",
                "metric": "rouge",
                "metric_parameters": {"threshold": 0.5},
                "prediction_fields": ["pred1", "pred2"],
                "reference_fields": ["ref1"],
            },
            {
                # No metric_parameters → field_configs gets the keys but
                # metric_parameters stays empty for these field_keys.
                "id": "cfg-B",
                "metric": "bleu",
                "prediction_fields": ["p"],
                "reference_fields": ["r"],
            },
        ]
        captured = {}

        def fake_ctor(evaluation_id, field_configs, metric_parameters):
            captured["evaluation_id"] = evaluation_id
            captured["field_configs"] = field_configs
            captured["metric_parameters"] = metric_parameters
            return MagicMock(name="SampleEvaluator")

        with patch("ml_evaluation.sample_evaluator.SampleEvaluator", side_effect=fake_ctor):
            _build_sample_evaluator_for_cell("eval-77", configs)

        assert captured["evaluation_id"] == "eval-77"
        # field_key = "{config_id}|{pred}|{ref}" for the cartesian product.
        assert set(captured["field_configs"].keys()) == {
            "cfg-A|pred1|ref1",
            "cfg-A|pred2|ref1",
            "cfg-B|p|r",
        }
        assert captured["field_configs"]["cfg-A|pred1|ref1"] == {"type": "text"}
        # metric_parameters only written when params truthy (cfg-A), keyed
        # by field_key → {metric: params}.
        assert captured["metric_parameters"] == {
            "cfg-A|pred1|ref1": {"rouge": {"threshold": 0.5}},
            "cfg-A|pred2|ref1": {"rouge": {"threshold": 0.5}},
        }
        # cfg-B (no params) absent from metric_parameters.
        assert "cfg-B|p|r" not in captured["metric_parameters"]

    def test_missing_id_defaults_to_unknown(self):
        configs = [
            {"metric": "bleu", "prediction_fields": ["p"], "reference_fields": ["r"]}
        ]
        captured = {}

        def fake_ctor(evaluation_id, field_configs, metric_parameters):
            captured["field_configs"] = field_configs
            return MagicMock()

        with patch("ml_evaluation.sample_evaluator.SampleEvaluator", side_effect=fake_ctor):
            _build_sample_evaluator_for_cell("e", configs)
        assert "unknown|p|r" in captured["field_configs"]


# ===========================================================================
# recompute_aggregates  (bind=True → MagicMock self)
# ===========================================================================


def _patch_aggregate_module():
    """Inject a fake `aggregate_summaries` module so the task's local import
    resolves without pulling the real (DB-heavy) recompute functions."""
    fake = types.ModuleType("aggregate_summaries")
    fake.recompute_project_summaries = MagicMock(return_value=4)
    fake.recompute_llm_leaderboard_scores = MagicMock(return_value=7)
    return patch.dict(sys.modules, {"aggregate_summaries": fake})


# ===========================================================================
# update_report_annotations_async  (bind=True → MagicMock self)
# ===========================================================================


def _patch_report_service():
    fake = types.ModuleType("report_service")
    fake.update_report_annotations_section = MagicMock()
    return patch.dict(sys.modules, {"report_service": fake})


