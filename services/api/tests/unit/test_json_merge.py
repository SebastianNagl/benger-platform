"""
Unit tests for JSON deep merge utility

Tests the deep_merge_dicts function to ensure it properly merges nested
dictionaries while preserving unrelated fields.

Issue #818: Prevent generation_config updates from overwriting unrelated fields
"""


from routers.projects.crud import deep_merge_dicts


class TestDeepMergeDicts:
    """Test suite for deep_merge_dicts function"""

    def test_basic_nested_dict_merge(self):
        """Test basic merging of nested dictionaries"""
        base = {"a": {"b": 1, "c": 2}, "d": 3}
        update = {"a": {"c": 99, "e": 4}, "f": 5}
        result = deep_merge_dicts(base, update)

        assert result == {
            "a": {"b": 1, "c": 99, "e": 4},  # b preserved, c updated, e added
            "d": 3,  # preserved
            "f": 5,  # added
        }

    def test_list_replacement_not_concatenation(self):
        """Test that lists are replaced, not merged/concatenated"""
        base = {"models": ["gpt-4", "claude-3"], "other": "value"}
        update = {"models": ["new-model"]}
        result = deep_merge_dicts(base, update)

        assert result["models"] == ["new-model"]  # Replaced, not merged
        assert result["other"] == "value"  # Other fields preserved

    def test_none_values_remove_keys(self):
        """Test that None values in update remove the key from base"""
        base = {"a": 1, "b": 2, "c": 3}
        update = {"b": None}
        result = deep_merge_dicts(base, update)

        assert "b" not in result
        assert result == {"a": 1, "c": 3}

    def test_empty_base_dict(self):
        """Test merging with empty base dictionary"""
        base = {}
        update = {"a": 1, "b": {"c": 2}}
        result = deep_merge_dicts(base, update)

        assert result == update

    def test_empty_update_dict(self):
        """Test merging with empty update dictionary"""
        base = {"a": 1, "b": {"c": 2}}
        update = {}
        result = deep_merge_dicts(base, update)

        assert result == base

    def test_none_base(self):
        """Test merging when base is None"""
        base = None
        update = {"a": 1, "b": 2}
        result = deep_merge_dicts(base, update)

        assert result == update

    def test_none_update(self):
        """Test merging when update is None"""
        base = {"a": 1, "b": 2}
        update = None
        result = deep_merge_dicts(base, update)

        assert result == base

    def test_both_none(self):
        """Test merging when both are None"""
        result = deep_merge_dicts(None, None)
        assert result == {}

    def test_deeply_nested_structures(self):
        """Test merging deeply nested dictionaries (3+ levels)"""
        base = {"level1": {"level2": {"level3": {"a": 1, "b": 2}, "other": "preserved"}}}
        update = {"level1": {"level2": {"level3": {"b": 99, "c": 3}}}}  # Update  # Add
        result = deep_merge_dicts(base, update)

        assert result["level1"]["level2"]["level3"]["a"] == 1  # Preserved
        assert result["level1"]["level2"]["level3"]["b"] == 99  # Updated
        assert result["level1"]["level2"]["level3"]["c"] == 3  # Added
        assert result["level1"]["level2"]["other"] == "preserved"  # Preserved

    def test_mixed_types(self):
        """Test merging with mixed types (dict, list, primitives)"""
        base = {
            "string": "hello",
            "number": 42,
            "list": [1, 2, 3],
            "dict": {"nested": "value"},
            "bool": True,
        }
        update = {"string": "world", "list": [4, 5], "dict": {"nested": "updated", "new": "field"}}
        result = deep_merge_dicts(base, update)

        assert result["string"] == "world"  # Replaced
        assert result["number"] == 42  # Preserved
        assert result["list"] == [4, 5]  # Replaced
        assert result["dict"]["nested"] == "updated"  # Updated
        assert result["dict"]["new"] == "field"  # Added
        assert result["bool"] is True  # Preserved

    def test_generation_config_use_case_models_then_prompts(self):
        """
        Test real-world use case: updating models, then prompt structures
        This simulates the bug scenario from Issue #818
        """
        # Initial state: prompt structures set
        base = {
            "selected_configuration": {
                "active_structures": ["structure1", "structure2"],
                "prompts": {"system": "existing prompt"},
            },
            "other_config": "preserved",
        }

        # User selects models
        update = {"selected_configuration": {"models": ["gpt-4", "claude-3-opus"]}}

        result = deep_merge_dicts(base, update)

        # Both models AND active_structures should be present
        assert result["selected_configuration"]["models"] == ["gpt-4", "claude-3-opus"]
        assert result["selected_configuration"]["active_structures"] == ["structure1", "structure2"]
        assert result["selected_configuration"]["prompts"]["system"] == "existing prompt"
        assert result["other_config"] == "preserved"

    def test_generation_config_use_case_prompts_then_models(self):
        """
        Test real-world use case: updating prompt structures, then models
        This simulates the reverse order of Issue #818
        """
        # Initial state: models set
        base = {"selected_configuration": {"models": ["gpt-4"], "parameters": {"temperature": 0.7}}}

        # User selects prompt structures
        update = {"selected_configuration": {"active_structures": ["structure1", "structure2"]}}

        result = deep_merge_dicts(base, update)

        # Both models AND active_structures should be present
        assert result["selected_configuration"]["models"] == ["gpt-4"]
        assert result["selected_configuration"]["active_structures"] == ["structure1", "structure2"]
        assert result["selected_configuration"]["parameters"]["temperature"] == 0.7

    def test_no_mutation_of_inputs(self):
        """Test that the function doesn't mutate input dictionaries"""
        base = {"a": {"b": 1}}
        update = {"a": {"c": 2}}

        base_copy = {"a": {"b": 1}}
        update_copy = {"a": {"c": 2}}

        result = deep_merge_dicts(base, update)

        # Inputs should remain unchanged
        assert base == base_copy
        assert update == update_copy
        # Result should be a new dict
        assert result is not base
        assert result is not update

    def test_multiple_sequential_updates(self):
        """Test multiple sequential updates preserve all changes"""
        base = {}

        # Update 1: Add models
        update1 = {"selected_configuration": {"models": ["gpt-4"]}}
        result1 = deep_merge_dicts(base, update1)

        # Update 2: Add prompts (using result1 as new base)
        update2 = {"selected_configuration": {"active_structures": ["s1", "s2"]}}
        result2 = deep_merge_dicts(result1, update2)

        # Update 3: Modify models (using result2 as new base)
        update3 = {"selected_configuration": {"models": ["claude-3"]}}
        result3 = deep_merge_dicts(result2, update3)

        # All updates should be preserved
        assert result3["selected_configuration"]["models"] == ["claude-3"]
        assert result3["selected_configuration"]["active_structures"] == ["s1", "s2"]

    def test_replacing_primitive_with_dict(self):
        """Test replacing a primitive value with a dictionary"""
        base = {"field": "string value"}
        update = {"field": {"nested": "dict"}}
        result = deep_merge_dicts(base, update)

        assert result["field"] == {"nested": "dict"}

    def test_replacing_dict_with_primitive(self):
        """Test replacing a dictionary with a primitive value"""
        base = {"field": {"nested": "dict"}}
        update = {"field": "string value"}
        result = deep_merge_dicts(base, update)

        assert result["field"] == "string value"
