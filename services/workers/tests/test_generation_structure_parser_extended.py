"""Extended tests for generation_structure_parser.py - edge cases.

Covers:
- parse_structure with invalid JSON
- parse_structure with non-dict JSON
- extract_nested_value edge cases
- _contains_sensitive_data
- _extract_prompt_mappings edge cases
- filter_task_data with sensitive nested data
- validate_structure edge cases
- SENSITIVE_FIELDS coverage
"""

import json
import os
import sys

import pytest

workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

from generation_structure_parser import GenerationStructureParser


class TestParseStructureEdgeCases:

    def setup_method(self):
        self.parser = GenerationStructureParser()

    def test_none_input(self):
        assert self.parser.parse_structure(None) is None

    def test_empty_string(self):
        assert self.parser.parse_structure("") is None

    def test_invalid_json_string(self):
        assert self.parser.parse_structure("not json at all {") is None

    def test_non_dict_json(self):
        assert self.parser.parse_structure("[1, 2, 3]") is None

    def test_empty_dict(self):
        # Empty dict is valid JSON but has no content, parse_structure returns None
        # because it checks `if not generation_structure` which is True for {}
        result = self.parser.parse_structure({})
        assert result is None


class TestExtractNestedValueEdgeCases:

    def setup_method(self):
        self.parser = GenerationStructureParser()

    def test_none_data(self):
        assert self.parser.extract_nested_value(None, "field") is None

    def test_none_path(self):
        assert self.parser.extract_nested_value({"a": 1}, None) is None

    def test_empty_path(self):
        assert self.parser.extract_nested_value({"a": 1}, "") is None

    def test_nested_none_in_path(self):
        data = {"a": {"b": None}}
        assert self.parser.extract_nested_value(data, "a.b.c") is None

    def test_array_out_of_bounds(self):
        data = {"items": [1, 2]}
        assert self.parser.extract_nested_value(data, "items[99]") is None

    def test_array_on_non_list(self):
        data = {"items": "not a list"}
        assert self.parser.extract_nested_value(data, "items[0]") is None

    def test_field_on_non_dict(self):
        data = {"a": 42}
        assert self.parser.extract_nested_value(data, "a.b") is None

    def test_deep_nesting(self):
        data = {"a": {"b": {"c": {"d": {"e": "deep_value"}}}}}
        assert self.parser.extract_nested_value(data, "a.b.c.d.e") == "deep_value"

    def test_array_index_with_no_field_name(self):
        """Array at root level via extract_nested_value is not directly accessible."""
        data = {"items": [[1, 2], [3, 4]]}
        val = self.parser.extract_nested_value(data, "items[0]")
        assert val == [1, 2]

    def test_invalid_array_index(self):
        data = {"items": [1, 2]}
        # The path parser won't create an invalid index, but test boundary
        assert self.parser.extract_nested_value(data, "items[-1]") is None


class TestContainsSensitiveData:

    def setup_method(self):
        self.parser = GenerationStructureParser()

    def test_dict_with_sensitive_key(self):
        assert self.parser._contains_sensitive_data({"annotations": []}) is True

    def test_dict_with_reference_key(self):
        assert self.parser._contains_sensitive_data({"reference_answer": "x"}) is True

    def test_dict_without_sensitive_key(self):
        assert self.parser._contains_sensitive_data({"question": "What?"}) is False

    def test_list_with_sensitive_dict(self):
        assert self.parser._contains_sensitive_data([{"ground_truth": "x"}]) is True

    def test_list_without_sensitive(self):
        assert self.parser._contains_sensitive_data([{"question": "x"}]) is False

    def test_non_container_value(self):
        assert self.parser._contains_sensitive_data("just a string") is False
        assert self.parser._contains_sensitive_data(42) is False

    def test_empty_dict(self):
        assert self.parser._contains_sensitive_data({}) is False

    def test_empty_list(self):
        assert self.parser._contains_sensitive_data([]) is False


class TestSensitiveFields:

    def setup_method(self):
        self.parser = GenerationStructureParser()

    def test_all_sensitive_fields_exist(self):
        expected = {
            'annotations', 'annotation', 'reference_answer', 'reference',
            'ground_truth', 'correct_answer', 'expected_output', 'label',
            'labels', 'gold_standard', 'binary_solution', 'reasoning',
            'answer', 'solution',
        }
        assert self.parser.SENSITIVE_FIELDS == expected


class TestExtractPromptMappings:

    def setup_method(self):
        self.parser = GenerationStructureParser()

    def test_string_field_reference(self):
        mappings = self.parser._extract_prompt_mappings("$area")
        assert mappings == {"area": "area"}

    def test_non_reference_string(self):
        mappings = self.parser._extract_prompt_mappings("Just a literal string")
        assert mappings == {}

    def test_dict_with_fields(self):
        config = {
            "template": "{{area}} in {{jurisdiction}}",
            "fields": {"area": "$area", "jurisdiction": "$context.jurisdiction"},
        }
        mappings = self.parser._extract_prompt_mappings(config)
        assert mappings == {"area": "area", "jurisdiction": "context.jurisdiction"}

    def test_dict_without_fields(self):
        config = {"template": "Static template"}
        mappings = self.parser._extract_prompt_mappings(config)
        assert mappings == {}

    def test_dict_with_non_reference_fields(self):
        config = {
            "template": "{{x}}",
            "fields": {"x": "not_a_reference"},
        }
        mappings = self.parser._extract_prompt_mappings(config)
        assert mappings == {}

    def test_non_dict_non_string(self):
        mappings = self.parser._extract_prompt_mappings(42)
        assert mappings == {}


