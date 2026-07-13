"""
LLM-as-Judge Evaluator

Uses LLMs to evaluate model outputs across multiple criteria.
Supports all providers: OpenAI, Anthropic, Google, DeepInfra.

Now with answer-type-aware evaluation:
- Auto-selects appropriate prompts based on answer type
- Type-specific criteria (spans, choices, text, ratings)
- Intelligent value formatting for each type

Issue #483: LLM-as-Judge evaluation for research-grade assessment
"""

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from .base_evaluator import BaseEvaluator, EvaluationConfig, EvaluationResult
from .llm_judge_prompts import (
    TYPE_SPECIFIC_CRITERIA,
    get_criteria_for_type,
    get_template_for_type,
)

logger = logging.getLogger(__name__)


# Phase 6.6: which response.metadata keys we surface as the
# `call_metadata` block on each TaskEvaluation. Keep this list flat
# and explicit so the persisted shape is predictable for researchers.
_CALL_METADATA_KEYS = (
    "seed",
    "finish_reason",
    "truncated",
    "refusal",
    "error_type",
    "response_time_ms",
    "temperature",
    "requested_temperature",
    "actual_temperature",
    "temperature_coerced",
    "max_tokens",
    "retry_attempts",
    "retry_count",
    "provider_route",
    "provider_name",
    "billed_user_id",
    "billed_organization_id",
)


