"""Per-slot label configs: Repeater expansion, array answers, slot maps.

Covers ``services/shared/label_config_repeater.py`` and its use by the
response parser, the structured-output schema generator and the generation
worker's field list. The configs and answers are invented examples in the
two shapes per-item tasks take: a Repeater over a list of cases answered as
one JSON object per case, and hand-written indexed names (``months_1``,
``months_2``) answered as one flat object.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from xml.etree import ElementTree as ET

import jsonschema
import pytest

_shared_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "shared"
)
if _shared_dir not in sys.path:
    sys.path.insert(0, _shared_dir)

from label_config_repeater import (  # noqa: E402
    ArrayAnswerError,
    derive_slot_map,
    expand_repeaters,
    expand_repeaters_with_counts,
    has_repeater,
    item_key_for,
    map_array_answers,
    repeater_answer_example,
    repeater_blocks,
    repeater_errors,
    resolve_data_path,
)
from response_parser import ResponseParser  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "_repeater_schema_generator", os.path.join(_shared_dir, "ai_services", "schema_generator.py")
)
_sg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sg)


DOCKET = """<View>
  <Header value="Docket"/>
  <Repeater on="$cases" indexFlag="{{idx}}" mode="pagination" answerKey="case">
    <Text name="case_{{idx}}" value="$cases[{{idx}}].text"/>
    <Number name="risk_{{idx}}" toName="case_{{idx}}" min="0" max="100"/>
    <Number name="months_{{idx}}" toName="case_{{idx}}" min="1" max="24"/>
    <Choices name="priority_{{idx}}" toName="case_{{idx}}">
      <Choice value="high"/><Choice value="low"/>
    </Choices>
    <TextArea name="note_{{idx}}" toName="case_{{idx}}"/>
  </Repeater>
</View>"""

DOCKET_TASK = {
    "cases": [
        {"text": "Case one: a bicycle was taken from a yard."},
        {"text": "Case two: an invoice was paid twice."},
        {"text": "Case three: a window was broken."},
    ]
}

TWO_DEFENDANTS = """<View>
  <Text name="facts" value="$facts"/>
  <Number name="months_1" toName="facts" min="0" max="48"/>
  <Number name="probation_1" toName="facts" min="0" max="100"/>
  <Rating name="credibility_1" toName="facts" maxRating="7"/>
  <Number name="months_2" toName="facts" min="0" max="48"/>
  <Number name="probation_2" toName="facts" min="0" max="100"/>
  <Rating name="credibility_2" toName="facts" maxRating="7"/>
