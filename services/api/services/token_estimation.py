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
import json
import logging
import random
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

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


#: OpenAI model families on the o200k tokenizer. tiktoken only knows the ids
#: that existed when it was released; a newer id of the same family
#: (``gpt-5.4-mini``) must not silently fall back to cl100k, which counts German
#: text ~15 % higher than the tokenizer the provider bills with.
_O200K_PREFIXES = ("gpt-4o", "gpt-4.1", "gpt-4.5", "gpt-5", "chatgpt-", "o1", "o3", "o4")


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
        if (model_id or "").lower().startswith(_O200K_PREFIXES):
            return tiktoken.get_encoding("o200k_base")
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
    overhead_tokens: Optional[Sequence[float]] = None,
) -> TokenEstimate:
    """
    Estimate input + output tokens per LLM call for `model_id` given a sample
    of rendered prompts (strings). Returns a TokenEstimate with mean/p95 input
    tokens and the heuristic output token estimate.

    ``overhead_tokens`` (aligned with ``prompt_samples``) adds input the
    rendered text does not contain, e.g. the system prompt and the strict JSON
    schema of a judge call (see :func:`sample_judge_prompts`).

    Caching: keyed on (project_id, model_id, sha256(joined_prompts)). 1h TTL.
    """
    overhead = [float(o or 0) for o in (overhead_tokens or [])]
    overhead += [0.0] * (len(prompt_samples) - len(overhead))
    joined = "\n\n".join(prompt_samples) + f"|{sum(overhead)}"
    cache_key = f"{project_id}:{model_id}:{_hash_prompt(joined)}"
    now = time.time()

    cached = _CACHE.get(cache_key)
    if cached and (now - cached.cached_at) < _CACHE_TTL_SECONDS:
        return cached

    if not TIKTOKEN_AVAILABLE:
        # Fall back to a crude chars/4 heuristic so the endpoint still returns
        # a number when tiktoken isn't installed (dev environments may skip
        # the optional dependency).
        char_lengths = [len(p) for p in prompt_samples]
        token_lengths = [c / 4 for c in char_lengths]
        encoding_name = "chars/4 (no tiktoken)"
    else:
        enc = _encoding_for_model(model_id)
        token_lengths = [len(enc.encode(p)) for p in prompt_samples]
        encoding_name = enc.name if hasattr(enc, "name") else "cl100k_base"
    token_lengths = [length + extra for length, extra in zip(token_lengths, overhead)]

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


def sample_prediction_inputs(
    *,
    db,
    project_id: str,
    sample_size: int = 10,
    seed: Optional[int] = None,
) -> List[str]:
    """Sample texts that approximate what an LLM judge actually sees.

    The judge input is roughly:
        judge_prompt_template (~500-1000 tokens, near-constant)
      + reference_text         (~1000-3000 tokens, per-config)
      + prediction             (~the model's full Gutachten — by far the
                               dominant component on the BenGER prompts)

    We return recent successful prediction texts because the prediction
    is the largest and most variable component. Estimating eval cost
    against the raw Sachverhalt (sample_task_texts) under-counts by
    ~3-5× — Gutachten outputs are 4-15K tokens, the Sachverhalt is
    ~1-3K. The estimator multiplies prompt length by token cost, so
    that's a ~3-5× under-estimate of the input bill.

    Falls back to sample_task_texts when the project has no successful
    generations yet (cold start).
    """
    from project_models import Task
    from models import Generation

    rows = (
        db.query(Generation.response_content)
        .join(Task, Task.id == Generation.task_id)
        .filter(Task.project_id == project_id)
        .filter(Generation.status == "completed")
        .filter(Generation.response_content.isnot(None))
        .order_by(Generation.created_at.desc())
        .limit(max(sample_size * 5, 50))
        .all()
    )
    texts: List[str] = [r[0] for r in rows if r[0]]
    if not texts:
        return sample_task_texts(db=db, project_id=project_id, sample_size=sample_size, seed=seed)

    if seed is not None:
        rng = random.Random(seed)
        if len(texts) > sample_size:
            texts = rng.sample(texts, sample_size)
        else:
            texts = list(texts)
    else:
        texts = texts[:sample_size]

    return texts


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
    tasks = _sample_tasks(db=db, project_id=project_id, sample_size=sample_size, seed=seed)
    if not tasks:
        return []

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


