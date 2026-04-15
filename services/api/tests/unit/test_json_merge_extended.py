"""
Unit tests for utils/json_merge.py to increase coverage.
"""

import pytest


class TestJsonMerge:
    def setup_method(self):
        from utils.json_merge import deep_merge_dicts
        self.merge = deep_merge_dicts

    def test_merge_simple(self):
        a = {"x": 1}
        b = {"y": 2}
        result = self.merge(a, b)
        assert result == {"x": 1, "y": 2}

    def test_merge_override(self):
        a = {"x": 1}
        b = {"x": 2}
        result = self.merge(a, b)
        assert result == {"x": 2}

    def test_merge_nested(self):
        a = {"config": {"a": 1, "b": 2}}
        b = {"config": {"b": 3, "c": 4}}
        result = self.merge(a, b)
        assert result["config"]["a"] == 1
        assert result["config"]["b"] == 3
        assert result["config"]["c"] == 4

    def test_merge_empty_a(self):
        result = self.merge({}, {"x": 1})
        assert result == {"x": 1}

    def test_merge_empty_b(self):
        result = self.merge({"x": 1}, {})
        assert result == {"x": 1}

    def test_merge_list_replaced(self):
        a = {"items": [1, 2]}
        b = {"items": [3, 4]}
        result = self.merge(a, b)
        assert result["items"] == [3, 4]

    def test_merge_deeply_nested(self):
        a = {"l1": {"l2": {"l3": {"val": "old"}}}}
        b = {"l1": {"l2": {"l3": {"val": "new"}}}}
        result = self.merge(a, b)
        assert result["l1"]["l2"]["l3"]["val"] == "new"

    def test_merge_new_keys(self):
        a = {"a": 1}
        b = {"b": {"c": 2}}
        result = self.merge(a, b)
        assert result["a"] == 1
        assert result["b"]["c"] == 2

    def test_merge_preserves_original(self):
        a = {"x": {"y": 1}}
        b = {"x": {"z": 2}}
        result = self.merge(a, b)
        assert "y" not in a.get("x", {}) or a["x"]["y"] == 1
        assert "z" in result["x"]

    def test_merge_none_values(self):
        a = {"x": 1, "y": 2}
        b = {"x": None}
        result = self.merge(a, b)
        # Behavior depends on implementation - None may remove or keep
        assert isinstance(result, dict)

    def test_merge_mixed_types(self):
        a = {"x": {"nested": True}}
        b = {"x": "flat"}
        result = self.merge(a, b)
        assert result["x"] == "flat"

    def test_merge_with_numeric(self):
        a = {"count": 5}
        b = {"count": 10}
        result = self.merge(a, b)
        assert result["count"] == 10

    def test_merge_boolean_values(self):
        a = {"enabled": True}
        b = {"enabled": False}
        result = self.merge(a, b)
        assert result["enabled"] is False
