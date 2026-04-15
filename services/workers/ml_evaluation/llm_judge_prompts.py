"""
Type-Specific Prompt Templates for LLM-as-Judge Evaluation.

Each answer type has optimized prompts and criteria for accurate evaluation.
Supports: text, choices, span_selection, rating, numeric.
"""

# =============================================================================
# TEXT EVALUATION PROMPT (Free-form text responses)
# =============================================================================

TEXT_EVALUATION_PROMPT = """You are an expert evaluator assessing the quality of an AI-generated text response.

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

# =============================================================================
# CHOICES/CLASSIFICATION EVALUATION PROMPT
# =============================================================================

CHOICES_EVALUATION_PROMPT = """You are an expert evaluator assessing a classification/selection prediction.

## Task Context
{context}

## Correct Answer(s)
{ground_truth}

## Model's Selection
{prediction}

## Evaluation Criterion: {criterion_name}
{criterion_description}

### Scoring Rubric
{rubric}

## Instructions
1. Compare the model's selection against the correct answer(s)
2. For single-choice: check for exact match
3. For multi-choice: evaluate both precision (no false positives) and recall (no false negatives)
4. Consider if partial credit is appropriate

Respond in JSON format:
{{
    "score": <integer 1-5>,
    "justification": "<explanation focusing on which choices match/differ>",
    "correct_selections": ["<list of correctly selected items>"],
    "incorrect_selections": ["<list of incorrectly selected items>"],
    "missing_selections": ["<list of items that should have been selected>"]
}}
"""

# =============================================================================
# SPAN/NER EVALUATION PROMPT (Named Entity Recognition)
# =============================================================================

SPAN_EVALUATION_PROMPT = """You are an expert evaluator assessing Named Entity Recognition (NER) / span annotations.

## Source Text
{context}

## Reference Annotations (Ground Truth)
{ground_truth}

## Model Annotations (Prediction)
{prediction}

## Evaluation Criterion: {criterion_name}
{criterion_description}

### Span Annotation Format
Each annotation shows: "TEXT" (characters START-END) labeled as [LABELS]

### Scoring Rubric
{rubric}

## Instructions
Evaluate the model's span annotations considering:
1. **Boundary Accuracy**: Are the character start/end positions exactly correct?
   - Exact match = full credit
   - Off by 1-2 chars = partial credit
   - Off by >2 chars = significant penalty
2. **Label Accuracy**: Are the assigned entity labels correct for each span?
3. **Coverage**: Are all entities from the reference found?
4. **Precision**: Are there spurious/incorrect spans in the prediction?

Respond in JSON format:
{{
    "score": <integer 1-5>,
    "justification": "<specific analysis of span quality>",
    "boundary_issues": [
        {{"predicted_span": "...", "reference_span": "...", "issue": "off by X chars"}}
    ],
    "label_issues": [
        {{"span": "...", "predicted_label": "...", "correct_label": "..."}}
    ],
    "missing_spans": ["<spans in reference but not prediction>"],
    "spurious_spans": ["<spans in prediction but not reference>"]
}}
"""

# =============================================================================
# NUMERIC/RATING EVALUATION PROMPT
# =============================================================================

NUMERIC_EVALUATION_PROMPT = """You are an expert evaluator assessing a numeric/rating prediction.

## Task Context
{context}

## Reference Value
{ground_truth}

## Model's Prediction
{prediction}

## Evaluation Criterion: {criterion_name}
{criterion_description}

### Scoring Rubric
{rubric}

## Instructions
1. Compare the predicted numeric value to the reference
2. Consider the scale and context of the measurement
3. Evaluate if the prediction is within acceptable tolerance
4. For ratings: consider if adjacent values are acceptable

Respond in JSON format:
{{
    "score": <integer 1-5>,
    "justification": "<analysis of the numeric difference>",
    "absolute_error": <calculated difference or null>,
    "percentage_error": <calculated percentage or null>,
    "within_tolerance": <true/false>
}}
"""

# =============================================================================
# TYPE-SPECIFIC CRITERIA DEFINITIONS
# =============================================================================

TYPE_SPECIFIC_CRITERIA = {
    # Criteria for Choices/Classification
    "accuracy": {
        "name": "Selection Accuracy",
        "description": "Did the model select the correct answer(s)?",
        "scale": "1-5",
        "rubric": """
