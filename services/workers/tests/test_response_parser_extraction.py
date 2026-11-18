"""JSON extraction of model answers in ``shared/response_parser.py``.

Well-formed answers in four shapes models commonly produce must parse into
their fields instead of falling back to a free-text ``__response__``:

- a JSON boolean for a Choices field whose choices are "true"/"false";
- a fenced JSON block whose closing fence follows the JSON directly;
- prose followed by an unfenced JSON object or array;
- a list of choices for a ``<Choices choice="multiple">`` field, stored as
  Label Studio stores it (``value.choices`` is the list).

The configs and answers are invented examples.
"""

import json
import os
import sys

import pytest

_shared_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "shared"
)
if _shared_dir not in sys.path:
    sys.path.insert(0, _shared_dir)

from response_parser import ResponseParser  # noqa: E402

BOOLEAN_CHOICES = """<View>
  <Text name="facts" value="$facts"/>
  <Choices name="liable" toName="facts">
    <Choice value="True"/><Choice value="False"/>
  </Choices>
  <TextArea name="reason" toName="facts"/>
</View>"""

MULTI_CHOICES = """<View>
  <Text name="facts" value="$facts"/>
  <Choices name="issues" toName="facts" choice="multiple">
    <Choice value="contract"/><Choice value="tort"/><Choice value="property"/>
  </Choices>
</View>"""


def _values(result):
    return {r["from_name"]: r["value"] for r in result.parsed_annotation}


class TestBooleanChoices:
    @pytest.mark.parametrize("raw, stored", [("true", "True"), ("false", "False")])
    def test_boolean_is_stored_as_the_matching_choice(self, raw, stored):
        result = ResponseParser({}, BOOLEAN_CHOICES).parse(f'{{"liable": {raw}, "reason": "r"}}')
        assert result.status == "success", result.error
        assert _values(result)["liable"] == {"choices": [stored]}

    def test_boolean_without_a_matching_choice_still_fails_the_schema(self):
        cfg = BOOLEAN_CHOICES.replace('"True"', '"Yes"').replace('"False"', '"No"')
        result = ResponseParser({}, cfg).parse('{"liable": true, "reason": "r"}')
        assert result.status == "success"
        assert [r["from_name"] for r in result.parsed_annotation] == ["__response__"]


class TestClosingFence:
    @pytest.mark.parametrize(
        "answer",
        [
            '```json\n{"liable": "True", "reason": "r"}```',
            '```json\n{"liable": "True", "reason": "r"}  ```',
            '```\n{"liable": "True", "reason": "r"}\n```',
        ],
    )
    def test_fence_closing_right_after_the_json(self, answer):
        result = ResponseParser({}, BOOLEAN_CHOICES).parse(answer)
        assert result.status == "success", result.error
        assert _values(result)["liable"] == {"choices": ["True"]}
        assert _values(result)["reason"] == {"text": ["r"]}


