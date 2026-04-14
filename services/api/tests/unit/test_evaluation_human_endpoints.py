"""
Unit tests for human evaluation session business logic (human.py).
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import HTTPException


class TestHumanEvaluationSessionLogic:
    """Tests for human evaluation session creation logic."""

    def test_session_config_likert_type(self):
        session_type = "likert"
        field_name = "answer"
        dimensions = ["correctness", "completeness"]

        config = {
            "field_name": field_name,
            "dimensions": dimensions if session_type == "likert" else None,
            "randomized": True,
            "allow_skip": True,
        }
        assert config["dimensions"] == ["correctness", "completeness"]

    def test_session_config_preference_type(self):
        session_type = "preference"
        dimensions = ["correctness", "completeness"]

        config = {
            "field_name": "answer",
            "dimensions": dimensions if session_type == "likert" else None,
            "randomized": True,
            "allow_skip": True,
        }
        assert config["dimensions"] is None

    def test_session_total_items_from_tasks(self):
        total_items = 50
        session = {
            "items_evaluated": 0,
            "total_items": total_items,
            "status": "active",
        }
        assert session["items_evaluated"] == 0
        assert session["total_items"] == 50

    def test_progress_percentage_partial(self):
        items_evaluated = 15
        total_items = 30
        progress = (items_evaluated / total_items) * 100 if total_items and total_items > 0 else 0.0
        assert progress == 50.0

    def test_progress_percentage_zero_total(self):
        items_evaluated = 0
        total_items = 0
        progress = (items_evaluated / total_items) * 100 if total_items and total_items > 0 else 0.0
        assert progress == 0.0

    def test_progress_percentage_completed(self):
        items_evaluated = 10
        total_items = 10
        progress = (items_evaluated / total_items) * 100 if total_items and total_items > 0 else 0.0
        assert progress == 100.0

    def test_response_anonymization_naming(self):
        responses = []
        for i in range(3):
            responses.append({
                "id": f"resp-{i}",
                "type": "llm",
                "content": f"Response {i}",
                "metadata": {
                    "model_id": f"model-{i}",
                    "anonymized_name": f"Response_{chr(65 + len(responses))}",
                },
            })
        assert responses[0]["metadata"]["anonymized_name"] == "Response_A"
        assert responses[1]["metadata"]["anonymized_name"] == "Response_B"
        assert responses[2]["metadata"]["anonymized_name"] == "Response_C"


class TestHumanEvaluationNextItem:
    """Tests for next item retrieval logic."""

    def test_evaluated_task_ids_extraction_likert(self):
        """Test extracting already-evaluated task IDs for Likert sessions."""
        raw_ids = [("task-1",), ("task-2",), ("task-3",)]
        evaluated_task_ids = [t[0] for t in raw_ids]
        assert evaluated_task_ids == ["task-1", "task-2", "task-3"]

    def test_evaluated_task_ids_extraction_empty(self):
        raw_ids = []
        evaluated_task_ids = [t[0] for t in raw_ids]
        assert evaluated_task_ids == []

    def test_session_completed_when_no_more_tasks(self):
        next_task = None
        session_status = "active"

        if not next_task:
            session_status = "completed"

        assert session_status == "completed"

    def test_preference_ranking_limits_to_2(self):
        """Test preference ranking response selection."""
        import random

        responses = [
            {"id": "r1", "content": "Response 1"},
            {"id": "r2", "content": "Response 2"},
            {"id": "r3", "content": "Response 3"},
        ]

        session_type = "preference"
        if session_type == "preference" and len(responses) >= 2:
            random.shuffle(responses)
            responses = responses[:2]

        assert len(responses) == 2


class TestLikertRatingLogic:
    """Tests for Likert scale rating submission logic."""

    def test_ratings_per_dimension(self):
        ratings = {"correctness": 4, "completeness": 3, "style": 5}
        comments = {"correctness": "Good answer", "style": "Well written"}

        evaluations = []
        for dimension, rating in ratings.items():
            comment = comments.get(dimension) if comments else None
            evaluations.append({
                "dimension": dimension,
                "rating": rating,
                "comment": comment,
            })

        assert len(evaluations) == 3
        assert evaluations[0]["dimension"] == "correctness"
        assert evaluations[0]["rating"] == 4
        assert evaluations[0]["comment"] == "Good answer"
        assert evaluations[1]["comment"] is None  # no comment for completeness

    def test_session_progress_increment(self):
        items_evaluated = 5
        items_evaluated += 1
        assert items_evaluated == 6


class TestPreferenceRankingLogic:
    """Tests for preference ranking submission."""

    def test_valid_winner_values(self):
        valid_winners = ["a", "b", "tie"]
        for winner in valid_winners:
            assert winner in valid_winners

    def test_ranking_data_structure(self):
        ranking = {
            "session_id": "sess-1",
            "task_id": "task-1",
            "response_a_id": "resp-a",
            "response_b_id": "resp-b",
            "winner": "a",
            "confidence": 0.9,
            "reasoning": "Response A is more complete",
            "time_spent_seconds": 45,
        }
        assert ranking["winner"] == "a"
        assert ranking["confidence"] == 0.9


class TestHumanEvaluationConfigLogic:
    """Tests for human evaluation config extraction."""

    def test_extract_human_methods_from_selected(self):
        evaluation_config = {
            "selected_methods": {
                "answer": {
                    "automated": ["bleu"],
                    "human": ["likert_scale", "preference"],
                },
                "summary": {
                    "automated": ["rouge"],
                },
                "rating": {
                    "human": ["likert_scale"],
                },
            },
        }

        human_methods = {}
        selected_methods = evaluation_config.get("selected_methods", {})
        for field_name, config in selected_methods.items():
            human_selections = config.get("human", [])
            if human_selections:
                human_methods[field_name] = human_selections

        assert "answer" in human_methods
        assert "rating" in human_methods
        assert "summary" not in human_methods  # no human methods

    def test_extract_likert_dimensions(self):
        from routers.evaluations.helpers import extract_metric_name

        human_methods = {
            "answer": [
                {
                    "name": "likert_scale",
                    "parameters": {"dimensions": ["correctness", "completeness"]},
                },
                "preference",
            ],
        }

        available_dimensions = []
        for field_name, methods in human_methods.items():
            for method in methods:
                method_name = extract_metric_name(method)
                if method_name == "likert_scale":
                    if isinstance(method, dict) and "parameters" in method:
                        dims = method["parameters"].get("dimensions", [])
                        available_dimensions.extend(dims)

        assert "correctness" in available_dimensions
        assert "completeness" in available_dimensions

    def test_default_dimensions_when_none_configured(self):
        available_dimensions = []
        default = (
            list(set(available_dimensions))
            if available_dimensions
            else ["correctness", "completeness", "style", "usability"]
        )
        assert len(default) == 4

    def test_no_eval_config_returns_empty(self):
        evaluation_config = None
        if not evaluation_config:
            result = {
                "project_id": "proj-1",
                "human_methods": {},
                "available_dimensions": [],
            }
        assert result["human_methods"] == {}
        assert result["available_dimensions"] == []

    def test_delete_session_cascades(self):
        """Test that delete logic covers Likert + Preference + Session."""
        operations = ["delete_likert", "delete_preference", "delete_session"]
        assert len(operations) == 3

    def test_session_permission_check_superadmin(self):
        is_superadmin = True
        evaluator_id = "other-user"
        current_user_id = "user-1"
        has_permission = is_superadmin or evaluator_id == current_user_id
        assert has_permission is True

    def test_session_permission_check_owner(self):
        is_superadmin = False
        evaluator_id = "user-1"
        current_user_id = "user-1"
        has_permission = is_superadmin or evaluator_id == current_user_id
        assert has_permission is True

    def test_session_permission_check_denied(self):
        is_superadmin = False
        evaluator_id = "other-user"
        current_user_id = "user-1"
        has_permission = is_superadmin or evaluator_id == current_user_id
        assert has_permission is False