</View>"""


def _fields(result):
    return {r["from_name"]: r["value"] for r in result.parsed_annotation}


# --------------------------------------------------------------------------
# Expansion, as Label Studio's Tree.tsx does it
# --------------------------------------------------------------------------


class TestExpansion:
    def test_repeats_children_per_item_with_zero_based_index(self):
        root = ET.fromstring(expand_repeaters(DOCKET, DOCKET_TASK))
        names = [e.get("name") for e in root.iter() if e.get("name")]
        assert names == [
            f"{stem}_{i}"
            for i in range(3)
            for stem in ("case", "risk", "months", "priority", "note")
        ]
        texts = [e.get("value") for e in root.iter("Text")]
        assert texts == ["$cases[0].text", "$cases[1].text", "$cases[2].text"]
        # toName follows the same substitution
        assert [e.get("toName") for e in root.iter("Number")][:2] == ["case_0", "case_0"]

    def test_repeater_becomes_view_with_one_view_per_item(self):
        root = ET.fromstring(expand_repeaters(DOCKET, DOCKET_TASK))
        assert root.find("Repeater") is None
        block = root[1]
        assert block.tag == "View"
        assert [child.tag for child in block] == ["View", "View", "View"]
        # Repeater-only attributes are gone from the expanded form
        assert not {"on", "indexFlag", "mode", "answerKey"} & set(block.attrib)

    def test_other_repeater_attributes_stay_on_the_view(self):
        cfg = '<View><Repeater on="$a" style="gap: 4px"><TextArea name="t_{{idx}}" toName="x"/></Repeater></View>'
        root = ET.fromstring(expand_repeaters(cfg, {"a": [1]}))
        assert root[0].get("style") == "gap: 4px"

    def test_custom_index_flag(self):
        cfg = '<View><Repeater on="$a" indexFlag="#n"><TextArea name="t_#n" toName="x_#n"/></Repeater></View>'
        root = ET.fromstring(expand_repeaters(cfg, {"a": ["p", "q"]}))
        assert [e.get("name") for e in root.iter("TextArea")] == ["t_0", "t_1"]
        assert [e.get("toName") for e in root.iter("TextArea")] == ["x_0", "x_1"]

    def test_attribute_names_are_case_insensitive_like_label_studio(self):
        cfg = '<View><Repeater ON="$a" indexflag="#n"><TextArea name="t_#n" toName="x"/></Repeater></View>'
        root = ET.fromstring(expand_repeaters(cfg, {"a": [1, 2]}))
        assert [e.get("name") for e in root.iter("TextArea")] == ["t_0", "t_1"]

    def test_text_content_is_not_substituted(self):
        cfg = '<View><Repeater on="$a"><Header value="Item {{idx}}">Item {{idx}}</Header><TextArea name="t_{{idx}}" toName="x"/></Repeater></View>'
        root = ET.fromstring(expand_repeaters(cfg, {"a": [1]}))
        header = root.find(".//Header")
        assert header.get("value") == "Item 0"
        assert header.text == "Item {{idx}}"

    def test_missing_or_non_list_binding_repeats_nothing(self):
        for data in ({}, {"cases": "not a list"}, {"cases": None}, None):
            root = ET.fromstring(expand_repeaters(DOCKET, data))
            assert [e for e in root.iter() if e.get("name")] == []

    def test_nested_data_path(self):
        cfg = '<View><Repeater on="$doc.cases"><TextArea name="t_{{idx}}" toName="x"/></Repeater></View>'
        root = ET.fromstring(expand_repeaters(cfg, {"doc": {"cases": [1, 2, 3, 4]}}))
        assert len(list(root.iter("TextArea"))) == 4

    def test_config_without_repeater_is_returned_unchanged(self):
        assert expand_repeaters(TWO_DEFENDANTS, {"facts": "x"}) is TWO_DEFENDANTS
        assert expand_repeaters_with_counts(TWO_DEFENDANTS, {"$a": 2}) is TWO_DEFENDANTS
        assert expand_repeaters(None, {}) is None
        assert not has_repeater(TWO_DEFENDANTS)
        assert not has_repeater("<View><Repeater")  # unparseable
        assert has_repeater(DOCKET)

    def test_expansion_to_given_counts(self):
        root = ET.fromstring(expand_repeaters_with_counts(DOCKET, {"$cases": 2}))
        assert len(list(root.iter("TextArea"))) == 2
        root = ET.fromstring(expand_repeaters_with_counts(DOCKET, {}))
        assert len(list(root.iter("TextArea"))) == 0

    def test_resolve_data_path(self):
        data = {"a": {"b": [{"c": 5}]}}
        assert resolve_data_path(data, "$a.b[0].c") == 5
        assert resolve_data_path(data, "$a.b.0.c") == 5
        assert resolve_data_path(data, "$a.b[3].c") is None
        assert resolve_data_path(data, "$a.x") is None
        assert resolve_data_path(data, "a.b") is None
        assert resolve_data_path(data, "$a.b.x") is None


class TestItemKeys:
    @pytest.mark.parametrize(
        "template, key",
        [
            ("risk_{{idx}}", "risk"),
            ("{{idx}}_risk", "risk"),
            ("person_{{idx}}_credibility", "person_credibility"),
            ("risk{{idx}}", "risk"),
            ("risk-{{idx}}", "risk"),
            ("risk", "risk"),
        ],
    )
    def test_item_key_drops_flag_and_one_separator(self, template, key):
        assert item_key_for(template, "{{idx}}") == key

    def test_blocks_describe_controls(self):
        (block,) = repeater_blocks(DOCKET)
        assert block.on == "$cases"
        assert block.answer_property == "cases"
        assert block.answer_key == "case"
        assert block.answer_key_start == 1
        assert block.mode == "pagination"
        assert [(c.item_key, c.tag) for c in block.controls] == [
            ("risk", "Number"),
            ("months", "Number"),
            ("priority", "Choices"),
            ("note", "TextArea"),
        ]
        assert block.item_count(DOCKET_TASK) == 3


# --------------------------------------------------------------------------
# Validation rules
# --------------------------------------------------------------------------


class TestRepeaterErrors:
    def _errors(self, inner, attrs='on="$a"'):
        return repeater_errors(ET.fromstring(f"<View><Repeater {attrs}>{inner}</Repeater></View>"))

    def test_valid_block_has_no_errors(self):
        assert repeater_errors(ET.fromstring(DOCKET)) == []

    def test_on_must_be_a_binding(self):
        assert any("'on'" in e for e in self._errors('<TextArea name="t_{{idx}}" toName="x"/>', 'on="a"'))
        assert any("'on'" in e for e in self._errors('<TextArea name="t_{{idx}}" toName="x"/>', ""))

    def test_control_without_index_flag_is_rejected(self):
        errors = self._errors('<TextArea name="t" toName="x"/>')
        assert any("must contain the index flag" in e for e in errors)

    def test_flag_twice_in_one_attribute_is_rejected(self):
        errors = self._errors('<TextArea name="t_{{idx}}_{{idx}}" toName="x"/>')
        assert any("more than once" in e for e in errors)

    def test_nested_repeaters_are_rejected(self):
        errors = self._errors('<Repeater on="$b" indexFlag="#j"><TextArea name="t_{{idx}}_#j" toName="x"/></Repeater>')
        assert any("Nested" in e for e in errors)

    def test_colliding_answer_keys_are_rejected(self):
        errors = self._errors('<TextArea name="t_{{idx}}" toName="x"/><Number name="{{idx}}_t" toName="x"/>')
        assert any("same answer key" in e for e in errors)

    def test_answer_key_must_not_be_a_control_key(self):
        errors = self._errors('<Number name="case_{{idx}}" toName="x"/>', 'on="$a" answerKey="case"')
        assert any("answerKey" in e for e in errors)

    def test_flag_only_name_is_rejected(self):
        errors = self._errors('<Number name="{{idx}}" toName="x"/>')
        assert any("besides the index flag" in e for e in errors)

    def test_bad_answer_key_start_and_empty_flag(self):
        assert any(
            "answerKeyStart" in e
            for e in self._errors('<Number name="n_{{idx}}" toName="x"/>', 'on="$a" answerKeyStart="one"')
        )
        assert any(
            "indexFlag" in e
            for e in self._errors('<Number name="n_{{idx}}" toName="x"/>', 'on="$a" indexFlag=" "')
        )
        assert any(
            "answerKey cannot" in e
            for e in self._errors('<Number name="n_{{idx}}" toName="x"/>', 'on="$a" answerKey=" "')
        )
        assert any(
            "no 'name'" in e
            for e in self._errors('<Number name="n_{{idx}}" toName="x"/>', 'on="$a" name="r"')
        )

    def test_answer_property_must_not_clash(self):
        cfg = '<View><TextArea name="a" toName="x"/><Repeater on="$a"><Number name="n_{{idx}}" toName="x"/></Repeater></View>'
        assert any("also the name of a control" in e for e in repeater_errors(ET.fromstring(cfg)))
        cfg = (
            '<View><Repeater on="$a"><Number name="n_{{idx}}" toName="x"/></Repeater>'
            '<Repeater on="$doc.a"><Number name="m_{{idx}}" toName="x"/></Repeater></View>'
        )
        assert any("same key" in e for e in repeater_errors(ET.fromstring(cfg)))

    @pytest.mark.parametrize(
        "outside",
        [
            '<Number name="risk_0" toName="x"/>',
            '<Number name="risk_12" toName="x"/>',
            '<Text name="risk_3" value="$x"/>',
        ],
    )
    def test_expanded_name_must_not_equal_an_outside_name(self, outside):
        cfg = (
            f'<View>{outside}<Repeater on="$a"><Number name="risk_{{{{idx}}}}" toName="x"/>'
            "</Repeater></View>"
        )
        assert any("outside it" in e for e in repeater_errors(ET.fromstring(cfg)))

    @pytest.mark.parametrize(
        "outside",
        ['<Number name="risk_01" toName="x"/>', '<Number name="risk_x" toName="x"/>',
         '<Number name="risk_" toName="x"/>', '<Number name="risk_0_b" toName="x"/>'],
    )
    def test_names_no_index_produces_are_fine(self, outside):
        cfg = (
            f'<View>{outside}<Repeater on="$a"><Number name="risk_{{{{idx}}}}" toName="x"/>'
            "</Repeater></View>"
        )
        assert repeater_errors(ET.fromstring(cfg)) == []

    @pytest.mark.parametrize(
        "first, second",
        [
            # a_{{idx}} and a_{{i}} both give a_0, a_1, ...
            ('<Repeater on="$a"><Number name="a_{{idx}}" toName="x"/></Repeater>',
             '<Repeater on="$b" indexFlag="{{i}}"><Number name="a_{{i}}" toName="x"/></Repeater>'),
            # a{{idx}} at 15 and a1{{i}} at 5 both give a15
            ('<Repeater on="$a"><Number name="a{{idx}}" toName="x"/></Repeater>',
             '<Repeater on="$b" indexFlag="{{i}}"><Number name="a1{{i}}" toName="x"/></Repeater>'),
            # within one block: x{{idx}}1 and x1{{idx}} both give x11 at index 1
            ('<Repeater on="$a"><Number name="x{{idx}}1" toName="x"/>'
             '<Number name="x1{{idx}}" toName="x"/></Repeater>', ""),
        ],
    )
    def test_templates_must_not_expand_to_the_same_name(self, first, second):
        cfg = f"<View>{first}{second}</View>"
        assert any("can expand to the same name" in e for e in repeater_errors(ET.fromstring(cfg)))

    @pytest.mark.parametrize(
        "first, second",
        [
            # a_{{idx}} never yields a_0b; b_{{i}} never yields a_...
            ('<Repeater on="$a"><Number name="a_{{idx}}" toName="x"/></Repeater>',
             '<Repeater on="$b" indexFlag="{{i}}"><Number name="b_{{i}}" toName="x"/></Repeater>'),
            # a_{{idx}} ends with digits, a_0{{i}} needs a leading zero
            ('<Repeater on="$a"><Number name="a_{{idx}}" toName="x"/></Repeater>',
             '<Repeater on="$b" indexFlag="{{i}}"><Number name="a_0{{i}}" toName="x"/></Repeater>'),
            ('<Repeater on="$a"><Number name="a_{{idx}}" toName="x"/></Repeater>',
             '<Repeater on="$b" indexFlag="{{i}}"><Number name="a_{{i}}_b" toName="x"/></Repeater>'),
        ],
    )
    def test_disjoint_templates_are_fine(self, first, second):
        cfg = f"<View>{first}{second}</View>"
        assert repeater_errors(ET.fromstring(cfg)) == []


# --------------------------------------------------------------------------
# Array answers -> indexed names
# --------------------------------------------------------------------------


class TestMapArrayAnswers:
    BLOCKS = repeater_blocks(DOCKET)

    def test_maps_by_answer_key_regardless_of_order(self):
        answer = {"cases": [{"case": 2, "risk": 70}, {"case": 3, "risk": 10}, {"case": 1, "risk": 50}]}
        assert map_array_answers(answer, self.BLOCKS, DOCKET_TASK) == {
            "risk_1": 70,
            "risk_2": 10,
            "risk_0": 50,
        }

    def test_answer_key_as_numeric_string_or_integral_float(self):
        answer = [{"case": "1", "risk": 1}, {"case": 2.0, "risk": 2}, {"case": " 3 ", "risk": 3}]
        assert map_array_answers(answer, self.BLOCKS, DOCKET_TASK) == {
            "risk_0": 1,
            "risk_1": 2,
            "risk_2": 3,
        }

    def test_maps_by_position_without_answer_key(self):
        answer = [{"risk": 1}, {"risk": 2}, {"risk": 3}]
        assert map_array_answers(answer, self.BLOCKS, DOCKET_TASK) == {
            "risk_0": 1,
            "risk_1": 2,
            "risk_2": 3,
        }

    def test_answer_key_start(self):
        cfg = DOCKET.replace('answerKey="case"', 'answerKey="case" answerKeyStart="0"')
        blocks = repeater_blocks(cfg)
        answer = [{"case": 0, "risk": 1}, {"case": 2, "risk": 3}, {"case": 1, "risk": 2}]
        assert map_array_answers(answer, blocks, DOCKET_TASK) == {
            "risk_0": 1,
            "risk_2": 3,
            "risk_1": 2,
        }

    def test_other_keys_are_kept(self):
        answer = {"cases": [{"risk": 1}] * 3, "summary": "s", "risk_0": 99}
        mapped = map_array_answers(answer, self.BLOCKS, DOCKET_TASK)
        assert mapped["summary"] == "s"
        # the array value for the same indexed name wins over a flat duplicate
        assert mapped["risk_0"] == 1

    def test_flat_answer_without_the_array_passes_through(self):
        answer = {"risk_0": 5}
        assert map_array_answers(answer, self.BLOCKS, DOCKET_TASK) == {"risk_0": 5}
        assert map_array_answers("text", self.BLOCKS, DOCKET_TASK) == "text"
        assert map_array_answers({"a": 1}, [], DOCKET_TASK) == {"a": 1}

    @pytest.mark.parametrize(
        "answer, message",
        [
            ([{"risk": 1}] * 2, "has 2 objects, the task has 3 items"),
            ({"cases": {"risk": 1}}, "must be a JSON list"),
            ([{"risk": 1}, "x", {"risk": 2}], "item 2 is not a JSON object"),
            ([{"case": 1}, {"case": 1}, {"case": 2}], "answer the same item"),
            ([{"case": 0}, {"case": 1}, {"case": 2}], "expected 1 to 3"),
            ([{"case": 4}, {"case": 1}, {"case": 2}], "expected 1 to 3"),
            ([{"case": "a"}, {"case": 1}, {"case": 2}], "expected 1 to 3"),
            ([{"case": True}, {"case": 1}, {"case": 2}], "expected 1 to 3"),
            ([{"case": 1.5}, {"case": 1}, {"case": 2}], "expected 1 to 3"),
        ],
    )
    def test_misfitting_arrays_are_errors(self, answer, message):
        with pytest.raises(ArrayAnswerError, match=message):
            map_array_answers(answer, self.BLOCKS, DOCKET_TASK)

    def test_top_level_list_is_ambiguous_with_two_blocks(self):
        cfg = (
            '<View><Repeater on="$a"><Number name="n_{{idx}}" toName="x"/></Repeater>'
            '<Repeater on="$b"><Number name="m_{{idx}}" toName="x"/></Repeater></View>'
        )
        with pytest.raises(ArrayAnswerError, match="ambiguous"):
            map_array_answers([], repeater_blocks(cfg), {"a": [], "b": []})

    def test_without_task_data_the_answer_sets_the_count(self):
        answer = [{"risk": 1}, {"risk": 2}]
        assert map_array_answers(answer, self.BLOCKS, None) == {"risk_0": 1, "risk_1": 2}


# --------------------------------------------------------------------------
# Response parser
# --------------------------------------------------------------------------

DOCKET_ANSWER = """```json
[
  {"case": 1, "risk": 45, "months": 4, "priority": "low", "note": "First note."},
  {"case": 2, "risk": 60, "months": 8, "priority": "high", "note": "Second note."},
  {"case": 3, "risk": 70, "months": 10, "priority": "high", "note": "Third note."}
]
```"""


class TestResponseParser:
    def test_array_answer_parses_onto_indexed_names(self):
        result = ResponseParser({}, DOCKET).parse(DOCKET_ANSWER, task_data=DOCKET_TASK)
        assert result.status == "success", result.error
        fields = _fields(result)
        assert fields["risk_0"] == {"number": 45}
        assert fields["months_2"] == {"number": 10}
        assert fields["priority_1"] == {"choices": ["high"]}
        assert fields["note_0"] == {"text": ["First note."]}
        assert len(fields) == 12
        # Results carry Label Studio's flat, expanded names and types
        assert {r["type"] for r in result.parsed_annotation} == {"number", "choices", "textarea"}

    def test_object_answer_and_extra_fields(self):
        cfg = DOCKET.replace("</Repeater>", '</Repeater><TextArea name="summary" toName="case_0"/>')
        answer = json.dumps(
            {
                "cases": [{"case": i + 1, "risk": i} for i in range(3)],
                "summary": "All three.",
            }
        )
        result = ResponseParser({}, cfg).parse(answer, task_data=DOCKET_TASK)
        assert result.status == "success", result.error
        fields = _fields(result)
        assert fields["summary"] == {"text": ["All three."]}
        assert fields["risk_2"] == {"number": 2}

    def test_wrong_item_count_is_a_validation_error_not_free_text(self):
        answer = json.dumps([{"case": 1, "risk": 1}, {"case": 2, "risk": 2}])
        result = ResponseParser({}, DOCKET).parse(answer, task_data=DOCKET_TASK)
        assert result.status == "validation_error"
        assert "has 2 objects, the task has 3 items" in result.error
        assert result.parsed_annotation is None

    def test_missing_required_item_value_follows_the_schema_fallback(self):
        cfg = DOCKET.replace('<Number name="risk_{{idx}}"', '<Number name="risk_{{idx}}" required="true"')
        answer = json.dumps([{"case": 1}, {"case": 2, "risk": 1}, {"case": 3, "risk": 1}])
        result = ResponseParser({}, cfg).parse(answer, task_data=DOCKET_TASK)
        # risk_0 is required in the expanded schema and missing; the parser's
        # existing fallback turns a schema failure into a free-text answer
        assert result.status == "success"
        assert [r["from_name"] for r in result.parsed_annotation] == ["__response__"]

    def test_repeater_config_needs_task_data(self):
        result = ResponseParser({}, DOCKET).parse(DOCKET_ANSWER)
        assert result.status == "failed"
        assert "task's data" in result.error

    def test_parsers_are_cached_per_item_count(self):
        parser = ResponseParser({}, DOCKET)
        parser.parse(DOCKET_ANSWER, task_data=DOCKET_TASK)
        parser.parse(DOCKET_ANSWER, task_data={"cases": [{}, {}, {}]})
        parser.parse("[]", task_data={"cases": []})
        assert set(parser._task_parsers) == {(3,), (0,)}

    def test_template_names_are_no_fields(self):
        assert ResponseParser({}, DOCKET).label_config_map == {}

    def test_array_and_flat_indexed_answers_parse_identically(self):
        # The same content in the two shapes the intent names: one object
        # per item keyed by an item number, and flat indexed control names.
        array_answer = json.dumps(
            {
                "cases": [
                    {"case": 2, "risk": 60, "months": 8, "priority": "high", "note": "Second."},
                    {"case": 1, "risk": 45, "months": 4, "priority": "low", "note": "First."},
                    {"case": 3, "risk": 70, "months": 10, "priority": "high", "note": "Third."},
                ]
            }
        )
        flat_answer = json.dumps(
            {
                "risk_0": 45, "months_0": 4, "priority_0": "low", "note_0": "First.",
                "risk_1": 60, "months_1": 8, "priority_1": "high", "note_1": "Second.",
                "risk_2": 70, "months_2": 10, "priority_2": "high", "note_2": "Third.",
            }
        )
        parser = ResponseParser({}, DOCKET)
        from_array = parser.parse(array_answer, task_data=DOCKET_TASK)
        from_flat = parser.parse(flat_answer, task_data=DOCKET_TASK)
        assert from_array.status == from_flat.status == "success"

        def by_name(result):
            return sorted(result.parsed_annotation, key=lambda r: r["from_name"])

        assert by_name(from_array) == by_name(from_flat)
        assert from_array.field_values == from_flat.field_values
        assert len(from_flat.parsed_annotation) == 12

    def test_display_only_repeater_does_not_take_a_bare_list(self):
        # A Repeater without answer controls asks for no array answer, so a
        # bare list still goes to the Labels field outside it.
        cfg = """<View>
  <Repeater on="$docs"><Text name="doc_{{idx}}" value="$docs[{{idx}}]"/></Repeater>
  <Text name="body" value="$body"/>
  <Labels name="ner" toName="body"><Label value="PER"/></Labels>
