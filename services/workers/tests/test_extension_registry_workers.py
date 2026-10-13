"""Worker-side behaviour of the N-package extension registry (core 2.37).

Fake ``<package>.workers`` modules are injected into ``sys.modules``, the
idiom the grading-policy, billing and notification tests already use, so the
suite runs in the platform image without any extension installed.
"""

import logging
import os
import sys
import types
from unittest.mock import MagicMock

import pytest

workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

import celery_queues  # noqa: E402
import extension_registry as registry  # noqa: E402
from core_version import CORE_API_VERSION  # noqa: E402


def _package(name, *, compatible=(CORE_API_VERSION,), **worker_attrs):
    pkg = types.ModuleType(name)
    pkg.__file__ = f"/fake/{name}/__init__.py"
    if compatible is not None:
        pkg.COMPATIBLE_CORE_VERSIONS = list(compatible)
    workers = types.ModuleType(f"{name}.workers")
    for attr, value in worker_attrs.items():
        setattr(workers, attr, value)
    pkg.workers = workers
    return pkg, workers


def _install(monkeypatch, *packages):
    for pkg, workers in packages:
        monkeypatch.setitem(sys.modules, pkg.__name__, pkg)
        monkeypatch.setitem(sys.modules, workers.__name__, workers)
    monkeypatch.setenv("BENGER_EXTENSIONS", ",".join(pkg.__name__ for pkg, _ in packages))


@pytest.fixture(autouse=True)
def _isolated_registry(monkeypatch):
    monkeypatch.delenv("BENGER_EXTENSIONS", raising=False)
    monkeypatch.delenv("BENGER_REQUIRE_EXTENSIONS", raising=False)
    monkeypatch.delenv("BENGER_REQUIRE_EXTENDED", raising=False)
    registry.reset()
    yield
    registry.reset()


@pytest.fixture
def isolated_task_queues(monkeypatch):
    monkeypatch.setattr(celery_queues, "TASK_QUEUES", dict(celery_queues.TASK_QUEUES))
    monkeypatch.setattr(
        celery_queues,
        "EXTENSION_REGISTERED_TASK_NAMES",
        set(celery_queues.EXTENSION_REGISTERED_TASK_NAMES),
    )
    monkeypatch.setattr(celery_queues, "_TASK_OWNERS", dict(celery_queues._TASK_OWNERS))


class TestWorkerAttrs:
    def test_resolves_lazily_in_configured_order(self, monkeypatch, caplog):
        a = _package("benger_extended", get_thing_fn=lambda: "ext-thing")
        b = _package("benger_two", get_thing_fn=lambda: "two-thing", get_other_fn=lambda: "two")
        _install(monkeypatch, a, b)
        # No load_all() call: the lookup works from sys.modules alone.
        assert [name for name, _ in registry.worker_attrs("get_thing_fn")] == [
            "benger_extended",
            "benger_two",
        ]
        assert registry.worker_attrs("get_other_fn")[0][0] == "benger_two"
        assert registry.worker_attrs("get_missing_fn") == []
        with caplog.at_level(logging.WARNING, logger="extension_registry"):
            assert registry.first_worker_attr("get_thing_fn", call=True) == "ext-thing"
        assert "get_thing_fn is provided by" in caplog.text
        assert registry.first_worker_attr("get_other_fn") is b[1].get_other_fn
        assert registry.first_worker_attr("get_missing_fn") is None
        assert registry.first_worker_attr("get_missing_fn", call=True) is None

    def test_missing_package_is_skipped(self, monkeypatch):
        monkeypatch.setenv("BENGER_EXTENSIONS", "benger_extended,benger_two")
        monkeypatch.setitem(sys.modules, "benger_extended", None)
        monkeypatch.setitem(sys.modules, "benger_extended.workers", None)
        b = _package("benger_two", get_thing_fn=lambda: "two")
        monkeypatch.setitem(sys.modules, "benger_two", b[0])
        monkeypatch.setitem(sys.modules, "benger_two.workers", b[1])
        assert registry.worker_attrs("get_thing_fn") == [("benger_two", b[1].get_thing_fn)]

    def test_rejected_package_is_skipped_but_an_absent_one_is_retried(self, monkeypatch):
        good = _package("benger_extended", get_thing_fn=lambda: "ext")
        bad = _package("benger_two", compatible=["0.0-nope"], get_thing_fn=lambda: "two")
        _install(monkeypatch, good, bad)
        monkeypatch.setenv("BENGER_EXTENSIONS", "benger_extended,benger_two,benger_late")
        monkeypatch.setitem(sys.modules, "benger_late", None)

        assert registry.loaded_names() == []
        assert [ext.name for ext in registry.load_all()] == ["benger_extended"]
        assert registry.rejected()["benger_two"].reason == "handshake"
        assert registry.rejected()["benger_late"].reason == "import"

        # The refused package never contributes; the absent one is looked up
        # again and found once a module appears (a test injecting a fake).
        assert [name for name, _ in registry.worker_attrs("get_thing_fn")] == ["benger_extended"]
        late = _package("benger_late", get_thing_fn=lambda: "late")
        monkeypatch.setitem(sys.modules, "benger_late", late[0])
        monkeypatch.setitem(sys.modules, "benger_late.workers", late[1])
        assert [name for name, _ in registry.worker_attrs("get_thing_fn")] == [
            "benger_extended",
            "benger_late",
        ]

    def test_worker_module_strict_mode(self, monkeypatch, tmp_path):
        # A real package on disk whose workers module has a broken import.
        pkg_dir = tmp_path / "benger_broken"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text("COMPATIBLE_CORE_VERSIONS = ['x']\n")
        (pkg_dir / "workers.py").write_text("import no_such_dependency_xyz\n")
        monkeypatch.syspath_prepend(str(tmp_path))
        for name in ("benger_broken", "benger_broken.workers"):
            monkeypatch.delitem(sys.modules, name, raising=False)

        assert registry.worker_module("benger_broken") is None
        with pytest.raises(ModuleNotFoundError, match="no_such_dependency_xyz"):
            registry.worker_module("benger_broken", strict=True)

        # A package without a workers module is answered with None in both modes.
        only = types.ModuleType("benger_only")
        only.__file__ = "/fake/benger_only/__init__.py"
        monkeypatch.setitem(sys.modules, "benger_only", only)
        monkeypatch.setitem(sys.modules, "benger_only.workers", None)
        assert registry.worker_module("benger_only") is None
        assert registry.worker_module("benger_only", strict=True) is None