1 - Completely incorrect: Selected entirely wrong choice(s), no overlap with correct answer
2 - Mostly incorrect: Selected mostly wrong choices with minimal overlap
3 - Partially correct: Some correct selections but significant errors (missing or extra)
4 - Mostly correct: Correct selection with minor errors (one wrong or missing)
5 - Fully correct: Exact match with reference selection
""",
    },
    "reasoning": {
        "name": "Reasoning Quality",
        "description": "Does the selection demonstrate sound reasoning based on the context?",
        "scale": "1-5",
        "rubric": """
1 - No reasoning: Selection appears random or contradicts the context
2 - Poor reasoning: Weak connection between context and selection
3 - Moderate reasoning: Some logical basis but gaps in understanding
4 - Good reasoning: Clear logical connection with minor gaps
5 - Excellent reasoning: Selection perfectly follows from the context
""",
    },
    "set_accuracy": {
        "name": "Set Accuracy (Multi-select)",
        "description": "How accurate is the set of selected items compared to the reference set?",
        "scale": "1-5",
        "rubric": """
1 - Very poor: Jaccard similarity < 0.2 (little overlap)
2 - Poor: Jaccard similarity 0.2-0.4
3 - Moderate: Jaccard similarity 0.4-0.6
4 - Good: Jaccard similarity 0.6-0.8
5 - Excellent: Jaccard similarity > 0.8 or exact match
""",
    },
    "partial_credit": {
        "name": "Partial Credit Score",
        "description": "Proportional credit for partially correct multi-select answers",
        "scale": "1-5",
        "rubric": """
1 - <20% of correct items selected with many false positives
2 - 20-40% of correct items selected
3 - 40-60% of correct items selected
4 - 60-80% of correct items selected with few false positives
5 - >80% of correct items selected with no/minimal false positives
""",
    },
    # Criteria for Spans/NER
    "boundary_accuracy": {
        "name": "Boundary Accuracy",
        "description": "Are entity boundaries (start/end character positions) correctly identified?",
        "scale": "1-5",
        "rubric": """
1 - Very poor: Most boundaries significantly off (>5 characters from reference)
2 - Poor: Many boundaries have notable errors (3-5 characters off)
3 - Moderate: Some boundaries correct, others with small errors (1-2 chars)
4 - Good: Most boundaries exact or within 1 character
5 - Excellent: All boundaries exactly match reference positions
""",
    },
    "label_accuracy": {
        "name": "Label Accuracy",
        "description": "Are entity labels correctly assigned to identified spans?",
        "scale": "1-5",
        "rubric": """
1 - Very poor: <20% of labels correct
2 - Poor: 20-40% of labels correct
3 - Moderate: 40-60% of labels correct
4 - Good: 60-80% of labels correct
5 - Excellent: >80% of labels correct or all correct
""",
    },
    "coverage": {
        "name": "Entity Coverage (Recall)",
        "description": "What proportion of reference entities were found by the model?",
        "scale": "1-5",
        "rubric": """
1 - Very poor coverage: <20% of reference entities found
2 - Low coverage: 20-40% of entities found
3 - Moderate coverage: 40-60% of entities found
4 - Good coverage: 60-80% of entities found
5 - Excellent coverage: >80% of entities found
""",
    },
    "span_precision": {
        "name": "Span Precision",
        "description": "What proportion of predicted spans are actually correct?",
        "scale": "1-5",
        "rubric": """
1 - Very poor: <20% of predicted spans are valid
2 - Poor: 20-40% of predictions valid
3 - Moderate: 40-60% of predictions valid
4 - Good: 60-80% of predictions valid
5 - Excellent: >80% of predictions valid
""",
    },
    # Criteria for Numeric/Rating
    "precision": {
        "name": "Numeric Precision",
        "description": "How close is the predicted value to the reference value?",
        "scale": "1-5",
        "rubric": """
1 - Far off: >50% error or completely wrong magnitude
2 - Poor accuracy: 25-50% error
3 - Moderate accuracy: 10-25% error
4 - Good accuracy: <10% error
5 - Excellent: Exact match or negligible difference (<1%)
""",
    },
    "scale_appropriateness": {
        "name": "Scale Appropriateness",
        "description": "Is the value appropriate for the rating scale and context?",
        "scale": "1-5",
        "rubric": """
1 - Inappropriate: Value outside valid scale or nonsensical
2 - Poor fit: Value technically valid but contextually wrong
3 - Moderate: Value reasonable but not ideal for context
4 - Good: Value appropriate with minor concerns
5 - Excellent: Value perfectly fits scale and context
""",
    },
    "magnitude_accuracy": {
        "name": "Magnitude Accuracy",
        "description": "Is the order of magnitude of the prediction correct?",
        "scale": "1-5",
        "rubric": """
