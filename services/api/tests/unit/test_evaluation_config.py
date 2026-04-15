"""
Unit tests for evaluation configuration system
Issue #483: Comprehensive evaluation configuration system
"""

from unittest.mock import Mock, patch

import pytest

from evaluation_config import (
    ANSWER_TYPE_TO_METRICS,
    AnswerType,
    AnswerTypeDetector,
    get_available_methods_for_project,
)


class TestAnswerTypeDetector:
    """Test answer type detection from Label Studio XML"""

    def test_detect_binary_choice(self):
        """Test detection of binary (Yes/No) answer types"""
        xml_config = """
        <View>
            <Text name="text" value="$text"/>
            <Choices name="answer" toName="text">
                <Choice value="Yes"/>
                <Choice value="No"/>
            </Choices>
        </View>
        """
        detector = AnswerTypeDetector(xml_config)
        result = detector.detect_answer_types()

        assert len(result) == 1
        assert result[0]['type'] == AnswerType.BINARY.value
        assert result[0]['name'] == 'answer'
        assert result[0]['choices'] == ['Yes', 'No']

    def test_detect_single_choice(self):
        """Test detection of single choice answer types"""
        xml_config = """
        <View>
            <Text name="text" value="$text"/>
            <Choices name="category" toName="text" choice="single">
                <Choice value="Contract"/>
                <Choice value="Agreement"/>
                <Choice value="Legal Opinion"/>
            </Choices>
        </View>
        """
        detector = AnswerTypeDetector(xml_config)
        result = detector.detect_answer_types()

        assert len(result) == 1
        assert result[0]['type'] == AnswerType.SINGLE_CHOICE.value
        assert result[0]['name'] == 'category'
        assert len(result[0]['choices']) == 3

    def test_detect_multiple_choice(self):
        """Test detection of multiple choice answer types"""
        xml_config = """
        <View>
            <Text name="text" value="$text"/>
            <Choices name="tags" toName="text" choice="multiple">
                <Choice value="Important"/>
                <Choice value="Urgent"/>
                <Choice value="Review"/>
            </Choices>
        </View>
        """
        detector = AnswerTypeDetector(xml_config)
        result = detector.detect_answer_types()

        assert len(result) == 1
        assert result[0]['type'] == AnswerType.MULTIPLE_CHOICE.value
        assert result[0]['name'] == 'tags'

    def test_detect_rating(self):
        """Test detection of rating answer types"""
        xml_config = """
        <View>
            <Text name="text" value="$text"/>
            <Rating name="quality" toName="text" maxRating="5"/>
        </View>
        """
        detector = AnswerTypeDetector(xml_config)
        result = detector.detect_answer_types()

        assert len(result) == 1
        assert result[0]['type'] == AnswerType.RATING.value
        assert result[0]['name'] == 'quality'
        assert result[0]['element_attrs']['maxRating'] == '5'

    def test_detect_text_types(self):
        """Test detection of text answer types"""
        xml_config = """
        <View>
            <Text name="text" value="$text"/>
            <TextArea name="summary" toName="text" rows="3"/>
            <TextArea name="analysis" toName="text" rows="10"/>
        </View>
        """
        detector = AnswerTypeDetector(xml_config)
        result = detector.detect_answer_types()

        assert len(result) == 2
        # First text area (3 rows = short text)
        assert result[0]['type'] == AnswerType.SHORT_TEXT.value
        # Second text area (10 rows = long text)
        assert result[1]['type'] == AnswerType.LONG_TEXT.value

    def test_detect_span_selection(self):
        """Test detection of span selection answer types"""
        xml_config = """
        <View>
            <Text name="text" value="$text"/>
            <Labels name="entities" toName="text">
                <Label value="Person"/>
                <Label value="Organization"/>
                <Label value="Location"/>
            </Labels>
        </View>
        """
        detector = AnswerTypeDetector(xml_config)
        result = detector.detect_answer_types()

        assert len(result) == 1
        assert result[0]['type'] == AnswerType.SPAN_SELECTION.value
        assert result[0]['name'] == 'entities'

    def test_detect_taxonomy(self):
        """Test detection of taxonomy answer types"""
        xml_config = """
        <View>
            <Text name="text" value="$text"/>
            <Taxonomy name="classification" toName="text">
                <Choice value="Legal">
                    <Choice value="Contract"/>
                    <Choice value="Agreement"/>
                </Choice>
                <Choice value="Financial">
                    <Choice value="Invoice"/>
                    <Choice value="Receipt"/>
                </Choice>
            </Taxonomy>
        </View>
        """
        detector = AnswerTypeDetector(xml_config)
        result = detector.detect_answer_types()

        assert len(result) == 1
        assert result[0]['type'] == AnswerType.TAXONOMY.value
        assert result[0]['name'] == 'classification'

    def test_detect_mixed_types(self):
        """Test detection of multiple answer types in one configuration"""
        xml_config = """
        <View>
            <Text name="text" value="$text"/>
            <Choices name="category" toName="text" choice="single">
                <Choice value="Type A"/>
                <Choice value="Type B"/>
            </Choices>
            <Rating name="confidence" toName="text" maxRating="5"/>
            <TextArea name="notes" toName="text" rows="3"/>
        </View>
        """
        detector = AnswerTypeDetector(xml_config)
        result = detector.detect_answer_types()

        assert len(result) == 3
        types = [r['type'] for r in result]
        assert AnswerType.SINGLE_CHOICE.value in types
        assert AnswerType.RATING.value in types
        assert AnswerType.SHORT_TEXT.value in types


