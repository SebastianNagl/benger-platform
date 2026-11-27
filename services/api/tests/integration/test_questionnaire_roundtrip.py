"""Questionnaires survive a full project export and import, in both formats.

Every moment's questionnaire comes back with each version's text, and every
answer with its version, hash, skip flag and links moved to the imported
rows: the participant's task and submission, the grader's grade row.
"""

import io
import json
import uuid

import pytest

from models import TaskEvaluation
from project_models import (
    Annotation,
    ProjectQuestionnaire,
    ProjectQuestionnaireVersion,
    QuestionnaireResponse,
    Task,
)
from routers.projects._export_stream import stream_comprehensive_project_data_json
from import_stream import run_full_project_import
from export_stream import stream_export_ndjson
from questionnaires import config_hash
from tests.fixtures.questionnaires import questionnaire
from tests.integration.test_ndjson_roundtrip import full_project  # noqa: F401  (fixture)

V1 = '<View><Likert name="motivation" toName="motivation" min="1" max="7"/></View>'
V2 = '<View><Likert name="motivation" toName="motivation" min="1" max="5"/></View>'
AFTER = '<View><Rating name="confidence" toName="confidence" maxRating="5"/></View>'
GRADER = '<View><TextArea name="note" toName="note"/></View>'


def _uid() -> str:
    return str(uuid.uuid4())


def _seed(db, project, admin):
    before = ProjectQuestionnaire(
        id=_uid(), project_id=project.id, trigger="before_task", enabled=True, config=V2,
        required=False, frequency="once_per_task", version=2,
    )
    # The fixture's after_submit answers (one per annotation) made this one.
    after = questionnaire(db, project.id, "after_submit")
    after.config, after.version = AFTER, 1
    grader = ProjectQuestionnaire(
        id=_uid(), project_id=project.id, trigger="korrektur", enabled=True, config=GRADER,
        required=False, frequency="once_per_submission", version=1,
    )
    db.add_all([before, grader])
    db.flush()
    for q, texts in ((before, [V1, V2]), (after, [AFTER]), (grader, [GRADER])):
        for n, text in enumerate(texts, start=1):
            db.add(ProjectQuestionnaireVersion(
                id=_uid(), questionnaire_id=q.id, version=n, config=text,
                config_hash=config_hash(text),
            ))
    tasks = db.query(Task).filter(Task.project_id == project.id).order_by(Task.inner_id).all()
    te = db.query(TaskEvaluation).filter(TaskEvaluation.task_id == tasks[1].id).first()
    te.created_by = admin.id
    db.add_all([
        QuestionnaireResponse(
            id=_uid(), project_id=project.id, questionnaire_id=before.id, trigger="before_task",
            questionnaire_version=1, config_hash=config_hash(V1), user_id=admin.id,
            task_id=tasks[0].id, subject_key=f"task:{tasks[0].id}",
            result=[{"from_name": "motivation", "type": "likert", "value": 6}],
        ),
        QuestionnaireResponse(
            id=_uid(), project_id=project.id, questionnaire_id=before.id, trigger="before_task",
            questionnaire_version=2, config_hash=config_hash(V2), user_id=admin.id,
            task_id=tasks[1].id, subject_key=f"task:{tasks[1].id}", skipped=True, result=[],
        ),
        QuestionnaireResponse(
            id=_uid(), project_id=project.id, questionnaire_id=grader.id, trigger="korrektur",
            questionnaire_version=1, config_hash=config_hash(GRADER), user_id=admin.id,
            task_id=te.task_id, task_evaluation_id=te.id,
            subject_key=f"generation:{te.generation_id}",
            result=[{"from_name": "note", "type": "textarea", "value": {"text": ["ok"]}}],
        ),
    ])
    db.commit()


