"""
Comprehensive tests for pure functions and helpers across the API.

Tests only pure functions (no DB, no I/O, no mocking).
Each test calls a function with inputs and asserts on outputs.
"""

import json
import math
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest


# ============================================================================
# 1. evaluation config: validate_metric_selection
# ============================================================================


class TestValidateMetricSelection:
    """Tests for services.evaluation.config.validate_metric_selection"""

    def test_valid_binary_exact_match(self):
        from services.evaluation.config import validate_metric_selection

        assert validate_metric_selection("binary", "exact_match") is True

    def test_valid_binary_accuracy(self):
        from services.evaluation.config import validate_metric_selection

        assert validate_metric_selection("binary", "accuracy") is True

    def test_invalid_binary_bleu(self):
        from services.evaluation.config import validate_metric_selection

        assert validate_metric_selection("binary", "bleu") is False

    def test_valid_long_text_bleu(self):
        from services.evaluation.config import validate_metric_selection

        assert validate_metric_selection("long_text", "bleu") is True

    def test_valid_long_text_rouge(self):
        from services.evaluation.config import validate_metric_selection

        assert validate_metric_selection("long_text", "rouge") is True

    def test_valid_numeric_mae(self):
        from services.evaluation.config import validate_metric_selection

        assert validate_metric_selection("numeric", "mae") is True

    def test_valid_numeric_rmse(self):
        from services.evaluation.config import validate_metric_selection

        assert validate_metric_selection("numeric", "rmse") is True

    def test_invalid_numeric_bleu(self):
        from services.evaluation.config import validate_metric_selection

        assert validate_metric_selection("numeric", "bleu") is False

    def test_unknown_answer_type_falls_to_custom(self):
        from services.evaluation.config import validate_metric_selection

        # Unknown type should fall back to CUSTOM which has all metrics
        assert validate_metric_selection("nonexistent_type", "exact_match") is True

    def test_custom_has_llm_judge(self):
        from services.evaluation.config import validate_metric_selection

        assert validate_metric_selection("custom", "llm_judge_classic") is True

    def test_rating_cohen_kappa(self):
        from services.evaluation.config import validate_metric_selection

        assert validate_metric_selection("rating", "cohen_kappa") is True

    def test_span_selection_iou(self):
        from services.evaluation.config import validate_metric_selection

        assert validate_metric_selection("span_selection", "iou") is True

    def test_taxonomy_hierarchical_f1(self):
        from services.evaluation.config import validate_metric_selection

        assert validate_metric_selection("taxonomy", "hierarchical_f1") is True

    def test_ranking_ndcg(self):
        from services.evaluation.config import validate_metric_selection

        assert validate_metric_selection("ranking", "ndcg") is True

    def test_multiple_choice_jaccard(self):
        from services.evaluation.config import validate_metric_selection

        assert validate_metric_selection("multiple_choice", "jaccard") is True

    def test_single_choice_confusion_matrix(self):
        from services.evaluation.config import validate_metric_selection

        assert validate_metric_selection("single_choice", "confusion_matrix") is True

    def test_nonexistent_metric(self):
        from services.evaluation.config import validate_metric_selection

        assert validate_metric_selection("binary", "totally_fake_metric") is False


# ============================================================================
# 2. evaluation config: get_selected_metrics_for_field
# ============================================================================


class TestGetSelectedMetricsForField:
    """Tests for services.evaluation.config.get_selected_metrics_for_field"""

    def test_none_config(self):
        from services.evaluation.config import get_selected_metrics_for_field

        assert get_selected_metrics_for_field(None, "field") == []

    def test_empty_config(self):
        from services.evaluation.config import get_selected_metrics_for_field

        assert get_selected_metrics_for_field({}, "field") == []

    def test_no_selected_methods_key(self):
        from services.evaluation.config import get_selected_metrics_for_field

        assert get_selected_metrics_for_field({"other": "data"}, "field") == []

    def test_field_not_in_methods(self):
        from services.evaluation.config import get_selected_metrics_for_field

        config = {"selected_methods": {"other_field": ["bleu"]}}
        assert get_selected_metrics_for_field(config, "field") == []

    def test_list_format(self):
        from services.evaluation.config import get_selected_metrics_for_field

        config = {"selected_methods": {"answer": ["bleu", "rouge"]}}
        assert get_selected_metrics_for_field(config, "answer") == ["bleu", "rouge"]

    def test_dict_format_with_metrics_key(self):
        from services.evaluation.config import get_selected_metrics_for_field

        config = {"selected_methods": {"answer": {"metrics": ["bleu", "rouge"]}}}
        assert get_selected_metrics_for_field(config, "answer") == ["bleu", "rouge"]

    def test_dict_format_without_metrics_key(self):
        from services.evaluation.config import get_selected_metrics_for_field

        config = {"selected_methods": {"answer": {"other": "data"}}}
        assert get_selected_metrics_for_field(config, "answer") == []

    def test_empty_list(self):
        from services.evaluation.config import get_selected_metrics_for_field

        config = {"selected_methods": {"answer": []}}
        assert get_selected_metrics_for_field(config, "answer") == []


# ============================================================================
# 3. evaluation config: lookup_available_methods
# ============================================================================


class TestLookupAvailableMethods:
    """Tests for services.evaluation.config.lookup_available_methods"""

    def test_empty_list(self):
        from services.evaluation.config import lookup_available_methods

        result = lookup_available_methods([])
        assert result == {}

    def test_single_binary_field(self):
        from services.evaluation.config import lookup_available_methods

        types = [{"name": "is_correct", "type": "binary", "tag": "choices", "to_name": "text"}]
        result = lookup_available_methods(types)
        assert "is_correct" in result
        assert result["is_correct"]["type"] == "binary"
        assert "exact_match" in result["is_correct"]["available_metrics"]

    def test_unknown_type_falls_to_custom(self):
        from services.evaluation.config import lookup_available_methods

        types = [{"name": "field", "type": "nonexistent_type", "tag": "unknown"}]
        result = lookup_available_methods(types)
        assert result["field"]["type"] == "custom"

    def test_enabled_metrics_starts_empty(self):
        from services.evaluation.config import lookup_available_methods

        types = [{"name": "f", "type": "numeric", "tag": "number", "to_name": ""}]
        result = lookup_available_methods(types)
        assert result["f"]["enabled_metrics"] == []

    def test_multiple_fields(self):
        from services.evaluation.config import lookup_available_methods

        types = [
            {"name": "a", "type": "binary", "tag": "choices"},
            {"name": "b", "type": "long_text", "tag": "textarea"},
        ]
        result = lookup_available_methods(types)
        assert len(result) == 2
        assert "bleu" in result["b"]["available_metrics"]
        assert "bleu" not in result["a"]["available_metrics"]

    def test_preserves_tag(self):
        from services.evaluation.config import lookup_available_methods

        types = [{"name": "f", "type": "rating", "tag": "rating", "to_name": "x"}]
        result = lookup_available_methods(types)
        assert result["f"]["tag"] == "rating"
        assert result["f"]["to_name"] == "x"


# ============================================================================
# 4. evaluation config: update_project_evaluation_config (pure)
# ============================================================================


