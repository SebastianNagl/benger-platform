"""Request and response shapes for anonymizing accounts.

Used by the LMS connection admin (``routers/lti_admin.py``) and the
superadmin user admin (``routers/users.py``). Blocker and warning codes are
listed in ``services/user_anonymization.py``.
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class AnonymizationUserRead(BaseModel):
    """Who the preview is about. ``name`` and ``email`` only for viewers who
    may see real names (D8); ``display`` follows the same rule."""

    id: str
    display: str
    pseudonym: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None


class AnonymizationPreviewRead(BaseModel):
    user_link_id: str
    registration_id: str
    user: AnonymizationUserRead
    eligible: bool
    blockers: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    keeps: Dict[str, int] = Field(default_factory=dict)
    removes: Dict[str, int] = Field(default_factory=dict)


class AnonymizeRequest(BaseModel):
    """The account the admin saw in the preview. The request is refused
    (409 ``link_changed``) when the link now points to another account."""

    expected_user_id: str = Field(..., min_length=1, max_length=64)


class AnonymizeResult(BaseModel):
    user_id: str
    anonymized: bool = True
    anonymized_at: datetime
    pseudonym: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    removed: Dict[str, int] = Field(default_factory=dict)
    kept: Dict[str, int] = Field(default_factory=dict)


class ConnectionAccountSkipped(BaseModel):
    """A provisioned account of a connection that is not anonymized."""

    user_link_id: str
    user_id: str
    display: str
    blockers: List[str] = Field(default_factory=list)


class ConnectionAnonymizationPreviewRead(BaseModel):
    """What ``DELETE /registrations/{id}?accounts=anonymize`` would do."""

    registration_id: str
    provisioned_accounts: int
    eligible_accounts: int
    #: Eligible accounts per warning code (e.g. ``has_password``).
    warnings: Dict[str, int] = Field(default_factory=dict)
    skipped: List[ConnectionAccountSkipped] = Field(default_factory=list)


class ConnectionDeleteReport(BaseModel):
    """Answer of ``DELETE /registrations/{id}?accounts=anonymize``: the
    connection is gone; ``skipped`` accounts stay as standalone accounts."""

    registration_id: str
    deleted: bool = True
    anonymized_accounts: int
    anonymized_user_ids: List[str] = Field(default_factory=list)
    skipped: List[ConnectionAccountSkipped] = Field(default_factory=list)


class UserAnonymizationPreviewRead(BaseModel):
    """Superadmin preview (``GET /api/users/{id}/anonymization``)."""

    user_id: str
    eligible: bool
    blockers: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    keeps: Dict[str, int] = Field(default_factory=dict)
    removes: Dict[str, int] = Field(default_factory=dict)
