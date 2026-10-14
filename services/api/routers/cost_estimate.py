"""
Cost estimate endpoint for the multi-run feature.

Returns a per-call / per-run / total cost estimate for a generation or
evaluation trigger. Pricing is read from the `llm_models` DB table (seeded
from `services/shared/seeds/llm_models.yaml`); token counts come from
`services/api/services/token_estimation.py` (tiktoken with cl100k_base proxy).

Estimate accuracy is best-effort — UI surfaces a "± ~20%" caveat.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from auth_module import require_user
from database import get_async_db
from models import LLMModel, User
from project_models import Project
from routers.projects.helpers import (
    check_project_accessible_async,
)
from evaluation_planning import judge_call_counts, judge_runs, plan_evaluation
from services.generation_planning import (
    StructureKeysRequired,
    plan_generation_cells_sync,
    run_structure_keys,
)
from services.token_estimation import (
    ESTIMATE_ACCURACY_PERCENT,
    JUDGE_OUTPUT_FIXED_TOKENS,
    JUDGE_OUTPUT_TOKENS_PER_STEP,
    estimate_tokens_for_calls,
    renders_judge_prompt,
    sample_judge_calls,
    sample_prediction_inputs,
    sample_task_texts,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/llm-models", tags=["cost-estimate"])


class EvalConfigForCost(BaseModel):
    """Subset of an evaluation config the cost endpoint needs to size the
    judge fan-out per prediction-field. Carries the metric name so we can
    mirror the worker's `llm_judge_falloesung` backward-compat rule
    (unprefixed prediction fields go to the annotation side for that
    metric only — see `services/workers/tasks.py` ~line 3291). The `id`
    names the stored config, so the judge-call count prices only the
    configs the user ticked instead of every config naming the judge."""
    id: Optional[str] = None
    metric: Optional[str] = None
    prediction_fields: List[str] = Field(default_factory=list)


class CostEstimateRequest(BaseModel):
    project_id: str
    mode: Literal["generation", "evaluation"]
    model_ids: List[str] = Field(default_factory=list)
    judge_models: List[str] = Field(default_factory=list)  # eval ensemble
    runs_per_call: int = Field(default=1, ge=1, le=25)
    samples_per_task: int = Field(default=1, ge=1, le=10)
    task_sample_size: int = Field(default=10, ge=1, le=50)
    # Evaluation scope filters (issue #69). When evaluation_configs is set
    # the eval cost is sized by (subject × prediction_field) pairs instead
    # of the legacy flat tasks-count formula. model_ids/annotator_user_ids
    # then narrow the generation/annotation subject pools respectively.
    annotator_user_ids: Optional[List[str]] = None
    evaluation_configs: List[EvalConfigForCost] = Field(default_factory=list)
    # Without these the estimator counts every (task, structure) combo for
    # every model, even when the user picked "Generate missing" — which
    # only fires the cells whose latest gen failed or is absent. Mirror
    # the trigger endpoint's `mode` and `structure_keys` so the cost
    # number matches what the worker will actually queue.
    generation_mode: Optional[Literal["all", "missing", "single"]] = None
    structure_keys: Optional[List[str]] = None

    @model_validator(mode="after")
    def _reject_cross_mode_keys(self) -> "CostEstimateRequest":
        """Eval-only keys silently passed in generation mode used to be
        ignored. Now reject so client bugs surface immediately instead of
        producing a cost number that doesn't reflect what the user
        intended."""
        if self.mode == "generation":
            offending = []
            if self.evaluation_configs:
                offending.append("evaluation_configs")
            if self.annotator_user_ids:
                offending.append("annotator_user_ids")
            if self.judge_models:
                offending.append("judge_models")
            if offending:
                raise ValueError(
                    f"{', '.join(offending)} are eval-only and must not be set "
                    "when mode == 'generation'"
                )
        return self


class PerModelCost(BaseModel):
    model_id: str
    per_call_usd: float
    per_run_usd: float
    total_usd: float
    pricing_known: bool
    cells_to_generate: int = 0


class TokenBreakdown(BaseModel):
    input_mean: float
    input_p95: float
    output_estimate: float
    encoding: str


class CostEstimateResponse(BaseModel):
    mode: Literal["generation", "evaluation"]
    runs_per_call: int
    sample_size: int
    tasks_total: int
    # Number of (subject × prediction_field) cells that will be (re-)scored
    # when mode == "evaluation" and evaluation_configs were provided. Zero
    # for generation mode and for the legacy eval path that did not pass
    # configs (in which case the cost falls back to tasks_total × samples).
    subject_count: int
    # ISO timestamp of when subject_count was computed (issue #69 follow-up
    # E4). Fresh on every endpoint call. Surfaced so the modal can render
    # an "as of HH:MM:SS" tooltip — the count depends on live DB state
    # (a generation completing changes it) and a user who waits seconds
    # between preview and Run-click otherwise has no way to tell their
    # estimate is stale.
    estimated_at: str
    per_model: List[PerModelCost]
    total_usd: float
    token_estimate: TokenBreakdown
    # English one-paragraph summary, kept for API clients; the UI phrases the
    # structured fields below in the reader's language instead.
    note: str
    accuracy_percent: int = ESTIMATE_ACCURACY_PERCENT
    encoding: str = ""
    # What the input tokens were counted on: raw task data, recent generation
    # outputs, or the rendered LLM-judge prompt (template, context, reference,
    # Bewertungsbogen, a sampled answer, system + schema overhead).
    input_basis: Literal["task_data", "generation_outputs", "rendered_judge_prompt"] = "task_data"
    # Share of max_tokens assumed as output; None when it varies per model
    # (generation: 90 for reasoning-tier models, 60 otherwise).
    output_utilization_percent: Optional[int] = None
    # How output tokens were estimated: a share of max_tokens, or (for
    # multi-step judges such as a Bewertungsbogen) a fixed part plus a share
    # per scored step.
    output_basis: Literal["utilization", "judge_steps"] = "utilization"
    missing_only: bool = False
    per_judge_cells: bool = False


def _count_eval_subjects(
    db: Session,
    project_id: str,
    evaluation_configs: List[EvalConfigForCost],
    model_ids: Optional[List[str]],
    annotator_user_ids: Optional[List[str]],
) -> int:
    """Count (subject × prediction_field) cells that the configured eval
    will (re-)score, scoped by the model + annotator filters. Generation
    rows are the subject for non-human fields; Annotation rows for human
    fields. Returns 0 when no configs are provided — the caller then falls
    back to the legacy tasks-count formula for backward-compat.

    Field classification (which fields are human vs LLM) is delegated to
    `services/shared/eval_field_classification.py` so the worker and the
    cost endpoint stay in lockstep, including extension-registered metrics
    that ship from `benger_extended`."""
    if not evaluation_configs:
        return 0

    from eval_field_classification import classify_pred_fields
    from services.eval_subject_pools import count_eval_subject_pools

    classified = [
        (cfg, classify_pred_fields(cfg.metric, cfg.prediction_fields))
        for cfg in evaluation_configs
    ]
    has_any_human_field = any(human for _, (human, _llm) in classified)
    has_any_llm_field = any(llm for _, (_human, llm) in classified)

    # The pools are shared with the evaluation-config save, which warns about
    # a config whose side has nothing to grade, so both read one definition.
    gen_count, ann_count = count_eval_subject_pools(
        db,
        project_id,
        model_ids=model_ids,
        annotator_user_ids=annotator_user_ids,
        generations=has_any_llm_field,
        annotations=has_any_human_field,
    )

    total = 0
    for _cfg, (human_fields, llm_fields) in classified:
        total += len(llm_fields) * gen_count + len(human_fields) * ann_count
    return total


def _resolve_pricing(db: Session, model_id: str) -> Optional[Dict[str, float]]:
    """Look up per-token cost from `llm_models` (Float columns quoted /1M tokens).
    Normalizes to USD per 1k tokens for downstream multiplication."""
    row = db.query(LLMModel).filter(LLMModel.id == model_id).first()
    if not row:
        return None
    in_per_m = row.input_cost_per_million
    out_per_m = row.output_cost_per_million
    if in_per_m is None and out_per_m is None:
        return None
    return {
        "input_per_1k": (float(in_per_m) / 1000.0) if in_per_m is not None else 0.0,
        "output_per_1k": (float(out_per_m) / 1000.0) if out_per_m is not None else 0.0,
    }


def _resolve_max_tokens_for_model(
    project_gen_config: Dict[str, Any],
    model_id: str,
    project_default: int,
) -> int:
    """Per-model `max_tokens` lookup.

    The cost estimate must mirror the worker's parameter-resolution chain
    (services/workers/tasks.py::_resolve_param) — otherwise an estimate
    computed against the project's 4 000 default while the actual call
    runs at the per-model 32 000 override (e.g. gpt-5.5-pro after the
    Pro-tier max_tokens bump) understates cost by ~8x.

    Priority (highest → lowest):
      1. selected_configuration.model_configs[model_id].max_tokens
      2. selected_configuration.parameters.max_tokens (passed in as project_default)
    """
    sel = (project_gen_config or {}).get("selected_configuration") or {}
    model_overrides = (sel.get("model_configs") or {}).get(model_id) or {}
    if "max_tokens" in model_overrides and model_overrides["max_tokens"]:
        return int(model_overrides["max_tokens"])
    return int(project_default)


def _is_reasoning_model(llm_model_row: LLMModel) -> bool:
    """A model is reasoning-tier if its catalog entry declares a
    reasoning-effort selector (default_config.reasoning_config) or a
    recommended reasoning_effort value. These are the cohorts whose
    output reliably approaches the configured max_tokens budget
    because hidden reasoning tokens are billed as output tokens.
    """
    dc = getattr(llm_model_row, "default_config", None) or {}
    if isinstance(dc, dict) and dc.get("reasoning_config"):
        return True
    rp = getattr(llm_model_row, "recommended_parameters", None) or {}
    if isinstance(rp, dict):
        rec_default = rp.get("default") or {}
        if isinstance(rec_default, dict) and rec_default.get("reasoning_effort"):
            return True
    return False


# Non-reasoning models rarely use more than ~60 % of the configured
# max_tokens budget on real prompts. Reasoning-tier models (Pro/o-series)
# routinely fill 80–95 % because hidden reasoning tokens count toward
# output. Picking 0.9 keeps the estimate slightly conservative without
# pretending every call hits the cap exactly.
_REASONING_OUTPUT_UTILIZATION = 0.9
_DEFAULT_OUTPUT_UTILIZATION = 0.6

# LLM judges output a structured score + short reasoning — typically
# 500-2000 tokens regardless of how high max_tokens is configured. Using
# the generation utilization (0.6 × 16K = 9.6K) over-counts the output
# bill by ~5× for a judge call. We pick 0.15 because typical judge
# `max_tokens` is 8K-16K and 0.15 × that = 1.2K-2.4K, the realistic band
# for a GPT-5-family judge producing JSON-shaped scoring + rationale.
_EVAL_OUTPUT_UTILIZATION = 0.15


def _run_eval_configs(project, request: "CostEstimateRequest") -> List[Dict[str, Any]]:
    """The stored configs a run started from the dialog grades: every enabled
    config, narrowed to the ticked ones when the client names them. A client
    that sends configs without ids keeps every enabled config."""
    eval_cfg = project.evaluation_config or {}
    if not isinstance(eval_cfg, dict):
        try:
            import json as _json

            eval_cfg = _json.loads(eval_cfg)
        except Exception:
            return []
    configs = [
        c for c in (eval_cfg.get("evaluation_configs") or [])
        if isinstance(c, dict) and c.get("enabled") is not False
    ]
    if request.evaluation_configs and all(c.id for c in request.evaluation_configs):
        selected = {c.id for c in request.evaluation_configs}
        configs = [c for c in configs if c.get("id") in selected]
    return configs


def _judge_configs(configs: List[Dict[str, Any]], judge_model_id: str) -> List[Dict[str, Any]]:
    """The ``llm_judge_*`` configs among ``configs`` that run this judge."""
    return [
        c for c in configs
        if (c.get("metric") or "").startswith("llm_judge_")
        and any(j == judge_model_id for j, _runs in judge_runs(c))
    ]


def _eval_judge_calls(
    db: Session, request: "CostEstimateRequest", configs: List[Dict[str, Any]]
) -> Dict[str, int]:
    """Judge calls per judge model for the run, from the planner the worker
    dispatches with (services/shared/evaluation_planning.py). Planned per
    config because the project dialog starts one run per config."""
    calls: Dict[str, int] = {}
    for config in configs:
        if not (config.get("metric") or "").startswith("llm_judge_"):
            continue
        plan = plan_evaluation(
            db,
            request.project_id,
            [config],
            # An explicit empty model list deselects the generation side.
            model_ids=request.model_ids if "model_ids" in request.model_fields_set else None,
            annotator_user_ids=request.annotator_user_ids,
            structure_keys=request.structure_keys,
            missing_only=request.generation_mode == "missing",
        )
        for judge, n in judge_call_counts(plan, [config]).items():
            calls[judge] = calls.get(judge, 0) + n
    return calls


def _has_completed_generations(db: Session, project_id: str) -> bool:
    from models import Generation
    from project_models import Task

    return (
        db.query(Generation.id)
        .join(Task, Task.id == Generation.task_id)
        .filter(Task.project_id == project_id, Generation.status == "completed")
        .first()
        is not None
    )


def _count_cells_to_generate(
    db: Session,
    project_id: str,
    model_id: str,
    structure_keys: List[Optional[str]],
    generation_mode: Optional[str],
) -> int:
    """(task, structure) cells a generation run queues for ``model_id``, from
    the planner the generate endpoint dispatches with
    (services/generation_planning.py)."""
    from project_models import Task

    task_ids = [r[0] for r in db.query(Task.id).filter(Task.project_id == project_id).all()]
    return len(
        plan_generation_cells_sync(
            db,
            project_id,
            task_ids,
            [model_id],
            list(structure_keys),
            generation_mode,
        )
    )


@router.post("/cost-estimate", response_model=CostEstimateResponse)
async def estimate_cost(
    request: CostEstimateRequest,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
) -> CostEstimateResponse:
    """Estimate total cost for a planned generation or evaluation trigger.

    The endpoint runs on the async lane for the project-existence check and the
    access-control gate. The cost computation itself is a deep graph of
    sync-only DB helpers (``_count_eval_subjects``, ``_count_evaluation_judge_calls``,
    ``_count_cells_to_generate``, ``_resolve_pricing`` …) plus the sync-only
    ``token_estimation`` samplers — none of which has an async twin and which
    all take ``db: Session``. Rather than partially convert (which the async
    playbook forbids — never mix ``db.query`` with ``await`` in one handler),
    the whole sync computation is bridged onto a sync ``Session`` bound to THIS
    async session's connection via ``await db.run_sync(...)``, so it runs inside
    the same transaction without opening a second connection.
    """
    # Async existence + access gate (read-only).
    project_exists = (
        await db.execute(select(Project.id).where(Project.id == request.project_id))
    ).scalar_one_or_none()
    if project_exists is None:
        raise HTTPException(status_code=404, detail="Project not found")

    if not await check_project_accessible_async(
        db, current_user, request.project_id
    ):
        raise HTTPException(status_code=403, detail="Access denied")

    # Bridge the sync-only cost computation onto a sync Session sharing this
    # async connection/transaction.
    return await db.run_sync(
        lambda sync_db: _compute_cost_estimate_impl(sync_db, request)
    )


def _compute_cost_estimate_impl(
    db: Session, request: CostEstimateRequest
) -> CostEstimateResponse:
    project = db.query(Project).filter(Project.id == request.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Pick the right model set to price.
    target_models = list(request.model_ids)
    if request.mode == "evaluation" and request.judge_models:
        # For evaluation cost, the spend is on the judge calls — the target
        # model has already been called during generation.
        target_models = list(request.judge_models)

    if not target_models:
        raise HTTPException(status_code=400, detail="model_ids required (or judge_models for evaluation)")

    # Sample texts to estimate input length.
    # - generation: raw task data (Sachverhalt) is what fills the prompt.
    # - evaluation: the judge sees `judge_prompt + reference + prediction`
    #   where the prediction (prior generation output) is by far the
    #   largest variable component. Sampling raw tasks here under-counts
    #   eval input tokens by 3-5× on Gutachten-style outputs and
    #   produces an embarrassingly small dollar figure.
    if request.mode == "evaluation":
        sample_texts = sample_prediction_inputs(
            db=db,
            project_id=request.project_id,
            sample_size=request.task_sample_size,
            seed=42,
        )
    else:
        sample_texts = sample_task_texts(
            db=db,
            project_id=request.project_id,
            sample_size=request.task_sample_size,
            seed=42,
        )
    if not sample_texts:
        sample_texts = [""]
    default_basis = "task_data"
    if request.mode == "evaluation" and _has_completed_generations(db, request.project_id):
        default_basis = "generation_outputs"
    input_basis = default_basis
    output_basis = "utilization"
    reported_sample_size = len(sample_texts)

    from project_models import Task

    total_tasks = db.query(Task).filter(Task.project_id == request.project_id).count()
    if total_tasks == 0:
        raise HTTPException(status_code=400, detail="Project has no tasks to estimate against")

    # Project-default max_tokens is the fallback when a model has no
    # per-model override. Per-model values (e.g. 32 000 for gpt-5.5-pro)
    # are read inside the loop because they vary by model.
    project_gen_config = project.generation_config or {}
    gen_params = project_gen_config.get("selected_configuration", {}).get("parameters", {})
    project_default_max_tokens = int(gen_params.get("max_tokens", 4000) or 4000)

    # Subject counting (issue #69): when the eval modal sends configs, size
    # the cost by actual (subject × prediction_field) cells the run will
    # touch, narrowed by model_ids/annotator_user_ids. Falls back to the
    # legacy tasks-count multiplier ONLY when no configs are supplied so
    # the cell-counting endpoint stays backwards-compatible. When configs
    # ARE supplied but yield zero subjects (e.g. user narrowed to a model
    # with no generations) the cost is genuinely zero — gating on
    # `subject_count > 0` here would incorrectly flip back to a full-sweep
    # estimate, so we gate on `evaluation_configs` instead.
    subject_count = 0
    if request.mode == "evaluation":
        # subject_count is the cell pool across the project for display only.
        # The per-model dollar math goes through _count_evaluation_judge_calls
        # below (per-judge, missing-aware). Issue #132: this used to drive
        # pricing and produced a 63x overshoot on partially-covered projects.
        subject_count = _count_eval_subjects(
            db=db,
            project_id=request.project_id,
            evaluation_configs=request.evaluation_configs,
            model_ids=request.model_ids or None,
            annotator_user_ids=request.annotator_user_ids,
        )

    # Evaluation: the configs the run grades and the judge calls they make,
    # planned once for every judge priced below.
    run_configs: List[Dict[str, Any]] = []
    calls_by_judge: Dict[str, int] = {}
    if request.mode == "evaluation":
        run_configs = _run_eval_configs(project, request)
        calls_by_judge = _eval_judge_calls(db, request, run_configs)
    else:
        # Generation: the structures the run generates, as the endpoint
        # resolves them. An explicit [] is the dialog with no structure
        # ticked (it won't start like that): nothing to price. Omitting the
        # field on a project with structures is a 422, as on the endpoint.
        if request.structure_keys == []:
            gen_structure_keys = []
        else:
            try:
                gen_structure_keys = run_structure_keys(
                    project.generation_config, request.structure_keys
                )
            except StructureKeysRequired as e:
                raise HTTPException(status_code=422, detail=str(e))

    per_model_costs: List[PerModelCost] = []
    total_usd = 0.0
    token_breakdown: Optional[TokenBreakdown] = None

    for model_id in target_models:
        # Each model can carry its own max_tokens override and its own
        # reasoning-tier classification. Cost estimates must reflect what
        # the worker will actually send, not the project default.
        model_max_tokens = _resolve_max_tokens_for_model(
            project_gen_config, model_id, project_default_max_tokens
        )
        llm_model_row = db.query(LLMModel).filter(LLMModel.id == model_id).first()
        is_reasoning = bool(llm_model_row and _is_reasoning_model(llm_model_row))
        if request.mode == "evaluation":
            # Judges emit a small structured score + reasoning, not the
            # full max_tokens budget — see _EVAL_OUTPUT_UTILIZATION.
            utilization = _EVAL_OUTPUT_UTILIZATION
        elif is_reasoning:
            utilization = _REASONING_OUTPUT_UTILIZATION
        else:
            utilization = _DEFAULT_OUTPUT_UTILIZATION

        # Cell count is per-model and per-mode:
        # - generation: count (task × structure) cells with no recent
        #   successful response_generations row (for mode=missing).
        # - evaluation: count (task × run_index) judge calls with no
        #   successful evaluation_judge_runs row for this judge model.
        # Without the eval-specific path the estimator would query the
        # generations table for evaluation runs — counting whichever
        # generations were missing instead of which judge calls are
        # missing. Different question, different answer.
        if request.mode == "evaluation":
            cells = calls_by_judge.get(model_id, 0)
            # The judge-call count already factors run_index, so don't
            # multiply by runs_per_call again below.
            runs_already_counted = True
        else:
            cells = _count_cells_to_generate(
                db=db,
                project_id=request.project_id,
                model_id=model_id,
                structure_keys=gen_structure_keys,
                generation_mode=request.generation_mode,
            )
            runs_already_counted = False

        # LLM-judge input is the rendered judge prompt, not just the answer:
        # template, case context, Musterlösung, the Bewertungsbogen, the
        # student's or model's answer and the system/schema overhead. Size the
        # configs this judge runs from those parts; model-side configs on the
        # built-in prompts keep the generation-output sample.
        model_samples: List[str] = sample_texts
        model_overhead: Optional[List[float]] = None
        model_outputs: Optional[List[Optional[float]]] = None
        model_basis = default_basis
        if request.mode == "evaluation":
            judge_cfgs = _judge_configs(run_configs, model_id)
            rendered_cfgs = [c for c in judge_cfgs if renders_judge_prompt(c)]
            rendered = (
                sample_judge_calls(
                    db=db,
                    project_id=request.project_id,
                    configs=rendered_cfgs,
                    sample_size=request.task_sample_size,
                    seed=42,
                )
                if rendered_cfgs
                else []
            )
            if rendered:
                model_samples = [text for text, _, _ in rendered]
                model_overhead = [extra for _, extra, _ in rendered]
                model_outputs = [output for _, _, output in rendered]
                if len(rendered_cfgs) < len(judge_cfgs):
                    model_samples = model_samples + list(sample_texts)
                    model_overhead = model_overhead + [0.0] * len(sample_texts)
                    model_outputs = model_outputs + [None] * len(sample_texts)
                model_basis = "rendered_judge_prompt"

        token_est = estimate_tokens_for_calls(
            project_id=request.project_id,
            model_id=model_id,
            prompt_samples=model_samples,
            max_output_tokens=model_max_tokens,
            output_utilization=utilization,
            overhead_tokens=model_overhead,
            output_tokens=model_outputs,
        )
        if model_outputs and any(o is not None for o in model_outputs):
            output_basis = "judge_steps"
        if token_breakdown is None:
            input_basis = model_basis
            reported_sample_size = len(model_samples)
            token_breakdown = TokenBreakdown(
                input_mean=token_est.input_mean,
                input_p95=token_est.input_p95,
                output_estimate=token_est.output_estimate,
                encoding=token_est.encoding_name,
            )

        pricing = _resolve_pricing(db, model_id)
        pricing is not None
        if pricing is None:
            per_model_costs.append(PerModelCost(
                model_id=model_id,
                per_call_usd=0.0,
                per_run_usd=0.0,
                total_usd=0.0,
                pricing_known=False,
                cells_to_generate=cells,
            ))
            continue

        per_call = (
            (token_est.input_mean / 1000.0) * pricing["input_per_1k"]
            + (token_est.output_estimate / 1000.0) * pricing["output_per_1k"]
        )
        # Eval mode prices the actual missing-aware per-judge cell count
        # returned by `_count_evaluation_judge_calls` (issue #132). The
        # per-judge function already folds in this config's per-judge `runs`,
        # so `runs_already_counted=True` and no global runs multiplier
        # applies. The legacy cells-based formula still drives the generation
        # path (`tasks × structure_keys × samples_per_task`).
        per_run = per_call * cells * request.samples_per_task
        model_total = per_run if runs_already_counted else per_run * request.runs_per_call

        per_model_costs.append(PerModelCost(
            model_id=model_id,
            per_call_usd=round(per_call, 4),
            per_run_usd=round(per_run, 4),
            total_usd=round(model_total, 2),
            pricing_known=True,
            cells_to_generate=cells,
        ))
        total_usd += model_total

    if token_breakdown is None:  # all models lacked pricing; still surface tokens
        token_breakdown = TokenBreakdown(
            input_mean=0.0,
            input_p95=0.0,
            output_estimate=0.0,
            encoding="unavailable",
        )

    mode_note = (
        " Counting only the cells that would actually fire under "
        f"generation_mode='{request.generation_mode}'"
        if request.generation_mode == "missing"
        else " Counting every (task × structure) cell"
    )
    if request.mode == "evaluation" and output_basis == "judge_steps":
        utilization_note = (
            " For evaluation, input is the rendered judge prompt (template, "
            "case context, reference, Bewertungsbogen and a sampled answer) "
            "plus system prompt and response-schema overhead; output is "
            f"{JUDGE_OUTPUT_FIXED_TOKENS} tokens plus {JUDGE_OUTPUT_TOKENS_PER_STEP} "
            "per scored step (score, reason and quoted evidence), reasoning "
            "tokens not included."
        )
    elif request.mode == "evaluation" and input_basis == "rendered_judge_prompt":
        utilization_note = (
            " For evaluation, input is the rendered judge prompt (template, "
            "case context, reference, Bewertungsbogen and a sampled answer) "
            "plus system prompt and response-schema overhead, and output "
            "utilization is 15 % of max_tokens — judges emit a short score + "
            "rationale, not a full completion."
        )
    elif request.mode == "evaluation":
        utilization_note = (
            " For evaluation, input is sampled from recent generation outputs "
            "(the prediction the judge sees) and output utilization is 15 % of "
            "max_tokens — judges emit a short score + rationale, not a full "
            "completion."
        )
    else:
        utilization_note = (
            " Output utilization is 90 % of max_tokens for reasoning-tier "
            "models (Pro/o-series) and 60 % otherwise."
        )
    # E2 (issue #69): the eval-with-configs path introduces additional
    # approximation sources beyond the ±20% disclaimer. Surface them when
    # active (see the `if eval_uses_subject_count` branch below) so the
    # user knows the variance band is wider for scoped runs.
    note = (
        f"Estimate accuracy ± ~{ESTIMATE_ACCURACY_PERCENT}%. Token counts use cl100k_base as a proxy "
        "for non-OpenAI models. Each model's max_tokens is read from "
        "selected_configuration.model_configs, falling back to the project "
        "default." + utilization_note + mode_note + "."
    )
    if request.mode == "evaluation" and bool(request.evaluation_configs):
        note += (
            " Eval-mode estimates count cells per-judge, using each config's "
            "own per-judge `runs` value, and subtract cells that already have "
            "a successful task_evaluations row under "
            "`{config_id}|{prediction_field}|...`. Sparse prediction fields "
            "or generations missing the parsed field can shift the actual "
            "cost by ±20%."
        )

    from datetime import datetime, timezone

    return CostEstimateResponse(
        mode=request.mode,
        runs_per_call=request.runs_per_call,
        sample_size=reported_sample_size,
        tasks_total=total_tasks,
        subject_count=subject_count,
        # UTC ISO timestamp; the frontend formats to local time for display.
        estimated_at=datetime.now(timezone.utc).isoformat(),
        per_model=per_model_costs,
        total_usd=round(total_usd, 2),
        token_estimate=token_breakdown,
        note=note,
        accuracy_percent=ESTIMATE_ACCURACY_PERCENT,
        encoding=token_breakdown.encoding,
        input_basis=input_basis,
        output_basis=output_basis,
        output_utilization_percent=(
            round(_EVAL_OUTPUT_UTILIZATION * 100) if request.mode == "evaluation" else None
        ),
        missing_only=request.generation_mode == "missing",
        per_judge_cells=request.mode == "evaluation" and bool(request.evaluation_configs),
    )
