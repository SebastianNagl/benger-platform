"""A refused or inactive extension package runs no code on the worker side.

The package can be importable while the registry refused it (failed version
handshake): it never registered a master flag, so ``extension_activation.
package_active`` answers True for it, and the direct ``from benger_extended
...`` imports found it. Every Falllösung surface and the billing-tier config
selector now go through ``extension_registry``, which skips refused packages;
a package switched off for the task refuses (``feature_disabled``) instead of
grading.
"""

import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

import extension_activation  # noqa: E402
import extension_registry as registry  # noqa: E402
from core_version import CORE_API_VERSION  # noqa: E402

FALLOESUNG = "llm_judge_falloesung"


def _overlay(monkeypatch, *, compatible):
    """A fake benger_extended with every surface the platform reaches."""
    pkg = types.ModuleType("benger_extended")
    pkg.__file__ = "/fake/benger_extended/__init__.py"
    pkg.COMPATIBLE_CORE_VERSIONS = list(compatible)
    workers = types.ModuleType("benger_extended.workers")
    compute = MagicMock(return_value={"status": "completed", "score": 1.0})
    bulk = MagicMock(return_value={"score": 50})
    workers.get_falloesung_compute_fn = lambda: compute
    workers.get_falloesung_bulk_compute_fn = lambda: bulk
    falloesung_tasks = types.ModuleType("benger_extended.workers.falloesung_tasks")
    persist_error = MagicMock()
    falloesung_tasks._persist_falloesung_eval_error = persist_error
    billing = types.ModuleType("benger_extended.billing")
    policy = types.ModuleType("benger_extended.billing.policy")
    select = MagicMock(
        side_effect=lambda db, user_id, configs, project=None: configs[:1]
    )
    policy.select_tier_config = select
    pkg.workers = workers
    pkg.billing = billing
    billing.policy = policy
    for name, module in {
        "benger_extended": pkg,
        "benger_extended.workers": workers,
        "benger_extended.workers.falloesung_tasks": falloesung_tasks,
        "benger_extended.billing": billing,
        "benger_extended.billing.policy": policy,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setenv("BENGER_EXTENSIONS", "benger_extended")
    registry.load_all()
    return types.SimpleNamespace(
        compute=compute, bulk=bulk, persist_error=persist_error, select=select
    )


@pytest.fixture(autouse=True)
def _isolated_registry(monkeypatch):
    monkeypatch.delenv("BENGER_EXTENSIONS", raising=False)
    monkeypatch.delenv("BENGER_REQUIRE_EXTENSIONS", raising=False)
    monkeypatch.delenv("BENGER_REQUIRE_EXTENDED", raising=False)
    registry.reset()
    yield
    registry.reset()


@pytest.fixture
def refused(monkeypatch):
    overlay = _overlay(monkeypatch, compatible=["0.0-nope"])
    assert registry.rejected()["benger_extended"].reason == "handshake"
    return overlay


@pytest.fixture
def switched_off(monkeypatch):
    overlay = _overlay(monkeypatch, compatible=[CORE_API_VERSION])
    assert registry.is_loaded("benger_extended")
    monkeypatch.setattr(
        extension_activation,
        "package_active",
        lambda package, gating=extension_activation.GATED: (
            gating == extension_activation.ALWAYS or package != "benger_extended"
        ),
    )
    return overlay


def _run_falloesung_immediately():
    import tasks as tasks_module
    from tasks import _run_immediate_config_job

    db = MagicMock()
    job = {
        "metric_type": FALLOESUNG,
        "metric_params": {},
        "field_name": "loesung",
        "prediction_value": "answer text",
        "reference_value": "",
        "judge_run_id": "jr-1",
        "evaluation_config_id": "cfg-1",
        "record_id": "rec-1",
    }
    with patch.object(tasks_module, "SessionLocal", return_value=db):
        result = _run_immediate_config_job(
            job=job,
            dispatch_eval_id="eval-1",
            project_id="proj-1",
            task_id="task-1",
            annotation_id="ann-1",
            organization_id=None,
            user_id="user-1",
            task_data={"sachverhalt": "case"},
        )
    rows = [c.args[0] for c in db.add.call_args_list]
    return result, rows


class TestRequireWorkerAttr:
    def test_a_refused_package_does_not_provide_it(self, refused):
        with pytest.raises(RuntimeError, match="requires the extended edition"):
            registry.require_worker_attr(
                "get_falloesung_compute_fn", missing="requires the extended edition"
            )

    def test_a_switched_off_package_refuses(self, switched_off):
        with pytest.raises(extension_activation.ExtensionInactive) as info:
            registry.require_worker_attr("get_falloesung_compute_fn", missing="x")
        assert info.value.package == "benger_extended"

    def test_an_active_package_provides_it(self, monkeypatch):
        overlay = _overlay(monkeypatch, compatible=[CORE_API_VERSION])
        fn = registry.require_worker_attr("get_falloesung_compute_fn", missing="x")
        assert fn() is overlay.compute

    def test_an_absent_package_does_not_provide_it(self, monkeypatch):
        monkeypatch.setenv("BENGER_EXTENSIONS", "")
        with pytest.raises(RuntimeError, match="not here"):
            registry.require_worker_attr(
                "get_falloesung_compute_fn", missing="not here"
            )


class TestImmediateFalloesung:
    def test_a_refused_package_neither_grades_nor_writes_the_error_row(self, refused):
        result, rows = _run_falloesung_immediately()
        refused.compute.assert_not_called()
        refused.persist_error.assert_not_called()
        assert result["status"] == "error"
        [row] = rows
        assert row.metrics[FALLOESUNG]["value"] is None
        assert row.passed is False

    def test_a_switched_off_package_records_feature_disabled(self, switched_off):
        result, rows = _run_falloesung_immediately()
        switched_off.compute.assert_not_called()
        switched_off.persist_error.assert_not_called()
        assert result["status"] == "error"
        [row] = rows
        blob = row.metrics[FALLOESUNG]
        assert blob["error"] == "feature_disabled"
        assert blob["details"]["reason"] == "feature_disabled"

    def test_an_active_package_grades(self, monkeypatch):
        overlay = _overlay(monkeypatch, compatible=[CORE_API_VERSION])
        with patch("evaluation.orchestration._hold_written_row"):
            result, _rows = _run_falloesung_immediately()
        overlay.compute.assert_called_once()
        assert result == {"status": "completed", "score": 1.0}


class TestTierConfigSelector:
    def test_a_refused_package_selects_nothing(self, refused):
        from immediate_eval_dispatch import _select_immediate_configs

        configs = [{"id": "free"}, {"id": "paid"}]
        assert _select_immediate_configs(MagicMock(), "user-1", configs) == configs
        refused.select.assert_not_called()

    def test_billing_selection_ignores_the_runtime_switch(self, switched_off):
        # Billing surfaces are ALWAYS: switching the package off must not
        # change which (paid or free) judge a grading uses.
        from immediate_eval_dispatch import _select_immediate_configs

        configs = [{"id": "free"}, {"id": "paid"}]
        assert _select_immediate_configs(MagicMock(), "user-1", configs) == [
            {"id": "free"}
        ]
        switched_off.select.assert_called_once()