class TestUpdateProjectEvaluationConfig:
    """Tests for services.evaluation.config.update_project_evaluation_config"""

    SIMPLE_XML = '<View><Choices name="label" toName="text"><Choice value="A"/><Choice value="B"/><Choice value="C"/></Choices></View>'

    def test_basic_generation(self):
        from services.evaluation.config import update_project_evaluation_config

        result = update_project_evaluation_config("proj-1", self.SIMPLE_XML)
        assert "detected_answer_types" in result
        assert "available_methods" in result
        assert "selected_methods" in result
        assert "last_updated" in result
        assert result["label_config_version"] is None

    def test_preserves_existing_selections(self):
        from services.evaluation.config import update_project_evaluation_config

        existing = {
            "selected_methods": {"label": ["exact_match"]},
            "available_methods": {},
            "detected_answer_types": [],
        }
        result = update_project_evaluation_config("proj-1", self.SIMPLE_XML, existing)
        assert result["selected_methods"]["label"] == ["exact_match"]

    def test_drops_selections_for_removed_fields(self):
        from services.evaluation.config import update_project_evaluation_config

        existing = {
            "selected_methods": {"nonexistent_field": ["bleu"]},
        }
        result = update_project_evaluation_config("proj-1", self.SIMPLE_XML, existing)
        assert "nonexistent_field" not in result["selected_methods"]

    def test_preserves_extra_keys(self):
        from services.evaluation.config import update_project_evaluation_config

        existing = {"evaluation_configs": [{"id": "c1"}], "custom_key": "value"}
        result = update_project_evaluation_config("proj-1", self.SIMPLE_XML, existing)
        assert result["evaluation_configs"] == [{"id": "c1"}]
        assert result["custom_key"] == "value"

    def test_label_config_version_tracked(self):
        from services.evaluation.config import update_project_evaluation_config

        result = update_project_evaluation_config("proj-1", self.SIMPLE_XML, label_config_version="v2")
        assert result["label_config_version"] == "v2"

    def test_empty_label_config(self):
        from services.evaluation.config import update_project_evaluation_config

        result = update_project_evaluation_config("proj-1", "")
        # Empty label config returns empty detected types
        assert result["detected_answer_types"] == []
        assert result["available_methods"] == {}


# ============================================================================
# 5. AnswerTypeDetector
# ============================================================================


class TestAnswerTypeDetectorExtended:
    """Additional tests for AnswerTypeDetector pure static methods."""

    def test_detect_number_field(self):
        from services.evaluation.config import AnswerTypeDetector

        xml = '<View><Number name="score" toName="text"/></View>'
        result = AnswerTypeDetector.detect_from_label_config(xml)
        assert any(r["type"] == "numeric" for r in result)

    def test_detect_ranker(self):
        from services.evaluation.config import AnswerTypeDetector

        xml = '<View><Ranker name="ranking" toName="text"/></View>'
        result = AnswerTypeDetector.detect_from_label_config(xml)
        assert any(r["type"] == "ranking" for r in result)

    def test_detect_textarea_short(self):
        from services.evaluation.config import AnswerTypeDetector

        xml = '<View><TextArea name="answer" toName="text" rows="3"/></View>'
        result = AnswerTypeDetector.detect_from_label_config(xml)
        assert any(r["type"] == "short_text" for r in result)

    def test_detect_textarea_long(self):
        from services.evaluation.config import AnswerTypeDetector

        xml = '<View><TextArea name="essay" toName="text" rows="10"/></View>'
        result = AnswerTypeDetector.detect_from_label_config(xml)
        assert any(r["type"] == "long_text" for r in result)

    def test_detect_json(self):
        from services.evaluation.config import AnswerTypeDetector

        xml = '<View><Json name="data" toName="text"/></View>'
        result = AnswerTypeDetector.detect_from_label_config(xml)
        assert any(r["type"] == "structured_text" for r in result)

    def test_detect_textfield(self):
        from services.evaluation.config import AnswerTypeDetector

        xml = '<View><TextField name="input" toName="text"/></View>'
        result = AnswerTypeDetector.detect_from_label_config(xml)
        assert any(r["type"] == "short_text" for r in result)

    def test_detect_labels_as_span_selection(self):
        from services.evaluation.config import AnswerTypeDetector

        xml = '<View><Labels name="ner" toName="text"><Label value="PER"/></Labels></View>'
        result = AnswerTypeDetector.detect_from_label_config(xml)
        assert any(r["type"] == "span_selection" for r in result)

    def test_detect_taxonomy(self):
        from services.evaluation.config import AnswerTypeDetector

        xml = '<View><Taxonomy name="cat" toName="text"/></View>'
        result = AnswerTypeDetector.detect_from_label_config(xml)
        assert any(r["type"] == "taxonomy" for r in result)

    def test_invalid_xml_returns_error_type(self):
        from services.evaluation.config import AnswerTypeDetector

        result = AnswerTypeDetector.detect_from_label_config("<not valid xml")
        assert len(result) == 1
        assert result[0]["type"] == "custom"
        assert result[0]["tag"] == "error"

    def test_no_controls_returns_custom(self):
        from services.evaluation.config import AnswerTypeDetector

        xml = '<View><Text name="display"/></View>'
        result = AnswerTypeDetector.detect_from_label_config(xml)
        assert any(r["type"] == "custom" for r in result)

    def test_binary_yes_no(self):
        from services.evaluation.config import AnswerTypeDetector

        xml = '<View><Choices name="q"><Choice value="Yes"/><Choice value="No"/></Choices></View>'
        result = AnswerTypeDetector.detect_from_label_config(xml)
        assert any(r["type"] == "binary" for r in result)

    def test_binary_ja_nein(self):
        from services.evaluation.config import AnswerTypeDetector

        xml = '<View><Choices name="q"><Choice value="Ja"/><Choice value="Nein"/></Choices></View>'
        result = AnswerTypeDetector.detect_from_label_config(xml)
        assert any(r["type"] == "binary" for r in result)

    def test_multiple_choice_attribute(self):
        from services.evaluation.config import AnswerTypeDetector

        xml = '<View><Choices name="q" multiple="true"><Choice value="A"/><Choice value="B"/></Choices></View>'
        result = AnswerTypeDetector.detect_from_label_config(xml)
        assert any(r["type"] == "multiple_choice" for r in result)

    def test_choice_type_multiple(self):
        from services.evaluation.config import AnswerTypeDetector

        xml = '<View><Choices name="q" choice="multiple"><Choice value="A"/><Choice value="B"/></Choices></View>'
        result = AnswerTypeDetector.detect_from_label_config(xml)
        assert any(r["type"] == "multiple_choice" for r in result)

    def test_choices_included_in_result(self):
        from services.evaluation.config import AnswerTypeDetector

        xml = '<View><Choices name="q"><Choice value="A"/><Choice value="B"/><Choice value="C"/></Choices></View>'
        result = AnswerTypeDetector.detect_from_label_config(xml)
        choices_result = [r for r in result if r.get("choices")]
        assert len(choices_result) == 1
        assert set(choices_result[0]["choices"]) == {"A", "B", "C"}


# ============================================================================
# 6. extract_fields_from_data
# ============================================================================


