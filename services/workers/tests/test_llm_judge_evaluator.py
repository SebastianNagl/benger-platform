"""
Tests for LLM-as-Judge Evaluator.

These tests verify:
1. Prompt construction follows expected format
2. Response parsing correctly extracts scores
3. Criteria definitions are complete
4. Pairwise comparison works correctly
5. Multi-judge consensus evaluation

NOTE: These tests do NOT call actual LLMs. They verify the prompt/response handling logic
using mocked AI service responses.
"""

import os
import sys
from unittest.mock import MagicMock

# Add path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml_evaluation.llm_judge_evaluator import (
    DEFAULT_CRITERIA,
    PAIRWISE_COMPARISON_PROMPT,
    SINGLE_EVALUATION_PROMPT,
    LLMJudgeEvaluator,
)


class TestLLMJudgePromptConstruction:
    """Test that LLM judge prompts are constructed correctly."""

    def test_prompt_template_contains_required_variables(self):
        """Test that the prompt template contains all required placeholders."""
        required_vars = [
            "{context}",
            "{ground_truth}",
            "{prediction}",
            "{criterion_name}",
            "{criterion_description}",
            "{rubric}",
        ]
        for var in required_vars:
            assert var in SINGLE_EVALUATION_PROMPT, f"Prompt should contain {var}"

    def test_prompt_requests_json_format(self):
        """Test that prompt requests JSON formatted response."""
        assert "JSON" in SINGLE_EVALUATION_PROMPT or "json" in SINGLE_EVALUATION_PROMPT
        assert '"score"' in SINGLE_EVALUATION_PROMPT

    def test_pairwise_prompt_contains_both_responses(self):
        """Test that pairwise prompt template includes both responses."""
        assert "{response_a}" in PAIRWISE_COMPARISON_PROMPT
        assert "{response_b}" in PAIRWISE_COMPARISON_PROMPT
        assert "{ground_truth}" in PAIRWISE_COMPARISON_PROMPT


class TestLLMJudgeResponseParsing:
    """Test that LLM judge responses are parsed correctly."""

    def setup_method(self):
        """Set up test evaluator."""
        self.evaluator = LLMJudgeEvaluator(
            ai_service=MagicMock(),
            judge_model="test-model",
            criteria=["helpfulness"],
        )

    def test_parse_valid_json_response(self):
        """Test parsing a valid JSON response."""
        response = '{"score": 4, "justification": "Good response"}'
        result = self.evaluator._parse_evaluation_response(response)

        assert result is not None
        assert result["score"] == 4
        assert result["justification"] == "Good response"

    def test_parse_json_in_markdown_block(self):
        """Test parsing JSON wrapped in markdown code block."""
        response = """Here is my evaluation:

```json
{"score": 5, "justification": "Excellent"}
```
"""
        result = self.evaluator._parse_evaluation_response(response)

        assert result is not None
        assert result["score"] == 5

    def test_parse_json_without_lang_tag(self):
        """Test parsing JSON in code block without language tag."""
        response = """
```
{"score": 3, "justification": "Average"}
```
"""
        result = self.evaluator._parse_evaluation_response(response)

        assert result is not None
        assert result["score"] == 3

    def test_parse_embedded_json(self):
        """Test parsing JSON embedded in text."""
        response = 'Based on analysis, the score is {"score": 4, "justification": "test"} as shown.'
        result = self.evaluator._parse_evaluation_response(response)

        assert result is not None
        assert result["score"] == 4

    def test_parse_pairwise_preference(self):
        """Test parsing pairwise comparison preference."""
        response = '{"preference": "A", "justification": "Response A is better"}'
        result = self.evaluator._parse_evaluation_response(response)

        assert result is not None
        assert result["preference"] == "A"

    def test_parse_invalid_response_returns_none(self):
        """Test that invalid responses return None."""
        response = "This response doesn't contain any JSON or score."
        result = self.evaluator._parse_evaluation_response(response)

        assert result is None


