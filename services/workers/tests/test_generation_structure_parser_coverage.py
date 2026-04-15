"""Comprehensive coverage tests for generation_structure_parser.py.

Targets: parse_structure, extract_nested_value, extract_field_mappings,
interpolate_template, filter_task_data, _contains_sensitive_data,
build_prompts, _build_single_prompt, process_generation_structure,
validate_structure.
"""

import json
import sys
import os

workers_root = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, workers_root)

from generation_structure_parser import GenerationStructureParser


class TestParseStructure:
    def setup_method(self):
        self.parser = GenerationStructureParser()

    def test_none_input(self):
        assert self.parser.parse_structure(None) is None

    def test_empty_string(self):
        assert self.parser.parse_structure("") is None

    def test_empty_dict(self):
        # Empty dict is falsy in Python, so parse_structure returns None
        result = self.parser.parse_structure({})
        assert result is None

    def test_valid_json_string(self):
        result = self.parser.parse_structure('{"system_prompt": "Hello"}')
        assert result == {"system_prompt": "Hello"}

    def test_invalid_json_string(self):
        result = self.parser.parse_structure("not json")
        assert result is None

    def test_non_dict_json(self):
        result = self.parser.parse_structure("[1,2,3]")
        assert result is None

    def test_dict_input(self):
        d = {"system_prompt": "test"}
        result = self.parser.parse_structure(d)
        assert result == d

    def test_string_caching(self):
        json_str = '{"key": "value"}'
        r1 = self.parser.parse_structure(json_str)
        r2 = self.parser.parse_structure(json_str)
        assert r1 is r2  # same object from cache


class TestExtractNestedValue:
    def setup_method(self):
        self.parser = GenerationStructureParser()

    def test_simple_key(self):
        assert self.parser.extract_nested_value({"a": 1}, "a") == 1

    def test_nested_dot(self):
        data = {"a": {"b": {"c": 3}}}
        assert self.parser.extract_nested_value(data, "a.b.c") == 3

    def test_array_access(self):
        data = {"items": [10, 20, 30]}
        assert self.parser.extract_nested_value(data, "items[1]") == 20

    def test_array_access_out_of_bounds(self):
        data = {"items": [10]}
        assert self.parser.extract_nested_value(data, "items[5]") is None

    def test_nested_array_access(self):
        data = {"a": {"items": [{"name": "first"}, {"name": "second"}]}}
        assert self.parser.extract_nested_value(data, "a.items[0].name") == "first"

    def test_missing_key(self):
        assert self.parser.extract_nested_value({"a": 1}, "b") is None

    def test_none_data(self):
        assert self.parser.extract_nested_value(None, "a") is None

    def test_empty_path(self):
        assert self.parser.extract_nested_value({"a": 1}, "") is None

    def test_array_on_non_list(self):
        data = {"items": "not a list"}
        assert self.parser.extract_nested_value(data, "items[0]") is None

    def test_array_on_dict(self):
        data = {"items": {"a": 1}}
        assert self.parser.extract_nested_value(data, "items[0]") is None

    def test_invalid_array_index(self):
        data = {"items": [1, 2]}
        # The bracket notation with non-numeric can fail
        assert self.parser.extract_nested_value(data, "[0]") is None

    def test_standalone_array_index(self):
        """Test bracket-only path like [0] on a list."""
        data = [10, 20, 30]
        # This path has no field_name before bracket
        assert self.parser.extract_nested_value(data, "[1]") == 20

    def test_deep_none_traversal(self):
        data = {"a": None}
        assert self.parser.extract_nested_value(data, "a.b") is None


