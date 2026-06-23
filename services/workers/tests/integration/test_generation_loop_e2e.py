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


def _make_child(db_conn, parent, run_index, task_id, model_id,
                status="completed"):
    """Seed one child Generation row for a parent's run_index (a trial that
    already produced a response)."""
    import uuid as _uuid

    child = Generation(
        id=str(_uuid.uuid4()),
        generation_id=parent.id,
        task_id=task_id,
        model_id=model_id,
        case_data="case",
        response_content="seeded response",
        run_index=run_index,
        status=status,
    )
    db_conn.add(child)
    db_conn.commit()
    return child


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

    # Re-run the SAME (generation_id, run_index=0) — the Celery redelivery
    # scenario the unique index `uq_generations_parent_run_index` guards. With
    # no label_config the first child is "parse_failed", so the run_index-aware
    # "skip existing response" guard (status=="completed") does NOT fire; the
    # loop regenerates and attempts a second INSERT with the same
    # (generation_id, run_index=0). The unique index rejects it — but the worker
    # now catches that IntegrityError as a graceful DUPLICATE skip (rolls back,
    # no session poisoning): the task returns "skipped", NO duplicate child is
    # created, and the original child is untouched.
    rerun = tasks.generate_llm_responses(
        generation_id=rg.id,
        config_data={"project_id": project.id, "rate_limit_delay": 0},
        model_id=model.id,
        user_id=user.id,
        run_index=0,
    )
    assert rerun["status"] == "skipped", (
        "duplicate-trial redelivery is handled idempotently (uq collision caught "
        "as a no-op skip, not a session-poisoning error)"
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


def test_generation_loop_multirun_derives_completed_from_children(
    db_conn, make_user, make_llm_model, make_project, make_task,
    patch_ai_service,
):
    """Keystone: parent runs_completed/status are DERIVED from the child rows
    (idempotent ``COUNT(DISTINCT run_index)``), never incremented. Dispatch all
    3 trials of a 3-run generation; the parent stays 'running' until the 3rd
    child lands, then reaches 'completed' with runs_completed==3 — and the
    derivation can't double-count under the fan-out."""
    user = make_user()
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id, label_config=None)
    task = make_task(project.id, {"text": "Frage"}, created_by=user.id)
    rg = _make_parent(db_conn, project.id, task.id, model.id, user.id,
                      runs_requested=3)
    db_conn.commit()

    for run_index in range(3):
        tasks.generate_llm_responses(
            generation_id=rg.id,
            config_data={"project_id": project.id, "rate_limit_delay": 0},
            model_id=model.id,
            user_id=user.id,
            run_index=run_index,
        )
        db_conn.expire(rg)
        if run_index < 2:
            assert rg.status == "running", f"still running after trial {run_index}"
            assert rg.runs_completed == run_index + 1
        else:
            assert rg.status == "completed", "completed only after the last trial"
            assert rg.runs_completed == 3

    children = (
        db_conn.query(Generation)
        .filter(Generation.generation_id == rg.id)
        .all()
    )
    assert len(children) == 3
    assert {c.run_index for c in children} == {0, 1, 2}