class TestLLMJudgeCriteriaDefinitions:
    """Test that all criteria are properly defined."""

    def test_helpfulness_criteria_defined(self):
        """Test that helpfulness criteria is defined with required fields."""
        assert "helpfulness" in DEFAULT_CRITERIA
        criteria = DEFAULT_CRITERIA["helpfulness"]
        assert "name" in criteria
        assert "description" in criteria
        assert "rubric" in criteria
        assert "help" in criteria["description"].lower()

    def test_correctness_criteria_defined(self):
        """Test that correctness criteria is defined."""
        assert "correctness" in DEFAULT_CRITERIA
        criteria = DEFAULT_CRITERIA["correctness"]
        assert "name" in criteria
        assert "rubric" in criteria
        assert any(
            word in criteria["description"].lower() for word in ["correct", "accura", "factual"]
        )

    def test_fluency_criteria_defined(self):
        """Test that fluency criteria is defined."""
        assert "fluency" in DEFAULT_CRITERIA
        criteria = DEFAULT_CRITERIA["fluency"]
        assert "rubric" in criteria

    def test_coherence_criteria_defined(self):
        """Test that coherence criteria is defined."""
        assert "coherence" in DEFAULT_CRITERIA
        criteria = DEFAULT_CRITERIA["coherence"]
        assert "rubric" in criteria

    def test_relevance_criteria_defined(self):
        """Test that relevance criteria is defined."""
        assert "relevance" in DEFAULT_CRITERIA
        criteria = DEFAULT_CRITERIA["relevance"]
        assert "rubric" in criteria

    def test_safety_criteria_defined(self):
        """Test that safety criteria is defined."""
        assert "safety" in DEFAULT_CRITERIA
        criteria = DEFAULT_CRITERIA["safety"]
        assert "rubric" in criteria

    def test_accuracy_criteria_defined(self):
        """Test that accuracy criteria is defined."""
        assert "accuracy" in DEFAULT_CRITERIA
        criteria = DEFAULT_CRITERIA["accuracy"]
        assert "rubric" in criteria
        assert "accurate" in criteria["description"].lower()

    def test_all_criteria_have_required_fields(self):
        """Test that all criteria have name, description, and rubric."""
        for criterion_id, criterion in DEFAULT_CRITERIA.items():
            assert "name" in criterion, f"{criterion_id} missing name"
            assert "description" in criterion, f"{criterion_id} missing description"
            assert "rubric" in criterion, f"{criterion_id} missing rubric"


class TestLLMJudgeSingleEvaluation:
    """Test single sample evaluation with mocked LLM calls."""

    def setup_method(self):
        """Set up test evaluator with mocked AI service."""
        self.mock_ai_service = MagicMock()
        self.evaluator = LLMJudgeEvaluator(
            ai_service=self.mock_ai_service,
            judge_model="test-model",
            criteria=["helpfulness", "correctness"],
        )

    def test_evaluate_single_criterion_success(self):
        """Test successful single criterion evaluation."""
        self.mock_ai_service.generate.return_value = {
            "success": True,
            "content": '{"score": 4, "justification": "Good response"}',
        }

        score = self.evaluator._evaluate_single_criterion(
            context="Test context",
            ground_truth="Expected answer",
            prediction="Model response",
            criterion="helpfulness",
        )

        assert score["score"] == 4.0
        self.mock_ai_service.generate.assert_called_once()

    def test_evaluate_single_criterion_clamps_score(self):
        """Test that scores are clamped to valid range."""
        # Score too high
        self.mock_ai_service.generate.return_value = {
            "success": True,
            "content": '{"score": 10, "justification": "Invalid high score"}',
        }

        score = self.evaluator._evaluate_single_criterion(
            context="Test",
            ground_truth="Test",
            prediction="Test",
            criterion="helpfulness",
        )

        assert score["score"] == 5.0  # Clamped to max

    def test_evaluate_single_criterion_handles_failure(self):
        """Test handling of failed LLM call."""
        self.mock_ai_service.generate.return_value = {
            "success": False,
            "error": "API error",
        }

        score = self.evaluator._evaluate_single_criterion(
            context="Test",
            ground_truth="Test",
            prediction="Test",
            criterion="helpfulness",
        )

        assert score is None


