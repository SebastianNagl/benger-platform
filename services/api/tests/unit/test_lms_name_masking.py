"""Fail-safe behaviour of the shared LMS name masking (``lms_name_masking``)."""

import sys
import types
from types import SimpleNamespace

import pytest

from lms_name_masking import NameVisibility, is_lms_account_sync, lms_user_ids_from_links

pytestmark = pytest.mark.unit


def _boom(*args, **kwargs):
    raise RuntimeError("exploded")


class _BrokenDB:
    def execute(self, *args, **kwargs):
        raise RuntimeError("database down")


def _users(*ids, use_pseudonym=True):
    return [SimpleNamespace(id=uid, pseudonym=f"P {uid}", use_pseudonym=use_pseudonym) for uid in ids]


class TestNameVisibility:
    def test_link_lookup_failure_masks_every_candidate(self):
        policy = NameVisibility(_boom, None)
        viewer = SimpleNamespace(id="v", is_superadmin=False)
        assert policy.masked_user_ids(
            _BrokenDB(), _users("u1", "u2"), project_id="p", viewer=viewer
        ) == {"u1", "u2"}

    def test_superadmin_and_self_are_never_masked(self):
        policy = NameVisibility(lambda db, org, ids: set(ids), None)
        admin = SimpleNamespace(id="a", is_superadmin=True)
        assert policy.masked_user_ids(None, _users("u1"), project_id="p", viewer=admin) == set()
        me = SimpleNamespace(id="u1", is_superadmin=False)
        assert policy.masked_user_ids(None, _users("u1"), project_id="p", viewer=me) == set()

    def test_no_viewer_masks_and_skips_the_viewer_hook(self):
        calls = []
        policy = NameVisibility(
            lambda db, org, ids: set(ids), lambda *a: calls.append(a) or set(a[3])
        )
        assert policy.masked_user_ids(None, _users("u1"), project_id="p") == {"u1"}
        assert calls == []

    def test_viewer_hook_unmasks_only_the_people_it_names(self):
        calls = []

        def people(db, viewer, project_id, ids):
            calls.append((viewer.id, project_id, list(ids)))
            return {"u1", "stranger"}

        policy = NameVisibility(lambda db, org, ids: set(ids), people)
        viewer = SimpleNamespace(id="v", is_superadmin=False)
        assert policy.masked_user_ids(
            None, _users("u1", "u2"), project_id="p", viewer=viewer
        ) == {"u2"}
        assert calls == [("v", "p", ["u1", "u2"])]

    def test_opted_out_users_are_not_candidates(self):
        policy = NameVisibility(_boom, _boom)
        viewer = SimpleNamespace(id="v", is_superadmin=False)
        assert (
            policy.masked_user_ids(
                None, _users("u1", use_pseudonym=False) + [None], project_id="p", viewer=viewer
            )
            == set()
        )

    def test_viewer_hook_needs_a_project(self):
        policy = NameVisibility(None, lambda db, v, p, ids: set(ids))
        viewer = SimpleNamespace(id="v", is_superadmin=False)
        assert policy.real_name_user_ids(None, viewer, None, ["u1"]) == set()
        assert policy.real_name_user_ids(None, None, "p", ["u1"]) == set()
        assert policy.real_name_user_ids(None, viewer, "p", []) == set()
        assert policy.real_name_user_ids(None, viewer, "p", ["u1", None]) == {"u1"}
        assert NameVisibility(None, _boom).real_name_user_ids(
            None, viewer, "p", ["u1"]
        ) == set()
        assert NameVisibility().real_name_user_ids(None, viewer, "p", ["u1"]) == set()
        admin = SimpleNamespace(id="a", is_superadmin=True)
        assert NameVisibility().real_name_user_ids(None, admin, None, ["u1"]) == {"u1"}

    def test_lms_hook_answers_are_limited_to_the_question(self):
        policy = NameVisibility(lambda db, org, ids: ["u1", "stranger", None], None)
        assert policy.lms_user_ids(None, ["u1", "u2", None, ""]) == {"u1"}
        assert policy.lms_user_ids(None, []) == set()

    @staticmethod
    def _worker_package(monkeypatch, getter):
        package = types.ModuleType("benger_extended")
        workers = types.ModuleType("benger_extended.workers")
        workers.get_name_visibility_fns = getter
        package.workers = workers
        monkeypatch.setitem(sys.modules, "benger_extended", package)
        monkeypatch.setitem(sys.modules, "benger_extended.workers", workers)

    def test_failing_worker_getter_uses_the_link_table(self, monkeypatch):
        monkeypatch.delitem(sys.modules, "extensions", raising=False)
        self._worker_package(monkeypatch, _boom)
        policy = NameVisibility.load()
        assert policy._lms_user_ids is None and policy._real_name_user_ids is None

    def test_missing_package_uses_the_link_table(self, monkeypatch):
        monkeypatch.delitem(sys.modules, "extensions", raising=False)
        monkeypatch.setitem(sys.modules, "benger_extended", None)
        policy = NameVisibility.load()
        assert policy._lms_user_ids is None and policy._real_name_user_ids is None

    def test_api_process_follows_the_extension_loader(self, monkeypatch):
        """In the API process a refused extended package (failed handshake)
        contributes no hooks; an accepted one does."""
        hooks = (lambda db, org, ids: set(ids), lambda db, v, p, ids: set())
        self._worker_package(monkeypatch, lambda: hooks)
        loader = types.ModuleType("extensions")
        loader.load_extended = lambda: None
        loader._extended = None
        monkeypatch.setitem(sys.modules, "extensions", loader)
        assert NameVisibility.load()._lms_user_ids is None

        loader._extended = object()
        policy = NameVisibility.load()
        assert policy._lms_user_ids is hooks[0]
        assert policy._real_name_user_ids is hooks[1]

        # A worker process has no extension loader: the hook is used.
        monkeypatch.delitem(sys.modules, "extensions")
        assert NameVisibility.load()._lms_user_ids is hooks[0]


class TestLinkTableHelpers:
    def test_empty_questions_skip_the_database(self):
        assert lms_user_ids_from_links(_BrokenDB(), []) == set()
        assert lms_user_ids_from_links(_BrokenDB(), None) == set()
        assert is_lms_account_sync(_BrokenDB(), None) is False
        assert is_lms_account_sync(_BrokenDB(), "") is False
