"""The batch billing extension hook of ``run_evaluation`` (core 2.20).

``tasks._apply_batch_evaluation_policy`` resolves the optional
``benger_extended.workers.get_batch_evaluation_policy_fn`` and returns
``(organization_id, billing_block, org_billing_authorized)``;
``tasks._apply_batch_billing`` fails a refused run before any judge work, and
every evaluation cell re-derives the authorization
(``tasks._batch_cell_billing_authorized``). The extended package is faked through
``sys.modules`` (the platform test image has none). The chord-level
behaviour runs against Postgres in
``tests/integration/test_billing_hooks_e2e.py``.
"""

import contextlib
import os
import sys
import types

import pytest

workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workers_root not in sys.path:
    sys.path.insert(0, workers_root)

import tasks as tasks_module  # noqa: E402


@pytest.fixture
def extended(monkeypatch):
    """Install a fake ``benger_extended.workers``.

    Only these two ``sys.modules`` keys are swapped; ``patch.dict`` over all
    of ``sys.modules`` would also drop modules imported meanwhile.
    """

    def _install(policy_fn=None, *, with_hook=True, missing=False):
        if missing:
            monkeypatch.setitem(sys.modules, "benger_extended", None)
            monkeypatch.setitem(sys.modules, "benger_extended.workers", None)
            return
        pkg = types.ModuleType("benger_extended")
        workers = types.ModuleType("benger_extended.workers")
        if with_hook:
            workers.get_batch_evaluation_policy_fn = lambda: policy_fn
        pkg.workers = workers
        monkeypatch.setitem(sys.modules, "benger_extended", pkg)
        monkeypatch.setitem(sys.modules, "benger_extended.workers", workers)

    return _install


class _DB:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0
        self.savepoints = []

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    @contextlib.contextmanager
    def begin_nested(self):
        record = {"outcome": None}
        self.savepoints.append(record)
        try:
            yield
        except BaseException:
            record["outcome"] = "rolled_back"
            raise
        record["outcome"] = "released"


def _policy(db, **kwargs):
    return tasks_module._apply_batch_evaluation_policy(
        db,
        project=types.SimpleNamespace(id="p1"),
        user_id=kwargs.pop("user_id", "u1"),
        organization_id="org-dispatched",
        configs=[{"metric": "llm_judge_custom"}],
        evaluation_id="eval-1",
    )


class TestBatchPolicyLookup:
    def test_community_edition_keeps_the_dispatched_org(self, extended):
        extended(missing=True)
        assert _policy(_DB()) == ("org-dispatched", None, False)

    def test_package_without_the_hook(self, extended):
        extended(with_hook=False)
        assert _policy(_DB()) == ("org-dispatched", None, False)

    def test_hook_without_a_policy(self, extended):
        extended(policy_fn=None)
        assert _policy(_DB()) == ("org-dispatched", None, False)

    def test_policy_receives_the_run_context_and_may_move_the_org(self, extended):
        seen = {}

        def policy(db, **kwargs):
            seen.update(kwargs)
            return "org-lms", None

        extended(policy)
        assert _policy(_DB()) == ("org-lms", None, False)
        assert seen["project"].id == "p1"
        assert seen["user_id"] == "u1"
        assert seen["organization_id"] == "org-dispatched"
        assert seen["configs"] == [{"metric": "llm_judge_custom"}]

    def test_no_starter_means_no_policy(self, extended):
        def policy(db, **kwargs):
            raise AssertionError("must not be called without a user")

        extended(policy)
        assert _policy(_DB(), user_id=None) == ("org-dispatched", None, False)

    def test_reason_string_is_normalized(self, extended):
        extended(lambda db, **k: (None, "org_not_paying"))
        assert _policy(_DB()) == (None, {"reason": "org_not_paying"}, False)

    def test_empty_block_means_allowed(self, extended):
        extended(lambda db, **k: ("org-x", {}))
        assert _policy(_DB()) == ("org-x", None, False)

    def test_three_tuple_carries_the_authorization(self, extended):
        extended(lambda db, **k: ("org-x", None, True))
        assert _policy(_DB()) == ("org-x", None, True)

    def test_a_refused_run_is_never_authorized(self, extended):
        extended(lambda db, **k: ("org-x", {"reason": "org_key_missing"}, True))
        assert _policy(_DB()) == ("org-x", {"reason": "org_key_missing"}, False)

    @pytest.mark.parametrize(
        "result",
        [RuntimeError("extension bug"), ("org-x",), "org-x", ("a", None, True, 1)],
    )
    def test_crash_or_bad_shape_keeps_the_dispatched_org_and_rolls_back(
        self, extended, result
    ):
        def policy(db, **kwargs):
            if isinstance(result, Exception):
                raise result
            return result

        extended(policy)
        db = _DB()
        assert _policy(db) == ("org-dispatched", None, False)
        assert db.rollbacks == 1


