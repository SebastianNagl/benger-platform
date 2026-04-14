"""Populate parameter_constraints for LLM models

Data migration to populate the parameter_constraints JSONB column
(added in migration 007) with model-specific temperature, max_tokens,
and reproducibility constraints. Covers GPT-5 series, o-series,
Claude, Qwen thinking, DeepSeek R1, and Gemini thinking models.

Revision ID: 028_populate_parameter_constraints
Revises: 027_add_feedback
Create Date: 2026-03-25
"""

import json

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "028_populate_parameter_constraints"
down_revision = "027_add_feedback"
branch_labels = None
depends_on = None

# Constraint templates
_GPT5 = {
    "temperature": {
        "supported": False,
        "required_value": 1.0,
        "reason": "OpenAI GPT-5 series enforces temperature=1.0 via API",
    },
    "max_tokens": {"default": 8000},
    "unsupported_params": [
        "top_p", "presence_penalty", "frequency_penalty",
        "logprobs", "top_logprobs", "logit_bias",
    ],
    "reproducibility_impact": "CRITICAL",
    "benchmark_notes": "Run multiple iterations (n>=5) and report variance. Results cannot be deterministic.",
}

_O_SERIES_BASE = {
    "temperature": {
        "supported": False,
        "required_value": 1.0,
        "reason": "OpenAI o-series enforces temperature=1.0 via API",
    },
    "unsupported_params": [
        "top_p", "presence_penalty", "frequency_penalty",
        "logprobs", "top_logprobs", "logit_bias",
    ],
    "reproducibility_impact": "CRITICAL",
    "benchmark_notes": "Run multiple iterations (n>=5) and report variance. Results cannot be deterministic.",
}


def _o_series(max_tokens_default):
    return {**_O_SERIES_BASE, "max_tokens": {"default": max_tokens_default}}


# All models and their constraints
CONSTRAINTS = {
    # GPT-5 series
    "gpt-5": _GPT5,
    "gpt-5.4": _GPT5,
    "gpt-5.2": _GPT5,
    "gpt-5.1": _GPT5,
    "gpt-5-mini": _GPT5,
    "gpt-5-nano": _GPT5,
    # o-series
    "o1": _o_series(16000),
    "o3": _o_series(16000),
    "o3-mini": _o_series(8000),
    "o4-mini": _o_series(8000),
    # Claude models
    "claude-opus-4-6": {
        "temperature": {"supported": True, "default": 0.0, "min": 0.0, "max": 1.0},
        "max_tokens": {"default": 16000},
    },
    "claude-sonnet-4-6": {
        "temperature": {"supported": True, "default": 0.0, "min": 0.0, "max": 1.0},
        "max_tokens": {"default": 8000},
    },
    "claude-opus-4-1-20250805": {
        "temperature": {
            "supported": True, "default": 0.0, "min": 0.0, "max": 1.0,
            "reason": "Standard support, but conflicts with top_p",
        },
        "top_p": {"supported": True, "conflicts_with": ["temperature"]},
        "max_tokens": {"default": 16000},
        "reproducibility_impact": "LOW",
        "benchmark_notes": "Use temperature=0.0 only, omit top_p parameter.",
    },
    "claude-opus-4-5-20251101": {
        "temperature": {"supported": True, "default": 0.0, "min": 0.0, "max": 1.0},
        "max_tokens": {"default": 16000},
    },
    "claude-sonnet-4-5-20250929": {
        "temperature": {"supported": True, "default": 0.0, "min": 0.0, "max": 1.0},
        "max_tokens": {"default": 8000},
    },
    "claude-opus-4-20250514": {
        "temperature": {"supported": True, "default": 0.0, "min": 0.0, "max": 1.0},
        "max_tokens": {"default": 16000},
    },
    "claude-sonnet-4-20250514": {
        "temperature": {"supported": True, "default": 0.0, "min": 0.0, "max": 1.0},
        "max_tokens": {"default": 8000},
    },
    # Qwen thinking models
    "Qwen/QwQ-32B": {
        "temperature": {
            "supported": True, "default": 0.6, "min": 0.6, "max": 2.0,
            "reason": "Greedy decoding (temp<0.6) causes endless repetitions",
        },
        "max_tokens": {"default": 8000},
        "reproducibility_impact": "MEDIUM",
        "benchmark_notes": "Lowest stable temperature is 0.6. Run 3 iterations, report variance.",
    },
    "Qwen/Qwen3-235B-A22B-Thinking-2507": {
        "temperature": {
            "supported": True, "default": 0.6, "min": 0.6, "max": 2.0,
            "reason": "Thinking mode requires temp>=0.6 to avoid repetitions",
        },
        "max_tokens": {"default": 8000},
        "reproducibility_impact": "MEDIUM",
        "benchmark_notes": "Lowest stable temperature is 0.6. Run 3 iterations, document thinking tokens.",
    },
    # DeepSeek models
    "deepseek-ai/DeepSeek-R1-0528": {
        "temperature": {
            "supported": True, "default": 0.6, "min": 0.0, "max": 2.0,
            "reason": "Works at 0.0 but optimal performance at 0.5-0.7",
        },
        "max_tokens": {"default": 8000},
        "reproducibility_impact": "LOW",
        "benchmark_notes": "For reproducibility: use 0.0. For quality benchmarks: use 0.6.",
    },
    "deepseek-ai/DeepSeek-R1-Distill-Llama-70B": {
        "temperature": {
            "supported": True, "default": 0.6, "min": 0.0, "max": 2.0,
            "reason": "Distilled model optimized for temp=0.5-0.7",
        },
        "max_tokens": {"default": 8000},
        "reproducibility_impact": "LOW",
        "benchmark_notes": "For reproducibility: use 0.0. For quality benchmarks: use 0.6.",
    },
    "deepseek-ai/DeepSeek-V3.1": {
        "temperature": {
            "supported": True, "default": 0.6, "min": 0.0, "max": 2.0,
            "reason": "Optimal performance at 0.5-0.7",
        },
        "max_tokens": {"default": 8000},
        "reproducibility_impact": "LOW",
    },
    # Gemini thinking models
    "gemini-2.5-pro": {
        "temperature": {"supported": True, "default": 0.0, "min": 0.0, "max": 2.0},
        "max_tokens": {"default": 8000},
    },
    "gemini-2.5-flash": {
        "temperature": {"supported": True, "default": 0.0, "min": 0.0, "max": 2.0},
        "max_tokens": {"default": 8000},
    },
}


def upgrade():
    conn = op.get_bind()
    for model_id, constraints in CONSTRAINTS.items():
        conn.execute(
            sa.text(
                "UPDATE llm_models SET parameter_constraints = CAST(:constraints AS jsonb) "
                "WHERE id = :model_id"
            ),
            {"model_id": model_id, "constraints": json.dumps(constraints)},
        )


def downgrade():
    conn = op.get_bind()
    for model_id in CONSTRAINTS:
        conn.execute(
            sa.text(
                "UPDATE llm_models SET parameter_constraints = NULL WHERE id = :model_id"
            ),
            {"model_id": model_id},
        )