def _snapshot(db, project_id):
    tasks = {t.id: t.inner_id for t in db.query(Task).filter(Task.project_id == project_id)}
    questionnaires = {
        q.trigger: (
            q.enabled, q.config, q.required, q.frequency, q.version,
            [(v.version, v.config, v.config_hash) for v in q.versions],
        )
        for q in db.query(ProjectQuestionnaire).filter(ProjectQuestionnaire.project_id == project_id)
    }
    answers = []
    for r in db.query(QuestionnaireResponse).filter(QuestionnaireResponse.project_id == project_id):
        te = db.get(TaskEvaluation, r.task_evaluation_id) if r.task_evaluation_id else None
        ann = db.get(Annotation, r.annotation_id) if r.annotation_id else None
        # Links compared by what they point at, not by id.
        kind, _, target = r.subject_key.partition(":")
        answers.append((
            r.trigger, r.questionnaire_version, r.config_hash, r.skipped,
            json.dumps(r.result, sort_keys=True), tasks.get(r.task_id),
            tasks.get(ann.task_id) if ann else None,
            (tasks.get(te.task_id), te.field_name) if te else None,
            kind, r.questionnaire.trigger,
        ))
        # The subject key names the imported row.
        if kind == "task":
            assert target in tasks
        if kind == "annotation":
            assert target == r.annotation_id
        if kind == "generation":
            assert te is not None and target == te.generation_id
    return questionnaires, sorted(answers, key=repr)


@pytest.mark.integration
@pytest.mark.parametrize("fmt", ["json", "ndjson"])
def test_questionnaires_and_answers_roundtrip(test_db, full_project, fmt):  # noqa: F811
    project, admin = full_project
    _seed(test_db, project, admin)
    if fmt == "json":
        payload = "".join(stream_comprehensive_project_data_json(test_db, project.id))
        data = json.loads(payload)
        assert [q["trigger"] for q in data["project"]["questionnaires"]] == [
            "after_submit", "before_task", "korrektur"]
        assert len(data["questionnaire_responses"]) == 3 + 3  # + the fixture's after_submit answers
        # The #1208 section keeps carrying the after_submit answers.
        assert {r["annotation_id"] for r in data["post_annotation_responses"]} <= {
            r["annotation_id"] for r in data["questionnaire_responses"]}
    else:
        payload = "".join(stream_export_ndjson(test_db, project.id))

    result = run_full_project_import(test_db, io.BytesIO(payload.encode("utf-8")), admin.id)
    new_pid = result["project_id"]

    assert _snapshot(test_db, new_pid) == _snapshot(test_db, project.id)
    # Imported once, although the #1208 section repeats the after_submit answers.
    assert test_db.query(QuestionnaireResponse).filter(
        QuestionnaireResponse.project_id == new_pid).count() == 6


@pytest.mark.integration
def test_an_export_from_before_the_store_imports_its_questionnaire(test_db, full_project):  # noqa: F811
    """An older export has only the project's two #1208 fields and the
    ``post_annotation_responses`` section: they become the after_submit
    questionnaire and its answers."""
    project, admin = full_project
    data = json.loads("".join(stream_comprehensive_project_data_json(test_db, project.id)))
    data["project"].pop("questionnaires")
    data.pop("questionnaire_responses")
    data["project"]["questionnaire_enabled"] = True
    data["project"]["questionnaire_config"] = AFTER

    result = run_full_project_import(
        test_db, io.BytesIO(json.dumps(data).encode("utf-8")), admin.id)
    new_pid = result["project_id"]

    (q,) = test_db.query(ProjectQuestionnaire).filter(
        ProjectQuestionnaire.project_id == new_pid).all()
    assert (q.trigger, q.enabled, q.config, q.version, q.frequency) == (
        "after_submit", True, AFTER, 1, "once_per_submission")
    answers = test_db.query(QuestionnaireResponse).filter(
        QuestionnaireResponse.project_id == new_pid).all()
    assert len(answers) == len(data["post_annotation_responses"]) == 3
    assert all(a.trigger == "after_submit" and a.questionnaire_id == q.id for a in answers)
    assert {a.config_hash for a in answers} == {"c" * 64}