</View>"""
        task = {"docs": ["one", "two"], "body": "Ann met Bob."}
        answer = json.dumps([{"start": 0, "end": 3, "type": "PER", "text": "Ann"}])
        result = ResponseParser({}, cfg).parse(answer, source_text=task["body"], task_data=task)
        assert result.status == "success", result.error
        assert [r["from_name"] for r in result.parsed_annotation] == ["ner"]
        spans = result.parsed_annotation[0]["value"]["spans"]
        assert [(s["start"], s["end"], s["labels"]) for s in spans] == [(0, 3, ["PER"])]

    def test_hand_written_indexed_names_parse_as_flat_fields(self):
        answer = '{"months_1": 6, "probation_1": 80, "credibility_1": 6, "months_2": 1, "probation_2": 90, "credibility_2": 7}'
        result = ResponseParser({}, TWO_DEFENDANTS).parse(answer, task_data={"facts": "x"})
        assert result.status == "success", result.error
        fields = _fields(result)
        assert fields["months_1"] == {"number": 6}
        assert fields["credibility_2"] == {"rating": 7}


# --------------------------------------------------------------------------
# Structured-output schema and prompt instruction
# --------------------------------------------------------------------------


class TestSchema:
    def test_repeater_becomes_array_of_objects(self):
        schema = _sg.generate_json_schema_from_label_config(DOCKET, task_data=DOCKET_TASK)
        assert list(schema["properties"]) == ["cases"]
        array = schema["properties"]["cases"]
        assert array["type"] == "array"
        assert array["minItems"] == array["maxItems"] == 3
        item = array["items"]
        assert list(item["properties"]) == ["case", "risk", "months", "priority", "note"]
        assert item["properties"]["case"]["minimum"] == 1
        assert item["properties"]["case"]["maximum"] == 3
        assert item["properties"]["risk"] == {"type": "number", "minimum": 0.0, "maximum": 100.0}
        assert item["properties"]["priority"] == {"type": "string", "enum": ["high", "low"]}
        # OpenAI strict mode: every object lists all keys and closes itself
        assert item["required"] == list(item["properties"])
        assert item["additionalProperties"] is False
        assert schema["required"] == ["cases"]

    def test_answer_validates_against_schema(self):
        schema = _sg.generate_json_schema_from_label_config(DOCKET, task_data=DOCKET_TASK)
        body = DOCKET_ANSWER.split("\n", 1)[1].rsplit("```", 1)[0]
        jsonschema.validate({"cases": json.loads(body)}, schema)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({"cases": json.loads(body)[:2]}, schema)

    def test_without_task_data_the_length_is_open(self):
        schema = _sg.generate_json_schema_from_label_config(DOCKET)
        array = schema["properties"]["cases"]
        assert "minItems" not in array and "maxItems" not in array
        assert "minimum" not in array["items"]["properties"]["case"]

    def test_loose_mode_keeps_only_required_controls(self):
        cfg = DOCKET.replace('<TextArea name="note_{{idx}}"', '<TextArea required="true" name="note_{{idx}}"')
        schema = _sg.generate_json_schema_from_label_config(cfg, strict_mode=False)
        item = schema["properties"]["cases"]["items"]
        assert item["required"] == ["case", "note"]
        assert "additionalProperties" not in item

    def test_format_instructions_and_example(self):
        text = _sg.generate_format_instructions(DOCKET, task_data=DOCKET_TASK)
        assert "list with one object per item (keys: case, risk, months, priority, note)" in text
        example = json.loads(text.split("```json\n", 1)[1].split("\n```", 1)[0])
        assert [item["case"] for item in example["cases"]] == [1, 2, 3]
        jsonschema.validate(example, _sg.generate_json_schema_from_label_config(DOCKET, task_data=DOCKET_TASK))

    def test_multi_choice_asks_for_a_list_flat_and_in_a_block(self):
        # Label Studio stores a choice="multiple" answer as a list of the
        # choice values (value.choices), so the schema asks for a list.
        cfg = """<View>
  <Text name="facts" value="$facts"/>
  <Choices name="issues" toName="facts" choice="multiple">
    <Choice value="contract"/><Choice value="tort"/>
  </Choices>
  <Repeater on="$cases">
    <Text name="case_{{idx}}" value="$cases[{{idx}}].text"/>
    <Choices name="topics_{{idx}}" toName="case_{{idx}}" choice="multiple-dropdown">
      <Choice value="fees"/><Choice value="damages"/>
    </Choices>
  </Repeater>
