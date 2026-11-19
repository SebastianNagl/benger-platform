"""The test stack's seeded evaluations (init_complete.setup_e2e_evaluations)
carry the id of the evaluation config the project declares, so the
evaluations page and its statistics, which select per-task rows by config
id, show them; rows seeded before that are tagged on the next seed run."""

import json
import uuid
from datetime import datetime, timezone

from init_complete import E2E_EVAL_CONFIG_ID, setup_e2e_evaluations
from models import Generation, ResponseGeneration, TaskEvaluation, User
from project_models import Project, Task


def _uid():
    return str(uuid.uuid4())


def _seed(db):
    # Earlier seeds of the same database own these names; inside the test's
    # transaction they step aside (rolled back afterwards).
    for p in db.query(Project).filter(Project.title == "E2E QA Project").all():
        p.title = f"E2E QA Project (earlier {p.id[:8]})"
    admin = db.query(User).filter(User.email == "admin@example.com").first()
    if admin is None:
        admin = User(id=_uid(), username=f"admin-{_uid()[:8]}", email="admin@example.com", name="Admin",
                     is_superadmin=True, is_active=True, email_verified=True,
                     created_at=datetime.now(timezone.utc))
        db.add(admin)
        db.flush()
    project = Project(id=_uid(), title="E2E QA Project", created_by=admin.id,
                      label_config='<View><Text name="q" value="$q"/></View>')
    db.add(project)
    db.flush()
    for i in range(3):
        task = Task(id=_uid(), project_id=project.id, data={"q": f"question {i}"}, inner_id=i + 1,
                    created_by=admin.id)
        db.add(task)
        db.flush()
        rg = ResponseGeneration(id=_uid(), project_id=project.id, task_id=task.id, model_id="gpt-4-turbo",
                                status="completed", created_by=admin.id)
        db.add(rg)
        db.flush()
        db.add(Generation(id=_uid(), generation_id=rg.id, task_id=task.id, model_id="gpt-4-turbo",
                          case_data="{}", response_content=f"answer {i}", status="completed",
                          response_metadata=json.dumps({})))
    db.commit()
    return project


def _rows(db, project):
    from models import EvaluationRun

    run_ids = [r.id for r in db.query(EvaluationRun).filter(EvaluationRun.project_id == project.id)]
    return db.query(TaskEvaluation).filter(TaskEvaluation.evaluation_id.in_(run_ids)).all()


def test_seeded_task_evaluations_carry_the_declared_config_id(test_db):
    project = _seed(test_db)
    setup_e2e_evaluations(test_db)
    test_db.refresh(project)

    rows = _rows(test_db, project)
    assert len(rows) == 3
    assert {r.evaluation_config_id for r in rows} == {E2E_EVAL_CONFIG_ID}
    declared = [c["id"] for c in project.evaluation_config["evaluation_configs"]]
    assert declared == [E2E_EVAL_CONFIG_ID]


def test_a_later_seed_run_tags_rows_seeded_without_the_config_id(test_db):
    project = _seed(test_db)
    setup_e2e_evaluations(test_db)
    for row in _rows(test_db, project):
        row.evaluation_config_id = None
    test_db.commit()

    setup_e2e_evaluations(test_db)
    assert {r.evaluation_config_id for r in _rows(test_db, project)} == {E2E_EVAL_CONFIG_ID}