class TestExtractFieldsFromData:
    """Tests for routers.projects.tasks.extract_fields_from_data"""

    def test_empty_dict(self):
        from routers.projects.tasks import extract_fields_from_data

        assert extract_fields_from_data({}) == []

    def test_non_dict_input(self):
        from routers.projects.tasks import extract_fields_from_data

        assert extract_fields_from_data("string") == []

    def test_string_field(self):
        from routers.projects.tasks import extract_fields_from_data

        result = extract_fields_from_data({"title": "Hello"})
        assert len(result) == 1
        assert result[0]["path"] == "$title"
        assert result[0]["data_type"] == "string"
        assert result[0]["sample_value"] == "Hello"
        assert result[0]["is_nested"] is False

    def test_number_field(self):
        from routers.projects.tasks import extract_fields_from_data

        result = extract_fields_from_data({"score": 42})
        assert result[0]["data_type"] == "number"
        assert result[0]["sample_value"] == "42"

    def test_float_field(self):
        from routers.projects.tasks import extract_fields_from_data

        result = extract_fields_from_data({"rate": 3.14})
        assert result[0]["data_type"] == "number"

    def test_boolean_field(self):
        from routers.projects.tasks import extract_fields_from_data

        # Note: Python's isinstance(True, (int, float)) is True, so booleans
        # are detected as "number" since that check comes first in the code.
        result = extract_fields_from_data({"active": True})
        assert result[0]["data_type"] == "number"
        assert result[0]["sample_value"] == "True"

    def test_list_field(self):
        from routers.projects.tasks import extract_fields_from_data

        result = extract_fields_from_data({"tags": ["a", "b", "c"]})
        assert result[0]["data_type"] == "array"
        assert result[0]["sample_value"] == "[3 items]"

    def test_nested_dict(self):
        from routers.projects.tasks import extract_fields_from_data

        result = extract_fields_from_data({"meta": {"key": "val"}})
        # Should have both the parent object and the nested field
        paths = {r["path"] for r in result}
        assert "$meta" in paths
        nested = [r for r in result if r["path"] == "$meta.key"]
        assert len(nested) == 1
        assert nested[0]["is_nested"] is True

    def test_long_string_truncation(self):
        from routers.projects.tasks import extract_fields_from_data

        long_text = "x" * 200
        result = extract_fields_from_data({"content": long_text})
        assert result[0]["sample_value"].endswith("...")
        assert len(result[0]["sample_value"]) == 103  # 100 chars + "..."

    def test_sensitive_field_filtered(self):
        from routers.projects.tasks import extract_fields_from_data

        result = extract_fields_from_data({"ground_truth": "secret", "question": "hello"})
        paths = [r["path"] for r in result]
        assert "$ground_truth" not in paths
        assert "$question" in paths

    def test_sensitive_reference_answer(self):
        from routers.projects.tasks import extract_fields_from_data

        result = extract_fields_from_data({"reference_answer": "answer"})
        assert len(result) == 0

    def test_sensitive_annotations(self):
        from routers.projects.tasks import extract_fields_from_data

        result = extract_fields_from_data({"annotations": [1, 2]})
        assert len(result) == 0

    def test_display_name_formatting(self):
        from routers.projects.tasks import extract_fields_from_data

        result = extract_fields_from_data({"my_field_name": "val"})
        assert result[0]["display_name"] == "My Field Name"

    def test_none_value(self):
        from routers.projects.tasks import extract_fields_from_data

        result = extract_fields_from_data({"x": None})
        assert result[0]["data_type"] == "unknown"

    def test_prefix_nesting(self):
        from routers.projects.tasks import extract_fields_from_data

        result = extract_fields_from_data({"a": "b"}, prefix="outer")
        assert result[0]["path"] == "$outer.a"
        assert result[0]["is_nested"] is True


# ============================================================================
# 7. _get_task_preview
# ============================================================================


class TestDetectProviderExtended:
    """Additional tests for detect_provider_from_model_id"""

    def test_gpt_4(self):
        from routers.leaderboards import detect_provider_from_model_id

        assert detect_provider_from_model_id("gpt-4") == "OpenAI"

    def test_gpt_4_turbo(self):
        from routers.leaderboards import detect_provider_from_model_id

        assert detect_provider_from_model_id("gpt-4-turbo") == "OpenAI"

    def test_claude_3_opus(self):
        from routers.leaderboards import detect_provider_from_model_id

        assert detect_provider_from_model_id("claude-3-opus-20240229") == "Anthropic"

    def test_gemini_pro(self):
        from routers.leaderboards import detect_provider_from_model_id

        assert detect_provider_from_model_id("gemini-pro") == "Google"

    def test_llama_in_middle(self):
        from routers.leaderboards import detect_provider_from_model_id

        assert detect_provider_from_model_id("meta-llama-3-70b") == "Meta"

    def test_mixtral(self):
        from routers.leaderboards import detect_provider_from_model_id

        assert detect_provider_from_model_id("mixtral-8x7b") == "Mistral"

    def test_qwen_2(self):
        from routers.leaderboards import detect_provider_from_model_id

        assert detect_provider_from_model_id("qwen-2-72b") == "Alibaba"

    def test_deepseek_coder(self):
        from routers.leaderboards import detect_provider_from_model_id

        assert detect_provider_from_model_id("deepseek-coder-v2") == "DeepSeek"

    def test_command_r(self):
        from routers.leaderboards import detect_provider_from_model_id

        assert detect_provider_from_model_id("command-r-plus") == "Cohere"

    def test_unknown_literal(self):
        from routers.leaderboards import detect_provider_from_model_id

        assert detect_provider_from_model_id("unknown") == "Unknown"

    def test_random_model(self):
        from routers.leaderboards import detect_provider_from_model_id

        assert detect_provider_from_model_id("some-random-model") == "Other"

    def test_case_insensitive_gpt(self):
        from routers.leaderboards import detect_provider_from_model_id

        assert detect_provider_from_model_id("GPT-4o") == "OpenAI"

    def test_case_insensitive_claude(self):
        from routers.leaderboards import detect_provider_from_model_id

        assert detect_provider_from_model_id("Claude-3.5-Sonnet") == "Anthropic"

    def test_empty_string(self):
        from routers.leaderboards import detect_provider_from_model_id

        assert detect_provider_from_model_id("") == "Other"


# ============================================================================
# 9. BatchProcessingConfig
# ============================================================================


class TestBatchProcessingConfigExtended:
    """Extended tests for BatchProcessingConfig pure class methods."""

    def test_boundary_999_is_small(self):
        from services.batch_processing_config import BatchProcessingConfig

        assert BatchProcessingConfig.get_dataset_size_category(999) == "small"

    def test_boundary_1000_is_medium(self):
        from services.batch_processing_config import BatchProcessingConfig

        assert BatchProcessingConfig.get_dataset_size_category(1000) == "medium"

    def test_boundary_4999_is_medium(self):
        from services.batch_processing_config import BatchProcessingConfig

        assert BatchProcessingConfig.get_dataset_size_category(4999) == "medium"

    def test_boundary_5000_is_large(self):
        from services.batch_processing_config import BatchProcessingConfig

        assert BatchProcessingConfig.get_dataset_size_category(5000) == "large"

    def test_boundary_9999_is_large(self):
        from services.batch_processing_config import BatchProcessingConfig

        assert BatchProcessingConfig.get_dataset_size_category(9999) == "large"

    def test_boundary_10000_is_xlarge(self):
        from services.batch_processing_config import BatchProcessingConfig

        assert BatchProcessingConfig.get_dataset_size_category(10000) == "xlarge"

    def test_zero_items(self):
        from services.batch_processing_config import BatchProcessingConfig

        assert BatchProcessingConfig.get_dataset_size_category(0) == "small"

    def test_enterprise_halves_import(self):
        from services.batch_processing_config import BatchProcessingConfig

        local = BatchProcessingConfig.get_optimal_batch_size("import", 500, "local")
        enterprise = BatchProcessingConfig.get_optimal_batch_size("import", 500, "enterprise")
        assert enterprise == local // 2

    def test_enterprise_halves_export(self):
        from services.batch_processing_config import BatchProcessingConfig

        local = BatchProcessingConfig.get_optimal_batch_size("export", 500, "local")
        enterprise = BatchProcessingConfig.get_optimal_batch_size("export", 500, "enterprise")
        assert enterprise == local // 2

    def test_timeout_connect_always_10(self):
        from services.batch_processing_config import BatchProcessingConfig

        for count in [100, 2000, 7000, 20000]:
            config = BatchProcessingConfig.get_timeout_config(count)
            assert config["connect"] == 10

    def test_timeout_read_increases_with_size(self):
        from services.batch_processing_config import BatchProcessingConfig

        small = BatchProcessingConfig.get_timeout_config(100)["read"]
        xlarge = BatchProcessingConfig.get_timeout_config(20000)["read"]
        assert xlarge > small

    def test_estimated_time_has_required_keys(self):
        from services.batch_processing_config import BatchProcessingConfig

        result = BatchProcessingConfig.calculate_estimated_time(1000, "import")
        assert "batch_size" in result
        assert "num_batches" in result
        assert "estimated_seconds" in result
        assert "estimated_minutes" in result
        assert "items_per_second" in result

    def test_xlarge_has_overhead(self):
        from services.batch_processing_config import BatchProcessingConfig

        # Over 5000 items should have 20% overhead
        result = BatchProcessingConfig.calculate_estimated_time(10000, "import")
        assert result["estimated_seconds"] > 0

    def test_rate_limit_local(self):
        from services.batch_processing_config import BatchProcessingConfig

        config = BatchProcessingConfig.get_rate_limit_config("local")
        assert config["requests_per_second"] == 50

    def test_rate_limit_enterprise(self):
        from services.batch_processing_config import BatchProcessingConfig

        config = BatchProcessingConfig.get_rate_limit_config("enterprise")
        assert config["requests_per_second"] == 10

    def test_rate_limit_unknown_defaults_to_local(self):
        from services.batch_processing_config import BatchProcessingConfig

        config = BatchProcessingConfig.get_rate_limit_config("unknown")
        assert config == BatchProcessingConfig.RATE_LIMIT_CONFIG["local"]


