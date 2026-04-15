"""
Debug endpoints - DEPRECATED

removed during the migration to the project-based annotation system.

New debug functionality should be implemented for the project-based system.
"""

import logging

from fastapi import APIRouter, Depends

from auth_module import User, require_superadmin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/debug", tags=["debug"], dependencies=[Depends(require_superadmin)])


@router.get("/status")
async def debug_status(current_user: User = Depends(require_superadmin)):
    """ """
    return {
        "status": "deprecated",
        "migration_date": "2025-01-19",
        "recommendation": "Use project-based debugging tools instead",
    }
