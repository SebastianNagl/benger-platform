"""Retired official models (shared/model_availability.py, migration 161).

Switching a catalog row off hid it from the pickers but did not stop saved
configs from using it. Now:

* generation start refuses an inactive official model, naming it;
* evaluation start refuses an inactive official judge, naming it;
* migration 161 rewrites saved references (generation config, model id
  list, evaluation config judges, project and organization OCR model) from
  each retired id to its replacement, and leaves results alone.
"""

from __future__ import annotations

import importlib.util
import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import LLMModel, ResponseGeneration, User
from project_models import Project, Task
from tests.fixtures.access_keys import seed_world
from tests.fixtures.v1 import make_project, v1_auth

MIGRATION_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "alembic",
        "versions",
        "161_retired_model_references.py",
    )
)


def _uid() -> str:
    return str(uuid.uuid4())


def _catalog_row(model_id: str, *, active: bool, official: bool = True) -> LLMModel:
    return LLMModel(
        id=model_id,
        name=model_id,
        provider="OpenAI",
        model_type="chat",
        capabilities=["text-generation"],
        is_active=active,
        is_official=official,
    )


# --------------------------------------------------------------------------- #
# generation start
# --------------------------------------------------------------------------- #


@pytest.fixture
async def world(async_test_db):
    w = await seed_world(async_test_db, group=False)
    w["project"] = await make_project(
        async_test_db, w["admin"].id, org_id=w["org"].id, title="retired"
    )
    await async_test_db.commit()
    return w


async def test_generation_start_refuses_a_retired_official_model(
    async_test_client, async_test_db, world
):
    retired = _catalog_row(f"retired-{uuid.uuid4().hex[:6]}", active=False)
    async_test_db.add(retired)
    world["project"].generation_config = {
        "prompt_structures": {
            "s": {"name": "S", "system_prompt": "Sys", "instruction_prompt": "Q"}
        },
        "selected_configuration": {"models": [retired.id], "active_structures": ["s"]},
    }
    await async_test_db.commit()

    with v1_auth(async_test_db, session_user=world["admin"]):
        start = await async_test_client.post(
            f"/api/generation-tasks/projects/{world['project'].id}/generate",
            json={"mode": "missing", "structure_keys": ["s"]},
        )
    assert start.status_code == 400, start.text
    detail = start.json()["detail"]
    assert retired.id in detail
    assert "no longer available" in detail


# --------------------------------------------------------------------------- #
# evaluation start
# --------------------------------------------------------------------------- #


@contextmanager
def _as_user(db_user):
    app.dependency_overrides[require_user] = lambda: AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    try:
        yield
    finally:
        app.dependency_overrides.pop(require_user, None)


