"""Mutation-kill tests for generation_structure_parser.GenerationStructureParser.

These complement the invariant/fuzz checks in
``test_generation_structure_parser_properties.py`` with HAND-COMPUTED
exact-value assertions on specific branches. Each test uses a known input and
an expected output derived by reading the source — so flipping an operator,
changing a constant, taking the wrong branch, mutating a regex, or returning
the wrong value makes a concrete assertion FAIL.

The test bodies/docstrings name the exact branch / operator / return each
pins. Notable source facts the assertions depend on:

* ``parse_structure`` returns None for any FALSY input — including an empty
  dict ``{}`` (``if not generation_structure: return None``).
* ``validate_structure`` runs ``parse_structure`` first, so ``{}`` yields the
  "Failed to parse structure" message, NOT "must define at least one prompt".
* ``interpolate_template`` only ever *replaces* matched ``{{name}}`` tokens; a
  token not in the dict is left verbatim whether or not ``allow_missing`` is
  set (the flag only suppresses a warning log).
* ``extract_nested_value`` array access guards with ``0 <= index < len(...)``
  — index 0 and ``len-1`` are in range; ``-1`` and ``len`` are not.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generation_structure_parser import GenerationStructureParser  # noqa: E402


@pytest.fixture
def parser():
    return GenerationStructureParser()


# ===========================================================================
# parse_structure — empty/None falsy guard, JSON decode, dict passthrough,
# string caching, non-dict rejection
# ===========================================================================

class TestParseStructure:
    def test_none_returns_none(self, parser):
        # `if not generation_structure: return None`.
        assert parser.parse_structure(None) is None

    def test_empty_dict_is_falsy_returns_none(self, parser):
        # {} is falsy -> early return None (NOT passed through as a dict).
        assert parser.parse_structure({}) is None

    def test_empty_string_returns_none(self, parser):
        assert parser.parse_structure("") is None

    def test_valid_json_string_decoded_to_dict(self, parser):
        out = parser.parse_structure('{"system_prompt": "$area"}')
        assert out == {"system_prompt": "$area"}

    def test_invalid_json_string_returns_none(self, parser):
        # json.JSONDecodeError branch -> None (logged), not a raise.
        assert parser.parse_structure("{not valid json") is None

    def test_json_string_non_object_returns_none(self, parser):
        # Valid JSON but a list -> `not isinstance(structure, dict)` -> None.
        assert parser.parse_structure("[1, 2, 3]") is None

    def test_dict_passed_through_identically(self, parser):
        d = {"instruction_prompt": "$x"}
        assert parser.parse_structure(d) is d

    def test_string_result_is_cached_same_object(self, parser):
        s = '{"fields": {"a": "$b"}}'
        first = parser.parse_structure(s)
        second = parser.parse_structure(s)
        # The cache returns the SAME object on the second call.
        assert first is second


# ===========================================================================
# interpolate_template — substitution, None->"", dict/list JSON, missing tokens
# ===========================================================================

class TestInterpolateTemplate:
    def test_two_placeholders_exact(self, parser):
        # "{{a}}-{{b}}" with {a:1,b:2} -> "1-2". The '-' literal is untouched.
        assert parser.interpolate_template("{{a}}-{{b}}", {"a": 1, "b": 2}) == "1-2"

    def test_string_value_substituted(self, parser):
        assert parser.interpolate_template(
            "Area: {{area}}", {"area": "contract_law"}
        ) == "Area: contract_law"

    def test_none_value_becomes_empty_string(self, parser):
        # `elif value is None: value_str = ""` -> "x {{a}} y" -> "x  y".
        assert parser.interpolate_template("x {{a}} y", {"a": None}) == "x  y"

    def test_dict_value_json_serialized_indent2(self, parser):
        # dict/list -> json.dumps(..., indent=2). Hand-computed exact string.
        assert parser.interpolate_template(
            "{{a}}", {"a": {"k": "v"}}
        ) == '{\n  "k": "v"\n}'

    def test_list_value_json_serialized_indent2(self, parser):
        assert parser.interpolate_template(
            "{{a}}", {"a": [1, 2]}
        ) == "[\n  1,\n  2\n]"

    def test_missing_placeholder_left_verbatim_default(self, parser):
        # Not in dict -> never replaced. allow_missing False only warns.
        assert parser.interpolate_template("{{x}}", {}) == "{{x}}"

    def test_missing_placeholder_left_verbatim_allow_missing(self, parser):
        assert parser.interpolate_template(
            "{{x}}", {}, allow_missing=True
        ) == "{{x}}"

    def test_mixed_present_and_missing(self, parser):
        # Present substituted, missing kept. {{a}}-{{b}} with only a.
        assert parser.interpolate_template(
            "{{a}}-{{b}}", {"a": "X"}
        ) == "X-{{b}}"

    def test_no_placeholders_returned_unchanged(self, parser):
        assert parser.interpolate_template("plain text", {"a": 1}) == "plain text"

    def test_integer_value_stringified(self, parser):
        # else-branch: str(value). 0 -> "0" (kills a falsy mishandle of 0).
        assert parser.interpolate_template("{{n}}", {"n": 0}) == "0"

    def test_bool_value_stringified_python_style(self, parser):
        assert parser.interpolate_template("{{b}}", {"b": True}) == "True"

    def test_unicode_value_not_escaped(self, parser):
        # json.dumps uses ensure_ascii=False for dict/list values.
        assert parser.interpolate_template(
            "{{a}}", {"a": {"k": "ä"}}
        ) == '{\n  "k": "ä"\n}'


# ===========================================================================
# extract_nested_value — dotted paths, array index bounds, missing -> None
# ===========================================================================

class TestExtractNestedValue:
    @pytest.fixture
    def data(self):
        return {
            "a": {"b": {"c": 42}},
            "arr": [10, 20, 30],
            "objs": [{"n": "x"}, {"n": "y"}],
        }

    def test_simple_key(self, parser, data):
        assert parser.extract_nested_value(data, "a") == {"b": {"c": 42}}

    def test_dotted_leaf(self, parser, data):
        assert parser.extract_nested_value(data, "a.b.c") == 42

    def test_array_index_in_range(self, parser, data):
        assert parser.extract_nested_value(data, "arr[1]") == 20

    def test_array_index_zero_boundary(self, parser, data):
        # `0 <= index` lower bound — index 0 is valid.
        assert parser.extract_nested_value(data, "arr[0]") == 10

    def test_array_index_last_boundary(self, parser, data):
        # `index < len(current)` upper bound — len-1 is valid.
        assert parser.extract_nested_value(data, "arr[2]") == 30

    def test_array_index_equal_len_out_of_range_none(self, parser, data):
        # index == len -> `index < len` is False -> None (not IndexError).
        assert parser.extract_nested_value(data, "arr[3]") is None

    def test_array_index_negative_out_of_range_none(self, parser, data):
        # index -1 -> `0 <= index` is False -> None. Pins the lower bound check
        # against a Python negative-index access.
        assert parser.extract_nested_value(data, "arr[-1]") is None

    def test_array_element_then_field(self, parser, data):
        assert parser.extract_nested_value(data, "objs[1].n") == "y"

    def test_missing_intermediate_returns_none(self, parser, data):
        assert parser.extract_nested_value(data, "a.x") is None

    def test_missing_top_level_returns_none(self, parser, data):
        assert parser.extract_nested_value(data, "nope") is None

    def test_empty_path_returns_none(self, parser, data):
        # `if not data or not path: return None` — empty path.
        assert parser.extract_nested_value(data, "") is None

    def test_none_data_returns_none(self, parser):
        assert parser.extract_nested_value(None, "a") is None

    def test_index_into_non_list_returns_none(self, parser):
        # arr field is a dict, [0] applied -> not a list -> None.
        assert parser.extract_nested_value({"arr": {"x": 1}}, "arr[0]") is None

    def test_standalone_bracket_index_on_top_list(self, parser):
        # A path that is just "[0]" with field_name None applies the index to
        # `current` directly. With current a dict, not a list -> None.
        assert parser.extract_nested_value({"k": 1}, "[0]") is None


# ===========================================================================
# extract_field_mappings — strips leading $, dict/template/fields formats
# ===========================================================================

class TestExtractFieldMappings:
    def test_simple_system_prompt_ref(self, parser):
        # "$area" -> mapping {"area": "area"} (key == value, $ stripped).
        assert parser.extract_field_mappings({"system_prompt": "$area"}) == {
            "area": "area"
        }

    def test_template_fields_mapping(self, parser):
        # dict prompt with 'fields' -> placeholder -> field path ($ stripped).
        struct = {
            "instruction_prompt": {
                "template": "{{t}}",
                "fields": {"t": "$prompts.clean"},
            }
        }
        assert parser.extract_field_mappings(struct) == {"t": "prompts.clean"}

    def test_legacy_fields_format(self, parser):
        # top-level 'fields' dict whose values start with $.
        assert parser.extract_field_mappings(
            {"fields": {"f": "$x"}}
        ) == {"f": "x"}

    def test_non_dollar_field_ignored_in_legacy(self, parser):
        # A value NOT starting with $ is skipped in the legacy branch.
        assert parser.extract_field_mappings({"fields": {"f": "literal"}}) == {}

    def test_combined_sources_merged(self, parser):
        struct = {
            "system_prompt": "$area",
            "instruction_prompt": {"template": "{{t}}", "fields": {"t": "$p.c"}},
            "fields": {"f": "$x"},
        }
        assert parser.extract_field_mappings(struct) == {
            "area": "area", "t": "p.c", "f": "x"
        }

    def test_non_dollar_simple_prompt_yields_no_mapping(self, parser):
        # A literal (non-$) system_prompt string adds nothing.
        assert parser.extract_field_mappings(
            {"system_prompt": "You are an expert"}
        ) == {}


# ===========================================================================
# filter_task_data — sensitive-field blocking, nested-sensitive, exclude_fields
# ===========================================================================

class TestFilterTaskData:
    @pytest.fixture
    def task(self):
        return {
            "area": "law",
            "annotations": {"x": 1},
            "ground_truth": "secret",
            "nested": {"reasoning": "leak", "ok": "fine"},
        }

    def test_safe_field_kept(self, parser, task):
        out = parser.filter_task_data(task, {"a": "area"})
        assert out == {"a": "law"}

    def test_sensitive_path_part_blocked(self, parser, task):
        # 'ground_truth' is in SENSITIVE_FIELDS -> the placeholder is dropped.
        out = parser.filter_task_data(
            task, {"a": "area", "b": "ground_truth", "c": "annotations"}
        )
        assert out == {"a": "law"}

    def test_sensitive_parent_in_dotted_path_blocked(self, parser, task):
        # 'annotations.x' -> path_parts contains 'annotations' (sensitive).
        out = parser.filter_task_data(task, {"k": "annotations.x"})
        assert out == {}

    def test_nested_sensitive_value_blocked(self, parser, task):
        # 'nested' maps to a dict containing key 'reasoning' (sensitive nested).
        # _contains_sensitive_data -> True -> dropped.
        out = parser.filter_task_data(task, {"d": "nested"})
        assert out == {}

    def test_missing_field_not_added(self, parser):
        # value is None -> the `if value is not None` guard drops it.
        assert parser.filter_task_data({"a": 1}, {"k": "absent"}) == {}

    def test_custom_exclude_field_blocked(self, parser):
        # exclude_fields extends the excluded set.
        assert parser.filter_task_data(
            {"foo": "v"}, {"k": "foo"}, exclude_fields=["foo"]
        ) == {}

    def test_placeholder_renames_field(self, parser):
        # The OUTPUT key is the placeholder name, not the field path.
        out = parser.filter_task_data({"area": "law"}, {"region": "area"})
        assert out == {"region": "law"}


# ===========================================================================
# _contains_sensitive_data — dict key match, list recursion, scalars
# ===========================================================================

class TestContainsSensitiveData:
    def test_sensitive_dict_key_true(self, parser):
        assert parser._contains_sensitive_data({"reasoning": "x"}) is True

    def test_substring_match_on_key(self, parser):
        # `sensitive in key.lower()` is a SUBSTRING test -> "my_answer" matches.
        assert parser._contains_sensitive_data({"my_answer": "x"}) is True

    def test_clean_dict_false(self, parser):
        assert parser._contains_sensitive_data({"ok": "x", "value": 1}) is False

    def test_list_with_sensitive_dict_true(self, parser):
        assert parser._contains_sensitive_data([{"solution": "x"}]) is True

    def test_list_of_clean_dicts_false(self, parser):
        assert parser._contains_sensitive_data([{"ok": 1}, {"fine": 2}]) is False

    def test_scalar_string_false(self, parser):
        assert parser._contains_sensitive_data("plain string") is False

    def test_empty_list_false(self, parser):
        # `elif isinstance(value, list) and value` — empty list short-circuits.
        assert parser._contains_sensitive_data([]) is False


# ===========================================================================
# _build_single_prompt — $ref, literal, JSON serialization, missing ref
# ===========================================================================

class TestBuildSinglePrompt:
    def test_dollar_ref_extracts_value(self, parser):
        assert parser._build_single_prompt({"area": "law"}, "$area") == "law"

    def test_literal_string_returned_as_is(self, parser):
        # No leading $ -> literal branch.
        assert parser._build_single_prompt({}, "literal text") == "literal text"

    def test_dollar_ref_dict_value_json_serialized(self, parser):
        assert parser._build_single_prompt(
            {"x": {"k": 1}}, "$x"
        ) == '{\n  "k": 1\n}'

    def test_dollar_ref_missing_returns_empty_string(self, parser):
        # value is None -> return "".
        assert parser._build_single_prompt({}, "$missing") == ""

    def test_template_dict_interpolated(self, parser):
        cfg = {"template": "Hi {{name}}", "fields": {"name": "$who"}}
        assert parser._build_single_prompt(
            {"who": "Ada"}, cfg
        ) == "Hi Ada"

    def test_template_dict_missing_field_left_unsubstituted(self, parser):
        # field ref resolves to None -> not added to placeholders -> token kept.
        cfg = {"template": "Hi {{name}}", "fields": {"name": "$absent"}}
        assert parser._build_single_prompt({}, cfg) == "Hi {{name}}"

    def test_template_no_fields_returns_template_verbatim(self, parser):
        cfg = {"template": "static prompt"}
        assert parser._build_single_prompt({}, cfg) == "static prompt"

    def test_non_str_non_dict_config_returns_empty(self, parser):
        # Neither str nor dict -> final `return ""`.
        assert parser._build_single_prompt({}, 12345) == ""

    def test_dollar_ref_integer_value_stringified(self, parser):
        # Non-dict/list value -> str(value). 0 must become "0", not "".
        assert parser._build_single_prompt({"n": 0}, "$n") == "0"


# ===========================================================================
# build_prompts — system/instruction prompts + context_fields appending
# ===========================================================================

class TestBuildPrompts:
    def test_system_and_instruction_from_refs(self, parser):
        struct = {"system_prompt": "$a", "instruction_prompt": "$b"}
        out = parser.build_prompts({"a": "sys", "b": "inst"}, struct)
        assert out == {"system_prompt": "sys", "instruction_prompt": "inst"}

    def test_context_fields_appended_to_existing_instruction(self, parser):
        # Existing instruction + context -> joined with the exact separator.
        struct = {"instruction_prompt": "$p", "context_fields": ["$c1", "$c2"]}
        out = parser.build_prompts({"p": "do it", "c1": "A", "c2": "B"}, struct)
        assert out["instruction_prompt"] == "do it\n\nContext:\nA\n\nB"

    def test_context_fields_without_instruction_creates_one(self, parser):
        # No instruction_prompt -> the else-branch seeds "Context:\n...".
        struct = {"context_fields": ["$c1"]}
        out = parser.build_prompts({"c1": "A"}, struct)
        assert out == {"instruction_prompt": "Context:\nA"}

    def test_context_field_missing_value_skipped(self, parser):
        # A context $ref resolving to None is not appended.
        struct = {"instruction_prompt": "$p", "context_fields": ["$absent"]}
        out = parser.build_prompts({"p": "do it"}, struct)
        assert out == {"instruction_prompt": "do it"}

    def test_no_prompts_returns_empty_dict(self, parser):
        assert parser.build_prompts({"a": 1}, {}) == {}

    def test_context_non_dollar_field_ignored(self, parser):
        # context_fields entry not starting with $ -> skipped, instruction kept.
        struct = {"instruction_prompt": "$p", "context_fields": ["literal"]}
        out = parser.build_prompts({"p": "do it"}, struct)
        assert out == {"instruction_prompt": "do it"}


# ===========================================================================
# process_generation_structure — full pipeline + fallback paths
# ===========================================================================

class TestProcessGenerationStructure:
    def test_no_structure_uses_fallback_instruction(self, parser):
        # parse_structure(None) -> None -> fallback branch.
        prompts, filtered = parser.process_generation_structure(
            {"a": 1}, None, fallback_instruction="FALLBACK"
        )
        assert prompts == {"instruction_prompt": "FALLBACK"}
        assert filtered == {}

    def test_no_structure_no_fallback_empty(self, parser):
        prompts, filtered = parser.process_generation_structure({"a": 1}, None)
        assert prompts == {}
        assert filtered == {}

    def test_full_pipeline_prompts_and_filtered(self, parser):
        struct = {
            "system_prompt": {"template": "Role: {{r}}", "fields": {"r": "$area"}},
            "instruction_prompt": {
                "template": "Q: {{q}}", "fields": {"q": "$question"}
            },
        }
        task = {"area": "law", "question": "Is it valid?"}
        prompts, filtered = parser.process_generation_structure(task, struct)
        assert prompts == {
            "system_prompt": "Role: law",
            "instruction_prompt": "Q: Is it valid?",
        }
        assert filtered == {"r": "law", "q": "Is it valid?"}

    def test_fallback_added_when_no_instruction_prompt_generated(self, parser):
        # Structure has only a system_prompt -> instruction_prompt absent ->
        # fallback is injected.
        struct = {"system_prompt": "$area"}
        prompts, _ = parser.process_generation_structure(
            {"area": "law"}, struct, fallback_instruction="DEFAULT"
        )
        assert prompts["system_prompt"] == "law"
        assert prompts["instruction_prompt"] == "DEFAULT"

    def test_sensitive_field_does_not_leak_into_filtered(self, parser):
        struct = {
            "instruction_prompt": {
                "template": "{{ans}}", "fields": {"ans": "$ground_truth"}
            }
        }
        task = {"ground_truth": "B"}
        prompts, filtered = parser.process_generation_structure(task, struct)
        # filter_task_data blocks the sensitive ground_truth mapping.
        assert "ans" not in filtered
        assert filtered == {}


# ===========================================================================
# validate_structure — parse-first, prompt-presence, template + type checks
# ===========================================================================

class TestValidateStructure:
    def test_empty_dict_fails_at_parse_stage(self, parser):
        # {} is falsy -> parse_structure returns None -> "Failed to parse".
        # This is NOT the "must define at least one prompt" message.
        ok, err = parser.validate_structure({})
        assert ok is False
        assert err == "Failed to parse structure"

    def test_no_prompt_keys_fails(self, parser):
        # A non-empty dict with no prompt keys reaches the prompt-presence check.
        ok, err = parser.validate_structure({"parameters": {}})
        assert ok is False
        assert err == "Structure must define at least one prompt"

    def test_valid_simple_instruction_passes(self, parser):
        ok, err = parser.validate_structure({"instruction_prompt": "$a"})
        assert ok is True
        assert err is None

    def test_dict_prompt_missing_template_fails(self, parser):
        ok, err = parser.validate_structure({"system_prompt": {"fields": {}}})
        assert ok is False
        assert err == "system_prompt dict must have 'template' field"

    def test_dict_prompt_fields_not_object_fails(self, parser):
        ok, err = parser.validate_structure(
            {"system_prompt": {"template": "x", "fields": "notdict"}}
        )
        assert ok is False
        assert err == "system_prompt.fields must be an object"

    def test_prompt_wrong_type_fails(self, parser):
        # prompt_config is neither dict nor str -> the elif-not-str branch.
        ok, err = parser.validate_structure({"instruction_prompt": 123})
        assert ok is False
        assert err == "instruction_prompt must be string or object"

    def test_exclude_fields_not_list_fails(self, parser):
        ok, err = parser.validate_structure(
            {"instruction_prompt": "$a", "exclude_fields": "str"}
        )
        assert ok is False
        assert err == "'exclude_fields' must be an array"

    def test_parameters_not_dict_fails(self, parser):
        ok, err = parser.validate_structure(
            {"system_prompt": "$a", "parameters": []}
        )
        assert ok is False
        assert err == "'parameters' must be an object"

    def test_valid_with_template_and_optional_fields_passes(self, parser):
        struct = {
            "instruction_prompt": {"template": "{{t}}", "fields": {"t": "$x"}},
            "exclude_fields": ["note"],
            "parameters": {"temperature": 0.0},
        }
        ok, err = parser.validate_structure(struct)
        assert ok is True
        assert err is None

    def test_fields_only_structure_counts_as_prompt(self, parser):
        # 'fields' is one of the accepted prompt keys -> presence check passes.
        ok, err = parser.validate_structure({"fields": {"f": "$x"}})
        assert ok is True
        assert err is None