def _sample_tasks(*, db, project_id: str, sample_size: int, seed: Optional[int]) -> List[Any]:
    """The first ``sample_size * 5`` (min 50) tasks by id, then a seeded sample
    of ``sample_size`` (or the head slice without a seed)."""
    from project_models import Task

    tasks = (
        db.query(Task)
        .filter(Task.project_id == project_id)
        .order_by(Task.id)
        .limit(max(sample_size * 5, 50))
        .all()
    )
    if seed is not None:
        rng = random.Random(seed)
        if len(tasks) > sample_size:
            return rng.sample(tasks, sample_size)
        return list(tasks)
    return tasks[:sample_size]


# ---------------------------------------------------------------------------
# Rendered LLM-judge prompts
# ---------------------------------------------------------------------------

#: The ± band the estimate is quoted with (structured field + UI text).
ESTIMATE_ACCURACY_PERCENT = 20

#: Input every judge call carries beyond the rendered template: system prompt,
#: chat framing and the fixed rule block the rubric judge appends after the
#: template. A constant on purpose; the judge engine owns that text.
JUDGE_FIXED_OVERHEAD_TOKENS = 600

#: A multi-step judge answers against a strict JSON schema with one object
#: (score, max, reason) per step, which the provider bills as input. Calibrated
#: on prod calls against a 46-step Bewertungsbogen: rendered prompt 16.5k
#: tokens, billed input 18.4k to 19.6k.
JUDGE_SCHEMA_TOKENS_PER_STEP = 40

_JUDGE_PLACEHOLDER_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}|\{(\w+)\}")
_MUSTER_METRICS = ("llm_judge_falloesung", "llm_judge_rubric")


def _get_insensitive(data: Any, key: str) -> Any:
    if not isinstance(data, dict):
        return None
    if key in data:
        return data[key]
    lower = key.lower()
    for k, value in data.items():
        if isinstance(k, str) and k.lower() == lower:
            return value
    return None


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _is_human_field(pred_field: str) -> bool:
    return pred_field == "__all_human__" or pred_field.startswith("human:")


def _is_model_field(pred_field: str) -> bool:
    return pred_field == "__all_model__" or pred_field.startswith("model:")


def renders_judge_prompt(config: Dict[str, Any]) -> bool:
    """Whether :func:`sample_judge_prompts` can size this judge config.

    True for the Bewertungsbogen judge, for any config with its own prompt
    template, and for configs that grade human answers (whose text the legacy
    generation-output sample never contains). Model-side configs on the
    built-in prompts keep the generation-output sample.
    """
    metric = config.get("metric") or ""
    params = config.get("metric_parameters") or {}
    if metric == "llm_judge_rubric" or params.get("custom_prompt_template"):
        return True
    return any(not _is_model_field(pf) for pf in config.get("prediction_fields") or [])


def _judge_context(task_data: Dict[str, Any]) -> str:
    """The ``{context}`` block the workers build for a judge call."""
    context = _as_text(
        _get_insensitive(task_data, "text")
        or _get_insensitive(task_data, "input")
        or _get_insensitive(task_data, "sachverhalt")
    )
    blocks = [
        ("## Bearbeitervermerk\n\n", _get_insensitive(task_data, "bearbeitervermerk")),
        ("## Zusatzmaterial\n\n", _get_insensitive(task_data, "zusatzmaterial")),
        (
            "Zusätzliche Hinweise für die Korrektur (vom Aufgabensteller):\n",
            _get_insensitive(task_data, "korrekturhinweise"),
        ),
    ]
    for heading, value in blocks:
        body = _as_text(value).strip()
        if body:
            context = f"{context}\n\n{heading}{body}" if context else f"{heading}{body}"
    return context


def _judge_reference(task_data: Dict[str, Any], metric: str, reference_fields: Sequence[str]) -> str:
    if metric in _MUSTER_METRICS:
        muster = _get_insensitive(task_data, "musterloesung") or _get_insensitive(task_data, "musterlösung")
        if muster:
            return _as_text(muster)
    for ref in reference_fields or []:
        key = ref[5:] if ref.startswith("task.") else ref
        value = task_data.get(key)
        if value is not None:
            return _as_text(value)
    return ""


