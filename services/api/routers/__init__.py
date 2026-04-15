"""
API Routers module.
Contains all endpoint routers organized by domain.
"""

from .auth import router as auth_router
from .dashboard import router as dashboard_router
from .evaluations import router as evaluations_router
from .generation import router as generation_router
from .generation_task_list import router as generation_task_list_router
from .health import router as health_router
from .llm_models import router as llm_models_router
from .notifications import router as notifications_router
from .storage import router as storage_router
from .users import router as users_router

__all__ = [
    "auth_router",
    "dashboard_router",
    "evaluations_router",
    "generation_router",
    "generation_task_list_router",
    "health_router",
    "llm_models_router",
    "notifications_router",
    "storage_router",
    "users_router",
]
