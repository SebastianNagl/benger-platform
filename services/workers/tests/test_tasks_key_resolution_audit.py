"""Tests for issue #82: the worker must log the actual key-resolution
route returned by `user_aware_ai_service.get_ai_service_for_user`, and
must persist that route (plus invocation context) into every
`llm_responses.response_metadata` row regardless of provider.

The fix is in ``services/workers/tasks.py`` — the log line near the
service-creation block and the two ``metadata = {...}`` dicts in the
``response_text`` and ``content`` branches.
"""

import json
import logging
import os
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

import tasks as tasks_module
from tasks import generate_llm_responses


def _build_ai_service(
    key_resolution_route: str,
    invocation_user_id: str,
    invocation_organization_id: str | None,
    provider_name: str = "openai",
):
    """Build a stubbed AI service stamped with the four Phase 6.5 audit
    attributes that ``get_ai_service_for_user`` sets on its return value.
    """
    ai_service = MagicMock()
    ai_service.is_available.return_value = True
    ai_service._key_resolution_route = key_resolution_route
    ai_service._provider_name = provider_name
    ai_service._invocation_user_id = invocation_user_id
    ai_service._invocation_organization_id = invocation_organization_id

    def _generate(**kwargs):
        return {
            "response_text": "answer",
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "total_tokens": 2,
            "cost_usd": 0.0,
        }

    ai_service.generate = _generate
    return ai_service


def _build_db_query_side_effect(gen, project, task, model):
    """Match the 6-step DB-lookup sequence in ``generate_llm_responses``:
    1) Generation, 2) Project, 3) Task, 4) Model, 5) existing-response
    join query, 6) existing-attempts count. Anything beyond returns None
    (report + notification lookups).
    """
    call_idx = [0]

    def query_side_effect(*args):
        mock_q = MagicMock()
        call_idx[0] += 1
        idx = call_idx[0]
        if idx == 1:
            mock_q.filter.return_value.first.return_value = gen
        elif idx == 2:
            mock_q.filter.return_value.first.return_value = project
        elif idx == 3:
            mock_q.filter.return_value.first.return_value = task
            mock_q.filter.return_value.filter.return_value.first.return_value = task
        elif idx == 4:
            mock_q.filter.return_value.first.return_value = model
        elif idx == 5:
            mock_q.join.return_value.filter.return_value.order_by.return_value.first.return_value = None
        elif idx == 6:
            mock_q.filter.return_value.count.return_value = 0
        else:
            mock_q.filter.return_value.first.return_value = None
            mock_q.filter.return_value.distinct.return_value.all.return_value = []
        return mock_q

    return query_side_effect


def _build_fixtures():
    gen = MagicMock()
    gen.status = "pending"
    gen.task_id = "task-1"
    gen.structure_key = None

    project = MagicMock()
    project.generation_config = {
        "prompt_structures": [
            {"key": "default", "structure": {"system_prompt": "be helpful"}},
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

    return gen, project, task, model


def _run(ai_service, *, organization_id, user_id="u1"):
    """Drive ``generate_llm_responses`` through one task/prompt iteration
    and return the LLMResponse instance the worker tried to persist.
    """
    db = MagicMock()
    gen, project, task, model = _build_fixtures()
    db.query.side_effect = _build_db_query_side_effect(gen, project, task, model)

    captured = []
    db.add.side_effect = lambda obj: captured.append(obj)

    mock_user_aware = MagicMock()
    mock_user_aware.get_ai_service_for_user.return_value = ai_service

    with patch.object(tasks_module, "HAS_DATABASE", True), \
         patch.object(tasks_module, "HAS_AI_SERVICES", True), \
         patch.object(tasks_module, "HAS_GENERATION_PARSER", False), \
         patch.object(tasks_module, "SessionLocal", MagicMock(return_value=db)), \
         patch.object(tasks_module, "user_aware_ai_service", mock_user_aware), \
         patch.object(tasks_module, "notify_task_completed", MagicMock()):
        result = generate_llm_responses(
            generation_id="gen-1",
            config_data={"project_id": "p1"},
            model_id="gpt-4",
            user_id=user_id,
            structure_key="default",
            organization_id=organization_id,
        )

    return result, mock_user_aware, captured


class TestKeyResolutionAuditTrail:
    """Issue #82: regardless of provider, the route returned by the
    user-aware service lands in ``response_metadata``."""

    def test_require_private_keys_true_persists_org_resolved_route(self, caplog):
        """When org context is honored but the resolver short-circuits
        to the user's key, the route is ``org_resolved`` and the
        ``invocation_organization_id`` survives into ``response_metadata``.
        This is the surprising path the issue calls out — the route
        names *the resolver context*, not which key actually billed.
        """
        org_id = "94e3b649-aaaa-bbbb-cccc-dddddddddddd"
        ai_service = _build_ai_service(
            key_resolution_route="org_resolved",
            invocation_user_id="u1",
            invocation_organization_id=org_id,
        )

        with caplog.at_level(logging.INFO, logger="tasks"):
            result, mock_user_aware, captured = _run(ai_service, organization_id=org_id)

        assert result["status"] == "success", result
        mock_user_aware.get_ai_service_for_user.assert_called_once()
        _, kwargs = mock_user_aware.get_ai_service_for_user.call_args
        assert kwargs["organization_id"] == org_id

        assert len(captured) == 1, "expected exactly one LLMResponse persisted"
        llm_response = captured[0]
        metadata = json.loads(llm_response.response_metadata)

        assert metadata["key_resolution_route"] == "org_resolved"
        assert metadata["provider_name"] == "openai"
        assert metadata["invocation_user_id"] == "u1"
        assert metadata["invocation_organization_id"] == org_id

        # Acceptance criterion #1: log line reflects the actual route,
        # not just whether organization_id was passed.
        log_text = "\n".join(r.getMessage() for r in caplog.records)
        assert "Using API key via org_resolved" in log_text
        assert "from org " not in log_text

    def test_no_org_context_persists_user_key_route(self, caplog):
        """No org context → route is ``user_key`` and
        ``invocation_organization_id`` is None in the metadata."""
        ai_service = _build_ai_service(
            key_resolution_route="user_key",
            invocation_user_id="u1",
            invocation_organization_id=None,
        )

        with caplog.at_level(logging.INFO, logger="tasks"):
            result, _, captured = _run(ai_service, organization_id=None)

        assert result["status"] == "success", result
        assert len(captured) == 1
        metadata = json.loads(captured[0].response_metadata)

        assert metadata["key_resolution_route"] == "user_key"
        assert metadata["invocation_organization_id"] is None
        assert metadata["invocation_user_id"] == "u1"

        log_text = "\n".join(r.getMessage() for r in caplog.records)
        assert "Using API key via user_key" in log_text