class TestOwnership:
    def test_owner_context_nests(self):
        assert registry.current_owner() is None
        with registry.owner("benger_a"):
            assert registry.current_owner() == "benger_a"
            with registry.owner("benger_b"):
                assert registry.current_owner() == "benger_b"
            assert registry.current_owner() == "benger_a"
        assert registry.current_owner() is None
        assert registry.describe_owner(None) == "the platform"

    def test_metric_registry_records_and_reports_the_owner(self, caplog):
        from ml_evaluation.handlers import MetricHandler, MetricRegistry

        class _H(MetricHandler):
            name = "owned_metric"

            def compute(self, ground_truth, prediction, answer_type, parameters=None):
                return {}

        reg = MetricRegistry()
        with registry.owner("benger_a"):
            reg.register(_H())
        assert reg.owner("owned_metric") == "benger_a"
        with caplog.at_level(logging.WARNING, logger="ml_evaluation.handlers"):
            with registry.owner("benger_b"):
                reg.register(_H())
        assert "registered by benger_b replaces benger_a's" in caplog.text
        assert reg.owner("owned_metric") == "benger_b"
        assert reg.owner("unknown") is None

    def test_evaluator_registry_records_and_reports_the_owner(self, caplog):
        from ml_evaluation.base_evaluator import BaseEvaluator
        from ml_evaluation.registry import EvaluatorRegistry

        class _E(BaseEvaluator):
            def evaluate(self, *args, **kwargs):  # pragma: no cover - never called
                return None

        reg = EvaluatorRegistry()
        with registry.owner("benger_a"):
            reg.register("owned_type", _E)
        assert reg.owner("owned_type") == "benger_a"
        with caplog.at_level(logging.WARNING, logger="ml_evaluation.registry"):
            reg.register("owned_type", _E)
        assert "registered by the platform replaces benger_a's" in caplog.text
        assert reg.owner("owned_type") is None

    def test_classifier_rules_record_the_owner(self, caplog):
        import eval_field_classification as efc

        rule = lambda fields: (list(fields), [])  # noqa: E731
        try:
            with registry.owner("benger_a"):
                efc.register_classifier_rule("owned_rule_metric", rule)
            assert efc._RULE_OWNERS["owned_rule_metric"] == "benger_a"
            with caplog.at_level(logging.WARNING, logger="eval_field_classification"):
                with registry.owner("benger_b"):
                    efc.register_classifier_rule("owned_rule_metric", rule)
            assert "registered by benger_b replaces benger_a's" in caplog.text
            # Same owner again: an idempotent reload, nothing to report.
            caplog.clear()
            with registry.owner("benger_b"):
                efc.register_classifier_rule("owned_rule_metric", rule)
            assert "replaces" not in caplog.text
        finally:
            efc._RULES.pop("owned_rule_metric", None)
            efc._RULE_OWNERS.pop("owned_rule_metric", None)


