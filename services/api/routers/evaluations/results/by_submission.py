"""The project's evaluation methods, and its results as one score per method
and submission.

``GET /projects/{project_id}/results/methods`` tells the results page which
configs grade one method together (shared/evaluation_methods.py), so it can
list a method once and keep its research configs out of the default view.

``GET /projects/{project_id}/results/by-submission`` is the readable results
file for the people who grade: one row per submission (the latest answer of
each account to each task), one column per evaluation method with its current
score (shared/current_scores.py) and, where the method gives them, its grade
points. A method that has not graded a submission yet (a human Korrektur that
has not happened, a judge still running) leaves the cell empty. Research
configs are left out unless ``include_research`` is set, and then every config
gets its own column. The comprehensive project export stays the full record
of every run.
"""

import csv
import io
import json
from datetime import datetime, timezone

from fastapi.responses import Response

import current_scores
from evaluation_methods import project_configs
from user_display import masked_name

from ._common import *  # noqa: F401,F403  (binds _common.__all__, the shared surface)
from .by_task_model import _require_content_access, _task_preview_rows
from .method_selection import load_method_selection

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _cell_text(value):
    """A text cell a spreadsheet will not run as a formula."""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def _config_label(config: dict) -> str:
    label = config.get("display_name")
    if isinstance(label, str) and label.strip():
        return label.strip()
    return str(config.get("metric") or config.get("id"))


