"""Annotator blinding for task payloads (benger-extended issue #56).

The classic task-serving endpoints historically returned the raw ``task.data``
to anyone with project access. Keys that are NOT bound in the label config
(``value="$key"``) are never rendered in the labeling UI — but they shipped in
the network payload, so an annotator inspecting the network tab could read a
project's reference solution (``musterloesung``, ``ground_truth``, …) before
submitting.

Policy implemented here (generalizes the extended korrektur "Meine Aufgaben"
blinding to the pre-submit serving surface):

- Effective role CONTRIBUTOR / ORG_ADMIN (incl. superadmins and the project
  creator) → **never blinded**. Superadmins and researchers inspect private
  student exams through the classic interface; that must keep working.
- Effective role ANNOTATOR — or no role at all (invitees / marketplace
  entitlements / discovered solves reach projects without holding an org
  role) → ``task.data`` is reduced to the label-config-bound keys, EXCEPT
  when ``project.annotator_full_visibility_after_submit`` is true AND the
  user has an active (non-cancelled) annotation on that task: then the full
  data is the intended post-submit reveal (same semantics the korrektur
  my-view endpoint applies, evaluated per task).

Note this is deliberately stricter than a plain "blind when the reveal flag
is off": on reveal-enabled projects (student exams default to
``annotator_full_visibility_after_submit=True``) a plain flag gate would ship
the Musterlösung PRE-submit — the exact leak this module closes.
"""

from typing import Dict, Iterable, Optional, Set

from sqlalchemy import case, cast, exists, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import JSON

from project_models import Annotation, Project
from routers.projects.helpers import get_effective_project_role_async

#: Effective roles that always receive the full task payload.
_FULL_DATA_ROLES = ("ORG_ADMIN", "CONTRIBUTOR")


async def annotator_bound_fields_or_none_async(
    db: AsyncSession, user, project: Project
) -> Optional[Set[str]]:
    """The visible-field set when ``user`` must be blinded, else ``None``.

    ``None`` means "serve the full task.data" (editor-tier role). A set —
    possibly empty, which fails closed on malformed configs — means "reduce
    task.data to these keys" (subject to the per-task reveal, see
    :func:`revealed_task_ids_async`).
    """
    role = await get_effective_project_role_async(db, user, project)
    if role in _FULL_DATA_ROLES:
        return None

    from services.label_config.parser import LabelConfigParser

    return LabelConfigParser.bound_data_fields(project.label_config)


def annotator_bound_fields_or_none(db, user, project: Project) -> Optional[Set[str]]:
    """Sync twin of :func:`annotator_bound_fields_or_none_async` (for the
    legacy-sync my-tasks route)."""
    from routers.projects.helpers import get_effective_project_role

    role = get_effective_project_role(db, user, project)
    if role in _FULL_DATA_ROLES:
        return None

    from services.label_config.parser import LabelConfigParser

    return LabelConfigParser.bound_data_fields(project.label_config)


async def revealed_task_ids_async(
    db: AsyncSession, user, project: Project, task_ids: Iterable[str]
) -> Set[str]:
    """Task ids whose FULL data the (blinded) user may see via the post-submit
    reveal: requires ``annotator_full_visibility_after_submit`` on the project
    and an active annotation by the user on the task. Batched for lists."""
    ids = [t for t in task_ids if t]
    if not ids or not getattr(project, "annotator_full_visibility_after_submit", False):
        return set()
    result = await db.execute(
        select(Annotation.task_id).where(
            Annotation.task_id.in_(ids),
            Annotation.completed_by == str(user.id),
            Annotation.was_cancelled == False,  # noqa: E712
        )
    )
    return {row for row in result.scalars().all()}


def visible_top_level_keys(bound_fields: Iterable[str]) -> Set[str]:
    """Normalize config bindings to the comparable top-level data keys.

    Must mirror how the labeling UI resolves a binding, or blinding strips
    keys the annotator is meant to see (empty Angabe while admins, who skip
    blinding, see content — 2026-08-20 prod incident on capitalized import
    keys):

    - Case-insensitive: the frontend resolver (``findKeyInsensitive`` in
      ``lib/labelConfig/dataBinding.ts``) matches ``$sachverhalt`` to a
      ``Sachverhalt`` data key; so must we. ``casefold`` on both sides.
    - Nested paths: ``$case.sachverhalt`` renders from inside the top-level
      ``case`` object, so the top-level segment is what must survive the
      filter. Deliberate consequence: a nested binding exposes its WHOLE
      top-level object — no wider than what the labeling UI can render.
    """
    return {f.split(".", 1)[0].casefold() for f in bound_fields}


def blind_task_data(task_data, bound_fields: Set[str]) -> Dict:
    """Reduce a ``task.data`` dict to the label-config-bound keys.

    An empty ``bound_fields`` still blinds everything (fail-closed). Unbound
    keys — most importantly a Musterlösung under ANY spelling — never pass.
    """
    if not isinstance(task_data, dict):
        return {}
    visible = visible_top_level_keys(bound_fields)
    return {k: v for k, v in task_data.items() if k.casefold() in visible}


def visible_keys_match(data_column, visible_keys: Iterable[str], pattern: str):
    """SQL condition: a top-level key of ``data_column`` (a task.data JSON
    column) whose casefolded name is in ``visible_keys`` — as produced by
    :func:`visible_top_level_keys` — has a text value ILIKE ``pattern``.

    The search counterpart of :func:`blind_task_data`: blinded callers may
    search only what they may see. Key matching is case-insensitive like the
    labeling UI's binding resolver (a ``$sachverhalt`` binding makes a
    ``Sachverhalt`` key searchable); non-object payloads never match.
    """
    keys = sorted(visible_keys)
    data_json = cast(data_column, JSON)
    data_obj = case(
        (func.json_typeof(data_json) == "object", data_json),
        else_=cast(literal("{}"), JSON),
    )
    kv = func.json_each_text(data_obj).table_valued("key", "value").alias("kv")
    return exists(
        select(literal(1))
        .select_from(kv)
        .where(func.lower(kv.c.key).in_(keys), kv.c.value.ilike(pattern))
    )
