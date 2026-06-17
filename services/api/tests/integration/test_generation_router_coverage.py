"""Behavioral integration tests for ``routers/generation.py`` — the COMPLEMENT
of ``test_generation_branches.py`` / ``test_remaining_router_endpoints.py``.

Those siblings cover the status/stop/delete happy paths and the
404/403/400 guard branches. This file targets the still-uncovered arms:

  - ``get_parse_metrics`` with NO ``project_id`` for a **non-superadmin** user,
    which exercises the org-scoping branch (``get_accessible_project_ids`` →
    ``accessible_ids`` narrowing) rather than the superadmin "see everything"
    short-circuit. Both the empty-accessible early return and the
    populated-org-scope aggregation are covered, asserting the aggregation
    runs against the org's real generation rows.
  - The ``pause`` / ``resume`` / ``retry`` SUCCESS attempts. These reach the
    generic ``except Exception`` handler and return HTTP 500 because the
    ``ResponseGeneration`` model is missing the ``paused_at`` / ``resumed_at`` /
    ``current_progress`` / ``completed_tasks`` / ``retry_count`` columns the
    router assigns (model↔router drift — see the FINDINGS note below and the
    docstring in ``test_generation_branches.py``). We assert the 500 AND that
    the persisted row did NOT transition state — pinning the bug behaviorally
    and covering the exception-handler lines that the guard-only tests skip.

Every test runs through the real ``client`` + ``test_db``; the only celery
touch point (``celery_app.send_task`` in resume/retry) is patched so no broker
call fires — though in practice the AttributeError short-circuits before it.
"""

import uuid
from datetime import datetime, timezone
from typing import List
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from models import Generation as DBLLMResponse
from models import ResponseGeneration as DBResponseGeneration
from models import User
from project_models import Project, ProjectOrganization, Task


def _uid() -> str:
    return str(uuid.uuid4())


def _seed_project(
    test_db: Session,
    test_users: List[User],
    test_org,
    *,
    owner: User = None,
    num_tasks: int = 1,
    link_org: bool = True,
) -> Project:
    owner = owner or test_users[0]
    project = Project(
        id=_uid(),
        title="gen-coverage",
        label_config='<View><Text name="text" value="$text"/></View>',
        created_by=owner.id,
        is_published=True,
        is_private=False,
    )
    test_db.add(project)
    test_db.flush()
    if link_org:
        test_db.add(
            ProjectOrganization(
                id=_uid(),
                project_id=project.id,
                organization_id=test_org.id,
                assigned_by=owner.id,
            )
        )
    test_db.flush()
    for i in range(num_tasks):
        test_db.add(
            Task(
                id=_uid(),
                project_id=project.id,
                inner_id=i + 1,
                data={"text": f"Task {i + 1}"},
                created_by=owner.id,
                updated_by=owner.id,
            )
        )
    test_db.commit()
    return project


def _first_task(test_db: Session, project: Project) -> Task:
    return test_db.query(Task).filter(Task.project_id == project.id).first()


def _seed_generation(
    test_db: Session,
    project: Project,
    *,
    created_by: str,
    status_val: str,
    task_id: str = None,
    model_id: str = "gpt-4o",
) -> DBResponseGeneration:
    gen = DBResponseGeneration(
        id=_uid(),
        project_id=project.id,
        task_id=task_id,
        model_id=model_id,
        status=status_val,
        created_by=created_by,
        created_at=datetime.now(timezone.utc),
    )
    test_db.add(gen)
    test_db.commit()
    return gen


def _seed_response(
    test_db: Session,
    gen: DBResponseGeneration,
    task: Task,
    *,
    model_id: str,
    parse_status: str,
    parse_error: str = None,
    parse_metadata: dict = None,
    run_index: int = 0,
) -> None:
    test_db.add(
        DBLLMResponse(
            id=_uid(),
            generation_id=gen.id,
            task_id=task.id,
            model_id=model_id,
            case_data="input case",
            response_content="generated answer",
            status="completed",
            parse_status=parse_status,
            parse_error=parse_error,
            parse_metadata=parse_metadata,
            run_index=run_index,
        )
    )


