"""Tests for the extension point architecture (community edition behavior)."""

import importlib
import sys
from unittest.mock import MagicMock


class TestExtensionLoader:
    """Test that extensions.py works correctly without benger_extended installed."""

    def test_load_extended_returns_false_without_package(self):
        """Community edition: load_extended returns False when package missing."""
        # Ensure benger_extended is not importable for this test
        if "benger_extended" in sys.modules:
            del sys.modules["benger_extended"]

        # Re-import to reset state
        import extensions
        importlib.reload(extensions)

        # Temporarily hide benger_extended
        original = sys.modules.get("benger_extended")
        sys.modules["benger_extended"] = None  # type: ignore

        try:
            importlib.reload(extensions)
            result = extensions.load_extended()
            assert result is False
        finally:
            if original:
                sys.modules["benger_extended"] = original
            else:
                sys.modules.pop("benger_extended", None)

    def test_get_extended_routers_returns_empty_without_package(self):
        """Community edition: get_extended_routers returns empty list."""
        from extensions import get_extended_routers

        # Without loading, should return empty
        result = get_extended_routers()
        assert result == []

    def test_on_annotation_created_noop_without_package(self):
        """Community edition: on_annotation_created is a no-op."""
        from extensions import on_annotation_created

        # Should not raise even with None db
        on_annotation_created(None, "task-1", "user-1", "ann-1", "proj-1")

    def test_on_draft_saved_noop_without_package(self):
        """Community edition: on_draft_saved is a no-op."""
        from extensions import on_draft_saved

        # Should not raise even with None db
        on_draft_saved(None, "task-1", "user-1", "proj-1", [])

    def test_after_user_signup_noop_without_package(self):
        """Community edition: after_user_signup is a no-op (no Vertretbar)."""
        from extensions import after_user_signup

        # Should not raise even with None db and a vertretbar-looking context.
        after_user_signup(None, object(), {"host": "vertretbar.net"})

    def test_after_user_login_noop_without_package(self):
        """Community edition: after_user_login is a no-op (no Vertretbar)."""
        from extensions import after_user_login

        # Should not raise even with None db and a vertretbar-looking context.
        after_user_login(None, object(), {"host": "vertretbar.net"})

    def test_core_api_version_defined(self):
        """CORE_API_VERSION is defined and is a string."""
        from extensions import CORE_API_VERSION

        assert isinstance(CORE_API_VERSION, str)
        # Bumped in lockstep with benger-extended's COMPATIBLE_CORE_VERSIONS.
        # 2.8 adds task_rubrics + llm_judge_rubric (Bewertungsbogen).
        # 2.9 adds the participant access tier + share governance helpers
        # (get_project_access_tier, check_user_can_manage_shares).
        # 2.10 adds org_resolution + project_consumers + the
        # org_billing_authorized consumer-inheritance flag.
        # 2.11 adds organization groups (shared/org_groups,
        # ProjectOrganization.group_id, group-scoped org API keys).
        # 2.12 adds the grading_feedback table + project_models.GradingFeedback
        # (solver thumbs/comment feedback on LLM and human gradings).
        # 2.13 adds task_rubrics.structure / grade_scale (float total_points),
        # shared rubric_structure + task_rubric_service, task-rubrics writes +
        # the stateless parse route, rubric grade points in the judge and
        # optional generator keys on llm_judge_rubric configs.
        # 2.14 adds the shared ``grade_scale_history`` module — the one audit
        # trail both writers of evaluation_config.grade_scale append through
        # (the extended exam router imports it at module level).
        # 2.15 REMOVES the Falllösung judge's prompt versioning: the bulk
        # fan-out no longer forwards ``metric_parameters.prompt_version`` (the
        # extended compute hook no longer takes it) and migration 101 strips
        # the dead key from stored evaluation configs. One judge prompt, one
        # Notenschlüssel, for every exam. It also widens the rubric importer
        # to .csv/.md/.json and adds ``rubric_import.rubric_document_text``,
        # which the extended AI-structuring fallback reads its document with.
        # 2.16 is the Bewertungsbogen fix train: model_defaults.DEFAULT_JUDGE_MODEL_ID,
        # eval_field_classification.bare_field_name / same_field /
        # unprefixed_is_human (migration 102), the evidence-quoted rubric
        # judge and import_jobs.organization_id (migration 103).
        # 2.17 adds rubric_structure.order_criteria_keys,
        # model_defaults.RUBRIC_JUDGE_MAX_TOKENS / METRIC_MAX_TOKENS_FLOOR and
        # creator access to an unattached project under a foreign org context
        # (the extended task-rubric reads route to the platform endpoints).
        # 2.18 adds the evaluation_received_* notification types and
        # notify_evaluation_received (the extended grade endpoints call it).
        # 2.19 adds the attempted access tier (TIER_ATTEMPTED,
        # user_attempted_project / get_attempted_project_ids, the tier= kwarg
        # of enforce_project_read_window) the extended student reads honour.
        # 2.20 adds the LMS self-service schema (migrations 105/106),
        # public_hosts / user_display / auth_module.org_scope, the five LTI
        # API hooks and the 4-tuple grading dispatch policy with block runs.
        # The full per-version log lives in services/shared/core_version.py.
        # 2.21 makes project read access context-free (every membership
        # counts), adds ProjectResponse.can_edit and the per-row roles.
        assert CORE_API_VERSION == "2.21"

    def test_tasks_with_feedback_for_user_empty_without_package(self):
        """Community edition: no human-feedback workflow -> empty set."""
        from extensions import tasks_with_feedback_for_user

        assert tasks_with_feedback_for_user(None, "p", "u", ["t1"]) == set()
        assert tasks_with_feedback_for_user(None, "p", "u", []) == set()

    def test_tasks_with_evaluation_for_user_empty_without_package(self):
        """Community edition: no evaluation-on-own-annotation badge -> empty set."""
        from extensions import tasks_with_evaluation_for_user

        assert tasks_with_evaluation_for_user(None, "p", "u", ["t1"]) == set()
        assert tasks_with_evaluation_for_user(None, "p", "u", []) == set()