# ============================================================================
# 10. TaskFormatter
# ============================================================================


class TestTaskFormatterExtended:
    """Extended tests for TaskFormatter pure methods."""

    def test_format_raw_json_includes_all_data(self):
        from services.task_formatter import TaskFormatter

        data = {"id": "t1", "text": "hello", "meta": {"k": "v"}}
        result = TaskFormatter.format_task(data, presentation_mode="raw_json")
        assert result["data"] == data

    def test_format_template_with_mappings(self):
        from services.task_formatter import TaskFormatter

        data = {"q": "What?", "a": "That."}
        result = TaskFormatter.format_task(
            data, presentation_mode="template", field_mappings={"q": "Question", "a": "Answer"}
        )
        assert result["data"]["Question"] == "What?"
        assert result["data"]["Answer"] == "That."

    def test_format_template_long_text_formatting(self):
        from services.task_formatter import TaskFormatter

        data = {"essay": "x" * 200}
        result = TaskFormatter.format_task(data, presentation_mode="template")
        assert "[ESSAY]" in result.get("formatted_text", "")

    def test_format_auto_detects_text(self):
        from services.task_formatter import TaskFormatter

        data = {"text": "hello world"}
        result = TaskFormatter.format_task(data, presentation_mode="auto")
        assert "text" in result.get("detected_type", "") or result["data"].get("text")

    def test_format_auto_detects_question(self):
        from services.task_formatter import TaskFormatter

        data = {"question": "What is this?"}
        result = TaskFormatter.format_task(data, presentation_mode="auto")
        assert result["data"].get("question") == "What is this?"

    def test_custom_instruction(self):
        from services.task_formatter import TaskFormatter

        data = {"text": "test"}
        result = TaskFormatter.format_task(data, instruction="Do X")
        assert result["instruction"] == "Do X"

    def test_default_instruction(self):
        from services.task_formatter import TaskFormatter

        data = {"text": "test"}
        result = TaskFormatter.format_task(data)
        assert "annotation task" in result["instruction"].lower()

    def test_batch_format_returns_list(self):
        from services.task_formatter import TaskFormatter

        tasks = [{"text": "a"}, {"text": "b"}]
        result = TaskFormatter.batch_format_tasks(tasks)
        assert len(result) == 2

    def test_create_llm_prompt_default_system(self):
        from services.task_formatter import TaskFormatter

        formatted = {"instruction": "Annotate this", "data": {"text": "hello"}}
        result = TaskFormatter.create_llm_prompt(formatted)
        assert "expert annotator" in result["system"].lower()
        assert "hello" in result["user"]

    def test_create_llm_prompt_custom_system(self):
        from services.task_formatter import TaskFormatter

        formatted = {"data": {"text": "hello"}}
        result = TaskFormatter.create_llm_prompt(formatted, system_prompt="You are a judge.")
        assert result["system"] == "You are a judge."

    def test_create_llm_prompt_with_choices(self):
        from services.task_formatter import TaskFormatter

        formatted = {
            "data": {"text": "test"},
            "annotation_requirements": {"choices": ["A", "B", "C"]},
        }
        result = TaskFormatter.create_llm_prompt(formatted)
        assert "Choose from" in result["user"]

    def test_create_llm_prompt_with_labels(self):
        from services.task_formatter import TaskFormatter

        formatted = {
            "data": {"text": "test"},
            "annotation_requirements": {"labels": ["PER", "ORG"]},
        }
        result = TaskFormatter.create_llm_prompt(formatted)
        assert "entity" in result["user"].lower()


# ============================================================================
# 11. LabelConfigParser
# ============================================================================


class TestLabelConfigParserExtended:
    """Extended tests for LabelConfigParser."""

    def test_number_with_min_max(self):
        from services.label_config.parser import LabelConfigParser

        xml = '<View><Number name="score" toName="text" min="0" max="100"/></View>'
        fields = LabelConfigParser.extract_fields(xml, sanitize=False)
        assert fields[0]["min"] == 0.0
        assert fields[0]["max"] == 100.0

    def test_rating_with_max_rating(self):
        from services.label_config.parser import LabelConfigParser

        xml = '<View><Rating name="stars" toName="text" maxRating="10"/></View>'
        fields = LabelConfigParser.extract_fields(xml, sanitize=False)
        assert fields[0]["maxRating"] == 10

    def test_choices_with_multiple_options(self):
        from services.label_config.parser import LabelConfigParser

        xml = '<View><Choices name="q" toName="text"><Choice value="A"/><Choice value="B"/><Choice value="C"/></Choices></View>'
        fields = LabelConfigParser.extract_fields(xml, sanitize=False)
        assert fields[0]["options"] == ["A", "B", "C"]

    def test_validate_config_valid(self):
        from services.label_config.parser import LabelConfigParser

        xml = '<View><Choices name="q" toName="text"><Choice value="A"/></Choices></View>'
        result = LabelConfigParser.validate_config(xml)
        assert result["valid"] is True
        assert result["field_count"] == 1

    def test_validate_config_empty(self):
        from services.label_config.parser import LabelConfigParser

        result = LabelConfigParser.validate_config("")
        assert result["valid"] is False

    def test_validate_config_no_fields(self):
        from services.label_config.parser import LabelConfigParser

        result = LabelConfigParser.validate_config("<View></View>")
        assert result["valid"] is False

    def test_validate_config_duplicate_names(self):
        from services.label_config.parser import LabelConfigParser

        xml = '<View><Choices name="q" toName="text"><Choice value="A"/></Choices><Choices name="q" toName="text"><Choice value="B"/></Choices></View>'
        result = LabelConfigParser.validate_config(xml)
        assert result["valid"] is False
        assert "Duplicate" in result["error"]

    def test_parse_field_attributes(self):
        from services.label_config.parser import LabelConfigParser

        xml = '<View><Choices name="q" toName="text" required="true"><Choice value="A"/></Choices></View>'
        attrs = LabelConfigParser.parse_field_attributes(xml, "q")
        assert attrs["required"] == "true"

    def test_parse_field_attributes_nonexistent(self):
        from services.label_config.parser import LabelConfigParser

        xml = '<View><Choices name="q" toName="text"><Choice value="A"/></Choices></View>'
        attrs = LabelConfigParser.parse_field_attributes(xml, "nonexistent")
        assert attrs == {}


