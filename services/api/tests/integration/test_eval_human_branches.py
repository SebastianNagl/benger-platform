"""Behavioral integration tests for the human-evaluation session router.

Target: ``services/api/routers/evaluations/human.py`` (mounted at prefix
``/api/evaluations`` via ``routers/evaluations/__init__.py``). The existing
``tests/unit/test_evaluation_human_endpoints.py`` only covers the in-process
logic snippets (config dicts, progress arithmetic) — it never drives an HTTP
round-trip or asserts persisted DB rows. This file fills the uncovered
endpoint branches end-to-end:

  POST   /human/session/start ....... 403 (non-editor), 404 (missing project),
                                      happy-path persist (likert + preference).
  GET    /human/next-item ........... 404 (unknown/foreign session), 400
                                      (session not active), the
                                      session-completes-when-no-tasks 404 +
                                      side-effect status flip, and the
                                      no-LLM-response 200 next item.
  POST   /human/likert .............. 404 (foreign/wrong-type session),
                                      multi-dimension persist + items_evaluated
                                      bump + comment-per-dimension mapping.
  POST   /human/preference .......... 404 (foreign/wrong-type session),
                                      persist + items_evaluated bump.
  GET    /human/session/{id}/progress 404, 403 (non-owner non-superadmin),
                                      percentage arithmetic (partial + zero
                                      total).
  GET    /human/sessions/{project_id} 403 (no project access), ordered list
                                      shape.
  GET    /human/config/{project_id} . 404, 403, the no-eval-config empty
                                      shape, the selected-methods extraction +
                                      likert-dimension lift, and the default
                                      dimensions fallback.
  DELETE /human/session/{id} ........ 404, 403 (non-owner non-superadmin),
                                      cascade delete of likert + preference
                                      rows.

Every test calls the endpoint via ``client`` and asserts the HTTP status +
response JSON; data-shaping tests also re-read the seeded rows from
``test_db`` to assert persisted state.

Access model recap (routers/projects/helpers):
  * ``test_users[0]`` = admin (superadmin) — always allowed / can edit.
  * ``test_users[1]`` = contributor, ``[2]`` = annotator, ``[3]`` = org_admin.
  * A private project is accessible only to its creator (or a superadmin);
    a non-private project linked to ``test_org`` is accessible to its
    members under the org-context header.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from models import (
    HumanEvaluationSession,
    LikertScaleEvaluation,
    PreferenceRanking,
)
from project_models import Project, ProjectOrganization, Task

BASE = "/api/evaluations"


# ---------------------------------------------------------------------------
# Seeding helpers
# ---------------------------------------------------------------------------


def _uid() -> str:
    return str(uuid.uuid4())


def _setup_project(db, admin, org, *, num_tasks=2, is_private=False, link_org=True,
                   evaluation_config=None):
    """Create a project owned by ``admin`` with ``num_tasks`` tasks.

    ``is_private=True`` + ``link_org=False`` builds the 403 fixture (a private
    project a non-creator non-superadmin cannot reach). ``link_org=True``
    attaches the project to ``org`` so org-context members pass the access
    check.
    """
    pid = _uid()
    p = Project(
        id=pid,
        title=f"Human Eval {pid[:6]}",
        created_by=admin.id,
        is_private=is_private,
        label_config=(
            '<View><Text name="text" value="$text"/>'
            '<Choices name="answer" toName="text">'
            '<Choice value="Ja"/><Choice value="Nein"/></Choices></View>'
        ),
        evaluation_config=evaluation_config,
    )
    db.add(p)
    db.flush()

    if link_org:
        db.add(ProjectOrganization(
            id=_uid(), project_id=pid,
            organization_id=org.id, assigned_by=admin.id,
        ))
        db.flush()

    tasks = []
    for i in range(num_tasks):
        t = Task(
            id=_uid(), project_id=pid,
            data={"text": f"Human task #{i}", "content": f"Content {i}"},
            inner_id=i + 1, created_by=admin.id,
        )
        db.add(t)
        tasks.append(t)
    db.flush()
    return p, tasks


def _make_session(db, project, evaluator_id, *, session_type="likert",
                  status="active", items_evaluated=0, total_items=2,
                  session_config=None):
    s = HumanEvaluationSession(
        id=_uid(),
        project_id=project.id,
        evaluator_id=evaluator_id,
        session_type=session_type,
        items_evaluated=items_evaluated,
        total_items=total_items,
        status=status,
        session_config=session_config or {"field_name": "answer"},
        created_at=datetime.now(timezone.utc),
    )
    db.add(s)
    db.flush()
    return s


def _h(auth_headers, org, role="admin"):
    return {**auth_headers[role], "X-Organization-Context": org.id}


# ===========================================================================
# POST /human/session/start
# ===========================================================================


@pytest.mark.integration
class TestStartSession:
    def test_non_editor_gets_403(self, client, test_db, test_users, auth_headers, test_org):
        """An annotator (only PROJECT_VIEW, not editor) cannot start a
        session — check_user_can_edit_project returns False → 403."""
        p, _ = _setup_project(test_db, test_users[0], test_org)
        test_db.commit()

        resp = client.post(
            f"{BASE}/human/session/start",
            json={"project_id": p.id, "session_type": "likert"},
            headers=_h(auth_headers, test_org, role="annotator"),
        )
        assert resp.status_code == 403, resp.text
        assert "only project editors" in resp.json()["detail"]

    def test_missing_project_404(self, client, test_db, test_users, auth_headers):
        """A superadmin passes the editor gate (check_user_can_edit_project is
        True for superadmin) but the project lookup misses → 404."""
        resp = client.post(
            f"{BASE}/human/session/start",
            json={"project_id": f"missing-{uuid.uuid4().hex}", "session_type": "likert"},
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404, resp.text
        assert "not found" in resp.json()["detail"]

    def test_likert_session_persists_with_dimensions(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """A likert session stamps the requested dimensions into session_config
        and sets total_items to the project's task count."""
        p, tasks = _setup_project(test_db, test_users[0], test_org, num_tasks=3)
        test_db.commit()

        resp = client.post(
            f"{BASE}/human/session/start",
            json={
                "project_id": p.id,
                "session_type": "likert",
                "field_name": "answer",
                "dimensions": ["correctness", "style"],
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["session_type"] == "likert"
        assert body["total_items"] == 3
        assert body["status"] == "active"
        assert body["session_config"]["dimensions"] == ["correctness", "style"]
        assert body["session_config"]["field_name"] == "answer"

        # DB state: a row landed with evaluator = admin, the dimensions stored.
        row = test_db.query(HumanEvaluationSession).filter_by(id=body["id"]).one()
        assert row.evaluator_id == test_users[0].id
        assert row.session_config["dimensions"] == ["correctness", "style"]
        assert row.total_items == 3

    def test_preference_session_nulls_dimensions(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """A preference session forces session_config.dimensions to None (the
        ``if session_type == 'likert'`` ternary's False arm)."""
        p, tasks = _setup_project(test_db, test_users[0], test_org, num_tasks=2)
        test_db.commit()

        resp = client.post(
            f"{BASE}/human/session/start",
            json={
                "project_id": p.id,
                "session_type": "preference",
                "dimensions": ["ignored"],
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["session_type"] == "preference"
        assert body["session_config"]["dimensions"] is None

        row = test_db.query(HumanEvaluationSession).filter_by(id=body["id"]).one()
        assert row.session_config["dimensions"] is None


# ===========================================================================
# GET /human/next-item
# ===========================================================================


@pytest.mark.integration
class TestNextItem:
    def test_foreign_session_404(self, client, test_db, test_users, auth_headers, test_org):
        """A session owned by another user is invisible (the query filters on
        evaluator_id == current_user.id) → 404."""
        p, _ = _setup_project(test_db, test_users[0], test_org)
        # Session owned by admin; the contributor asks for it.
        s = _make_session(test_db, p, test_users[0].id)
        test_db.commit()

        resp = client.get(
            f"{BASE}/human/next-item?session_id={s.id}",
            headers=_h(auth_headers, test_org, role="contributor"),
        )
        assert resp.status_code == 404, resp.text
        assert "not found or unauthorized" in resp.json()["detail"]

    def test_inactive_session_400(self, client, test_db, test_users, auth_headers, test_org):
        """A completed session is not active → the 400 branch."""
        p, _ = _setup_project(test_db, test_users[0], test_org)
        s = _make_session(test_db, p, test_users[0].id, status="completed")
        test_db.commit()

        resp = client.get(
            f"{BASE}/human/next-item?session_id={s.id}",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 400, resp.text
        assert "not active" in resp.json()["detail"]

    def test_no_more_tasks_completes_session_404(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """An active session on a project with zero tasks hits the
        ``not next_task`` branch: status flips to 'completed', completed_at is
        stamped, and a 404 'session completed' is raised."""
        p, _ = _setup_project(test_db, test_users[0], test_org, num_tasks=0)
        s = _make_session(test_db, p, test_users[0].id, total_items=0)
        test_db.commit()

        resp = client.get(
            f"{BASE}/human/next-item?session_id={s.id}",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404, resp.text
        assert "session completed" in resp.json()["detail"]

        # Side-effect: the session was flipped to completed + timestamped.
        test_db.expire_all()
        row = test_db.query(HumanEvaluationSession).filter_by(id=s.id).one()
        assert row.status == "completed"
        assert row.completed_at is not None

    def test_returns_next_task_without_llm_responses(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """With tasks present and no LLM generations, the next unevaluated task
        is returned with an empty responses list and item_number = evaluated+1."""
        p, tasks = _setup_project(test_db, test_users[0], test_org, num_tasks=2)
        s = _make_session(test_db, p, test_users[0].id, items_evaluated=0, total_items=2)
        test_db.commit()

        resp = client.get(
            f"{BASE}/human/next-item?session_id={s.id}",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["session_id"] == s.id
        assert body["item_number"] == 1
        assert body["total_items"] == 2
        assert body["responses"] == []
        assert body["task_id"] in {t.id for t in tasks}


# ===========================================================================
# POST /human/likert
# ===========================================================================


@pytest.mark.integration
class TestSubmitLikert:
    def test_wrong_type_session_404(self, client, test_db, test_users, auth_headers, test_org):
        """Submitting likert to a preference session misses the
        session_type=='likert' filter → 404."""
        p, tasks = _setup_project(test_db, test_users[0], test_org, num_tasks=1)
        s = _make_session(test_db, p, test_users[0].id, session_type="preference")
        test_db.commit()

        resp = client.post(
            f"{BASE}/human/likert",
            json={
                "session_id": s.id,
                "task_id": tasks[0].id,
                "response_id": "resp-1",
                "ratings": {"correctness": 4},
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404, resp.text
        assert "not found or unauthorized" in resp.json()["detail"]

    def test_persists_one_row_per_dimension_and_bumps_progress(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """Each rated dimension yields a LikertScaleEvaluation row; comments map
        per-dimension; the session's items_evaluated increments by one."""
        p, tasks = _setup_project(test_db, test_users[0], test_org, num_tasks=1)
        s = _make_session(test_db, p, test_users[0].id, items_evaluated=2)
        test_db.commit()

        resp = client.post(
            f"{BASE}/human/likert",
            json={
                "session_id": s.id,
                "task_id": tasks[0].id,
                "response_id": "resp-A",
                "ratings": {"correctness": 5, "style": 3},
                "comments": {"correctness": "spot on"},
                "time_spent_seconds": 42,
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # items_evaluated bumped from 2 to 3 (one item, not one per dimension).
        assert body["items_evaluated"] == 3

        # DB state: two rows (one per dimension); the comment only attaches to
        # the dimension that had one.
        rows = (
            test_db.query(LikertScaleEvaluation)
            .filter(LikertScaleEvaluation.session_id == s.id)
            .all()
        )
        assert len(rows) == 2
        by_dim = {r.dimension: r for r in rows}
        assert by_dim["correctness"].rating == 5
        assert by_dim["correctness"].comment == "spot on"
        assert by_dim["correctness"].time_spent_seconds == 42
        assert by_dim["style"].rating == 3
        assert by_dim["style"].comment is None

        test_db.expire_all()
        assert test_db.query(HumanEvaluationSession).filter_by(id=s.id).one().items_evaluated == 3


# ===========================================================================
# POST /human/preference
# ===========================================================================


@pytest.mark.integration
class TestSubmitPreference:
    def test_wrong_type_session_404(self, client, test_db, test_users, auth_headers, test_org):
        """Submitting preference to a likert session misses the
        session_type=='preference' filter → 404."""
        p, tasks = _setup_project(test_db, test_users[0], test_org, num_tasks=1)
        s = _make_session(test_db, p, test_users[0].id, session_type="likert")
        test_db.commit()

        resp = client.post(
            f"{BASE}/human/preference",
            json={
                "session_id": s.id,
                "task_id": tasks[0].id,
                "response_a_id": "a",
                "response_b_id": "b",
                "winner": "a",
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 404, resp.text

    def test_persists_ranking_and_bumps_progress(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """A preference submission writes one PreferenceRanking row carrying the
        winner/confidence/reasoning and bumps items_evaluated."""
        p, tasks = _setup_project(test_db, test_users[0], test_org, num_tasks=1)
        s = _make_session(test_db, p, test_users[0].id,
                          session_type="preference", items_evaluated=0)
        test_db.commit()

        resp = client.post(
            f"{BASE}/human/preference",
            json={
                "session_id": s.id,
                "task_id": tasks[0].id,
                "response_a_id": "resp-a",
                "response_b_id": "resp-b",
                "winner": "b",
                "confidence": 0.8,
                "reasoning": "B is more complete",
                "time_spent_seconds": 30,
            },
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["items_evaluated"] == 1

        rows = (
            test_db.query(PreferenceRanking)
            .filter(PreferenceRanking.session_id == s.id)
            .all()
        )
        assert len(rows) == 1
        r = rows[0]
        assert r.winner == "b"
        assert r.confidence == 0.8
        assert r.reasoning == "B is more complete"
        assert r.response_a_id == "resp-a"
        assert r.response_b_id == "resp-b"


# ===========================================================================
# GET /human/session/{session_id}/progress
# ===========================================================================


@pytest.mark.integration
class TestProgress:
    def test_missing_session_404(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            f"{BASE}/human/session/missing-{uuid.uuid4().hex}/progress",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404, resp.text
        assert "not found" in resp.json()["detail"]

    def test_non_owner_non_superadmin_403(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """A session owned by admin, requested by the contributor (not owner,
        not superadmin) → 403."""
        p, _ = _setup_project(test_db, test_users[0], test_org)
        s = _make_session(test_db, p, test_users[0].id)
        test_db.commit()

        resp = client.get(
            f"{BASE}/human/session/{s.id}/progress",
            headers=_h(auth_headers, test_org, role="contributor"),
        )
        assert resp.status_code == 403, resp.text
        assert "permission" in resp.json()["detail"]

    def test_partial_progress_percentage(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """items_evaluated=15 / total_items=30 → 50.0 percent."""
        p, _ = _setup_project(test_db, test_users[0], test_org)
        s = _make_session(test_db, p, test_users[0].id,
                          items_evaluated=15, total_items=30)
        test_db.commit()

        resp = client.get(
            f"{BASE}/human/session/{s.id}/progress",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["items_evaluated"] == 15
        assert body["total_items"] == 30
        assert body["progress_percentage"] == pytest.approx(50.0)
        assert body["session_id"] == s.id

    def test_zero_total_items_gives_zero_percentage(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """total_items=0 short-circuits the percentage to 0.0 (avoids div-by-0)."""
        p, _ = _setup_project(test_db, test_users[0], test_org)
        s = _make_session(test_db, p, test_users[0].id,
                          items_evaluated=0, total_items=0)
        test_db.commit()

        resp = client.get(
            f"{BASE}/human/session/{s.id}/progress",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["progress_percentage"] == pytest.approx(0.0)


# ===========================================================================
# GET /human/sessions/{project_id}
# ===========================================================================


@pytest.mark.integration
class TestListSessions:
    def test_no_project_access_403(self, client, test_db, test_users, auth_headers, test_org):
        """A private project the contributor cannot reach → 403."""
        p, _ = _setup_project(
            test_db, test_users[0], test_org, is_private=True, link_org=False,
        )
        test_db.commit()

        resp = client.get(
            f"{BASE}/human/sessions/{p.id}",
            headers=_h(auth_headers, test_org, role="contributor"),
        )
        assert resp.status_code == 403, resp.text
        assert "access" in resp.json()["detail"]

    def test_lists_sessions_newest_first(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """All sessions for the project come back ordered created_at DESC."""
        p, _ = _setup_project(test_db, test_users[0], test_org)
        s_old = _make_session(test_db, p, test_users[0].id, session_type="likert")
        s_old.created_at = datetime.now(timezone.utc).replace(microsecond=0)
        # Newer one by forcing a strictly larger created_at.
        s_new = _make_session(test_db, p, test_users[0].id, session_type="preference")
        from datetime import timedelta
        s_new.created_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        test_db.commit()

        resp = client.get(
            f"{BASE}/human/sessions/{p.id}",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        ids = [row["id"] for row in body]
        assert set(ids) == {s_old.id, s_new.id}
        # Newest first.
        assert ids[0] == s_new.id


# ===========================================================================
# GET /human/config/{project_id}
# ===========================================================================


@pytest.mark.integration
class TestHumanConfig:
    def test_missing_project_404(self, client, test_db, test_users, auth_headers):
        resp = client.get(
            f"{BASE}/human/config/missing-{uuid.uuid4().hex}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404, resp.text
        assert "not found" in resp.json()["detail"]

    def test_access_denied_403(self, client, test_db, test_users, auth_headers, test_org):
        p, _ = _setup_project(
            test_db, test_users[0], test_org, is_private=True, link_org=False,
        )
        test_db.commit()

        resp = client.get(
            f"{BASE}/human/config/{p.id}",
            headers=_h(auth_headers, test_org, role="annotator"),
        )
        assert resp.status_code == 403, resp.text
        assert "permission" in resp.json()["detail"]

    def test_no_eval_config_returns_empty_shape(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """A project with evaluation_config=None returns the empty-config
        envelope (no available_dimensions default kicks in here)."""
        p, _ = _setup_project(test_db, test_users[0], test_org, evaluation_config=None)
        test_db.commit()

        resp = client.get(
            f"{BASE}/human/config/{p.id}",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body == {
            "project_id": p.id,
            "human_methods": {},
            "available_dimensions": [],
        }

    def test_extracts_human_methods_and_likert_dimensions(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """selected_methods with human entries surface in human_methods; a
        likert_scale method carrying parameters.dimensions lifts those into
        available_dimensions."""
        cfg = {
            "selected_methods": {
                "answer": {
                    "automated": ["bleu"],
                    "human": [
                        {
                            "name": "likert_scale",
                            "parameters": {"dimensions": ["correctness", "completeness"]},
                        }
                    ],
                },
                # summary has no human entry → excluded from human_methods.
                "summary": {"automated": ["rouge"]},
            }
        }
        p, _ = _setup_project(test_db, test_users[0], test_org, evaluation_config=cfg)
        test_db.commit()

        resp = client.get(
            f"{BASE}/human/config/{p.id}",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "answer" in body["human_methods"]
        assert "summary" not in body["human_methods"]
        assert set(body["available_dimensions"]) == {"correctness", "completeness"}
        assert body["evaluation_config"] == cfg

    def test_default_dimensions_when_no_likert_params(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """A human method without likert dimensions falls back to the four
        canonical defaults."""
        cfg = {
            "selected_methods": {
                "answer": {"human": ["preference"]},
            }
        }
        p, _ = _setup_project(test_db, test_users[0], test_org, evaluation_config=cfg)
        test_db.commit()

        resp = client.get(
            f"{BASE}/human/config/{p.id}",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "answer" in body["human_methods"]
        assert set(body["available_dimensions"]) == {
            "correctness", "completeness", "style", "usability",
        }


# ===========================================================================
# DELETE /human/session/{session_id}
# ===========================================================================


@pytest.mark.integration
class TestDeleteSession:
    def test_missing_session_404(self, client, test_db, test_users, auth_headers):
        resp = client.delete(
            f"{BASE}/human/session/missing-{uuid.uuid4().hex}",
            headers=auth_headers["admin"],
        )
        assert resp.status_code == 404, resp.text
        assert "not found" in resp.json()["detail"]

    def test_non_owner_non_superadmin_403(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        p, _ = _setup_project(test_db, test_users[0], test_org)
        s = _make_session(test_db, p, test_users[0].id)
        test_db.commit()

        resp = client.delete(
            f"{BASE}/human/session/{s.id}",
            headers=_h(auth_headers, test_org, role="contributor"),
        )
        assert resp.status_code == 403, resp.text
        assert "permission" in resp.json()["detail"]

    def test_delete_cascades_likert_and_preference(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """Deleting a session also removes its child Likert + Preference rows,
        then the session itself."""
        p, tasks = _setup_project(test_db, test_users[0], test_org, num_tasks=1)
        s = _make_session(test_db, p, test_users[0].id)
        # Seed one likert and one preference row under the session.
        test_db.add(LikertScaleEvaluation(
            id=_uid(), session_id=s.id, task_id=tasks[0].id,
            response_id="r1", dimension="correctness", rating=4,
        ))
        test_db.add(PreferenceRanking(
            id=_uid(), session_id=s.id, task_id=tasks[0].id,
            response_a_id="a", response_b_id="b", winner="a",
        ))
        test_db.commit()

        # Sanity: children exist before delete.
        assert test_db.query(LikertScaleEvaluation).filter_by(session_id=s.id).count() == 1
        assert test_db.query(PreferenceRanking).filter_by(session_id=s.id).count() == 1

        resp = client.delete(
            f"{BASE}/human/session/{s.id}",
            headers=_h(auth_headers, test_org),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["session_id"] == s.id

        # DB state: everything gone.
        test_db.expire_all()
        assert test_db.query(HumanEvaluationSession).filter_by(id=s.id).first() is None
        assert test_db.query(LikertScaleEvaluation).filter_by(session_id=s.id).count() == 0
        assert test_db.query(PreferenceRanking).filter_by(session_id=s.id).count() == 0

    def test_owner_can_delete_own_session(
        self, client, test_db, test_users, auth_headers, test_org
    ):
        """A non-superadmin session owner can delete their own session (the
        ``evaluator_id == current_user.id`` arm of the permission check)."""
        p, _ = _setup_project(test_db, test_users[0], test_org)
        # Session owned by the contributor; the contributor deletes it.
        s = _make_session(test_db, p, test_users[1].id)
        test_db.commit()

        resp = client.delete(
            f"{BASE}/human/session/{s.id}",
            headers=_h(auth_headers, test_org, role="contributor"),
        )
        assert resp.status_code == 200, resp.text
        test_db.expire_all()
        assert test_db.query(HumanEvaluationSession).filter_by(id=s.id).first() is None