1 - Wrong magnitude: Off by 2+ orders of magnitude
2 - Poor: Off by 1 order of magnitude
3 - Moderate: Same order but significant difference
4 - Good: Same order with reasonable difference
5 - Excellent: Correct magnitude with minimal error
""",
    },
}

# =============================================================================
# PROMPT TEMPLATES REGISTRY
# =============================================================================

PROMPT_TEMPLATES = {
    "text": {
        "name": "Free-form Text",
        "description": "Evaluate quality, correctness, and coherence of text responses",
        "template": TEXT_EVALUATION_PROMPT,
        "criteria": ["helpfulness", "correctness", "fluency", "coherence", "relevance"],
        "hint": "Best for essays, summaries, explanations, and open-ended responses",
    },
    "short_text": {
        "name": "Short Text",
        "description": "Evaluate brief text responses",
        "template": TEXT_EVALUATION_PROMPT,
        "criteria": ["correctness", "relevance"],
        "hint": "Best for short answers, fill-in-the-blank",
    },
    "long_text": {
        "name": "Long Text",
        "description": "Evaluate detailed text responses",
        "template": TEXT_EVALUATION_PROMPT,
        "criteria": ["helpfulness", "correctness", "fluency", "coherence", "relevance"],
        "hint": "Best for essays, detailed explanations",
    },
    "choices": {
        "name": "Classification (Single Choice)",
        "description": "Evaluate if the correct single choice was selected",
        "template": CHOICES_EVALUATION_PROMPT,
        "criteria": ["accuracy", "reasoning"],
        "hint": "Best for single-choice questions, yes/no, binary decisions",
    },
    "single_choice": {
        "name": "Single Choice",
        "description": "Evaluate single selection from options",
        "template": CHOICES_EVALUATION_PROMPT,
        "criteria": ["accuracy", "reasoning"],
        "hint": "Best for radio button selections",
    },
    "binary": {
        "name": "Binary Choice",
        "description": "Evaluate yes/no or true/false selections",
        "template": CHOICES_EVALUATION_PROMPT,
        "criteria": ["accuracy"],
        "hint": "Best for yes/no, true/false questions",
    },
    "multiple_choice": {
        "name": "Multiple Choice (Multi-select)",
        "description": "Evaluate selection of multiple correct items",
        "template": CHOICES_EVALUATION_PROMPT,
        "criteria": ["set_accuracy", "partial_credit", "reasoning"],
        "hint": "Best for checkbox selections, multiple correct answers",
    },
    "span_selection": {
        "name": "Named Entity Recognition (NER)",
        "description": "Evaluate entity boundaries AND labels (strictest mode)",
        "template": SPAN_EVALUATION_PROMPT,
        "criteria": ["boundary_accuracy", "label_accuracy", "coverage"],
        "hint": "Evaluates both WHERE spans are and WHAT they're labeled",
    },
    "rating": {
        "name": "Rating Scale",
        "description": "Evaluate numeric rating predictions (e.g., 1-5 stars)",
        "template": NUMERIC_EVALUATION_PROMPT,
        "criteria": ["precision", "scale_appropriateness"],
        "hint": "Best for star ratings, Likert scales",
    },
    "numeric": {
        "name": "Numeric Value",
        "description": "Evaluate numeric predictions",
        "template": NUMERIC_EVALUATION_PROMPT,
        "criteria": ["precision", "magnitude_accuracy"],
        "hint": "Best for numerical answers, measurements",
    },
}


def get_template_for_type(answer_type: str) -> str:
    """Get the appropriate prompt template for an answer type."""
    type_config = PROMPT_TEMPLATES.get(answer_type)
    if type_config:
        return type_config["template"]
    # Fallback to text template
    return TEXT_EVALUATION_PROMPT


def get_criteria_for_type(answer_type: str) -> list:
    """Get the recommended criteria for an answer type."""
    type_config = PROMPT_TEMPLATES.get(answer_type)
    if type_config:
        return type_config["criteria"]
    # Fallback to default text criteria
    return ["helpfulness", "correctness"]


def get_all_criteria() -> dict:
    """Get all type-specific criteria definitions."""
    return TYPE_SPECIFIC_CRITERIA


def get_template_info(answer_type: str) -> dict:
    """Get full template information for an answer type."""
    return PROMPT_TEMPLATES.get(answer_type, PROMPT_TEMPLATES["text"])
