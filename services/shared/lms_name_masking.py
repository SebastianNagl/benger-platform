"""Hiding the real names of LMS users (owner decision D8).

An account that an LMS (LTI) launch created, or that is linked to an LMS
identity, carries the clear name and email the learning platform sent. Lists
show such an account by its pseudonym unless the viewer may see the real
name. Who may see it is extended logic behind two hooks
(``privacy_protected_member_ids`` and ``project_real_name_user_ids``); this
module holds the platform side that runs in the API and in the workers:

- :func:`lms_user_ids_from_links` / :func:`is_lms_account` read the platform
  link table with the definition the hook contract documents: an LMS user
  has a link that a launch provisioned (it keeps the LMS clear name, even
  after an admin unlink) or any link that is not unlinked. The API uses it
  for the ``is_lms_account`` flag of ``/auth/me``; exports use it when the
  extended hooks are not available.
- :class:`NameVisibility` applies the rule to one project-scoped list of
  users (the export ``users`` block). The API member lists and task listings
  use the API extension loader instead (``services/member_privacy.py``); the
  workers have no such loader, so the hooks come from the optional worker
  hook ``benger_extended.workers.get_name_visibility_fns``.

Rule for a project-scoped list: a user is masked when they are an LMS user,
show their pseudonym by default, are not the viewer, and the viewer may not
see that person's real name on the project (the hook names the people who
take part in the exam through a connection whose students the viewer may
see). Superadmins see every name. A masked user keeps their id.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Callable, Iterable, Optional

from sqlalchemy import or_, select

from user_display import prefers_pseudonym

logger = logging.getLogger(__name__)


def _lms_link_filters(user_id_clause):
    from models import LtiUserLink

    return (
        user_id_clause,
        or_(
            LtiUserLink.link_method == "provisioned",
            LtiUserLink.unlinked_at.is_(None),
        ),
    )


def lms_link_exists(user_id_column):
    """SQL EXISTS clause: the user in ``user_id_column`` is an LMS user."""
    from sqlalchemy import exists

    from models import LtiUserLink

    return exists().where(*_lms_link_filters(LtiUserLink.user_id == user_id_column))


def _build_select_lms_user_ids(user_ids: Iterable[str]):
    from models import LtiUserLink

    ids = sorted({str(uid) for uid in user_ids})
    return (
        select(LtiUserLink.user_id)
        .where(*_lms_link_filters(LtiUserLink.user_id.in_(ids)))
        .distinct()
    )


def _build_select_is_lms_account(user_id: str):
    from sqlalchemy import exists

    from models import LtiUserLink

    return select(
        exists().where(*_lms_link_filters(LtiUserLink.user_id == str(user_id)))
    )


def _clean_ids(user_ids: Optional[Iterable[Any]]) -> set:
    return {str(uid) for uid in (user_ids or ()) if uid}


def lms_user_ids_from_links(db, user_ids: Optional[Iterable[Any]]) -> set:
    """The LMS users among ``user_ids`` (sync session)."""
    ids = _clean_ids(user_ids)
    if not ids:
        return set()
    rows = db.execute(_build_select_lms_user_ids(ids)).scalars().all()
    return {str(uid) for uid in rows} & ids


def is_lms_account_sync(db, user_id: Optional[str]) -> bool:
    """True when ``user_id`` is an LMS user (sync session)."""
    if not user_id:
        return False
    return db.execute(_build_select_is_lms_account(user_id)).scalar() is True


async def is_lms_account(db, user_id: Optional[str]) -> bool:
    """Async twin of :func:`is_lms_account_sync`."""
    if not user_id:
        return False
    result = await db.execute(_build_select_is_lms_account(user_id))
    return result.scalar() is True


class NameVisibility:
    """The two name-visibility hooks, bound for one process.

    ``lms_user_ids`` has the signature of the ``privacy_protected_member_ids``
    hook ``(db, organization_id, user_ids)``, ``real_name_user_ids`` that of
    ``project_real_name_user_ids`` ``(db, viewer, project_id, user_ids)`` and
    answers which of the given people the viewer may see by name on the
    project. Without the first, the link table decides who is an LMS user;
    without the second, only superadmins see real names. A failing hook
    never reveals a name.
    """

    def __init__(
        self,
        lms_user_ids: Optional[Callable] = None,
        real_name_user_ids: Optional[Callable] = None,
    ):
        self._lms_user_ids = lms_user_ids
        self._real_name_user_ids = real_name_user_ids

    @classmethod
    def load(cls) -> "NameVisibility":
        """The hooks of this process.

        Reads the optional worker hook of the extended edition, which works in
        the API process as well. In the API process the extension loader has
        the last word: when it refused the extended package (a failed version
        handshake, for example), the hooks are not used either. The community
        edition has no LMS accounts, so the link table (empty there) is all it
        needs.
        """
        loader = sys.modules.get("extensions")
        if (
            loader is not None
            and hasattr(loader, "load_extended")
            and getattr(loader, "_extended", None) is None
        ):
            return cls()
        try:
            from benger_extended import workers as extended_workers
        except ImportError:
            return cls()
        getter = getattr(extended_workers, "get_name_visibility_fns", None)
        if getter is None:
            return cls()
        try:
            lms_user_ids, real_name_user_ids = getter()
        except Exception:
            logger.exception("get_name_visibility_fns failed; using the link table")
            return cls()
        return cls(lms_user_ids, real_name_user_ids)

    def lms_user_ids(self, db, user_ids: Optional[Iterable[Any]]) -> set:
        """The LMS users among ``user_ids``."""
        ids = _clean_ids(user_ids)
        if not ids:
            return set()
        if self._lms_user_ids is not None:
            try:
                result = self._lms_user_ids(db, None, sorted(ids))
                return {str(uid) for uid in (result or ())} & ids
            except Exception:
                logger.exception("privacy_protected_member_ids hook failed")
        try:
            return lms_user_ids_from_links(db, ids)
        except Exception:
            logger.exception("LMS link lookup failed; masking every candidate")
            return ids

    def real_name_user_ids(
        self, db, viewer, project_id: Optional[str], user_ids: Optional[Iterable[Any]]
    ) -> set:
        """Which of ``user_ids`` ``viewer`` may see by real name on the
        project (all of them for superadmins, none without the hook)."""
        ids = _clean_ids(user_ids)
        if viewer is None or not ids:
            return set()
        if getattr(viewer, "is_superadmin", False) is True:
            return ids
        if self._real_name_user_ids is None or not project_id:
            return set()
        try:
            result = self._real_name_user_ids(db, viewer, str(project_id), sorted(ids))
            return {str(uid) for uid in (result or ())} & ids
        except Exception:
            logger.exception(
                "project_real_name_user_ids hook failed for project %s", project_id
            )
            return set()

    def masked_user_ids(
        self, db, users: Iterable[Any], *, project_id: Optional[str], viewer=None
    ) -> set:
        """Ids of ``users`` that ``viewer`` sees only by pseudonym."""
        viewer_id = str(getattr(viewer, "id", "") or "") if viewer is not None else ""
        candidates = {
            str(user.id)
            for user in users
            if user is not None and getattr(user, "id", None) and prefers_pseudonym(user)
        }
        candidates.discard(viewer_id)
        if not candidates:
            return set()
        if viewer is not None and getattr(viewer, "is_superadmin", False) is True:
            return set()
        lms = self.lms_user_ids(db, candidates)
        if not lms:
            return set()
        return lms - self.real_name_user_ids(db, viewer, project_id, lms)