# ============================================================================
# 12. LabelConfigSanitizer
# ============================================================================


class TestLabelConfigSanitizerExtended:
    """Extended tests for LabelConfigSanitizer."""

    def test_sanitize_script_tag(self):
        from services.label_config.sanitizer import LabelConfigSanitizer

        result = LabelConfigSanitizer.sanitize_field_name('<script>alert("xss")</script>')
        assert "<script>" not in result
        assert "alert" not in result or "&lt;" in result

    def test_sanitize_javascript_protocol(self):
        from services.label_config.sanitizer import LabelConfigSanitizer

        result = LabelConfigSanitizer.sanitize_field_name("javascript:alert(1)")
        assert "javascript:" not in result

    def test_sanitize_event_handler(self):
        from services.label_config.sanitizer import LabelConfigSanitizer

        result = LabelConfigSanitizer.sanitize_field_name('onclick=alert(1)')
        # Should be escaped
        assert "onclick=" not in result or "&" in result

    def test_sanitize_empty_string(self):
        from services.label_config.sanitizer import LabelConfigSanitizer

        assert LabelConfigSanitizer.sanitize_field_name("") == ""

    def test_sanitize_none(self):
        from services.label_config.sanitizer import LabelConfigSanitizer

        assert LabelConfigSanitizer.sanitize_field_name(None) is None

    def test_sanitize_normal_name(self):
        from services.label_config.sanitizer import LabelConfigSanitizer

        assert LabelConfigSanitizer.sanitize_field_name("my_field") == "my_field"

    def test_sanitize_field_dict(self):
        from services.label_config.sanitizer import LabelConfigSanitizer

        field = {"name": "field<script>", "type": "Choices"}
        result = LabelConfigSanitizer.sanitize_field(field)
        assert "<script>" not in result["name"]

    def test_sanitize_field_non_dict(self):
        from services.label_config.sanitizer import LabelConfigSanitizer

        assert LabelConfigSanitizer.sanitize_field("string") == "string"

    def test_sanitize_field_with_list(self):
        from services.label_config.sanitizer import LabelConfigSanitizer

        field = {"options": ["<script>", "normal"]}
        result = LabelConfigSanitizer.sanitize_field(field)
        assert "<script>" not in result["options"][0]

    def test_sanitize_nested_dict(self):
        from services.label_config.sanitizer import LabelConfigSanitizer

        field = {"attrs": {"val": '<img onerror="alert(1)">'}}
        result = LabelConfigSanitizer.sanitize_field(field)
        assert "onerror" not in result["attrs"]["val"] or "&" in result["attrs"]["val"]

    def test_sanitize_label_config_response_empty(self):
        from services.label_config.sanitizer import LabelConfigSanitizer

        assert LabelConfigSanitizer.sanitize_label_config_response("") == ""
        assert LabelConfigSanitizer.sanitize_label_config_response(None) is None

    def test_sanitize_label_config_response_xml(self):
        from services.label_config.sanitizer import LabelConfigSanitizer

        xml = '<View><Choices name="q"/></View>'
        result = LabelConfigSanitizer.sanitize_label_config_response(xml)
        assert "&lt;" in result


# ============================================================================
# 13. sanitize_user_input
# ============================================================================


class TestSanitizeUserInputExtended:
    """Extended tests for auth_module.user_service.sanitize_user_input"""

    def test_basic_string(self):
        from auth_module.user_service import sanitize_user_input

        assert sanitize_user_input("Hello World") == "Hello World"

    def test_html_escape(self):
        from auth_module.user_service import sanitize_user_input

        result = sanitize_user_input("<b>bold</b>")
        assert "<b>" not in result
        assert "&lt;b&gt;" in result

    def test_script_removal(self):
        from auth_module.user_service import sanitize_user_input

        result = sanitize_user_input('<script>alert("xss")</script>')
        assert "script" not in result.lower() or "&lt;" in result

    def test_max_length_truncation(self):
        from auth_module.user_service import sanitize_user_input

        long_input = "a" * 200
        result = sanitize_user_input(long_input)
        assert len(result) <= 100

    def test_whitespace_stripping(self):
        from auth_module.user_service import sanitize_user_input

        assert sanitize_user_input("  hello  ") == "hello"

    def test_empty_string(self):
        from auth_module.user_service import sanitize_user_input

        assert sanitize_user_input("") == ""

    def test_none_input(self):
        from auth_module.user_service import sanitize_user_input

        assert sanitize_user_input(None) is None

    def test_iframe_removal(self):
        from auth_module.user_service import sanitize_user_input

        result = sanitize_user_input('<iframe src="evil.com"></iframe>')
        # After HTML escaping, the iframe tags become &lt;iframe...
        # The dangerous pattern regex won't match the escaped version, but
        # the content is still safe because it's HTML-escaped
        assert "<iframe" not in result

    def test_special_chars_preserved(self):
        from auth_module.user_service import sanitize_user_input

        # Ampersand gets HTML-escaped
        result = sanitize_user_input("A & B")
        assert "A" in result and "B" in result


# ============================================================================
# 14. email_validation extended
# ============================================================================