def _annotation_answer(result: Any, field: Optional[str]) -> Tuple[str, Dict[str, str]]:
    from annotation_utils import extract_all_field_values, extract_field_value

    outputs = {
        k: _as_text(v) for k, v in extract_all_field_values(result or []).items() if isinstance(v, str)
    }
    if field:
        return _as_text(extract_field_value(result or [], field)), outputs
    return "\n\n".join(outputs.values()), outputs


def _generation_answer(generation: Any, field: Optional[str]) -> Tuple[str, Dict[str, str]]:
    from annotation_utils import extract_all_field_values, extract_field_value

    parsed = getattr(generation, "parsed_annotation", None)
    outputs = {}
    if isinstance(parsed, list):
        outputs = {k: _as_text(v) for k, v in extract_all_field_values(parsed).items() if isinstance(v, str)}
        if field:
            value = extract_field_value(parsed, field)
            if value:
                return _as_text(value), outputs
    return _as_text(getattr(generation, "response_content", None)), outputs


def _judge_rubric_row(db, task_id: str, metric_parameters: Dict[str, Any]) -> Any:
    """Same row the worker grades with (active rubric, or the selector's)."""
    from project_models import TaskRubric

    generator = ((metric_parameters or {}).get("rubric_selector") or {}).get("generator_model_id")
    query = db.query(TaskRubric).filter(TaskRubric.task_id == task_id)
    if generator:
        return (
            query.filter(TaskRubric.generator_model_id == generator, TaskRubric.status != "archived")
            .order_by(TaskRubric.created_at.desc())
            .first()
        )
    return query.filter(TaskRubric.status == "active").first()


def _scored_steps(criteria: Any) -> int:
    if not isinstance(criteria, dict):
        return 0
    return sum(1 for d in criteria.values() if isinstance(d, dict) and d.get("max_score") is not None)


def _render_judge_template(template: str, variables: Dict[str, str]) -> str:
    """One pass over ``{var}`` / ``{{var}}``; unknown placeholders stay literal
    and substituted values are never scanned again."""
    def substitute(match: re.Match) -> str:
        key = match.group(1) or match.group(2)
        return variables[key] if key in variables else match.group(0)

    return _JUDGE_PLACEHOLDER_RE.sub(substitute, template)


class _AnswerPool:
    """Answers per task for the sampled tasks, with a project-wide fallback so
    a task nobody answered yet is still sized with a realistic answer."""

    def __init__(self, db, project_id: str, task_ids: List[str]):
        self.db = db
        self.project_id = project_id
        self.task_ids = task_ids
        self._annotations: Optional[Dict[str, List[Any]]] = None
        self._generations: Optional[Dict[str, List[Any]]] = None

    def _load_annotations(self) -> Dict[str, List[Any]]:
        if self._annotations is None:
            from project_models import Annotation

            rows = (
                self.db.query(Annotation.task_id, Annotation.result)
                .filter(Annotation.task_id.in_(self.task_ids), Annotation.was_cancelled.is_(False))
                .order_by(Annotation.created_at.desc())
                .limit(len(self.task_ids) * 10)
                .all()
            )
            if not rows:
                rows = (
                    self.db.query(Annotation.task_id, Annotation.result)
                    .filter(Annotation.project_id == self.project_id, Annotation.was_cancelled.is_(False))
                    .order_by(Annotation.created_at.desc())
                    .limit(1)
                    .all()
                )
            self._annotations = {}
            for task_id, result in rows:
                self._annotations.setdefault(task_id, []).append(result)
        return self._annotations

    def _load_generations(self) -> Dict[str, List[Any]]:
        if self._generations is None:
            from models import Generation
            from project_models import Task

            base = self.db.query(Generation).filter(
                Generation.status == "completed", Generation.response_content.isnot(None)
            )
            rows = (
                base.filter(Generation.task_id.in_(self.task_ids))
                .order_by(Generation.created_at.desc())
                .limit(len(self.task_ids) * 10)
                .all()
            )
            if not rows:
                rows = (
                    base.join(Task, Task.id == Generation.task_id)
                    .filter(Task.project_id == self.project_id)
                    .order_by(Generation.created_at.desc())
                    .limit(1)
                    .all()
                )
            self._generations = {}
            for gen in rows:
                self._generations.setdefault(gen.task_id, []).append(gen)
        return self._generations

    @staticmethod
    def _pick(by_task: Dict[str, List[Any]], task_id: str) -> Any:
        if by_task.get(task_id):
            return by_task[task_id][0]
        return next((rows[0] for rows in by_task.values() if rows), None)

    def answer(self, task_id: str, pred_field: str) -> Tuple[str, Dict[str, str]]:
        field = pred_field.split(":", 1)[1] if ":" in pred_field else (
            None if pred_field.startswith("__all_") else pred_field
        )
        if not _is_model_field(pred_field):
            result = self._pick(self._load_annotations(), task_id)
            if result is not None:
                text, outputs = _annotation_answer(result, field)
                if text or _is_human_field(pred_field):
                    return text, outputs
        if not _is_human_field(pred_field):
            gen = self._pick(self._load_generations(), task_id)
            if gen is not None:
                return _generation_answer(gen, field)
        return "", {}