class TestLLMJudgePairwiseComparison:
    """Test pairwise comparison functionality."""

    def setup_method(self):
        """Set up test evaluator with mocked AI service."""
        self.mock_ai_service = MagicMock()
        self.evaluator = LLMJudgeEvaluator(
            ai_service=self.mock_ai_service,
            judge_model="test-model",
        )

    def test_pairwise_returns_preference_a(self):
        """Test pairwise comparison returns preference A."""
        self.mock_ai_service.generate.return_value = {
            "success": True,
            "content": '{"preference": "A", "justification": "Response A is better"}',
        }

        result = self.evaluator.evaluate_pairwise(
            context="Test question",
            ground_truth="Expected answer",
            response_a="First response",
            response_b="Second response",
            criterion="helpfulness",
        )

        assert result["preference"] == "A"
        assert "justification" in result

    def test_pairwise_returns_preference_b(self):
        """Test pairwise comparison returns preference B."""
        self.mock_ai_service.generate.return_value = {
            "success": True,
            "content": '{"preference": "b", "justification": "B is better"}',
        }

        result = self.evaluator.evaluate_pairwise(
            context="Test",
            ground_truth="Test",
            response_a="A",
            response_b="B",
            criterion="correctness",
        )

        assert result["preference"] == "B"  # Uppercase

    def test_pairwise_returns_tie(self):
        """Test pairwise comparison returns tie."""
        self.mock_ai_service.generate.return_value = {
            "success": True,
            "content": '{"preference": "tie", "justification": "Both are equal"}',
        }

        result = self.evaluator.evaluate_pairwise(
            context="Test",
            ground_truth="Test",
            response_a="A",
            response_b="B",
            criterion="fluency",
        )

        assert result["preference"] == "TIE"

    def test_pairwise_handles_failure(self):
        """Test pairwise comparison handles failure gracefully."""
        self.mock_ai_service.generate.return_value = {
            "success": False,
            "error": "API error",
        }

        result = self.evaluator.evaluate_pairwise(
            context="Test",
            ground_truth="Test",
            response_a="A",
            response_b="B",
            criterion="helpfulness",
        )

        assert result["preference"] == "TIE"  # Default on failure


class TestLLMJudgeMultiJudge:
    """Test multi-judge consensus evaluation."""

    def setup_method(self):
        """Set up test evaluator with mocked AI service."""
        self.mock_ai_service = MagicMock()
        self.evaluator = LLMJudgeEvaluator(
            ai_service=self.mock_ai_service,
            judge_model="primary-model",
            criteria=["helpfulness"],
        )

    def test_multi_judge_aggregates_scores(self):
        """Test that multi-judge aggregates scores from multiple judges."""
        # Primary judge returns 4
        self.mock_ai_service.generate.return_value = {
            "success": True,
            "content": '{"score": 4, "justification": "Good"}',
        }

        # Create additional judge configs
        additional_judges = [
            {"ai_service": MagicMock(), "model_name": "judge-2"},
            {"ai_service": MagicMock(), "model_name": "judge-3"},
        ]

        # Second judge returns 3
        additional_judges[0]["ai_service"].generate.return_value = {
            "success": True,
            "content": '{"score": 3, "justification": "Average"}',
        }

        # Third judge returns 5
        additional_judges[1]["ai_service"].generate.return_value = {
            "success": True,
            "content": '{"score": 5, "justification": "Excellent"}',
        }

        result = self.evaluator.evaluate_multi_judge(
            context="Test question",
            ground_truth="Expected answer",
            prediction="Model response",
            criteria=["helpfulness"],
            additional_judge_configs=additional_judges,
        )

        assert "scores_by_judge" in result
        assert "consensus_scores" in result
        assert "confidence_intervals" in result
        assert "inter_judge_agreement" in result

        # Consensus is average of normalized scores: (4-1)/4=0.75, (3-1)/4=0.5, (5-1)/4=1.0
        # Average = (0.75 + 0.5 + 1.0) / 3 = 0.75
        assert result["consensus_scores"]["helpfulness"] == 0.75

    def test_multi_judge_calculates_confidence_intervals(self):
        """Test that multi-judge calculates confidence intervals."""
        self.mock_ai_service.generate.return_value = {
            "success": True,
            "content": '{"score": 4, "justification": "Good"}',
        }

        additional_judges = [
            {"ai_service": MagicMock(), "model_name": "judge-2"},
        ]
        additional_judges[0]["ai_service"].generate.return_value = {
            "success": True,
            "content": '{"score": 4, "justification": "Good"}',
        }

        result = self.evaluator.evaluate_multi_judge(
            context="Test",
            ground_truth="Test",
            prediction="Test",
            criteria=["helpfulness"],
            additional_judge_configs=additional_judges,
        )

        assert "confidence_intervals" in result
        ci = result["confidence_intervals"]["helpfulness"]
        assert isinstance(ci, tuple)
        assert len(ci) == 2
        assert ci[0] <= ci[1]


