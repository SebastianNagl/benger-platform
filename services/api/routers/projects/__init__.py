"""
Projects API router - modular structure.

This module aggregates all project-related endpoints into sub-routers:
- crud: Core CRUD operations
- tasks: Task management
- annotations: Annotation operations
- assignments: Task assignment
- import_export: Import/export functionality
- bulk: Bulk operations
- organizations: Organization management
- members: Member management
- generation: LLM generation
- label_config_versions: Label config version management
"""

from fastapi import APIRouter

# Import all sub-routers
from routers.projects import (
    annotations,
    assignments,
    bulk,
    crud,
    drafts,
    generation,
    import_export,
    label_config_versions,
    members,
    questionnaire,
    tasks,
)

# Create main router with prefix
router = APIRouter(prefix="/api/projects", tags=["projects"])

# Include all sub-routers
# Order matters for route matching - more specific routes first

# Root-level operations (/, /bulk-*, /import-project, /tasks/*)
router.include_router(crud.router)
router.include_router(bulk.router)
router.include_router(import_export.router)

# Project-specific operations (/{project_id}/*)
router.include_router(tasks.router)
router.include_router(annotations.router)
router.include_router(assignments.router)
router.include_router(members.router)
router.include_router(generation.router)
router.include_router(drafts.router)
router.include_router(questionnaire.router)
router.include_router(label_config_versions.router)
