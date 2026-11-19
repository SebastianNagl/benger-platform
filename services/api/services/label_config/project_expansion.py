"""A project's label config with every <Repeater> expanded.

A <Repeater> only gets concrete control names against a task's data. Where a
consumer needs the field names of a whole project (evaluation field
detection, the field lists of the evaluation UI, the config exported to Label
Studio), each Repeater is expanded to the longest array any task of the
project holds; the lengths come from one SQL aggregate per Repeater, so no
task data is loaded. A config without a Repeater is returned as it is.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from sqlalchemy import String, case, cast, func, literal, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from label_config_repeater import (
    data_path_segments,
    expand_repeaters_with_counts,
    has_repeater,
    repeater_blocks,
)
from project_models import Task


def _longest_array_query(project_id: str, binding: str):
    path = data_path_segments(binding)
    value = cast(Task.data, JSONB).op("#>")(cast(literal(path), ARRAY(String)))
    # jsonb_array_length raises on a non-array; CASE only evaluates the
    # branch it takes, so tasks without the array count as no row.
    length = case(
        (func.jsonb_typeof(value) == "array", func.jsonb_array_length(value)),
        else_=None,
    )
    return select(func.max(length)).where(Task.project_id == project_id)


async def repeater_item_counts_async(
    db: AsyncSession, project_id: str, label_config: Optional[str]
) -> Dict[str, int]:
    """``{on binding: longest array over the project's tasks}`` per Repeater."""
    counts: Dict[str, int] = {}
    for block in repeater_blocks(label_config):
        if block.on in counts or not data_path_segments(block.on):
            continue
        longest = (await db.execute(_longest_array_query(project_id, block.on))).scalar()
        counts[block.on] = int(longest or 0)
    return counts


async def expanded_project_label_config_async(
    db: AsyncSession, project_id: str, label_config: Optional[str]
) -> Tuple[Optional[str], Dict[str, int]]:
    """``(expanded config, item counts)`` for a project; a config without a
    Repeater comes back unchanged with empty counts."""
    if not has_repeater(label_config):
        return label_config, {}
    counts = await repeater_item_counts_async(db, project_id, label_config)
    return expand_repeaters_with_counts(label_config, counts), counts
