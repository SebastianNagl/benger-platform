"""
Token estimation for cost preview.

Used by the cost-estimate endpoint (multi-run feature). Tokenizes a sample of
project prompt templates with `tiktoken` and returns mean/p95 input-token
counts plus an output-token estimate. The estimate is best-effort: we proxy
non-OpenAI models with cl100k_base and surface a "± ~20%" caveat in the UI.

Cached per (project_id, model_id, prompt_hash) for 1 hour to avoid
re-tokenizing on every modal open.
"""

from __future__ import annotations

import hashlib
import logging
import random
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import tiktoken

    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False


# Heuristic for output-token utilization: judge templates and chat completions
# rarely fill `max_tokens`; this captures the typical usage. Tuned against the
# small handful of evals we have on prod (Phase 6.6 latency telemetry).
DEFAULT_OUTPUT_UTILIZATION = 0.6

# Process-local cache. Tiny memory footprint; entries expire after 1 hour.
_CACHE: Dict[str, "TokenEstimate"] = {}
_CACHE_TTL_SECONDS = 60 * 60


@dataclass
class TokenEstimate:
    """Per-call token estimate from `estimate_tokens_for_calls`."""

    input_mean: float
    input_p95: float
    output_estimate: float
    sample_size: int
    encoding_name: str
    cached_at: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "input_mean": round(self.input_mean, 1),
            "input_p95": round(self.input_p95, 1),
            "output_estimate": round(self.output_estimate, 1),
            "sample_size": self.sample_size,
            "encoding": self.encoding_name,
        }


def _encoding_for_model(model_id: str):
    """Pick a tiktoken encoding for a model_id. cl100k_base is the OpenAI
    default and a reasonable proxy for non-OpenAI models — close enough for
    order-of-magnitude cost estimates."""
    if not TIKTOKEN_AVAILABLE:
        return None
    try:
        # OpenAI models map directly; non-OpenAI fall through to cl100k_base.
        return tiktoken.encoding_for_model(model_id)
    except (KeyError, ValueError):
        return tiktoken.get_encoding("cl100k_base")


def _hash_prompt(prompt_text: str) -> str:
    return hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()[:16]


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = max(0, min(len(sorted_vals) - 1, int(round((pct / 100.0) * (len(sorted_vals) - 1)))))
    return float(sorted_vals[k])


def estimate_tokens_for_calls(
    *,
    project_id: str,
    model_id: str,
    prompt_samples: List[str],
    max_output_tokens: int,
    output_utilization: float = DEFAULT_OUTPUT_UTILIZATION,
) -> TokenEstimate:
    """
    Estimate input + output tokens per LLM call for `model_id` given a sample
    of rendered prompts (strings). Returns a TokenEstimate with mean/p95 input
    tokens and the heuristic output token estimate.

    Caching: keyed on (project_id, model_id, sha256(joined_prompts)). 1h TTL.
    """
    joined = "\n\n".join(prompt_samples)
    cache_key = f"{project_id}:{model_id}:{_hash_prompt(joined)}"
    now = time.time()

    cached = _CACHE.get(cache_key)
    if cached and (now - cached.cached_at) < _CACHE_TTL_SECONDS:
        return cached

    if not TIKTOKEN_AVAILABLE:
        # Fall back to a crude chars/4 heuristic so the endpoint still returns
        # a number when tiktoken isn't installed (dev environments may skip
        # the optional dependency).
        char_lengths = [len(p) for p in prompt_samples] or [0]
        token_lengths = [c / 4 for c in char_lengths]
        encoding_name = "chars/4 (no tiktoken)"
    else:
        enc = _encoding_for_model(model_id)
        token_lengths = [len(enc.encode(p)) for p in prompt_samples]
        encoding_name = enc.name if hasattr(enc, "name") else "cl100k_base"

    if not token_lengths:
        token_lengths = [0.0]

    estimate = TokenEstimate(
        input_mean=float(sum(token_lengths) / len(token_lengths)),
        input_p95=_percentile(token_lengths, 95),
        output_estimate=float(max_output_tokens) * float(output_utilization),
        sample_size=len(prompt_samples),
        encoding_name=encoding_name,
        cached_at=now,
    )
    _CACHE[cache_key] = estimate

    # Lazy GC: drop entries older than 2× TTL so the cache doesn't grow
    # unbounded on a long-running API process.
    expired = [k for k, v in _CACHE.items() if (now - v.cached_at) > 2 * _CACHE_TTL_SECONDS]
    for k in expired:
        _CACHE.pop(k, None)

    return estimate


def sample_task_texts(
    *,
    db,
    project_id: str,
    sample_size: int = 10,
    seed: Optional[int] = None,
) -> List[str]:
    """
    Pull a sample of task data strings from the project for prompt rendering.
    Deterministic with `seed`; otherwise picks the first N tasks by id.

    Importantly, this returns the raw task data as a string — callers that
    need a fully-rendered prompt template should render the project's prompt
    against each text before passing to `estimate_tokens_for_calls`.
    """
    from project_models import Task

    tasks = (
        db.query(Task)
        .filter(Task.project_id == project_id)
        .order_by(Task.id)
        .limit(max(sample_size * 5, 50))
        .all()
    )
    if not tasks:
        return []

    if seed is not None:
        rng = random.Random(seed)
        if len(tasks) > sample_size:
            tasks = rng.sample(tasks, sample_size)
        else:
            tasks = list(tasks)
    else:
        tasks = tasks[:sample_size]

    texts: List[str] = []
    for task in tasks:
        data = task.data or {}
        if isinstance(data, dict):
            # Flatten the dict into a single string — close enough for token
            # counting since the actual prompt template will wrap each field.
            parts = []
            for v in data.values():
                if isinstance(v, str):
                    parts.append(v)
                else:
                    parts.append(str(v))
            texts.append("\n".join(parts))
        elif isinstance(data, str):
            texts.append(data)
        else:
            texts.append(str(data))

    return texts
