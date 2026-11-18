"""Rules of the compliance records (shared ``compliance_records``, core 2.56).

Pure tests on stand-in objects: the static transition tables and the stamps
they set, the registration lock, the read-only states, the canonical hash,
and that the router, the models and migration 145 use the same vocabularies.
"""

import importlib.util
import os
import typing
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import compliance_records as records

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


def _assessment(status="draft", thresholds=None):
    return SimpleNamespace(
        status=status,
        thresholds=thresholds if thresholds is not None else {"a": 1},
        thresholds_hash=None,
        registered_at=None,
        attested_at=None,
    )


def _run(status="queued"):
    return SimpleNamespace(status=status, started_at=None, finished_at=None)


class TestAssessmentTransitions:
    def test_every_status_has_a_row_and_targets_are_known(self):
        assert set(records.ASSESSMENT_TRANSITIONS) == set(records.ASSESSMENT_STATUSES)
        for targets in records.ASSESSMENT_TRANSITIONS.values():
            assert targets <= set(records.ASSESSMENT_STATUSES)

    def test_terminal_statuses_lead_only_to_supersession(self):
        for status in records.TERMINAL_ASSESSMENT_STATUSES:
            assert records.ASSESSMENT_TRANSITIONS[status] <= {records.ASSESSMENT_SUPERSEDED}
        assert records.ASSESSMENT_TRANSITIONS[records.ASSESSMENT_WITHDRAWN] == frozenset()
        assert records.ASSESSMENT_TRANSITIONS[records.ASSESSMENT_SUPERSEDED] == frozenset()

    def test_full_path_stamps_registration_and_attestation(self):
        a = _assessment(thresholds={"b": [1, 2], "a": {"y": 2, "x": 1}})
        for status in ("registered", "collecting", "scoring", "review", "attested"):
            records.transition_assessment(a, status, now=NOW)
        assert a.status == "attested"
        assert a.registered_at == NOW and a.attested_at == NOW
        assert a.thresholds_hash == records.canonical_sha256(
            {"a": {"x": 1, "y": 2}, "b": [1, 2]}
        )
        records.transition_assessment(a, "superseded", now=NOW)
        assert a.status == "superseded"

    @pytest.mark.parametrize(
        "start,target",
        [("draft", "attested"), ("draft", "scoring"), ("registered", "draft"),
         ("attested", "withdrawn"), ("withdrawn", "draft"), ("superseded", "attested")],
    )
    def test_moves_outside_the_table_are_refused(self, start, target):
        a = _assessment(status=start)
        with pytest.raises(records.ComplianceRecordConflict) as exc:
            records.transition_assessment(a, target, now=NOW)
        assert exc.value.code == "invalid_transition"
        assert a.status == start and a.registered_at is None

    def test_unknown_status_is_a_value_error(self):
        with pytest.raises(ValueError):
            records.transition_assessment(_assessment(), "finished")

    def test_rescoring_loops_are_allowed(self):
        a = _assessment(status="review")
        records.transition_assessment(a, "scoring")
        records.transition_assessment(a, "collecting")
        assert a.status == "collecting"


class TestLocks:
    def test_draft_accepts_every_field(self):
        records.check_assessment_editable(_assessment(), records.REGISTRATION_LOCKED_FIELDS)

    @pytest.mark.parametrize("status", ["registered", "collecting", "scoring", "review"])
    def test_registered_fixes_the_locked_fields_only(self, status):
        a = _assessment(status=status)
        records.check_assessment_editable(a, ["title", "limitations_text"])
        with pytest.raises(records.ComplianceRecordConflict) as exc:
            records.check_assessment_editable(a, ["title", "thresholds"])
        assert exc.value.code == "assessment_registered"
        assert "thresholds" in exc.value.detail

    @pytest.mark.parametrize("status", sorted(records.TERMINAL_ASSESSMENT_STATUSES))
    def test_terminal_refuses_everything(self, status):
        a = _assessment(status=status)
        for check in (
            lambda: records.check_assessment_editable(a, ["title"]),
            lambda: records.check_assessment_accepts_suite_runs(a),
            lambda: records.check_findings_writable(a, _run("running")),
        ):
            with pytest.raises(records.ComplianceRecordConflict) as exc:
                check()
            assert exc.value.code == "assessment_closed"

    def test_only_drafts_and_their_runs_are_deleted(self):
        records.check_assessment_deletable(_assessment())
        records.check_suite_run_deletable(_assessment(), _run("succeeded"))
        for status in ("registered", "attested", "withdrawn"):
            with pytest.raises(records.ComplianceRecordConflict):
                records.check_assessment_deletable(_assessment(status=status))
            with pytest.raises(records.ComplianceRecordConflict):
                records.check_suite_run_deletable(_assessment(status=status), _run())

    @pytest.mark.parametrize("status", sorted(records.TERMINAL_SUITE_RUN_STATUSES))
    def test_finished_runs_fix_their_findings(self, status):
        with pytest.raises(records.ComplianceRecordConflict) as exc:
            records.check_findings_writable(_assessment(status="scoring"), _run(status))
        assert exc.value.code == "suite_run_finished"

    def test_open_runs_take_findings(self):
        for status in ("queued", "running"):
            records.check_findings_writable(_assessment(status="scoring"), _run(status))