class TestApplyBatchBilling:
    def _evaluation(self, meta=None):
        return types.SimpleNamespace(
            id="eval-1",
            status="running",
            error_message=None,
            completed_at=None,
            eval_metadata=meta,
        )

    def test_refused_run_is_failed_with_the_reason(self, extended, monkeypatch):
        import sqlalchemy.orm.attributes as orm_attributes

        block = {
            "code": "lti_org_unfunded",
            "reason": "org_key_missing",
            "org_id": "org-lms",
            "missing_providers": ["openai"],
        }
        flagged = []
        monkeypatch.setattr(
            orm_attributes, "flag_modified", lambda obj, key: flagged.append(key)
        )
        extended(lambda d, **k: ("org-lms", block))
        db = _DB()
        evaluation = self._evaluation({"triggered_by": "u1", "evaluation_type": "batch"})
        org, got, authorized = tasks_module._apply_batch_billing(
            db,
            evaluation=evaluation,
            project=types.SimpleNamespace(id="p1"),
            organization_id="org-dispatched",
            configs=[],
        )
        assert (org, got, authorized) == ("org-dispatched", block, False)
        assert evaluation.status == "failed"
        assert evaluation.error_message == "billing_blocked:org_key_missing"
        assert evaluation.completed_at is not None
        meta = evaluation.eval_metadata
        assert meta["evaluation_type"] == "batch"
        assert meta["error"] == "billing_blocked:org_key_missing"
        assert {k: meta["billing_block"][k] for k in block} == block
        assert meta["billing_block"]["checked_at"]
        assert flagged == ["eval_metadata"]
        assert db.commits == 1
        # The policy may have aborted the transaction: roll back before the
        # failure is written (the caller committed 'running' already).
        assert db.rollbacks == 1

    def test_block_after_a_failed_query_is_still_recorded(self, extended, monkeypatch):
        """A failed query inside the policy aborts the transaction; the
        fail-closed block must still be written, not lost on the commit."""
        import sqlalchemy.orm.attributes as orm_attributes

        monkeypatch.setattr(orm_attributes, "flag_modified", lambda obj, key: None)

        class _AbortedDB(_DB):
            aborted = False

            def commit(self):
                if self.aborted:
                    raise RuntimeError("current transaction is aborted")
                super().commit()

            def rollback(self):
                self.aborted = False
                super().rollback()

        db = _AbortedDB()

        def policy(d, **kwargs):
            d.aborted = True  # the policy's own query failed
            return "org-lms", {"reason": "billing_check_failed"}

        extended(policy)
        evaluation = self._evaluation({"triggered_by": "u1"})
        org, got, authorized = tasks_module._apply_batch_billing(
            db,
            evaluation=evaluation,
            project=types.SimpleNamespace(id="p1"),
            organization_id="org-dispatched",
            configs=[],
        )
        assert got == {"reason": "billing_check_failed"}
        assert evaluation.status == "failed"
        assert evaluation.error_message == "billing_blocked:billing_check_failed"
        assert evaluation.eval_metadata["billing_block"]["reason"] == (
            "billing_check_failed"
        )
        assert db.commits == 1

    def test_allowed_run_is_untouched(self, extended):
        extended(lambda d, **k: ("org-lms", None, True))
        db = _DB()
        evaluation = self._evaluation({"triggered_by": "u1"})
        org, got, authorized = tasks_module._apply_batch_billing(
            db,
            evaluation=evaluation,
            project=types.SimpleNamespace(id="p1"),
            organization_id=None,
            configs=[],
        )
        assert (org, got, authorized) == ("org-lms", None, True)
        assert evaluation.status == "running"
        assert db.commits == 0

    def test_run_without_metadata_has_no_starter(self, extended):
        def policy(db, **kwargs):
            raise AssertionError("must not be called without a starter")

        extended(policy)
        db = _DB()
        org, got, authorized = tasks_module._apply_batch_billing(
            db,
            evaluation=self._evaluation(None),
            project=types.SimpleNamespace(id="p1"),
            organization_id="org-dispatched",
            configs=[],
        )
        assert (org, got, authorized) == ("org-dispatched", None, False)


