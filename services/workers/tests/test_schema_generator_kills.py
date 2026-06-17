"""Mutation-grade kills for the GENERATION-side structured-output schema
builder in ``services/shared/ai_services/schema_generator.py``.

This module turns a Label-Studio ``label_config`` XML into the JSON schema
that *constrains* an LLM's structured generation (plus the human-readable
format instructions and an example). A wrong schema constrains the model
wrong -> wrong or rejected generation -> a corrupted benchmark input. The
file shipped with NO dedicated test (``test_task_template_schema_extended.py``
tests a different module, ``task_template_schema``).

Every expected value below is HAND-COMPUTED from the source so that each
assertion pins one operator/constant/branch/regex and would die under the
corresponding mutation. The strongest kill is the example round-trip:
``jsonschema.validate(example, schema)`` must not raise for the example
produced from that very schema.

Import note: importing through the ``ai_services`` package pulls every
provider SDK + an EncryptionService. We file-import the module directly via
``importlib.util.spec_from_file_location`` (it is pure: only ``json``,
``xml.etree``, ``typing`` -- no relative imports), mirroring
``tests/test_response_validator_kills.py``.
"""

from __future__ import annotations

import importlib.util
import json
import os

import jsonschema
import pytest

# --- Direct file-import of the module under test (no SDK cascade) ----------
_workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_services_root = os.path.dirname(_workers_root)
_sg_path = os.path.join(
    _services_root, "shared", "ai_services", "schema_generator.py"
)
_spec = importlib.util.spec_from_file_location("_schema_generator_kills", _sg_path)
_sg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sg)

generate_json_schema_from_label_config = _sg.generate_json_schema_from_label_config
generate_format_instructions = _sg.generate_format_instructions
extract_field_names = _sg.extract_field_names
_empty_schema = _sg._empty_schema
_generate_example = _sg._generate_example
_parse_element = _sg._parse_element


# ===========================================================================
# Per-element TYPE -> property schema fragment
#   (strict_mode defaults True: required = ALL keys, additionalProperties=False)
# ===========================================================================
class TestPerElementType:
    def test_textarea_is_string_with_placeholder_description(self):
        """TextArea -> {"type":"string","description":<placeholder>} when
        include_descriptions (default True). Pins the TextArea branch + the
        placeholder->description copy."""
        cfg = (
            '<View>'
            '<TextArea name="answer" toName="task" placeholder="Enter answer..."/>'
            '</View>'
        )
        schema = generate_json_schema_from_label_config(cfg)
        assert schema["properties"]["answer"] == {
            "type": "string",
            "description": "Enter answer...",
        }

    def test_choices_is_string_enum_exact_options_in_order(self):
        """Choices -> {"type":"string","enum":[...]} with the Choice values in
        document order. Pins the enum extraction + order."""
        cfg = (
            '<View>'
            '<Choices name="verdict" toName="task">'
            '<Choice value="Ja"/>'
            '<Choice value="Nein"/>'
            '<Choice value="Teilweise"/>'
            '</Choices>'
            '</View>'
        )
        schema = generate_json_schema_from_label_config(cfg)
        assert schema["properties"]["verdict"] == {
            "type": "string",
            "enum": ["Ja", "Nein", "Teilweise"],
        }

    def test_choices_without_values_falls_back_to_plain_string(self):
        """Choices whose Choice children have no value attr -> the empty-enum
        fallback {"type":"string"} (no enum key). Pins the `if choices:` branch."""
        cfg = (
            '<View>'
            '<Choices name="verdict" toName="task">'
            '<Choice/>'
            '</Choices>'
            '</View>'
        )
        schema = generate_json_schema_from_label_config(cfg)
        assert schema["properties"]["verdict"] == {"type": "string"}

    def test_rating_is_integer_with_min_1_and_max_from_maxRating(self):
        """Rating -> {"type":"integer","minimum":1,"maximum":maxRating}.
        maxRating="7" pins the int() parse + that it becomes the maximum,
        and that minimum is the constant 1 (NOT 0)."""
        cfg = '<View><Rating name="score" toName="task" maxRating="7"/></View>'
        schema = generate_json_schema_from_label_config(cfg)
        assert schema["properties"]["score"] == {
            "type": "integer",
            "minimum": 1,
            "maximum": 7,
        }

    def test_rating_default_maxRating_is_5(self):
        """No maxRating attr -> default 5. Pins the int(elem.get('maxRating', 5))
        default constant."""
        cfg = '<View><Rating name="score" toName="task"/></View>'
        schema = generate_json_schema_from_label_config(cfg)
        assert schema["properties"]["score"]["maximum"] == 5
        assert schema["properties"]["score"]["minimum"] == 1

    def test_number_is_number_with_float_min_max(self):
        """Number -> {"type":"number", "minimum":float(min), "maximum":float(max)}.
        Pins the Number branch + the float() coercion (0 -> 0.0, 10 -> 10.0)."""
        cfg = '<View><Number name="confidence" toName="task" min="0" max="10"/></View>'
        schema = generate_json_schema_from_label_config(cfg)
        prop = schema["properties"]["confidence"]
        assert prop["type"] == "number"
        assert prop["minimum"] == 0.0
        assert prop["maximum"] == 10.0
        assert isinstance(prop["minimum"], float)
        assert isinstance(prop["maximum"], float)

    def test_number_omits_bounds_when_attrs_absent(self):
        """Number with no min/max -> just {"type":"number"} (no bounds keys).
        Pins the `if min_val is not None` guards."""
        cfg = '<View><Number name="confidence" toName="task"/></View>'
        schema = generate_json_schema_from_label_config(cfg)
        assert schema["properties"]["confidence"] == {"type": "number"}

    def test_text_element_is_display_only_and_excluded(self):
        """Text (display-only, value="$...") is NOT an answer field and must be
        excluded from the schema. Pins that _parse_element returns None for it."""
        cfg = (
            '<View>'
            '<Text name="task_text" value="$text"/>'
            '<TextArea name="answer" toName="task"/>'
            '</View>'
        )
        schema = generate_json_schema_from_label_config(cfg)
        assert "task_text" not in schema["properties"]
        assert "answer" in schema["properties"]
        assert list(schema["properties"].keys()) == ["answer"]

    def test_unknown_labels_element_is_excluded(self):
        """An element type the builder does not handle (e.g. Labels) yields no
        property -- _parse_element returns None for unmapped tags. Pins the
        final `return None`."""
        cfg = (
            '<View>'
            '<Labels name="spans" toName="task"><Label value="X"/></Labels>'
            '<TextArea name="answer" toName="task"/>'
            '</View>'
        )
        schema = generate_json_schema_from_label_config(cfg)
        assert "spans" not in schema["properties"]
        assert list(schema["properties"].keys()) == ["answer"]

    def test_element_without_name_attr_is_skipped(self):
        """An annotation element with no name attr -> None (cannot key it).
        Pins the `if not name: return None` guard. The root <View> also has no
        name and must not leak in."""
        cfg = '<View><TextArea toName="task"/><Choices toName="task"><Choice value="A"/></Choices></View>'
        schema = generate_json_schema_from_label_config(cfg)
        assert schema["properties"] == {}
        # No named fields at all -> _empty_schema()
        assert schema == _empty_schema()


