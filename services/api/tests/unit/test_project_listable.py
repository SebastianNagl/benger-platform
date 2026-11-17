"""``project_listable()``: the predicate of every project list and count
(not deleted and not a creation-wizard draft), next to its instance twin
``project_is_wizard_draft``. The per-project deciders keep
``project_not_deleted`` so a creator still opens their own draft."""

from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from project_models import (
    Project,
    project_is_wizard_draft,
    project_listable,
    project_not_deleted,
)


def _sql(clause) -> str:
    return str(
        select(Project.id).where(clause).compile(dialect=postgresql.dialect())
    )


def test_listable_excludes_deleted_projects_and_drafts():
    sql = _sql(project_listable())
    assert "projects.deleted_at IS NULL" in sql
    assert "projects.is_wizard_draft IS false" in sql


def test_not_deleted_does_not_exclude_drafts():
    assert "is_wizard_draft" not in _sql(project_not_deleted())


def test_instance_twin():
    assert project_is_wizard_draft(SimpleNamespace(is_wizard_draft=True)) is True
    assert project_is_wizard_draft(SimpleNamespace(is_wizard_draft=False)) is False
    assert project_is_wizard_draft(SimpleNamespace()) is False