class _ProjectDB(_DB):
    """Answers the cell's project lookup with ``project`` (or raises)."""

    def __init__(self, project=None, error=None):
        super().__init__()
        self.project = project
        self.error = error
        self.lookups = 0

    def query(self, model):
        self.lookups += 1
        if self.error is not None:
            raise self.error
        db = self

        class _Q:
            def filter(self, *args):
                return self

            def first(self):
                return db.project

        return _Q()


class TestCellAuthorization:
    PROJECT = types.SimpleNamespace(id="p1")

    def _check(self, db, **overrides):
        kwargs = dict(
            project_id="p1",
            user_id="u1",
            organization_id="org-lms",
            configs=[{"metric": "llm_judge_custom"}],
        )
        kwargs.update(overrides)
        return tasks_module._batch_cell_billing_authorized(db, **kwargs)

    def test_policy_is_asked_again_inside_the_cell(self, extended):
        seen = {}

        def policy(db, **kwargs):
            seen.update(kwargs)
            return "org-lms", None, True

        extended(policy)
        db = _ProjectDB(self.PROJECT)
        assert self._check(db) is True
        assert db.savepoints == [{"outcome": "released"}]
        assert seen["project"] is self.PROJECT
        assert seen["organization_id"] == "org-lms"
        assert seen["user_id"] == "u1"

    @pytest.mark.parametrize(
        "result",
        [
            ("org-lms", None, False),
            ("org-other", None, True),
            ("org-lms", {"reason": "org_key_missing"}, True),
            ("org-lms", None),
        ],
        ids=["not-granted", "other-org", "refused", "old-shape"],
    )
    def test_anything_but_a_matching_grant_is_false(self, extended, result):
        extended(lambda db, **k: result)
        assert self._check(_ProjectDB(self.PROJECT)) is False

    def test_policy_runs_in_a_savepoint_and_a_failed_release_is_false(
        self, extended
    ):
        """A failed query inside the policy must not poison the cell's
        session: the policy runs in a savepoint, and a RELEASE that fails
        (aborted savepoint) means "not authorized"."""

        class _ReleaseFails(_ProjectDB):
            @contextlib.contextmanager
            def begin_nested(self):
                self.savepoints.append({"outcome": "rolled_back"})
                yield
                raise RuntimeError("RELEASE SAVEPOINT: transaction is aborted")

        extended(lambda db, **k: ("org-lms", None, True))
        db = _ReleaseFails(self.PROJECT)
        assert self._check(db) is False
        assert db.savepoints == [{"outcome": "rolled_back"}]
        assert db.rollbacks == 0

    def test_no_lookup_without_the_hook_or_the_inputs(self, extended):
        extended(missing=True)
        db = _ProjectDB(self.PROJECT)
        assert self._check(db) is False
        assert db.lookups == 0
        extended(lambda db, **k: ("org-lms", None, True))
        assert self._check(db, project_id=None) is False
        assert self._check(db, organization_id=None) is False
        assert self._check(db, user_id=None) is False
        assert db.lookups == 0

    def test_missing_project_or_failed_lookup_is_false(self, extended):
        extended(lambda db, **k: ("org-lms", None, True))
        assert self._check(_ProjectDB(None)) is False
        broken = _ProjectDB(error=RuntimeError("db down"))
        assert self._check(broken) is False
        assert broken.rollbacks == 1

    def test_cell_judges_get_the_authorization_once(self, extended, monkeypatch):
        calls = []
        monkeypatch.setattr(
            tasks_module,
            "_batch_cell_billing_authorized",
            lambda db, **k: calls.append(k) or True,
        )
        created = []

        import ml_evaluation.llm_judge_evaluator as judge_module

        monkeypatch.setattr(
            judge_module,
            "create_llm_judge_for_user",
            lambda **kwargs: created.append(kwargs) or object(),
        )
        entry = {
            "judge_model_id": "gpt-x",
            "judge_run_id": "jr",
            "judge_evaluator_kwargs": {"judge_model": "gpt-x"},
        }
        tasks_module._reconstruct_judge_evaluators_for_cell(
            configs_for_cell=[{"id": "c1", "metric": "llm_judge_custom"}],
            judge_run_ids_by_config={
                "c1": [dict(entry, run_index=0), dict(entry, run_index=1)]
            },
            triggered_by_user_id="u1",
            organization_id="org-lms",
            db="db",
            project_id="p1",
        )
        assert len(calls) == 1
        assert calls[0]["project_id"] == "p1"
        assert [c["org_billing_authorized"] for c in created] == [True, True]
