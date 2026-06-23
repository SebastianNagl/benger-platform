"""
Reusable FastAPI dependencies for project-scoped routers.

The project routers repeat a near-identical access preamble dozens of times::

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    org_context = get_org_context_from_request(request)
    if not check_project_accessible(db, current_user, project_id, org_context):
        raise HTTPException(status_code=403, detail="Access denied")

``require_project_access`` factors that preamble into a single FastAPI
dependency. It loads the project, resolves the org context, runs the existing
``check_project_accessible`` authorization helper, raises the same 404/403
status codes with the same messages, and hands the resolved objects back to the
handler via a small :class:`ProjectAccess` container — so adopting it changes
neither behavior nor the HTTP contract.

Authorization semantics are intentionally unchanged: this dependency only calls
the canonical ``check_project_accessible`` (and, when ``min_role="edit"``,
``check_user_can_edit_project``) that already live in ``helpers.py``. It adds no
new policy of its own.

Adoption note: several existing project endpoints have unit tests that patch the
authorization helpers on the *handler's own module* (e.g.
``@patch("routers.projects.tasks.check_project_accessible")``). Because this
dependency calls the helper from ``routers.projects.deps`` instead, those
endpoints cannot adopt the dependency without also re-pointing their test
patches. New endpoints (and any endpoint whose tests patch
``routers.projects.deps.*`` or go through the real authorization path) can use it
as a clean drop-in.
"""

from typing import Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_module import require_user
from database import get_async_db
from project_models import Project

from routers.projects.helpers import (
    check_project_accessible_async,
    check_user_can_edit_project_async,
    get_org_context_from_request,
)


class ProjectAccess:
    """Resolved project-access context returned by ``require_project_access``.

    Attributes:
        project: The loaded :class:`Project` (guaranteed non-None).
        user: The authenticated user.
        org_context: The organization context resolved from the request
            (``request.state`` or the ``X-Organization-Context`` header), or
            ``None`` in legacy mode.
    """

    __slots__ = ("project", "user", "org_context")

    def __init__(self, project: Project, user, org_context: Optional[str]):
        self.project = project
        self.user = user
        self.org_context = org_context


def require_project_access(
    min_role: str = "view",
    *,
    not_found_detail: str = "Project not found",
    access_denied_detail: str = "Access denied",
    edit_denied_detail: str = "You don't have permission to edit this project",
):
    """Build a FastAPI dependency that enforces project access.

    Args:
        min_role: ``"view"`` (default) checks read access via
            ``check_project_accessible``; ``"edit"`` additionally requires
            ``check_user_can_edit_project``.
        not_found_detail: Detail message for the 404 when the project is absent.
        access_denied_detail: Detail message for the 403 on failed read access.
        edit_denied_detail: Detail message for the 403 on failed edit access.

    Returns:
        A dependency callable yielding a :class:`ProjectAccess`. It raises
        ``HTTPException`` 404 / 403 with the same status codes and (by default)
        the same messages the inline preamble used.
    """

    async def _dependency(
        project_id: str,
        request: Request,
        current_user=Depends(require_user),
        db: AsyncSession = Depends(get_async_db),
    ) -> ProjectAccess:
        result = await db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=404, detail=not_found_detail)

        org_context = get_org_context_from_request(request)
        if not await check_project_accessible_async(
            db, current_user, project_id, org_context, project=project
        ):
            raise HTTPException(status_code=403, detail=access_denied_detail)

        if min_role == "edit" and not await check_user_can_edit_project_async(
            db, current_user, project_id
        ):
            raise HTTPException(status_code=403, detail=edit_denied_detail)

        return ProjectAccess(project=project, user=current_user, org_context=org_context)

    return _dependency