def test_generation_loop_failed_trial_latches_even_if_not_last(
    db_conn, make_user, make_llm_model, make_project, make_task, monkeypatch,
):
    """First-failure latch (the keystone regression): in a 3-run generation one
    trial fails (writes NO child, sets status='failed') and a SIBLING success
    finalizes AFTER it. The later success must NOT un-fail the parent — a failed
    trial's run_index never gets a child, so COUNT(DISTINCT run_index) can never
    reach runs_requested and a flip back to 'running' would strand the parent
    forever (retry needs failed/stopped, resume needs paused).

    Then a retry-style re-run of the missing trial (status reset to 'running',
    as the API retry endpoint does) drives it to 'completed' — proving the latch
    never blocks a deliberate retry.
    """
    from conftest import FakeAIService

    user = make_user()
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id, label_config=None)
    task = make_task(project.id, {"text": "Frage"}, created_by=user.id)
    rg = _make_parent(db_conn, project.id, task.id, model.id, user.id,
                      runs_requested=3)
    db_conn.commit()

    # Fail ONLY the first generate call (we drive run_index 1 first), succeed
    # after. on_generate runs after the calls counter increments, so call_n==1
    # is the very first generate.
    def _fail_first(call_n):
        if call_n == 1:
            raise RuntimeError("simulated LLM failure for trial 1")

    fake = FakeAIService(on_generate=_fail_first)
    monkeypatch.setattr(
        tasks.user_aware_ai_service,
        "get_ai_service_for_user",
        lambda db, user_id, provider, organization_id=None: fake,
    )

    # Trial 1 fails first → status latches 'failed', no child written.
    res1 = tasks.generate_llm_responses(
        generation_id=rg.id,
        config_data={"project_id": project.id, "rate_limit_delay": 0},
        model_id=model.id, user_id=user.id, run_index=1,
    )
    assert res1["status"] == "failed"
    db_conn.expire(rg)
    assert rg.status == "failed"

    # Trials 0 then 2 succeed AFTER the failure. Each finalizes while the parent
    # is already 'failed'; neither may overwrite it back to 'running'.
    for run_index in (0, 2):
        tasks.generate_llm_responses(
            generation_id=rg.id,
            config_data={"project_id": project.id, "rate_limit_delay": 0},
            model_id=model.id, user_id=user.id, run_index=run_index,
        )
        db_conn.expire(rg)
        assert rg.status == "failed", (
            f"a later success (run {run_index}) must NOT un-fail the parent"
        )

    # Two children landed (runs 0 & 2); run 1 never wrote one.
    children = (
        db_conn.query(Generation).filter(Generation.generation_id == rg.id).all()
    )
    assert {c.run_index for c in children} == {0, 2}
    assert rg.runs_completed == 2

    # Retry the missing trial: the API retry endpoint resets status to 'running'
    # before re-dispatch, which clears the latch. Re-run run_index 1 (the fake
    # now succeeds — call_n > 1) and the parent reaches 'completed'.
    rg.status = "running"
    db_conn.commit()
    res_retry = tasks.generate_llm_responses(
        generation_id=rg.id,
        config_data={"project_id": project.id, "rate_limit_delay": 0},
        model_id=model.id, user_id=user.id, run_index=1,
    )
    assert res_retry["status"] == "success"
    db_conn.expire(rg)
    assert rg.status == "completed"
    assert rg.runs_completed == 3
    children = (
        db_conn.query(Generation).filter(Generation.generation_id == rg.id).all()
    )
    assert {c.run_index for c in children} == {0, 1, 2}


def test_generation_loop_completion_wins_over_stale_failed_latch(
    db_conn, make_user, make_llm_model, make_project, make_task, patch_ai_service,
):
    """Completion must win over a stale 'failed' latch. A multi-run gen can be
    latched 'failed' (a trial failed) while its last missing run_index later
    LANDS — e.g. a prior-epoch survivor finishes after the latch, or a retry
    refilled it. Once every run_index has a child, COUNT(DISTINCT run_index)
    reaches runs_requested and the gen IS complete; the finalizer must derive
    'completed' rather than preserve the now-stale 'failed' (which would be an
    inconsistent terminal state with all children present). This guards the
    recompute branch order (completion checked BEFORE the failed-latch)."""
    user = make_user()
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id, label_config=None)
    task = make_task(project.id, {"text": "Frage"}, created_by=user.id)
    rg = _make_parent(db_conn, project.id, task.id, model.id, user.id,
                      runs_requested=3)
    # Two trials already produced children; the parent is latched 'failed' (a
    # third trial failed earlier without a row). The missing run_index is 2.
    _make_child(db_conn, rg, run_index=0, task_id=task.id, model_id=model.id)
    _make_child(db_conn, rg, run_index=1, task_id=task.id, model_id=model.id)
    rg.status = "failed"
    rg.runs_completed = 2
    rg.runs_failed = 1
    db_conn.commit()

    # The last missing trial lands. The start-of-trial guard leaves status
    # 'failed' (not pending/running), the trial writes child run_index=2, and the
    # recompute now sees _completed==3>=runs_requested → completion wins.
    result = tasks.generate_llm_responses(
        generation_id=rg.id,
        config_data={"project_id": project.id, "rate_limit_delay": 0},
        model_id=model.id, user_id=user.id, run_index=2,
    )
    assert result["status"] == "success"

    db_conn.expire(rg)
    assert rg.status == "completed", "completion must win over the stale failed latch"
    assert rg.runs_completed == 3
    assert rg.runs_failed == 0
    children = (
        db_conn.query(Generation).filter(Generation.generation_id == rg.id).all()
    )
    assert {c.run_index for c in children} == {0, 1, 2}


