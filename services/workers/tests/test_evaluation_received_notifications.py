"""Grading notifications from the workers (tasks.py).

- ``_resolve_notification_brand_host``: the soft extension hook (fake
  ``benger_extended.workers`` modules injected via ``sys.modules``, as in
  test_tasks_grading_policy_hooks.py).
- ``send_notification_batch_task``: brand and link per recipient.
- ``_notify_immediate_grading_received`` / ``_notify_batch_grading_received``:
  the two worker triggers, plus their wiring into ``finalize_evaluation_run``.
"""

import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

import tasks as tasks_module  # noqa: E402
from tasks import finalize_evaluation_run, send_notification_batch_task  # noqa: E402

pytest.importorskip("notification_service")
from mailer.branding import resolve_email_brand  # noqa: E402


@pytest.fixture
def fake_extended(monkeypatch):
    """Install an empty fake ``benger_extended.workers`` module."""
    pkg = types.ModuleType("benger_extended")
    mod = types.ModuleType("benger_extended.workers")
    pkg.workers = mod
    monkeypatch.setitem(sys.modules, "benger_extended", pkg)
    monkeypatch.setitem(sys.modules, "benger_extended.workers", mod)
    return mod


# ---------------------------------------------------------------------------
# _resolve_notification_brand_host
# ---------------------------------------------------------------------------


class TestResolveNotificationBrandHost:
    def test_community_edition_returns_none(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "benger_extended", None)
        monkeypatch.setitem(sys.modules, "benger_extended.workers", None)
        assert tasks_module._resolve_notification_brand_host(MagicMock(), None, "t", {}) is None

    def test_extended_without_the_hook_returns_none(self, fake_extended):
        assert tasks_module._resolve_notification_brand_host(MagicMock(), None, "t", {}) is None

    def test_hook_returning_no_function_returns_none(self, fake_extended):
        fake_extended.get_notification_brand_host_fn = lambda: None
        assert tasks_module._resolve_notification_brand_host(MagicMock(), None, "t", {}) is None

    def test_hook_result_is_passed_through(self, fake_extended):
        seen = {}

        def brand_host(db, user, notification_type, data):
            seen["args"] = (db, user, notification_type, data)
            return "vertretbar.net"

        fake_extended.get_notification_brand_host_fn = lambda: brand_host
        db, user = MagicMock(), types.SimpleNamespace(id="u1")
        data = {"project_id": "p1"}
        host = tasks_module._resolve_notification_brand_host(
            db, user, "evaluation_received_human", data
        )
        assert host == "vertretbar.net"
        assert seen["args"] == (db, user, "evaluation_received_human", data)

    def test_hook_crash_falls_back_to_none(self, fake_extended):
        def boom(*args):
            raise RuntimeError("db gone")

        fake_extended.get_notification_brand_host_fn = lambda: boom
        db = MagicMock()
        assert tasks_module._resolve_notification_brand_host(db, None, "t", {}) is None
        db.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# send_notification_batch_task: brand + link
# ---------------------------------------------------------------------------


class _FakeQuery:
    def __init__(self, first):
        self._first = first

    def filter(self, *a, **k):
        return self

    def first(self):
        return self._first


class _FakeSession:
    def __init__(self, user):
        self._user = user

    def query(self, model):
        return _FakeQuery(self._user)

    def rollback(self):
        pass

    def close(self):
        pass


def _student(preferred_ui_mode=None):
    return types.SimpleNamespace(
        id="u1",
        email="student@example.com",
        name="Student",
        preferred_ui_mode=preferred_ui_mode,
    )


def _send(notif, user, brand_host):
    """Run the batch for one recipient and capture the arguments the task
    hands to ``send_notification_email``. They are read off the coroutine
    passed to ``asyncio.run`` (a not-yet-started coroutine's frame holds its
    arguments), so nothing is sent and no coroutine is left unawaited."""
    captured = {}

    def fake_run(coro):
        captured.update(coro.cr_frame.f_locals)
        coro.close()
        return True

    session = _FakeSession(user)
    with patch.object(tasks_module, "SessionLocal", return_value=session), patch.object(
        tasks_module, "HAS_NOTIFICATION_SERVICE", False
    ), patch.object(
        tasks_module, "_resolve_notification_brand_host", return_value=brand_host
    ) as hook, patch("asyncio.run", side_effect=fake_run):
        out = send_notification_batch_task([notif])
    return out, captured, hook, session


def _grading(type_value="evaluation_received_human", kind="exam"):
    return {
        "id": "n1",
        "user_id": "u1",
        "type": type_value,
        "title": "New grading",
        "message": "m",
        "data": {"project_id": "p1", "project_kind": kind, "source": "human"},
    }