# ===========================================================================
# Multi-field config: all fields present, none dropped, correct types
# ===========================================================================
class TestMultiFieldConfig:
    CFG = (
        '<View>'
        '<Text name="task_text" value="$text"/>'  # display-only, excluded
        '<TextArea name="reasoning" toName="task" placeholder="Explain"/>'
        '<Choices name="verdict" toName="task">'
        '<Choice value="Ja"/><Choice value="Nein"/>'
        '</Choices>'
        '<Rating name="confidence_rating" toName="task" maxRating="5"/>'
        '<Number name="score" toName="task" min="0" max="100"/>'
        '</View>'
    )

    def test_all_answer_fields_present_in_order_text_excluded(self):
        """Every answer field appears; the display-only Text is dropped; order
        follows document order (root.iter() is pre-order)."""
        schema = generate_json_schema_from_label_config(self.CFG)
        assert list(schema["properties"].keys()) == [
            "reasoning",
            "verdict",
            "confidence_rating",
            "score",
        ]

    def test_each_field_has_correct_type(self):
        """Cross-field type pinning in one shot."""
        props = generate_json_schema_from_label_config(self.CFG)["properties"]
        assert props["reasoning"]["type"] == "string"
        assert props["verdict"]["type"] == "string"
        assert props["verdict"]["enum"] == ["Ja", "Nein"]
        assert props["confidence_rating"]["type"] == "integer"
        assert props["score"]["type"] == "number"

    def test_object_envelope_shape(self):
        """type:object, strict-mode required=ALL keys, additionalProperties=False."""
        schema = generate_json_schema_from_label_config(self.CFG)
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        assert schema["required"] == [
            "reasoning",
            "verdict",
            "confidence_rating",
            "score",
        ]