class _FakeExtended:
    """Stand-in for a loaded benger_extended package with given hooks."""

    COMPATIBLE_CORE_VERSIONS = ["2.20"]

    def __init__(self, hooks):
        self._hooks = hooks

    def get_hooks(self):
        return self._hooks


def _boom(*args, **kwargs):
    raise RuntimeError("hook exploded")


class TestLtiHooksWithoutPackage:
    """Community edition: every LMS hook answers with its safe default."""

    def test_dispatch_lti_grade_sync_returns_false(self, monkeypatch):
        import extensions

        monkeypatch.setattr(extensions, "_extended", None)
        assert extensions.dispatch_lti_grade_sync("sync-1") is False

    def test_privacy_protected_member_ids_is_empty(self, monkeypatch):
        import extensions

        monkeypatch.setattr(extensions, "_extended", None)
        assert extensions.privacy_protected_member_ids(None, "org-1", ["u1"]) == set()
        assert extensions.privacy_protected_member_ids(None, None, []) == set()

    def test_project_real_name_viewer_is_false(self, monkeypatch):
        import extensions

        monkeypatch.setattr(extensions, "_extended", None)
        assert extensions.project_real_name_viewer(None, object(), "p1") is False

    def test_lti_anonymization_policy_has_no_rules(self, monkeypatch):
        import extensions

        monkeypatch.setattr(extensions, "_extended", None)
        assert extensions.lti_anonymization_policy(None, "u1") == {
            "implicit_org_ids": set(),
            "blockers": [],
        }

    def test_no_protected_orgs(self, monkeypatch):
        import extensions

        monkeypatch.setattr(extensions, "_extended", None)
        assert extensions.lti_protected_org_ids(None) == set()
        assert extensions.is_lti_protected_org(None, "org-1") is False
        assert extensions.lti_protected_org_subset(None, ["org-1"]) == set()

    def test_nobody_is_unmasked(self, monkeypatch):
        import extensions

        monkeypatch.setattr(extensions, "_extended", None)
        assert extensions.project_real_name_user_ids(None, object(), "p1", ["u1"]) == set()

    def test_package_without_the_hooks_behaves_like_community(self, monkeypatch):
        import extensions

        monkeypatch.setattr(extensions, "_extended", _FakeExtended({}))
        assert extensions.dispatch_lti_grade_sync("sync-1") is False
        assert extensions.privacy_protected_member_ids(None, "o", ["u1"]) == set()
        assert extensions.project_real_name_viewer(None, object(), "p1") is False
        assert extensions.lti_anonymization_policy(None, "u1")["blockers"] == []
        assert extensions.is_lti_protected_org(None, "org-1") is False
        assert extensions.lti_protected_org_subset(None, ["org-1"]) == set()
        assert extensions.project_real_name_user_ids(None, object(), "p1", ["u1"]) == set()


