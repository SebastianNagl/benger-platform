"""The Label Studio export of a project whose label config has a <Repeater>.

Results parsed from array answers are stored under the expanded, indexed
control names (risk_0, risk_1, ...), which is what Label Studio itself
stores for an expanded Repeater. Label Studio only renders a result that
names its object in ``to_name``, so the export fills a missing or dangling
``to_name`` from the control's ``toName`` in the task's expanded config.
"""

import json

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.database]

DOCKET = """<View>
  <Repeater on="$cases" indexFlag="{{idx}}" answerKey="case">
    <Text name="case_{{idx}}" value="$cases[{{idx}}].text"/>
    <Number name="risk_{{idx}}" toName="case_{{idx}}" min="0" max="100"/>
    <TextArea name="note_{{idx}}" toName="case_{{idx}}"/>
  </Repeater>
</View>"""


def test_label_studio_export_targets_indexed_results(
    db_conn, make_user, make_project, make_task, make_annotation,
):
    from export_stream import select_export_generator
    from response_parser import ResponseParser

    user = make_user()
    project = make_project(created_by=user.id, label_config=DOCKET)
    parser = ResponseParser({}, DOCKET)
    tasks = []
    for cases, answer in (
        (["One.", "Two.", "Three."], [{"case": 3, "risk": 70, "note": "c"}, {"case": 1, "risk": 10, "note": "a"}, {"case": 2, "risk": 40, "note": "b"}]),
        (["Only."], [{"case": 1, "risk": 5, "note": "x"}]),
    ):
        data = {"cases": [{"text": text} for text in cases]}
        task = make_task(project.id, data, created_by=user.id)
        parsed = parser.parse(json.dumps(answer), task_data=data)
        assert parsed.status == "success", parsed.error
        make_annotation(project.id, task.id, user.id, parsed.parsed_annotation)
        tasks.append(task)

    exported = json.loads("".join(select_export_generator(db_conn, project, "label_studio")))

    by_task = {t["data"]["cases"][0]["text"]: t for t in exported}
    first = by_task["One."]["annotations"][0]["result"]
    assert {r["from_name"]: (r["to_name"], r["value"]) for r in first} == {
        "risk_0": ("case_0", {"number": 10}),
        "note_0": ("case_0", {"text": ["a"]}),
        "risk_1": ("case_1", {"number": 40}),
        "note_1": ("case_1", {"text": ["b"]}),
        "risk_2": ("case_2", {"number": 70}),
        "note_2": ("case_2", {"text": ["c"]}),
    }
    single = by_task["Only."]["annotations"][0]["result"]
    assert {r["from_name"]: r["to_name"] for r in single} == {"risk_0": "case_0", "note_0": "case_0"}

    # The stored rows keep what the parser wrote (no to_name added).
    from project_models import Annotation

    db_conn.expire_all()
    stored = db_conn.query(Annotation).filter(Annotation.task_id == tasks[0].id).one()
    assert all("to_name" not in r for r in stored.result)
