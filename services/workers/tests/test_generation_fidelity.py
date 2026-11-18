"""generation_fidelity: answer-format options of a prompt structure."""

import json

import pytest

from generation_fidelity import (
    AnswerFormat,
    FormatRetry,
    answer_format,
    refusal_matches,
    render_answer_schema,
    schema_instruction,
    validate_answer_schema,
    validate_format_retry,
    validate_refusal_heuristic,
)
from response_parser import ResponseParser

LABEL_CONFIG = """<View>
  <Text name="akte" value="$akte"/>
  <Number name="anteil_mieter" toName="akte"/>
  <Choices name="vorrang" toName="akte">
    <Choice value="mieter"/><Choice value="vermieter"/><Choice value="offen"/>
  </Choices>
</View>"""

# Answer keys named after the parties of the case, filled from task data.
PARTY_SCHEMA = {
    "fields": {
        "anteil_mieter": {"key": "anteil_{{parteien.mieter|lower}}"},
        "vorrang": {
            "values": {
                "{{parteien.mieter|lower}}": "mieter",
                "{{parteien.vermieter|lower}}": "vermieter",
            }
        },
    }
}
TASK = {"akte": "...", "parteien": {"mieter": "Wagner", "vermieter": "Okafor"}}


def test_defaults_keep_the_existing_behaviour():
    assert answer_format({}) == AnswerFormat()
    assert answer_format(None) == AnswerFormat()
    fmt = answer_format({"name": "x", "system_prompt": "s", "instruction_prompt": "i"})
    assert fmt.append_schema_instruction is True
    assert fmt.structured_output == "auto"
    assert fmt.format_retry is None and fmt.refusal_heuristic is None


def test_options_are_read_and_invalid_ones_fall_back():
    fmt = answer_format(
        {
            "append_schema_instruction": False,
            "structured_output": "off",
            "format_retry": {"message": "Bitte nur JSON."},
            "refusal_heuristic": {"pattern": "kann ich nicht", "window": 100},
        }
    )
    assert (fmt.append_schema_instruction, fmt.structured_output) == (False, "off")
    assert fmt.format_retry == FormatRetry(message="Bitte nur JSON.")
    assert fmt.as_record()["format_retry"] == {"message": "Bitte nur JSON."}
    assert fmt.refusal_heuristic.window == 100 and fmt.refusal_heuristic.flags == "i"

    broken = answer_format(
        {
            "append_schema_instruction": "no",
            "structured_output": "maybe",
            "format_retry": {"message": "x", "extra": 1},
            "refusal_heuristic": {"pattern": "("},
            "answer_schema": {"fields": []},
        }
    )
    assert broken == AnswerFormat()


@pytest.mark.parametrize(
    "value, message",
    [
        ("x", "must be an object"),
        ({"message": "  "}, "non-empty"),
        ({}, "non-empty"),
        ({"max": 1, "message": "m"}, "unknown keys"),
        ({"message": "m", "extra": 1}, "unknown keys"),
    ],
)
def test_format_retry_validation(value, message):
    with pytest.raises(ValueError, match=message):
        validate_format_retry(value)


def test_a_stored_format_retry_with_max_is_read_as_one_re_ask():
    fmt = answer_format({"format_retry": {"max": 3, "message": "Bitte nur JSON."}})
    assert fmt.format_retry == FormatRetry(message="Bitte nur JSON.")


@pytest.mark.parametrize(
    "value, message",
    [
        ({"pattern": ""}, "non-empty"),
        ({"pattern": "("}, "not a valid regular expression"),
        ({"pattern": "a", "flags": "x"}, "flags"),
        ({"pattern": "a", "window": 0}, "window"),
    ],
)
def test_refusal_heuristic_validation(value, message):
    with pytest.raises(ValueError, match=message):
        validate_refusal_heuristic(value)


@pytest.mark.parametrize(
    "value, message",
    [
        ({"fields": {}}, "non-empty"),
        ({"fields": {"a": {"key": ""}}}, "non-empty string"),
        ({"fields": {"a": {}}}, "needs a 'key' or 'values'"),
        ({"fields": {"a": {"values": {"x": 1}}}}, "map answer values"),
        ({"other": 1}, "only 'fields'"),
    ],
)
def test_answer_schema_validation(value, message):
    with pytest.raises(ValueError, match=message):
        validate_answer_schema(value)


