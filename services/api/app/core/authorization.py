"""
Centralized authorization service for the BenGER API.
Eliminates duplicate permission checking logic across routers.
"""

import logging
from enum import Enum
from functools import wraps
from typing import Callable, List, Optional

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth_module import User, require_user
from database import get_db
from project_models import Project

logger = logging.getLogger(__name__)


class Permission(Enum):
    """Enumeration of available permissions."""

    # Project permissions
    PROJECT_VIEW = "project:view"
    PROJECT_EDIT = "project:edit"
    PROJECT_DELETE = "project:delete"
    PROJECT_CREATE = "project:create"

    # Task permissions
    TASK_VIEW = "task:view"
    TASK_EDIT = "task:edit"
    TASK_DELETE = "task:delete"
    TASK_CREATE = "task:create"

    # Annotation permissions
    ANNOTATION_VIEW = "annotation:view"
    ANNOTATION_EDIT = "annotation:edit"
    ANNOTATION_DELETE = "annotation:delete"
    ANNOTATION_CREATE = "annotation:create"

    # Generation permissions
    GENERATION_VIEW = "generation:view"
    GENERATION_EDIT = "generation:edit"
    GENERATION_DELETE = "generation:delete"
    GENERATION_CREATE = "generation:create"

    # Organization permissions
    ORG_VIEW = "organization:view"
    ORG_EDIT = "organization:edit"
    ORG_DELETE = "organization:delete"
    ORG_CREATE = "organization:create"
    ORG_MANAGE_MEMBERS = "organization:manage_members"

    # Admin permissions
    ADMIN_VIEW = "admin:view"
    ADMIN_EDIT = "admin:edit"
    FEATURE_FLAG_MANAGE = "feature_flag:manage"