def _user(db) -> User:
    user = User(
        id=_uid(),
        username=f"rm-{_uid()[:8]}",
        email=f"{_uid()[:8]}@example.com",
        name="Retired Models",
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()
    return user


def _eval_project(db, user) -> Project:
    project = Project(
        id=_uid(),
        title="Retired judge",
        created_by=user.id,
        label_config=(
            '<View><Text name="text" value="$text"/>'
            '<TextArea name="answer" toName="text"/></View>'
        ),
    )
    db.add(project)
    db.flush()
    db.add(Task(id=_uid(), project_id=project.id, inner_id=1, data={"text": "Q", "reference": "A"}))
    db.flush()
    return project


def _judge_config(metric_parameters):
    return {
        "id": "cfg-judge",
        "metric": "llm_judge_classic",
        "prediction_fields": ["answer"],
        "reference_fields": ["reference"],
        "enabled": True,
        "metric_parameters": metric_parameters,
    }


def _start_evaluation(client, user, project, config):
    with _as_user(user), patch(
        "routers.evaluations.multi_field.run.celery_app.send_task",
        return_value=MagicMock(id="celery-run"),
    ), patch(
        "routers.evaluations.multi_field.run.resolve_user_org_for_project",
        return_value=None,
    ):
        return client.post(
            "/api/evaluations/run",
            json={"project_id": project.id, "evaluation_configs": [config]},
        )


@pytest.mark.integration
class TestEvaluationStart:
    @pytest.mark.parametrize(
        "params",
        [
            lambda judge: {"judge_model": judge},
            lambda judge: {"judges": [{"judge_model_id": "current-judge", "runs": 1},
                                      {"judge_model_id": judge, "runs": 2}]},
        ],
        ids=["legacy-judge", "judge-list"],
    )
    def test_a_retired_judge_is_refused_before_a_run_exists(self, client, test_db, params):
        from models import EvaluationRun

        retired = _catalog_row(f"retired-{uuid.uuid4().hex[:6]}", active=False)
        test_db.add_all([retired, _catalog_row("current-judge", active=True)])
        user = _user(test_db)
        project = _eval_project(test_db, user)
        test_db.commit()

        r = _start_evaluation(client, user, project, _judge_config(params(retired.id)))
        assert r.status_code == 400, r.text
        assert retired.id in r.json()["detail"]
        assert test_db.query(EvaluationRun).filter_by(project_id=project.id).count() == 0

    def test_an_active_judge_still_starts(self, client, test_db):
        test_db.add(_catalog_row("current-judge-2", active=True))
        user = _user(test_db)
        project = _eval_project(test_db, user)
        test_db.commit()

        r = _start_evaluation(
            client, user, project, _judge_config({"judge_model": "current-judge-2"})
        )
        assert r.status_code == 200, r.text

    def test_an_inactive_custom_judge_is_left_to_the_custom_checks(self, client, test_db):
        """Only official rows are refused here; a custom row's liveness and
        access are checked where its credential is resolved."""
        from model_availability import inactive_official_model_ids

        custom = _catalog_row(f"custom-{uuid.uuid4().hex[:6]}", active=False, official=False)
        custom.base_url = "https://example.com/v1"
        custom.endpoint_model_name = "m"
        test_db.add(custom)
        test_db.commit()
        assert inactive_official_model_ids(test_db, [custom.id]) == []


# --------------------------------------------------------------------------- #
# migration 161
# --------------------------------------------------------------------------- #


@pytest.fixture
def migration():
    spec = importlib.util.spec_from_file_location("retired_model_references", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.integration
class TestMigration161:
    def test_saved_references_move_to_the_replacements(self, test_db, migration, capsys):
        from models import Organization

        user = _user(test_db)
        org = Organization(
            id=_uid(),
            name="Org",
            display_name="Org",
            slug=f"org-{_uid()[:8]}",
            settings={"handwriting_ocr_model": "gpt-5-mini", "other": 1},
        )
        test_db.add(org)
        project = Project(
            id=_uid(),
            title="Saved configs",
            created_by=user.id,
            handwriting_ocr_model="gemini-2.5-pro",
            llm_model_ids=["gpt-5", "o3", "gpt-4o"],
            generation_config={
                "prompt_structures": {"s": {"name": "S"}},
                "selected_configuration": {
                    "models": ["gpt-5-mini", "gpt-6.1-terra", "claude-sonnet-4-5-20250929"],
                    "model_configs": {
                        "gpt-5-mini": {"max_tokens": 5000},
                        "gpt-6.1-terra": {"max_tokens": 9000},
                        "o3": {"reasoning_effort": "high"},
                        "gpt-4o": {"temperature": 0.2},
                    },
                    "parameters": {"temperature": 0.0},
                },
            },
            evaluation_config={
                "evaluation_configs": [
                    {
                        "id": "a",
                        "metric": "llm_judge_classic",
                        "display_name": "Notenpunkte (gpt-5, o3; gpt-5.4-mini)",
                        "metric_parameters": {
                            "judge_model": "gpt-5",
                            "judges": [
                                {"judge_model_id": "o3", "runs": 2},
                                {"judge_model_id": "gpt-6.1-sol", "runs": 1},
                                {"judge_model_id": "Qwen/Qwen3-Max", "runs": 1},
                            ],
                            "rubric_selector": {"generator_model_id": "gpt-5"},
                        },
                    },
                    {
                        "id": "b",
                        "metric": "bleu",
                        "display_name": "BLEU (not gpt-5)",
                    },
                ],
                "selected_methods": {
                    "answer": {"automated": [{"name": "llm_judge_classic", "parameters": {"judge_model": "gemini-3.7-flash"}}]}
                },
            },
        )
        untouched = Project(
            id=_uid(),
            title="Current models only",
            created_by=user.id,
            llm_model_ids=["gpt-5.4-mini"],
            generation_config={"selected_configuration": {"models": ["gpt-5.4-mini"]}},
        )
        test_db.add_all([project, untouched])
        test_db.flush()
        result = ResponseGeneration(
            id=_uid(), project_id=project.id, model_id="gpt-5-mini", status="completed",
            created_by=user.id,
        )
        test_db.add(result)
        test_db.commit()

        with patch.object(migration.op, "get_bind", return_value=test_db.connection()):
            migration.upgrade()
        test_db.commit()
        out = capsys.readouterr().out
        assert "projects.generation_config=1" in out
        assert "projects.llm_model_ids=1" in out
        assert "projects.evaluation_config=1" in out
        assert "organizations.settings=1" in out
        assert "projects.handwriting_ocr_model=1" in out

        test_db.expire_all()
        p = test_db.get(Project, project.id)
        selected = p.generation_config["selected_configuration"]
        assert selected["models"] == ["gpt-6.1-terra", "claude-sonnet-5-5"]
        # The replacement's own settings win; a retired model's move over.
        assert selected["model_configs"] == {
            "gpt-6.1-terra": {"max_tokens": 9000},
            "gpt-6.1-sol": {"reasoning_effort": "high"},
            "gpt-4o": {"temperature": 0.2},
        }
        assert selected["parameters"] == {"temperature": 0.0}
        assert p.generation_config["prompt_structures"] == {"s": {"name": "S"}}
        assert p.llm_model_ids == ["gpt-6.1-sol", "gpt-4o"]
        params = p.evaluation_config["evaluation_configs"][0]["metric_parameters"]
        assert params["judge_model"] == "gpt-6.1-sol"
        assert params["judges"] == [
            {"judge_model_id": "gpt-6.1-sol", "runs": 2},
            {"judge_model_id": "Qwen/Qwen3.8-Max", "runs": 1},
        ]
        entries = p.evaluation_config["evaluation_configs"]
        # The label follows the judge; a longer id that merely starts with a
        # retired one, and an entry whose judge did not move, keep theirs.
        assert entries[0]["display_name"] == "Notenpunkte (gpt-6.1-sol, gpt-6.1-sol; gpt-5.4-mini)"
        assert entries[1]["display_name"] == "BLEU (not gpt-5)"
        # A rubric lookup key names past records, not a model to call.
        assert params["rubric_selector"] == {"generator_model_id": "gpt-5"}
        legacy = p.evaluation_config["selected_methods"]["answer"]["automated"][0]
        assert legacy["parameters"]["judge_model"] == "gemini-3.8-flash"
        assert p.handwriting_ocr_model == "gemini-3.8-flash"
        assert test_db.get(Organization, org.id).settings == {
            "handwriting_ocr_model": "gpt-6.1-terra",
            "other": 1,
        }
        # Results keep the model they were produced with.
        assert test_db.get(ResponseGeneration, result.id).model_id == "gpt-5-mini"
        u = test_db.get(Project, untouched.id)
        assert u.llm_model_ids == ["gpt-5.4-mini"]

        # Idempotent: a second run finds nothing left to rewrite.
        with patch.object(migration.op, "get_bind", return_value=test_db.connection()):
            migration.upgrade()
        test_db.commit()
        second = capsys.readouterr().out
        assert "projects.generation_config=0" in second
        assert "projects.handwriting_ocr_model=0" in second

    def test_every_replacement_is_an_active_catalog_model(self, migration):
        from seeds.llm_models_loader import load_catalog

        by_id = {m["id"]: m for m in load_catalog().models}
        for retired, replacement in migration.REPLACEMENTS.items():
            assert by_id[retired]["is_active"] is False, retired
            assert by_id[replacement]["is_active"] is True, replacement

    def test_rewriters_leave_unrelated_shapes_alone(self, migration):
        assert migration.rewrite_generation_config(None) is None
        assert migration.rewrite_generation_config({"selected_configuration": "x"}) is None
        assert migration.rewrite_evaluation_config({"evaluation_configs": []}) is None
        assert migration.rewrite_org_settings({"handwriting_ocr_model": "gpt-5.6-luna"}) is None
        assert json.dumps(migration.REPLACEMENTS)  # plain data