class TestLtiHooksWithPackage:
    def test_hooks_receive_arguments_and_results_are_normalized(self, monkeypatch):
        import extensions

        calls = {}

        def dispatch(sync_id):
            calls["dispatch"] = sync_id
            return 1

        def protected(db, org_id, user_ids):
            calls["protected"] = (db, org_id, list(user_ids))
            # A foreign id in the answer must never widen the result.
            return ["u2", "stranger"]

        def viewer(db, user, project_id):
            calls["viewer"] = (db, user, project_id)
            return "yes"

        def people(db, user, project_id, user_ids):
            calls["people"] = (db, user, project_id, list(user_ids))
            return ["u1", "stranger"]

        def policy(db, user_id):
            calls["policy"] = (db, user_id)
            return {"implicit_org_ids": ["org-v"], "blockers": ("has_payment_records",)}

        monkeypatch.setattr(
            extensions,
            "_extended",
            _FakeExtended(
                {
                    "dispatch_lti_grade_sync": dispatch,
                    "privacy_protected_member_ids": protected,
                    "project_real_name_viewer": viewer,
                    "project_real_name_user_ids": people,
                    "lti_anonymization_policy": policy,
                    "lti_protected_org_ids": lambda db: ["org-v"],
                }
            ),
        )
        db, user = object(), object()

        assert extensions.dispatch_lti_grade_sync("sync-9") is True
        assert calls["dispatch"] == "sync-9"

        assert extensions.privacy_protected_member_ids(db, "org-1", ["u2", "u1", "u2"]) == {"u2"}
        assert calls["protected"] == (db, "org-1", ["u1", "u2"])

        assert extensions.project_real_name_viewer(db, user, "p1") is True
        assert calls["viewer"] == (db, user, "p1")

        assert extensions.project_real_name_user_ids(
            db, user, "p1", ["u2", "u1", None]
        ) == {"u1"}
        assert calls["people"] == (db, user, "p1", ["u1", "u2"])
        # No viewer, no project or nobody asked about: the hook is skipped.
        calls.pop("people")
        assert extensions.project_real_name_user_ids(db, None, "p1", ["u1"]) == set()
        assert extensions.project_real_name_user_ids(db, user, "", ["u1"]) == set()
        assert extensions.project_real_name_user_ids(db, user, "p1", []) == set()
        assert "people" not in calls

        assert extensions.lti_anonymization_policy(db, "u1") == {
            "implicit_org_ids": {"org-v"},
            "blockers": ["has_payment_records"],
        }
        assert calls["policy"] == (db, "u1")

        assert extensions.lti_protected_org_ids(db) == {"org-v"}
        assert extensions.is_lti_protected_org(db, "org-v") is True
        assert extensions.is_lti_protected_org(db, "org-u") is False
        assert extensions.is_lti_protected_org(db, None) is False
        assert extensions.lti_protected_org_subset(db, ["org-v", "org-u", None]) == {
            "org-v"
        }
        assert extensions.lti_protected_org_subset(db, []) == set()

    def test_empty_member_list_skips_the_hook(self, monkeypatch):
        import extensions

        monkeypatch.setattr(
            extensions,
            "_extended",
            _FakeExtended({"privacy_protected_member_ids": _boom}),
        )
        assert extensions.privacy_protected_member_ids(None, "org-1", []) == set()

    def test_failing_hooks_are_logged_and_fail_safe(self, monkeypatch):
        import extensions

        logger = MagicMock()
        monkeypatch.setattr(extensions, "logger", logger)

        monkeypatch.setattr(
            extensions,
            "_extended",
            _FakeExtended(
                {
                    "dispatch_lti_grade_sync": _boom,
                    "privacy_protected_member_ids": _boom,
                    "project_real_name_viewer": _boom,
                    "project_real_name_user_ids": _boom,
                    "lti_anonymization_policy": _boom,
                    "lti_protected_org_ids": _boom,
                }
            ),
        )
        # Nothing is dispatched; the sweep picks the row up later.
        assert extensions.dispatch_lti_grade_sync("sync-1") is False
        # Privacy fails closed: every asked-about member stays masked, and
        # no org admin may unmask anyone.
        assert extensions.privacy_protected_member_ids(None, None, ["u1", "u2"]) == {
            "u1",
            "u2",
        }
        assert extensions.privacy_protected_member_ids(None, "o", ["u1", "u2"]) == set()
        assert extensions.project_real_name_viewer(None, object(), "p1") is False
        assert extensions.project_real_name_user_ids(None, object(), "p1", ["u1"]) == set()
        # Anonymization is blocked while the policy cannot be checked.
        assert extensions.lti_anonymization_policy(None, "u1") == {
            "implicit_org_ids": set(),
            "blockers": ["policy_unavailable"],
        }
        assert extensions.lti_protected_org_ids(None) == set()
        # The access gates fail closed.
        assert extensions.is_lti_protected_org(None, "org-1") is True
        assert extensions.lti_protected_org_subset(None, ["org-1", "org-2"]) == {
            "org-1",
            "org-2",
        }
        # Every failure was logged, none was raised.
        assert logger.exception.call_count == 9