# ===========================================================================
# REQUIRED handling -- the per-element required flag only drives the
# `required` array when strict_mode=False (strict forces ALL keys required).
# ===========================================================================
class TestRequiredHandling:
    CFG = (
        '<View>'
        '<TextArea name="req_field" toName="task" required="true"/>'
        '<TextArea name="opt_field" toName="task" required="false"/>'
        '<TextArea name="default_field" toName="task"/>'
        '</View>'
    )

    def test_strict_mode_forces_all_keys_required(self):
        """strict_mode default True -> required is the full key list regardless
        of per-field required attr. Pins `schema["required"]=list(properties.keys())`."""
        schema = generate_json_schema_from_label_config(self.CFG)
        assert schema["required"] == ["req_field", "opt_field", "default_field"]
        assert schema["additionalProperties"] is False

    def test_non_strict_mode_honours_per_field_required_flag(self):
        """strict_mode False -> only fields with required="true" go in `required`.
        Pins the flipped-required check: req in, opt/default out. Also pins that
        non-strict does NOT add additionalProperties."""
        schema = generate_json_schema_from_label_config(self.CFG, strict_mode=False)
        assert schema["required"] == ["req_field"]
        assert "additionalProperties" not in schema

    def test_non_strict_mode_no_required_fields_omits_required_key(self):
        """strict_mode False with zero required fields -> the `required` key is
        absent entirely (the `elif required:` branch is not taken)."""
        cfg = (
            '<View>'
            '<TextArea name="a" toName="task"/>'
            '<TextArea name="b" toName="task" required="false"/>'
            '</View>'
        )
        schema = generate_json_schema_from_label_config(cfg, strict_mode=False)
        assert "required" not in schema

    def test_required_is_case_insensitive_true(self):
        """required="TRUE" must count -- the source lowercases before comparing.
        Pins the `.lower() == "true"` (kills dropping .lower())."""
        cfg = '<View><TextArea name="a" toName="task" required="TRUE"/></View>'
        schema = generate_json_schema_from_label_config(cfg, strict_mode=False)
        assert schema["required"] == ["a"]


# ===========================================================================
# include_descriptions True vs False
# ===========================================================================
class TestIncludeDescriptions:
    CFG = '<View><TextArea name="answer" toName="task" placeholder="Explain"/></View>'

    def test_descriptions_included_by_default(self):
        schema = generate_json_schema_from_label_config(self.CFG)
        assert schema["properties"]["answer"]["description"] == "Explain"

    def test_descriptions_excluded_when_flag_false(self):
        """include_descriptions=False -> no description key. Pins the branch
        `if include_descriptions and placeholder`."""
        schema = generate_json_schema_from_label_config(
            self.CFG, include_descriptions=False
        )
        assert "description" not in schema["properties"]["answer"]
        assert schema["properties"]["answer"] == {"type": "string"}

    def test_no_placeholder_means_no_description_even_when_included(self):
        """No placeholder attr -> no description, even with include_descriptions
        True. Pins the `and placeholder` half of the guard."""
        cfg = '<View><TextArea name="answer" toName="task"/></View>'
        schema = generate_json_schema_from_label_config(cfg)
        assert "description" not in schema["properties"]["answer"]


# ===========================================================================
# _empty_schema / display-only-or-empty configs
# ===========================================================================
class TestEmptySchema:
    EMPTY = {"type": "object", "properties": {}, "additionalProperties": True}

    def test_empty_schema_exact_shape(self):
        """The documented empty schema: object, no properties,
        additionalProperties=True (NOT False -- opposite of strict mode)."""
        assert _empty_schema() == self.EMPTY

    def test_blank_config_returns_empty_schema(self):
        assert generate_json_schema_from_label_config("") == self.EMPTY
        assert generate_json_schema_from_label_config("   ") == self.EMPTY

    def test_display_only_config_returns_empty_schema(self):
        """A config with only display-only Text -> no properties -> empty schema.
        Pins `if not properties: return _empty_schema()`."""
        cfg = '<View><Text name="task_text" value="$text"/></View>'
        assert generate_json_schema_from_label_config(cfg) == self.EMPTY

    def test_invalid_xml_returns_empty_schema_no_crash(self):
        """Malformed XML -> caught ParseError -> empty schema, never a crash.
        Pins the try/except ET.ParseError path."""
        cfg = '<View><TextArea name="answer" toName="task"></View>'  # unclosed
        assert generate_json_schema_from_label_config(cfg) == self.EMPTY


