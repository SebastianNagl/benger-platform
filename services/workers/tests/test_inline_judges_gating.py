"""The inline judge follows the package's runtime switch (core 2.42).

``resolve_inline_judge`` looks ``get_inline_judge`` up through
``extension_registry`` (gating class gated), so a task whose context has the
owning package off gets no inline judge and the metric takes the generic
path.
"""

import sys
import types
from unittest.mock import patch

import pytest

import extension_activation
import extension_registry
from evaluation.inline_judges import resolve_inline_judge


@pytest.fixture(autouse=True)
def _fresh_registry():
    # Earlier tests may have loaded (or refused) a package in this process.
    extension_registry.reset()
    yield
    extension_registry.reset()


def _overlay(judge):
    pkg = types.ModuleType("benger_extended")
    workers = types.ModuleType("benger_extended.workers")
    workers.get_inline_judge = lambda metric: judge
    pkg.workers = workers
    return patch.dict(sys.modules, {"benger_extended": pkg, "benger_extended.workers": workers})


def test_get_inline_judge_is_gated():
    assert extension_registry.worker_attr_gating("get_inline_judge") == extension_activation.GATED


def test_package_off_for_the_task_means_no_inline_judge():
    judge = object()
    with _overlay(judge), patch.dict("os.environ", {"BENGER_EXTENSIONS": "benger_extended"}):
        with patch.object(extension_activation, "package_active", return_value=False) as active:
            assert resolve_inline_judge("llm_judge_feedback") is None
        active.assert_called_with("benger_extended", extension_activation.GATED)
        with patch.object(extension_activation, "package_active", return_value=True):
            assert resolve_inline_judge("llm_judge_feedback") is judge
