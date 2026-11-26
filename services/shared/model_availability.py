"""Refusing official catalog models that are no longer active.

Switching a catalog row off (``is_active: false`` in ``llm_models.yaml``)
hides the model from every picker, but a project, evaluation config or
organization setting saved earlier still names it. Without a check, such a
saved config keeps queueing jobs for a model the provider has retired (each
one fails at the provider) or rerouted to another model (each one is
silently answered by that other model). The generation and evaluation entry
points, the generation worker and the judge factory therefore refuse an
inactive official model with :func:`inactive_models_message`, which names
the model and says what to do.

Custom (BYOM) rows keep their own checks, which already refuse an inactive
custom model. Ids the catalog does not know are left to the existing
unknown-model handling.
"""

from __future__ import annotations

from typing import Iterable, List, Optional


class InactiveModelError(Exception):
    """A job names an official catalog model that is no longer active."""

    def __init__(self, model_ids: Iterable[str]):
        self.model_ids = sorted(set(model_ids))
        super().__init__(inactive_models_message(self.model_ids))


def inactive_models_message(model_ids: Iterable[str]) -> str:
    """The user-facing refusal for retired catalog models."""
    ids = ", ".join(sorted(set(model_ids)))
    return (
        f"Model(s) no longer available: {ids}. The provider has retired or "
        "replaced them, so BenGER no longer runs them. Choose a current model "
        "in the project's settings and start again."
    )


def inactive_official_model_ids(db, model_ids: Iterable[Optional[str]]) -> List[str]:
    """Of ``model_ids``, the ones the catalog holds as official rows that are
    no longer active (sync session). Sorted, without duplicates."""
    from models import LLMModel

    ids = sorted({m for m in model_ids if isinstance(m, str) and m})
    if not ids:
        return []
    rows = (
        db.query(LLMModel.id)
        .filter(
            LLMModel.id.in_(ids),
            LLMModel.is_official.is_(True),
            LLMModel.is_active.is_(False),
        )
        .all()
    )
    return sorted(row[0] for row in rows)


async def inactive_official_model_ids_async(
    db, model_ids: Iterable[Optional[str]]
) -> List[str]:
    """:func:`inactive_official_model_ids` for an async session."""
    from sqlalchemy import select

    from models import LLMModel

    ids = sorted({m for m in model_ids if isinstance(m, str) and m})
    if not ids:
        return []
    rows = (
        await db.execute(
            select(LLMModel.id).where(
                LLMModel.id.in_(ids),
                LLMModel.is_official.is_(True),
                LLMModel.is_active.is_(False),
            )
        )
    ).all()
    return sorted(row[0] for row in rows)


def configured_judge_model_ids(metric_parameters) -> List[str]:
    """The judge models an evaluation config names itself: the legacy
    ``judge_model`` and every ``judges[].judge_model_id``. The platform
    default judge (used when it names none) is not included."""
    if not isinstance(metric_parameters, dict):
        return []
    ids: List[str] = []
    legacy = metric_parameters.get("judge_model")
    if isinstance(legacy, str) and legacy:
        ids.append(legacy)
    judges = metric_parameters.get("judges")
    if isinstance(judges, list):
        for entry in judges:
            if isinstance(entry, dict):
                judge = entry.get("judge_model_id")
                if isinstance(judge, str) and judge:
                    ids.append(judge)
    return ids


def row_is_inactive_official(row) -> bool:
    """Whether a loaded ``LLMModel`` row is an official model switched off."""
    return (
        row is not None
        and bool(getattr(row, "is_official", True))
        and not bool(getattr(row, "is_active", True))
    )