class TestExtractFieldMappings:
    def setup_method(self):
        self.parser = GenerationStructureParser()

    def test_system_prompt_field_ref(self):
        structure = {"system_prompt": "$context"}
        result = self.parser.extract_field_mappings(structure)
        assert result == {"context": "context"}

    def test_instruction_prompt_field_ref(self):
        structure = {"instruction_prompt": "$question"}
        result = self.parser.extract_field_mappings(structure)
        assert result == {"question": "question"}

    def test_template_prompt(self):
        structure = {
            "system_prompt": {
                "template": "Analyze {{text}}",
                "fields": {"text": "$content"}
            }
        }
        result = self.parser.extract_field_mappings(structure)
        assert result == {"text": "content"}

    def test_legacy_fields(self):
        structure = {"fields": {"q": "$data.question"}}
        result = self.parser.extract_field_mappings(structure)
        assert result == {"q": "data.question"}

    def test_non_variable_in_fields(self):
        structure = {"fields": {"q": "literal_value"}}
        result = self.parser.extract_field_mappings(structure)
        assert result == {}

    def test_combined_prompts_and_fields(self):
        structure = {
            "system_prompt": "$sys",
            "instruction_prompt": "$inst",
            "fields": {"f1": "$data.f1"},
        }
        result = self.parser.extract_field_mappings(structure)
        assert "sys" in result
        assert "inst" in result
        assert "f1" in result

    def test_empty_structure(self):
        result = self.parser.extract_field_mappings({})
        assert result == {}

    def test_prompt_literal_string(self):
        structure = {"system_prompt": "Just a literal"}
        result = self.parser.extract_field_mappings(structure)
        assert result == {}

    def test_prompt_dict_no_fields(self):
        structure = {"system_prompt": {"template": "Hello"}}
        result = self.parser.extract_field_mappings(structure)
        assert result == {}

    def test_prompt_dict_non_variable_fields(self):
        structure = {"system_prompt": {"template": "T", "fields": {"k": "literal"}}}
        result = self.parser.extract_field_mappings(structure)
        assert result == {}


class TestInterpolateTemplate:
    def setup_method(self):
        self.parser = GenerationStructureParser()

    def test_simple_replacement(self):
        result = self.parser.interpolate_template("Hello {{name}}", {"name": "World"})
        assert result == "Hello World"

    def test_multiple_replacements(self):
        result = self.parser.interpolate_template("{{a}} and {{b}}", {"a": "X", "b": "Y"})
        assert result == "X and Y"

    def test_dict_value(self):
        result = self.parser.interpolate_template("{{data}}", {"data": {"key": "value"}})
        assert '"key": "value"' in result

    def test_list_value(self):
        result = self.parser.interpolate_template("{{items}}", {"items": [1, 2, 3]})
        assert "1" in result and "2" in result

    def test_none_value(self):
        result = self.parser.interpolate_template("{{x}}", {"x": None})
        assert result == ""

    def test_numeric_value(self):
        result = self.parser.interpolate_template("{{n}}", {"n": 42})
        assert result == "42"

    def test_missing_placeholder_no_allow(self):
        result = self.parser.interpolate_template("{{missing}}", {})
        assert "{{missing}}" in result

    def test_missing_placeholder_allow(self):
        result = self.parser.interpolate_template("{{missing}}", {}, allow_missing=True)
        assert "{{missing}}" in result


