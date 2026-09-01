"""Membership-agnostic project consumer predicates (worker-safe).

``org_resolution`` answers "which org may this MEMBER bill?" and is
membership-first by design. These helpers answer the orthogonal question
"is this non-member a legitimate consumer of the project?" — needed by the
billing-inheritance policy (extended): an org that provides keys
(``require_private_keys`` False) covers gradings for everyone legitimately
using its projects, consumers included (owner decision 2026-08-31).

Generic data-shape lookups over platform tables only (split rule: platform).
No fastapi/pydantic imports — the workers container must import this.
Fail-closed: any DB error yields the empty/negative answer.
"""

import logging
from typing import List

logger = logging.getLogger(__name__)


def project_linked_org_ids(db, project) -> List[str]:
    """ALL org ids linked to the project (``project_organizations``),
    regardless of the caller's membership. Accepts a Project row or bare id.
    """
    from project_models import ProjectOrganization

    project_id = str(getattr(project, "id", project))
    try:
        rows = (
            db.query(ProjectOrganization.organization_id)
            .filter(ProjectOrganization.project_id == project_id)
            .all()
        )
        return [str(r[0]) for r in rows]
    except Exception:
        logger.warning(
            "project_linked_org_ids failed for project %s", project_id, exc_info=True
        )
        return []


def is_project_consumer(db, user_id, project_id) -> bool:
    """Legitimate consumer of the project: a non-revoked
    ``MarketplaceEntitlement`` (ANY source — purchase | vendor_grant |
    discovered) OR a consented ``ProjectShareMember`` row. Mirrors the
    participant-tier union in ``routers/projects/helpers.py`` minus the
    org-exam-participant arm (that one is membership-based and handled by
    ``org_resolution``).
    """
    from project_models import MarketplaceEntitlement, ProjectShareMember

    try:
        entitled = (
            db.query(MarketplaceEntitlement)
            .filter(
                MarketplaceEntitlement.user_id == str(user_id),
                MarketplaceEntitlement.project_id == str(project_id),
                MarketplaceEntitlement.revoked_at.is_(None),
            )
            .first()
        )
        if entitled is not None:
            return True
        share = (
            db.query(ProjectShareMember)
            .filter(
                ProjectShareMember.user_id == str(user_id),
                ProjectShareMember.project_id == str(project_id),
                ProjectShareMember.gdpr_consent_at.isnot(None),
            )
            .first()
        )
        return share is not None
    except Exception:
        logger.warning(
            "is_project_consumer failed for user %s / project %s",
            user_id,
            project_id,
            exc_info=True,
        )
        return False
