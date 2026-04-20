"""Tests for the extension point architecture (community edition behavior)."""

import importlib
import sys

import pytest


class TestExtensionLoader:
    """Test that extensions.py works correctly without benger_extended installed."""

    def test_load_extended_returns_false_without_package(self):
        """Community edition: load_extended returns False when package missing."""
        # Ensure benger_extended is not importable for this test
        if "benger_extended" in sys.modules:
            del sys.modules["benger_extended"]

        # Re-import to reset state
        import extensions
        importlib.reload(extensions)

        # Temporarily hide benger_extended
        original = sys.modules.get("benger_extended")
        sys.modules["benger_extended"] = None  # type: ignore

        try:
            importlib.reload(extensions)
            result = extensions.load_extended()
            assert result is False
        finally:
            if original:
                sys.modules["benger_extended"] = original
            else:
                sys.modules.pop("benger_extended", None)

    def test_get_extended_routers_returns_empty_without_package(self):
        """Community edition: get_extended_routers returns empty list."""
        from extensions import get_extended_routers

        # Without loading, should return empty
        result = get_extended_routers()
        assert result == []

    def test_on_annotation_created_noop_without_package(self):
        """Community edition: on_annotation_created is a no-op."""
        from extensions import on_annotation_created

        # Should not raise even with None db
        on_annotation_created(None, "task-1", "user-1", "ann-1", "proj-1")

    def test_on_draft_saved_noop_without_package(self):
        """Community edition: on_draft_saved is a no-op."""
        from extensions import on_draft_saved

        # Should not raise even with None db
        on_draft_saved(None, "task-1", "user-1", "proj-1", [])

    def test_core_api_version_defined(self):
        """CORE_API_VERSION is defined and is a string."""
        from extensions import CORE_API_VERSION

        assert isinstance(CORE_API_VERSION, str)
        assert CORE_API_VERSION == "1.0"