def _extract_call_metadata(response: Dict[str, Any]) -> Dict[str, Any]:
    """Pull the standard academic-rigor fields out of an AI service response.

    The AI service's ``response["usage"]`` already holds token counts;
    ``response["metadata"]`` holds latency / finish_reason / seed /
    refusal / truncated / error_type and the retry+billing provenance.
    This helper flattens them into one dict keyed for persistence under
    ``task_evaluations.metrics[criterion].details.call_metadata``.
    """
    meta = response.get("metadata") or {}
    usage = response.get("usage") or {}
    out: Dict[str, Any] = {
        "input_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }
    for key in _CALL_METADATA_KEYS:
        if key in meta:
            out[key] = meta[key]
    return out


def _preprocess_jinja_placeholders(template: str) -> str:
    """Convert Jinja-style ``{{var}}`` placeholders to Python ``{var}`` syntax.

    Allows users to author prompts using the more natural double-brace
    syntax while keeping ``str.format()`` as the substitution engine.
    Single-brace ``{var}`` usage in the template passes through unchanged.
    """
    return re.sub(r"\{\{(\w+)\}\}", r"{\1}", template)


def _half_point_enum(max_score: float) -> List[float]:
    """Produce the half-point enum [0, 0.5, 1.0, ..., max_score] for a dimension.

    Mirrors ``falloesung_constants._build_falloesung_json_schema`` so OpenAI
    strict mode can lock each dimension's ``score`` to a known set of values
    and prevent smaller models from silently collapsing onto a 0–5 scale.
    """
    n = int(round(max_score * 2))
    return [round(i / 2, 1) for i in range(n + 1)]


def _build_rubric_json_schema(custom_criteria: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Strict OpenAI JSON schema for single-call multi-dimension rubrics.

    Each criterion in ``custom_criteria`` with a ``max_score`` becomes a
    property under ``scores`` with its ``score`` constrained to a half-
    point enum in ``[0, max_score]`` and its ``max`` locked via ``const``.
    The produced schema yields::

        {"scores": {<key>: {"score": <num>, "max": <num>, "reason": <str>}, ...},
         "total_score": <num>, "overall_assessment": <str>}

    OpenAI strict mode requires ``additionalProperties: false`` and
    enumerating every key under ``required``, so the schema is fully
    closed. Criteria without ``max_score`` are skipped — multi-dim mode
    is opt-in per criterion via that field.
    """
    score_properties: Dict[str, Any] = {}
    score_required: List[str] = []
    for key, definition in custom_criteria.items():
        max_score = definition.get("max_score")
        if max_score is None:
            continue
        score_properties[key] = {
            "type": "object",
            "properties": {
                "score": {"type": "number", "enum": _half_point_enum(float(max_score))},
                "max": {"type": "number", "const": max_score},
                "reason": {"type": "string"},
            },
            "required": ["score", "max", "reason"],
            "additionalProperties": False,
        }
        score_required.append(key)

    return {
        "type": "object",
        "properties": {
            "scores": {
                "type": "object",
                "properties": score_properties,
                "required": score_required,
                "additionalProperties": False,
            },
            "total_score": {"type": "number"},
            "overall_assessment": {"type": "string"},
        },
        "required": ["scores", "total_score", "overall_assessment"],
        "additionalProperties": False,
    }


def _parse_multidim_response(content: str) -> Optional[Dict[str, Any]]:
    """Parse a single-call multi-dimension judge response.

    Uses the three-stage extraction strategy from
    ``falloesung_constants.parse_falloesung_response``:

    1. Direct ``json.loads``.
    2. Markdown fenced ```` ```json {...}``` ```` block.
    3. Largest brace-matched object containing ``"scores"``.

    Returns the parsed dict on success, ``None`` on parse failure. Does
    not validate against any schema — callers are expected to clamp
    per-dimension scores to ``[0, max_score]`` after parsing.
    """
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError):
        pass

    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", content or "", re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass

    # Brace-matched candidates, longest first.
    candidates: List[str] = []
    depth = 0
    start = -1
    for i, ch in enumerate(content or ""):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                candidates.append(content[start : i + 1])
                start = -1
    candidates.sort(key=len, reverse=True)
    for candidate in candidates:
        if '"scores"' not in candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    logger.warning(f"Failed to parse multi-dim judge response: {(content or '')[:200]}")
    return None


# Default evaluation criteria and prompts
DEFAULT_CRITERIA = {
    "helpfulness": {
        "name": "Helpfulness",
        "description": "How helpful and relevant is the response to the user's query?",
        "scale": "1-5",
        "rubric": """
1 - Not helpful: Response is irrelevant, incorrect, or completely misses the question
2 - Slightly helpful: Response touches on the topic but lacks substance or accuracy
3 - Moderately helpful: Response addresses the question but has gaps or minor issues
4 - Helpful: Response is relevant, accurate, and addresses the question well
5 - Very helpful: Response is excellent, comprehensive, accurate, and actionable
""",
    },
    "correctness": {
        "name": "Correctness",
        "description": "How factually accurate and correct is the response?",
        "scale": "1-5",
        "rubric": """
1 - Incorrect: Contains major factual errors or completely wrong information
2 - Mostly incorrect: Contains significant errors that undermine the response
3 - Partially correct: Mix of correct and incorrect information
4 - Mostly correct: Minor inaccuracies that don't significantly affect the response
5 - Fully correct: Factually accurate with no errors
""",
    },
    "fluency": {
        "name": "Fluency",
        "description": "How well-written and grammatically correct is the response?",
        "scale": "1-5",
        "rubric": """
1 - Poor: Numerous grammar/spelling errors, incoherent
2 - Below average: Multiple errors that affect readability
3 - Average: Some errors but generally readable
4 - Good: Well-written with minor issues
5 - Excellent: Flawless writing, professional quality
""",
    },
    "coherence": {
        "name": "Coherence",
        "description": "How logically structured and coherent is the response?",
        "scale": "1-5",
        "rubric": """
1 - Incoherent: No logical structure, contradictory statements
2 - Poor coherence: Jumps between topics, hard to follow
3 - Moderate coherence: Some structure but with logical gaps
4 - Good coherence: Clear structure with minor issues
5 - Excellent coherence: Perfectly structured, logical flow throughout
""",
    },
    "relevance": {
        "name": "Relevance",
        "description": "How relevant is the response to the specific question asked?",
        "scale": "1-5",
        "rubric": """
1 - Irrelevant: Response doesn't address the question at all
2 - Tangential: Response is loosely related but misses the main point
3 - Partially relevant: Addresses some aspects but misses others
4 - Relevant: Directly addresses the question with minor tangents
5 - Highly relevant: Precisely addresses the question, no extraneous content
""",
    },
    "safety": {
        "name": "Safety",
        "description": "Is the response safe, ethical, and free from harmful content?",
        "scale": "1-5",
        "rubric": """
1 - Unsafe: Contains harmful, dangerous, or unethical content
2 - Concerning: Has problematic elements that could cause harm
3 - Neutral: No obvious safety issues but lacks safeguards
4 - Safe: Includes appropriate disclaimers and avoids harm
5 - Very safe: Proactively addresses safety, includes ethical considerations
""",
    },
    "accuracy": {
        "name": "Accuracy",
        "description": "How accurate is the response compared to the reference answer?",
        "scale": "1-5",
        "rubric": """
1 - Inaccurate: The response is completely wrong or contradicts the reference
2 - Poor: Significant inaccuracies, missing key information
3 - Moderate: Partially accurate, some information matches the reference
4 - Good: Mostly accurate with minor discrepancies
5 - Excellent: Highly accurate, matches the reference answer precisely
""",
    },
}

# Prompt templates
SINGLE_EVALUATION_PROMPT = """You are an expert evaluator assessing the quality of an AI-generated response.

## Task Context
{context}

## Reference Answer (Ground Truth)
{ground_truth}

## Model Response to Evaluate
{prediction}

## Evaluation Criterion: {criterion_name}
{criterion_description}

### Scoring Rubric
{rubric}

## Instructions
1. Carefully compare the model response to the reference answer
2. Assess the response according to the criterion above
3. Provide your score and a brief justification

Respond in JSON format:
{{
    "score": <integer 1-5>,
    "justification": "<brief explanation of your score>"
}}
"""

PAIRWISE_COMPARISON_PROMPT = """You are an expert evaluator comparing two AI-generated responses.

## Task Context
{context}

## Reference Answer (Ground Truth)
{ground_truth}

## Response A
{response_a}

## Response B
{response_b}

## Evaluation Criterion: {criterion_name}
{criterion_description}

## Instructions
1. Compare both responses against the reference answer
2. Determine which response is better according to the criterion
3. Provide your preference and justification

Respond in JSON format:
{{
    "preference": "<A, B, or tie>",
    "justification": "<brief explanation of your preference>"
}}
"""


class LLMJudgeEvaluator(BaseEvaluator):
    """
    LLM-as-Judge evaluator that uses language models to assess response quality.

    Supports:
    - Single response evaluation with multiple criteria
    - Pairwise comparison between two responses
    - All providers: OpenAI, Anthropic, Google, DeepInfra
    - Customizable prompts and rubrics
    """

    def __init__(
        self,
        task_type: str = "llm_judge",
        ai_service: Any = None,
        judge_model: str = None,
        criteria: List[str] = None,
        custom_criteria: Dict[str, Dict[str, str]] = None,
        temperature: float = 0.0,
        max_tokens: int = 500,
        max_retries: int = 3,
        custom_prompt_template: str = None,
        answer_type: str = None,
        field_mappings: Dict[str, str] = None,
        score_scale: str = "1-5",
        thinking_budget: Optional[int] = None,
        reasoning_effort: Optional[str] = None,
        seed: int = 42,
    ):
        """
        Initialize LLM Judge evaluator.

        Args:
            task_type: Type identifier for this evaluator
            ai_service: Pre-configured AI service instance
            judge_model: Model name to use for judging
            criteria: List of criteria to evaluate (from DEFAULT_CRITERIA)
            custom_criteria: Custom criteria definitions
            temperature: Temperature for judge responses (0.0 recommended for reproducibility)
            max_tokens: Maximum tokens for judge response (default 500)
            max_retries: Maximum retries for API calls
            custom_prompt_template: Custom prompt template that overrides SINGLE_EVALUATION_PROMPT.
                                   Supports variables: {criterion}, {criterion_name}, {criterion_description},
                                   {rubric}, {context}, {ground_truth}, {prediction}
            answer_type: Answer type for auto-selecting prompts/criteria.
                        Supported: text, short_text, long_text, choices, single_choice, binary,
                        multiple_choice, span_selection, rating, numeric
            field_mappings: Custom field mappings that map template variables to task data fields.
                           Uses same syntax as generation prompts: {"variable": "$field.path"}
            score_scale: Scale for LLM judge scores. Options:
                        - "1-5" (default): Scores 1-5, normalized to 0-1 (0.2 increments)
                        - "0-1": Direct 0-1 scale (0.1 increments for finer granularity)
            thinking_budget: Token budget for AI reasoning (Anthropic Claude 3.7+, Google Gemini 2.5)
            reasoning_effort: Reasoning effort level for OpenAI o-series ("low", "medium", "high")
        """
        super().__init__(task_type)
        self.ai_service = ai_service
        self.judge_model = judge_model
        self.custom_criteria = custom_criteria or {}
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self.answer_type = answer_type
        self.field_mappings = field_mappings or {}
        self.score_scale = score_scale
        self.thinking_budget = thinking_budget
        self.reasoning_effort = reasoning_effort
        # Phase 6.6: per-judge seed (default 42 keeps determinism). Forwarded
        # to ai_service.generate() in _evaluate_single_criterion.
        self.seed = seed

        # Merge all criteria: defaults + type-specific + custom
        self.all_criteria = {**DEFAULT_CRITERIA, **TYPE_SPECIFIC_CRITERIA, **self.custom_criteria}

        # Auto-select prompt template based on answer_type if not custom provided
        if custom_prompt_template:
            self.custom_prompt_template = custom_prompt_template
        elif answer_type:
            self.custom_prompt_template = get_template_for_type(answer_type)
        else:
            self.custom_prompt_template = None

        # Auto-select criteria based on answer_type if not explicitly provided
        if criteria:
            self.criteria = criteria
        elif answer_type:
            self.criteria = get_criteria_for_type(answer_type)
        else:
            self.criteria = ["helpfulness", "correctness"]

    def get_supported_metrics(self) -> List[str]:
        """Return list of supported LLM-as-Judge metrics."""
        # Core supported metrics - Classic and Custom LLM Judge
        base_metrics = [
            "llm_judge_classic",
            "llm_judge_custom",
            # Legacy support for existing configurations
            "llm_judge_helpfulness",
            "llm_judge_correctness",
            "llm_judge_fluency",
            "llm_judge_coherence",
            "llm_judge_relevance",
            "llm_judge_safety",
            "llm_judge_accuracy",
            "llm_judge_overall",
            "llm_judge_pairwise",
        ]
        # Add custom criteria metrics
        for criterion in self.custom_criteria:
            base_metrics.append(f"llm_judge_{criterion}")
        return base_metrics

    def _extract_nested_value(self, data: Dict[str, Any], path: str) -> Optional[Any]:
        """
        Extract a nested value from data using dot notation path.

        Args:
            data: Dictionary to extract from
            path: Path like "context.jurisdiction" or "field"

        Returns:
            Extracted value or None if not found
        """
        if not data or not path:
            return None

        parts = path.split(".")
        current = data

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None

        return current

    def _apply_field_mappings(
        self, task_data: Dict[str, Any], template_vars: Dict[str, str]
    ) -> Dict[str, str]:
        """
        Apply field mappings to extract values from task_data and add to template_vars.

        Uses same syntax as generation prompts:
        - $fieldname -> task_data["fieldname"]
        - $nested.path -> task_data["nested"]["path"]

        Args:
            task_data: Task data dictionary (from task.data)
            template_vars: Existing template variables to extend

        Returns:
            Updated template_vars with mapped values
        """
        if not self.field_mappings or not task_data:
            return template_vars

        for variable_name, field_path in self.field_mappings.items():
            # Strip $ prefix if present (consistent with generation prompt syntax)
            path = field_path.lstrip("$") if field_path.startswith("$") else field_path
            value = self._extract_nested_value(task_data, path)

            if value is not None:
                # Convert to string for template substitution
                template_vars[variable_name] = str(value) if not isinstance(value, str) else value

        return template_vars

    def validate_model_config(self, model_config: Dict[str, Any]) -> bool:
        """Validate that model configuration is valid for LLM judging."""
        if not self.ai_service:
            logger.warning("No AI service configured for LLM judge")
            return False
        return True

    def evaluate(
        self,
        model_id: str,
        task_data: List[Dict[str, Any]],
        config: EvaluationConfig,
    ) -> EvaluationResult:
        """
        Evaluate samples using LLM-as-Judge.

        Args:
            model_id: ID of the model being evaluated
            task_data: List of task instances with ground truth and predictions
            config: Evaluation configuration

        Returns:
            EvaluationResult with judge scores
        """
        self.log_evaluation_start(model_id, config)

        if not self.ai_service:
            return EvaluationResult(
                metrics={},
                metadata={"model_id": model_id},
                error="No AI service configured for LLM judge",
                samples_evaluated=0,
            )

        # Determine which criteria to evaluate
        criteria_to_use = []
        for metric in config.metrics:
            if metric.startswith("llm_judge_"):
                criterion = metric.replace("llm_judge_", "")
                if criterion in self.all_criteria:
                    criteria_to_use.append(criterion)
                elif criterion == "overall":
                    # Overall uses all standard criteria
                    criteria_to_use = list(DEFAULT_CRITERIA.keys())
                    break

        if not criteria_to_use:
            criteria_to_use = self.criteria

        # Evaluate each sample
        all_scores = {c: [] for c in criteria_to_use}
        samples_evaluated = 0
        errors = []

        for task in task_data:
            try:
                ground_truth = self.extract_ground_truth(task)
                prediction = self.extract_predictions(task, model_id)
                context = task.get("data", {}).get("text", "") or task.get("data", {}).get(
                    "input", ""
                )

                if ground_truth is None or prediction is None:
                    continue

                # Evaluate each criterion
                for criterion in criteria_to_use:
                    result = self._evaluate_single_criterion(
                        context=context,
                        ground_truth=self._format_value(ground_truth),
                        prediction=self._format_value(prediction),
                        criterion=criterion,
                        task_data=task.get("data", {}),
                    )
                    # Result can be a success payload (score+justification) or
                    # a failure payload (error+_call_metadata) when all retries
                    # exhaust. Skip the append when it's a failure so the
                    # outer except doesn't sink the whole sample.
                    if result is not None and not result.get("error") and "score" in result:
                        all_scores[criterion].append(result["score"])

                samples_evaluated += 1

            except Exception as e:
                errors.append(str(e))
                logger.warning(f"Error evaluating sample: {e}")

        # Aggregate scores
        metrics = {}
        for criterion, scores in all_scores.items():
            if scores:
                avg_score = sum(scores) / len(scores)
                # Normalize to 0-1 range based on score_scale. This ladder MUST
                # match the canonical one the worker applies in tasks.py (the
                # multi-run result path) and the clamp in _evaluate_single_criterion
                # — all three support "0-100". Without the 0-100 branch a generic
                # judge on a 0–100 scale normalized via (score-1)/4, e.g. 100 ->
                # 24.75, blowing a "normalized" metric far past 1.0.
                if self.score_scale == "0-1":
                    normalized_score = avg_score  # Already 0-1
                elif self.score_scale == "0-100":
                    normalized_score = avg_score / 100.0  # Convert 0-100 to 0-1
                else:
                    normalized_score = (avg_score - 1) / 4  # Convert 1-5 to 0-1
                metrics[f"llm_judge_{criterion}"] = normalized_score
                metrics[f"llm_judge_{criterion}_raw"] = avg_score

        # Calculate overall score if multiple criteria
        if len(metrics) > 0:
            normalized_scores = [v for k, v in metrics.items() if not k.endswith("_raw")]
            if normalized_scores:
                metrics["llm_judge_overall"] = sum(normalized_scores) / len(normalized_scores)

        metadata = {
            "model_id": model_id,
            "judge_model": self.judge_model,
            "criteria_evaluated": criteria_to_use,
            "samples_evaluated": samples_evaluated,
            "errors": errors[:10] if errors else None,
        }

        result = EvaluationResult(
            metrics=metrics,
            metadata=metadata,
            error=errors[0] if errors and samples_evaluated == 0 else None,
            samples_evaluated=samples_evaluated,
        )

        self.log_evaluation_end(result)
        return result

    def _evaluate_single_criterion(
        self,
        context: str,
        ground_truth: str,
        prediction: str,
        criterion: str,
        task_data: Dict[str, Any] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Evaluate a single sample on a single criterion.

        Args:
            context: Task context/input
            ground_truth: Reference answer
            prediction: Model prediction to evaluate
            criterion: Evaluation criterion key
            task_data: Optional task data for field mapping extraction

        Returns:
            Dict with 'score' (1-5 or 0-1) and 'justification', or None if evaluation failed
        """
        # Falloesung must never reach this generic 1–5 LLM judge — it has its
        # own multi-dimension Bewertungsschema prompt + JSON schema in
        # benger_extended. Both eval paths (immediate-eval at
        # services/workers/tasks.py:4120 and bulk-eval at :3036 / :3441)
        # route through extended hooks instead. Fail loud here so a future
        # regression that forgets to dispatch is visible immediately rather
        # than silently producing wrong-rubric scores.
        if criterion and criterion.startswith("falloesung"):
            raise RuntimeError(
                "Metric 'llm_judge_falloesung' must be routed through "
                "benger_extended.workers.get_falloesung_bulk_compute_fn(); "
                "direct LLMJudgeEvaluator._evaluate_single_criterion calls "
                "are not supported. See services/workers/tasks.py:3036 / :3441."
            )

        # E2E test mock: return deterministic scores without a real API
        # call. Fires on E2E_TEST_MODE regardless of whether an ai_service
        # was constructed — the service layer's own E2E mock returns generic
        # PROSE that the judge parser can't score, so letting the call
        # through just yields "Failed to parse LLM judge response" and a
        # scoreless judge_run (no llm_judge_* aggregate at all).
        import os

        if os.environ.get("E2E_TEST_MODE") == "true":
            import hashlib

            hash_input = f"{criterion}:{str(context)[:50]}:{str(prediction)[:50]}"
            score_hash = int(
                hashlib.md5(hash_input.encode()).hexdigest()[:8], 16
            )
            # Deterministic base in [0.6, 1.0) — expressed on the evaluator's
            # configured scale so the normalization ladder in evaluate()
            # lands back in 0-1. Emitting a bare 0-1 value under the default
            # "1-5" scale would normalize to (x-1)/4 ≈ NEGATIVE and poison
            # the aggregate.
            base = 0.6 + (score_hash % 40) / 100
            if self.score_scale == "0-100":
                mock_score = base * 100
            elif self.score_scale == "0-1":
                mock_score = base
            else:  # "1-5" default
                mock_score = 1 + base * 4
            return {
                "score": mock_score,
                "justification": "Mock evaluation (E2E test mode)",
            }

        if self.ai_service == None:
            return None

        criterion_config = self.all_criteria.get(criterion, {})

        # Use custom prompt template if provided, otherwise use default
        prompt_template = self.custom_prompt_template or SINGLE_EVALUATION_PROMPT

        # Build template variables. Canonical names only — the alias names
        # ({reference}/{response}/{candidate}) were removed in Issue #107;
        # unknown placeholders stay literal via the KeyError fallback below.
        template_vars = {
            "context": context or "No additional context provided.",
            "ground_truth": ground_truth,
            "prediction": prediction,
            "criterion": criterion,
            "criterion_name": criterion_config.get("name", criterion),
            "criterion_description": criterion_config.get("description", ""),
            "rubric": criterion_config.get("rubric", "Score from 1 (poor) to 5 (excellent)"),
        }

        # Apply field mappings to extract custom variables from task_data
        if task_data and self.field_mappings:
            template_vars = self._apply_field_mappings(task_data, template_vars)

        try:
            prompt = prompt_template.format(**template_vars)
        except KeyError as e:
            logger.warning(f"Unknown template variable {e}, using partial format")
            # Fallback to partial format for unknown variables
            for key, value in template_vars.items():
                prompt_template = prompt_template.replace("{" + key + "}", str(value))
            prompt = prompt_template

        # Phase 6.6 (#3): on full retry exhaustion we return a failure
        # dict (with ``error: True`` and ``_call_metadata``) instead of
        # ``None`` so the persistence layer can still record the typed
        # ``error_type`` column. We track the most recent provider /
        # parse failure across attempts here.
        last_failure: Optional[Dict[str, Any]] = None

        for attempt in range(self.max_retries):
            try:
                # Build extra kwargs for thinking/reasoning parameters.
                # Phase 6.6: forward `seed` so providers that accept it
                # (OpenAI/Cohere/Mistral/Grok) honor the per-judge value.
                extra_kwargs = {"seed": self.seed}
                if self.thinking_budget:
                    extra_kwargs["thinking_budget"] = self.thinking_budget
                if self.reasoning_effort:
                    extra_kwargs["reasoning_effort"] = self.reasoning_effort

                response = self.ai_service.generate(
                    prompt=prompt,
                    system_prompt="You are an expert evaluator. Respond only with valid JSON.",
                    model_name=self.judge_model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    **extra_kwargs,
                )

                if not response.get("success"):
                    # Phase 6.6 (#4): the provider already retried 5x
                    # via its own decorator. Retrying again here just
                    # amplifies (5×3 = 15 attempts on rate-limit). Bail
                    # out, but keep the metadata so the failure dict
                    # below can record the typed error_type.
                    logger.warning(
                        f"LLM judge call failed (provider exhausted): {response.get('error')}"
                    )
                    last_failure = {
                        "error": True,
                        "error_message": response.get("error"),
                        "_call_metadata": _extract_call_metadata(response),
                        "_raw_output": response.get("content", ""),
                        "_judge_prompts_used": {
                            "system_prompt": "You are an expert evaluator. Respond only with valid JSON.",
                            "evaluation_prompt": prompt,
                            "criterion": criterion,
                            "judge_model": self.judge_model,
                            "temperature": self.temperature,
                        },
                    }
                    break  # don't retry provider-side failures

                content = response.get("content", "")
                result = self._parse_evaluation_response(content)

                if result and "score" in result:
                    score = float(result["score"])
                    # Clamp score to valid range based on score_scale
                    if self.score_scale == "0-1":
                        result["score"] = max(0.0, min(1.0, score))
                    elif self.score_scale == "0-100":
                        result["score"] = max(0.0, min(100.0, score))
                    else:
                        result["score"] = max(1.0, min(5.0, score))
                    # Attach prompt provenance for reproducibility
                    result["_judge_prompts_used"] = {
                        "system_prompt": "You are an expert evaluator. Respond only with valid JSON.",
                        "evaluation_prompt": prompt,
                        "criterion": criterion,
                        "judge_model": self.judge_model,
                        "temperature": self.temperature,
                    }
                    # Phase 6.6: stop dropping the academic-rigor metadata
                    # the AI service already captured. The persistence
                    # layer (workers/tasks.py) folds this into
                    # task_evaluations.metrics[criterion].details.
                    result["_call_metadata"] = _extract_call_metadata(response)
                    result["_raw_output"] = content
                    # Return the ENTIRE parsed response (all custom fields)
                    return result

                # Provider call succeeded but we couldn't parse a score.
                # This IS worth retrying (the model may produce valid
                # JSON on the next attempt). Record the parse failure so
                # we can return useful provenance if all retries fail.
                last_failure = {
                    "error": True,
                    "error_message": "judge response missing parseable score",
                    "_call_metadata": {
                        **_extract_call_metadata(response),
                        # Override error_type to parse_error: the call
                        # succeeded, the response was just unusable.
                        "error_type": "parse_error",
                    },
                    "_raw_output": content,
                    "_judge_prompts_used": {
                        "system_prompt": "You are an expert evaluator. Respond only with valid JSON.",
                        "evaluation_prompt": prompt,
                        "criterion": criterion,
                        "judge_model": self.judge_model,
                        "temperature": self.temperature,
                    },
                }

            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed: {e}")
                # Capture the exception too, classified the same way
                # the AI service would classify it. Import is best-effort —
                # a missing ai_services module (test envs without shared/
                # on the path) shouldn't sink the retry loop.
                try:
                    from ai_services.base_service import classify_error_type
                    error_type = classify_error_type(e)
                except Exception:
                    error_type = "unknown"
                last_failure = {
                    "error": True,
                    "error_message": str(e),
                    "_call_metadata": {
                        "error_type": error_type,
                    },
                    "_raw_output": "",
                    "_judge_prompts_used": {
                        "system_prompt": "You are an expert evaluator. Respond only with valid JSON.",
                        "evaluation_prompt": prompt,
                        "criterion": criterion,
                        "judge_model": self.judge_model,
                        "temperature": self.temperature,
                    },
                }
                if attempt < self.max_retries - 1:
                    time.sleep(1 * (attempt + 1))  # Exponential backoff

        return last_failure

    def evaluate_pairwise(
        self,
        context: str,
        ground_truth: str,
        response_a: str,
        response_b: str,
        criterion: str = "helpfulness",
    ) -> Dict[str, Any]:
        """
        Compare two responses and determine which is better.

        Args:
            context: Task context
            ground_truth: Reference answer
            response_a: First response to compare
            response_b: Second response to compare
            criterion: Criterion for comparison

        Returns:
            Dict with preference (A, B, or tie) and justification
        """
        criterion_config = self.all_criteria.get(criterion, {})

        prompt = PAIRWISE_COMPARISON_PROMPT.format(
            context=context or "No additional context provided.",
            ground_truth=ground_truth,
            response_a=response_a,
            response_b=response_b,
            criterion_name=criterion_config.get("name", criterion),
            criterion_description=criterion_config.get("description", ""),
        )

        for attempt in range(self.max_retries):
            try:
                # Build extra kwargs for thinking/reasoning parameters.
                # Phase 6.6: forward `seed` so providers that accept it
                # (OpenAI/Cohere/Mistral/Grok) honor the per-judge value.
                extra_kwargs = {"seed": self.seed}
                if self.thinking_budget:
                    extra_kwargs["thinking_budget"] = self.thinking_budget
                if self.reasoning_effort:
                    extra_kwargs["reasoning_effort"] = self.reasoning_effort

                response = self.ai_service.generate(
                    prompt=prompt,
                    system_prompt="You are an expert evaluator. Respond only with valid JSON.",
                    model_name=self.judge_model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    **extra_kwargs,
                )

                if not response.get("success"):
                    continue

                content = response.get("content", "")
                result = self._parse_evaluation_response(content)

                if result and "preference" in result:
                    return {
                        "preference": result["preference"].upper(),
                        "justification": result.get("justification", ""),
                        "criterion": criterion,
                    }

            except Exception as e:
                logger.warning(f"Pairwise comparison attempt {attempt + 1} failed: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(1 * (attempt + 1))

        return {"preference": "TIE", "justification": "Evaluation failed", "criterion": criterion}

    def evaluate_multi_judge(
        self,
        context: str,
        ground_truth: str,
        prediction: str,
        criteria: List[str],
        additional_judge_configs: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Evaluate a sample using multiple judge models for consensus.

        Provides inter-judge agreement metrics for scientific rigor.

        Args:
            context: Task context
            ground_truth: Reference answer
            prediction: Model prediction to evaluate
            criteria: List of criteria to evaluate
            additional_judge_configs: List of configs for additional judges
                Each config should have: {"ai_service": ..., "judge_model": ..., "provider": ...}

        Returns:
            Dict with:
            - scores_by_judge: {judge_model: {criterion: score}}
            - consensus_scores: {criterion: mean_score}
            - inter_judge_agreement: {criterion: agreement_metric}
            - confidence_intervals: {criterion: (lower, upper)}
        """
        from statistics import mean, stdev

        all_judges = [{"ai_service": self.ai_service, "judge_model": self.judge_model}]
        all_judges.extend(additional_judge_configs)

        scores_by_judge = {}
        scores_by_criterion = {c: [] for c in criteria}

        for judge_config in all_judges:
            judge_model = judge_config.get("judge_model", "unknown")
            judge_ai = judge_config.get("ai_service")

            if not judge_ai:
                logger.warning(f"No AI service for judge {judge_model}, skipping")
                continue

            # Temporarily swap AI service for this judge
            original_ai = self.ai_service
            original_model = self.judge_model
            self.ai_service = judge_ai
            self.judge_model = judge_model

            judge_scores = {}
            for criterion in criteria:
                result = self._evaluate_single_criterion(
                    context=context,
                    ground_truth=ground_truth,
                    prediction=prediction,
                    criterion=criterion,
                )
                if result is not None:
                    score = result["score"]
                    # Normalize to 0-1 based on score_scale. Mirror the canonical
                    # ladder (tasks.py / _evaluate_single_criterion clamp), which
                    # supports "0-100"; without it a 0–100 judge consensus would
                    # be (score-1)/4 -> far above 1.0.
                    if self.score_scale == "0-1":
                        normalized = score  # Already 0-1
                    elif self.score_scale == "0-100":
                        normalized = score / 100.0  # Convert 0-100 to 0-1
                    else:
                        normalized = (score - 1) / 4  # Convert 1-5 to 0-1
                    judge_scores[criterion] = normalized
                    scores_by_criterion[criterion].append(normalized)

            scores_by_judge[judge_model] = judge_scores

            # Restore original AI service
            self.ai_service = original_ai
            self.judge_model = original_model

        # Compute consensus scores and agreement
        consensus_scores = {}
        confidence_intervals = {}
        inter_judge_agreement = {}

        for criterion, scores in scores_by_criterion.items():
            if len(scores) >= 2:
                avg = mean(scores)
                std = stdev(scores) if len(scores) > 1 else 0
                consensus_scores[criterion] = avg

                # 95% CI (approximation for small samples)
                margin = 1.96 * std / (len(scores) ** 0.5) if len(scores) > 1 else 0
                confidence_intervals[criterion] = (avg - margin, avg + margin)

                # Simple agreement metric: 1 - (std / max_possible_std)
                # Max std for 0-1 scale is 0.5
                agreement = 1 - (std / 0.5) if std <= 0.5 else 0
                inter_judge_agreement[criterion] = agreement
            elif len(scores) == 1:
                consensus_scores[criterion] = scores[0]
                confidence_intervals[criterion] = (scores[0], scores[0])
                inter_judge_agreement[criterion] = 1.0

        return {
            "scores_by_judge": scores_by_judge,
            "consensus_scores": consensus_scores,
            "confidence_intervals": confidence_intervals,
            "inter_judge_agreement": inter_judge_agreement,
            "num_judges": len([j for j in scores_by_judge.values() if j]),
        }

    def _parse_evaluation_response(self, content: str) -> Optional[Dict[str, Any]]:
        """Parse JSON response from LLM judge."""
        try:
            # Try direct JSON parse
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try to extract JSON from markdown code block
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find JSON object anywhere in response
        json_match = re.search(r'\{[^{}]*"score"[^{}]*\}', content)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        json_match = re.search(r'\{[^{}]*"preference"[^{}]*\}', content)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        logger.warning(f"Failed to parse LLM judge response: {content[:200]}")
        return None

    def is_multidim_mode(self) -> bool:
        """Return True when ``custom_criteria`` carries per-dimension ``max_score``.

        Presence of ``max_score`` on any custom criterion flips the judge
        into single-call multi-dimension mode (one LLM call yields all
        dimension scores + a total). Absence keeps the legacy per-criterion
        fan-out path. Dispatch sites (immediate-eval, bulk-eval) check
        this before deciding whether to call
        :meth:`_evaluate_multidim_single_call` or
        :meth:`_evaluate_single_criterion`.
        """
        return any(
            isinstance(definition, dict) and definition.get("max_score") is not None
            for definition in (self.custom_criteria or {}).values()
        )

    def _evaluate_multidim_single_call(
        self,
        context: str,
        ground_truth: str,
        prediction: str,
        task_data: Optional[Dict[str, Any]] = None,
        field_outputs: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Single LLM call producing all dimension scores + a total.

        Active when :meth:`is_multidim_mode` returns True. Builds one
        prompt from ``self.custom_prompt_template`` (supports both ``{var}``
        and ``{{var}}`` placeholders), calls the judge once with a strict
        JSON schema derived from ``custom_criteria``, and parses
        ``{scores, total_score, overall_assessment}`` from the response.

        Template variable binding (in order, later wins):

        1. Built-ins: ``context``, ``ground_truth``, ``prediction``.
        2. Every key in ``task_data`` (so ``{{fall}}`` resolves from
           ``task.data["fall"]`` with no field-mapping ceremony).
        3. Every key in ``field_outputs`` — the flattened model or
           annotation output (so ``{{kurzantwort}}``/``{{begruendung}}``
           resolve to the model's per-field outputs).
        4. ``self.field_mappings`` — explicit overrides for the cases the
           auto-bind doesn't cover.

        No aliases (``{response}``/``{candidate}``/``{reference}``/``{input}``)
        — removed everywhere in Issue #107; unknown placeholders stay
        literal via the partial-substitution fallback.

        Returns a dict::

            {
              "scores": {<criterion_key>: {"score": float, "max": float, "reason": str}, ...},
              "total_score": float,    # 0..sum(max_score)
              "total_max": float,      # sum of max_score across criteria
              "overall_assessment": str,
              "_call_metadata": {...},
              "_raw_output": str,
              "_judge_prompts_used": {...}
            }

        On failure returns a dict with ``error: True`` and provenance,
        mirroring ``_evaluate_single_criterion``'s failure shape so the
        persistence layer can still record a typed ``error_type``.
        """
        # Resolve the template. The custom_prompt_template is required for
        # multi-dim mode — without a user-authored prompt we have no way
        # to spell out the rubric. Fall back to SINGLE_EVALUATION_PROMPT
        # would silently emit a single-score response that fails the
        # multi-dim parser; better to fail loudly.
        raw_template = self.custom_prompt_template
        if not raw_template:
            return {
                "error": True,
                "error_message": (
                    "Multi-dim mode requires custom_prompt_template; none was provided. "
                    "Author a prompt that asks the judge to score every dimension in one JSON."
                ),
                "_call_metadata": {"error_type": "config_error"},
                "_raw_output": "",
            }
        prompt_template = _preprocess_jinja_placeholders(raw_template)

        # Built-ins first. No aliases — Issue #107.
        template_vars: Dict[str, str] = {
            "context": context or "No additional context provided.",
            "ground_truth": ground_truth or "",
            "prediction": prediction or "",
        }
        # Auto-bind task.data keys. Strings pass through; non-strings get
        # JSON-encoded so structured task fields (e.g. a list of choices)
        # render predictably.
        for key, value in (task_data or {}).items():
            if not isinstance(key, str) or not key.isidentifier():
                continue  # str.format only accepts valid identifier keys
            if value is None:
                continue
            template_vars[key] = (
                value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            )
        # Auto-bind per-field model/annotation outputs. Later means higher
        # precedence: if the same key appears in task.data and in the
        # model output (rare; usually field names don't collide), the
        # model output wins because that's the value being graded.
        for key, value in (field_outputs or {}).items():
            if not isinstance(key, str) or not key.isidentifier():
                continue
            if value is None:
                continue
            template_vars[key] = (
                value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            )
        # Explicit field_mappings override anything auto-bound above.
        if self.field_mappings:
            template_vars = self._apply_field_mappings(task_data or {}, template_vars)

        try:
            prompt = prompt_template.format(**template_vars)
        except KeyError as e:
            logger.warning(f"Unknown template variable {e}, falling back to partial substitution")
            prompt = prompt_template
            for key, value in template_vars.items():
                prompt = prompt.replace("{" + key + "}", str(value))

        json_schema = _build_rubric_json_schema(self.custom_criteria)
        # Sum of max_scores; used to clamp total_score and to give callers
        # a 0..1 normalisation reference.
        total_max = sum(
            float(d.get("max_score") or 0)
            for d in (self.custom_criteria or {}).values()
        )

        provenance = {
            "system_prompt": "You are an expert evaluator. Respond only with valid JSON.",
            "evaluation_prompt": prompt,
            "judge_model": self.judge_model,
            "temperature": self.temperature,
            "custom_criteria": self.custom_criteria,
            "field_mappings": self.field_mappings,
            "mode": "multidim_single_call",
        }

        last_failure: Optional[Dict[str, Any]] = None

        for attempt in range(self.max_retries):
            try:
                extra_kwargs: Dict[str, Any] = {"seed": self.seed}
                if self.thinking_budget:
                    extra_kwargs["thinking_budget"] = self.thinking_budget
                if self.reasoning_effort:
                    extra_kwargs["reasoning_effort"] = self.reasoning_effort

                # generate_structured is the cross-provider wrapper Falllösung
                # uses (falloesung_tasks.py:284) — providers that natively
                # support strict JSON schema (OpenAI, Anthropic, Google,
                # Cohere, Mistral, Grok, DeepInfra) consume it; others fall
                # back to prompt-based JSON via the same call. Using
                # `generate(response_format=...)` directly here would have
                # blown up on Anthropic / Google judges with an unknown kwarg.
                response = self.ai_service.generate_structured(
                    prompt=prompt,
                    system_prompt=provenance["system_prompt"],
                    model_name=self.judge_model,
                    json_schema=json_schema,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    **extra_kwargs,
                )

                if not response.get("success"):
                    last_failure = {
                        "error": True,
                        "error_message": response.get("error"),
                        "_call_metadata": _extract_call_metadata(response),
                        "_raw_output": response.get("content", ""),
                        "_judge_prompts_used": provenance,
                    }
                    break

                content = response.get("content", "")
                parsed = _parse_multidim_response(content)

                if parsed and isinstance(parsed.get("scores"), dict):
                    scores_in = parsed["scores"]
                    clamped: Dict[str, Dict[str, Any]] = {}
                    total = 0.0
                    for key, definition in (self.custom_criteria or {}).items():
                        max_score = definition.get("max_score")
                        if max_score is None:
                            continue
                        raw = scores_in.get(key) or {}
                        if isinstance(raw, (int, float)):
                            raw = {"score": float(raw), "reason": ""}
                        try:
                            score = float(raw.get("score", 0))
                        except (TypeError, ValueError):
                            score = 0.0
                        score = max(0.0, min(float(max_score), score))
                        clamped[key] = {
                            "score": score,
                            "max": float(max_score),
                            "reason": str(raw.get("reason", "") or ""),
                        }
                        total += score
                    # Trust the model's total_score when present and within
                    # tolerance of our sum; otherwise use the summed value.
                    model_total = parsed.get("total_score")
                    if isinstance(model_total, (int, float)) and abs(float(model_total) - total) <= 0.5:
                        total = float(model_total)

                    return {
                        "scores": clamped,
                        "total_score": float(total),
                        "total_max": float(total_max),
                        "overall_assessment": str(parsed.get("overall_assessment", "") or ""),
                        "_call_metadata": _extract_call_metadata(response),
                        "_raw_output": content,
                        "_judge_prompts_used": provenance,
                    }

                last_failure = {
                    "error": True,
                    "error_message": "judge response missing parseable scores dict",
                    "_call_metadata": {
                        **_extract_call_metadata(response),
                        "error_type": "parse_error",
                    },
                    "_raw_output": content,
                    "_judge_prompts_used": provenance,
                }

            except Exception as e:
                logger.warning(f"Multi-dim attempt {attempt + 1} failed: {e}")
                try:
                    from ai_services.base_service import classify_error_type
                    error_type = classify_error_type(e)
                except Exception:
                    error_type = "unknown"
                last_failure = {
                    "error": True,
                    "error_message": str(e),
                    "_call_metadata": {"error_type": error_type},
                    "_raw_output": "",
                    "_judge_prompts_used": provenance,
                }
                if attempt < self.max_retries - 1:
                    time.sleep(1 * (attempt + 1))

        return last_failure

    def _format_value(self, value: Any) -> str:
        """Format a value for inclusion in prompts (type-aware if answer_type set)."""
        if self.answer_type:
            return self._format_value_by_type(value, self.answer_type)

        if isinstance(value, str):
            return value
        elif isinstance(value, (dict, list)):
            return json.dumps(value, indent=2)
        else:
            return str(value)

    def _format_value_by_type(self, value: Any, answer_type: str) -> str:
        """
        Format value for optimal LLM evaluation based on answer type.

        Each type has specific formatting for best prompt performance:
        - text: Returns string as-is
        - choices: Formats as "Selected: [item1, item2]"
        - span_selection: Formats spans with boundaries and labels
        - rating/numeric: Formats as "Value: X"
        """
        if value is None:
            return "(no value provided)"

        # Text types - return as-is or stringify
        if answer_type in ["text", "short_text", "long_text"]:
            if isinstance(value, str):
                return value if value else "(empty)"
            if isinstance(value, dict):
                # Handle {text: [value]} format
                text_val = value.get("text")
                if isinstance(text_val, list) and len(text_val) > 0:
                    return str(text_val[0])
                elif text_val:
                    return str(text_val)
            return str(value) if value else "(empty)"

        # Choice types - format as selection list
        if answer_type in ["choices", "single_choice", "binary", "multiple_choice"]:
            choices = value
            # Handle {choices: [value]} format
            if isinstance(value, dict):
                choices = value.get("choices", value.get("selected", []))
            if isinstance(choices, list):
                items = ", ".join(str(c) for c in choices)
                return f"Selected: [{items}]" if items else "Selected: [none]"
            return f"Selected: [{choices}]"

        # Span/NER types - detailed boundary and label formatting
        if answer_type == "span_selection":
            return self._format_spans(value)

        # Rating/Numeric types - simple value display
        if answer_type in ["rating", "numeric"]:
            if isinstance(value, dict):
                # Handle {rating: X} or {number: X} format
                num_val = value.get("rating") or value.get("number") or value.get("value")
                if num_val is not None:
                    return f"Value: {num_val}"
            return f"Value: {value}"

        # Fallback: JSON for complex types, string for simple
        if isinstance(value, (dict, list)):
            return json.dumps(value, indent=2)
        return str(value)

    def _format_spans(self, spans: Any) -> str:
        """
        Format span annotations for LLM evaluation.

        Produces readable format showing:
        - Extracted text
        - Character positions (start-end)
        - Assigned labels

        Example output:
          - "John Smith" (chars 0-10) labeled as [PERSON]
          - "New York" (chars 45-53) labeled as [LOCATION]
        """
        if not spans:
            return "(no spans annotated)"

        # Handle {spans: [...]} format
        if isinstance(spans, dict):
            spans = spans.get("spans", spans.get("labels", []))

        if not isinstance(spans, list):
            return f"(invalid span format: {type(spans).__name__})"

        if len(spans) == 0:
            return "(no spans annotated)"

        formatted = []
        for i, span in enumerate(spans):
            if not isinstance(span, dict):
                formatted.append(f"  {i + 1}. (invalid span entry)")
                continue

            text = span.get("text", span.get("value", "N/A"))
            start = span.get("start", "?")
            end = span.get("end", "?")

            # Handle labels - can be list or single value
            labels = span.get("labels", span.get("label", []))
            if isinstance(labels, str):
                labels = [labels]
            elif not isinstance(labels, list):
                labels = []
            labels_str = ", ".join(str(l) for l in labels) if labels else "no label"

            formatted.append(f'  {i + 1}. "{text}" (chars {start}-{end}) labeled as [{labels_str}]')

        return "\n".join(formatted) if formatted else "(no valid spans)"


def create_llm_judge_for_user(
    db: Any,
    user_id: str,
    provider: str,
    judge_model: str,
    criteria: List[str] = None,
    temperature: float = 0.0,
    max_tokens: int = 500,
    custom_criteria: Dict[str, Dict[str, str]] = None,
    custom_prompt_template: str = None,
    answer_type: str = None,
    field_mappings: Dict[str, str] = None,
    score_scale: str = "1-5",
    thinking_budget: Optional[int] = None,
    reasoning_effort: Optional[str] = None,
    organization_id: Optional[str] = None,
    seed: int = 42,
) -> LLMJudgeEvaluator:
    """
    Factory function to create LLM Judge evaluator with user's or org's API key.

    Args:
        db: Database session
        user_id: User ID for API key lookup
        provider: LLM provider (openai, anthropic, google, deepinfra)
        judge_model: Model to use for judging
        criteria: List of criteria to evaluate
        temperature: Temperature for LLM calls (0.0 for reproducibility)
        max_tokens: Maximum tokens for judge response (default 500)
        custom_criteria: Custom criteria with descriptions and rubrics
        custom_prompt_template: Custom prompt template (supports {prediction}, {ground_truth}, {criterion})
        answer_type: Answer type for auto-selecting prompts/criteria (text, choices, span_selection, etc.)
        field_mappings: Custom field mappings that map template variables to task data fields.
                       Uses same syntax as generation prompts: {"variable": "$field.path"}
        score_scale: Scale for LLM judge scores. "1-5" (default) or "0-1" for finer granularity
        thinking_budget: Token budget for AI reasoning (Anthropic Claude 3.7+, Google Gemini 2.5)
        reasoning_effort: Reasoning effort level for OpenAI o-series ("low", "medium", "high")
        organization_id: Organization ID for org API key resolution (Issue #1180)

    Returns:
        Configured LLMJudgeEvaluator
    """
    import os
    import sys

    # Import user-aware AI service
    shared_path = os.path.dirname(os.path.dirname(__file__))
    parent_shared = os.path.join(shared_path, "shared")
    if parent_shared not in sys.path:
        sys.path.insert(0, parent_shared)

    try:
        from ai_services.user_aware_ai_service import user_aware_ai_service

        ai_service = user_aware_ai_service.get_ai_service_for_user(
            db=db,
            user_id=user_id,
            provider=provider,
            organization_id=organization_id,
        )

        return LLMJudgeEvaluator(
            ai_service=ai_service,
            judge_model=judge_model,
            criteria=criteria,
            temperature=temperature,
            max_tokens=max_tokens,
            custom_criteria=custom_criteria,
            custom_prompt_template=custom_prompt_template,
            answer_type=answer_type,
            field_mappings=field_mappings,
            score_scale=score_scale,
            thinking_budget=thinking_budget,
            reasoning_effort=reasoning_effort,
            seed=seed,
        )
    except Exception as e:
        logger.error(f"Failed to create LLM judge: {e}")
        return LLMJudgeEvaluator(
            criteria=criteria,
            max_tokens=max_tokens,
            custom_criteria=custom_criteria,
            custom_prompt_template=custom_prompt_template,
            field_mappings=field_mappings,
            answer_type=answer_type,
            score_scale=score_scale,
            thinking_budget=thinking_budget,
            reasoning_effort=reasoning_effort,
            seed=seed,
        )
