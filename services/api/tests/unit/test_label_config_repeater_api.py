"""Label Studio <Repeater> in the API: validation, field extraction, task-data
blinding and the Label Studio export of results.

The shared expansion and answer mapping are covered by
``services/workers/tests/test_label_config_repeater.py``.
"""

import copy

import pytest

from export_stream import convert_to_label_studio_format
from label_config_repeater import control_targets, expand_repeaters
from routers.projects.tasks.blinding import blind_task_data, visible_top_level_keys
from services.label_config.parser import LabelConfigParser
from services.label_config.validator import LabelConfigValidator

DOCKET = """<View>
  <Header value="Docket"/>
  <Repeater on="$cases" indexFlag="{{idx}}" mode="pagination" answerKey="case">
    <Text name="case_{{idx}}" value="$cases[{{idx}}].text"/>
    <Number name="risk_{{idx}}" toName="case_{{idx}}" min="0" max="100"/>
    <Choices name="priority_{{idx}}" toName="case_{{idx}}">
      <Choice value="high"/><Choice value="low"/>
    </Choices>
  </Repeater>
  <TextArea name="summary" toName="intro"/>
  <Text name="intro" value="$intro"/>
</View>"""

TASK = {
    "intro": "Three cases.",
    "cases": [{"text": "One."}, {"text": "Two."}, {"text": "Three."}],
    "reference_solution": "never shown to annotators",
}


class TestValidator:
    def test_repeater_config_is_valid(self):
        assert LabelConfigValidator.validate(DOCKET) == (True, [])

    def test_template_names_are_checked_as_their_first_expansion(self):
        cfg = '<View><Repeater on="$a"><Number name="1x_{{idx}}" toName="t"/></Repeater></View>'
        valid, errors = LabelConfigValidator.validate(cfg)
        assert not valid
        assert any("Invalid field name '1x_{{idx}}'" in e for e in errors)

    @pytest.mark.parametrize(
        "inner, attrs, message",
        [
            ('<Number name="n" toName="t"/>', 'on="$a"', "must contain the index flag"),
            ('<Number name="n_{{idx}}" toName="t"/>', 'on="a"', "requires an 'on' attribute"),
            (
                '<Repeater on="$b" indexFlag="#j"><Number name="n_{{idx}}_#j" toName="t"/></Repeater>',
                'on="$a"',
                "Nested <Repeater>",
            ),
        ],
    )
    def test_repeater_rules_are_enforced(self, inner, attrs, message):
        valid, errors = LabelConfigValidator.validate(
            f"<View><Repeater {attrs}>{inner}</Repeater></View>"
        )
        assert not valid
        assert any(message in e for e in errors), errors

    def test_expanded_config_is_valid_too(self):
        assert LabelConfigValidator.validate(expand_repeaters(DOCKET, TASK)) == (True, [])


class TestParser:
    def test_fields_without_task_data_keep_template_names(self):
        fields = {f["name"]: f for f in LabelConfigParser.extract_fields(DOCKET)}
        risk = fields["risk_{{idx}}"]
        assert risk["repeater"] == {"on": "$cases", "index_flag": "{{idx}}", "item_key": "risk"}
        assert "repeater" not in fields["summary"]

    def test_fields_with_task_data_are_expanded(self):
        names = [f["name"] for f in LabelConfigParser.extract_fields(DOCKET, task_data=TASK)]
        assert names == [
            "case_0", "risk_0", "priority_0",
            "case_1", "risk_1", "priority_1",
            "case_2", "risk_2", "priority_2",
            "summary", "intro",
        ]
        fields = LabelConfigParser.extract_fields(DOCKET, task_data=TASK)
        assert all("repeater" not in f for f in fields)

    def test_bound_fields_include_the_repeated_array(self):
        bound = LabelConfigParser.bound_data_fields(DOCKET)
        assert {"cases", "intro"} <= bound


class TestBlinding:
    def test_indexed_bindings_keep_their_top_level_key(self):
        assert visible_top_level_keys({"cases[{{idx}}].text", "cases[0].text", "doc.text"}) == {
            "cases",
            "doc",
        }

    def test_annotators_see_the_repeated_array_but_not_unbound_keys(self):
        visible = blind_task_data(TASK, LabelConfigParser.bound_data_fields(DOCKET))
        assert visible == {"intro": TASK["intro"], "cases": TASK["cases"]}


class TestLabelStudioExportTargets:
    STORED = [
        {"from_name": "risk_0", "type": "number", "value": {"number": 45}},
        {"from_name": "priority_2", "to_name": "text", "type": "choices", "value": {"choices": ["low"]}},
        {"from_name": "summary", "to_name": "intro", "type": "textarea", "value": {"text": ["s"]}},
        {"from_name": "__response__", "type": "textarea", "value": {"text": ["raw"]}},
    ]

    def test_missing_or_dangling_to_name_gets_the_controls_target(self):
        targets = control_targets(expand_repeaters(DOCKET, TASK))
        stored = copy.deepcopy(self.STORED)
        out = convert_to_label_studio_format(stored, targets)
        assert [r.get("to_name") for r in out] == ["case_0", "case_2", "intro", None]
        # the stored results are not touched
        assert stored == self.STORED

    def test_without_targets_results_pass_through(self):
        assert convert_to_label_studio_format(copy.deepcopy(self.STORED)) == self.STORED

    def test_control_targets(self):
        targets, objects = control_targets(expand_repeaters(DOCKET, TASK))
        assert targets["risk_1"] == "case_1"
        assert {"case_0", "case_1", "case_2", "intro"} <= objects
        assert control_targets("<View") == ({}, set())