class TestAnswerTypeToMetrics:
    """Test the answer type to metrics mapping (NEW FLAT STRUCTURE)"""

    def test_all_answer_types_have_metrics(self):
        """Ensure all answer types have associated metrics as flat lists"""
        for answer_type in AnswerType:
            assert answer_type in ANSWER_TYPE_TO_METRICS
            metrics = ANSWER_TYPE_TO_METRICS[answer_type]
            # NEW: metrics should be a flat list, not a nested dict
            assert isinstance(
                metrics, list
            ), f"Expected list for {answer_type}, got {type(metrics)}"
            assert len(metrics) > 0, f"No metrics defined for {answer_type}"

    def test_binary_metrics(self):
        """Test metrics for binary answer type"""
        metrics = ANSWER_TYPE_TO_METRICS[AnswerType.BINARY]

        # Should be a flat list
        assert isinstance(metrics, list)

        # Should have classification metrics
        assert 'accuracy' in metrics
        assert 'precision' in metrics
        assert 'recall' in metrics
        assert 'f1' in metrics

        # Should have LLM judge metrics (classic and custom)
        assert 'llm_judge_classic' in metrics
        assert 'llm_judge_custom' in metrics

    def test_text_generation_metrics(self):
        """Test metrics for text generation answer types"""
        long_text_metrics = ANSWER_TYPE_TO_METRICS[AnswerType.LONG_TEXT]

        # Should be a flat list
        assert isinstance(long_text_metrics, list)

        # Should have text generation metrics
        assert 'bleu' in long_text_metrics
        assert 'rouge' in long_text_metrics
        assert 'bertscore' in long_text_metrics

        # Should have LLM judge metrics (classic and custom)
        assert 'llm_judge_classic' in long_text_metrics
        assert 'llm_judge_custom' in long_text_metrics

    def test_numeric_metrics(self):
        """Test metrics for numeric answer types"""
        numeric_metrics = ANSWER_TYPE_TO_METRICS[AnswerType.NUMERIC]

        # Should be a flat list
        assert isinstance(numeric_metrics, list)

        # Should have regression metrics
        assert 'mae' in numeric_metrics
        assert 'rmse' in numeric_metrics
        assert 'r2' in numeric_metrics

    def test_llm_judge_metrics_available_for_text_types(self):
        """Test that LLM judge metrics are available for text answer types"""
        # Short text should have LLM judge metrics
        short_text_metrics = ANSWER_TYPE_TO_METRICS[AnswerType.SHORT_TEXT]
        assert 'llm_judge_classic' in short_text_metrics
        assert 'llm_judge_custom' in short_text_metrics

        # Long text should have LLM judge metrics
        long_text_metrics = ANSWER_TYPE_TO_METRICS[AnswerType.LONG_TEXT]
        assert 'llm_judge_classic' in long_text_metrics
        assert 'llm_judge_custom' in long_text_metrics

    def test_span_selection_metrics(self):
        """Test metrics for span selection (NER) answer type.

        iou must be present (was missing before fix).
        token_f1 must NOT be present (stringifies JSON spans, produces garbage).
        """
        metrics = ANSWER_TYPE_TO_METRICS[AnswerType.SPAN_SELECTION]

        assert isinstance(metrics, list)

        # Must have span-specific metrics
        assert 'span_exact_match' in metrics
        assert 'iou' in metrics
        assert 'partial_match' in metrics
        assert 'boundary_accuracy' in metrics

        # Must NOT have token_f1 (broken for span data - it stringifies JSON)
        assert 'token_f1' not in metrics, (
            "token_f1 must not be in SPAN_SELECTION: it stringifies span JSON, producing meaningless scores"
        )

        # Should have LLM judge metrics
        assert 'llm_judge_classic' in metrics
        assert 'llm_judge_custom' in metrics

    def test_custom_answer_type_has_all_metrics(self):
        """Test that CUSTOM answer type includes all available metrics"""
        custom_metrics = ANSWER_TYPE_TO_METRICS[AnswerType.CUSTOM]

        # Should have LLM judge metrics (classic, custom)
        assert 'llm_judge_classic' in custom_metrics
        assert 'llm_judge_custom' in custom_metrics
        assert 'llm_judge_custom' in custom_metrics

        # Should have deterministic metrics
        assert 'bleu' in custom_metrics
        assert 'rouge' in custom_metrics
        assert 'exact_match' in custom_metrics
        assert 'accuracy' in custom_metrics


