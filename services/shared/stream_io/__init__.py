"""Shared, behavior-preserving helpers extracted from the project import/export
stream drivers (``import_stream.py`` / ``export_stream.py``).

Why ``stream_io`` and not ``io``: ``/shared`` is first on ``sys.path`` in both
the api and workers containers (see benger-platform CLAUDE.md). A subpackage
literally named ``io`` would sit at ``sys.path[0]`` and shadow CPython's stdlib
``io`` module — which ``export_stream.py`` (``io.StringIO``) and
``storage/storage_service.py`` both import, and which the interpreter itself
re-imports during startup. That shadowing fatally breaks the interpreter
(``module 'io' has no attribute 'open'`` at ``init_sys_streams``), so the package
is named ``stream_io`` to keep the same intent without the collision.

This package holds ONLY logic that was genuinely duplicated or cleanly generic
across the two stream modules. Anything that differed subtly between import and
export was deliberately left in place (see the module-level notes in
``serialization.py``). Pure move/extract: no serialized shape, field name,
ordering, or behavior changed.
"""

from .batch_utils import drain_expunge, fetch_batch_children, stream_array_rows
from .query_builders import (
    build_eval_run_ids,
    build_gen_counts,
    build_task_id_subquery,
)
from .serialization import (
    build_project_export_data,
    empty_export_stats,
    serialize_evaluation_judge_run_row,
    serialize_evaluation_metric_row,
    serialize_human_evaluation_config_row,
    serialize_human_evaluation_result_row,
    serialize_human_evaluation_session_row,
    serialize_likert_scale_evaluation_row,
    serialize_post_annotation_response_row,
    serialize_preference_ranking_row,
    serialize_project_member_row,
    serialize_response_generation_row,
    serialize_task_assignment_row,
    serialize_user_row,
)

__all__ = [
    # batch_utils
    "drain_expunge",
    "fetch_batch_children",
    "stream_array_rows",
    # query_builders
    "build_task_id_subquery",
    "build_gen_counts",
    "build_eval_run_ids",
    # serialization
    "build_project_export_data",
    "empty_export_stats",
    "serialize_response_generation_row",
    "serialize_project_member_row",
    "serialize_task_assignment_row",
    "serialize_evaluation_metric_row",
    "serialize_evaluation_judge_run_row",
    "serialize_human_evaluation_config_row",
    "serialize_human_evaluation_session_row",
    "serialize_human_evaluation_result_row",
    "serialize_preference_ranking_row",
    "serialize_likert_scale_evaluation_row",
    "serialize_post_annotation_response_row",
    "serialize_user_row",
]
