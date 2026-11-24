"""Load a project's method selection (shared/evaluation_methods.py) in an
async handler: the static config fields plus the extension hook's answer,
which runs on the sync side of the request's session."""

from typing import Iterable, Optional

import extensions
from evaluation_methods import MethodSelection, build_method_selection, project_configs
from extension_activation import use_context as use_extension_context


async def load_method_selection(
    db, project, user_ids: Optional[Iterable[str]] = None
) -> MethodSelection:
    """The method selection of ``project`` for answers of ``user_ids``.

    The hook is asked only when the project has two enabled configs or more:
    with fewer there is nothing to choose between.
    """
    configs = project_configs(project)
    if len(configs) < 2:
        return build_method_selection(configs)
    wanted = sorted({str(u) for u in (user_ids or []) if u})

    def _ask(sync_db):
        # The project's organizations decide whether a package is active here.
        with use_extension_context(project_id=project.id):
            return extensions.evaluation_method_selection(sync_db, project, configs, wanted)

    answer = await db.run_sync(_ask)
    return build_method_selection(configs, answer)
