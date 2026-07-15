"""Supplementary coverage for the multi-field results + available-fields reads.

Complements ``tests/integration/test_eval_multifield_branches.py`` by driving the
still-uncovered branches after the greenlet-coverage fix:
  * ``results.py._resolve_scope_block`` — the scoped-run block that resolves
    ``annotator_user_ids`` to display names (pseudonym-aware) and echoes
    ``task_ids`` / ``model_ids``.
  * ``results.py`` immediate/human run-level metric key parsing (the
    ``pred_field|metric`` 2-part shape).
  * ``fields.py`` reference fields sourced from ``project.evaluation_config``'s
    ``detected_answer_types`` ``to_name`` mappings.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from auth_module.dependencies import require_user
from auth_module.models import User as AuthUser
from main import app
from models import EvaluationRun, User
from project_models import Project, ProjectOrganization, Task

BASE = "/api/evaluations"


def _uid() -> str:
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user):
    au = AuthUser(
        id=db_user.id, username=db_user.username, email=db_user.email, name=db_user.name,
        is_superadmin=db_user.is_superadmin, is_active=True, email_verified=True,
        created_at=getattr(db_user, "created_at", None) or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: au
    try:
        yield au
    finally:
        app.dependency_overrides.pop(require_user, None)


async def _mk_user(db, *, superadmin=True, name="U", use_pseudonym=False, pseudonym=None) -> User:
    u = User(
        id=_uid(), username=f"u-{_uid()[:8]}", email=f"{_uid()[:8]}@e.com", name=name,
        is_superadmin=superadmin, is_active=True, email_verified=True,
        use_pseudonym=use_pseudonym, pseudonym=pseudonym,
        created_at=datetime.now(timezone.utc),
    )
    db.add(u)
    await db.flush()
    return u


async def _mk_project(db, owner, **kw) -> Project:
    p = Project(id=_uid(), title="P", created_by=owner.id, is_private=True, **kw)
    db.add(p)
    await db.flush()
    return p


async def _mk_run(db, project, owner, *, metrics=None, eval_metadata=None, model_id="gpt-4"):
    er = EvaluationRun(
        id=_uid(), project_id=project.id, model_id=model_id, evaluation_type_ids=["accuracy"],
        status="completed", metrics=metrics or {}, samples_evaluated=1,
        eval_metadata=eval_metadata if eval_metadata is not None else {"evaluation_type": "evaluation"},
        created_by=owner.id, created_at=datetime.now(timezone.utc),
    )
    db.add(er)
    await db.flush()
    return er


@pytest.mark.integration
class TestScopeBlock:
    @pytest.mark.asyncio
    async def test_scope_resolves_annotator_display_and_ids(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        annotator = await _mk_user(async_test_db, superadmin=False, name="Anna Annotator")
        p = await _mk_project(async_test_db, owner)
        er = await _mk_run(
            async_test_db, p, owner,
            metrics={"cfg|__response__|musterloesung|bleu": 0.5},
            eval_metadata={
                "evaluation_type": "evaluation",
                "evaluation_configs": [{"id": "cfg", "metric": "bleu"}],
                "task_ids": ["t1", "t2"],
                "model_ids": ["gpt-4"],
                "annotator_user_ids": [annotator.id],
            },
        )
        await async_test_db.commit()

        with _as_user(owner):
            r = await async_test_client.get(f"{BASE}/run/results/{er.id}")
        assert r.status_code == 200, r.text
        scope = r.json()["scope"]
        assert scope is not None
        assert scope["task_ids"] == ["t1", "t2"]
        assert scope["model_ids"] == ["gpt-4"]
        assert len(scope["annotators"]) == 1
        assert scope["annotators"][0]["user_id"] == annotator.id
        assert scope["annotators"][0]["display"] == "Anna Annotator"

    @pytest.mark.asyncio
    async def test_scope_uses_pseudonym_and_missing_user_fallback(self, async_test_client, async_test_db):
        owner = await _mk_user(async_test_db)
        pseud = await _mk_user(
            async_test_db, superadmin=False, name="Real Name",
            use_pseudonym=True, pseudonym="Bearbeiter-7",
        )
        ghost_id = _uid()  # id with no User row → display falls back to id[:8]
        p = await _mk_project(async_test_db, owner)
        er = await _mk_run(
            async_test_db, p, owner,
            eval_metadata={
                "evaluation_type": "evaluation",
                "annotator_user_ids": [pseud.id, ghost_id],
            },
        )
        await async_test_db.commit()

        with _as_user(owner):
            r = await async_test_client.get(f"{BASE}/run/results/{er.id}")
        assert r.status_code == 200, r.text
        by_id = {a["user_id"]: a["display"] for a in r.json()["scope"]["annotators"]}
        assert by_id[pseud.id] == "Bearbeiter-7"  # pseudonym wins
        assert by_id[ghost_id] == ghost_id[:8]  # missing-user fallback


@pytest.mark.integration
class TestImmediateShapeParsing:
    @pytest.mark.asyncio
    async def test_project_results_two_part_metric_key(self, async_test_client, async_test_db):
        """The run-level 'pred_field|metric' 2-part key (immediate / human-graded
        shape, no config_id/ref_field) still groups + headlines a score."""
        owner = await _mk_user(async_test_db)
        p = await _mk_project(async_test_db, owner)
        await _mk_run(
            async_test_db, p, owner,
            metrics={"human:loesung|korrektur_falloesung": {"value": 0.75}},
            eval_metadata={"evaluation_type": "immediate"},
            model_id="immediate",
        )
        await async_test_db.commit()

        with _as_user(owner):
            r = await async_test_client.get(f"{BASE}/run/results/project/{p.id}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total_count"] == 1
        cfg = body["evaluations"][0]["results_by_config"]["korrektur_falloesung"]
        combo = cfg["field_results"][0]
        assert combo["prediction_field"] == "human:loesung"
        # aggregate coerced from the {value} shape.
        assert cfg["aggregate_score"] == pytest.approx(0.75)


@pytest.mark.integration
class TestAvailableFieldsEvaluationConfig:
    @pytest.mark.asyncio
    async def test_reference_fields_from_evaluation_config(self, async_test_client, async_test_db):
        """detected_answer_types[].to_name in evaluation_config contributes
        reference fields (the branch existing tests don't exercise)."""
        owner = await _mk_user(async_test_db)
        p = await _mk_project(
            async_test_db, owner,
            label_config='<View><Text name="t" value="$text"/></View>',
            evaluation_config={"detected_answer_types": [{"to_name": "gutachten"}]},
        )
        async_test_db.add(Task(id=_uid(), project_id=p.id, data={"text": "x"}, inner_id=1))
        await async_test_db.commit()

        with _as_user(owner):
            r = await async_test_client.get(f"{BASE}/projects/{p.id}/available-fields")
        assert r.status_code == 200, r.text
        assert "gutachten" in r.json()["reference_fields"]