def test_generation_loop_post_loop_failure_preserves_user_terminal_status(
    db_conn, make_user, make_llm_model, make_project, make_task, monkeypatch,
):
    """The inner exception handler must NOT clobber a user-terminal status. If an
    exception fires OUTSIDE the per-prompt try (here: resolving the AI service,
    line ~396 — before the loop) AFTER a concurrent stop flipped the parent to
    'stopped', the handler must preserve 'stopped', not overwrite it with
    'failed'. (A SIGTERM from the stop-revoke surfacing in the post-loop region
    is the real-world trigger.)"""
    user = make_user()
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id, label_config=None)
    task = make_task(project.id, {"text": "Frage"}, created_by=user.id)
    # Parent is 'running' so the worker passes the up-front skip check and reaches
    # the AI-service resolution.
    rg = _make_parent(db_conn, project.id, task.id, model.id, user.id)
    rg.status = "running"
    db_conn.commit()

    def _flip_to_stopped_then_raise(db, user_id, provider, organization_id=None):
        # Simulate a concurrent stop landing while this trial is in flight, then
        # a failure (e.g. SIGTERM) surfacing outside the per-prompt try.
        sess = tasks.SessionLocal()
        try:
            row = (
                sess.query(ResponseGeneration)
                .filter(ResponseGeneration.id == rg.id)
                .first()
            )
            row.status = "stopped"
            sess.commit()
        finally:
            sess.close()
        raise RuntimeError("simulated post-stop failure resolving AI service")

    monkeypatch.setattr(
        tasks.user_aware_ai_service,
        "get_ai_service_for_user",
        _flip_to_stopped_then_raise,
    )

    result = tasks.generate_llm_responses(
        generation_id=rg.id,
        config_data={"project_id": project.id, "rate_limit_delay": 0},
        model_id=model.id, user_id=user.id, run_index=0,
    )
    # The trial errored (the umbrella reports error), but the parent's
    # user-terminal 'stopped' must survive — NOT be clobbered to 'failed'.
    assert result["status"] == "error"
    db_conn.expire(rg)
    assert rg.status == "stopped", (
        "inner exception handler must not clobber a user-terminal status"
    )


def test_generation_loop_completion_notification_only_on_terminal_complete(
    db_conn, make_user, make_llm_model, make_project, make_task,
    patch_ai_service, monkeypatch,
):
    """The 'Generation Complete' notification fires EXACTLY ONCE — from the trial
    that drives the parent to terminal 'completed'. In a multi-run fan-out each
    trial runs this function, so without the _final_status gate the N-1
    still-'running' trials would each fire a premature completion notification."""
    notes = []
    monkeypatch.setattr(
        tasks.NotificationService,
        "create_notification",
        lambda *a, **k: notes.append(k) or [],
    )
    user = make_user()
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id, label_config=None)
    task = make_task(project.id, {"text": "Frage"}, created_by=user.id)
    rg = _make_parent(db_conn, project.id, task.id, model.id, user.id,
                      runs_requested=3)
    db_conn.commit()

    cfg = {"project_id": project.id, "rate_limit_delay": 0}
    # Trials 0 and 1 leave the parent 'running' → NO completion notification.
    for run_index in (0, 1):
        tasks.generate_llm_responses(generation_id=rg.id, config_data=cfg,
                                     model_id=model.id, user_id=user.id,
                                     run_index=run_index)
    assert notes == [], "no completion notification while the parent is still running"

    # Trial 2 drives the parent to 'completed' → exactly one notification.
    tasks.generate_llm_responses(generation_id=rg.id, config_data=cfg,
                                 model_id=model.id, user_id=user.id, run_index=2)
    db_conn.expire(rg)
    assert rg.status == "completed"
    assert len(notes) == 1, "exactly one completion notification, from the finishing trial"


def test_generation_loop_failed_trial_sends_no_completion_notification(
    db_conn, make_user, make_llm_model, make_project, make_task, monkeypatch,
):
    """A failed trial (responses_generated==0, status='failed') must NOT send a
    'Generation Complete' notification — it would falsely read '0/1 responses'."""
    from conftest import FakeAIService

    notes = []
    monkeypatch.setattr(
        tasks.NotificationService,
        "create_notification",
        lambda *a, **k: notes.append(k) or [],
    )
    user = make_user()
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id, label_config=None)
    task = make_task(project.id, {"text": "Frage"}, created_by=user.id)
    rg = _make_parent(db_conn, project.id, task.id, model.id, user.id)
    db_conn.commit()

    def _always_fail(call_n):
        raise RuntimeError("simulated LLM failure")

    fake = FakeAIService(on_generate=_always_fail)
    monkeypatch.setattr(
        tasks.user_aware_ai_service, "get_ai_service_for_user",
        lambda db, user_id, provider, organization_id=None: fake,
    )

    result = tasks.generate_llm_responses(
        generation_id=rg.id,
        config_data={"project_id": project.id, "rate_limit_delay": 0},
        model_id=model.id, user_id=user.id, run_index=0,
    )
    assert result["status"] == "failed"
    db_conn.expire(rg)
    assert rg.status == "failed"
    assert notes == [], "a failed generation must not send a completion notification"