class TestTaskQueueRegistration:
    def test_register_task_queue_tracks_ownership(self, isolated_task_queues):
        celery_queues.register_task_queue("ownx.run", "interactive", owner="benger_a")
        assert celery_queues.TASK_QUEUES["ownx.run"] == "interactive"
        assert celery_queues.task_owner("ownx.run") == "benger_a"
        assert "ownx.run" in celery_queues.EXTENSION_REGISTERED_TASK_NAMES
        # The same owner may re-register (reload); another may not.
        celery_queues.register_task_queue("ownx.run", "evaluation", owner="benger_a")
        assert celery_queues.TASK_QUEUES["ownx.run"] == "evaluation"
        with pytest.raises(ValueError, match="routed by 'benger_a'"):
            celery_queues.register_task_queue("ownx.run", "bulk", owner="benger_b")
        assert celery_queues.TASK_QUEUES["ownx.run"] == "evaluation"
        # Ownerless calls (platform code, tests) keep working.
        celery_queues.register_task_queue("ownx.run", "bulk")
        assert celery_queues.TASK_QUEUES["ownx.run"] == "bulk"
        assert celery_queues.task_owner("ownx.run") == "benger_a"
        with pytest.raises(ValueError, match="not a declared queue"):
            celery_queues.register_task_queue("ownx.other", "nope", owner="benger_a")

    def test_load_all_feeds_get_task_queues_with_the_owner(
        self, monkeypatch, isolated_task_queues
    ):
        pkg, workers = _package("benger_comp")
        pkg.EXTENSION_ID = "comp"
        pkg.get_task_queues = lambda: {"comp.run_suite": "evaluation"}
        _install(monkeypatch, (pkg, workers))
        assert [ext.short for ext in registry.load_all()] == ["comp"]
        assert celery_queues.TASK_QUEUES["comp.run_suite"] == "evaluation"
        assert celery_queues.task_owner("comp.run_suite") == "benger_comp"
        assert celery_queues.queue_for("comp.run_suite") == "evaluation"

    def test_a_second_package_may_not_take_over_a_routed_task(
        self, monkeypatch, isolated_task_queues, caplog
    ):
        first, w1 = _package("benger_one")
        first.get_task_queues = lambda: {"one.job": "interactive"}
        second, w2 = _package("benger_two")
        second.get_task_queues = lambda: {"one.job": "bulk"}
        _install(monkeypatch, (first, w1), (second, w2))
        with caplog.at_level(logging.ERROR, logger="extension_registry"):
            assert registry.loaded_names() == [] and len(registry.load_all()) == 2
        assert celery_queues.TASK_QUEUES["one.job"] == "interactive"
        assert "get_task_queues() ignored" in caplog.text


class TestWorkerEntryPoints:
    def test_tasks_bootstrap_uses_the_registry(self):
        import tasks

        assert tasks._extension_registry is registry

    def test_grading_dispatch_policy_comes_from_the_first_package(self, monkeypatch):
        import tasks

        policy_a = object()
        policy_b = object()
        a = _package("benger_extended", get_grading_dispatch_policy_fn=lambda: policy_a)
        b = _package("benger_two", get_grading_dispatch_policy_fn=lambda: policy_b)
        _install(monkeypatch, b, a)
        assert tasks._get_grading_dispatch_policy_fn() is policy_b
        assert tasks._get_batch_evaluation_policy_fn() is None

    def test_grading_finalize_runs_every_package_isolated(self, monkeypatch):
        import tasks

        seen = []

        def boom(run_id, success):
            raise RuntimeError("ledger down")

        a = _package("benger_extended", get_grading_finalize_fn=lambda: boom)
        b = _package(
            "benger_two", get_grading_finalize_fn=lambda: lambda r, s: seen.append((r, s))
        )
        _install(monkeypatch, a, b)
        monkeypatch.setattr(tasks, "logger", MagicMock())
        tasks._run_grading_finalize_hook("run-1", True)
        assert seen == [("run-1", True)]
        tasks.logger.error.assert_called_once()

    def test_notification_brand_host_first_answer_wins(self, monkeypatch):
        import tasks

        a = _package("benger_extended", get_notification_brand_host_fn=lambda: lambda *a: None)
        b = _package(
            "benger_two", get_notification_brand_host_fn=lambda: lambda *a: "vertretbar.net"
        )
        c = _package("benger_three", get_notification_brand_host_fn=lambda: lambda *a: "late")
        _install(monkeypatch, a, b, c)
        db = MagicMock()
        assert tasks._resolve_notification_brand_host(db, None, "t", {}) == "vertretbar.net"
        db.rollback.assert_not_called()

    def test_grading_block_first_block_wins_each_in_a_savepoint(self, monkeypatch):
        import immediate_eval_dispatch as ied

        a = _package(
            "benger_extended", get_grading_block_fn=lambda: lambda db, **kw: None
        )
        b = _package(
            "benger_two", get_grading_block_fn=lambda: lambda db, **kw: "org_not_paying"
        )
        c = _package(
            "benger_three", get_grading_block_fn=lambda: lambda db, **kw: {"reason": "late"}
        )
        _install(monkeypatch, a, b, c)
        db = MagicMock()
        block = ied._grading_block(db, project=None, user_id="u", configs=[])
        assert block == {"reason": "org_not_paying"}
        assert db.begin_nested.call_count == 2

    def test_grading_block_skips_a_failing_package(self, monkeypatch):
        import immediate_eval_dispatch as ied

        def boom(db, **kw):
            raise RuntimeError("policy down")

        a = _package("benger_extended", get_grading_block_fn=lambda: boom)
        b = _package("benger_two", get_grading_block_fn=lambda: lambda db, **kw: None)
        _install(monkeypatch, a, b)
        assert ied._grading_block(MagicMock(), project=None, user_id="u", configs=[]) is None