# ===========================================================================
# generate_format_instructions -- the human-readable prompt text
# ===========================================================================
class TestFormatInstructions:
    CFG = (
        '<View>'
        '<TextArea name="reasoning" toName="task" placeholder="Explain your answer"/>'
        '<Choices name="verdict" toName="task">'
        '<Choice value="Ja"/><Choice value="Nein"/>'
        '</Choices>'
        '<Rating name="confidence" toName="task" maxRating="5"/>'
        '<Number name="score" toName="task"/>'
        '</View>'
    )

    def test_header_and_trailer_present(self):
        text = generate_format_instructions(self.CFG)
        assert "## Output Format" in text
        assert "Respond ONLY with valid JSON, no other text." in text

    def test_each_field_listed_with_name(self):
        text = generate_format_instructions(self.CFG)
        for fname in ("reasoning", "verdict", "confidence", "score"):
            assert f"**{fname}**" in text

    def test_enum_field_lists_allowed_values(self):
        """Enum field -> 'one of: Ja, Nein'. Pins the enum type_hint join."""
        text = generate_format_instructions(self.CFG)
        assert "one of: Ja, Nein" in text

    def test_integer_field_shows_range(self):
        """Rating (integer) -> 'integer (1-5)'. Pins the integer min-max hint."""
        text = generate_format_instructions(self.CFG)
        assert "integer (1-5)" in text

    def test_number_field_shows_number_hint(self):
        text = generate_format_instructions(self.CFG)
        assert "- **score**: number" in text

    def test_required_marker_present_in_strict_mode(self):
        """All fields are required under strict mode (the schema used internally
        is strict by default) -> every field carries ' (required)'."""
        text = generate_format_instructions(self.CFG)
        assert "**reasoning**: string (required)" in text

    def test_description_appended_when_present(self):
        """A field with a description renders ' - <description>' after the hint."""
        text = generate_format_instructions(self.CFG)
        assert "Explain your answer" in text
        assert "(required) - Explain your answer" in text

    def test_example_block_included_by_default(self):
        text = generate_format_instructions(self.CFG)
        assert "**Example response:**" in text
        assert "```json" in text

    def test_example_block_omitted_when_disabled(self):
        """include_example=False -> no example block. Pins the `if include_example`
        branch."""
        text = generate_format_instructions(self.CFG, include_example=False)
        assert "**Example response:**" not in text
        assert "```json" not in text
        # trailer still present
        assert "Respond ONLY with valid JSON, no other text." in text

    def test_empty_config_returns_empty_string(self):
        """No properties -> empty string (not the header). Pins
        `if not schema.get('properties'): return ''`."""
        assert generate_format_instructions("") == ""
        assert generate_format_instructions('<View><Text name="t" value="$x"/></View>') == ""

    def test_embedded_example_json_parses_and_has_all_fields(self):
        """The JSON inside the ```json fence must parse and carry exactly the
        answer fields. Pins json.dumps(_generate_example(...))."""
        text = generate_format_instructions(self.CFG)
        block = text.split("```json", 1)[1].split("```", 1)[0].strip()
        parsed = json.loads(block)
        assert set(parsed.keys()) == {"reasoning", "verdict", "confidence", "score"}


