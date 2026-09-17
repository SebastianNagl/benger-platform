"""Real names of LMS users in the API's lists (owner decision D8).

LMS accounts carry the clear name and email of the learning platform and are
shown by pseudonym by default. This module applies the extension hooks
``extensions.privacy_protected_member_ids`` and
``extensions.project_real_name_user_ids`` on the async lane:

- **Org lists** (org member list, ``/organizations/manage/users``, group
  roster): a masked user shows the real name and email only to superadmins
  and to the admins of an org whose own connections the user belongs to
  (``privacy_protected_member_ids(db, org_id, ids)``). A group admin who is
  not an org admin sees the real names of the LMS users of connections
  scoped to the groups they administer
  (``privacy_protected_member_ids(db, org_id, ids, group_ids=...)``, see
  :func:`reveal_group_accounts`), not of whoever is a member of their
  group: group membership is something a group admin can change. The
  roster of an org whose LMS connections stay superadmin-run
  (``protected_org_ids``; every LMS user and every pilot teacher joins it)
  is for its org admins only.
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
Id lists go to the hooks in chunks of :data:`_HOOK_CHUNK`, so a large org
never exceeds the database driver's bind-parameter limit.
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
    "project_name_masks",
    "protected_org_ids",
    "reveal_group_accounts",
    "masked_name",
]

# Ids per hook call. asyncpg refuses more than 32767 bind parameters, and the
# hooks bind one per id (``IN (...)``).
_HOOK_CHUNK = 5000


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


def _chunks(ids: list) -> list:
    return [ids[i : i + _HOOK_CHUNK] for i in range(0, len(ids), _HOOK_CHUNK)]


def _protected_ids_sync(sync_db, organization_id, ids: list, **kwargs) -> set:
    """``privacy_protected_member_ids`` over ``ids`` in chunks. Each chunk
    fails closed on its own (the wrapper's safe value)."""
    found: set = set()
    for chunk in _chunks(ids):
        found |= extensions.privacy_protected_member_ids(
            sync_db, organization_id, chunk, **kwargs
        )
    return found


async def lms_account_ids(db, user_ids: Iterable[Any]) -> set:
    """The LMS users among ``user_ids``."""
    ids = _clean(user_ids)
    if not ids:
        return set()
    return await db.run_sync(lambda sync_db: _protected_ids_sync(sync_db, None, ids))


async def _org_lms_account_ids(
    db, organization_id: str, user_ids: Iterable[Any], group_ids=None
) -> set:
    ids = _clean(user_ids)
    if not ids or not organization_id:
        return set()
    kwargs = {} if group_ids is None else {"group_ids": sorted(group_ids)}
    return await db.run_sync(
        lambda sync_db: _protected_ids_sync(
            sync_db, str(organization_id), ids, **kwargs
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


async def reveal_group_accounts(
    db,
    mask: NameMask,
    organization_id: str,
    admin_group_ids: Iterable[Any],
    user_ids: Iterable[Any],
) -> NameMask:
    """``mask`` with the LMS users among ``user_ids`` unmasked that belong
    to ``organization_id``'s connections scoped to one of
    ``admin_group_ids`` (a group admin's view, D1/D8).

    Org-wide connections and connections of other groups do not count, and
    neither does membership in the group. No groups: nothing is unmasked.
    """
    candidates = set(_clean(user_ids)) & set(mask.masked_ids)
    groups = set(_clean(admin_group_ids))
    if not candidates or not organization_id or not groups:
        return mask
    revealed = await _org_lms_account_ids(
        db, organization_id, candidates, group_ids=groups
    )
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


async def project_name_mask(
    db,
    users: Iterable[Any],
    *,
    viewer,
    project_id: str,
    lms_ids: Optional[Iterable[Any]] = None,
) -> NameMask:
    """Mask for a project-scoped list of ORM users (see module docstring).

    ``lms_ids``: the caller's answer of :func:`lms_account_ids` for (at
    least) these users, so it is not asked again.
    """
    users_by_id = _by_id(users)
    if lms_ids is None:
        lms = await lms_account_ids(db, users_by_id)
    else:
        lms = {str(uid) for uid in lms_ids} & set(users_by_id)
    candidates = _candidates(users_by_id, lms, viewer)
    if not candidates or _is_superadmin(viewer):
        return NameMask(frozenset(lms), frozenset())
    ids = sorted(candidates)

    def _revealed(sync_db) -> set:
        found: set = set()
        for chunk in _chunks(ids):
            found |= extensions.project_real_name_user_ids(
                sync_db, viewer, project_id, chunk
            )
        return found

    revealed = await db.run_sync(_revealed)
    return NameMask(frozenset(lms), frozenset(candidates - set(revealed)))


async def project_name_masks(
    db,
    users_by_project: dict,
    *,
    viewer,
    lms_ids: Optional[Iterable[Any]] = None,
) -> dict:
    """:func:`project_name_mask` for many projects with one hook call.

    ``users_by_project`` maps project ids to their ORM users (for example
    each project's creator). Returns a :class:`NameMask` per project id.
    ``lms_ids`` as in :func:`project_name_mask`; without it one lookup
    covers every user of every project.
    """
    by_project = {
        str(pid): _by_id(users) for pid, users in (users_by_project or {}).items() if pid
    }
    if lms_ids is None:
        every = set()
        for users_by_id in by_project.values():
            every |= set(users_by_id)
        lms_all = await lms_account_ids(db, every)
    else:
        lms_all = {str(uid) for uid in lms_ids}
    lms_by_project = {
        pid: lms_all & set(users_by_id) for pid, users_by_id in by_project.items()
    }
    candidates = {
        pid: _candidates(users_by_id, lms_by_project[pid], viewer)
        for pid, users_by_id in by_project.items()
    }
    wanted = {pid: sorted(ids) for pid, ids in candidates.items() if ids}
    revealed: dict = {}
    if wanted and not _is_superadmin(viewer):
        revealed = await db.run_sync(
            lambda sync_db: extensions.projects_real_name_user_ids(
                sync_db, viewer, wanted
            )
        )
    masks = {}
    for pid in by_project:
        lms = frozenset(lms_by_project[pid])
        if _is_superadmin(viewer):
            masks[pid] = NameMask(lms, frozenset())
            continue
        shown = set(revealed.get(pid) or ())
        masks[pid] = NameMask(lms, frozenset(candidates[pid] - shown))
    return masks
