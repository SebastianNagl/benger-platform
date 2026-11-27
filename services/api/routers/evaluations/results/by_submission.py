"""The project's evaluation methods, and its results as one score per method
and submission.

``GET /projects/{project_id}/results/methods`` tells the results page which
configs grade one method together (shared/evaluation_methods.py), so it can
list a method once and keep its research configs out of the default view.

``GET /projects/{project_id}/results/by-submission`` is the readable results
file for the people who grade: one row per submission (the latest answer of
each account to each task), one column per evaluation method with its current
score (shared/current_scores.py) and, where the method gives them, its grade
points. A method graded by alternative configs takes the official config's
score for the submitting account, else the score of another config of the
group (shared/evaluation_methods.py, ``teacher_current_rows``); when that
happens anywhere in a column, a ``(graded by)`` column names the config
that supplied each score. A method that has not graded a submission yet (a human Korrektur that
has not happened, a judge still running) leaves the cell empty. A config that
grades once per reference field (shared/current_scores.py) has one current
score per reference field, so it gets one column per reference field. Research
configs are left out unless ``include_research`` is set, and then every config
gets its own column. The comprehensive project export stays the full record
of every run.
"""

import csv
import io
from datetime import datetime, timezone

from fastapi.responses import Response

import current_scores
from evaluation_methods import project_configs, teacher_current_rows
from metric_filters import graded_reference_fields
from spreadsheet_cells import formula_safe
from user_display import masked_name

from ._common import *  # noqa: F401,F403  (binds _common.__all__, the shared surface)
from .by_task_model import _require_content_access, _task_preview_rows
from .method_selection import load_method_selection

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


def _reference_columns(configs) -> list:
    """The reference fields a column of ``configs`` splits into: ``[""]``
    (one column) unless one of them grades once per reference field."""
    refs: list = []
    for config in configs:
        graded = graded_reference_fields(config)
        if len(graded) > 1:
            refs.extend(str(r) for r in graded if str(r) not in refs)
    return refs or [""]


def _method_columns(configs, selection, include_research: bool):
    """``[(label, config ids, grouped, reference field)]`` in config order;
    the reference field is ``""`` for a column that is not split by it."""
    by_id = {str(c["id"]): c for c in configs}
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
    split = []
    for label, ids, grouped in columns:
        refs = _reference_columns([by_id[cid] for cid in ids])
        for ref in refs:
            split.append((f"{label} ({ref})" if ref else label, ids, grouped, ref))
    # Two methods with one label would share a column name.
    used: dict = {}
    out = []
    for label, ids, grouped, ref in split:
        used[label] = used.get(label, 0) + 1
        out.append((label if used[label] == 1 else f"{label} ({used[label]})", ids, grouped, ref))
    return out


@router.get("/projects/{project_id}/results/by-submission")
async def export_project_results_by_submission(
    project_id: str,
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
    wanted_configs = {cid for _label, ids, _g, _ref in columns for cid in ids}
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
    shown = teacher_current_rows(selection, current, submitter_of, configs_lookup)

    # Per (annotation, column): the newest current row with a score, a row of
    # the official config before a stand-in's (a stand-in graded once per
    # prediction field may stand in for another reference field only). A row
    # of a config graded once per prediction field (reference part "") fills
    # every reference column of its method.
    epoch = datetime.min.replace(tzinfo=timezone.utc)

    def _rank(row):
        return (shown.get(str(row.id)) is None, row.created_at or epoch)

    picked: dict = {}
    for row in current:
        config_id = current_scores.cell_config_id(row.evaluation_config_id, row.field_name)
        row_ref = current_scores.cell_ref_field(row.field_name, configs_lookup.get(config_id))
        for index, (_label, ids, grouped, ref) in enumerate(columns):
            if config_id not in ids or row_ref not in ("", ref):
                continue
            if grouped and str(row.id) not in shown:
                continue
            if _extract_primary_score(row.metrics) is None:
                continue
            key = (row.annotation_id, index)
            held = picked.get(key)
            if held is None or _rank(row) > _rank(held):
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
    has_stand_in = [False] * len(columns)
    label_of = {str(c["id"]): _config_label(c) for c in configs}
    records = []
    for sub in sorted(
        submissions,
        key=lambda s: (task_order.get(s.task_id, len(task_order)), str(s.task_id), str(s.completed_by)),
    ):
        methods = []
        for index in range(len(columns)):
            row = picked.get((sub.id, index))
            if row is None:
                methods.append({"score": None, "grade_points": None, "graded_by": None})
                continue
            points = current_scores.extract_grade_points(full_metrics.get(row.id))
            if points is not None:
                has_points[index] = True
            if shown.get(str(row.id)) is not None and columns[index][2]:
                has_stand_in[index] = True
            config_id = current_scores.cell_config_id(row.evaluation_config_id, row.field_name)
            methods.append(
                {
                    "score": _extract_primary_score(row.metrics),
                    "grade_points": points,
                    "graded_by": label_of.get(config_id, config_id),
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
    output = io.StringIO()
    writer = csv.writer(output)
    header = ["task_id", "task", "submitter_id", "submitter", "submitted_at"]
    for index, (label, _ids, _grouped, _ref) in enumerate(columns):
        header.append(formula_safe(label))
        if has_points[index]:
            header.append(formula_safe(f"{label} (grade points)"))
        if has_stand_in[index]:
            header.append(formula_safe(f"{label} (graded by)"))
    writer.writerow(header)
    for record in records:
        line = [
            record["task_id"],
            formula_safe(record["task"]),
            record["submitter_id"],
            formula_safe(record["submitter"]),
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
            if has_stand_in[index]:
                line.append(formula_safe(method["graded_by"] or ""))
        writer.writerow(line)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="results_by_submission_{project_id}_{stamp}.csv"'
        },
    )