# ===========================================================================
# _generate_example -- type-appropriate placeholders + ROUND-TRIP validation
# ===========================================================================
class TestGenerateExample:
    def test_placeholder_values_per_type(self):
        """string -> "...", enum -> first member, integer -> minimum,
        number -> 0.0. Pins each placeholder constant/branch."""
        schema = {
            "type": "object",
            "properties": {
                "s": {"type": "string"},
                "e": {"type": "string", "enum": ["A", "B"]},
                "i": {"type": "integer", "minimum": 1, "maximum": 5},
                "n": {"type": "number"},
            },
        }
        ex = _generate_example(schema)
        assert ex == {"s": "...", "e": "A", "i": 1, "n": 0.0}

    def test_integer_example_uses_minimum_value(self):
        """integer with minimum 3 -> example value 3 (not the default 1).
        Pins field_schema.get('minimum', 1)."""
        schema = {
            "type": "object",
            "properties": {"i": {"type": "integer", "minimum": 3, "maximum": 9}},
        }
        assert _generate_example(schema) == {"i": 3}

    def test_example_empty_for_empty_properties(self):
        assert _generate_example({"type": "object", "properties": {}}) == {}
        assert _generate_example({}) == {}

    @pytest.mark.parametrize(
        "cfg",
        [
            '<View><TextArea name="a" toName="t"/></View>',
            '<View><Choices name="c" toName="t"><Choice value="X"/><Choice value="Y"/></Choices></View>',
            '<View><Rating name="r" toName="t" maxRating="7"/></View>',
            '<View><Number name="n" toName="t" min="0" max="8"/></View>',
            '<View><Number name="n" toName="t" max="8"/></View>',
            # Number with a POSITIVE minimum: after the fix the example uses the
            # minimum (2.0), so it round-trips. (Before the fix the constant 0.0
            # violated minimum=2.0 -- the bug pinned in
            # test_number_example_uses_minimum_value.)
            '<View><Number name="n" toName="t" min="2" max="8"/></View>',
            (
                '<View>'
                '<TextArea name="reasoning" toName="t" placeholder="why"/>'
                '<Choices name="verdict" toName="t"><Choice value="Ja"/><Choice value="Nein"/></Choices>'
                '<Rating name="conf" toName="t" maxRating="5"/>'
                '<Number name="score" toName="t" min="0" max="100"/>'
                '</View>'
            ),
        ],
    )
    def test_example_validates_against_its_own_schema(self, cfg):
        """STRONGEST KILL: the example generated from a schema must VALIDATE
        against that same schema. If a placeholder has the wrong type, is out
        of an enum, or violates min/max, jsonschema.validate raises -> the test
        fails. This catches example-vs-schema drift end-to-end. Includes a Number
        with a POSITIVE minimum, which round-trips now that _generate_example
        respects the minimum (the fixed bug)."""
        schema = generate_json_schema_from_label_config(cfg)
        example = _generate_example(schema)
        # round-trip: must not raise
        jsonschema.validate(instance=example, schema=schema)

    def test_number_example_uses_minimum_value(self):
        """Regression for the example-violates-own-schema bug: _generate_example
        used a CONSTANT 0.0 for any `number` field, ignoring the schema's
        `minimum` (unlike the `integer` branch, which uses get("minimum", 1)).
        A Number with min>0 then produced an example that VIOLATED its own schema
        -- and that example is injected into the prompt (generate_format_instructions)
        as the canonical sample response, teaching the LLM an out-of-range value.
        Fixed: the number branch now mirrors integer -- field_schema.get("minimum",
        0.0). A Number without a min still defaults to 0.0 (see
        test_placeholder_values_per_type)."""
        cfg = '<View><Number name="n" toName="t" min="2" max="8"/></View>'
        schema = generate_json_schema_from_label_config(cfg)
        assert schema["properties"]["n"]["minimum"] == 2.0
        example = _generate_example(schema)
        assert example == {"n": 2.0}  # respects minimum, NOT the old constant 0.0
        # round-trip: the example now VALIDATES against its own schema (was raising)
        jsonschema.validate(instance=example, schema=schema)

    def test_enum_example_is_a_member(self):
        """Defensive: the enum placeholder must be IN the enum (validate would
        reject otherwise). Pins enum_values[0] (a real member)."""
        cfg = '<View><Choices name="c" toName="t"><Choice value="X"/><Choice value="Y"/></Choices></View>'
        schema = generate_json_schema_from_label_config(cfg)
        ex = _generate_example(schema)
        assert ex["c"] in schema["properties"]["c"]["enum"]


# ===========================================================================
# extract_field_names -- exactly the answer-field names, in order
# ===========================================================================
class TestExtractFieldNames:
    def test_returns_answer_fields_in_order_text_excluded(self):
        cfg = (
            '<View>'
            '<Text name="task_text" value="$text"/>'  # excluded
            '<TextArea name="reasoning" toName="task"/>'
            '<Choices name="verdict" toName="task"><Choice value="Ja"/></Choices>'
            '<Rating name="conf" toName="task"/>'
            '<Number name="score" toName="task"/>'
            '</View>'
        )
        assert extract_field_names(cfg) == ["reasoning", "verdict", "conf", "score"]

    def test_empty_for_blank_or_display_only(self):
        assert extract_field_names("") == []
        assert extract_field_names('<View><Text name="t" value="$x"/></View>') == []

    def test_empty_for_invalid_xml(self):
        assert extract_field_names('<View><TextArea name="a"></View>') == []


# ===========================================================================
# _parse_element directly (the per-element contract)
# ===========================================================================
class TestParseElementDirect:
    def _elem(self, xml: str):
        from xml.etree import ElementTree as ET

        return ET.fromstring(xml)

    def test_textarea_required_flag_true(self):
        name, schema, req = _parse_element(
            self._elem('<TextArea name="a" required="true"/>'), True
        )
        assert (name, schema, req) == ("a", {"type": "string"}, True)

    def test_textarea_required_flag_false_by_default(self):
        name, schema, req = _parse_element(
            self._elem('<TextArea name="a"/>'), True
        )
        assert req is False

    def test_text_display_element_returns_none(self):
        assert _parse_element(self._elem('<Text name="t" value="$x"/>'), True) is None

    def test_no_name_returns_none(self):
        assert _parse_element(self._elem('<TextArea/>'), True) is None
