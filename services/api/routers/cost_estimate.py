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
from services.token_estimation import estimate_tokens_for_calls, sample_task_texts

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


class PerModelCost(BaseModel):
    model_id: str
    per_call_usd: float
    per_run_usd: float
    total_usd: float
    pricing_known: bool


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

    # Sample task texts for prompt-length estimation. For evaluation we use
    # the same texts; the actual evaluation prompt wraps prediction +
    # reference but the order of magnitude is similar.
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
        utilization = (
            _REASONING_OUTPUT_UTILIZATION if is_reasoning else _DEFAULT_OUTPUT_UTILIZATION
        )

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
            ))
            continue

        per_call = (
            (token_est.input_mean / 1000.0) * pricing["input_per_1k"]
            + (token_est.output_estimate / 1000.0) * pricing["output_per_1k"]
        )
        per_run = per_call * total_tasks * request.samples_per_task
        model_total = per_run * request.runs_per_call

        per_model_costs.append(PerModelCost(
            model_id=model_id,
            per_call_usd=round(per_call, 4),
            per_run_usd=round(per_run, 4),
            total_usd=round(model_total, 2),
            pricing_known=True,
        ))
        total_usd += model_total

    if token_breakdown is None:  # all models lacked pricing; still surface tokens
        token_breakdown = TokenBreakdown(
            input_mean=0.0,
            input_p95=0.0,
            output_estimate=0.0,
            encoding="unavailable",
        )

    note = (
        "Estimate accuracy ± ~20%. Token counts use cl100k_base as a proxy "
        "for non-OpenAI models. Output utilization is 90% of max_tokens for "
        "reasoning-tier models (Pro/o-series — hidden reasoning tokens are "
        "billed as output) and 60% for non-reasoning models. Each model's "
        "max_tokens is read from selected_configuration.model_configs, "
        "falling back to the project default."
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
