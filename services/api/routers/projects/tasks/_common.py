"""Shared imports, router, and helpers for the tasks router package."""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import String, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from auth_module import require_user
from auth_module.models import User as AuthUser
from database import get_async_db, get_db
from models import EvaluationRun, Generation, TaskEvaluation, User
from project_models import (
    Annotation,
    PostAnnotationResponse,
    Project,
    ProjectOrganization,
    SkippedTask,
    Task,
    TaskAssignment,
)
from project_schemas import SkipTaskRequest, SkipTaskResponse, TaskResponse
from routers.projects.helpers import (
    check_project_accessible,
    check_project_accessible_async,
    check_task_assigned_to_user,
    check_task_assigned_to_user_async,
    check_user_can_edit_project,
    check_user_can_edit_project_async,
    check_user_can_edit_task_data,
    check_user_can_edit_task_data_async,
    enforce_project_read_window_async,
    enforce_project_write_window_async,
    get_org_context_from_request,
    get_user_with_memberships,
    get_user_with_memberships_async,
)

router = APIRouter()


# Explicit export surface. ``from ._common import *`` binds exactly these names,
# so the concern submodules (export / fields / listing / metadata_ops /
# mutations) no longer need to repeat an explicit ``from ._common import (...)``
# block just to dodge F405 — this single list documents the shared surface once.
# It is the FULL set of public names this module binds (every import above plus
# ``router``), so the star binding is unchanged.
__all__ = [
    # stdlib / typing
    "json",
    "uuid",
    "datetime",
    "Any",
    "Dict",
    "List",
    "Optional",
    # fastapi
    "APIRouter",
    "Depends",
    "HTTPException",
    "Query",
    "Request",
    # sqlalchemy
    "String",
    "and_",
    "func",
    "or_",
    "select",
    "AsyncSession",
    "Session",
    # auth_module
    "require_user",
    "AuthUser",
    # database
    "get_async_db",
    "get_db",
    # models
    "EvaluationRun",
    "Generation",
    "TaskEvaluation",
    "User",
    # project_models
    "Annotation",
    "PostAnnotationResponse",
    "Project",
    "ProjectOrganization",
    "SkippedTask",
    "Task",
    "TaskAssignment",
    # project_schemas
    "SkipTaskRequest",
    "SkipTaskResponse",
    "TaskResponse",
    # routers.projects.helpers
    "check_project_accessible",
    "check_project_accessible_async",
    "check_task_assigned_to_user",
    "check_task_assigned_to_user_async",
    "check_user_can_edit_project",
    "check_user_can_edit_project_async",
    "check_user_can_edit_task_data",
    "check_user_can_edit_task_data_async",
    "enforce_project_read_window_async",
    "enforce_project_write_window_async",
    "get_org_context_from_request",
    "get_user_with_memberships",
    "get_user_with_memberships_async",
    # this module
    "router",
]