class AuthorizationService:
    """Service for handling authorization and permission checks."""

    def __init__(self):
        self.permission_cache = {}

    def _get_user_org_memberships(self, user, db: Session):
        """Get user organization memberships, handling both Pydantic and DB User models.

        The Pydantic User model has 'organizations' (list of dicts with id/name/role),
        while the DB User model has 'organization_memberships' (list of ORM objects).
        """
        if hasattr(user, 'organization_memberships') and user.organization_memberships is not None:
            return user.organization_memberships

        # Pydantic User model: query DB for actual memberships
        from routers.projects.helpers import get_user_with_memberships

        db_user = get_user_with_memberships(db, str(user.id))
        if db_user and db_user.organization_memberships:
            return db_user.organization_memberships
        return []

    def check_project_access(
        self,
        user: User,
        project: Project,
        permission: Permission,
        db: Session,
        org_context: "Optional[str]" = None,
    ) -> bool:
        """
        Check if a user has access to a project with specific permission.

        Args:
            user: User making the request
            project: Project to check access for
            permission: Required permission
            db: Database session
            org_context: Value of X-Organization-Context header.
                When provided, enforces context-aware checking:
                - "private" -> only creator's own private projects
                - org_id -> only check membership in that specific org
                When None, falls back to legacy behavior (any org membership).
        """
        # Superadmins have all permissions
        if user.is_superadmin:
            return True

        # Context-aware mode
        if org_context is not None:
            if org_context == "private":
                # Private mode: only creator's own private projects
                if not getattr(project, 'is_private', False):
                    return False
                return user.id == project.created_by

            # Org mode: project must belong to this specific org
            from project_models import ProjectOrganization

            project_orgs = (
                db.query(ProjectOrganization.organization_id)
                .filter(ProjectOrganization.project_id == project.id)
                .all()
            )
            project_org_ids = [org[0] for org in project_orgs] if project_orgs else []

            if org_context not in project_org_ids:
                return False

            # User must be a member of this specific org with the right role
            memberships = self._get_user_org_memberships(user, db)
            membership = next(
                (m for m in memberships if m.organization_id == org_context and m.is_active),
                None,
            )
            if not membership:
                return False
            return self._check_org_role_permission(membership.role, permission)

        # Legacy mode (org_context=None): backward compatibility
        # Private projects: only creator can access
        if getattr(project, 'is_private', False):
            return user.id == project.created_by

        # Check if user is project creator for edit/delete permissions
        if user.id == project.created_by:
            if permission in [
                Permission.PROJECT_VIEW,
                Permission.PROJECT_EDIT,
                Permission.PROJECT_DELETE,
            ]:
                return True

        # Check organization membership
        from project_models import ProjectOrganization

        project_orgs = (
            db.query(ProjectOrganization.organization_id)
            .filter(ProjectOrganization.project_id == project.id)
            .all()
        )
        project_org_ids = [org[0] for org in project_orgs] if project_orgs else []

        if project_org_ids:
            memberships = self._get_user_org_memberships(user, db)
            user_org_ids = [m.organization_id for m in memberships]
            for org_id in project_org_ids:
                if org_id in user_org_ids:
                    membership = next(
                        (m for m in memberships if m.organization_id == org_id),
                        None,
                    )
                    if membership:
                        return self._check_org_role_permission(membership.role, permission)

        return False

    def check_organization_access(
        self, user: User, organization_id: str, permission: Permission, db: Session
    ) -> bool:
        """
        Check if a user has access to an organization with specific permission.

        Args:
            user: User making the request
            organization_id: Organization ID to check access for
            permission: Required permission
            db: Database session

        Returns:
            True if user has access, False otherwise
        """
        # Superadmins have all permissions
        if user.is_superadmin:
            return True

        # Check organization membership
        memberships = self._get_user_org_memberships(user, db)
        membership = next((m for m in memberships if m.organization_id == organization_id), None)

        if not membership:
            return False

        return self._check_org_role_permission(membership.role, permission)

    def _check_org_role_permission(self, role: str, permission: Permission) -> bool:
        """
        Check if an organization role has a specific permission.

        Args:
            role: Organization role (org_admin, contributor, annotator, user)
            permission: Required permission

        Returns:
            True if role has permission, False otherwise
        """
        # Normalize role to lowercase string for comparison
        role_str = role.value.lower() if hasattr(role, 'value') else str(role).lower()

        role_permissions = {
            "org_admin": [
                Permission.PROJECT_VIEW,
                Permission.PROJECT_EDIT,
                Permission.PROJECT_DELETE,
                Permission.PROJECT_CREATE,
                Permission.TASK_VIEW,
                Permission.TASK_EDIT,
                Permission.TASK_DELETE,
                Permission.TASK_CREATE,
                Permission.ANNOTATION_VIEW,
                Permission.ANNOTATION_EDIT,
                Permission.ANNOTATION_DELETE,
                Permission.ANNOTATION_CREATE,
                Permission.GENERATION_VIEW,
                Permission.GENERATION_EDIT,
                Permission.GENERATION_DELETE,
                Permission.GENERATION_CREATE,
                Permission.ORG_VIEW,
                Permission.ORG_EDIT,
                Permission.ORG_MANAGE_MEMBERS,
            ],
            "contributor": [
                Permission.PROJECT_VIEW,
                Permission.PROJECT_EDIT,
                Permission.PROJECT_CREATE,
                Permission.TASK_VIEW,
                Permission.TASK_EDIT,
                Permission.TASK_CREATE,
                Permission.TASK_DELETE,
                Permission.ANNOTATION_VIEW,
                Permission.ANNOTATION_EDIT,
                Permission.ANNOTATION_CREATE,
                Permission.ANNOTATION_DELETE,
                Permission.GENERATION_VIEW,
                Permission.GENERATION_EDIT,
                Permission.GENERATION_CREATE,
                Permission.GENERATION_DELETE,
                Permission.ORG_VIEW,
            ],
            "annotator": [
                Permission.PROJECT_VIEW,
                Permission.TASK_VIEW,
                Permission.ANNOTATION_VIEW,
                Permission.ANNOTATION_EDIT,
                Permission.ANNOTATION_CREATE,
                Permission.ORG_VIEW,
            ],
            "user": [
                Permission.PROJECT_VIEW,
                Permission.TASK_VIEW,
                Permission.ANNOTATION_VIEW,
                Permission.GENERATION_VIEW,
                Permission.ORG_VIEW,
            ],
        }

        return permission in role_permissions.get(role_str, [])

    def require_permission(
        self, permission: Permission, resource_getter: Optional[Callable] = None
    ):
        """
        Decorator to require specific permission for an endpoint.

        Args:
            permission: Required permission
            resource_getter: Optional function to get the resource (project, org, etc.)

        Returns:
            Decorator function
        """

        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def wrapper(
                *args,
                current_user: User = Depends(require_user),
                db: Session = Depends(get_db),
                **kwargs,
            ):
                # If resource_getter is provided, get the resource and check access
                if resource_getter:
                    resource = await resource_getter(*args, db=db, **kwargs)

                    if isinstance(resource, Project):
                        if not self.check_project_access(current_user, resource, permission, db):
                            raise HTTPException(
                                status_code=status.HTTP_403_FORBIDDEN,
                                detail=f"Insufficient permissions for {permission.value}",
                            )
                    # Add other resource types as needed

                # Check if user is superadmin for admin permissions
                elif permission in [
                    Permission.ADMIN_VIEW,
                    Permission.ADMIN_EDIT,
                    Permission.FEATURE_FLAG_MANAGE,
                ]:
                    if not current_user.is_superadmin:
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
                        )

                return await func(*args, current_user=current_user, db=db, **kwargs)

            return wrapper

        return decorator

    def can_edit_project(self, user: User, project: Project, db: Session) -> bool:
        """
        Check if user can edit a project.
        Convenience method for common use case.
        """
        return self.check_project_access(user, project, Permission.PROJECT_EDIT, db)

    def can_delete_project(self, user: User, project: Project, db: Session) -> bool:
        """
        Check if user can delete a project.
        Convenience method for common use case.
        """
        return self.check_project_access(user, project, Permission.PROJECT_DELETE, db)

    def filter_accessible_projects(
        self, user: User, projects: List[Project], permission: Permission, db: Session
    ) -> List[Project]:
        """
        Filter a list of projects to only those the user has access to.

        Args:
            user: User to check access for
            projects: List of projects to filter
            permission: Required permission
            db: Database session

        Returns:
            List of accessible projects
        """
        if user.is_superadmin:
            return projects

        return [
            project
            for project in projects
            if self.check_project_access(user, project, permission, db)
        ]


# Global authorization service instance
auth_service = AuthorizationService()


# Convenience decorators
def require_project_view():
    """Decorator to require project view permission."""
    return auth_service.require_permission(Permission.PROJECT_VIEW)


def require_project_edit():
    """Decorator to require project edit permission."""
    return auth_service.require_permission(Permission.PROJECT_EDIT)


def require_project_delete():
    """Decorator to require project delete permission."""
    return auth_service.require_permission(Permission.PROJECT_DELETE)


def require_admin():
    """Decorator to require admin permission."""
    return auth_service.require_permission(Permission.ADMIN_VIEW)


def require_superadmin():
    """Decorator to require superadmin status."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, current_user: User = Depends(require_user), **kwargs):
            if not current_user.is_superadmin:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, detail="Superadmin access required"
                )
            return await func(*args, current_user=current_user, **kwargs)

        return wrapper

    return decorator
