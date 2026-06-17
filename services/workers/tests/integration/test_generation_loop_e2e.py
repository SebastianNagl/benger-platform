"""End-to-end behavioral tests for the LLM generation loop.

Drives the REAL `generate_llm_responses` task body synchronously against
the real test Postgres, with a deterministic FakeAIService (no network).

The loop iterates task × instruction_prompt (one default instruction
prompt), calls the AI service, parses (skipped when no label_config), and
writes one child Generation row per response, bumping the parent
ResponseGeneration's runs_completed/runs_failed counters and deriving its
final status.
"""

import pytest

import tasks
from models import Generation, ResponseGeneration

pytestmark = [pytest.mark.integration, pytest.mark.database]


def _make_parent(db_conn, project_id, task_id, model_id, created_by,
                 runs_requested=1):
    import uuid as _uuid

    rg = ResponseGeneration(
        id=str(_uuid.uuid4()),
        project_id=project_id,
        task_id=task_id,
        model_id=model_id,
        status="pending",
        runs_requested=runs_requested,
        created_by=created_by,
    )
    db_conn.add(rg)
    db_conn.commit()
    return rg


# ---------------------------------------------------------------------------
# Test 5 — generation loop happy path + run_index uniqueness
# ---------------------------------------------------------------------------


def test_generation_loop_happy_path_and_unique_run_index(
    db_conn, make_user, make_llm_model, make_project, make_task,
    patch_ai_service,
):
    user = make_user()
    model = make_llm_model(provider="OpenAI")
    # No label_config → parsing is skipped (parse_status="pending",
    # final child status "completed"); standard (non-structured) generate
    # path with the fake service.
    project = make_project(created_by=user.id, label_config=None)
    task = make_task(project.id, {"text": "Ist der Vertrag gültig?"},
                     created_by=user.id)

    rg = _make_parent(db_conn, project.id, task.id, model.id, user.id,
                      runs_requested=1)
    db_conn.commit()  # release savepoint so the task's session sees the row

    result = tasks.generate_llm_responses(
        generation_id=rg.id,
        config_data={"project_id": project.id, "rate_limit_delay": 0},
        model_id=model.id,
        user_id=user.id,
        run_index=0,
    )

    assert result["status"] == "success"
    assert result["responses_generated"] == 1
    assert result["total_expected"] == 1
    assert patch_ai_service.calls == 1

    # Exactly one child Generation row.
    children = (
        db_conn.query(Generation)
        .filter(Generation.generation_id == rg.id)
        .all()
    )
    assert len(children) == 1
    child = children[0]
    assert child.run_index == 0
    assert child.task_id == task.id
    assert child.response_content  # non-empty

    child_id = child.id

    # Parent transitioned to completed (runs_completed >= runs_requested).
    db_conn.expire(rg)
    assert rg.status == "completed"
    assert rg.runs_completed == 1

    # Re-run the SAME (generation_id, run_index=0). This is the Celery
    # redelivery scenario the unique index `uq_generations_parent_run_index`
    # exists to guard. With no label_config, parsing is skipped → the first
    # child's status is "parse_failed", so the loop's "skip existing
    # response" guard (which only matches status=="completed") does NOT fire;
    # the loop regenerates and attempts a second INSERT with the same
    # (generation_id, run_index=0). The unique index rejects it; the
    # UniqueViolation poisons the loop's session so the task returns "error".
    # Crucially: NO duplicate child row is created (the index is the real
    # idempotency backstop) and the original child is untouched.
    rerun = tasks.generate_llm_responses(
        generation_id=rg.id,
        config_data={"project_id": project.id, "rate_limit_delay": 0},
        model_id=model.id,
        user_id=user.id,
        run_index=0,
    )
    assert rerun["status"] == "error", (
        "duplicate-trial redelivery surfaces as error after the unique-index "
        "violation poisons the session"
    )

    children_after = (
        db_conn.query(Generation)
        .filter(Generation.generation_id == rg.id)
        .all()
    )
    assert len(children_after) == 1, (
        "uq_generations_parent_run_index must block a duplicate "
        "(generation_id, run_index=0) child"
    )
    assert children_after[0].id == child_id, "original child row preserved"


# ---------------------------------------------------------------------------
# Test 6 (xfail) — cooperative mid-loop cancel is not implemented (issue #198)
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason="cooperative mid-loop cancel not implemented — issue #198",
    strict=False,
)
def test_generation_loop_cooperative_cancel_midrun(
    db_conn, make_user, make_llm_model, make_project, make_task,
    monkeypatch,
):
    """Forward-reference test: the AI service flips the parent to 'cancelled'
    during the generation call (after the loop's single up-front status
    check). A COOPERATIVE loop would re-read the status after the AI call
    returns and skip persisting the now-cancelled response.

    Today `generate_llm_responses` checks `generation.status == "cancelled"`
    exactly ONCE, before any work, and never re-reads it after the AI call —
    so the response is written regardless and `children == 1`. The assertion
    below expects 0, so it xfails now; it flips to xpass when #198 lands a
    cooperative post-call cancel re-check.
    """
    from conftest import FakeAIService

    user = make_user()
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id, label_config=None)
    task = make_task(project.id, {"text": "Frage"}, created_by=user.id)

    rg = _make_parent(db_conn, project.id, task.id, model.id, user.id)
    db_conn.commit()

    # Flip the parent to cancelled DURING the AI call — i.e. after the loop's
    # one up-front status check, before it persists the response — via a
    # separate committed session a cooperative re-read would observe.
    def _on_generate(call_n):
        sess = tasks.SessionLocal()
        try:
            row = (
                sess.query(ResponseGeneration)
                .filter(ResponseGeneration.id == rg.id)
                .first()
            )
            if row:
                row.status = "cancelled"
                sess.commit()
        finally:
            sess.close()

    fake = FakeAIService(on_generate=_on_generate)
    monkeypatch.setattr(
        tasks.user_aware_ai_service,
        "get_ai_service_for_user",
        lambda db, user_id, provider, organization_id=None: fake,
    )

    tasks.generate_llm_responses(
        generation_id=rg.id,
        config_data={"project_id": project.id, "rate_limit_delay": 0},
        model_id=model.id,
        user_id=user.id,
        run_index=0,
    )

    # A cooperative loop would have observed the mid-call cancel and skipped
    # the write. Today it writes the row regardless → children == 1 → this
    # assertion fails → xfail (flips to xpass once #198 lands).
    children = (
        db_conn.query(Generation)
        .filter(Generation.generation_id == rg.id)
        .count()
    )
    assert children == 0, "cooperative mid-call cancel should have skipped the write"