class TestGetAvailableMethodsForProject:
    """Test the get_available_methods_for_project function"""

    @patch('services.evaluation.config.AnswerTypeDetector')
    def test_get_methods_for_simple_config(self, mock_detector_class):
        """Test getting available methods for a simple configuration"""
        # Mock the detector
        mock_detector = Mock()
        mock_detector.detect_answer_types.return_value = [
            {
                'type': 'binary',
                'name': 'answer',
                'tag': 'Choices',
                'to_name': 'text',
                'element_attrs': {},
                'choices': ['Yes', 'No'],
            }
        ]
        mock_detector_class.return_value = mock_detector

        label_config = "<mock>config</mock>"
        result = get_available_methods_for_project(label_config)

        assert 'detected_answer_types' in result
        assert 'available_methods' in result
        assert len(result['detected_answer_types']) == 1
        assert 'answer' in result['available_methods']

        # Check that binary metrics are included
        answer_methods = result['available_methods']['answer']
        assert answer_methods['type'] == 'binary'
        assert 'accuracy' in answer_methods['available_metrics']
        assert 'cohen_kappa' in answer_methods['available_metrics']

    @patch('services.evaluation.config.AnswerTypeDetector')
    def test_get_methods_for_complex_config(self, mock_detector_class):
        """Test getting available methods for a complex configuration"""
        # Mock the detector with multiple answer types
        mock_detector = Mock()
        mock_detector.detect_answer_types.return_value = [
            {
                'type': 'single_choice',
                'name': 'category',
                'tag': 'Choices',
                'to_name': 'text',
                'element_attrs': {},
                'choices': ['A', 'B', 'C'],
            },
            {
                'type': 'rating',
                'name': 'quality',
                'tag': 'Rating',
                'to_name': 'text',
                'element_attrs': {'maxRating': '5'},
            },
            {
                'type': 'long_text',
                'name': 'analysis',
                'tag': 'TextArea',
                'to_name': 'text',
                'element_attrs': {'rows': '10'},
            },
        ]
        mock_detector_class.return_value = mock_detector

        label_config = "<mock>complex config</mock>"
        result = get_available_methods_for_project(label_config)

        assert len(result['detected_answer_types']) == 3
        assert 'category' in result['available_methods']
        assert 'quality' in result['available_methods']
        assert 'analysis' in result['available_methods']

        # Check specific metrics for each type
        category_methods = result['available_methods']['category']
        assert 'accuracy' in category_methods['available_metrics']

        quality_methods = result['available_methods']['quality']
        assert 'mae' in quality_methods['available_metrics']

        analysis_methods = result['available_methods']['analysis']
        assert 'bleu' in analysis_methods['available_metrics']
        assert 'rouge' in analysis_methods['available_metrics']

    def test_empty_label_config(self):
        """Test handling of empty label configuration"""
        result = get_available_methods_for_project("")

        assert result['detected_answer_types'] == []
        assert result['available_methods'] == {}

    def test_invalid_xml_config(self):
        """Test handling of invalid XML configuration"""
        invalid_xml = "<invalid>not closed properly"

        # Should not raise an exception, but return empty results
        result = get_available_methods_for_project(invalid_xml)

        assert result['detected_answer_types'] == []
        assert result['available_methods'] == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