class TestLLMJudgeCustomPrompt:
    """Test custom prompt template support."""

    def test_custom_prompt_template_used(self):
        """Test that custom prompt template is used when provided."""
        custom_template = (
            "Evaluate {candidate} against {reference} for {criterion_name}. Return JSON with score."
        )

        mock_ai_service = MagicMock()
        mock_ai_service.generate.return_value = {
            "success": True,
            "content": '{"score": 4}',
        }

        evaluator = LLMJudgeEvaluator(
            ai_service=mock_ai_service,
            judge_model="test-model",
            custom_prompt_template=custom_template,
        )

        evaluator._evaluate_single_criterion(
            context="Test",
            ground_truth="Expected",
            prediction="Actual",
            criterion="helpfulness",
        )

        # Check that the custom template was used
        call_args = mock_ai_service.generate.call_args
        prompt = call_args.kwargs.get("prompt") or call_args[1].get("prompt") or call_args[0][0]

        # The prompt should contain "Evaluate" from custom template, not default
        assert "Evaluate Actual against Expected" in prompt


class TestLLMJudgeCustomCriteria:
    """Test custom criteria support."""

    def test_custom_criteria_merged(self):
        """Test that custom criteria is merged with defaults."""
        custom_criteria = {
            "legal_german": {
                "name": "German Legal Accuracy",
                "description": "Accuracy for German law",
                "rubric": "1-5 scale for German legal accuracy",
            }
        }

        evaluator = LLMJudgeEvaluator(
            ai_service=MagicMock(),
            judge_model="test-model",
            custom_criteria=custom_criteria,
        )

        assert "legal_german" in evaluator.all_criteria
        assert "helpfulness" in evaluator.all_criteria  # Default still present

    def test_custom_criteria_appears_in_supported_metrics(self):
        """Test that custom criteria appears in supported metrics."""
        custom_criteria = {
            "my_custom": {
                "name": "My Custom Criterion",
                "description": "Custom evaluation",
                "rubric": "Custom rubric",
            }
        }

        evaluator = LLMJudgeEvaluator(
            ai_service=MagicMock(),
            judge_model="test-model",
            custom_criteria=custom_criteria,
        )

        supported = evaluator.get_supported_metrics()
        assert "llm_judge_my_custom" in supported


class TestLLMJudgeNoActualCalls:
    """Verify tests don't make actual LLM API calls."""

    def test_mock_prevents_actual_calls(self):
        """Verify that mocking prevents actual API calls."""
        mock_ai_service = MagicMock()
        mock_ai_service.generate.return_value = {
            "success": True,
            "content": '{"score": 4, "justification": "Test"}',
        }

        evaluator = LLMJudgeEvaluator(
            ai_service=mock_ai_service,
            judge_model="test-model",
        )

        score = evaluator._evaluate_single_criterion(
            context="Test context",
            ground_truth="Expected",
            prediction="Actual",
            criterion="helpfulness",
        )

        # Verify mock was called, not real API
        assert mock_ai_service.generate.called
        assert score["score"] == 4.0