class TestNotificationBatchBranding:
    def test_vertretbar_member_gets_vertretbar_brand_and_student_link(self):
        notif = _grading()
        out, captured, hook, session = _send(notif, _student(), "vertretbar.net")
        assert out["sent"] == 1
        user = hook.call_args.args[1]
        assert hook.call_args.args == (session, user, "evaluation_received_human", notif["data"])
        brand = captured["brand"]
        expected = resolve_email_brand("vertretbar.net")
        assert brand == expected
        assert captured["context"]["action_url"] == (
            expected.frontend_url.rstrip("/") + "/student/exams/p1"
        )
        assert captured["context"]["user_name"] == "Student"

    def test_benger_annotator_gets_my_tasks_link(self):
        _, captured, _, _ = _send(_grading(), _student(), None)
        expected = resolve_email_brand(None)
        assert captured["brand"] == expected
        assert captured["context"]["action_url"] == (
            expected.frontend_url.rstrip("/") + "/projects/p1/my-tasks"
        )

    def test_student_mode_on_benger_links_to_the_exam_page(self):
        _, captured, _, _ = _send(_grading(), _student(preferred_ui_mode="student"), None)
        expected = resolve_email_brand(None)
        assert captured["brand"] == expected
        assert captured["context"]["action_url"] == (
            expected.frontend_url.rstrip("/") + "/student/exams/p1"
        )

    def test_other_types_get_no_link(self):
        notif = _grading(type_value="korrektur_assigned")
        _, captured, _, _ = _send(notif, _student(), None)
        assert "action_url" not in captured["context"]
        assert captured["brand"] == resolve_email_brand(None)


# ---------------------------------------------------------------------------
# Immediate grading trigger
# ---------------------------------------------------------------------------


def _db_with_row(has_row):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = ("te1",) if has_row else None
    return db


class TestImmediateGradingNotification:
    def test_notifies_the_annotator_when_the_run_wrote_rows(self):
        db = _db_with_row(True)
        with patch(
            "notification_service.annotator_ids_for_annotations", return_value=["student"]
        ) as annotators, patch("notification_service.notify_evaluation_received") as notify:
            tasks_module._notify_immediate_grading_received(db, "run1", "p1", "t1", "a1")
        annotators.assert_called_once_with(db, ["a1"])
        notify.assert_called_once_with(
            db,
            source="immediate",
            project_id="p1",
            recipient_ids=["student"],
            task_id="t1",
            evaluation_id="run1",
        )

    def test_run_without_rows_notifies_nobody(self):
        db = _db_with_row(False)
        with patch("notification_service.notify_evaluation_received") as notify:
            tasks_module._notify_immediate_grading_received(db, "run1", "p1", "t1", "a1")
        notify.assert_not_called()

    def test_no_annotation_skips_the_query(self):
        db = MagicMock()
        with patch("notification_service.notify_evaluation_received") as notify:
            tasks_module._notify_immediate_grading_received(db, "run1", "p1", "t1", None)
        db.query.assert_not_called()
        notify.assert_not_called()

    def test_failure_is_swallowed(self):
        db = _db_with_row(True)
        with patch(
            "notification_service.annotator_ids_for_annotations",
            side_effect=RuntimeError("boom"),
        ):
            tasks_module._notify_immediate_grading_received(db, "run1", "p1", "t1", "a1")


# ---------------------------------------------------------------------------
# Batch run trigger
# ---------------------------------------------------------------------------


def _evaluation(meta=None):
    return types.SimpleNamespace(
        id="run1",
        project_id="p1",
        eval_metadata={"triggered_by": "expert"} if meta is None else meta,
    )


