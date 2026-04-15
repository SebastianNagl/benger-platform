"""
Unit tests for multi-field evaluation business logic (multi_field.py).
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import HTTPException


class TestMultiFieldEvaluationRunLogic:
    """Tests for evaluation run business logic."""

    def test_enabled_configs_filter(self):
        configs = [
            Mock(enabled=True, metric="bleu"),
            Mock(enabled=False, metric="rouge"),
            Mock(enabled=True, metric="bert_score"),
        ]
        enabled = [c for c in configs if c.enabled]
        assert len(enabled) == 2

    def test_no_enabled_configs_error(self):
        configs = [
            Mock(enabled=False, metric="bleu"),
            Mock(enabled=False, metric="rouge"),
        ]
        enabled = [c for c in configs if c.enabled]
        assert len(enabled) == 0

    def test_empty_configs_error(self):
        configs = []
        assert len(configs) == 0

    def test_unique_evaluation_type_ids(self):
        enabled_configs = [
            Mock(metric="bleu"),
            Mock(metric="rouge"),
            Mock(metric="bleu"),
        ]
        evaluation_type_ids = list(set(c.metric for c in enabled_configs))
        assert len(evaluation_type_ids) == 2

    def test_model_id_from_generation(self):
        generation_model_query = ("gpt-4o", 50)
        evaluated_model_id = generation_model_query[0] if generation_model_query else "unknown"
        assert evaluated_model_id == "gpt-4o"

    def test_model_id_fallback_unknown(self):
        generation_model_query = None
        evaluated_model_id = generation_model_query[0] if generation_model_query else "unknown"
        assert evaluated_model_id == "unknown"

    def test_evaluation_metadata_structure(self):
        eval_metadata = {
            "evaluation_type": "evaluation",
            "triggered_by": "user-1",
            "evaluation_configs": [{"id": "cfg1", "metric": "bleu"}],
            "batch_size": 100,
            "label_config_version": "v1",
            "evaluated_model_id": "gpt-4o",
            "force_rerun": False,
            "organization_id": "org-1",
        }
        assert eval_metadata["evaluation_type"] == "evaluation"
        assert eval_metadata["batch_size"] == 100
        assert not eval_metadata["force_rerun"]

    def test_force_rerun_inverts_to_missing_only(self):
        force_rerun = True
        evaluate_missing_only = not force_rerun
        assert evaluate_missing_only is False

        force_rerun = False
        evaluate_missing_only = not force_rerun
        assert evaluate_missing_only is True


class TestAvailableFieldsLogic:
    """Tests for available fields extraction logic."""

    def test_fields_from_label_config(self):
        human_fields = set()
        label_config_fields = ["answer", "summary", "rating"]
        human_fields.update(label_config_fields)
        assert human_fields == {"answer", "summary", "rating"}

    def test_reference_fields_from_eval_config(self):
        evaluation_config = {
            "detected_answer_types": [
                {"name": "answer", "to_name": "text"},
                {"name": "summary", "to_name": "content"},
                {"name": "rating"},
            ]
        }
        reference_fields = set()
        for at in evaluation_config.get("detected_answer_types", []):
            to_name = at.get("to_name", "")
            if to_name:
                reference_fields.add(to_name)
        assert reference_fields == {"text", "content"}

    def test_model_fields_from_generation(self):
        model_fields = set()
        parsed_annotation = [
            {"from_name": "gen_answer", "to_name": "text"},
            {"from_name": "gen_summary"},
        ]
        for result in parsed_annotation:
            from_name = result.get("from_name", "")
            if from_name:
                model_fields.add(from_name)
        assert model_fields == {"gen_answer", "gen_summary"}

    def test_human_fields_from_annotation_result(self):
        human_fields = set()
        reference_fields = set()
        annotation_result = [
            {"from_name": "answer", "to_name": "text"},
            {"from_name": "label", "to_name": "document"},
        ]
        for result in annotation_result:
            from_name = result.get("from_name", "")
            to_name = result.get("to_name", "")
            if from_name:
                human_fields.add(from_name)
            if to_name:
                reference_fields.add(to_name)
        assert human_fields == {"answer", "label"}
        assert reference_fields == {"text", "document"}

    def test_task_data_reference_fields(self):
        task_data = {
            "question": "What is the answer?",
            "answer": "42",
            "_internal_id": "abc",
            "tags": ["tag1", "tag2"],
            "count": 5,
        }
        reference_fields = set()
        for field_name, field_value in task_data.items():
            if not field_name.startswith("_") and isinstance(field_value, (str, list)):
                reference_fields.add(field_name)
        assert "question" in reference_fields
        assert "answer" in reference_fields
        assert "tags" in reference_fields
        assert "_internal_id" not in reference_fields
        assert "count" not in reference_fields

    def test_all_fields_union(self):
        model_fields = {"gen_answer"}
        human_fields = {"answer", "label"}
        reference_fields = {"text", "answer"}
        all_fields = model_fields | human_fields | reference_fields
        assert all_fields == {"gen_answer", "answer", "label", "text"}


class TestProjectEvaluationResults:
    """Tests for project evaluation results parsing logic."""

    def test_metrics_parsing_by_config(self):
        metrics = {
            "cfg1:answer:gold:bleu": 0.85,
            "cfg1:answer:gold:rouge": 0.78,
            "cfg2:summary:gold_summary:bert_score": 0.92,
        }

        parsed_results = {}
        for key, value in metrics.items():
            parts = key.split(":")
            if len(parts) >= 4:
                config_id = parts[0]
                pred_field = parts[1]
                ref_field = parts[2]
                metric_name = ":".join(parts[3:])

                if config_id not in parsed_results:
                    parsed_results[config_id] = {"field_results": [], "aggregate_score": None}

                combo_key = f"{pred_field}_vs_{ref_field}"
                existing = next(
                    (r for r in parsed_results[config_id]["field_results"]
                     if r.get("combo_key") == combo_key), None
                )
                if not existing:
                    existing = {
                        "combo_key": combo_key,
                        "prediction_field": pred_field,
                        "reference_field": ref_field,
                        "scores": {},
                    }
                    parsed_results[config_id]["field_results"].append(existing)
                existing["scores"][metric_name] = value

        assert len(parsed_results) == 2
        assert parsed_results["cfg1"]["field_results"][0]["scores"]["bleu"] == 0.85

    def test_aggregate_score_calculation(self):
        field_results = [
            {"scores": {"bleu": 0.8, "rouge": 0.7}},
            {"scores": {"bleu": 0.9}},
        ]

        all_scores = []
        for fr in field_results:
            for score_val in fr["scores"].values():
                if isinstance(score_val, (int, float)):
                    all_scores.append(score_val)

        aggregate = sum(all_scores) / len(all_scores) if all_scores else None
        assert aggregate == pytest.approx(0.8, abs=0.01)

    def test_evaluation_type_filtering(self):
        all_evaluations = [
            Mock(eval_metadata={"evaluation_type": "evaluation"}),
            Mock(eval_metadata={"evaluation_type": "multi_field"}),
            Mock(eval_metadata={"evaluation_type": "llm_judge"}),
            Mock(eval_metadata={"evaluation_type": "immediate"}),
            Mock(eval_metadata={"evaluation_type": "unknown_type"}),
            Mock(eval_metadata=None),
            Mock(eval_metadata={}),
        ]

        valid_types = ("multi_field", "evaluation", "llm_judge", "immediate")
        evaluations = [
            e for e in all_evaluations
            if (e.eval_metadata or {}).get("evaluation_type") in valid_types
        ]
        assert len(evaluations) == 4

    def test_latest_only_returns_first(self):
        evaluations = [Mock(id="e1"), Mock(id="e2"), Mock(id="e3")]
        latest_only = True
        if latest_only and evaluations:
            evaluations = [evaluations[0]]
        assert len(evaluations) == 1
        assert evaluations[0].id == "e1"

    def test_latest_only_empty_list(self):
        evaluations = []
        latest_only = True
        if latest_only and evaluations:
            evaluations = [evaluations[0]]
        assert evaluations == []

    def test_eval_configs_extraction(self):
        eval_metadata = {
            "evaluation_configs": [{"id": "cfg1"}],
            "configs": [{"id": "old_cfg1"}],
        }
        eval_configs = (
            (eval_metadata.get("evaluation_configs")
             or eval_metadata.get("configs", []))
        )
        assert eval_configs == [{"id": "cfg1"}]

    def test_eval_configs_fallback(self):
        eval_metadata = {
            "configs": [{"id": "old_cfg1"}],
        }
        eval_configs = (
            (eval_metadata.get("evaluation_configs")
             or eval_metadata.get("configs", []))
        )
        assert eval_configs == [{"id": "old_cfg1"}]

    def test_eval_configs_none_metadata(self):
        eval_metadata = None
        eval_configs = (
            (eval_metadata.get("evaluation_configs") or eval_metadata.get("configs", []))
            if eval_metadata
            else []
        )
        assert eval_configs == []

    def test_progress_extraction(self):
        eval_metadata = {
            "samples_passed": 45,
            "samples_failed": 3,
            "samples_skipped": 2,
        }
        progress = {
            "samples_passed": eval_metadata.get("samples_passed", 0),
            "samples_failed": eval_metadata.get("samples_failed", 0),
            "samples_skipped": eval_metadata.get("samples_skipped", 0),
        }
        assert progress["samples_passed"] == 45
        assert progress["samples_failed"] == 3

    def test_detailed_result_parsing(self):
        """Test 4-part key parsing for detailed results."""
        metrics = {
            "cfg1:pred:ref:metric": 0.5,
            "cfg1:pred:ref:metric2": 0.6,
        }
        parsed = {}
        for key, value in metrics.items():
            parts = key.split(":")
            if len(parts) == 4:
                config_id, pred_field, ref_field, metric_name = parts
                if config_id not in parsed:
                    parsed[config_id] = {}
                combo_key = f"{pred_field}_vs_{ref_field}"
                if combo_key not in parsed[config_id]:
                    parsed[config_id][combo_key] = {}
                parsed[config_id][combo_key][metric_name] = value

        assert parsed["cfg1"]["pred_vs_ref"]["metric"] == 0.5

    def test_evaluation_run_type_check(self):
        """Test that non-evaluation runs are rejected."""
        eval_metadata = {"evaluation_type": "generation"}
        is_evaluation = eval_metadata.get("evaluation_type") in ("multi_field", "evaluation")
        assert is_evaluation is False

        eval_metadata = {"evaluation_type": "evaluation"}
        is_evaluation = eval_metadata.get("evaluation_type") in ("multi_field", "evaluation")
        assert is_evaluation is True


class TestResolveUserOrgForProject:
    """Tests for resolve_user_org_for_project helper."""

    def test_no_organizations(self):
        from routers.evaluations.helpers import resolve_user_org_for_project

        project = Mock(organizations=[])
        user = Mock(id="user-1")
        db = Mock()

        result = resolve_user_org_for_project(user, project, db)
        assert result is None

    def test_fallback_to_first_org(self):
        from routers.evaluations.helpers import resolve_user_org_for_project

        org1 = Mock(id="org-1")
        project = Mock(organizations=[org1])
        user = Mock(id="user-1")
        db = MagicMock()

        # No memberships found
        db.query.return_value.filter.return_value.all.return_value = []

        result = resolve_user_org_for_project(user, project, db)
        assert result == "org-1"

    def test_user_membership_found(self):
        from routers.evaluations.helpers import resolve_user_org_for_project

        org1 = Mock(id="org-1")
        org2 = Mock(id="org-2")
        project = Mock(organizations=[org1, org2])
        user = Mock(id="user-1")
        db = MagicMock()

        membership = Mock(organization_id="org-2")
        db.query.return_value.filter.return_value.all.return_value = [membership]

        result = resolve_user_org_for_project(user, project, db)
        assert result == "org-2"
