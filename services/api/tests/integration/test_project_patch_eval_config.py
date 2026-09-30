"""``PATCH /api/projects/{id}`` writes ``evaluation_config`` like the eval-config PUT.

Both endpoints deep-merge into the same JSONB document, so the PATCH must not
store what the PUT rejects. Pinned here against Postgres (async lane):

- the PUT's checks (``runs_per_task``, every ``evaluation_configs`` entry,
  legacy ``selected_methods``) run on the merged document, before any write;
- only keys the body carries are checked, so a stored legacy value never
  blocks an unrelated save such as the eval-defaults card;
- the ``after_eval_config_save`` extension hook runs with the saved document,
  and an explicit ``korrektur_enabled`` in the same body still wins.

The Notenschlüssel (``grade_scale``) is covered in
``test_rubric_mirror_grade_key.py``.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

import extensions
from models import User
from project_models import Project

RUBRIC_TEMPLATE = "Bewerte {{answer}}"


def _uid():
    return str(uuid.uuid4())


@contextmanager
def _as_user(db_user):
    from auth_module.dependencies import require_user
    from auth_module.models import User as AuthUser
    from main import app

    auth_user = AuthUser(
        id=db_user.id,
        username=db_user.username,
        email=db_user.email,
        name=db_user.name,
        is_superadmin=db_user.is_superadmin,
        is_active=True,
        email_verified=True,
        created_at=db_user.created_at or datetime.now(timezone.utc),
    )
    app.dependency_overrides[require_user] = lambda: auth_user
    try:
        yield auth_user
    finally:
        app.dependency_overrides.pop(require_user, None)


async def _seed(db, evaluation_config=None):
    owner = User(
        id=_uid(),
        username=f"patch-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        name="Patch Tester",
        is_superadmin=False,
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(owner)
    await db.flush()
    project = Project(
        id=_uid(),
        title="Original",
        created_by=owner.id,
        is_private=True,
        evaluation_config=evaluation_config,
    )
    db.add(project)
    await db.commit()
    return owner, project.id


async def _stored(db, project_id):
    db.expire_all()
    return (
        await db.execute(
            select(Project.title, Project.evaluation_config, Project.korrektur_enabled).where(
                Project.id == project_id
            )
        )
    ).one()


async def _patch(client, project_id, body):
    return await client.patch(f"/api/projects/{project_id}", json=body)


def _entry(**overrides):
    entry = {
        "id": "a",
        "metric": "bleu",
        "prediction_fields": ["__all_model__"],
        "reference_fields": ["task.expected"],
        "enabled": True,
    }
    entry.update(overrides)
    return entry


@pytest.mark.integration
class TestPatchRunsTheEvalConfigChecks:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("value", [0, 26, "five", 2.5])
    async def test_runs_per_task_out_of_contract_is_422(
        self, async_test_client, async_test_db, value
    ):
        owner, project_id = await _seed(async_test_db, {"runs_per_task": 3})
        with _as_user(owner):
            resp = await _patch(
                async_test_client,
                project_id,
                {"title": "Neu", "evaluation_config": {"runs_per_task": value}},
            )
        assert resp.status_code == 422, resp.text
        assert "runs_per_task" in resp.json()["detail"]
        title, config, _ = await _stored(async_test_db, project_id)
        assert title == "Original"
        assert config == {"runs_per_task": 3}

    @pytest.mark.asyncio
    async def test_a_null_runs_per_task_deletes_it(self, async_test_client, async_test_db):
        owner, project_id = await _seed(
            async_test_db, {"runs_per_task": 3, "default_temperature": 0.2}
        )
        with _as_user(owner):
            resp = await _patch(
                async_test_client, project_id, {"evaluation_config": {"runs_per_task": None}}
            )
        assert resp.status_code == 200, resp.text
        _, config, _ = await _stored(async_test_db, project_id)
        assert config == {"default_temperature": 0.2}

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "entry, fragment",
        [
            (_entry(metric_parameters={"judges": []}), "judges"),
            (_entry(metric="llm_judge_rubric", metric_parameters={}), "custom_prompt_template"),
            (
                _entry(metric="llm_judge_falloesung", metric_parameters={"score_scale": "1-5"}),
                "score_scale",
            ),
            (_entry(prediction_fields=[]), "prediction_fields"),
        ],
    )
    async def test_an_invalid_entry_is_422_before_any_write(
        self, async_test_client, async_test_db, entry, fragment
    ):
        stored = {"evaluation_configs": [_entry()]}
        owner, project_id = await _seed(async_test_db, stored)
        with _as_user(owner):
            resp = await _patch(
                async_test_client,
                project_id,
                {"title": "Neu", "evaluation_config": {"evaluation_configs": [entry]}},
            )
        assert resp.status_code == 422, resp.text
        assert fragment in str(resp.json()["detail"])
        title, config, _ = await _stored(async_test_db, project_id)
        assert title == "Original"
        assert config == stored

    @pytest.mark.asyncio
    async def test_a_valid_entry_is_stored(self, async_test_client, async_test_db):
        owner, project_id = await _seed(async_test_db, {"default_temperature": 0.2})
        entry = _entry(
            id="r",
            metric="llm_judge_rubric",
            metric_parameters={"custom_prompt_template": RUBRIC_TEMPLATE},
        )
        with _as_user(owner):
            resp = await _patch(
                async_test_client, project_id, {"evaluation_config": {"evaluation_configs": [entry]}}
            )
        assert resp.status_code == 200, resp.text
        _, config, _ = await _stored(async_test_db, project_id)
        assert config["evaluation_configs"] == [entry]
        assert config["default_temperature"] == 0.2

    @pytest.mark.asyncio
    async def test_legacy_selected_methods_are_checked_like_the_put(
        self, async_test_client, async_test_db
    ):
        owner, project_id = await _seed(async_test_db, {})
        body = {
            "available_methods": {
                "answer": {"available_metrics": ["exact_match"], "available_human": []}
            },
            "selected_methods": {"answer": {"automated": ["nonexistent_metric"]}},
        }
        with _as_user(owner):
            resp = await _patch(async_test_client, project_id, {"evaluation_config": body})
        assert resp.status_code == 400, resp.text
        assert "nonexistent_metric" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_a_stored_legacy_value_does_not_block_an_unrelated_save(
        self, async_test_client, async_test_db
    ):
        """The eval-defaults card PATCHes only its own keys. Values stored
        before the checks existed must not turn that save into a 422."""
        legacy = {
            "runs_per_task": 99,
            "evaluation_configs": [_entry(metric="llm_judge_rubric", metric_parameters={})],
        }
        owner, project_id = await _seed(async_test_db, legacy)
        with _as_user(owner):
            resp = await _patch(
                async_test_client,
                project_id,
                {"evaluation_config": {"default_temperature": 0.3, "defaults_mode": "custom"}},
            )
        assert resp.status_code == 200, resp.text
        _, config, _ = await _stored(async_test_db, project_id)
        assert config == {**legacy, "default_temperature": 0.3, "defaults_mode": "custom"}


@pytest.mark.integration
class TestPatchRunsTheAfterSaveHook:
    @pytest.fixture
    def hook_calls(self, monkeypatch):
        """A stand-in for extended's hook: records the call and derives
        ``korrektur_enabled`` the way extended does (a korrektur metric in the
        saved evaluation_configs)."""
        calls = []

        def _hook(db, project, config):
            calls.append({"session": db, "config": dict(config)})
            project.korrektur_enabled = any(
                str(cfg.get("metric", "")).startswith("korrektur_")
                for cfg in config.get("evaluation_configs") or []
            )

        monkeypatch.setattr(extensions, "run_after_eval_config_save", _hook)
        return calls

    @pytest.mark.asyncio
    async def test_the_hook_sees_the_saved_document(
        self, async_test_client, async_test_db, hook_calls
    ):
        owner, project_id = await _seed(async_test_db, {"default_temperature": 0.2})
        configs = [{"id": "k", "metric": "korrektur_falloesung", "enabled": True}]
        with _as_user(owner):
            resp = await _patch(
                async_test_client, project_id, {"evaluation_config": {"evaluation_configs": configs}}
            )
        assert resp.status_code == 200, resp.text
        assert len(hook_calls) == 1
        # A sync session (the hook contract), and the merged document.
        assert isinstance(hook_calls[0]["session"], Session)
        assert hook_calls[0]["config"]["evaluation_configs"] == configs
        assert hook_calls[0]["config"]["default_temperature"] == 0.2
        _, _, korrektur_enabled = await _stored(async_test_db, project_id)
        assert korrektur_enabled is True

    @pytest.mark.asyncio
    async def test_an_explicit_korrektur_flag_in_the_same_body_wins(
        self, async_test_client, async_test_db, hook_calls
    ):
        owner, project_id = await _seed(async_test_db, {})
        configs = [{"id": "k", "metric": "korrektur_falloesung", "enabled": True}]
        with _as_user(owner):
            resp = await _patch(
                async_test_client,
                project_id,
                {"evaluation_config": {"evaluation_configs": configs}, "korrektur_enabled": False},
            )
        assert resp.status_code == 200, resp.text
        assert len(hook_calls) == 1
        _, _, korrektur_enabled = await _stored(async_test_db, project_id)
        assert korrektur_enabled is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "body",
        [{"title": "Neu"}, {"evaluation_config": None}],
        ids=["no-evaluation-config", "null-evaluation-config"],
    )
    async def test_no_evaluation_config_write_no_hook(
        self, async_test_client, async_test_db, hook_calls, body
    ):
        owner, project_id = await _seed(async_test_db, {"default_temperature": 0.2})
        with _as_user(owner):
            resp = await _patch(async_test_client, project_id, body)
        assert resp.status_code == 200, resp.text
        assert hook_calls == []
        _, config, _ = await _stored(async_test_db, project_id)
        assert config == {"default_temperature": 0.2}

    @pytest.mark.asyncio
    async def test_a_rejected_write_runs_no_hook(
        self, async_test_client, async_test_db, hook_calls
    ):
        owner, project_id = await _seed(async_test_db, {})
        with _as_user(owner):
            resp = await _patch(
                async_test_client, project_id, {"evaluation_config": {"runs_per_task": 0}}
            )
        assert resp.status_code == 422, resp.text
        assert hook_calls == []
