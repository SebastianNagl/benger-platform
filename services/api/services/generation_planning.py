"""Which (task, model, prompt structure) cells a generation run queues.

Shared by the generate endpoint (``routers/generation_task_list.py``), which
dispatches the cells, and the cost estimate (``routers/cost_estimate.py``),
which prices them, so the estimate counts exactly what a run starts. The
generation grid resolves a cell's status with the same :func:`resolve_cell`.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select

from models import ResponseGeneration

# A cell whose newest row ended without an answer gets generated again under
# mode "missing": failed, stopped by the user, or cancelled by a rerun. Pending,
# running and paused cells are still in flight; completed ones are done.
MISSING_MODE_REGENERATE_STATUSES = frozenset({"failed", "stopped", "cancelled"})

Cell = Tuple[str, str, Optional[str]]


def implicit_structure_keys(prompt_structures) -> List[str]:
    """The project's generation structures (the grid's columns, and the keys a
    run must choose from).

    Handles both the dict shape and the legacy list shape, and skips
    structures flagged ``exclude_from_generation`` — prompts that other
    features reference by key (e.g. Bewertungsbogen generation) without
    being general generation prompts. Explicitly requested structure_keys
    bypass this filter (validated against ALL known keys).
    """
    if isinstance(prompt_structures, dict):
        return [
            key
            for key, entry in prompt_structures.items()
            if not (isinstance(entry, dict) and entry.get("exclude_from_generation"))
        ]
    if isinstance(prompt_structures, list):
        return [
            ps.get("key", str(i))
            for i, ps in enumerate(prompt_structures)
            if not (isinstance(ps, dict) and ps.get("exclude_from_generation"))
        ]
    return []


class StructureKeysRequired(ValueError):
    """A run on a project with generation structures named none of them."""

    def __init__(self, available: Sequence[str]):
        self.available = sorted(available)
        super().__init__(
            "structure_keys is required: this project has prompt structures "
            f"{self.available}; name the ones to generate"
        )


def run_structure_keys(
    generation_config: Optional[dict], requested: Optional[Sequence[str]]
) -> List[Optional[str]]:
    """The structures a run generates: the requested ones, or ``[None]`` for a
    project without generation structures.

    A project WITH structures must name them. Falling back to all of them made
    a call that simply omitted the field generate every structure (2-3x the
    cost on ZJS and Benchathon); the dialog always sends its selection, so
    only scripts and API clients ever hit that default.
    """
    if requested:
        return list(requested)
    keys = implicit_structure_keys((generation_config or {}).get("prompt_structures", {}))
    if keys:
        raise StructureKeysRequired(keys)
    return [None]


def latest_status_stmt(project_id: str, task_ids: Sequence[str], model_ids: Sequence[str]):
    """Status of the newest ``response_generations`` row per (task, model,
    structure). One round-trip (issue #83), backed by
    ``ix_response_generations_cell`` (migration 052)."""
    return (
        select(
            ResponseGeneration.task_id,
            ResponseGeneration.model_id,
            ResponseGeneration.structure_key,
            ResponseGeneration.status,
        )
        .where(
            ResponseGeneration.project_id == project_id,
            ResponseGeneration.task_id.in_(task_ids),
            ResponseGeneration.model_id.in_(model_ids),
        )
        .distinct(
            ResponseGeneration.task_id,
            ResponseGeneration.model_id,
            ResponseGeneration.structure_key,
        )
        .order_by(
            ResponseGeneration.task_id,
            ResponseGeneration.model_id,
            ResponseGeneration.structure_key,
            ResponseGeneration.created_at.desc(),
        )
    )


def resolve_cell(latest: Dict[tuple, object], task_id, model_id, structure_key):
    """The newest row (or value) for a cell, falling back to a legacy
    NULL-structure row when the exact structure has none."""
    exact = latest.get((task_id, model_id, structure_key))
    if exact is not None:
        return exact
    if structure_key is not None:
        return latest.get((task_id, model_id, None))
    return None


def select_cells(
    task_ids: Sequence[str],
    model_ids: Sequence[str],
    structure_keys: Sequence[Optional[str]],
    mode: Optional[str],
    latest_status: Dict[tuple, str],
) -> List[Cell]:
    """The cells to queue. ``all``/``single`` (or no mode) queue every cell;
    ``missing`` only those without a row or whose newest row ended without
    an answer."""
    cells: List[Cell] = []
    for task_id in task_ids:
        for model_id in model_ids:
            for structure_key in structure_keys:
                if mode == "missing":
                    status = resolve_cell(latest_status, task_id, model_id, structure_key)
                    if status is not None and status not in MISSING_MODE_REGENERATE_STATUSES:
                        continue
                cells.append((task_id, model_id, structure_key))
    return cells


def _status_map(rows) -> Dict[tuple, str]:
    return {(r.task_id, r.model_id, r.structure_key): r.status for r in rows}


async def plan_generation_cells(
    db,
    project_id: str,
    task_ids: Sequence[str],
    model_ids: Sequence[str],
    structure_keys: Sequence[Optional[str]],
    mode: Optional[str],
) -> List[Cell]:
    """Async: the cells a run queues (generate endpoint)."""
    latest: Dict[tuple, str] = {}
    if mode == "missing" and task_ids and model_ids:
        rows = (await db.execute(latest_status_stmt(project_id, task_ids, model_ids))).all()
        latest = _status_map(rows)
    return select_cells(task_ids, model_ids, structure_keys, mode, latest)


def plan_generation_cells_sync(
    db,
    project_id: str,
    task_ids: Sequence[str],
    model_ids: Sequence[str],
    structure_keys: Sequence[Optional[str]],
    mode: Optional[str],
) -> List[Cell]:
    """Sync twin (cost estimate)."""
    latest: Dict[tuple, str] = {}
    if mode == "missing" and task_ids and model_ids:
        rows = db.execute(latest_status_stmt(project_id, task_ids, model_ids)).all()
        latest = _status_map(rows)
    return select_cells(task_ids, model_ids, structure_keys, mode, latest)
