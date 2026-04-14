"""Deep coverage tests for tasks.py.

Targets uncovered lines across:
- generate_llm_responses (cancelled, structure lookup, rate limiting, parsing, report update)
- generate_response (bridge task)
- run_evaluation (multiple branches)
- cleanup_project_data (TESTING env)
- send_bulk_invitations_task (edge cases)
- _extract_field_value_from_annotation / _extract_field_value_from_parsed_annotation
- run_single_sample_evaluation (multiple metric types)
- _evaluate_llm_judge_single
- process_all_digests_task / send_test_digest_task
- _get_provider_from_model
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, PropertyMock, call, patch

import pytest

workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

import tasks as tasks_module
from tasks import (
    _extract_field_value_from_annotation,
    _extract_field_value_from_parsed_annotation,
    cleanup_project_data,
    extract_label_config_fields,
    generate_classification_samples,
    generate_llm_responses,
    generate_synthetic_data,
    get_supported_metrics,
    send_bulk_invitations_task,
    send_invitation_email_task,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_db():
    """Create a mock DB session with chainable query/filter/first."""
    db = MagicMock()
    return db


def _mock_db_query_returns(db, return_value):
    """Configure db.query(...).filter(...).first() to return value."""
    db.query.return_value.filter.return_value.first.return_value = return_value
    return db


def _setup_generate_llm_mocks(
    ai_response_fn=None,
    generation_config=None,
    label_config=None,
    model_id="gpt-4",
    model_name="GPT-4",
    model_provider="OpenAI",
    parameter_constraints=None,
):
    """Build the standard mock objects for generate_llm_responses tests.

    Returns (db, gen, project, task, model, ai_service) and wires up
    db.query.side_effect with the standard 6-step lookup sequence.
    """
    db = _mock_db()

    gen = MagicMock()
    gen.status = "pending"
    gen.task_id = "task-1"
    gen.structure_key = None

    project = MagicMock()
    project.generation_config = generation_config
    project.label_config = label_config
    project.label_config_version = None

    task = MagicMock()
    task.id = "task-1"
    task.project_id = "p1"
    task.data = {"text": "test"}
    task.meta = {}
    task.created_at = datetime.now()

    model = MagicMock()
    model.id = model_id
    model.name = model_name
    model.provider = model_provider
    model.parameter_constraints = parameter_constraints

    ai_service = MagicMock()
    ai_service.is_available.return_value = True

    if ai_response_fn is None:
        async def ai_response_fn(**kwargs):
            return {
                "response_text": "answer",
                "prompt_tokens": 1,
                "completion_tokens": 1,
                "total_tokens": 2,
                "cost_usd": 0.0,
            }

    ai_service.generate_response = ai_response_fn
    # The generation code calls ai_service.generate(), not generate_response()
    if asyncio.iscoroutinefunction(ai_response_fn):
        def sync_generate(**kwargs):
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(ai_response_fn(**kwargs))
            finally:
                loop.close()
        ai_service.generate = sync_generate
    else:
        ai_service.generate = ai_response_fn

    call_idx = [0]
    def query_side_effect(*args):
        mock_q = MagicMock()
        call_idx[0] += 1
        if call_idx[0] == 1:
            mock_q.filter.return_value.first.return_value = gen
        elif call_idx[0] == 2:
            mock_q.filter.return_value.first.return_value = project
        elif call_idx[0] == 3:
            mock_q.filter.return_value.first.return_value = task
            mock_q.filter.return_value.filter.return_value.first.return_value = task
        elif call_idx[0] == 4:
            mock_q.filter.return_value.first.return_value = model
        elif call_idx[0] == 5:
            mock_q.join.return_value.filter.return_value.order_by.return_value.first.return_value = None
        elif call_idx[0] == 6:
            mock_q.filter.return_value.count.return_value = 0
        else:
            mock_q.filter.return_value.first.return_value = None
            mock_q.filter.return_value.distinct.return_value.all.return_value = []
        return mock_q

    db.query.side_effect = query_side_effect

    return db, gen, project, task, model, ai_service


def _run_generate_with_mocks(db, ai_service, config_data=None, model_id="gpt-4",
                              structure_key=None):
    """Execute generate_llm_responses with standard mock wiring."""
    if config_data is None:
        config_data = {"project_id": "p1"}

    mock_user_aware = MagicMock()
    mock_user_aware.get_ai_service_for_user.return_value = ai_service

    with patch.object(tasks_module, "user_aware_ai_service", mock_user_aware):
        with patch.object(tasks_module, "notify_task_completed", MagicMock()):
            kwargs = dict(
                generation_id="gen-1",
                config_data=config_data,
                model_id=model_id,
                user_id="u1",
            )
            if structure_key is not None:
                kwargs["structure_key"] = structure_key
            return generate_llm_responses(**kwargs)


# ===========================================================================
# _extract_field_value helpers
# ===========================================================================


class TestExtractFieldValueFromAnnotation:
    """Test _extract_field_value_from_annotation delegation."""

    @patch("annotation_utils.extract_field_value", return_value="extracted")
    def test_delegates_to_annotation_utils(self, mock_extract):
        result = _extract_field_value_from_annotation(
            [{"from_name": "answer", "value": {"text": ["yes"]}}], "answer"
        )
        mock_extract.assert_called_once()
        assert result == "extracted"

    @patch("annotation_utils.extract_field_value", return_value=None)
    def test_returns_none_when_field_missing(self, mock_extract):
        result = _extract_field_value_from_annotation([], "missing")
        assert result is None


class TestExtractFieldValueFromParsedAnnotation:
    """Test _extract_field_value_from_parsed_annotation delegation."""

    @patch("annotation_utils.extract_field_value", return_value="val")
    def test_delegates_to_annotation_utils(self, mock_extract):
        result = _extract_field_value_from_parsed_annotation(
            [{"from_name": "x", "value": {"text": ["val"]}}], "x"
        )
        assert result == "val"


# ===========================================================================
# cleanup_project_data - TESTING env path
# ===========================================================================


class TestCleanupProjectDataTestingEnv:
    """Test cleanup_project_data with TESTING=true."""

    @patch("tasks.redis")
    def test_uses_test_redis_db(self, mock_redis_module):
        mock_r = MagicMock()
        mock_r.delete.return_value = 0
        mock_redis_module.from_url.return_value = mock_r

        with patch.dict(os.environ, {"TESTING": "true"}):
            result = cleanup_project_data("proj-test")

        mock_redis_module.from_url.assert_called_with("redis://localhost:6379/1")
        assert result["status"] == "success"

    @patch("tasks.redis")
    def test_zero_deleted_keys(self, mock_redis_module):
        mock_r = MagicMock()
        mock_r.delete.return_value = 0
        mock_redis_module.from_url.return_value = mock_r

        result = cleanup_project_data("proj-empty")
        assert result["deleted_keys"] == 0
        assert result["status"] == "success"


# ===========================================================================
# generate_synthetic_data
# ===========================================================================


class TestGenerateSyntheticDataLabels:
    def test_alternating_labels(self):
        result = generate_synthetic_data("t1", num_samples=4)
        labels = [d["label"] for d in result["data"]]
        assert labels == ["contract", "agreement", "contract", "agreement"]

    def test_text_includes_task_id(self):
        result = generate_synthetic_data("my-task", num_samples=1)
        assert "my-task" in result["data"][0]["text"]


# ===========================================================================
# get_supported_metrics - error branch
# ===========================================================================


class TestGetSupportedMetricsError:
    def test_exception_returns_error(self):
        with patch.object(tasks_module, "evaluator_registry") as mock_reg:
            mock_reg.get_supported_metrics.side_effect = RuntimeError("boom")
            result = get_supported_metrics("qa")
        assert result["status"] == "error"
        assert "boom" in result["message"]


# ===========================================================================
# generate_llm_responses - cancelled generation
# ===========================================================================


class TestGenerateLLMResponsesCancelled:
    @patch("tasks.HAS_DATABASE", True)
    @patch("tasks.SessionLocal")
    def test_cancelled_generation_skipped(self, mock_session_cls):
        db = _mock_db()
        mock_session_cls.return_value = db

        gen = MagicMock()
        gen.status = "cancelled"
        db.query.return_value.filter.return_value.first.return_value = gen

        result = generate_llm_responses(
            generation_id="gen-1",
            config_data={"project_id": "p1"},
            model_id="gpt-4",
            user_id="u1",
        )
        assert result["status"] == "skipped"
        assert "cancelled" in result["message"]
        db.close.assert_called_once()


class TestGenerateLLMResponsesNoDatabase:
    @patch("tasks.HAS_DATABASE", False)
    def test_returns_error(self):
        result = generate_llm_responses(
            generation_id="gen-1",
            config_data={},
            model_id="m1",
            user_id="u1",
        )
        assert result["status"] == "error"
        assert "Database" in result["message"] or "database" in result["message"].lower()


class TestGenerateLLMResponsesGenerationNotFound:
    @patch("tasks.HAS_DATABASE", True)
    @patch("tasks.SessionLocal")
    def test_generation_not_found_raises(self, mock_session_cls):
        db = _mock_db()
        mock_session_cls.return_value = db
        db.query.return_value.filter.return_value.first.return_value = None

        result = generate_llm_responses(
            generation_id="missing-gen",
            config_data={"project_id": "p1"},
            model_id="m1",
            user_id="u1",
        )
        assert result["status"] == "error"
        assert "not found" in result["message"]


class TestGenerateLLMResponsesProjectNotFound:
    @patch("tasks.HAS_DATABASE", True)
    @patch("tasks.HAS_AI_SERVICES", True)
    @patch("tasks.SessionLocal")
    def test_project_not_found(self, mock_session_cls):
        db = _mock_db()
        mock_session_cls.return_value = db

        gen = MagicMock()
        gen.status = "pending"
        gen.structure_key = None

        call_count = [0]
        def query_side_effect(model):
            mock_q = MagicMock()
            call_count[0] += 1
            if call_count[0] == 1:
                # generation query
                mock_q.filter.return_value.first.return_value = gen
            else:
                # project query
                mock_q.filter.return_value.first.return_value = None
            return mock_q

        db.query.side_effect = query_side_effect

        result = generate_llm_responses(
            generation_id="gen-1",
            config_data={"project_id": "p1"},
            model_id="m1",
            user_id="u1",
        )
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()


class TestGenerateLLMResponsesStructureKeyListFormat:
    """Test structure_key lookup with list format prompt_structures."""

    @patch("tasks.HAS_DATABASE", True)
    @patch("tasks.HAS_AI_SERVICES", True)
    @patch("tasks.HAS_GENERATION_PARSER", False)
    @patch("tasks.SessionLocal")
    def test_structure_key_found_by_key(self, mock_session_cls):
        db = _mock_db()
        mock_session_cls.return_value = db

        gen = MagicMock()
        gen.status = "pending"
        gen.task_id = "task-1"

        project = MagicMock()
        project.generation_config = {
            "prompt_structures": [
                {"key": "my_struct", "structure": {"system_prompt": "test"}},
            ],
            "selected_configuration": {"parameters": {}, "model_configs": {}},
        }
        project.label_config = None
        project.label_config_version = None

        task = MagicMock()
        task.id = "task-1"
        task.project_id = "p1"
        task.data = {"text": "hello"}
        task.meta = {}
        task.created_at = datetime.now()

        model = MagicMock()
        model.id = "gpt-4"
        model.name = "GPT-4"
        model.provider = "OpenAI"
        model.parameter_constraints = None

        ai_service = MagicMock()
        ai_service.is_available.return_value = True

        def mock_gen_response(**kwargs):
            return {"response_text": "answer", "prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10, "cost_usd": 0.001}

        ai_service.generate = mock_gen_response

        # No existing response
        existing_resp_query = MagicMock()
        existing_resp_query.first.return_value = None

        query_results = iter([gen, project, task, model])
        join_filter_mock = MagicMock()
        join_filter_mock.filter.return_value = existing_resp_query

        call_idx = [0]
        def query_side_effect(*args):
            mock_q = MagicMock()
            call_idx[0] += 1
            idx = call_idx[0]
            if idx <= 4:
                obj = next(query_results, None)
                mock_q.filter.return_value.first.return_value = obj
                mock_q.filter.return_value.filter.return_value.first.return_value = obj
            elif idx == 5:
                # existing response check (join query with order_by)
                mock_q.join.return_value.filter.return_value.order_by.return_value.first.return_value = None
            elif idx == 6:
                # existing attempts count
                mock_q.filter.return_value.count.return_value = 0
            else:
                # report query and notification queries
                mock_q.filter.return_value.first.return_value = None
                mock_q.filter.return_value.distinct.return_value.all.return_value = []
            return mock_q

        db.query.side_effect = query_side_effect

        mock_user_aware = MagicMock()
        mock_user_aware.get_ai_service_for_user.return_value = ai_service

        with patch.object(tasks_module, "user_aware_ai_service", mock_user_aware):
            with patch.object(tasks_module, "notify_task_completed", MagicMock()):
                result = generate_llm_responses(
                    generation_id="gen-1",
                    config_data={"project_id": "p1"},
                    model_id="gpt-4",
                    user_id="u1",
                    structure_key="my_struct",
                )

        assert result["status"] == "success"
        assert result["responses_generated"] >= 1


class TestGenerateLLMResponsesStructureKeyNotFound:
    """Test structure_key not found in list format raises error."""

    @patch("tasks.HAS_DATABASE", True)
    @patch("tasks.HAS_AI_SERVICES", True)
    @patch("tasks.SessionLocal")
    def test_structure_key_not_found_in_list(self, mock_session_cls):
        db = _mock_db()
        mock_session_cls.return_value = db

        gen = MagicMock()
        gen.status = "pending"
        gen.task_id = "task-1"

        project = MagicMock()
        project.generation_config = {
            "prompt_structures": [
                {"key": "other_struct", "structure": {}},
            ],
        }

        call_idx = [0]
        def query_side_effect(model_cls):
            mock_q = MagicMock()
            call_idx[0] += 1
            if call_idx[0] == 1:
                mock_q.filter.return_value.first.return_value = gen
            elif call_idx[0] == 2:
                mock_q.filter.return_value.first.return_value = project
            else:
                mock_q.filter.return_value.first.return_value = None
            return mock_q

        db.query.side_effect = query_side_effect

        result = generate_llm_responses(
            generation_id="gen-1",
            config_data={"project_id": "p1"},
            model_id="m1",
            user_id="u1",
            structure_key="nonexistent",
        )
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()


class TestGenerateLLMResponsesStructureKeyDictFormat:
    """Test structure_key lookup with legacy dict format."""

    @patch("tasks.HAS_DATABASE", True)
    @patch("tasks.HAS_AI_SERVICES", True)
    @patch("tasks.SessionLocal")
    def test_structure_key_not_found_in_dict(self, mock_session_cls):
        db = _mock_db()
        mock_session_cls.return_value = db

        gen = MagicMock()
        gen.status = "pending"
        gen.task_id = "task-1"

        project = MagicMock()
        project.generation_config = {
            "prompt_structures": {"other": {"system_prompt": "x"}},
        }

        call_idx = [0]
        def query_side_effect(model_cls):
            mock_q = MagicMock()
            call_idx[0] += 1
            if call_idx[0] == 1:
                mock_q.filter.return_value.first.return_value = gen
            elif call_idx[0] == 2:
                mock_q.filter.return_value.first.return_value = project
            else:
                mock_q.filter.return_value.first.return_value = None
            return mock_q

        db.query.side_effect = query_side_effect

        result = generate_llm_responses(
            generation_id="gen-1",
            config_data={"project_id": "p1"},
            model_id="m1",
            user_id="u1",
            structure_key="missing_key",
        )
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()


class TestGenerateLLMResponsesNoAIServices:
    @patch("tasks.HAS_DATABASE", True)
    @patch("tasks.HAS_AI_SERVICES", False)
    @patch("tasks.SessionLocal")
    def test_no_ai_services(self, mock_session_cls):
        db = _mock_db()
        mock_session_cls.return_value = db

        gen = MagicMock()
        gen.status = "pending"
        gen.task_id = "task-1"

        project = MagicMock()
        project.generation_config = None
        project.label_config = None

        task = MagicMock()
        task.id = "task-1"
        task.project_id = "p1"
        task.data = {"text": "hi"}
        task.meta = {}
        task.created_at = datetime.now()

        model = MagicMock()
        model.id = "gpt-4"
        model.provider = "OpenAI"

        call_idx = [0]
        def query_side_effect(model_cls):
            mock_q = MagicMock()
            call_idx[0] += 1
            if call_idx[0] == 1:
                mock_q.filter.return_value.first.return_value = gen
            elif call_idx[0] == 2:
                mock_q.filter.return_value.first.return_value = project
            elif call_idx[0] == 3:
                mock_q.filter.return_value.first.return_value = task
                mock_q.filter.return_value.filter.return_value.first.return_value = task
            elif call_idx[0] == 4:
                mock_q.filter.return_value.first.return_value = model
            else:
                mock_q.filter.return_value.first.return_value = None
            return mock_q

        db.query.side_effect = query_side_effect

        result = generate_llm_responses(
            generation_id="gen-1",
            config_data={"project_id": "p1"},
            model_id="gpt-4",
            user_id="u1",
        )
        assert result["status"] == "error"
        assert "AI services" in result["message"]


class TestGenerateLLMResponsesAPIKeyError:
    @patch("tasks.HAS_DATABASE", True)
    @patch("tasks.HAS_AI_SERVICES", True)
    @patch("tasks.SessionLocal")
    def test_api_key_not_configured(self, mock_session_cls):
        db = _mock_db()
        mock_session_cls.return_value = db

        gen = MagicMock()
        gen.status = "pending"
        gen.task_id = "task-1"

        project = MagicMock()
        project.generation_config = None
        project.label_config = None

        task = MagicMock()
        task.id = "task-1"
        task.project_id = "p1"
        task.data = {}
        task.meta = {}
        task.created_at = datetime.now()

        model = MagicMock()
        model.id = "gpt-4"
        model.provider = "OpenAI"

        call_idx = [0]
        def query_side_effect(model_cls):
            mock_q = MagicMock()
            call_idx[0] += 1
            if call_idx[0] == 1:
                mock_q.filter.return_value.first.return_value = gen
            elif call_idx[0] == 2:
                mock_q.filter.return_value.first.return_value = project
            elif call_idx[0] == 3:
                mock_q.filter.return_value.first.return_value = task
                mock_q.filter.return_value.filter.return_value.first.return_value = task
            elif call_idx[0] == 4:
                mock_q.filter.return_value.first.return_value = model
            else:
                mock_q.filter.return_value.first.return_value = None
            return mock_q

        db.query.side_effect = query_side_effect

        mock_user_aware = MagicMock()
        mock_user_aware.get_ai_service_for_user.side_effect = Exception(
            "No API key configured for OpenAI"
        )

        with patch.object(tasks_module, "user_aware_ai_service", mock_user_aware):
            result = generate_llm_responses(
                generation_id="gen-1",
                config_data={"project_id": "p1"},
                model_id="gpt-4",
                user_id="u1",
            )
        assert result["status"] == "error"
        assert "API key" in result["message"]


class TestGenerateLLMResponsesZeroResponses:
    """When all response generation attempts fail, status should be failed."""

    @patch("tasks.HAS_DATABASE", True)
    @patch("tasks.HAS_AI_SERVICES", True)
    @patch("tasks.HAS_GENERATION_PARSER", False)
    @patch("tasks.SessionLocal")
    def test_zero_responses_returns_failed(self, mock_session_cls):
        async def failing_gen(**kwargs):
            raise Exception("LLM error")

        db, gen, project, task, model, ai_service = _setup_generate_llm_mocks(
            ai_response_fn=failing_gen,
        )
        mock_session_cls.return_value = db

        result = _run_generate_with_mocks(db, ai_service)

        assert result["status"] == "failed"
        assert result["responses_generated"] == 0


# ===========================================================================
# generate_response (bridge task)
# ===========================================================================


class TestGenerateResponseBridge:
    @patch("tasks.HAS_DATABASE", False)
    def test_no_database_returns_error(self):
        from tasks import generate_response
        result = generate_response(
            generation_id="gen-1",
            project_id="p1",
            task_id="t1",
            model_id="m1",
        )
        assert result["status"] == "error"
        assert "Database" in result["message"] or "database" in result["message"].lower()

    @patch("tasks.HAS_DATABASE", True)
    @patch("tasks.SessionLocal")
    def test_generation_not_found(self, mock_session_cls):
        db = _mock_db()
        mock_session_cls.return_value = db
        db.query.return_value.filter.return_value.first.return_value = None

        from tasks import generate_response
        result = generate_response(
            generation_id="missing",
            project_id="p1",
            task_id="t1",
            model_id="m1",
        )
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()


# ===========================================================================
# send_bulk_invitations_task - edge cases
# ===========================================================================


class TestBulkInvitationsEdgeCases:
    def test_empty_list(self):
        result = send_bulk_invitations_task([])
        assert result["sent"] == 0
        assert result["failed"] == 0
        assert result["total"] == 0
        assert result["results"] == []

    def test_all_fail(self):
        invitations = [
            {"invitation_id": "i1", "to_email": "a@b.com", "inviter_name": "X",
             "organization_name": "O", "invitation_url": "u", "role": "r"},
            {"invitation_id": "i2", "to_email": "c@d.com", "inviter_name": "X",
             "organization_name": "O", "invitation_url": "u", "role": "r"},
        ]

        with patch.object(
            send_invitation_email_task, 'apply_async',
            side_effect=Exception("Queue down")
        ):
            result = send_bulk_invitations_task(invitations)

        assert result["sent"] == 0
        assert result["failed"] == 2
        assert all(r["status"] == "failed" for r in result["results"])


# ===========================================================================
# run_evaluation - various branches
# ===========================================================================


class TestRunEvaluationNotFound:
    @patch("tasks.SessionLocal")
    def test_evaluation_not_found(self, mock_session_cls):
        db = _mock_db()
        mock_session_cls.return_value = db
        db.query.return_value.filter.return_value.first.return_value = None

        from tasks import run_evaluation
        result = run_evaluation(
            evaluation_id="eval-1",
            project_id="p1",
            evaluation_configs=[],
        )
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()


class TestRunEvaluationProjectNotFound:
    @patch("tasks.SessionLocal")
    def test_project_not_found(self, mock_session_cls):
        db = _mock_db()
        mock_session_cls.return_value = db

        evaluation = MagicMock()
        evaluation.status = "pending"
        evaluation.eval_metadata = {}

        call_idx = [0]
        def query_side_effect(model_cls):
            mock_q = MagicMock()
            call_idx[0] += 1
            if call_idx[0] == 1:
                mock_q.filter.return_value.first.return_value = evaluation
            else:
                mock_q.filter.return_value.first.return_value = None
            return mock_q

        db.query.side_effect = query_side_effect

        from tasks import run_evaluation
        result = run_evaluation(
            evaluation_id="eval-1",
            project_id="p1",
            evaluation_configs=[{"metric": "accuracy", "enabled": True}],
        )
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()


class TestRunEvaluationNoEnabledConfigs:
    @patch("tasks.SessionLocal")
    def test_no_enabled_configs(self, mock_session_cls):
        db = _mock_db()
        mock_session_cls.return_value = db

        evaluation = MagicMock()
        evaluation.status = "pending"
        evaluation.eval_metadata = {}

        project = MagicMock()

        call_idx = [0]
        def query_side_effect(model_cls):
            mock_q = MagicMock()
            call_idx[0] += 1
            if call_idx[0] == 1:
                mock_q.filter.return_value.first.return_value = evaluation
            elif call_idx[0] == 2:
                mock_q.filter.return_value.first.return_value = project
            return mock_q

        db.query.side_effect = query_side_effect

        from tasks import run_evaluation
        result = run_evaluation(
            evaluation_id="eval-1",
            project_id="p1",
            evaluation_configs=[{"metric": "accuracy", "enabled": False}],
        )
        assert result["status"] == "error"
        assert "No enabled" in result["message"]


class TestRunEvaluationNoTasks:
    @patch("tasks.SessionLocal")
    def test_no_tasks(self, mock_session_cls):
        db = _mock_db()
        mock_session_cls.return_value = db

        evaluation = MagicMock()
        evaluation.status = "pending"
        evaluation.eval_metadata = {}

        project = MagicMock()

        call_idx = [0]
        def query_side_effect(model_cls):
            mock_q = MagicMock()
            call_idx[0] += 1
            if call_idx[0] == 1:
                mock_q.filter.return_value.first.return_value = evaluation
            elif call_idx[0] == 2:
                mock_q.filter.return_value.first.return_value = project
            elif call_idx[0] == 3:
                # tasks query
                mock_q.filter.return_value.limit.return_value.all.return_value = []
            return mock_q

        db.query.side_effect = query_side_effect

        from tasks import run_evaluation
        result = run_evaluation(
            evaluation_id="eval-1",
            project_id="p1",
            evaluation_configs=[{"metric": "accuracy", "enabled": True, "prediction_fields": ["pred"], "reference_fields": ["ref"]}],
        )
        assert result["status"] == "error"
        assert "No tasks" in result["message"]


class TestRunEvaluationOuterException:
    """Test the outer except block that updates evaluation status to failed."""

    @patch("tasks.SessionLocal")
    def test_outer_exception_updates_status(self, mock_session_cls):
        # First call: inner db raises exception
        # Second call: outer recovery db updates status
        inner_db = _mock_db()
        inner_db.query.side_effect = RuntimeError("Unexpected crash")

        outer_db = _mock_db()
        eval_record = MagicMock()
        eval_record.eval_metadata = {"triggered_by": "u1"}
        outer_db.query.return_value.filter.return_value.first.return_value = eval_record

        call_count = [0]
        def session_factory():
            call_count[0] += 1
            if call_count[0] == 1:
                return inner_db
            return outer_db

        mock_session_cls.side_effect = session_factory

        from tasks import run_evaluation
        result = run_evaluation(
            evaluation_id="eval-1",
            project_id="p1",
            evaluation_configs=[{"metric": "bleu", "enabled": True}],
        )
        assert result["status"] == "error"
        assert eval_record.status == "failed"


# ===========================================================================
# run_single_sample_evaluation
# ===========================================================================


class TestRunSingleSampleEvaluation:
    def _call_task(self, eval_configs, annotation_results, task_data,
                   user_id="u1", organization_id=None):
        """Helper to call run_single_sample_evaluation with mocked DB."""
        db = _mock_db()

        # Make db.query(EvaluationRun).filter(...).first() return None initially,
        # then on re-query return the run we created
        eval_run_obj = MagicMock()
        eval_run_obj.eval_metadata = {"configs": eval_configs}
        eval_run_obj.metrics = {}
        eval_run_obj.status = "running"

        query_mock = MagicMock()
        query_mock.filter.return_value.first.return_value = eval_run_obj
        query_mock.filter.return_value.all.return_value = []

        db.query.return_value = query_mock

        with patch.object(tasks_module, "SessionLocal", MagicMock(return_value=db)):
            from tasks import run_single_sample_evaluation
            result = run_single_sample_evaluation.run(
                evaluation_record_id="eval-rec-1",
                project_id="p1",
                task_id="t1",
                annotation_id="a1",
                evaluation_configs=eval_configs,
                annotation_results=annotation_results,
                task_data=task_data,
                organization_id=organization_id,
                user_id=user_id,
            )
        return result, db

    def test_skips_when_no_prediction(self):
        """When prediction field is not in annotation_results, metric is skipped."""
        result, db = self._call_task(
            eval_configs=[{
                "metric": "bleu",
                "prediction_fields": ["missing_field"],
                "reference_fields": ["task.ref"],
            }],
            annotation_results={"other_field": "value"},
            task_data={"ref": "reference text"},
        )
        assert result["status"] == "completed"
        assert len(result["results"]) == 0

    def test_deterministic_metric_success(self):
        """Test that a deterministic metric (non-LLM) gets computed."""
        mock_evaluator = MagicMock()
        mock_evaluator._compute_metric.return_value = 0.85

        db = _mock_db()
        eval_run_obj = MagicMock()
        eval_run_obj.eval_metadata = {"configs": [{"metric": "bleu", "display_name": "BLEU"}]}
        eval_run_obj.metrics = {}
        eval_run_obj.status = "running"

        query_mock = MagicMock()
        query_mock.filter.return_value.first.return_value = eval_run_obj
        query_mock.filter.return_value.all.return_value = []
        db.query.return_value = query_mock

        with patch.object(tasks_module, "SessionLocal", MagicMock(return_value=db)):
            with patch("ml_evaluation.sample_evaluator.SampleEvaluator", return_value=mock_evaluator):
                from tasks import run_single_sample_evaluation
                result = run_single_sample_evaluation.run(
                    evaluation_record_id="eval-rec-2",
                    project_id="p1",
                    task_id="t1",
                    annotation_id="a1",
                    evaluation_configs=[{
                        "metric": "bleu",
                        "prediction_fields": ["answer"],
                        "reference_fields": ["task.ref"],
                        "metric_parameters": {},
                    }],
                    annotation_results={"answer": "my answer"},
                    task_data={"ref": "reference text"},
                    user_id="u1",
                )

        assert result["status"] == "completed"
        assert len(result["results"]) == 1
        assert result["results"][0]["status"] == "completed"
        assert result["results"][0]["score"] == 0.85

    def test_metric_exception_persists_error(self):
        """When metric computation raises, error record is persisted."""
        db = _mock_db()
        eval_run_obj = MagicMock()
        eval_run_obj.eval_metadata = {"configs": [{"metric": "bad_metric", "display_name": "Bad"}]}
        eval_run_obj.metrics = {}
        eval_run_obj.status = "running"

        query_mock = MagicMock()
        query_mock.filter.return_value.first.return_value = eval_run_obj
        query_mock.filter.return_value.all.return_value = []
        db.query.return_value = query_mock

        with patch.object(tasks_module, "SessionLocal", MagicMock(return_value=db)):
            with patch("ml_evaluation.sample_evaluator.SampleEvaluator", side_effect=Exception("No such metric")):
                from tasks import run_single_sample_evaluation
                result = run_single_sample_evaluation.run(
                    evaluation_record_id="eval-rec-err",
                    project_id="p1",
                    task_id="t1",
                    annotation_id="a1",
                    evaluation_configs=[{
                        "metric": "bad_metric",
                        "prediction_fields": ["answer"],
                        "reference_fields": ["task.ref"],
                        "metric_parameters": {},
                    }],
                    annotation_results={"answer": "my answer"},
                    task_data={"ref": "reference text"},
                    user_id="u1",
                )

        assert result["status"] == "completed"
        assert len(result["results"]) == 1
        assert result["results"][0]["status"] == "error"


# ===========================================================================
# _evaluate_llm_judge_single
# ===========================================================================


class TestEvaluateLLMJudgeSingle:
    def test_success(self):
        db = _mock_db()

        mock_judge = MagicMock()
        mock_judge.ai_service = MagicMock()
        mock_judge.evaluate_single.return_value = {"overall_score": 0.75, "details": {}}

        with patch("ml_evaluation.llm_judge_evaluator.create_llm_judge_for_user", return_value=mock_judge):
            with patch.object(tasks_module, "_get_provider_from_model", return_value="openai"):
                from tasks import _evaluate_llm_judge_single
                result = _evaluate_llm_judge_single(
                    db=db, record_id="r1", immediate_eval_id="i1",
                    project_id="p1", task_id="t1", annotation_id="a1",
                    user_id="u1", field_name="answer", metric_type="llm_judge_correctness",
                    prediction="pred", reference="ref",
                    metric_params={"judge_model": "gpt-4o"},
                    organization_id=None,
                )

        assert result["status"] == "completed"
        assert result["score"] == 0.75
        assert result["metric"] == "llm_judge_correctness"
        db.add.assert_called_once()
        db.commit.assert_called_once()

    def test_no_ai_service_raises(self):
        db = _mock_db()

        mock_judge = MagicMock()
        mock_judge.ai_service = None

        with patch("ml_evaluation.llm_judge_evaluator.create_llm_judge_for_user", return_value=mock_judge):
            with patch.object(tasks_module, "_get_provider_from_model", return_value="openai"):
                from tasks import _evaluate_llm_judge_single
                with pytest.raises(RuntimeError, match="No AI service"):
                    _evaluate_llm_judge_single(
                        db=db, record_id="r1", immediate_eval_id="i1",
                        project_id="p1", task_id="t1", annotation_id="a1",
                        user_id="u1", field_name="f", metric_type="llm_judge_x",
                        prediction="p", reference="r",
                        metric_params={}, organization_id=None,
                    )


# ===========================================================================
# _get_provider_from_model
# ===========================================================================


class TestGetProviderFromModel:
    def test_delegates_to_provider_capabilities(self):
        with patch("ai_services.provider_capabilities.get_provider_from_model", return_value="Anthropic") as mock_fn:
            from tasks import _get_provider_from_model
            result = _get_provider_from_model("claude-3-5-sonnet")
        assert result == "Anthropic"
        mock_fn.assert_called_once_with("claude-3-5-sonnet")


# ===========================================================================
# Temperature constraint logic (within generate_llm_responses)
# ===========================================================================


class TestTemperatureConstraints:
    """Test model parameter constraint application."""

    @patch("tasks.HAS_DATABASE", True)
    @patch("tasks.HAS_AI_SERVICES", True)
    @patch("tasks.HAS_GENERATION_PARSER", False)
    @patch("tasks.SessionLocal")
    def test_temperature_not_supported_uses_required_value(self, mock_session_cls):
        """When model says temperature not supported, use required_value."""
        db, gen, project, task, model, ai_service = _setup_generate_llm_mocks(
            generation_config={"selected_configuration": {"parameters": {"temperature": 0.7}, "model_configs": {}}},
            model_id="gpt-5",
            model_name="GPT-5",
            parameter_constraints={"temperature": {"supported": False, "required_value": 1.0}},
        )
        mock_session_cls.return_value = db

        result = _run_generate_with_mocks(db, ai_service, model_id="gpt-5")

        assert result["status"] == "success"


# ===========================================================================
# Content format response parsing
# ===========================================================================


class TestResponseFormatContentKey:
    """Test the elif 'content' branch in response parsing."""

    @patch("tasks.HAS_DATABASE", True)
    @patch("tasks.HAS_AI_SERVICES", True)
    @patch("tasks.HAS_GENERATION_PARSER", False)
    @patch("tasks.SessionLocal")
    def test_content_format_parsed(self, mock_session_cls):
        async def content_format_gen(**kwargs):
            return {"content": "openai answer", "usage": {"total_tokens": 5}, "temperature": 0.0}

        db, gen, project, task, model, ai_service = _setup_generate_llm_mocks(
            ai_response_fn=content_format_gen,
        )
        mock_session_cls.return_value = db

        result = _run_generate_with_mocks(db, ai_service)

        assert result["status"] == "success"
        assert result["responses_generated"] == 1


# ===========================================================================
# Digest tasks
# ===========================================================================


def _run_async(coro):
    """Run an async coroutine in a fresh event loop."""
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestProcessAllDigestsTask:
    @patch("tasks.HAS_DATABASE", False)
    def test_no_database(self):
        result = _run_async(tasks_module.process_all_digests_task.run())
        assert result["status"] == "error"
        assert "Database not available" in result["message"]

    @patch("tasks.HAS_DATABASE", True)
    @patch("tasks.SessionLocal")
    def test_success(self, mock_session_cls):
        db = _mock_db()
        mock_session_cls.return_value = db

        mock_digest = MagicMock()

        async def mock_process(db_session):
            return {"total_users": 5, "digests_sent": 3, "errors": 0}

        mock_digest.process_all_digests = mock_process

        with patch.object(tasks_module, "DigestService", mock_digest):
            result = _run_async(tasks_module.process_all_digests_task.run())

        assert result["status"] == "success"
        assert result["stats"]["digests_sent"] == 3
        db.close.assert_called_once()

    @patch("tasks.HAS_DATABASE", True)
    @patch("tasks.SessionLocal")
    def test_exception(self, mock_session_cls):
        db = _mock_db()
        mock_session_cls.return_value = db

        mock_digest = MagicMock()

        async def mock_process(db_session):
            raise Exception("Digest error")

        mock_digest.process_all_digests = mock_process

        with patch.object(tasks_module, "DigestService", mock_digest):
            result = _run_async(tasks_module.process_all_digests_task.run())

        assert result["status"] == "error"
        assert "Digest error" in result["message"]


class TestSendTestDigestTask:
    @patch("tasks.HAS_DATABASE", False)
    def test_no_database(self):
        result = _run_async(tasks_module.send_test_digest_task.run("user-1"))
        assert result["status"] == "error"

    @patch("tasks.HAS_DATABASE", True)
    @patch("tasks.SessionLocal")
    def test_user_not_found(self, mock_session_cls):
        db = _mock_db()
        mock_session_cls.return_value = db
        db.query.return_value.filter.return_value.first.return_value = None

        result = _run_async(tasks_module.send_test_digest_task.run("missing-user"))
        assert result["status"] == "error"
        assert "not found" in result["message"]

    @patch("tasks.HAS_DATABASE", True)
    @patch("tasks.SessionLocal")
    def test_digest_sent(self, mock_session_cls):
        db = _mock_db()
        mock_session_cls.return_value = db

        user = MagicMock()
        user.email = "test@example.com"
        db.query.return_value.filter.return_value.first.return_value = user

        async def mock_process(db_session, user_obj):
            return True

        mock_digest = MagicMock()
        mock_digest.process_digest_for_user = mock_process

        with patch.object(tasks_module, "DigestService", mock_digest):
            result = _run_async(tasks_module.send_test_digest_task.run("user-1"))

        assert result["status"] == "success"
        assert "test@example.com" in result["message"]

    @patch("tasks.HAS_DATABASE", True)
    @patch("tasks.SessionLocal")
    def test_digest_skipped(self, mock_session_cls):
        db = _mock_db()
        mock_session_cls.return_value = db

        user = MagicMock()
        user.email = "test@example.com"
        db.query.return_value.filter.return_value.first.return_value = user

        async def mock_process(db_session, user_obj):
            return False

        mock_digest = MagicMock()
        mock_digest.process_digest_for_user = mock_process

        with patch.object(tasks_module, "DigestService", mock_digest):
            result = _run_async(tasks_module.send_test_digest_task.run("user-1"))

        assert result["status"] == "skipped"

    @patch("tasks.HAS_DATABASE", True)
    @patch("tasks.SessionLocal")
    def test_digest_exception(self, mock_session_cls):
        db = _mock_db()
        mock_session_cls.return_value = db

        user = MagicMock()
        user.email = "test@example.com"
        db.query.return_value.filter.return_value.first.return_value = user

        async def mock_process(db_session, user_obj):
            raise Exception("SMTP error")

        mock_digest = MagicMock()
        mock_digest.process_digest_for_user = mock_process

        with patch.object(tasks_module, "DigestService", mock_digest):
            result = _run_async(tasks_module.send_test_digest_task.run("user-1"))

        assert result["status"] == "error"
        assert "SMTP error" in result["message"]


# ===========================================================================
# Model config temperature resolution
# ===========================================================================


class TestModelConfigTemperature:
    """Test nested generation_config temperature resolution."""

    @patch("tasks.HAS_DATABASE", True)
    @patch("tasks.HAS_AI_SERVICES", True)
    @patch("tasks.HAS_GENERATION_PARSER", False)
    @patch("tasks.SessionLocal")
    def test_nested_model_config_temperature(self, mock_session_cls):
        """Test temperature from model_config.generation_config.temperature (nested)."""
        async def temp_tracking_gen(**kwargs):
            return {"response_text": "ans", "prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost_usd": 0.0, "temperature": kwargs.get("temperature", 0)}

        db, gen, project, task, model, ai_service = _setup_generate_llm_mocks(
            ai_response_fn=temp_tracking_gen,
            generation_config={
                "selected_configuration": {
                    "parameters": {},
                    "model_configs": {
                        "gpt-4": {
                            "generation_config": {"temperature": 0.9, "max_tokens": 3000}
                        }
                    },
                }
            },
        )
        mock_session_cls.return_value = db

        result = _run_generate_with_mocks(db, ai_service)

        assert result["status"] == "success"


# ===========================================================================
# Force rerun and existing response skip
# ===========================================================================


class TestForceRerun:
    @patch("tasks.HAS_DATABASE", True)
    @patch("tasks.HAS_AI_SERVICES", True)
    @patch("tasks.HAS_GENERATION_PARSER", False)
    @patch("tasks.SessionLocal")
    def test_force_rerun_regenerates(self, mock_session_cls):
        """When force_rerun=True in config_data, skip existing response check."""
        db, gen, project, task, model, ai_service = _setup_generate_llm_mocks()
        mock_session_cls.return_value = db

        # force_rerun skips the existing-response join query (step 5), so step 5
        # becomes the existing attempts count instead. Override the query chain.
        call_idx = [0]
        def query_side_effect(*args):
            mock_q = MagicMock()
            call_idx[0] += 1
            if call_idx[0] == 1:
                mock_q.filter.return_value.first.return_value = gen
            elif call_idx[0] == 2:
                mock_q.filter.return_value.first.return_value = project
            elif call_idx[0] == 3:
                mock_q.filter.return_value.first.return_value = task
                mock_q.filter.return_value.filter.return_value.first.return_value = task
            elif call_idx[0] == 4:
                mock_q.filter.return_value.first.return_value = model
            elif call_idx[0] == 5:
                # force_rerun skips join check; this is the attempts count
                mock_q.filter.return_value.count.return_value = 0
            else:
                mock_q.filter.return_value.first.return_value = None
                mock_q.filter.return_value.distinct.return_value.all.return_value = []
            return mock_q

        db.query.side_effect = query_side_effect

        result = _run_generate_with_mocks(
            db, ai_service,
            config_data={"project_id": "p1", "force_rerun": True},
        )

        assert result["status"] == "success"
        assert result["responses_generated"] == 1


# ===========================================================================
# Rate limit delay override
# ===========================================================================


class TestRateLimitOverride:
    @patch("tasks.HAS_DATABASE", True)
    @patch("tasks.HAS_AI_SERVICES", True)
    @patch("tasks.HAS_GENERATION_PARSER", False)
    @patch("tasks.SessionLocal")
    def test_rate_limit_delay_from_config(self, mock_session_cls):
        """Test rate_limit_delay override from config_data."""
        db, gen, project, task, model, ai_service = _setup_generate_llm_mocks()
        mock_session_cls.return_value = db

        result = _run_generate_with_mocks(
            db, ai_service,
            config_data={"project_id": "p1", "rate_limit_delay": 0.1},
        )

        assert result["status"] == "success"


# ===========================================================================
# Unexpected response format
# ===========================================================================


class TestUnexpectedResponseFormat:
    @patch("tasks.HAS_DATABASE", True)
    @patch("tasks.HAS_AI_SERVICES", True)
    @patch("tasks.HAS_GENERATION_PARSER", False)
    @patch("tasks.SessionLocal")
    def test_unexpected_format_fails_gracefully(self, mock_session_cls):
        """When response has neither response_text nor content, generation fails."""
        async def weird_format_gen(**kwargs):
            return {"weird_key": "value"}

        db, gen, project, task, model, ai_service = _setup_generate_llm_mocks(
            ai_response_fn=weird_format_gen,
        )
        mock_session_cls.return_value = db

        result = _run_generate_with_mocks(db, ai_service)

        # Should fail but not crash
        assert result["status"] == "failed"
        assert result["responses_generated"] == 0


# ===========================================================================
# Label config fields with structured output
# ===========================================================================


class TestLabelConfigStructuredOutput:
    """Test extract_label_config_fields with complex configs."""

    def test_nested_view_elements(self):
        config = """<View>
            <View>
                <TextArea name="inner_field" toName="text"/>
            </View>
            <Choices name="outer_choice" toName="text">
                <Choice value="A"/>
            </Choices>
        </View>"""
        fields = extract_label_config_fields(config)
        assert "inner_field" in fields
        assert "outer_choice" in fields

    def test_empty_string(self):
        fields = extract_label_config_fields("")
        assert fields == []