def sample_judge_prompts(
    *,
    db,
    project_id: str,
    configs: List[Dict[str, Any]],
    sample_size: int = 10,
    seed: Optional[int] = None,
) -> List[Tuple[str, float]]:
    """Render the prompt an LLM judge call would send, per config and sampled
    task, without calling a model.

    Each sample is ``(rendered_text, overhead_tokens)``. The text mirrors the
    workers' binding: ``{context}`` (case text plus Bearbeitervermerk,
    Zusatzmaterial and Korrekturhinweise blocks), ``{ground_truth}`` (the
    Musterlösung for Falllösung / Bewertungsbogen judges, else the reference
    field), ``{prediction}`` (an annotation for human-side fields, a completed
    generation for model-side ones), every task-data key, the answer's own
    fields and, for ``llm_judge_rubric``, ``{bewertungsbogen}`` rendered from
    the task's rubric row. A config without a template is sized as those parts
    joined. ``overhead_tokens`` covers the system prompt, the fixed rule block
    and the strict per-step response schema.

    ``configs`` are dicts with ``metric``, ``prediction_fields``,
    ``metric_parameters`` and optionally ``reference_fields``.
    """
    from rubric_structure import rubric_prompt_text

    tasks = _sample_tasks(db=db, project_id=project_id, sample_size=sample_size, seed=seed)
    if not tasks or not configs:
        return []
    answers = _AnswerPool(db, project_id, [t.id for t in tasks])

    samples: List[Tuple[str, float]] = []
    for config in configs:
        metric = config.get("metric") or ""
        params = config.get("metric_parameters") or {}
        template = params.get("custom_prompt_template")
        pred_fields = list(config.get("prediction_fields") or []) or ["__all_model__"]
        for task in tasks:
            data = task.data if isinstance(task.data, dict) else {}
            answer, outputs = answers.answer(task.id, pred_fields[0])
            sheet = ""
            steps = _scored_steps(params.get("custom_criteria"))
            if metric == "llm_judge_rubric":
                rubric = _judge_rubric_row(db, task.id, params)
                if rubric is not None:
                    sheet = rubric_prompt_text(rubric, include_grade_scale=False)
                    steps = _scored_steps(rubric.criteria)
                else:
                    sheet = _as_text(_get_insensitive(data, "bewertungsbogen"))
            context = _judge_context(data)
            reference = _judge_reference(data, metric, config.get("reference_fields") or [])
            if template:
                variables: Dict[str, str] = {
                    "context": context or "No additional context provided.",
                    "ground_truth": reference,
                    "prediction": answer,
                }
                for key, value in data.items():
                    if isinstance(key, str) and key.isidentifier() and value is not None:
                        variables[key] = _as_text(value)
                if metric == "llm_judge_rubric":
                    variables["bewertungsbogen"] = sheet
                variables.update({k: v for k, v in outputs.items() if k.isidentifier()})
                text = _render_judge_template(template, variables)
            else:
                text = "\n\n".join(part for part in (context, reference, sheet, answer) if part)
            overhead = JUDGE_FIXED_OVERHEAD_TOKENS + JUDGE_SCHEMA_TOKENS_PER_STEP * steps
            samples.append((text, float(overhead)))
    return samples