class TestBatchGradingNotification:
    def test_marker_is_committed_before_notifying(self):
        db = MagicMock()
        db.execute.return_value.all.return_value = [("s2",), ("s1",), ("expert",)]
        order = []
        db.commit.side_effect = lambda: order.append("commit")
        evaluation = _evaluation()
        with patch("sqlalchemy.orm.attributes.flag_modified"), patch(
            "notification_service.notify_evaluation_received",
            side_effect=lambda *a, **k: order.append(("notify", a, k)),
        ):
            tasks_module._notify_batch_grading_received(db, evaluation)

        assert db.execute.call_args.args[1] == {"eid": "run1"}
        assert evaluation.eval_metadata == {"triggered_by": "expert", "annotators_notified": True}
        assert order[0] == "commit"
        _, args, kwargs = order[1]
        assert args == (db,)
        assert kwargs == {
            "source": "batch",
            "project_id": "p1",
            "recipient_ids": ["expert", "s1", "s2"],
            "exclude_user_ids": ["expert"],
            "evaluation_id": "run1",
        }

    def test_already_notified_run_is_skipped(self):
        db = MagicMock()
        with patch("notification_service.notify_evaluation_received") as notify:
            tasks_module._notify_batch_grading_received(
                db, _evaluation({"annotators_notified": True})
            )
        db.execute.assert_not_called()
        db.commit.assert_not_called()
        notify.assert_not_called()

    def test_run_without_annotations_sets_the_marker_only(self):
        db = MagicMock()
        db.execute.return_value.all.return_value = []
        evaluation = _evaluation()
        with patch("sqlalchemy.orm.attributes.flag_modified"), patch(
            "notification_service.notify_evaluation_received"
        ) as notify:
            tasks_module._notify_batch_grading_received(db, evaluation)
        assert evaluation.eval_metadata["annotators_notified"] is True
        db.commit.assert_called_once()
        notify.assert_not_called()

    def test_failure_is_swallowed_and_rolled_back(self):
        db = MagicMock()
        db.execute.side_effect = RuntimeError("db gone")
        tasks_module._notify_batch_grading_received(db, _evaluation())
        db.rollback.assert_called_once()


class TestFinalizeWiresTheBatchTrigger:
    def _finalize(self, any_child_completed):
        evaluation = types.SimpleNamespace(
            id="run1",
            project_id="p1",
            status="running",
            samples_evaluated=0,
            eval_metadata={},
            error_message=None,
            completed_at=None,
            metrics=None,
            has_sample_results=False,
        )
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = evaluation
        db.execute.return_value.all.return_value = []
        fake_report_service = types.ModuleType("report_service")
        fake_report_service.update_report_evaluation_section = lambda *a, **k: None
        with patch.object(tasks_module, "SessionLocal", return_value=db), patch.object(
            tasks_module,
            "_finalize_judge_runs_by_rows",
            return_value=(any_child_completed, not any_child_completed, []),
        ), patch.object(
            tasks_module, "_notify_batch_grading_received"
        ) as batch_trigger, patch(
            "sqlalchemy.orm.attributes.flag_modified"
        ), patch.dict(
            sys.modules, {"report_service": fake_report_service}
        ):
            out = finalize_evaluation_run(None, "run1")
        return out, batch_trigger, db, evaluation

    def test_completed_run_notifies_annotators(self):
        out, batch_trigger, db, evaluation = self._finalize(True)
        assert out["final_status"] == "completed"
        batch_trigger.assert_called_once_with(db, evaluation)

    def test_failed_run_notifies_nobody(self):
        out, batch_trigger, _, _ = self._finalize(False)
        assert out["final_status"] == "failed"
        batch_trigger.assert_not_called()


# ---------------------------------------------------------------------------
# run_single_sample_evaluation wires the immediate trigger
# ---------------------------------------------------------------------------


def _hooks_harness():
    """The fake-session harness of test_tasks_grading_policy_hooks.py, loaded
    by path so this module doesn't depend on how pytest names test modules."""
    import importlib.util

    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "test_tasks_grading_policy_hooks.py"
    )
    spec = importlib.util.spec_from_file_location("_grading_hooks_harness", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestRunSingleSampleEvaluationWiresTheImmediateTrigger:
    def test_successful_grading_notifies(self):
        harness = _hooks_harness()
        db = harness._fresh_db()
        with patch.dict(sys.modules, harness._fake_extended()), patch.object(
            tasks_module, "_notify_immediate_grading_received"
        ) as trigger:
            result = harness._run(db, harness._configs())
        assert result["status"] == "completed"
        trigger.assert_called_once_with(db, "eval-hook-1", "p1", "t1", "a1")

    def test_errored_job_notifies_nobody(self):
        harness = _hooks_harness()
        db = harness._fresh_db()

        def failing_job(**kwargs):
            return {"status": "error", "error": "judge exploded"}

        with patch.dict(sys.modules, harness._fake_extended()), patch.object(
            tasks_module, "SessionLocal", MagicMock(return_value=db)
        ), patch.object(
            tasks_module, "_run_immediate_config_job", side_effect=failing_job
        ), patch.object(
            tasks_module, "_notify_immediate_grading_received"
        ) as trigger:
            result = tasks_module.run_single_sample_evaluation.run(
                evaluation_record_id="eval-hook-1",
                project_id="p1",
                task_id="t1",
                annotation_id="a1",
                evaluation_configs=harness._configs(),
                annotation_results={"loesung": "meine lösung"},
                task_data={"musterloesung": "referenz"},
                organization_id=None,
                user_id="u1",
            )
        assert result["status"] == "completed"
        trigger.assert_not_called()