class TestSuiteRunTransitions:
    def test_running_then_succeeded_stamps_both_times(self):
        run = _run()
        records.transition_suite_run(run, "running", now=NOW)
        assert run.started_at == NOW and run.finished_at is None
        later = datetime(2026, 11, 18, 13, 0, tzinfo=timezone.utc)
        records.transition_suite_run(run, "succeeded", now=later)
        assert run.status == "succeeded"
        assert run.started_at == NOW and run.finished_at == later

    def test_same_status_is_a_no_op(self):
        run = _run("running")
        records.transition_suite_run(run, "running", now=NOW)
        assert run.started_at is None

    def test_queued_cannot_succeed_and_finished_cannot_move(self):
        with pytest.raises(records.ComplianceRecordConflict):
            records.transition_suite_run(_run(), "succeeded")
        for status in records.TERMINAL_SUITE_RUN_STATUSES:
            with pytest.raises(records.ComplianceRecordConflict):
                records.transition_suite_run(_run(status), "running")

    def test_queued_can_fail_or_be_cancelled(self):
        for status in ("failed", "cancelled"):
            run = _run()
            records.transition_suite_run(run, status, now=NOW)
            assert run.finished_at == NOW and run.started_at is None


class TestCanonicalHash:
    def test_key_order_does_not_change_the_hash(self):
        assert records.canonical_sha256({"b": 1, "a": {"d": 2, "c": 3}}) == (
            records.canonical_sha256({"a": {"c": 3, "d": 2}, "b": 1})
        )

    def test_canonical_form(self):
        assert records.canonical_json({"b": "ä", "a": [1, 2.5]}) == '{"a":[1,2.5],"b":"ä"}'

    def test_non_finite_numbers_are_refused(self):
        with pytest.raises(ValueError):
            records.canonical_json({"x": float("nan")})


class TestVocabularyParity:
    """The router's request types, the models' CHECK constraints and
    migration 145 all spell the same statuses and verdicts."""

    def test_router_literals(self):
        from routers import compliance_records as router

        assert typing.get_args(router.Verdict) == records.VERDICTS
        assert typing.get_args(router.SuiteRunStatus) == records.SUITE_RUN_STATUSES
        assert typing.get_args(router.AssessmentStatus) == records.ASSESSMENT_STATUSES

    def test_migration_constants(self):
        versions = os.path.join(os.path.dirname(__file__), "..", "..", "alembic", "versions")
        path = os.path.join(versions, "145_compliance_findings.py")
        spec = importlib.util.spec_from_file_location("mig145_vocab", path)
        mig = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mig)
        assert mig._ASSESSMENT_STATUSES == records.ASSESSMENT_STATUSES
        assert mig._SUITE_RUN_STATUSES == records.SUITE_RUN_STATUSES
        assert mig._VERDICTS == records.VERDICTS

    def test_model_checks(self):
        from models import ComplianceAssessment, ComplianceFinding, ComplianceSuiteRun

        def check(model, name):
            for constraint in model.__table__.constraints:
                if constraint.name == name:
                    return str(constraint.sqltext)
            raise AssertionError(name)

        for value in records.ASSESSMENT_STATUSES:
            assert f"'{value}'" in check(ComplianceAssessment, "ck_compliance_assessments_status")
        for value in records.SUITE_RUN_STATUSES:
            assert f"'{value}'" in check(ComplianceSuiteRun, "ck_compliance_suite_runs_status")
        for value in records.VERDICTS:
            assert f"'{value}'" in check(ComplianceFinding, "ck_compliance_findings_verdict")
