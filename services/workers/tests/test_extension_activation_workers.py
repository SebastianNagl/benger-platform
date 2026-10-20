"""Worker side of the runtime extension switch (core 2.42): the task
context from the ``benger_ext_ctx`` header, the master flags registered in
the worker, gated worker getters and metric handlers of inactive packages.
"""

import os
import sys
import types
from unittest.mock import patch

import pytest

workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

import extension_activation as activation  # noqa: E402
import extension_registry as registry  # noqa: E402
from core_version import CORE_API_VERSION  # noqa: E402
from feature_flags import registry as flag_registry  # noqa: E402
from feature_flags import service  # noqa: E402

PKG = "benger_wfake"
MASTER = "extension.wfake"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    for var in ("BENGER_EXTENSIONS", "BENGER_REQUIRE_EXTENSIONS", "BENGER_REQUIRE_EXTENDED"):
        monkeypatch.delenv(var, raising=False)
    registry.reset()
    yield
    registry.reset()
    flag_registry.unregister_flags(PKG)
    flag_registry.reset_master_flags()


def _snapshot(state, users=()):
    return patch.object(
        service,
        "cache_get",
        lambda: {MASTER: {"state": state, "users": list(users), "orgs": []}},
    )


def _install(monkeypatch, **worker_attrs):
    pkg = types.ModuleType(PKG)
    pkg.__file__ = f"/fake/{PKG}/__init__.py"
    pkg.COMPATIBLE_CORE_VERSIONS = [CORE_API_VERSION]
    pkg.EXTENSION_ID = "wfake"
    workers = types.ModuleType(f"{PKG}.workers")
    for attr, value in worker_attrs.items():
        setattr(workers, attr, value)
    monkeypatch.setitem(sys.modules, PKG, pkg)
    monkeypatch.setitem(sys.modules, f"{PKG}.workers", workers)
    monkeypatch.setenv("BENGER_EXTENSIONS", PKG)
    # An earlier import (ml_evaluation) may already have run load_all().
    registry.reset()
    loaded = registry.load_all()
    assert [ext.name for ext in loaded] == [PKG]
    activation.register_master_flags(loaded)
    return pkg, workers


def test_master_flags_register_in_the_worker(monkeypatch):
    _install(monkeypatch)
    assert flag_registry.master_for_owner(PKG) == MASTER
    assert flag_registry.flag(MASTER).default_state == "off"


def test_prerun_and_postrun_set_and_reset_the_context():
    from worker_celery import _reset_extension_context, _set_extension_context

    request = types.SimpleNamespace(
        **{activation.CELERY_HEADER: {"user_id": "u1", "project_id": "p1"}}
    )
    task = types.SimpleNamespace(request=request)
    before = activation.current_context()
    _set_extension_context(task_id="t-1", task=task, args=(), kwargs={})
    try:
        ctx = activation.current_context()
        assert (ctx.user_id, ctx.project_id, ctx.kind) == ("u1", "p1", activation.KIND_TASK)
    finally:
        _reset_extension_context(task_id="t-1")
    after = activation.current_context()
    assert after.user_id == before.user_id is None


def test_prerun_falls_back_to_kwargs_and_system():
    from worker_celery import _reset_extension_context, _set_extension_context

    task = types.SimpleNamespace(request=types.SimpleNamespace())
    _set_extension_context(task_id="t-2", task=task, kwargs={"user_id": "u9"})
    try:
        assert activation.current_context().user_id == "u9"
    finally:
        _reset_extension_context(task_id="t-2")
    _set_extension_context(task_id="t-3", task=task, kwargs={})
    try:
        assert activation.current_context().kind == activation.KIND_SYSTEM
    finally:
        _reset_extension_context(task_id="t-3")


def test_gated_getters_follow_the_task_context(monkeypatch):
    _install(
        monkeypatch,
        get_grading_finalize_fn=lambda: "finalize",
        get_notification_brand_host_fn=lambda: "brand",
    )
    with _snapshot("allowlist", users=["u1"]):
        with activation.use_context(user_id="u2", inherit=False):
            assert registry.worker_attrs("get_notification_brand_host_fn") == []
            # Settlement keeps running for an inactive package.
            assert [n for n, _ in registry.worker_attrs("get_grading_finalize_fn")] == [PKG]
        with activation.use_context(user_id="u1", inherit=False):
            assert [n for n, _ in registry.worker_attrs("get_notification_brand_host_fn")] == [PKG]


def test_metric_handlers_of_inactive_packages_do_not_run(monkeypatch):
    from ml_evaluation.handlers import MetricHandler, MetricRegistry

    _install(monkeypatch)

    class FakeHandler(MetricHandler):
        name = "wfake_metric"

        def compute(self, *args, **kwargs):  # pragma: no cover - must not run
            raise AssertionError("ran while the package is off")

    metrics = MetricRegistry()
    with registry.owner(PKG):
        metrics.register(FakeHandler())
    with _snapshot("off"):
        with activation.use_context(user_id="u1", inherit=False):
            result = metrics.disabled_result("wfake_metric")
            assert result["error"] == "feature_disabled"
            assert result["details"]["flag"] == MASTER
            with pytest.raises(activation.ExtensionInactive):
                metrics.ensure_owner_active("wfake_metric")
    with _snapshot("everyone"):
        with activation.use_context(user_id="u1", inherit=False):
            assert metrics.disabled_result("wfake_metric") is None


def test_sample_evaluator_records_feature_disabled(monkeypatch):
    import ml_evaluation
    from ml_evaluation.handlers import MetricHandler
    from ml_evaluation.sample_evaluator import SampleEvaluator

    _install(monkeypatch)

    class FakeHandler(MetricHandler):
        name = "wfake_metric_eval"

        def compute(self, *args, **kwargs):  # pragma: no cover - must not run
            raise AssertionError("ran while the package is off")

    with registry.owner(PKG):
        ml_evaluation.metric_registry.register(FakeHandler())
    try:
        evaluator = SampleEvaluator("e1", {"f": {"type": "text"}}, {})
        with _snapshot("off"):
            with activation.use_context(user_id="u1", inherit=False):
                result = evaluator._compute_metric_with_details(
                    "wfake_metric_eval", "a", "b", "text", {}
                )
        assert result["error"] == "feature_disabled"
        assert result["method"] == "wfake_metric_eval"
    finally:
        ml_evaluation.metric_registry._handlers.pop("wfake_metric_eval", None)
        ml_evaluation.metric_registry._owners.pop("wfake_metric_eval", None)
