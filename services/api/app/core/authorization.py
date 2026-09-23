"""
Centralized authorization service for the BenGER API.
Eliminates duplicate permission checking logic across routers.
"""

import logging
from enum import Enum
from functools import wraps
from typing import Callable, List, Optional

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
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
        if hasattr(user, 'organization_memberships') and user.organization_memberships != None:  # noqa: E711
            return user.organization_memberships

        # Pydantic User model: query DB for actual memberships
        from routers.projects.helpers import get_user_with_memberships

        db_user = get_user_with_memberships(db, str(user.id))
        if db_user and db_user.organization_memberships:
            return db_user.organization_memberships
        return []

    async def _get_user_org_memberships_async(self, user, db: AsyncSession):
        """Async twin of :meth:`_get_user_org_memberships`.

        Same shape: returns the user's org memberships, reading from the
        Pydantic ``organizations`` proxy when present or eager-loading the DB
        memberships via the async helper otherwise.
        """
        if hasattr(user, 'organization_memberships') and user.organization_memberships != None:  # noqa: E711
            return user.organization_memberships

        from routers.projects.helpers import get_user_with_memberships_async

        db_user = await get_user_with_memberships_async(db, str(user.id))
        if db_user and db_user.organization_memberships:
            return db_user.organization_memberships
        return []

    def _decide_project_access(
        self,
        user: User,
        project: Project,
        permission: "Permission",
        project_org_ids: List[str],
        memberships,
        attachment_groups=None,
        user_groups=None,
        lti_attachments=None,
        protected_org_ids=None,
    ) -> bool:
        """Pure access decision shared by the sync/async entry points.

        Takes already-loaded data (project org ids + the user's memberships) so
        both lanes run byte-identical decision logic; only the reads differ
        between sync and async. ``attachment_groups`` ({org_id: group_id|None})
        and ``user_groups`` ({group_id: is_group_admin}) carry the group axis
        (see shared/org_groups); omitted, every attachment counts as org-wide.
        ``lti_attachments`` ({org_id: group_id|None} of the rows LMS linking
        created) opens a private exam to those orgs' eligible staff with
        their staff role (``org_groups.lti_staff_role``), whatever context the
        client sends; omitted, a private project stays creator-only.
        ``protected_org_ids`` are the linked orgs whose connections stay
        superadmin-run: only their admins count there. On a non-private exam
        the entry points drop such orgs' LMS rows from ``attachment_groups``
        for everyone else before calling this. Every active membership
        counts, whatever organization the client has selected.

        The decision applies the exam carve-out of ``helpers._org_grants_full_tier``
        (``org_groups.grants_full_tier``): an ANNOTATOR membership confers no
        project-level permission on an exam-kind project, because for an exam
        those permissions expose the Musterlösung, the Bewertungsbogen
        criteria and the evaluation config. Students reach org exams through
        the narrow participant tier instead (``get_student_read_access``). A
        group admin of the attachment counts as staff, and the creator keeps
        the role-based access to their own exam.
        """
        # Superadmins have all permissions
        if user.is_superadmin:
            return True

        # Soft-deleted (migration 093): the project does not exist for
        # non-superadmins — no permission, not even for its creator.
        if getattr(project, "deleted_at", None) is not None:
            return False

        # Public projects: dedicated path that ignores memberships.
        if getattr(project, 'is_public', False) is True:
            if user.id == project.created_by:
                return self._check_org_role_permission("ORG_ADMIN", permission)
            if permission in (
                Permission.PROJECT_EDIT,
                Permission.PROJECT_DELETE,
                Permission.PROJECT_CREATE,
            ):
                return False
            public_role = getattr(project, 'public_role', None)
            if public_role:
                return self._check_org_role_permission(public_role, permission)
            return False

        # Private projects belong to their creator, whatever context the
        # client sends (the sync entry point applies the same rule as a
        # zero-DB fast path; the async lane relies on this branch). Without
        # it, an org member reached a private org-attached exam in org mode.
        # The one exception: staff of an org the exam is LMS-linked to get
        # their staff role's permissions (never ANNOTATORs).
        if getattr(project, 'is_private', False):
            if user.id == project.created_by:
                return True
            from org_groups import lti_staff_role

            role = lti_staff_role(
                getattr(project, "kind", None),
                memberships,
                lti_attachments,
                user_groups,
                protected_org_ids=protected_org_ids,
            )
            return role is not None and self._check_org_role_permission(
                role, permission
            )

        is_creator = user.id == project.created_by
        project_kind = getattr(project, "kind", None)

        # The creator holds the ORG_ADMIN role on their own project (the same
        # rule as the public branch and get_effective_project_role), whatever
        # context the client sends and whether or not they are a member of
        # an attached org.
        if is_creator:
            return self._check_org_role_permission("ORG_ADMIN", permission)

        if project_org_ids:
            from org_groups import attachment_eligible, grants_full_tier

            for org_id in project_org_ids:
                # Only an ACTIVE membership counts (same as the helpers
                # deciders): a removed member keeps a soft-deleted row that
                # must not grant anything.
                membership = next(
                    (
                        m
                        for m in memberships
                        if m.organization_id == org_id and m.is_active
                    ),
                    None,
                )
                if membership:
                    # Group axis: an ineligible grouped attachment is
                    # skipped (the next attachment may still grant);
                    # eligibility via a group the user group-admins
                    # upgrades that attachment's role to ORG_ADMIN.
                    group_id = (attachment_groups or {}).get(org_id)
                    if not attachment_eligible(
                        group_id,
                        is_creator=is_creator,
                        membership_role=membership.role,
                        user_groups=user_groups,
                    ):
                        continue
                    # Exam carve-out: an ANNOTATOR attachment is skipped too,
                    # a staff membership through another org may still grant.
                    if not grants_full_tier(
                        project_kind, membership.role, group_id, user_groups
                    ):
                        continue
                    role = (
                        "ORG_ADMIN"
                        if group_id is not None
                        and (user_groups or {}).get(group_id, False)
                        else membership.role
                    )
                    return self._check_org_role_permission(role, permission)

        return False

    def check_project_access(
        self,
        user: User,
        project: Project,
        permission: Permission,
        db: Session,
    ) -> bool:
        """
        Check if a user has access to a project with specific permission.

        Args:
            user: User making the request
            project: Project to check access for
            permission: Required permission
            db: Database session

        Every active membership counts, whatever organization the client
        has selected.
        """
        # Superadmins have all permissions
        if user.is_superadmin:
            return True

        # Zero-DB fast-paths (mirrored inside the decider, kept here so the
        # deleted/public/private shapes resolve without loading memberships):
        if getattr(project, "deleted_at", None) is not None:
            return False
        if getattr(project, 'is_public', False) is True:
            if user.id == project.created_by:
                return self._check_org_role_permission("ORG_ADMIN", permission)
            if permission in (
                Permission.PROJECT_EDIT,
                Permission.PROJECT_DELETE,
                Permission.PROJECT_CREATE,
            ):
                return False
            public_role = getattr(project, 'public_role', None)
            if public_role:
                return self._check_org_role_permission(public_role, permission)
            return False
        # A private project resolves on creatorship alone, except someone
        # else's private exam: its LMS attachments may grant staff (the
        # decider below), so that shape falls through to the reads.
        needs_lti = self._private_exam_needs_lti_map(user, project)
        if getattr(project, 'is_private', False) and not needs_lti:
            return user.id == project.created_by
        if user.id == project.created_by:
            # Creator fast-path (identical branch inside the decider),
            # zero-DB like the pre-refactor inline code.
            return self._check_org_role_permission("ORG_ADMIN", permission)

        # Load-then-delegate to the shared pure decider (same as the async
        # lane) so the sync/async ORG semantics — including the group axis
        # and the soft-delete guard the old inline copy was missing — cannot
        # drift. This used to be a third inline copy of the decision logic.
        from org_groups import (
            get_attachment_group_map,
            get_lti_attachment_map,
            get_user_group_context,
        )

        lti_attachments = None
        protected_org_ids = None
        if needs_lti:
            lti_attachments = get_lti_attachment_map(db, str(project.id))
            if not lti_attachments:
                return False
            protected_org_ids = self._protected_org_ids(db, lti_attachments)
        attachment_groups = get_attachment_group_map(db, str(project.id))
        memberships = self._get_user_org_memberships(user, db)
        user_groups = get_user_group_context(db, str(user.id))
        if self._needs_protected_lti_filter(user, project) and attachment_groups:
            from org_groups import drop_protected_lti_attachments, get_lti_row_org_ids

            lti_orgs = get_lti_row_org_ids(db, str(project.id)) & set(attachment_groups)
            protected = self._protected_org_ids(db, lti_orgs) if lti_orgs else set()
            if protected:
                attachment_groups = drop_protected_lti_attachments(
                    attachment_groups, protected, memberships, user_groups
                )
        return self._decide_project_access(
            user,
            project,
            permission,
            list(attachment_groups.keys()),
            memberships,
            attachment_groups=attachment_groups,
            user_groups=user_groups,
            lti_attachments=lti_attachments,
            protected_org_ids=protected_org_ids,
        )

    async def check_project_access_async(
        self,
        user: User,
        project: Project,
        permission: "Permission",
        db: AsyncSession,
    ) -> bool:
        """Async twin of :meth:`check_project_access`.

        Resolves the same two reads (project org ids + the user's memberships)
        through the async engine, then defers to the shared pure decision
        helper so the access semantics are identical to the sync path.
        """
        # Fast paths that need no DB read mirror the sync ordering; the shared
        # decider also short-circuits these, but resolving them first avoids
        # two needless round-trips for superadmins / public-creator / private.
        if user.is_superadmin:
            return True
        # Soft-deleted (093): gone for every non-superadmin.
        if getattr(project, "deleted_at", None) is not None:
            return False

        from org_groups import (
            get_attachment_group_map_async,
            get_lti_attachment_map_async,
            get_user_group_context_async,
        )

        # Lockstep with the sync lane: the LMS attachment map is only read
        # for someone else's private exam.
        lti_attachments = None
        protected_org_ids = None
        if self._private_exam_needs_lti_map(user, project):
            lti_attachments = await get_lti_attachment_map_async(db, str(project.id))
            if not lti_attachments:
                return False
            org_ids = list(lti_attachments)
            protected_org_ids = await db.run_sync(
                lambda sync_db: self._protected_org_ids(sync_db, org_ids)
            )
        attachment_groups = await get_attachment_group_map_async(db, str(project.id))
        memberships = await self._get_user_org_memberships_async(user, db)
        user_groups = await get_user_group_context_async(db, str(user.id))
        if self._needs_protected_lti_filter(user, project) and attachment_groups:
            from org_groups import (
                drop_protected_lti_attachments,
                get_lti_row_org_ids_async,
            )

            lti_orgs = await get_lti_row_org_ids_async(db, str(project.id))
            lti_orgs &= set(attachment_groups)
            protected = set()
            if lti_orgs:
                protected = await db.run_sync(
                    lambda sync_db: self._protected_org_ids(sync_db, lti_orgs)
                )
            if protected:
                attachment_groups = drop_protected_lti_attachments(
                    attachment_groups, protected, memberships, user_groups
                )
        return self._decide_project_access(
            user,
            project,
            permission,
            list(attachment_groups.keys()),
            memberships,
            attachment_groups=attachment_groups,
            user_groups=user_groups,
            lti_attachments=lti_attachments,
            protected_org_ids=protected_org_ids,
        )

    @staticmethod
    def _protected_org_ids(db, org_ids) -> set:
        """The linked orgs whose connections stay superadmin-run (sync;
        fails closed, see ``extensions.lti_protected_org_subset``)."""
        import extensions

        return extensions.lti_protected_org_subset(db, list(org_ids))

    @staticmethod
    def _needs_protected_lti_filter(user, project) -> bool:
        """Someone else's non-private, non-public exam: the LMS attachments of
        orgs whose connections stay superadmin-run count only for their
        admins (``org_groups.drop_protected_lti_attachments``), as on
        private exams."""
        return (
            getattr(project, "kind", None) == "exam"
            and getattr(project, "is_private", False) is not True
            and getattr(project, "is_public", False) is not True
            and user.id != project.created_by
        )

    @staticmethod
    def _private_exam_needs_lti_map(user, project) -> bool:
        """Whether the decision needs the LMS attachment map: only someone
        else's private, non-public exam can be opened through one."""
        return (
            bool(getattr(project, "is_private", False))
            and getattr(project, "is_public", False) is not True
            and user.id != project.created_by
            and getattr(project, "kind", None) == "exam"
        )

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