class TestLLMJudgeThinkingParameters:
    """Test thinking_budget and reasoning_effort parameter passing.

    These tests verify that extended thinking parameters are correctly:
    1. Stored in the evaluator instance
    2. Passed through to the AI service generate() calls
    """

    def test_thinking_budget_stored_in_evaluator(self):
        """Verify thinking_budget is stored in evaluator instance."""
        mock_ai_service = MagicMock()
        evaluator = LLMJudgeEvaluator(
            ai_service=mock_ai_service,
            judge_model="claude-3-7-sonnet",
            thinking_budget=16000,
        )

        assert evaluator.thinking_budget == 16000

    def test_reasoning_effort_stored_in_evaluator(self):
        """Verify reasoning_effort is stored in evaluator instance."""
        mock_ai_service = MagicMock()
        evaluator = LLMJudgeEvaluator(
            ai_service=mock_ai_service,
            judge_model="o3-mini",
            reasoning_effort="high",
        )

        assert evaluator.reasoning_effort == "high"

    def test_thinking_budget_passed_to_ai_service(self):
        """Verify thinking_budget is passed to AI service generate call."""
        mock_ai_service = MagicMock()
        mock_ai_service.generate.return_value = {
            "success": True,
            "content": '{"score": 4, "justification": "Good response"}',
        }

        evaluator = LLMJudgeEvaluator(
            ai_service=mock_ai_service,
            judge_model="claude-3-7-sonnet",
            criteria=["helpfulness"],
            thinking_budget=16000,
        )

        evaluator._evaluate_single_criterion(
            context="test context",
            ground_truth="expected answer",
            prediction="actual response",
            criterion="helpfulness",
        )

        # Verify thinking_budget was passed to generate()
        call_kwargs = mock_ai_service.generate.call_args.kwargs
        assert call_kwargs.get("thinking_budget") == 16000

    def test_reasoning_effort_passed_to_ai_service(self):
        """Verify reasoning_effort is passed to AI service for OpenAI o-series."""
        mock_ai_service = MagicMock()
        mock_ai_service.generate.return_value = {
            "success": True,
            "content": '{"score": 4, "justification": "Good response"}',
        }

        evaluator = LLMJudgeEvaluator(
            ai_service=mock_ai_service,
            judge_model="o3-mini",
            criteria=["helpfulness"],
            reasoning_effort="high",
        )

        evaluator._evaluate_single_criterion(
            context="test context",
            ground_truth="expected answer",
            prediction="actual response",
            criterion="helpfulness",
        )

        # Verify reasoning_effort was passed to generate()
        call_kwargs = mock_ai_service.generate.call_args.kwargs
        assert call_kwargs.get("reasoning_effort") == "high"

    def test_thinking_budget_not_passed_when_none(self):
        """Verify thinking_budget is not passed when not set."""
        mock_ai_service = MagicMock()
        mock_ai_service.generate.return_value = {
            "success": True,
            "content": '{"score": 4, "justification": "Good"}',
        }

        evaluator = LLMJudgeEvaluator(
            ai_service=mock_ai_service,
            judge_model="gpt-4o",
            criteria=["helpfulness"],
            # No thinking_budget set
        )

        evaluator._evaluate_single_criterion(
            context="test",
            ground_truth="expected",
            prediction="actual",
            criterion="helpfulness",
        )

        call_kwargs = mock_ai_service.generate.call_args.kwargs
        # thinking_budget should not be in kwargs or should be None
        assert call_kwargs.get("thinking_budget") is None

    def test_reasoning_effort_not_passed_when_none(self):
        """Verify reasoning_effort is not passed when not set."""
        mock_ai_service = MagicMock()
        mock_ai_service.generate.return_value = {
            "success": True,
            "content": '{"score": 4, "justification": "Good"}',
        }

        evaluator = LLMJudgeEvaluator(
            ai_service=mock_ai_service,
            judge_model="gpt-4o",
            criteria=["helpfulness"],
            # No reasoning_effort set
        )

        evaluator._evaluate_single_criterion(
            context="test",
            ground_truth="expected",
            prediction="actual",
            criterion="helpfulness",
        )

        call_kwargs = mock_ai_service.generate.call_args.kwargs
        # reasoning_effort should not be in kwargs or should be None
        assert call_kwargs.get("reasoning_effort") is None

    def test_both_thinking_params_passed_together(self):
        """Verify both thinking_budget and reasoning_effort can be passed."""
        mock_ai_service = MagicMock()
        mock_ai_service.generate.return_value = {
            "success": True,
            "content": '{"score": 4, "justification": "Good"}',
        }

        evaluator = LLMJudgeEvaluator(
            ai_service=mock_ai_service,
            judge_model="test-model",
            criteria=["helpfulness"],
            thinking_budget=8000,
            reasoning_effort="medium",
        )

        evaluator._evaluate_single_criterion(
            context="test",
            ground_truth="expected",
            prediction="actual",
            criterion="helpfulness",
        )

        call_kwargs = mock_ai_service.generate.call_args.kwargs
        assert call_kwargs.get("thinking_budget") == 8000
        assert call_kwargs.get("reasoning_effort") == "medium"

    def test_temperature_passed_to_ai_service(self):
        """Verify temperature is passed to AI service generate call."""
        mock_ai_service = MagicMock()
        mock_ai_service.generate.return_value = {
            "success": True,
            "content": '{"score": 4, "justification": "Good"}',
        }

        evaluator = LLMJudgeEvaluator(
            ai_service=mock_ai_service,
            judge_model="gpt-4o",
            criteria=["helpfulness"],
            temperature=0.3,
        )

        evaluator._evaluate_single_criterion(
            context="test",
            ground_truth="expected",
            prediction="actual",
            criterion="helpfulness",
        )

        call_kwargs = mock_ai_service.generate.call_args.kwargs
        assert call_kwargs.get("temperature") == 0.3
