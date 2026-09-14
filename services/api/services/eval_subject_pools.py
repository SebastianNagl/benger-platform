"""How many evaluation subjects a project has on each side.

An evaluation grades two kinds of subject: model generations, for the
model-side prediction fields, and human annotations, for the human-side ones
(``eval_field_classification`` decides which side a field is on). The cost
preview multiplies these pools by per-call prices, and the evaluation-config
save uses them to warn about a config whose side has nothing to grade. One
query pair serves both, so the preview and the warning cannot disagree about
what a project contains.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from sqlalchemy.orm import Session


def count_eval_subject_pools(
    db: Session,
    project_id: str,
    *,
    model_ids: Optional[List[str]] = None,
    annotator_user_ids: Optional[List[str]] = None,
    generations: bool = True,
    annotations: bool = True,
) -> Tuple[int, int]:
    """``(generation_count, annotation_count)`` for one project.

    Generations are every row on the project's tasks, narrowed to
    ``model_ids`` when given. Annotations are the non-cancelled rows, narrowed
    to ``annotator_user_ids`` when given. Pass ``generations=False`` or
    ``annotations=False`` to skip a query whose answer is not needed; a
    skipped side reports 0.
    """
    from models import Generation
    from project_models import Annotation, Task

    gen_count = 0
    if generations:
        # Generation has no `project_id` column; it scopes through Task.
        gen_q = (
            db.query(Generation)
            .join(Task, Generation.task_id == Task.id)
            .filter(Task.project_id == project_id)
        )
        if model_ids:
            gen_q = gen_q.filter(Generation.model_id.in_(model_ids))
        gen_count = gen_q.count()

    ann_count = 0
    if annotations:
        ann_q = (
            db.query(Annotation)
            .join(Task, Annotation.task_id == Task.id)
            .filter(Task.project_id == project_id, Annotation.was_cancelled == False)  # noqa: E712
        )
        if annotator_user_ids:
            ann_q = ann_q.filter(Annotation.completed_by.in_(annotator_user_ids))
        ann_count = ann_q.count()

    return gen_count, ann_count