class _SavepointSession:
    """Records ``begin_nested()`` use and how each savepoint ended."""

    def __init__(self):
        self.savepoints = []

    def begin_nested(self):
        session = self

        class _Savepoint:
            def __enter__(self):
                session.savepoints.append("open")
                return self

            def __exit__(self, exc_type, exc, tb):
                session.savepoints[-1] = "rolled_back" if exc_type else "released"
                return False

        return _Savepoint()


class TestLtiHooksRunInASavepoint:
    """A hook that queries through ``db`` must not poison the caller's
    transaction when its query fails: it runs in a savepoint, and the safe
    value is the answer."""

    def _install(self, monkeypatch, hooks):
        import extensions

        monkeypatch.setattr(extensions, "_extended", _FakeExtended(hooks))
        monkeypatch.setattr(extensions, "logger", MagicMock())
        return extensions

    def test_query_hooks_use_a_savepoint(self, monkeypatch):
        extensions = self._install(
            monkeypatch,
            {
                "privacy_protected_member_ids": lambda db, org, ids, **kw: ids,
                "project_real_name_viewer": lambda db, v, p: True,
                "project_real_name_user_ids": lambda db, v, p, ids: ids,
                "lti_anonymization_policy": lambda db, uid: {"blockers": []},
            },
        )
        db = _SavepointSession()
        assert extensions.privacy_protected_member_ids(db, None, ["u1"]) == {"u1"}
        assert extensions.project_real_name_viewer(db, object(), "p1") is True
        assert extensions.project_real_name_user_ids(db, object(), "p1", ["u1"]) == {
            "u1"
        }
        assert extensions.lti_anonymization_policy(db, "u1")["blockers"] == []
        assert db.savepoints == ["released"] * 4

    def test_failing_query_hooks_roll_back_their_savepoint(self, monkeypatch):
        extensions = self._install(
            monkeypatch,
            {
                "privacy_protected_member_ids": _boom,
                "project_real_name_viewer": _boom,
                "project_real_name_user_ids": _boom,
                "lti_anonymization_policy": _boom,
            },
        )
        db = _SavepointSession()
        assert extensions.privacy_protected_member_ids(db, None, ["u1"]) == {"u1"}
        assert extensions.privacy_protected_member_ids(db, "o", ["u1"]) == set()
        assert extensions.project_real_name_viewer(db, object(), "p1") is False
        assert extensions.project_real_name_user_ids(db, object(), "p1", ["u1"]) == set()
        assert extensions.lti_anonymization_policy(db, "u1")["blockers"] == [
            "policy_unavailable"
        ]
        assert db.savepoints == ["rolled_back"] * 5


