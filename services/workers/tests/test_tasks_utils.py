"""Tests for utility functions and task entry points in tasks.py.

Covers:
- extract_label_config_fields (pure function)
- generate_classification_samples (pure function)
- get_supported_metrics task
- generate_synthetic_data task
- cleanup_project_data task (with mocked Redis)
- generate_response / generate_llm_responses error paths
"""

import json
import os
import sys
from unittest.mock import MagicMock, Mock, patch

import pytest

# Ensure workers dir is importable
workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

from tasks import extract_label_config_fields, generate_classification_samples


# ---------------------------------------------------------------------------
# extract_label_config_fields
# ---------------------------------------------------------------------------

class TestExtractLabelConfigFields:
    """Test the pure XML parsing utility."""

    def test_choices_field(self):
        config = """
        <View>
            <Text name="text" value="$text"/>
            <Choices name="sentiment" toName="text">
                <Choice value="positive"/>
                <Choice value="negative"/>
            </Choices>
        </View>
        """
        fields = extract_label_config_fields(config)
        assert "sentiment" in fields

    def test_textarea_field(self):
        config = """
        <View>
            <Text name="text" value="$text"/>
            <TextArea name="answer" toName="text"/>
        </View>
        """
        fields = extract_label_config_fields(config)
        assert "answer" in fields

    def test_rating_field(self):
        config = """
        <View>
            <Text name="text" value="$text"/>
            <Rating name="confidence" toName="text"/>
        </View>
        """
        fields = extract_label_config_fields(config)
        assert "confidence" in fields

    def test_number_field(self):
        config = """
        <View>
            <Text name="text" value="$text"/>
            <Number name="score" toName="text"/>
        </View>
        """
        fields = extract_label_config_fields(config)
        assert "score" in fields

    def test_text_display_excluded(self):
        """Text elements are display-only and should not appear in output fields."""
        config = """
        <View>
            <Text name="text" value="$text"/>
            <TextArea name="answer" toName="text"/>
        </View>
        """
        fields = extract_label_config_fields(config)
        assert "text" not in fields

    def test_header_excluded(self):
        config = """
        <View>
            <Header value="Instructions"/>
            <TextArea name="answer" toName="text"/>
        </View>
        """
        fields = extract_label_config_fields(config)
        assert len(fields) == 1
        assert "answer" in fields

    def test_multiple_fields(self):
        config = """
        <View>
            <Text name="text" value="$text"/>
            <Choices name="sentiment" toName="text">
                <Choice value="pos"/>
            </Choices>
            <TextArea name="reasoning" toName="text"/>
            <Rating name="confidence" toName="text"/>
            <Number name="score" toName="text"/>
        </View>
        """
        fields = extract_label_config_fields(config)
        assert set(fields) == {"sentiment", "reasoning", "confidence", "score"}

    def test_invalid_xml(self):
        fields = extract_label_config_fields("<not valid xml")
        assert fields == []

    def test_empty_config(self):
        fields = extract_label_config_fields("<View></View>")
        assert fields == []

    def test_no_name_attribute(self):
        config = """
        <View>
            <TextArea toName="text"/>
        </View>
        """
        fields = extract_label_config_fields(config)
        assert fields == []


# ---------------------------------------------------------------------------
# generate_classification_samples
# ---------------------------------------------------------------------------

class TestGenerateClassificationSamples:
    """Test the sample generation utility."""

    def test_default_count(self):
        samples = generate_classification_samples()
        assert len(samples) == 100

    def test_custom_count(self):
        samples = generate_classification_samples(num_samples=5)
        assert len(samples) == 5

    def test_sample_structure(self):
        samples = generate_classification_samples(num_samples=1)
        sample = samples[0]
        assert "id" in sample
        assert "text" in sample
        assert "category" in sample
        assert "confidence" in sample

    def test_categories_valid(self):
        valid = {"contract", "agreement", "legal_opinion", "judgment", "statute"}
        samples = generate_classification_samples(num_samples=50)
        for s in samples:
            assert s["category"] in valid

    def test_confidence_range(self):
        samples = generate_classification_samples(num_samples=50)
        for s in samples:
            assert 0.6 <= s["confidence"] <= 0.95

    def test_ids_sequential(self):
        samples = generate_classification_samples(num_samples=5)
        assert [s["id"] for s in samples] == [0, 1, 2, 3, 4]

    def test_zero_samples(self):
        samples = generate_classification_samples(num_samples=0)
        assert samples == []


