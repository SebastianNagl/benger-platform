"""Superadmin-only endpoints for managing the LLM model catalog.

The catalog is seeded from `services/api/seeds/llm_models.yaml` at startup,
gated by content hash. Use the reseed endpoint here to force a re-apply
without restarting the API container — useful after editing the YAML on a
running staging or prod environment.
"""

from __future__ import annotations

import glob
import logging
import os
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth_module.dependencies import require_superadmin
from database import get_db, initialize_llm_models
from models import User
from seeds.llm_models_loader import load_catalog
from ai_services.provider_capabilities import reload_cost_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/llm-models", tags=["admin", "llm-models"])

_LLM_SEED_FLAG_GLOB = "/tmp/.benger_llm_seed_*.done"


@router.post("/reseed", response_model=Dict[str, Any])
def reseed_llm_models(
    current_user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Force re-apply the YAML catalog to the database.

    Useful after editing `seeds/llm_models.yaml` on a running deployment.
    Clears the per-hash flag file so the next normal startup also re-runs
    if needed.
    """
    catalog = load_catalog()
    rows_changed = initialize_llm_models(db)
    reload_cost_cache()

    # Drop any pre-existing flag files so the seed isn't accidentally skipped
    # next startup; the lifespan code will recreate the right one.
    for stale in glob.glob(_LLM_SEED_FLAG_GLOB):
        try:
            os.remove(stale)
        except OSError as e:
            logger.warning("Could not remove stale flag %s: %s", stale, e)

    logger.info(
        "Manual reseed by %s: %d rows changed (catalog v%s)",
        current_user.username,
        rows_changed,
        catalog.content_hash[:8],
    )
    return {
        "catalog_version": catalog.content_hash[:8],
        "models_in_catalog": len(catalog.models),
        "rows_changed": rows_changed,
        "sources": catalog.sources,
    }


@router.get("/catalog-version", response_model=Dict[str, Any])
def get_catalog_version(
    current_user: User = Depends(require_superadmin),
) -> Dict[str, Any]:
    """Return the content hash of the YAML the API is currently configured with.

    Compare against the deployed-vs-applied flag in /tmp to detect drift.
    """
    catalog = load_catalog()
    applied = sorted(
        os.path.basename(p).removeprefix(".benger_llm_seed_").removesuffix(".done")
        for p in glob.glob(_LLM_SEED_FLAG_GLOB)
    )
    return {
        "yaml_version": catalog.content_hash[:8],
        "yaml_full_hash": catalog.content_hash,
        "models_in_catalog": len(catalog.models),
        "sources": catalog.sources,
        "applied_versions": applied,
    }
