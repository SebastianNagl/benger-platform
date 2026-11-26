"""Retired official models stop in the worker (shared/model_availability.py).

The API refuses an inactive official model at generation and evaluation
start; jobs that were queued earlier, resumes and retries of older runs, and
judges resolved inside a run reach the worker without that check. There:

* the judge factory raises ``InactiveModelError`` for an inactive official
  judge instead of building an evaluator that fails every cell;
* a generation job for an inactive official model fails with the same
  message before any provider service is resolved.

Custom (BYOM) rows keep their own liveness and access checks.
"""

import os
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml_evaluation.llm_judge_evaluator import create_llm_judge_for_user  # noqa: E402
from model_availability import (  # noqa: E402
    InactiveModelError,
    configured_judge_model_ids,
    inactive_models_message,
    row_is_inactive_official,
)


def _row(model_id, *, official, active):
    row = MagicMock()
    row.id = model_id
    row.name = model_id
    row.is_official = official
    row.is_active = active
    return row


def _db_returning(row):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = row
    return db


class TestHelpers:
    def test_only_switched_off_official_rows_count(self):
        assert row_is_inactive_official(_row("a", official=True, active=False))
        assert not row_is_inactive_official(_row("a", official=True, active=True))
        assert not row_is_inactive_official(_row("custom-a", official=False, active=False))
        assert not row_is_inactive_official(None)

    def test_configured_judges_are_the_explicit_ones(self):
        assert configured_judge_model_ids(None) == []
        assert configured_judge_model_ids({}) == []
        assert configured_judge_model_ids(
            {"judge_model": "a", "judges": [{"judge_model_id": "b"}, {"runs": 2}, "x"]}
        ) == ["a", "b"]

    def test_the_message_names_each_model_once(self):
        message = inactive_models_message(["o3", "gpt-5", "o3"])
        assert message.startswith("Model(s) no longer available: gpt-5, o3.")


class TestJudgeFactory:
    def test_a_retired_official_judge_is_refused(self):
        import ai_services.user_aware_ai_service  # noqa: F401

        uaas_mod = sys.modules["ai_services.user_aware_ai_service"]
        fake_singleton = MagicMock()
        with patch.object(uaas_mod, "user_aware_ai_service", fake_singleton):
            with pytest.raises(InactiveModelError) as exc:
                create_llm_judge_for_user(
                    db=_db_returning(_row("gpt-5-mini", official=True, active=False)),
                    user_id="user-1",
                    provider="openai",
                    judge_model="gpt-5-mini",
                )
        assert exc.value.model_ids == ["gpt-5-mini"]
        assert "gpt-5-mini" in str(exc.value)
        fake_singleton.get_ai_service_for_user.assert_not_called()
        fake_singleton.get_ai_service_for_model_row.assert_not_called()

    def test_an_active_judge_is_built(self):
        import ai_services.user_aware_ai_service  # noqa: F401

        uaas_mod = sys.modules["ai_services.user_aware_ai_service"]
        fake_singleton = MagicMock()
        with patch.object(uaas_mod, "user_aware_ai_service", fake_singleton):
            evaluator = create_llm_judge_for_user(
                db=_db_returning(_row("gpt-6.1-terra", official=True, active=True)),
                user_id="user-1",
                provider="openai",
                judge_model="gpt-6.1-terra",
            )
        assert evaluator.judge_model == "gpt-6.1-terra"
        fake_singleton.get_ai_service_for_user.assert_called_once()

    def test_a_custom_judge_is_left_to_its_own_checks(self):
        import ai_services.user_aware_ai_service  # noqa: F401

        uaas_mod = sys.modules["ai_services.user_aware_ai_service"]
        fake_singleton = MagicMock()
        fake_singleton.get_ai_service_for_model_row.return_value = None
        with patch.object(uaas_mod, "user_aware_ai_service", fake_singleton):
            create_llm_judge_for_user(
                db=_db_returning(_row("custom-x", official=False, active=False)),
                user_id="user-1",
                provider="openai",
                judge_model="custom-x",
            )
        fake_singleton.get_ai_service_for_model_row.assert_called_once()


def _query_side_effect(gen, project, task, model):
    """The worker's lookup order: generation, project, task, model."""
    calls = [0]

    def side_effect(*args):
        q = MagicMock()
        calls[0] += 1
        if calls[0] == 1:
            q.filter.return_value.first.return_value = gen
        elif calls[0] == 2:
            q.filter.return_value.first.return_value = project
        elif calls[0] == 3:
            q.filter.return_value.first.return_value = task
            q.filter.return_value.filter.return_value.first.return_value = task
        elif calls[0] == 4:
            q.filter.return_value.first.return_value = model
        else:
            q.filter.return_value.first.return_value = gen
        return q

    return side_effect


class TestGenerationWorker:
    def test_a_job_for_a_retired_official_model_fails_before_any_provider_call(self):
        import tasks as tasks_module
        from tasks import generate_llm_responses

        gen = MagicMock()
        gen.status = "pending"
        gen.task_id = "task-1"
        gen.structure_key = None
        gen.runs_requested = 1
        project = MagicMock()
        project.deleted_at = None
        project.generation_config = {
            "prompt_structures": [
                {
                    "key": "default",
                    "structure": {"system_prompt": "Du bist Richter.", "instruction_prompt": "$text"},
                },
            ],
            "selected_configuration": {"models": ["o3"]},
        }
        task = MagicMock()
        task.id = "task-1"
        task.project_id = "p1"
        task.data = {"text": "Ein erfundener Sachverhalt."}
        task.meta = {}
        task.created_at = datetime.now()
        model = _row("o3", official=True, active=False)
        model.default_config = None

        db = MagicMock()
        db.query.side_effect = _query_side_effect(gen, project, task, model)
        user_aware = MagicMock()

        with patch.object(tasks_module, "HAS_DATABASE", True), patch.object(
            tasks_module, "HAS_AI_SERVICES", True
        ), patch.object(tasks_module, "SessionLocal", MagicMock(return_value=db)), patch.object(
            tasks_module, "user_aware_ai_service", user_aware
        ), patch.object(tasks_module, "notify_task_completed", MagicMock()):
            result = generate_llm_responses(
                generation_id="gen-1",
                config_data={"project_id": "p1"},
                model_id="o3",
                user_id="u1",
                structure_key="default",
                organization_id=None,
            )

        assert result["status"] == "error", result
        assert result["message"] == inactive_models_message(["o3"])
        assert gen.status == "failed"
        assert gen.error_message == inactive_models_message(["o3"])
        user_aware.get_ai_service_for_user.assert_not_called()
        user_aware.get_ai_service_for_model_row.assert_not_called()