def test_generation_loop_structured_output_parses_via_response_parser(
    db_conn, make_user, make_llm_model, make_project, make_task, monkeypatch,
):
    """Regression for the dropped ``from response_parser import ResponseParser``
    in tasks.py: the generation service parses structured output via
    ``tasks.ResponseParser(...)``. When that import was lost in the tasks.py
    decomposition, ``tasks.ResponseParser`` AttributeError'd and EVERY
    structured-output response was stored unparsed (parse_status='failed',
    parse_error "module 'tasks' has no attribute 'ResponseParser'"). This drives
    the real parser end-to-end: a project WITH a label_config + a parseable
    response must yield parse_status='success'."""
    from conftest import FakeAIService

    # Cheapest direct guard of the binding itself.
    assert hasattr(tasks, "ResponseParser"), (
        "tasks.ResponseParser must be bound at module scope so the generation "
        "service can parse structured output"
    )

    choices_config = (
        '<View><Text name="text" value="$text"/>'
        '<Choices name="sentiment" toName="text">'
        '<Choice value="positive"/><Choice value="negative"/>'
        '<Choice value="neutral"/></Choices></View>'
    )
    user = make_user()
    model = make_llm_model(provider="OpenAI")
    project = make_project(created_by=user.id, label_config=choices_config)
    task = make_task(project.id, {"text": "Ein toller Tag."}, created_by=user.id)
    rg = _make_parent(db_conn, project.id, task.id, model.id, user.id)
    db_conn.commit()

    # The fake LLM returns a response the parser accepts for the choices schema.
    fake = FakeAIService(response_text='{"sentiment": "positive"}')
    monkeypatch.setattr(
        tasks.user_aware_ai_service, "get_ai_service_for_user",
        lambda db, user_id, provider, organization_id=None: fake,
    )

    result = tasks.generate_llm_responses(
        generation_id=rg.id,
        config_data={"project_id": project.id, "rate_limit_delay": 0},
        model_id=model.id, user_id=user.id, run_index=0,
    )
    assert result["status"] == "success"

    child = (
        db_conn.query(Generation).filter(Generation.generation_id == rg.id).first()
    )
    assert child is not None
    assert child.parse_status == "success", (
        "structured output must parse via tasks.ResponseParser; got "
        f"parse_status={child.parse_status!r}, parse_error={child.parse_error!r}"
    )


# ---------------------------------------------------------------------------
# Test 6 — cooperative mid-loop cancel (issue #198, implemented)
# ---------------------------------------------------------------------------


def test_generation_loop_cooperative_cancel_midrun(
    db_conn, make_user, make_llm_model, make_project, make_task,
    monkeypatch,
):
    """Issue #198 (implemented): the AI service flips the parent to 'cancelled'
    DURING the generation call (after the loop's up-front status check). The
    cooperative loop re-reads the status with a raw scalar AFTER the AI call
    returns and skips persisting the now-cancelled response — so `children == 0`
    (we can't un-spend the call, but we don't write it and we stop). The
    post-loop guard then preserves the 'cancelled' status.
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

    result = tasks.generate_llm_responses(
        generation_id=rg.id,
        config_data={"project_id": project.id, "rate_limit_delay": 0},
        model_id=model.id,
        user_id=user.id,
        run_index=0,
    )

    # The umbrella reports the cancel (not "failed"/"success") so no spurious
    # "Generation Complete" notification fires.
    assert result["status"] == "cancelled"

    # The cooperative loop observed the mid-call cancel (post-call status
    # re-read) and skipped the write → no child Generation row persisted.
    children = (
        db_conn.query(Generation)
        .filter(Generation.generation_id == rg.id)
        .count()
    )
    assert children == 0, "cooperative mid-call cancel should have skipped the write"

    # And the cancel is preserved — not relabeled by the trial counters.
    db_conn.expire_all()
    refreshed = (
        db_conn.query(ResponseGeneration)
        .filter(ResponseGeneration.id == rg.id)
        .first()
    )
    assert refreshed.status == "cancelled"