class TestJsonAfterProse:
    def test_object_after_prose(self):
        answer = (
            'Weighing the facts {as stated} gives the answer below.\n'
            '{"liable": "False", "reason": "No duty was owed."}'
        )
        result = ResponseParser({}, BOOLEAN_CHOICES).parse(answer)
        assert result.status == "success", result.error
        assert _values(result) == {
            "liable": {"choices": ["False"]},
            "reason": {"text": ["No duty was owed."]},
        }

    def test_the_last_json_value_wins(self):
        answer = (
            'A first draft: {"liable": "True", "reason": "draft"}\n'
            'Final: {"liable": "False", "reason": "final"} Done.'
        )
        result = ResponseParser({}, BOOLEAN_CHOICES).parse(answer)
        assert _values(result)["reason"] == {"text": ["final"]}

    @pytest.mark.parametrize(
        "answer",
        [
            # the final object is cut off after a complete draft
            'Draft: {"liable": "True", "reason": "draft"}\n'
            'On reflection the draft is wrong. Final: {"liable": "False", "reason": "no duty was ow',
            # a complete inner object inside a cut-off outer one
            'Answer: {"details": {"liable": "True", "reason": "inner"}, "liable": "Fal',
        ],
    )
    def test_truncated_final_value_promotes_no_earlier_value(self, answer):
        result = ResponseParser({}, BOOLEAN_CHOICES).parse(answer)
        assert result.status == "success"
        assert result.field_values == {"__response__": answer}

    def test_array_after_prose(self):
        cfg = """<View>
  <Text name="body" value="$body"/>
  <Labels name="ner" toName="body"><Label value="PER"/></Labels>
</View>"""
        answer = 'The persons are:\n[{"start": 0, "end": 3, "type": "PER", "text": "Ann"}]'
        result = ResponseParser({}, cfg).parse(answer, source_text="Ann met Bob.")
        assert result.status == "success", result.error
        spans = _values(result)["ner"]["spans"]
        assert [(s["start"], s["end"], s["labels"]) for s in spans] == [(0, 3, ["PER"])]

    def test_json_without_a_known_field_leaves_the_pattern_fallback(self):
        cfg = """<View>
  <Text name="facts" value="$facts"/>
  <TextArea name="verdict" toName="facts"/>
  <TextArea name="reason" toName="facts"/>
</View>"""
        answer = 'Verdict: no\nReason: see {"a": 1}'
        result = ResponseParser({}, cfg).parse(answer)
        assert result.status == "success", result.error
        assert _values(result)["verdict"] == {"text": ["no"]}

    def test_truncated_repeater_array_is_not_an_empty_success(self):
        cfg = """<View>
  <Repeater on="$cases" answerKey="item">
    <Text name="case_{{idx}}" value="$cases[{{idx}}].text"/>
    <Choices name="risk_{{idx}}" toName="case_{{idx}}">
      <Choice value="high"/><Choice value="low"/>
    </Choices>
  </Repeater>
</View>"""
        task = {"cases": [{"text": "a"}, {"text": "b"}, {"text": "c"}]}
        answer = '[{"item":1,"risk":"high"},{"item":2,"risk":"low"},{"item":3,"ri'
        parser = ResponseParser({}, cfg)
        assert parser._for_task(task)._try_json_parse(answer).status == "failed"
        result = parser.parse(answer, task_data=task)
        assert result.status == "success"
        assert result.field_values == {"__response__": answer}

    def test_prose_without_json_stays_free_text(self):
        answer = "The claim fails because no duty was owed."
        result = ResponseParser({}, BOOLEAN_CHOICES).parse(answer)
        assert result.status == "success"
        assert result.field_values == {"__response__": answer}


class TestMultiChoice:
    def test_list_answer_is_stored_as_the_choices_list(self):
        result = ResponseParser({}, MULTI_CHOICES).parse(json.dumps({"issues": ["contract", "tort"]}))
        assert result.status == "success", result.error
        assert _values(result)["issues"] == {"choices": ["contract", "tort"]}

    def test_single_string_stays_accepted(self):
        result = ResponseParser({}, MULTI_CHOICES).parse('{"issues": "tort"}')
        assert result.status == "success", result.error
        assert _values(result)["issues"] == {"choices": ["tort"]}

    def test_unknown_choice_in_the_list_is_rejected(self):
        parser = ResponseParser({}, MULTI_CHOICES)
        result = parser._try_json_parse(json.dumps({"issues": ["contract", "crime"]}))
        assert result.status == "validation_error"

    def test_single_choice_field_takes_no_list(self):
        cfg = MULTI_CHOICES.replace(' choice="multiple"', "")
        result = ResponseParser({}, cfg)._try_json_parse(json.dumps({"issues": ["tort"]}))
        assert result.status == "validation_error"

    def test_multiple_dropdown_takes_a_list_too(self):
        cfg = MULTI_CHOICES.replace('choice="multiple"', 'choice="multiple-dropdown"')
        result = ResponseParser({}, cfg).parse(json.dumps({"issues": ["property"]}))
        assert _values(result)["issues"] == {"choices": ["property"]}
