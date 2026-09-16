"""Real names of LMS users in the API's lists (owner decision D8).

LMS accounts carry the clear name and email of the learning platform and are
shown by pseudonym by default. This module applies the extension hooks
``extensions.privacy_protected_member_ids`` and
``extensions.project_real_name_user_ids`` on the async lane:

- **Org lists** (org member list, ``/organizations/manage/users``, group
  roster): a masked user shows the real name and email only to superadmins
  and to the admins of an org whose own connections the user belongs to
  (``privacy_protected_member_ids(db, org_id, ids)``). Which orgs count as
  "admin" is the caller's decision (org admins for the member list, org and
  group admins for a group roster). The roster of an org whose LMS
  connections stay superadmin-run (``protected_org_ids``; every LMS user and
  every pilot teacher joins it) is for its org admins only.
- **Project lists** (project members, task listing and assignments):
  masked unless ``project_real_name_user_ids`` names the person for this
  viewer. That set holds only people who take part in the exam through a
  connection whose students the viewer may see, so an org-wide member list
  of a linked exam never unmasks the rest of the university (or, on a
  platform-wide org, every other university's students).

A user is a masking candidate when they are an LMS user
(``privacy_protected_member_ids(db, None, ids)``), show their pseudonym by
default and are not the viewer. Masked rows keep their ids and show
:func:`user_display.masked_name`; emails are left out.

The hooks are sync and read only; they run through ``AsyncSession.run_sync``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

import extensions
from user_display import masked_name, prefers_pseudonym

__all__ = [
    "NameMask",
    "lms_account_ids",
    "masked_org_member_ids",
    "org_name_mask",
    "project_name_mask",
    "protected_org_ids",
    "reveal_org_accounts",
    "masked_name",
]


@dataclass(frozen=True)
class NameMask:
    """Result for one list: which users are LMS users, which are masked."""

    lms_ids: frozenset = field(default_factory=frozenset)
    masked_ids: frozenset = field(default_factory=frozenset)

    def is_lms(self, user_id: Any) -> bool:
        return str(user_id) in self.lms_ids

    def is_masked(self, user_id: Any) -> bool:
        return str(user_id) in self.masked_ids

    def label(self, user: Any) -> Optional[str]:
        """The name to show for ``user`` (an ORM row)."""
        if user is None:
            return None
        if self.is_masked(user.id):
            return masked_name(user)
        return user.name

    def email(self, user: Any) -> Optional[str]:
        """The email to show for ``user``; None when masked."""
        if user is None or self.is_masked(user.id):
            return None
        return user.email


def _clean(user_ids: Iterable[Any]) -> list:
    return sorted({str(uid) for uid in user_ids if uid})


def _is_superadmin(viewer: Any) -> bool:
    return bool(viewer is not None and getattr(viewer, "is_superadmin", False) is True)


def _viewer_id(viewer: Any) -> str:
    return str(getattr(viewer, "id", "") or "") if viewer is not None else ""


async def lms_account_ids(db, user_ids: Iterable[Any]) -> set:
    """The LMS users among ``user_ids``."""
    ids = _clean(user_ids)
    if not ids:
        return set()
    return await db.run_sync(
        lambda sync_db: extensions.privacy_protected_member_ids(sync_db, None, ids)
    )


async def _org_lms_account_ids(db, organization_id: str, user_ids: Iterable[Any]) -> set:
    ids = _clean(user_ids)
    if not ids or not organization_id:
        return set()
    return await db.run_sync(
        lambda sync_db: extensions.privacy_protected_member_ids(
            sync_db, str(organization_id), ids
        )
    )


async def masked_org_member_ids(
    db, candidate_ids: Iterable[Any], *, viewer, admin_org_ids: Iterable[str] = ()
) -> set:
    """Which of ``candidate_ids`` stay masked in an org list.

    ``candidate_ids`` are LMS users with the pseudonym on (the viewer is
    dropped here). ``admin_org_ids`` are the orgs in which the viewer may
    unmask the LMS users of that org's own connections.
    """
    candidates = set(_clean(candidate_ids))
    candidates.discard(_viewer_id(viewer))
    if not candidates or _is_superadmin(viewer):
        return set()
    revealed: set = set()
    for org_id in sorted({str(o) for o in admin_org_ids if o}):
        remaining = candidates - revealed
        if not remaining:
            break
        revealed |= await _org_lms_account_ids(db, org_id, remaining)
    return candidates - revealed


async def protected_org_ids(db, organization_ids: Iterable[Any]) -> set:
    """The orgs among ``organization_ids`` whose LMS connections stay
    superadmin-run (a platform-wide org every LMS user joins). Their
    rosters are for their admins only. Fails closed
    (``extensions.lti_protected_org_subset``)."""
    ids = _clean(organization_ids)
    if not ids:
        return set()
    return await db.run_sync(
        lambda sync_db: extensions.lti_protected_org_subset(sync_db, ids)
    )


async def reveal_org_accounts(
    db, mask: NameMask, organization_id: str, user_ids: Iterable[Any]
) -> NameMask:
    """``mask`` with the LMS accounts of ``organization_id``'s own
    connections among ``user_ids`` unmasked (a group admin's view of their
    groups' members in the org list)."""
    candidates = set(_clean(user_ids)) & set(mask.masked_ids)
    if not candidates or not organization_id:
        return mask
    revealed = await _org_lms_account_ids(db, organization_id, candidates)
    if not revealed:
        return mask
    return NameMask(mask.lms_ids, frozenset(set(mask.masked_ids) - revealed))


def _candidates(users_by_id: dict, lms_ids: set, viewer) -> set:
    viewer_id = _viewer_id(viewer)
    return {
        uid
        for uid in lms_ids
        if uid != viewer_id and uid in users_by_id and prefers_pseudonym(users_by_id[uid])
    }


def _by_id(users: Iterable[Any]) -> dict:
    return {str(u.id): u for u in users if u is not None and getattr(u, "id", None)}


async def org_name_mask(
    db, users: Iterable[Any], *, viewer, admin_org_ids: Iterable[str] = ()
) -> NameMask:
    """Mask for an org-scoped list of ORM users (see module docstring)."""
    users_by_id = _by_id(users)
    lms = await lms_account_ids(db, users_by_id)
    candidates = _candidates(users_by_id, lms, viewer)
    masked = await masked_org_member_ids(
        db, candidates, viewer=viewer, admin_org_ids=admin_org_ids
    )
    return NameMask(frozenset(lms), frozenset(masked))


async def project_name_mask(db, users: Iterable[Any], *, viewer, project_id: str) -> NameMask:
    """Mask for a project-scoped list of ORM users (see module docstring)."""
    users_by_id = _by_id(users)
    lms = await lms_account_ids(db, users_by_id)
    candidates = _candidates(users_by_id, lms, viewer)
    if not candidates or _is_superadmin(viewer):
        return NameMask(frozenset(lms), frozenset())
    ids = sorted(candidates)
    revealed = await db.run_sync(
        lambda sync_db: extensions.project_real_name_user_ids(
            sync_db, viewer, project_id, ids
        )
    )
    return NameMask(frozenset(lms), frozenset(candidates - set(revealed)))