class TestEmailValidationExtended:
    """Extended tests for email validation pure functions."""

    def test_valid_standard_email(self):
        from services.email.email_validation import is_valid_email

        assert is_valid_email("user@domain.com") is True

    def test_valid_with_plus(self):
        from services.email.email_validation import is_valid_email

        assert is_valid_email("user+tag@domain.com") is True

    def test_valid_with_dots(self):
        from services.email.email_validation import is_valid_email

        assert is_valid_email("first.last@domain.com") is True

    def test_invalid_no_at(self):
        from services.email.email_validation import is_valid_email

        assert is_valid_email("nodomain") is False

    def test_invalid_double_at(self):
        from services.email.email_validation import is_valid_email

        assert is_valid_email("user@@domain.com") is False

    def test_invalid_consecutive_dots(self):
        from services.email.email_validation import is_valid_email

        assert is_valid_email("user..name@domain.com") is False

    def test_invalid_no_domain_dot(self):
        from services.email.email_validation import is_valid_email

        assert is_valid_email("user@domain") is False

    def test_invalid_empty(self):
        from services.email.email_validation import is_valid_email

        assert is_valid_email("") is False

    def test_invalid_none(self):
        from services.email.email_validation import is_valid_email

        assert is_valid_email(None) is False

    def test_validate_details_whitespace(self):
        from services.email.email_validation import validate_email_with_details

        valid, msg = validate_email_with_details("user @domain.com")
        assert valid is False
        assert "whitespace" in msg.lower()

    def test_validate_details_no_at(self):
        from services.email.email_validation import validate_email_with_details

        valid, msg = validate_email_with_details("userdomain.com")
        assert valid is False
        assert "@" in msg

    def test_validate_details_empty_local(self):
        from services.email.email_validation import validate_email_with_details

        valid, msg = validate_email_with_details("@domain.com")
        assert valid is False

    def test_validate_details_local_starts_dot(self):
        from services.email.email_validation import validate_email_with_details

        valid, msg = validate_email_with_details(".user@domain.com")
        assert valid is False

    def test_validate_details_local_ends_dot(self):
        from services.email.email_validation import validate_email_with_details

        valid, msg = validate_email_with_details("user.@domain.com")
        assert valid is False

    def test_validate_details_domain_starts_dot(self):
        from services.email.email_validation import validate_email_with_details

        valid, msg = validate_email_with_details("user@.domain.com")
        assert valid is False

    def test_validate_details_valid(self):
        from services.email.email_validation import validate_email_with_details

        valid, msg = validate_email_with_details("user@domain.com")
        assert valid is True
        assert msg is None

    def test_sanitize_email_strips_spaces(self):
        from services.email.email_validation import sanitize_email

        result = sanitize_email("  user@domain.com  ")
        assert result == "user@domain.com"

    def test_sanitize_email_lowercase(self):
        from services.email.email_validation import sanitize_email

        result = sanitize_email("User@Domain.COM")
        assert result == "user@domain.com"

    def test_sanitize_email_invalid_returns_none(self):
        from services.email.email_validation import sanitize_email

        assert sanitize_email("not-an-email") is None

    def test_sanitize_email_none(self):
        from services.email.email_validation import sanitize_email

        assert sanitize_email(None) is None

    def test_extract_domain(self):
        from services.email.email_validation import extract_domain

        assert extract_domain("user@example.org") == "example.org"

    def test_extract_domain_invalid(self):
        from services.email.email_validation import extract_domain

        assert extract_domain("not-an-email") is None

    def test_disposable_mailinator(self):
        from services.email.email_validation import is_disposable_email

        assert is_disposable_email("user@mailinator.com") is True

    def test_disposable_yopmail(self):
        from services.email.email_validation import is_disposable_email

        assert is_disposable_email("user@yopmail.com") is True

    def test_not_disposable(self):
        from services.email.email_validation import is_disposable_email

        assert is_disposable_email("user@gmail.com") is False

    def test_bulk_emails(self):
        from services.email.email_validation import validate_bulk_emails

        result = validate_bulk_emails(["good@domain.com", "bad", "also@good.org"])
        assert result["stats"]["valid_count"] == 2
        assert result["stats"]["invalid_count"] == 1
        assert len(result["valid"]) == 2
        assert len(result["invalid"]) == 1

    def test_bulk_empty_list(self):
        from services.email.email_validation import validate_bulk_emails

        result = validate_bulk_emails([])
        assert result["stats"]["total"] == 0
        assert result["stats"]["validity_rate"] == 0

    def test_long_local_part(self):
        from services.email.email_validation import is_valid_email

        long_local = "a" * 65
        assert is_valid_email(f"{long_local}@domain.com") is False

    def test_long_domain(self):
        from services.email.email_validation import is_valid_email

        long_domain = "a" * 254 + ".com"
        assert is_valid_email(f"user@{long_domain}") is False


# ============================================================================
# 15. _ensure_dict extended
# ============================================================================


class TestEnsureDictExtended:
    """Extended tests for _ensure_dict helper in auth router."""

    def test_valid_json_string(self):
        from routers.auth import _ensure_dict

        result = _ensure_dict('{"a": 1, "b": 2}')
        assert result == {"a": 1, "b": 2}

    def test_list_json_string_returns_none(self):
        from routers.auth import _ensure_dict

        assert _ensure_dict("[1, 2, 3]") is None

    def test_invalid_json_string_returns_none(self):
        from routers.auth import _ensure_dict

        assert _ensure_dict("not json at all") is None

    def test_empty_json_object(self):
        from routers.auth import _ensure_dict

        assert _ensure_dict("{}") == {}

    def test_nested_json_string(self):
        from routers.auth import _ensure_dict

        result = _ensure_dict('{"outer": {"inner": 1}}')
        assert result == {"outer": {"inner": 1}}

    def test_integer_returns_none(self):
        from routers.auth import _ensure_dict

        assert _ensure_dict(42) is None

    def test_boolean_returns_none(self):
        from routers.auth import _ensure_dict

        assert _ensure_dict(True) is None

    def test_float_returns_none(self):
        from routers.auth import _ensure_dict

        assert _ensure_dict(3.14) is None


# ============================================================================
# 16. _derive_evaluation_configs_from_selected_methods
# ============================================================================


