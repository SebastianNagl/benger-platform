"""Load a project's method selection (shared/evaluation_methods.py) in an
async handler: the extension hook's answer, which runs on the sync side of
the request's session."""

from typing import Any, Iterable, Optional

import extensions
from evaluation_methods import MethodSelection, build_method_selection, project_configs
from extension_activation import use_context as use_extension_context


def method_answer_sync(sync_db, project, user_ids: Optional[Iterable[str]] = None) -> Any:
    """The extension hook's answer for ``project`` and the answers of
    ``user_ids`` (``None``: every account with an answer in the project), or
    ``None`` when the project has fewer than two enabled configs (nothing to
    choose between) or no package answers."""
    configs = project_configs(project)
    if len(configs) < 2:
        return None
    if user_ids is None:
        from project_models import Annotation, Task

        user_ids = [
            u
            for (u,) in sync_db.query(Annotation.completed_by)
            .join(Task, Task.id == Annotation.task_id)
            .filter(Task.project_id == project.id, Annotation.completed_by.isnot(None))
            .distinct()
        ]
    wanted = sorted({str(u) for u in user_ids if u})
    # The project's organizations decide whether a package is active here.
    with use_extension_context(project_id=project.id):
        return extensions.evaluation_method_selection(sync_db, project, configs, wanted)


async def load_method_answer(db, project, user_ids: Optional[Iterable[str]] = None) -> Any:
    """:func:`method_answer_sync` on the sync side of an async session."""
    if len(project_configs(project)) < 2:
        return None
    return await db.run_sync(lambda sync_db: method_answer_sync(sync_db, project, user_ids))


async def load_method_selection(
    db, project, user_ids: Optional[Iterable[str]] = None
) -> MethodSelection:
    """The method selection of ``project`` for answers of ``user_ids``.

    The hook is asked only when the project has two enabled configs or more:
    with fewer there is nothing to choose between.
    """
    answer = await load_method_answer(db, project, list(user_ids or []))
    return build_method_selection(project_configs(project), answer)