class TestGroupScopedLmsUsers:
    """``group_ids`` limits the reveal to the connections of those groups."""

    def test_group_ids_reach_the_hook(self, monkeypatch):
        import extensions

        calls = []

        def protected(db, org_id, user_ids, group_ids=None):
            calls.append((org_id, list(user_ids), group_ids))
            return ["u1"]

        monkeypatch.setattr(
            extensions,
            "_extended",
            _FakeExtended({"privacy_protected_member_ids": protected}),
        )
        got = extensions.privacy_protected_member_ids(
            None, "org-1", ["u1", "u2"], group_ids={"g2", "g1", None}
        )
        assert got == {"u1"}
        assert calls == [("org-1", ["u1", "u2"], ["g1", "g2"])]

    def test_empty_groups_or_no_org_reveal_nobody_without_asking(self, monkeypatch):
        import extensions

        monkeypatch.setattr(
            extensions,
            "_extended",
            _FakeExtended({"privacy_protected_member_ids": _boom}),
        )
        assert (
            extensions.privacy_protected_member_ids(None, "org-1", ["u1"], group_ids=[])
            == set()
        )
        assert (
            extensions.privacy_protected_member_ids(None, None, ["u1"], group_ids=["g"])
            == set()
        )

    def test_hook_without_the_keyword_fails_closed(self, monkeypatch):
        import extensions

        monkeypatch.setattr(extensions, "logger", MagicMock())
        monkeypatch.setattr(
            extensions,
            "_extended",
            _FakeExtended(
                {"privacy_protected_member_ids": lambda db, org, ids: list(ids)}
            ),
        )
        assert (
            extensions.privacy_protected_member_ids(None, "org-1", ["u1"], group_ids=["g"])
            == set()
        )
        # The org-wide call still works with the old signature.
        assert extensions.privacy_protected_member_ids(None, "org-1", ["u1"]) == {"u1"}

    def test_community_edition_reveals_nobody(self, monkeypatch):
        import extensions

        monkeypatch.setattr(extensions, "_extended", None)
        assert (
            extensions.privacy_protected_member_ids(None, "org-1", ["u1"], group_ids=["g"])
            == set()
        )


class TestBulkProjectRealNames:
    def test_bulk_hook_is_called_once(self, monkeypatch):
        import extensions

        calls = []

        def bulk(db, viewer, wanted):
            calls.append(wanted)
            return {"p1": ["u1", "stranger"], "p2": None, "other": ["x"]}

        monkeypatch.setattr(
            extensions,
            "_extended",
            _FakeExtended(
                {"projects_real_name_user_ids": bulk, "project_real_name_user_ids": _boom}
            ),
        )
        got = extensions.projects_real_name_user_ids(
            None, object(), {"p1": ["u1", "u2"], "p2": ["u3"], "p3": [], None: ["u9"]}
        )
        assert got == {"p1": {"u1"}, "p2": set(), "p3": set()}
        assert calls == [{"p1": ["u1", "u2"], "p2": ["u3"]}]

    def test_without_the_bulk_hook_each_project_is_asked(self, monkeypatch):
        import extensions

        calls = []

        def single(db, viewer, project_id, ids):
            calls.append((project_id, list(ids)))
            return ids if project_id == "p1" else []

        monkeypatch.setattr(
            extensions,
            "_extended",
            _FakeExtended({"project_real_name_user_ids": single}),
        )
        got = extensions.projects_real_name_user_ids(
            None, object(), {"p1": ["u1"], "p2": ["u2"]}
        )
        assert got == {"p1": {"u1"}, "p2": set()}
        assert sorted(calls) == [("p1", ["u1"]), ("p2", ["u2"])]

    def test_failures_and_community_reveal_nobody(self, monkeypatch):
        import extensions

        monkeypatch.setattr(extensions, "logger", MagicMock())
        monkeypatch.setattr(
            extensions,
            "_extended",
            _FakeExtended({"projects_real_name_user_ids": _boom}),
        )
        wanted = {"p1": ["u1"]}
        assert extensions.projects_real_name_user_ids(None, object(), wanted) == {
            "p1": set()
        }
        monkeypatch.setattr(
            extensions,
            "_extended",
            _FakeExtended({"projects_real_name_user_ids": lambda *a: ["not", "a", "dict"]}),
        )
        assert extensions.projects_real_name_user_ids(None, object(), wanted) == {
            "p1": set()
        }
        assert extensions.projects_real_name_user_ids(None, None, wanted) == {
            "p1": set()
        }
        monkeypatch.setattr(extensions, "_extended", None)
        assert extensions.projects_real_name_user_ids(None, object(), wanted) == {
            "p1": set()
        }