</View>"""
        task = {"facts": "f", "cases": [{"text": "a"}, {"text": "b"}]}
        schema = _sg.generate_json_schema_from_label_config(cfg, task_data=task)
        good = {"issues": ["contract", "tort"], "cases": [{"topics": ["fees"]}, {"topics": ["fees", "damages"]}]}
        jsonschema.validate(good, schema)
        for bad in (
            {**good, "issues": "contract"},
            {**good, "issues": ["crime"]},
            {**good, "cases": [{"topics": "fees"}, {"topics": ["fees"]}]},
        ):
            with pytest.raises(jsonschema.ValidationError):
                jsonschema.validate(bad, schema)
        text = _sg.generate_format_instructions(cfg, task_data=task)
        example = json.loads(text.split("```json\n", 1)[1].split("\n```", 1)[0])
        jsonschema.validate(example, schema)
        assert example["issues"] == ["contract"]
        parsed = ResponseParser({}, cfg).parse(json.dumps(good), task_data=task)
        assert parsed.status == "success", parsed.error
        assert _fields(parsed)["issues"] == {"choices": ["contract", "tort"]}
        assert _fields(parsed)["topics_1"] == {"choices": ["fees", "damages"]}

    def test_multi_choice_without_static_choices_asks_for_strings(self):
        # Dynamic choices come from task data (value="$opts"), so the schema
        # knows no enum: the field is a list of strings, flat and per item.
        cfg = """<View>
  <Text name="facts" value="$facts"/>
  <Choices name="tags" toName="facts" choice="multiple" value="$opts"/>
  <Repeater on="$cases">
    <Text name="case_{{idx}}" value="$cases[{{idx}}].text"/>
    <Choices name="labels_{{idx}}" toName="case_{{idx}}" choice="multiple" value="$opts"/>
  </Repeater>