class TestFilterTaskData:
    def setup_method(self):
        self.parser = GenerationStructureParser()

    def test_basic_filtering(self):
        task_data = {"question": "What?", "answer": "Yes"}
        mappings = {"q": "question"}
        result = self.parser.filter_task_data(task_data, mappings)
        assert result == {"q": "What?"}
        assert "answer" not in result

    def test_sensitive_field_blocked(self):
        task_data = {"annotations": "secret", "text": "safe"}
        mappings = {"a": "annotations", "t": "text"}
        result = self.parser.filter_task_data(task_data, mappings)
        assert "a" not in result
        assert "t" in result

    def test_custom_exclude(self):
        task_data = {"custom_secret": "hidden", "text": "safe"}
        mappings = {"c": "custom_secret", "t": "text"}
        result = self.parser.filter_task_data(task_data, mappings, exclude_fields=["custom_secret"])
        assert "c" not in result
        assert "t" in result

    def test_nested_sensitive_data(self):
        task_data = {"data": {"annotations": "secret", "text": "safe"}}
        mappings = {"d": "data"}
        result = self.parser.filter_task_data(task_data, mappings)
        # "data" contains a key "annotations" which is sensitive
        assert "d" not in result

    def test_missing_field(self):
        task_data = {"a": 1}
        mappings = {"b": "nonexistent"}
        result = self.parser.filter_task_data(task_data, mappings)
        assert result == {}

    def test_sensitive_path_part(self):
        task_data = {"reference_answer": {"nested": "data"}}
        mappings = {"r": "reference_answer.nested"}
        result = self.parser.filter_task_data(task_data, mappings)
        assert "r" not in result


class TestContainsSensitiveData:
    def setup_method(self):
        self.parser = GenerationStructureParser()

    def test_dict_with_sensitive_key(self):
        assert self.parser._contains_sensitive_data({"ground_truth": "x"}) is True

    def test_dict_without_sensitive_key(self):
        assert self.parser._contains_sensitive_data({"question": "x"}) is False

    def test_list_with_sensitive_nested(self):
        assert self.parser._contains_sensitive_data([{"answer": "x"}]) is True

    def test_list_without_sensitive(self):
        assert self.parser._contains_sensitive_data([{"q": "x"}]) is False

    def test_empty_list(self):
        assert self.parser._contains_sensitive_data([]) is False

    def test_non_dict_non_list(self):
        assert self.parser._contains_sensitive_data("string value") is False

    def test_none(self):
        assert self.parser._contains_sensitive_data(None) is False

    def test_list_with_non_dict_items(self):
        assert self.parser._contains_sensitive_data(["a", "b", "c"]) is False


class TestBuildPrompts:
    def setup_method(self):
        self.parser = GenerationStructureParser()

    def test_system_prompt_field_ref(self):
        task_data = {"context": "Legal case text"}
        structure = {"system_prompt": "$context"}
        result = self.parser.build_prompts(task_data, structure)
        assert result["system_prompt"] == "Legal case text"

    def test_instruction_prompt_template(self):
        task_data = {"question": "Is this valid?"}
        structure = {
            "instruction_prompt": {
                "template": "Answer: {{q}}",
                "fields": {"q": "$question"},
            }
        }
        result = self.parser.build_prompts(task_data, structure)
        assert result["instruction_prompt"] == "Answer: Is this valid?"

    def test_context_fields(self):
        task_data = {"part1": "First", "part2": "Second"}
        structure = {
            "instruction_prompt": "$part1",
            "context_fields": ["$part2"],
        }
        result = self.parser.build_prompts(task_data, structure)
        assert "Context:" in result["instruction_prompt"]
        assert "Second" in result["instruction_prompt"]

    def test_context_fields_no_instruction(self):
        task_data = {"part": "Data"}
        structure = {"context_fields": ["$part"]}
        result = self.parser.build_prompts(task_data, structure)
        assert "Context:" in result["instruction_prompt"]

    def test_missing_field_ref(self):
        task_data = {}
        structure = {"system_prompt": "$missing"}
        result = self.parser.build_prompts(task_data, structure)
        assert result["system_prompt"] == ""


class TestBuildSinglePrompt:
    def setup_method(self):
        self.parser = GenerationStructureParser()

    def test_literal_string(self):
        result = self.parser._build_single_prompt({}, "Hello world")
        assert result == "Hello world"

    def test_field_ref_dict_value(self):
        task_data = {"data": {"key": "val"}}
        result = self.parser._build_single_prompt(task_data, "$data")
        assert '"key"' in result

    def test_field_ref_list_value(self):
        task_data = {"items": [1, 2]}
        result = self.parser._build_single_prompt(task_data, "$items")
        assert "1" in result

    def test_non_string_non_dict(self):
        result = self.parser._build_single_prompt({}, 42)
        assert result == ""