def test_schema_instruction_text_is_stable():
    text = schema_instruction(["anteil", "begruendung"])
    assert text.startswith("\n\n---\nIMPORTANT: Respond ONLY with valid JSON")
    assert (
        json.dumps(
            {"anteil": "<your response>", "begruendung": "<your response>"}, indent=2
        )
        in text
    )


def test_answer_keys_render_from_task_data():
    keys = render_answer_schema(PARTY_SCHEMA, TASK)
    assert keys.key_to_field == {"anteil_wagner": "anteil_mieter"}
    assert keys.value_maps == {"vorrang": {"wagner": "mieter", "okafor": "vermieter"}}
    assert keys.answer_key("anteil_mieter") == "anteil_wagner"
    assert keys.answer_key("vorrang") == "vorrang"
    assert render_answer_schema(None, TASK) is None


def test_answer_keys_refuse_missing_and_sensitive_paths():
    with pytest.raises(ValueError, match="does not hold"):
        render_answer_schema(PARTY_SCHEMA, {"parteien": {"mieter": "Wagner"}})
    with pytest.raises(ValueError, match="sensitive"):
        render_answer_schema(
            {"fields": {"a": {"key": "{{loesung}}"}}},
            {"loesung": "x"},
            is_sensitive=lambda path: path == "loesung",
        )
    with pytest.raises(ValueError, match="two fields"):
        render_answer_schema(
            {"fields": {"a": {"key": "k_{{n}}"}, "b": {"key": "k_{{n}}"}}}, {"n": 1}
        )


def test_parser_reads_rendered_keys_and_values():
    keys = render_answer_schema(PARTY_SCHEMA, TASK)
    answer = '```json\n{"anteil_wagner": 30, "vorrang": "Okafor"}\n```'
    result = ResponseParser({}, LABEL_CONFIG, answer_keys=keys).parse(answer)
    assert result.status == "success"
    by_field = {item["from_name"]: item["value"] for item in result.parsed_annotation}
    assert by_field["anteil_mieter"] == {"number": 30}
    assert by_field["vorrang"] == {"choices": ["vermieter"]}
    assert result.mapped_keys == {"anteil_wagner": "anteil_mieter"}
    assert result.mapped_values == {"vorrang": {"Okafor": "vermieter"}}

    # Without the rendered keys the same answer yields no number field.
    plain = ResponseParser({}, LABEL_CONFIG).parse(answer)
    assert "anteil_mieter" not in (plain.field_values or {})


def test_structured_schema_uses_the_rendered_keys():
    keys = render_answer_schema(PARTY_SCHEMA, TASK)
    schema = {
        "type": "object",
        "properties": {
            "anteil_mieter": {"type": "number"},
            "vorrang": {"type": "string", "enum": ["mieter", "vermieter", "offen"]},
        },
        "required": ["anteil_mieter", "vorrang"],
    }
    renamed = keys.rename_schema(schema)
    assert list(renamed["properties"]) == ["anteil_wagner", "vorrang"]
    assert renamed["properties"]["vorrang"]["enum"] == ["wagner", "okafor", "offen"]
    assert renamed["required"] == ["anteil_wagner", "vorrang"]
    assert list(schema["properties"]) == ["anteil_mieter", "vorrang"]


def test_refusal_heuristic_reads_the_opening_only():
    heuristic = answer_format(
        {"refusal_heuristic": {"pattern": r"ich kann (dazu )?nicht", "window": 40}}
    ).refusal_heuristic
    assert refusal_matches(heuristic, "Ich kann dazu nicht Stellung nehmen.")
    assert not refusal_matches(heuristic, "x" * 50 + "ich kann nicht")
    assert refusal_matches(heuristic, '{"anteil": 1}', "Ich kann nicht helfen.")
    assert not refusal_matches(None, "Ich kann nicht.")
    assert not refusal_matches(heuristic, None, "")