</View>"""
        task = {"facts": "f", "opts": [{"value": "x"}], "cases": [{"text": "a"}]}
        schema = _sg.generate_json_schema_from_label_config(cfg, task_data=task)
        text = _sg.generate_format_instructions(cfg, task_data=task)
        assert "- **tags**: list of strings" in text
        example = json.loads(text.split("```json\n", 1)[1].split("\n```", 1)[0])
        assert example["tags"] == ["..."]
        assert example["cases"] == [{"labels": ["..."]}]
        jsonschema.validate(example, schema)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({**example, "tags": [{}]}, schema)

    def test_single_choice_keeps_its_string_schema(self):
        cfg = '<View><Choices name="c" toName="x"><Choice value="a"/></Choices></View>'
        assert _sg.generate_json_schema_from_label_config(cfg)["properties"]["c"] == {
            "type": "string", "enum": ["a"],
        }

    def test_repeater_without_controls_adds_nothing(self):
        cfg = '<View><TextArea name="a" toName="x"/><Repeater on="$c"><Text name="t_{{idx}}" value="$c[{{idx}}]"/></Repeater></View>'
        assert list(_sg.generate_json_schema_from_label_config(cfg)["properties"]) == ["a"]

    def test_prompt_example_has_one_object_per_item(self):
        (block,) = repeater_blocks(DOCKET)
        example = repeater_answer_example(block, DOCKET_TASK)
        assert [item["case"] for item in example] == [1, 2, 3]
        assert set(example[0]) == {"case", "risk", "months", "priority", "note"}
        assert len(repeater_answer_example(block)) == 1
        assert repeater_answer_example(block, {"cases": []}) == []

    def test_task_without_items_shows_an_empty_list(self):
        empty = {"cases": []}
        text = _sg.generate_format_instructions(DOCKET, task_data=empty)
        example = json.loads(text.split("```json\n", 1)[1].split("\n```", 1)[0])
        assert example["cases"] == []
        jsonschema.validate(example, _sg.generate_json_schema_from_label_config(DOCKET, task_data=empty))
        # the example is an answer the parser accepts for that task
        assert ResponseParser({}, DOCKET).parse(json.dumps(example), task_data=empty).status == "success"


# --------------------------------------------------------------------------
# Slot maps
# --------------------------------------------------------------------------


class TestSlotMap:
    def test_repeater_slots(self):
        (group,) = derive_slot_map(DOCKET, DOCKET_TASK)
        assert group["source"] == "repeater"
        assert group["on"] == "$cases"
        assert group["index_base"] == 0
        assert group["answer_key_start"] == 1
        assert [slot["index"] for slot in group["slots"]] == [0, 1, 2]
        assert group["slots"][1]["controls"] == {
            "risk": "risk_1",
            "months": "months_1",
            "priority": "priority_1",
            "note": "note_1",
        }

    def test_repeater_slots_need_task_data(self):
        (group,) = derive_slot_map(DOCKET)
        assert group["slots"] == []

    def test_pattern_slots_for_hand_written_names(self):
        (group,) = derive_slot_map(
            TWO_DEFENDANTS, patterns=["months_{idx}", "probation_{idx}", "credibility_{idx}"]
        )
        assert group["source"] == "pattern"
        assert group["slots"] == [
            {"index": 1, "controls": {"months": "months_1", "probation": "probation_1", "credibility": "credibility_1"}},
            {"index": 2, "controls": {"months": "months_2", "probation": "probation_2", "credibility": "credibility_2"}},
        ]

    def test_patterns_over_an_expanded_repeater(self):
        groups = derive_slot_map(DOCKET, DOCKET_TASK, patterns=["risk_{idx}"])
        assert groups[1]["slots"][2] == {"index": 2, "controls": {"risk": "risk_2"}}

    def test_pattern_needs_one_placeholder(self):
        with pytest.raises(ValueError, match="exactly once"):
            derive_slot_map(TWO_DEFENDANTS, patterns=["months"])


# --------------------------------------------------------------------------
# Generation worker field list
# --------------------------------------------------------------------------


def test_worker_field_list_leaves_repeater_controls_to_the_array():
    from tasks import extract_label_config_fields

    cfg = DOCKET.replace("</Repeater>", '</Repeater><TextArea name="summary" toName="x"/>')
    assert extract_label_config_fields(cfg) == ["summary"]
