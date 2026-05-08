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

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth_module import require_user
from database import get_db
from models import LLMModel, User
from project_models import Project
from routers.projects.helpers import check_project_accessible, get_org_context_from_request
from services.token_estimation import (
    estimate_tokens_for_calls,
    sample_prediction_inputs,
    sample_task_texts,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/llm-models", tags=["cost-estimate"])


class CostEstimateRequest(BaseModel):
    project_id: str
    mode: Literal["generation", "evaluation"]
    model_ids: List[str] = Field(default_factory=list)
    judge_models: List[str] = Field(default_factory=list)  # eval ensemble
    runs_per_call: int = Field(default=1, ge=1, le=25)
    samples_per_task: int = Field(default=1, ge=1, le=10)
    task_sample_size: int = Field(default=10, ge=1, le=50)
    # Without these the estimator counts every (task, structure) combo for
    # every model, even when the user picked "Generate missing" — which
    # only fires the cells whose latest gen failed or is absent. Mirror
    # the trigger endpoint's `mode` and `structure_keys` so the cost
    # number matches what the worker will actually queue.
    generation_mode: Optional[Literal["all", "missing", "single"]] = None
    structure_keys: Optional[List[str]] = None


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
    per_model: List[PerModelCost]
    total_usd: float
    token_estimate: TokenBreakdown
    note: str


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


def _count_evaluation_judge_calls(
    db: Session,
    project_id: str,
    judge_model_id: str,
    runs_per_call: int,
    generation_mode: Optional[str],
) -> int:
    """Count (task × run_index) judge calls that would actually fire for
    `judge_model_id`.

    Each LLM-judge metric records one row per judge invocation in
    `evaluation_judge_runs` (linked via `evaluation_id` to the
    `evaluation_runs` row carrying the project + task). For an ensemble
    of size N, every task fans out into N parallel judge runs at each
    `run_index`. That's the API-call boundary, so it's also the cost
    boundary.

    - mode in ('all', None): every (task × run_index) is one call.
    - mode == 'missing': a call counts only when no completed
      `evaluation_judge_runs` row exists for this (task, judge,
      run_index). Mirrors the worker's `evaluate_missing_only` decision
      in services/workers/tasks.py around line 2722, which skips a
      task once a successful judge run is on file.

    Deterministic metrics (BERTScore/BLEU/exact_match/etc.) do not
    appear here — they don't go through `evaluation_judge_runs` and
    incur compute time, not API cost.
    """
    from project_models import Task
    from models import EvaluationRun, EvaluationJudgeRun

    task_ids = [r[0] for r in db.query(Task.id).filter(Task.project_id == project_id).all()]
    if not task_ids or runs_per_call <= 0:
        return 0

    if generation_mode != "missing":
        return len(task_ids) * runs_per_call

    # Bulk-load all completed (task_id, run_index) pairs for this judge
    # once per call instead of N×M individual queries.
    done_rows = (
        db.query(EvaluationRun.task_id, EvaluationJudgeRun.run_index)
        .join(EvaluationJudgeRun, EvaluationJudgeRun.evaluation_id == EvaluationRun.id)
        .filter(
            EvaluationRun.project_id == project_id,
            EvaluationJudgeRun.judge_model_id == judge_model_id,
            EvaluationJudgeRun.status == "completed",
        )
        .distinct()
        .all()
    )
    done = {(tid, ri) for tid, ri in done_rows}

    cells = 0
    for tid in task_ids:
        for ri in range(runs_per_call):
            if (tid, ri) not in done:
                cells += 1
    return cells


def _count_cells_to_generate(
    db: Session,
    project_id: str,
    model_id: str,
    structure_keys: Optional[List[str]],
    generation_mode: Optional[str],
) -> int:
    """Count (task, structure) cells that would actually fire for `model_id`.

    Mirrors the should_generate() decision in
    services/api/routers/generation_task_list.py around lines 555-585:

    - mode in ('all', 'single', None): every (task, structure) cell counts,
      regardless of existing generations.
    - mode == 'missing': a cell counts only when the latest matching
      `response_generations` row has status='failed' or no row exists
      at all. Cells whose latest is `completed`/`pending`/`running` are
      skipped — they wouldn't be re-queued.

    The cell count, not raw task count, is what drives cost: with one
    structure active and 14/15 tasks already succeeded, "Generate missing"
    fires 1 cell, not 15.
    """
    from project_models import Task
    from models import ResponseGeneration as DBResponseGeneration

    task_ids = [r[0] for r in db.query(Task.id).filter(Task.project_id == project_id).all()]
    if not task_ids:
        return 0
    structures: List[Optional[str]] = list(structure_keys) if structure_keys else [None]

    if generation_mode != "missing":
        return len(task_ids) * len(structures)

    # mode == "missing": check latest row per (task, model, structure)
    from sqlalchemy import case
    cells = 0
    for task_id in task_ids:
        for sk in structures:
            q = db.query(DBResponseGeneration).filter(
                DBResponseGeneration.task_id == task_id,
                DBResponseGeneration.model_id == model_id,
            )
            if sk is not None:
                # Match exact structure_key, falling back to legacy NULL rows
                # — same precedence the worker uses
                # (generation_task_list.py:196-208).
                q = q.filter(
                    (DBResponseGeneration.structure_key == sk)
                    | (DBResponseGeneration.structure_key.is_(None))
                ).order_by(
                    case((DBResponseGeneration.structure_key == sk, 0), else_=1),
                    DBResponseGeneration.created_at.desc(),
                )
            else:
                q = q.filter(DBResponseGeneration.structure_key.is_(None)).order_by(
                    DBResponseGeneration.created_at.desc()
                )
            latest = q.first()
            if latest is None or latest.status == "failed":
                cells += 1
    return cells


@router.post("/cost-estimate", response_model=CostEstimateResponse)
def estimate_cost(
    request: CostEstimateRequest,
    raw_request: Request,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> CostEstimateResponse:
    """Estimate total cost for a planned generation or evaluation trigger."""

    project = db.query(Project).filter(Project.id == request.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    org_context = get_org_context_from_request(raw_request)
    if not check_project_accessible(db, current_user, request.project_id, org_context):
        raise HTTPException(status_code=403, detail="Access denied")

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
            cells = _count_evaluation_judge_calls(
                db=db,
                project_id=request.project_id,
                judge_model_id=model_id,
                runs_per_call=request.runs_per_call,
                generation_mode=request.generation_mode,
            )
            # The judge-call count already factors run_index, so don't
            # multiply by runs_per_call again below.
            runs_already_counted = True
        else:
            cells = _count_cells_to_generate(
                db=db,
                project_id=request.project_id,
                model_id=model_id,
                structure_keys=request.structure_keys,
                generation_mode=request.generation_mode,
            )
            runs_already_counted = False

        token_est = estimate_tokens_for_calls(
            project_id=request.project_id,
            model_id=model_id,
            prompt_samples=sample_texts,
            max_output_tokens=model_max_tokens,
            output_utilization=utilization,
        )
        if token_breakdown is None:
            token_breakdown = TokenBreakdown(
                input_mean=token_est.input_mean,
                input_p95=token_est.input_p95,
                output_estimate=token_est.output_estimate,
                encoding=token_est.encoding_name,
            )

        pricing = _resolve_pricing(db, model_id)
        pricing_known = pricing is not None
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
        per_run = per_call * cells * request.samples_per_task
        # For evaluation, `cells` is already (tasks × run_index) so the
        # outer runs_per_call multiplier would double-count. For
        # generation it stays 1× per cell so the multiplier still applies.
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
        f" Counting only the cells that would actually fire under "
        f"generation_mode='{request.generation_mode}'"
        if request.generation_mode == "missing"
        else " Counting every (task × structure) cell"
    )
    if request.mode == "evaluation":
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
    note = (
        "Estimate accuracy ± ~20%. Token counts use cl100k_base as a proxy "
        "for non-OpenAI models. Each model's max_tokens is read from "
        "selected_configuration.model_configs, falling back to the project "
        "default." + utilization_note + mode_note + "."
    )

    return CostEstimateResponse(
        mode=request.mode,
        runs_per_call=request.runs_per_call,
        sample_size=len(sample_texts),
        tasks_total=total_tasks,
        per_model=per_model_costs,
        total_usd=round(total_usd, 2),
        token_estimate=token_breakdown,
        note=note,
    )