class TestExtractFieldMappings:

    def setup_method(self):
        self.parser = GenerationStructureParser()

    def test_from_system_prompt(self):
        structure = {"system_prompt": "$area"}
        mappings = self.parser.extract_field_mappings(structure)
        assert "area" in mappings

    def test_from_instruction_prompt(self):
        structure = {"instruction_prompt": "$question"}
        mappings = self.parser.extract_field_mappings(structure)
        assert "question" in mappings

    def test_from_legacy_fields(self):
        structure = {"fields": {"area": "$area", "q": "$question"}}
        mappings = self.parser.extract_field_mappings(structure)
        assert mappings["area"] == "area"
        assert mappings["q"] == "question"

    def test_legacy_fields_non_reference(self):
        structure = {"fields": {"area": "literal"}}
        mappings = self.parser.extract_field_mappings(structure)
        assert "area" not in mappings

    def test_combined_sources(self):
        structure = {
            "system_prompt": "$area",
            "instruction_prompt": {
                "template": "{{q}}",
                "fields": {"q": "$question"},
            },
            "fields": {"extra": "$context"},
        }
        mappings = self.parser.extract_field_mappings(structure)
        assert "area" in mappings
        assert "q" in mappings
        assert "extra" in mappings


class TestFilterTaskDataSensitive:

    def setup_method(self):
        self.parser = GenerationStructureParser()

    def test_sensitive_path_blocked(self):
        task_data = {"annotations": {"ref": "secret"}, "question": "What?"}
        mappings = {"ref": "annotations.ref", "q": "question"}
        filtered = self.parser.filter_task_data(task_data, mappings)
        assert "ref" not in filtered
        assert "q" in filtered

    def test_sensitive_nested_data_blocked(self):
        task_data = {"data": {"ground_truth": "secret", "question": "What?"}}
        mappings = {"d": "data"}
        filtered = self.parser.filter_task_data(task_data, mappings)
        assert "d" not in filtered

    def test_custom_exclude_fields(self):
        task_data = {"internal": "private", "public": "visible"}
        mappings = {"i": "internal", "p": "public"}
        filtered = self.parser.filter_task_data(task_data, mappings, exclude_fields=["internal"])
        assert "i" not in filtered
        assert "p" in filtered

    def test_missing_field_not_included(self):
        task_data = {"a": 1}
        mappings = {"b": "nonexistent"}
        filtered = self.parser.filter_task_data(task_data, mappings)
        assert "b" not in filtered


class TestBuildPrompts:

    def setup_method(self):
        self.parser = GenerationStructureParser()

    def test_literal_system_prompt(self):
        structure = {"system_prompt": "You are a legal expert."}
        prompts = self.parser.build_prompts({}, structure)
        assert prompts["system_prompt"] == "You are a legal expert."

    def test_missing_field_returns_empty(self):
        structure = {"system_prompt": "$nonexistent"}
        prompts = self.parser.build_prompts({}, structure)
        assert prompts["system_prompt"] == ""

    def test_context_fields_without_instruction(self):
        task_data = {"ctx": "some context"}
        structure = {"context_fields": ["$ctx"]}
        prompts = self.parser.build_prompts(task_data, structure)
        assert "Context:" in prompts["instruction_prompt"]

    def test_dict_value_serialized(self):
        task_data = {"metadata": {"key": "value"}}
        structure = {"system_prompt": "$metadata"}
        prompts = self.parser.build_prompts(task_data, structure)
        assert '"key"' in prompts["system_prompt"]


class TestValidateStructureEdgeCases:

    def setup_method(self):
        self.parser = GenerationStructureParser()

    def test_invalid_json_fails(self):
        valid, error = self.parser.validate_structure("not json")
        assert not valid

    def test_parameters_must_be_dict(self):
        structure = {"system_prompt": "test", "parameters": "not_a_dict"}
        valid, error = self.parser.validate_structure(structure)
        assert not valid
        assert "'parameters' must be an object" in error

    def test_invalid_prompt_type(self):
        structure = {"system_prompt": 42}
        valid, error = self.parser.validate_structure(structure)
        assert not valid
        assert "must be string or object" in error

    def test_fields_must_be_dict_in_prompt(self):
        structure = {
            "system_prompt": {"template": "test", "fields": "not_a_dict"}
        }
        valid, error = self.parser.validate_structure(structure)
        assert not valid
        assert "fields must be an object" in error


class TestInterpolateTemplateEdgeCases:

    def setup_method(self):
        self.parser = GenerationStructureParser()

    def test_none_value_becomes_empty(self):
        result = self.parser.interpolate_template("Value: {{x}}", {"x": None})
        assert result == "Value: "

    def test_no_placeholders_unchanged(self):
        result = self.parser.interpolate_template("No placeholders here", {})
        assert result == "No placeholders here"

    def test_list_value_serialized(self):
        result = self.parser.interpolate_template("Items: {{items}}", {"items": [1, 2, 3]})
        assert "1" in result
        assert "2" in result
        assert "3" in result
