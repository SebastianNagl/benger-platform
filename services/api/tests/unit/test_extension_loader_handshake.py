"""OPEN-CORE CONTRACT TEST — platform-side extension loader / version handshake.

`extensions.load_extended()` is the gate that decides whether the extended
overlay loads. Its handshake logic is what CrashLoops a prod pod on a version
mismatch (with BENGER_REQUIRE_EXTENDED set) or silently degrades to the
community edition (without it). The extended repo already asserts its
COMPATIBLE_CORE_VERSIONS includes the platform version; this test exercises the
PLATFORM half — the actual branch behavior — which nothing covered before.

Community-edition runnable: a fake ``benger_extended`` module is injected into
sys.modules; no real extended package needed.
"""

import sys
import types

import pytest

import extensions
from core_version import CORE_API_VERSION


def _fake_extended(compatible):
    mod = types.ModuleType("benger_extended")
    mod.COMPATIBLE_CORE_VERSIONS = list(compatible)
    # No get_field_type_registrations / get_routers — the loader guards on
    # hasattr, so a minimal module is enough to exercise the handshake.
    return mod


@pytest.fixture(autouse=True)
def _reset_loader_state(monkeypatch):
    # load_extended() mutates a module global; isolate each test.
    monkeypatch.setattr(extensions, "_extended", None, raising=False)
    monkeypatch.delenv("BENGER_REQUIRE_EXTENDED", raising=False)
    yield


class TestVersionHandshake:
    def test_compatible_version_loads(self, monkeypatch):
        monkeypatch.setitem(
            sys.modules, "benger_extended", _fake_extended([CORE_API_VERSION])
        )
        assert extensions.load_extended() is True
        assert extensions._extended is not None

    def test_mismatch_without_require_degrades_to_community(self, monkeypatch):
        monkeypatch.setitem(
            sys.modules, "benger_extended", _fake_extended(["0.0-nope"])
        )
        # No BENGER_REQUIRE_EXTENDED → disable extended, run community, no raise.
        assert extensions.load_extended() is False
        assert extensions._extended is None

    def test_mismatch_with_require_raises(self, monkeypatch):
        monkeypatch.setitem(
            sys.modules, "benger_extended", _fake_extended(["0.0-nope"])
        )
        monkeypatch.setenv("BENGER_REQUIRE_EXTENDED", "true")
        with pytest.raises(RuntimeError, match="incompatible"):
            extensions.load_extended()

    def test_import_failure_without_require_degrades(self, monkeypatch):
        def _boom(name):
            raise ImportError("no extended overlay in this build")

        monkeypatch.setattr(extensions.importlib, "import_module", _boom)
        assert extensions.load_extended() is False

    def test_import_failure_with_require_raises(self, monkeypatch):
        def _boom(name):
            raise ImportError("no extended overlay in this build")

        monkeypatch.setattr(extensions.importlib, "import_module", _boom)
        monkeypatch.setenv("BENGER_REQUIRE_EXTENDED", "true")
        with pytest.raises(RuntimeError, match="Refusing to start"):
            extensions.load_extended()


class TestHookGracefulNoOp:
    """Community edition (no extended loaded): every hook the platform calls
    must be a graceful no-op, never raise, and return its documented default.
    This is the other half of the hook contract — the extended repo asserts it
    REGISTERS the keys; this asserts the platform SURVIVES their absence."""

    def test_void_hooks_no_op_without_extended(self, monkeypatch):
        monkeypatch.setattr(extensions, "_extended", None, raising=False)
        # None of these should raise or do anything when extended is absent.
        assert extensions.on_annotation_created(None, "t", "u", "a", "p") is None
        assert extensions.on_draft_saved(None, "t", "u", "p", {}) is None
        assert extensions.run_after_eval_config_save(None, object(), {}) is None
        assert extensions.validate_signup(None, object()) is None

    def test_tasks_with_feedback_defaults_to_empty_set(self, monkeypatch):
        monkeypatch.setattr(extensions, "_extended", None, raising=False)
        assert extensions.tasks_with_feedback_for_user(None, "p", "u", ["t1"]) == set()
        # Empty input short-circuits to an empty set regardless.
        assert extensions.tasks_with_feedback_for_user(None, "p", "u", []) == set()
