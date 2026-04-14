"""
Unit tests for routers/projects/crud.py - deep_merge_dicts and visibility endpoints.
"""

import pytest


class TestDeepMergeDicts:
    """Test the deep_merge_dicts helper function directly."""

    def setup_method(self):
        from routers.projects.crud import deep_merge_dicts
        self.merge = deep_merge_dicts

    def test_both_none(self):
        assert self.merge(None, None) == {}

    def test_base_none(self):
        assert self.merge(None, {"a": 1}) == {"a": 1}

    def test_update_none(self):
        assert self.merge({"a": 1}, None) == {"a": 1}

    def test_both_empty(self):
        assert self.merge({}, {}) == {}

    def test_base_empty(self):
        assert self.merge({}, {"a": 1}) == {"a": 1}

    def test_update_empty(self):
        assert self.merge({"a": 1}, {}) == {"a": 1}

    def test_simple_merge(self):
        result = self.merge({"a": 1}, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_overwrite_value(self):
        result = self.merge({"a": 1}, {"a": 2})
        assert result == {"a": 2}

    def test_none_value_removes_key(self):
        result = self.merge({"a": 1, "b": 2}, {"a": None})
        assert result == {"b": 2}

    def test_deep_merge_nested_dicts(self):
        base = {"config": {"model": "gpt-4", "temp": 0.7}}
        update = {"config": {"temp": 0.5}}
        result = self.merge(base, update)
        assert result == {"config": {"model": "gpt-4", "temp": 0.5}}

    def test_list_replaced_not_concatenated(self):
        base = {"tags": [1, 2, 3]}
        update = {"tags": [4, 5]}
        result = self.merge(base, update)
        assert result == {"tags": [4, 5]}

    def test_does_not_mutate_input(self):
        base = {"a": {"b": 1}}
        update = {"a": {"c": 2}}
        result = self.merge(base, update)
        assert "c" not in base["a"]
        assert result["a"] == {"b": 1, "c": 2}

    def test_deeply_nested_merge(self):
        base = {"l1": {"l2": {"l3": "original", "keep": True}}}
        update = {"l1": {"l2": {"l3": "updated"}}}
        result = self.merge(base, update)
        assert result["l1"]["l2"]["l3"] == "updated"
        assert result["l1"]["l2"]["keep"] is True

    def test_new_nested_key(self):
        base = {"a": 1}
        update = {"b": {"c": 2}}
        result = self.merge(base, update)
        assert result == {"a": 1, "b": {"c": 2}}

    def test_mixed_types_override(self):
        base = {"a": {"nested": True}}
        update = {"a": "flat_string"}
        result = self.merge(base, update)
        assert result == {"a": "flat_string"}

    def test_generation_config_scenario(self):
        """Real scenario: update selected models without losing prompt structure."""
        base = {
            "selected_configuration": {
                "models": ["gpt-3.5"],
                "prompt_structure_id": "ps-1",
            },
            "output_format": "json",
        }
        update = {
            "selected_configuration": {
                "models": ["gpt-4", "claude-3"],
            }
        }
        result = self.merge(base, update)
        assert result["selected_configuration"]["models"] == ["gpt-4", "claude-3"]
        assert result["selected_configuration"]["prompt_structure_id"] == "ps-1"
        assert result["output_format"] == "json"
