"""Unit tests for the extension loader (services/api/extensions.py).

Covers the open-core seam behavior:
- community edition degrades gracefully when benger_extended is absent,
- an incompatible extended package is rejected by the version handshake,
- BENGER_REQUIRE_EXTENDED flips both failure modes into hard startup
  errors so a broken overlay fails the rollout instead of shipping a
  silently degraded deployment.

The fake extended packages are injected via sys.modules, so these tests
run identically in the community image (no benger_extended installed) and
in the combined extended image (where the real package exists).
"""

import sys
import types

import pytest

import extensions
from core_version import CORE_API_VERSION


@pytest.fixture(autouse=True)
def _reset_loader_state(monkeypatch):
    """Each test starts with no extended package loaded."""
    monkeypatch.setattr(extensions, "_extended", None)
    yield
    extensions._extended = None


def _fake_extended(compatible_versions):
    mod = types.ModuleType("benger_extended")
    mod.COMPATIBLE_CORE_VERSIONS = compatible_versions
    return mod


def test_community_edition_degrades_gracefully(monkeypatch):
    """No extended package, flag unset -> load returns False, no raise."""
    monkeypatch.delenv("BENGER_REQUIRE_EXTENDED", raising=False)
    monkeypatch.setitem(sys.modules, "benger_extended", None)

    assert extensions.load_extended() is False
    assert extensions._extended is None
    assert extensions.get_extended_routers() == []


def test_missing_package_raises_when_required(monkeypatch):
    monkeypatch.setenv("BENGER_REQUIRE_EXTENDED", "true")
    monkeypatch.setitem(sys.modules, "benger_extended", None)

    with pytest.raises(RuntimeError, match="BENGER_REQUIRE_EXTENDED"):
        extensions.load_extended()


def test_compatible_package_loads(monkeypatch):
    monkeypatch.delenv("BENGER_REQUIRE_EXTENDED", raising=False)
    monkeypatch.setitem(
        sys.modules, "benger_extended", _fake_extended([CORE_API_VERSION])
    )

    assert extensions.load_extended() is True
    assert extensions._extended is not None


def test_incompatible_package_disables_extended(monkeypatch):
    """Handshake mismatch, flag unset -> degrade with extended disabled."""
    monkeypatch.delenv("BENGER_REQUIRE_EXTENDED", raising=False)
    monkeypatch.setitem(sys.modules, "benger_extended", _fake_extended(["0.0"]))

    assert extensions.load_extended() is False
    assert extensions._extended is None


def test_incompatible_package_raises_when_required(monkeypatch):
    """Handshake mismatch + flag -> hard fail naming both versions."""
    monkeypatch.setenv("BENGER_REQUIRE_EXTENDED", "true")
    monkeypatch.setitem(sys.modules, "benger_extended", _fake_extended(["0.0"]))

    with pytest.raises(RuntimeError) as excinfo:
        extensions.load_extended()

    message = str(excinfo.value)
    assert "0.0" in message
    assert CORE_API_VERSION in message
    assert extensions._extended is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("true", True),
        ("1", True),
        ("YES", True),
        (" True ", True),
        ("false", False),
        ("0", False),
        ("", False),
    ],
)
def test_extended_required_parsing(monkeypatch, raw, expected):
    from core_version import extended_required

    monkeypatch.setenv("BENGER_REQUIRE_EXTENDED", raw)
    assert extended_required() is expected