async def _load_project(db, current_user, project_id: str):
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found",
        )
    if not await check_project_accessible_async(db, current_user, project_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    await _require_content_access(db, current_user, project_id)
    return project


@router.get("/projects/{project_id}/results/methods")
async def get_project_evaluation_methods(
    project_id: str,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """The project's method groups and the configs the default views leave
    out as research data (shared/evaluation_methods.py)."""
    project = await _load_project(db, current_user, project_id)
    configs = project_configs(project)
    selection = await load_method_selection(db, project)
    display_names = {str(c["id"]): _config_label(c) for c in configs}
    return {"project_id": project_id, **selection.to_public(display_names)}


def _method_columns(configs, selection, include_research: bool):
    """``[(label, config ids, grouped)]`` in config order."""
    columns = []
    seen_groups = set()
    group_of = selection.group_of
    for config in configs:
        cid = str(config["id"])
        group = group_of.get(cid)
        if include_research or group is None:
            if not include_research and cid in selection.research_only:
                continue
            columns.append((_config_label(config), [cid], False))
            continue
        if group in seen_groups:
            continue
        seen_groups.add(group)
        official = selection.official_config(group)
        label = selection.labels.get(group) or next(
            (_config_label(c) for c in configs if str(c["id"]) == official), group
        )
        columns.append((label, list(selection.groups[group]), True))
    # Two methods with one label would share a column name.
    used: dict = {}
    out = []
    for label, ids, grouped in columns:
        used[label] = used.get(label, 0) + 1
        out.append((label if used[label] == 1 else f"{label} ({used[label]})", ids, grouped))
    return out


@router.get("/projects/{project_id}/results/by-submission")
async def export_project_results_by_submission(
    project_id: str,
    format: str = Query("csv", pattern="^(csv|json)$"),
    include_research: bool = Query(
        False,
        description="Also list the research configs, each in its own column.",
    ),
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_async_db),
):
    """One row per submission with the current score of every method."""
    from models import TaskEvaluation
    from models import TaskEvaluationMetricKeys as MK
    from models import User as DBUser

    project = await _load_project(db, current_user, project_id)
    configs = project_configs(project)
    configs_lookup = current_scores.configs_by_id(project.evaluation_config)

    latest = (
        select(
            Annotation.id.label("ann_id"),
            func.row_number()
            .over(
                partition_by=[Annotation.task_id, Annotation.completed_by],
                order_by=Annotation.created_at.desc(),
            )
            .label("rn"),
        )
        .join(Task, Task.id == Annotation.task_id)
        .where(
            Task.project_id == project_id,
            Annotation.completed_by.isnot(None),
            Annotation.was_cancelled == False,  # noqa: E712
        )
        .subquery()
    )
    submissions = (
        await db.execute(
            select(
                Annotation.id,
                Annotation.task_id,
                Annotation.completed_by,
                Annotation.created_at,
                DBUser.pseudonym,
            )
            .join(latest, latest.c.ann_id == Annotation.id)
            .join(DBUser, DBUser.id == Annotation.completed_by)
            .where(latest.c.rn == 1)
        )
    ).all()

    selection = await load_method_selection(
        db, project, {s.completed_by for s in submissions}
    )
    columns = _method_columns(configs, selection, include_research)
    wanted_configs = {cid for _label, ids, _g in columns for cid in ids}
    submitter_of = {s.id: s.completed_by for s in submissions}

    rows = []
    if submissions and wanted_configs:
        rows = (
            await db.execute(
                select(
                    MK.task_evaluation_id.label("id"),
                    MK.task_id,
                    MK.annotation_id,
                    MK.generation_id,
                    MK.field_name,
                    MK.evaluation_config_id,
                    MK.metrics_lite.label("metrics"),
                    MK.created_at,
                ).where(
                    MK.annotation_id.in_(list(submitter_of)),
                    MK.generation_id.is_(None),
                )
            )
        ).all()
    current = list(current_scores.pick_current(rows, configs_lookup).values())

    # Per (annotation, column): the newest current row with a score.
    picked: dict = {}
    for row in current:
        config_id = current_scores.cell_config_id(row.evaluation_config_id, row.field_name)
        for index, (_label, ids, grouped) in enumerate(columns):
            if config_id not in ids:
                continue
            if grouped and not selection.is_official(config_id, submitter_of.get(row.annotation_id)):
                continue
            if _extract_primary_score(row.metrics) is None:
                continue
            key = (row.annotation_id, index)
            held = picked.get(key)
            if held is None or (row.created_at or datetime.min.replace(tzinfo=timezone.utc)) > (
                held.created_at or datetime.min.replace(tzinfo=timezone.utc)
            ):
                picked[key] = row

    # Grade points live in the parts of the metrics the lite projection drops.
    full_metrics = {}
    picked_ids = [r.id for r in picked.values()]
    for start in range(0, len(picked_ids), 1000):
        chunk = picked_ids[start:start + 1000]
        full_metrics.update(
            (
                await db.execute(
                    select(TaskEvaluation.id, TaskEvaluation.metrics).where(
                        TaskEvaluation.id.in_(chunk)
                    )
                )
            ).all()
        )

    previews = dict(await _task_preview_rows(db, project_id))
    task_order = {tid: i for i, tid in enumerate(previews)}
    has_points = [False] * len(columns)
    records = []
    for sub in sorted(
        submissions,
        key=lambda s: (task_order.get(s.task_id, len(task_order)), str(s.task_id), str(s.completed_by)),
    ):
        methods = []
        for index, (label, _ids, _grouped) in enumerate(columns):
            row = picked.get((sub.id, index))
            if row is None:
                methods.append({"method": label, "score": None, "grade_points": None, "evaluation_config_id": None, "graded_at": None})
                continue
            points = current_scores.extract_grade_points(full_metrics.get(row.id))
            if points is not None:
                has_points[index] = True
            methods.append(
                {
                    "method": label,
                    "score": _extract_primary_score(row.metrics),
                    "grade_points": points,
                    "evaluation_config_id": current_scores.cell_config_id(
                        row.evaluation_config_id, row.field_name
                    ),
                    "graded_at": row.created_at.isoformat() if row.created_at else None,
                }
            )
        records.append(
            {
                "task_id": sub.task_id,
                "task": previews.get(sub.task_id, ""),
                "submitter_id": sub.completed_by,
                # A file never names anyone: account id and pseudonym only.
                "submitter": masked_name(user_id=sub.completed_by, pseudonym=sub.pseudonym),
                "submitted_at": sub.created_at.isoformat() if sub.created_at else None,
                "methods": methods,
            }
        )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    if format == "json":
        return Response(
            content=json.dumps(
                {"project_id": project_id, "methods": [c[0] for c in columns], "submissions": records},
                ensure_ascii=False,
            ),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="results_by_submission_{project_id}_{stamp}.json"'
            },
        )

    output = io.StringIO()
    writer = csv.writer(output)
    header = ["task_id", "task", "submitter_id", "submitter", "submitted_at"]
    for index, (label, _ids, _grouped) in enumerate(columns):
        header.append(_cell_text(label))
        if has_points[index]:
            header.append(_cell_text(f"{label} (grade points)"))
    writer.writerow(header)
    for record in records:
        line = [
            record["task_id"],
            _cell_text(record["task"]),
            record["submitter_id"],
            _cell_text(record["submitter"]),
            record["submitted_at"] or "",
        ]
        for index, method in enumerate(record["methods"]):
            score = method["score"]
            line.append("" if score is None else round(score, 4))
            if has_points[index]:
                points = method["grade_points"]
                if points is None:
                    line.append("")
                else:
                    line.append(int(points) if float(points).is_integer() else points)
        writer.writerow(line)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="results_by_submission_{project_id}_{stamp}.csv"'
        },
    )