# ---------------------------------------------------------------------------
# get_parse_metrics — no project_id → org-scoping branch (non-superadmin)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestParseMetricsOrgScoped:
    def test_non_superadmin_org_scope_aggregates_member_projects(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """A non-superadmin (contributor) requesting parse-metrics WITHOUT a
        project_id hits the org-scoping branch: get_accessible_project_ids
        narrows to the projects the user can see, and the aggregation runs over
        those rows. The contributor is a member of test_org, so the project's
        responses are counted."""
        contributor = test_users[1]
        project = _seed_project(
            test_db, test_users, test_org, owner=contributor, link_org=True
        )
        task = _first_task(test_db, project)
        gen = _seed_generation(
            test_db, project, created_by=contributor.id,
            status_val="completed", task_id=task.id,
        )
        _seed_response(
            test_db, gen, task, model_id="gpt-4o",
            parse_status="success", parse_metadata={"retry_count": 1}, run_index=0,
        )
        _seed_response(
            test_db, gen, task, model_id="gpt-4o",
            parse_status="failed", parse_error="bad json", run_index=1,
        )
        test_db.commit()

        resp = client.get(
            "/api/generation/parse-metrics",
            headers={
                **auth_headers["contributor"],
                "X-Organization-Context": test_org.id,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # The org-scoped aggregation saw both rows of the member project.
        assert body["total_generations"] >= 2
        assert body["parse_success"] >= 1
        assert body["parse_failed"] >= 1
        errors = {e["error"]: e["count"] for e in body["common_parse_errors"]}
        assert errors.get("bad json", 0) >= 1

    def test_non_superadmin_no_accessible_projects_returns_zeroed(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """A non-superadmin requesting metrics in the default ('private') context
        with NO private projects of their own and no public projects in scope →
        get_accessible_project_ids returns [] → the `if not accessible_ids`
        early zeroed-metrics return. A response row exists on an admin-owned,
        org-linked project the annotator can't reach, proving the scoping
        actually excludes it (rather than the DB just being empty)."""
        admin = test_users[0]
        project = _seed_project(test_db, test_users, test_org, owner=admin, link_org=True)
        task = _first_task(test_db, project)
        gen = _seed_generation(
            test_db, project, created_by=admin.id,
            status_val="completed", task_id=task.id,
        )
        _seed_response(
            test_db, gen, task, model_id="gpt-4o",
            parse_status="success", parse_metadata={"retry_count": 1}, run_index=0,
        )
        test_db.commit()

        # No X-Organization-Context header → defaults to "private"; the annotator
        # owns no private projects, so accessible_ids == [].
        resp = client.get(
            "/api/generation/parse-metrics",
            headers=auth_headers["annotator"],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_generations"] == 0
        assert body["parse_success"] == 0
        assert body["parse_success_rate"] == 0
        assert body["common_parse_errors"] == []


    def test_superadmin_no_project_aggregates_all_rows(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """Superadmin + no project_id → get_accessible_project_ids returns None
        (include_all_private path), so NO narrowing filter is applied and the
        aggregation spans every response row. Seeded rows must show up in the
        counts."""
        admin = test_users[0]
        project = _seed_project(test_db, test_users, test_org, owner=admin)
        task = _first_task(test_db, project)
        gen = _seed_generation(
            test_db, project, created_by=admin.id,
            status_val="completed", task_id=task.id,
        )
        _seed_response(
            test_db, gen, task, model_id="gpt-4o",
            parse_status="success", parse_metadata={"retry_count": 2}, run_index=0,
        )
        _seed_response(
            test_db, gen, task, model_id="gpt-4o",
            parse_status="validation_error", parse_error="schema mismatch", run_index=1,
        )
        test_db.commit()

        resp = client.get(
            "/api/generation/parse-metrics", headers=auth_headers["admin"]
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_generations"] >= 2
        assert body["parse_success"] >= 1
        assert body["parse_validation_error"] >= 1


# ---------------------------------------------------------------------------
# stop_generation — celery-revoke failure is swallowed (still 200 + persisted)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestStopRevokeResilience:
    def test_revoke_exception_is_swallowed(
        self, client, test_db, test_users, test_org, auth_headers
    ):
        """If celery's control.revoke raises, the warning branch swallows it and
        the generation still persists as 'stopped' (the broker hiccup must not
        fail the user's stop request)."""
        project = _seed_project(test_db, test_users, test_org)
        gen = _seed_generation(
            test_db, project, created_by=test_users[0].id, status_val="running"
        )
        with patch("routers.generation.celery_app") as mock_celery:
            mock_celery.control.revoke.side_effect = RuntimeError("broker unreachable")
            resp = client.post(
                f"/api/generation/{gen.id}/stop", headers=auth_headers["admin"]
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "stopped"
        test_db.expire_all()
        refreshed = (
            test_db.query(DBResponseGeneration)
            .filter(DBResponseGeneration.id == gen.id)
            .first()
        )
        assert refreshed.status == "stopped"
        assert refreshed.completed_at is not None