# ---------------------------------------------------------------------------
# get_supported_metrics (Celery task)
# ---------------------------------------------------------------------------

class TestGetSupportedMetrics:

    def test_specific_task_type(self):
        from tasks import get_supported_metrics

        result = get_supported_metrics("qa")
        assert result["status"] == "success"
        assert result["task_type"] == "qa"
        assert isinstance(result["metrics"], list)

    def test_all_task_types(self):
        from tasks import get_supported_metrics

        result = get_supported_metrics()
        assert result["status"] == "success"
        assert "supported_task_types" in result
        assert "metrics_by_task_type" in result


# ---------------------------------------------------------------------------
# generate_synthetic_data (Celery task)
# ---------------------------------------------------------------------------

class TestGenerateSyntheticData:

    def test_default_samples(self):
        from tasks import generate_synthetic_data

        result = generate_synthetic_data("task-123")
        assert result["status"] == "success"
        assert result["task_id"] == "task-123"
        assert result["generated_count"] == 10
        assert len(result["data"]) == 10

    def test_custom_count(self):
        from tasks import generate_synthetic_data

        result = generate_synthetic_data("task-456", num_samples=3)
        assert result["generated_count"] == 3
        assert len(result["data"]) == 3

    def test_sample_labels(self):
        from tasks import generate_synthetic_data

        result = generate_synthetic_data("t", num_samples=4)
        labels = [d["label"] for d in result["data"]]
        for label in labels:
            assert label in ("contract", "agreement")


# ---------------------------------------------------------------------------
# cleanup_project_data (with mocked Redis)
# ---------------------------------------------------------------------------

class TestCleanupProjectData:

    @patch("tasks.redis")
    def test_successful_cleanup(self, mock_redis_module):
        mock_r = MagicMock()
        mock_r.delete.return_value = 1
        mock_redis_module.from_url.return_value = mock_r

        from tasks import cleanup_project_data

        result = cleanup_project_data("proj-123")
        assert result["status"] == "success"
        assert result["project_id"] == "proj-123"
        assert result["deleted_keys"] >= 0

    @patch("tasks.redis")
    def test_redis_error(self, mock_redis_module):
        mock_redis_module.from_url.side_effect = Exception("Connection refused")

        from tasks import cleanup_project_data

        result = cleanup_project_data("proj-123")
        assert result["status"] == "error"
        assert "proj-123" in result["project_id"]

    @patch("tasks.redis")
    def test_cleanup_deletes_both_key_formats(self, mock_redis_module):
        mock_r = MagicMock()
        mock_r.delete.return_value = 1
        mock_redis_module.from_url.return_value = mock_r

        from tasks import cleanup_project_data

        cleanup_project_data("my-project")
        # Should try to delete both project: and task: key formats
        calls = [c[0][0] for c in mock_r.delete.call_args_list]
        assert "project:my-project" in calls
        assert "task:my-project" in calls


# ---------------------------------------------------------------------------
# generate_llm_responses error paths
# ---------------------------------------------------------------------------

class TestGenerateLLMResponsesErrors:

    @patch("tasks.HAS_DATABASE", False)
    def test_no_database_returns_error(self):
        from tasks import generate_llm_responses

        result = generate_llm_responses(
            generation_id="gen-1",
            config_data={},
            model_id="gpt-4",
            user_id="u1",
        )
        assert result["status"] == "error"
        assert "Database not available" in result["message"] or "database" in result["message"].lower()