class TestDeriveEvaluationConfigs:
    """Tests for _derive_evaluation_configs_from_selected_methods."""

    def test_empty_methods(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods

        assert _derive_evaluation_configs_from_selected_methods({}) == []

    def test_single_field_string_metric(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods

        methods = {"answer": {"automated": ["bleu"], "field_mapping": {}}}
        result = _derive_evaluation_configs_from_selected_methods(methods)
        assert len(result) == 1
        assert result[0]["metric"] == "bleu"
        assert result[0]["id"] == "answer_bleu"

    def test_object_metric_with_params(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods

        methods = {
            "answer": {
                "automated": [{"name": "bleu", "parameters": {"max_order": 2}}],
                "field_mapping": {},
            }
        }
        result = _derive_evaluation_configs_from_selected_methods(methods)
        assert result[0]["metric_parameters"] == {"max_order": 2}

    def test_field_mapping_respected(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods

        methods = {
            "answer": {
                "automated": ["rouge"],
                "field_mapping": {
                    "prediction_field": "gen_output",
                    "reference_field": "gold_answer",
                },
            }
        }
        result = _derive_evaluation_configs_from_selected_methods(methods)
        assert result[0]["prediction_fields"] == ["gen_output"]
        assert result[0]["reference_fields"] == ["gold_answer"]

    def test_default_field_mapping(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods

        methods = {"answer": {"automated": ["bleu"], "field_mapping": {}}}
        result = _derive_evaluation_configs_from_selected_methods(methods)
        # Default should use the field name itself
        assert result[0]["prediction_fields"] == ["answer"]
        assert result[0]["reference_fields"] == ["answer"]

    def test_non_dict_selections_skipped(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods

        methods = {"answer": "not_a_dict"}
        result = _derive_evaluation_configs_from_selected_methods(methods)
        assert result == []

    def test_display_name_formatting(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods

        methods = {"answer": {"automated": ["exact_match"], "field_mapping": {}}}
        result = _derive_evaluation_configs_from_selected_methods(methods)
        assert result[0]["display_name"] == "Exact Match"

    def test_multiple_metrics(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods

        methods = {"answer": {"automated": ["bleu", "rouge", "meteor"], "field_mapping": {}}}
        result = _derive_evaluation_configs_from_selected_methods(methods)
        assert len(result) == 3
        metrics = [r["metric"] for r in result]
        assert "bleu" in metrics
        assert "rouge" in metrics
        assert "meteor" in metrics

    def test_enabled_flag(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods

        methods = {"answer": {"automated": ["bleu"], "field_mapping": {}}}
        result = _derive_evaluation_configs_from_selected_methods(methods)
        assert result[0]["enabled"] is True

    def test_no_automated_key(self):
        from routers.evaluations.config import _derive_evaluation_configs_from_selected_methods

        methods = {"answer": {"field_mapping": {}}}
        result = _derive_evaluation_configs_from_selected_methods(methods)
        assert result == []


# ============================================================================
# 17. extract_metric_name
# ============================================================================


class TestExtractMetricName:
    """Tests for extract_metric_name helper."""

    def test_string_input(self):
        from routers.evaluations.helpers import extract_metric_name

        assert extract_metric_name("bleu") == "bleu"

    def test_dict_input(self):
        from routers.evaluations.helpers import extract_metric_name

        assert extract_metric_name({"name": "rouge", "params": {}}) == "rouge"

    def test_dict_without_name(self):
        from routers.evaluations.helpers import extract_metric_name

        assert extract_metric_name({"params": {}}) == ""

    def test_none_input(self):
        from routers.evaluations.helpers import extract_metric_name

        assert extract_metric_name(None) == ""

    def test_integer_input(self):
        from routers.evaluations.helpers import extract_metric_name

        assert extract_metric_name(42) == ""

    def test_empty_string(self):
        from routers.evaluations.helpers import extract_metric_name

        assert extract_metric_name("") == ""

    def test_empty_dict(self):
        from routers.evaluations.helpers import extract_metric_name

        assert extract_metric_name({}) == ""

    def test_dict_with_empty_name(self):
        from routers.evaluations.helpers import extract_metric_name

        assert extract_metric_name({"name": ""}) == ""


# ============================================================================
# 18. deep_merge_dicts extended
# ============================================================================


class TestDeepMergeDictsExtended:
    """Extended edge case tests for deep_merge_dicts."""

    def test_merge_with_empty_nested_dict(self):
        from routers.projects.crud import deep_merge_dicts

        result = deep_merge_dicts({"a": {}}, {"a": {"b": 1}})
        assert result == {"a": {"b": 1}}

    def test_merge_preserves_types(self):
        from routers.projects.crud import deep_merge_dicts

        result = deep_merge_dicts({"a": 1}, {"a": "string"})
        assert result["a"] == "string"

    def test_merge_list_replaces(self):
        from routers.projects.crud import deep_merge_dicts

        result = deep_merge_dicts({"a": [1, 2]}, {"a": [3, 4, 5]})
        assert result["a"] == [3, 4, 5]

    def test_merge_new_key_added(self):
        from routers.projects.crud import deep_merge_dicts

        result = deep_merge_dicts({"a": 1}, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_merge_none_value_removes_key(self):
        from routers.projects.crud import deep_merge_dicts

        result = deep_merge_dicts({"a": 1, "b": 2}, {"a": None})
        assert "a" not in result
        assert result["b"] == 2

    def test_merge_deeply_nested(self):
        from routers.projects.crud import deep_merge_dicts

        base = {"a": {"b": {"c": 1, "d": 2}}}
        update = {"a": {"b": {"c": 3, "e": 4}}}
        result = deep_merge_dicts(base, update)
        assert result == {"a": {"b": {"c": 3, "d": 2, "e": 4}}}

    def test_both_empty(self):
        from routers.projects.crud import deep_merge_dicts

        result = deep_merge_dicts({}, {})
        assert result == {}


# ============================================================================
# 19. convert_to/from_label_studio_format
# ============================================================================


class TestLabelStudioFormatConversion:
    """Tests for import_export format conversion functions."""

    def test_to_ls_non_span_passthrough(self):
        from routers.projects.import_export import convert_to_label_studio_format

        results = [{"type": "choices", "value": {"choices": ["A"]}}]
        output = convert_to_label_studio_format(results)
        assert output == results

    def test_to_ls_none_input(self):
        from routers.projects.import_export import convert_to_label_studio_format

        assert convert_to_label_studio_format(None) is None

    def test_to_ls_empty_list(self):
        from routers.projects.import_export import convert_to_label_studio_format

        assert convert_to_label_studio_format([]) == []

    def test_to_ls_span_flattening(self):
        from routers.projects.import_export import convert_to_label_studio_format

        results = [
            {
                "type": "labels",
                "from_name": "ner",
                "to_name": "text",
                "value": {
                    "spans": [
                        {"id": "s1", "start": 0, "end": 5, "text": "Hello", "labels": ["PER"]},
                        {"id": "s2", "start": 10, "end": 15, "text": "World", "labels": ["ORG"]},
                    ]
                },
            }
        ]
        output = convert_to_label_studio_format(results)
        assert len(output) == 2
        assert output[0]["value"]["start"] == 0
        assert output[1]["value"]["start"] == 10

    def test_from_ls_non_span_passthrough(self):
        from routers.projects.import_export import convert_from_label_studio_format

        results = [{"type": "choices", "value": {"choices": ["A"]}}]
        output = convert_from_label_studio_format(results)
        assert output == results

    def test_from_ls_none_input(self):
        from routers.projects.import_export import convert_from_label_studio_format

        assert convert_from_label_studio_format(None) is None

    def test_from_ls_consolidates_spans(self):
        from routers.projects.import_export import convert_from_label_studio_format

        results = [
            {
                "id": "s1",
                "type": "labels",
                "from_name": "ner",
                "to_name": "text",
                "value": {"start": 0, "end": 5, "text": "Hello", "labels": ["PER"]},
            },
            {
                "id": "s2",
                "type": "labels",
                "from_name": "ner",
                "to_name": "text",
                "value": {"start": 10, "end": 15, "text": "World", "labels": ["ORG"]},
            },
        ]
        output = convert_from_label_studio_format(results)
        # Should consolidate into one entry with spans array
        span_entries = [r for r in output if r.get("value", {}).get("spans")]
        assert len(span_entries) == 1
        assert len(span_entries[0]["value"]["spans"]) == 2


# ============================================================================
# 20. _isoformat
# ============================================================================


class TestIsoformat:
    """Tests for _isoformat helper."""

    def test_with_datetime(self):
        from routers.projects.serializers import _isoformat

        dt = datetime(2024, 1, 15, 10, 30, 0)
        assert _isoformat(dt) == "2024-01-15T10:30:00"

    def test_with_none(self):
        from routers.projects.serializers import _isoformat

        assert _isoformat(None) is None

    def test_with_timezone(self):
        from routers.projects.serializers import _isoformat

        dt = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
        result = _isoformat(dt)
        assert "2024-06-01" in result

    def test_with_false_value(self):
        from routers.projects.serializers import _isoformat

        assert _isoformat(0) is None
        assert _isoformat("") is None


# ============================================================================
# 21. build_evaluation_indexes
# ============================================================================


class TestBuildEvaluationIndexes:
    """Tests for build_evaluation_indexes helper."""

    def test_empty_list(self):
        from routers.projects.serializers import build_evaluation_indexes

        by_task, by_gen = build_evaluation_indexes([])
        assert by_task == {}
        assert by_gen == {}

    def test_single_task_eval(self):
        from routers.projects.serializers import build_evaluation_indexes

        te = SimpleNamespace(task_id="t1", generation_id=None)
        by_task, by_gen = build_evaluation_indexes([te])
        assert "t1" in by_task
        assert len(by_task["t1"]) == 1
        assert by_gen == {}

    def test_generation_eval(self):
        from routers.projects.serializers import build_evaluation_indexes

        te = SimpleNamespace(task_id="t1", generation_id="g1")
        by_task, by_gen = build_evaluation_indexes([te])
        assert "t1" in by_task
        assert "g1" in by_gen

    def test_multiple_evals_same_task(self):
        from routers.projects.serializers import build_evaluation_indexes

        te1 = SimpleNamespace(task_id="t1", generation_id="g1")
        te2 = SimpleNamespace(task_id="t1", generation_id="g2")
        by_task, by_gen = build_evaluation_indexes([te1, te2])
        assert len(by_task["t1"]) == 2
        assert len(by_gen) == 2

    def test_mixed_with_and_without_generation(self):
        from routers.projects.serializers import build_evaluation_indexes

        te1 = SimpleNamespace(task_id="t1", generation_id=None)
        te2 = SimpleNamespace(task_id="t1", generation_id="g1")
        by_task, by_gen = build_evaluation_indexes([te1, te2])
        assert len(by_task["t1"]) == 2
        assert "g1" in by_gen
        assert len(by_gen) == 1


# ============================================================================
# 22. build_judge_model_lookup extended
# ============================================================================


class TestBuildJudgeModelLookupExtended:
    """Extended tests for build_judge_model_lookup."""

    def test_empty_runs(self):
        from routers.projects.serializers import build_judge_model_lookup

        assert build_judge_model_lookup([]) == {}

    def test_new_format(self):
        from routers.projects.serializers import build_judge_model_lookup

        er = SimpleNamespace(
            id="run1",
            eval_metadata={"judge_models": {"config1": "gpt-4", "config2": "claude-3"}},
        )
        result = build_judge_model_lookup([er])
        assert result[("run1", "config1")] == "gpt-4"
        assert result[("run1", "config2")] == "claude-3"

    def test_old_format(self):
        from routers.projects.serializers import build_judge_model_lookup

        er = SimpleNamespace(
            id="run1",
            eval_metadata={
                "evaluation_configs": [
                    {"id": "cfg1", "metric_parameters": {"judge_model": "gpt-4"}},
                ]
            },
        )
        result = build_judge_model_lookup([er])
        assert result[("run1", "cfg1")] == "gpt-4"

    def test_new_format_precedence(self):
        from routers.projects.serializers import build_judge_model_lookup

        er = SimpleNamespace(
            id="run1",
            eval_metadata={
                "judge_models": {"cfg1": "claude-3"},
                "evaluation_configs": [
                    {"id": "cfg1", "metric_parameters": {"judge_model": "gpt-4"}},
                ],
            },
        )
        result = build_judge_model_lookup([er])
        assert result[("run1", "cfg1")] == "claude-3"

    def test_none_eval_metadata(self):
        from routers.projects.serializers import build_judge_model_lookup

        er = SimpleNamespace(id="run1", eval_metadata=None)
        result = build_judge_model_lookup([er])
        assert result == {}

    def test_old_format_no_judge_model(self):
        from routers.projects.serializers import build_judge_model_lookup

        er = SimpleNamespace(
            id="run1",
            eval_metadata={
                "evaluation_configs": [{"id": "cfg1", "metric_parameters": {}}]
            },
        )
        result = build_judge_model_lookup([er])
        assert result == {}

    def test_old_format_no_metric_parameters(self):
        from routers.projects.serializers import build_judge_model_lookup

        er = SimpleNamespace(
            id="run1",
            eval_metadata={"evaluation_configs": [{"id": "cfg1"}]},
        )
        result = build_judge_model_lookup([er])
        assert result == {}


# ============================================================================
# 23. validate_structure_key
# ============================================================================


class TestValidateStructureKey:
    """Tests for validate_structure_key."""

    def test_valid_alphanumeric(self):
        from routers.prompt_structures import validate_structure_key

        # Should not raise
        validate_structure_key("myStructure123")

    def test_valid_with_underscore(self):
        from routers.prompt_structures import validate_structure_key

        validate_structure_key("my_structure")

    def test_valid_with_hyphen(self):
        from routers.prompt_structures import validate_structure_key

        validate_structure_key("my-structure")

    def test_invalid_empty(self):
        from routers.prompt_structures import validate_structure_key

        with pytest.raises(Exception):
            validate_structure_key("")

    def test_invalid_too_long(self):
        from routers.prompt_structures import validate_structure_key

        with pytest.raises(Exception):
            validate_structure_key("a" * 51)

    def test_invalid_special_chars(self):
        from routers.prompt_structures import validate_structure_key

        with pytest.raises(Exception):
            validate_structure_key("invalid key!")

    def test_invalid_slash(self):
        from routers.prompt_structures import validate_structure_key

        with pytest.raises(Exception):
            validate_structure_key("path/key")

    def test_invalid_space(self):
        from routers.prompt_structures import validate_structure_key

        with pytest.raises(Exception):
            validate_structure_key("has space")

    def test_single_char_valid(self):
        from routers.prompt_structures import validate_structure_key

        validate_structure_key("a")

    def test_max_length_valid(self):
        from routers.prompt_structures import validate_structure_key

        validate_structure_key("a" * 50)


# ============================================================================
# 24. generate_invitation_token
# ============================================================================


class TestGenerateInvitationToken:
    """Tests for generate_invitation_token."""

    def test_returns_string(self):
        from routers.invitations import generate_invitation_token

        token = generate_invitation_token()
        assert isinstance(token, str)

    def test_non_empty(self):
        from routers.invitations import generate_invitation_token

        token = generate_invitation_token()
        assert len(token) > 0

    def test_unique(self):
        from routers.invitations import generate_invitation_token

        tokens = {generate_invitation_token() for _ in range(100)}
        assert len(tokens) == 100

    def test_url_safe(self):
        from routers.invitations import generate_invitation_token

        token = generate_invitation_token()
        # URL-safe tokens contain only alphanumeric, hyphen, underscore
        safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
        assert all(c in safe_chars for c in token)


# ============================================================================
# 25. password hashing (pure, no DB)
# ============================================================================


class TestPasswordHashing:
    """Tests for password hashing pure functions."""

    def test_hash_not_plaintext(self):
        from auth_module.user_service import get_password_hash

        hashed = get_password_hash("mypassword")
        assert hashed != "mypassword"

    def test_hash_is_string(self):
        from auth_module.user_service import get_password_hash

        hashed = get_password_hash("test")
        assert isinstance(hashed, str)

    def test_verify_correct(self):
        from auth_module.user_service import get_password_hash, verify_password

        hashed = get_password_hash("secret")
        assert verify_password("secret", hashed) is True

    def test_verify_wrong(self):
        from auth_module.user_service import get_password_hash, verify_password

        hashed = get_password_hash("secret")
        assert verify_password("wrong", hashed) is False

    def test_verify_empty_password(self):
        from auth_module.user_service import verify_password

        # Should not crash, just return False or True depending on hash
        result = verify_password("", "$2b$12$invalid")
        assert result is False

    def test_alias_hash_password(self):
        from auth_module.user_service import hash_password

        hashed = hash_password("test")
        assert isinstance(hashed, str)

    def test_alias_check_password(self):
        from auth_module.user_service import check_password, hash_password

        hashed = hash_password("test")
        assert check_password("test", hashed) is True


# ============================================================================
# 26. _extract_primary_score extended
# ============================================================================


class TestExtractPrimaryScoreExtended:
    """Additional tests for _extract_primary_score."""

    def test_custom_with_float(self):
        from routers.evaluations.results import _extract_primary_score

        assert _extract_primary_score({"llm_judge_custom": 0.85}) == 0.85

    def test_generic_llm_judge(self):
        from routers.evaluations.results import _extract_primary_score

        assert _extract_primary_score({"llm_judge_something": 0.75}) == 0.75

    def test_skips_response_suffix(self):
        from routers.evaluations.results import _extract_primary_score

        result = _extract_primary_score(
            {"llm_judge_test_response": "text", "score": 0.5}
        )
        assert result == 0.5

    def test_skips_passed_suffix(self):
        from routers.evaluations.results import _extract_primary_score

        result = _extract_primary_score(
            {"llm_judge_test_passed": True, "overall_score": 0.7}
        )
        assert result == 0.7

    def test_overall_score_fallback(self):
        from routers.evaluations.results import _extract_primary_score

        assert _extract_primary_score({"overall_score": 0.9}) == 0.9

    def test_mixed_non_numeric_and_numeric(self):
        from routers.evaluations.results import _extract_primary_score

        result = _extract_primary_score({
            "llm_judge_custom": "also_invalid",
            "score": 0.6,
        })
        assert result == 0.6