class _RollbackSession:
    """Records rollbacks; the resend hook runs without a savepoint."""

    def __init__(self, fail_rollback=False):
        self.rollbacks = 0
        self.fail_rollback = fail_rollback

    def begin_nested(self):  # pragma: no cover - must not be used
        raise AssertionError("resend_all_lti_grades must not open a savepoint")

    def rollback(self):
        self.rollbacks += 1
        if self.fail_rollback:
            raise RuntimeError("connection gone")


class TestResendAllLtiGrades:
    """``extensions.resend_all_lti_grades``: None without the hook, the
    hook's dict otherwise, ``{"status": "failed"}`` when it breaks."""

    def test_community_edition_has_no_resend(self, monkeypatch):
        import extensions

        monkeypatch.setattr(extensions, "_extended", None)
        assert extensions.resend_all_lti_grades(None, "reg-1") is None
        monkeypatch.setattr(extensions, "_extended", _FakeExtended({}))
        assert extensions.resend_all_lti_grades(None, "reg-1") is None

    def test_the_hook_answer_is_passed_through(self, monkeypatch):
        import extensions

        calls = []
        answer = {"status": "queued", "transfers": 4}

        def hook(db, registration_id):
            calls.append((db, registration_id))
            return answer

        monkeypatch.setattr(
            extensions, "_extended", _FakeExtended({"resend_all_lti_grades": hook})
        )
        db = _RollbackSession()

        result = extensions.resend_all_lti_grades(db, 7)

        assert result == answer
        assert result is not answer
        assert calls == [(db, "7")]
        assert db.rollbacks == 0

    def test_a_failing_hook_rolls_back_and_reports_failed(self, monkeypatch):
        import extensions

        logger = MagicMock()
        monkeypatch.setattr(extensions, "logger", logger)
        monkeypatch.setattr(
            extensions, "_extended", _FakeExtended({"resend_all_lti_grades": _boom})
        )
        db = _RollbackSession()

        assert extensions.resend_all_lti_grades(db, "reg-1") == {"status": "failed"}
        assert db.rollbacks == 1
        logger.exception.assert_called()

        broken = _RollbackSession(fail_rollback=True)
        assert extensions.resend_all_lti_grades(broken, "reg-1") == {"status": "failed"}
        # A session without rollback (a test double) is fine too.
        assert extensions.resend_all_lti_grades(None, "reg-1") == {"status": "failed"}

    def test_a_wrong_answer_is_failed(self, monkeypatch):
        import extensions

        monkeypatch.setattr(extensions, "logger", MagicMock())
        monkeypatch.setattr(
            extensions,
            "_extended",
            _FakeExtended({"resend_all_lti_grades": lambda db, rid: ["queued"]}),
        )
        assert extensions.resend_all_lti_grades(None, "reg-1") == {"status": "failed"}

    def test_a_broken_hook_table_is_failed(self, monkeypatch):
        import extensions

        class _Broken:
            def get_hooks(self):
                raise RuntimeError("import error")

        monkeypatch.setattr(extensions, "logger", MagicMock())
        monkeypatch.setattr(extensions, "_extended", _Broken())
        assert extensions.resend_all_lti_grades(None, "reg-1") == {"status": "failed"}
