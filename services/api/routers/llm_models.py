"""
LLM models endpoints.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import LLMModel as DBLLMModel

try:
    from shared.ai_services.provider_capabilities import PROVIDER_CAPABILITIES
except ImportError:
    PROVIDER_CAPABILITIES = {}

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/llm_models", tags=["llm_models"])


# ============= Response Models =============


class LLMModelResponse(BaseModel):
    """Response model for LLM models from database"""

    model_config = {"protected_namespaces": ()}

    id: str
    name: str
    description: Optional[str] = None
    provider: str
    model_type: str
    capabilities: List[str] = []
    config_schema: Optional[Dict[str, Any]] = None
    default_config: Optional[Dict[str, Any]] = None
    input_cost_per_million: Optional[float] = None
    output_cost_per_million: Optional[float] = None
    parameter_constraints: Optional[Dict[str, Any]] = None
    is_active: bool = True
    created_at: datetime
    updated_at: Optional[datetime] = None


# ============= Endpoints =============


@router.get("/public/models", response_model=List[LLMModelResponse])
async def get_public_llm_models(
    db: Session = Depends(get_db),
):
    """
    Get all active LLM models (public endpoint for Models page).
    No authentication required.
    """
    try:
        models = db.query(DBLLMModel).filter(DBLLMModel.is_active.is_(True)).all()

        result = []
        for model in models:
            result.append(
                LLMModelResponse(
                    id=model.id,
                    name=model.name,
                    description=model.description,
                    provider=model.provider,
                    model_type=model.model_type,
                    capabilities=model.capabilities,
                    config_schema=model.config_schema,
                    default_config=model.default_config,
                    input_cost_per_million=model.input_cost_per_million,
                    output_cost_per_million=model.output_cost_per_million,
                    parameter_constraints=model.parameter_constraints,
                    is_active=model.is_active,
                    created_at=model.created_at,
                    updated_at=model.updated_at,
                )
            )

        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving LLM models: {str(e)}",
        )


@router.get("/public/provider-capabilities")
async def get_provider_capabilities():
    """
    Get provider capabilities (temperature, structured output, determinism).
    Public endpoint for the Models page. Single source of truth from provider_capabilities.py.
    """
    result = {}
    for key, data in PROVIDER_CAPABILITIES.items():
        result[key] = {
            "display_name": data.get("display_name", key.title()),
            "temperature": data.get("temperature", {}),
            "structured_output": {
                "method": str(data.get("structured_output", {}).get("method", "prompt_based")),
                "strict_mode": data.get("structured_output", {}).get("strict_mode", False),
                "guaranteed": data.get("structured_output", {}).get("guaranteed", False),
            },
            "determinism": data.get("determinism", {}),
        }
    return result