class TestProcessGenerationStructure:
    def setup_method(self):
        self.parser = GenerationStructureParser()

    def test_no_structure(self):
        prompts, data = self.parser.process_generation_structure({}, None)
        assert prompts == {}
        assert data == {}

    def test_no_structure_with_fallback(self):
        prompts, data = self.parser.process_generation_structure(
            {}, None, fallback_instruction="Do this"
        )
        assert prompts["instruction_prompt"] == "Do this"

    def test_valid_structure(self):
        task_data = {"text": "Hello"}
        structure = {"instruction_prompt": "$text"}
        prompts, data = self.parser.process_generation_structure(task_data, structure)
        assert prompts["instruction_prompt"] == "Hello"

    def test_fallback_when_no_instruction(self):
        task_data = {"text": "Hello"}
        structure = {"system_prompt": "$text"}
        prompts, data = self.parser.process_generation_structure(
            task_data, structure, fallback_instruction="Fallback"
        )
        assert prompts["instruction_prompt"] == "Fallback"

    def test_exclude_fields_in_structure(self):
        task_data = {"text": "Hello", "secret": "hidden"}
        structure = {
            "instruction_prompt": "$text",
            "exclude_fields": ["secret"],
        }
        prompts, data = self.parser.process_generation_structure(task_data, structure)
        assert "secret" not in data

    def test_json_string_structure(self):
        task_data = {"text": "Hello"}
        structure_json = json.dumps({"instruction_prompt": "$text"})
        prompts, data = self.parser.process_generation_structure(task_data, structure_json)
        assert prompts["instruction_prompt"] == "Hello"


class TestValidateStructure:
    def setup_method(self):
        self.parser = GenerationStructureParser()

    def test_valid_with_system_prompt(self):
        is_valid, err = self.parser.validate_structure({"system_prompt": "Hello"})
        assert is_valid is True
        assert err is None

    def test_valid_with_fields(self):
        is_valid, err = self.parser.validate_structure({"fields": {"q": "$text"}})
        assert is_valid is True

    def test_invalid_no_prompts(self):
        is_valid, err = self.parser.validate_structure({"other": "value"})
        assert is_valid is False
        assert "at least one prompt" in err

    def test_invalid_parse_failure(self):
        is_valid, err = self.parser.validate_structure("not json")
        assert is_valid is False

    def test_prompt_dict_missing_template(self):
        is_valid, err = self.parser.validate_structure({
            "system_prompt": {"fields": {"k": "v"}}
        })
        assert is_valid is False
        assert "template" in err

    def test_prompt_dict_fields_not_dict(self):
        is_valid, err = self.parser.validate_structure({
            "system_prompt": {"template": "T", "fields": "not-a-dict"}
        })
        assert is_valid is False
        assert "fields must be an object" in err

    def test_prompt_invalid_type(self):
        is_valid, err = self.parser.validate_structure({"system_prompt": 42})
        assert is_valid is False
        assert "string or object" in err

    def test_exclude_fields_not_list(self):
        is_valid, err = self.parser.validate_structure({
            "system_prompt": "ok",
            "exclude_fields": "not-a-list",
        })
        assert is_valid is False
        assert "array" in err

    def test_parameters_not_dict(self):
        is_valid, err = self.parser.validate_structure({
            "system_prompt": "ok",
            "parameters": "not-a-dict",
        })
        assert is_valid is False
        assert "object" in err

    def test_valid_complete_structure(self):
        is_valid, err = self.parser.validate_structure({
            "system_prompt": {"template": "{{x}}", "fields": {"x": "$text"}},
            "instruction_prompt": "Simple",
            "exclude_fields": ["secret"],
            "parameters": {"temp": 0.0},
        })
        assert is_valid is True
