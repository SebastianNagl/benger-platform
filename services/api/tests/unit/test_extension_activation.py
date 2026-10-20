"""``extension_activation`` (core 2.42): per-context decisions, memoization,
propagation across threadpools and Celery messages, worker getter gating."""

from __future__ import annotations

import sys
import types
from unittest.mock import patch

import pytest
from starlette.concurrency import run_in_threadpool

import extension_activation as activation
import extension_registry
from feature_flags import registry, service
from feature_flags.registry import STATE_ALLOWLIST, STATE_EVERYONE, STATE_OFF

PKG = "benger_fake"
MASTER = "extension.fake"


@pytest.fixture(autouse=True)
def _master():
    registry.register_master_flag(PKG, "fake", STATE_OFF)
    yield
    registry.unregister_flags(PKG)
    registry.reset_master_flags()


def _snapshot(state, users=(), orgs=()):
    return {MASTER: {"state": state, "users": list(users), "orgs": list(orgs)}}


class _CountingCache:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.reads = 0

    def __call__(self):
        self.reads += 1
        return self.snapshot


def _with_snapshot(snapshot):
    return patch.object(service, "cache_get", _CountingCache(snapshot))


class TestDecisions:
    def test_platform_and_always_are_always_active(self):
        with _with_snapshot(_snapshot(STATE_OFF)):
            assert activation.package_active("platform")
            assert activation.extension_active("platform")
            assert activation.package_active(PKG, activation.ALWAYS)
            assert not activation.package_active(PKG, activation.GATED)
            assert not activation.package_active(PKG, activation.POLICY_GLOBAL)

    def test_package_without_a_master_flag_counts_as_active(self):
        assert activation.package_active("benger_stand_in")
        # ... but a package that is neither loaded nor registered is not.
        assert not activation.extension_active("benger_stand_in")

    def test_anonymous_and_system_contexts(self):
        with _with_snapshot(_snapshot(STATE_ALLOWLIST, users=["u1"], orgs=["o1"])):
            with activation.use_context(kind=activation.KIND_SYSTEM):
                assert not activation.package_active(PKG)
                assert activation.package_active(PKG, activation.POLICY_GLOBAL)
        with _with_snapshot(_snapshot(STATE_EVERYONE)):
            with activation.use_context():
                assert activation.package_active(PKG)

    def test_user_and_org_rules(self):
        with _with_snapshot(_snapshot(STATE_ALLOWLIST, users=["u1"], orgs=["o1"])):
            with activation.use_context(user_id="u1"):
                assert activation.package_active(PKG)
            with activation.use_context(user_id="u2", org_ids=["o1"]):
                assert activation.package_active(PKG)
            with activation.use_context(user_id="u2", org_ids=["o2"]):
                assert not activation.package_active(PKG)
            # Memberships decide when no org override is set.
            with patch.object(activation, "_membership_org_ids", return_value=frozenset({"o1"})):
                with activation.use_context(user_id="u3"):
                    assert activation.package_active(PKG)

    def test_project_orgs_replace_memberships(self):
        with _with_snapshot(_snapshot(STATE_ALLOWLIST, orgs=["o1"])):
            with patch.object(activation, "project_org_ids", return_value=frozenset({"o1"})):
                with activation.use_context(user_id="u9", project_id="p1"):
                    assert activation.package_active(PKG)
            with patch.object(activation, "project_org_ids", return_value=frozenset()):
                with patch.object(
                    activation, "_membership_org_ids", return_value=frozenset({"o1"})
                ) as memberships:
                    with activation.use_context(user_id="u9", project_id="p2"):
                        assert not activation.package_active(PKG)
                    memberships.assert_not_called()

    def test_unknown_gating_class_is_refused(self):
        with pytest.raises(ValueError):
            activation.package_active(PKG, "sometimes")


class TestFlagActive:
    """``flag_active``: any registered flag in the current context."""

    NOTES = registry.MARGIN_NOTES

    def _snap(self, state, users=(), orgs=(), master=STATE_EVERYONE):
        return {
            MASTER: {"state": master, "users": [], "orgs": []},
            self.NOTES: {"state": state, "users": list(users), "orgs": list(orgs)},
            "fake_feature": {"state": state, "users": list(users), "orgs": list(orgs)},
        }

    def test_platform_flag_states(self):
        with _with_snapshot(self._snap(STATE_OFF)):
            with activation.use_context(user_id="u1"):
                assert not activation.flag_active(self.NOTES)
        with _with_snapshot(self._snap(STATE_EVERYONE)):
            with activation.use_context(kind=activation.KIND_SYSTEM):
                assert activation.flag_active(self.NOTES)

    def test_allowlist_follows_the_project_orgs(self):
        with _with_snapshot(self._snap(STATE_ALLOWLIST, orgs=["o1"])):
            with patch.object(activation, "project_org_ids", return_value=frozenset({"o1"})):
                with activation.use_context(user_id="teacher", project_id="p1"):
                    assert activation.flag_active(self.NOTES)
            with patch.object(activation, "project_org_ids", return_value=frozenset({"o2"})):
                with activation.use_context(user_id="teacher", project_id="p2"):
                    assert not activation.flag_active(self.NOTES)
            # A system context without user or project passes only everyone.
            with activation.use_context(kind=activation.KIND_SYSTEM):
                assert not activation.flag_active(self.NOTES)

    def test_unregistered_name_is_off(self):
        with _with_snapshot({"nope": {"state": STATE_EVERYONE, "users": [], "orgs": []}}):
            assert not activation.flag_active("nope")

    def test_package_flag_is_coupled_to_its_master(self):
        registry.register_flags(
            PKG, [registry.FlagDefinition("fake_feature", "test", STATE_OFF)]
        )
        with _with_snapshot(self._snap(STATE_EVERYONE, master=STATE_OFF)):
            with activation.use_context(user_id="u1"):
                assert not activation.flag_active("fake_feature")
        with _with_snapshot(self._snap(STATE_EVERYONE, master=STATE_EVERYONE)):
            with activation.use_context(user_id="u1"):
                assert activation.flag_active("fake_feature")


class TestMemo:
    def test_one_snapshot_read_per_context(self):
        cache = _CountingCache(_snapshot(STATE_EVERYONE))
        with patch.object(service, "cache_get", cache):
            with activation.use_context(user_id="u1", inherit=False):
                for _ in range(5):
                    assert activation.package_active(PKG)
                    assert activation.package_active(PKG, activation.POLICY_GLOBAL)
                with activation.use_context(project_id="p1"):
                    assert activation.package_active(PKG)
        assert cache.reads == 1

    @pytest.mark.asyncio
    async def test_context_and_memo_cross_run_in_threadpool(self):
        cache = _CountingCache(_snapshot(STATE_ALLOWLIST, users=["u1"]))
        with patch.object(service, "cache_get", cache):
            ctx = activation.new_context(user_id="u1", kind=activation.KIND_REQUEST)
            token = activation.set_context(ctx)
            try:
                assert activation.package_active(PKG)

                def in_thread():
                    return activation.current_context(), activation.package_active(PKG)

                seen, active = await run_in_threadpool(in_thread)
            finally:
                activation.reset_context(token)
        assert seen is ctx
        assert active is True
        assert cache.reads == 1

    def test_unavailable_snapshot_uses_the_defaults(self):
        registry.register_master_flag(PKG, "fake", STATE_EVERYONE)
        with patch.object(service, "cache_get", return_value=None), patch.object(
            activation, "_session", side_effect=RuntimeError("db down")
        ):
            with activation.use_context(inherit=False):
                assert activation.package_active(PKG)


class TestCeleryPropagation:
    def test_header_round_trip(self):
        with activation.use_context(user_id="u1", inherit=False):
            headers = {}
            activation._before_task_publish(
                sender="tasks.x", body=((), {"project_id": "p1"}, {}), headers=headers
            )
        assert headers[activation.CELERY_HEADER] == {"user_id": "u1", "project_id": "p1"}

        request = types.SimpleNamespace(**{activation.CELERY_HEADER: headers[activation.CELERY_HEADER]})
        ctx = activation.context_from_task(request, {})
        assert (ctx.user_id, ctx.project_id, ctx.kind) == ("u1", "p1", activation.KIND_TASK)

    def test_header_keeps_an_explicit_value_and_skips_empty_context(self):
        headers = {activation.CELERY_HEADER: {"user_id": "x", "project_id": None}}
        with activation.use_context(user_id="u1", inherit=False):
            activation._before_task_publish(body=((), {}, {}), headers=headers)
        assert headers[activation.CELERY_HEADER]["user_id"] == "x"
        empty = {}
        token = activation.set_context(None)
        try:
            activation._before_task_publish(body=((), {}, {}), headers=empty)
        finally:
            activation.reset_context(token)
        assert empty == {}

    def test_task_kwargs_and_system_fallback(self):
        ctx = activation.context_from_task(types.SimpleNamespace(), {"user_id": "u5"})
        assert (ctx.user_id, ctx.kind) == ("u5", activation.KIND_TASK)
        ctx = activation.context_from_task(None, {})
        assert (ctx.user_id, ctx.project_id, ctx.kind) == (None, None, activation.KIND_SYSTEM)

    def test_celery_publish_carries_the_header(self):
        from celery import Celery

        activation.install_publish_signal()
        app = Celery("t", broker="memory://", backend="cache+memory://")
        captured = {}

        from celery.signals import before_task_publish

        def _capture(headers=None, **_):
            captured.update(headers or {})

        before_task_publish.connect(_capture, weak=False)
        try:
            with activation.use_context(user_id="u7", inherit=False):
                app.send_task("tasks.noop", kwargs={"project_id": "p7"})
        finally:
            before_task_publish.disconnect(_capture)
        assert captured.get(activation.CELERY_HEADER) == {"user_id": "u7", "project_id": "p7"}


class TestWorkerAttrGating:
    @pytest.fixture
    def fake_workers(self, monkeypatch):
        pkg = types.ModuleType(PKG)
        pkg.__file__ = f"/fake/{PKG}/__init__.py"
        workers = types.ModuleType(f"{PKG}.workers")
        workers.get_grading_block_fn = lambda: "block"
        workers.get_notification_brand_host_fn = lambda: "brand"
        workers.get_something_new_fn = lambda: "new"
        monkeypatch.setitem(sys.modules, PKG, pkg)
        monkeypatch.setitem(sys.modules, f"{PKG}.workers", workers)
        monkeypatch.setenv("BENGER_EXTENSIONS", PKG)
        extension_registry.reset()
        yield
        extension_registry.reset()

    def test_classes_are_pinned(self):
        always = {
            "get_grading_dispatch_policy_fn",
            "get_batch_evaluation_policy_fn",
            "get_grading_finalize_fn",
            "get_grading_block_fn",
            "get_name_visibility_fns",
        }
        for attr in always:
            assert extension_registry.worker_attr_gating(attr) == activation.ALWAYS
        for attr in (
            "get_notification_brand_host_fn",
            "get_falloesung_compute_fn",
            "get_falloesung_bulk_compute_fn",
            "get_inline_judge",
            "anything_else",
        ):
            assert extension_registry.worker_attr_gating(attr) == activation.GATED

    def test_master_off_skips_gated_getters_only(self, fake_workers):
        with _with_snapshot(_snapshot(STATE_OFF)):
            with activation.use_context(user_id="u1", inherit=False):
                assert [n for n, _ in extension_registry.worker_attrs("get_grading_block_fn")] == [PKG]
                assert extension_registry.worker_attrs("get_notification_brand_host_fn") == []
                assert extension_registry.first_worker_attr("get_something_new_fn") is None
        with _with_snapshot(_snapshot(STATE_EVERYONE)):
            with activation.use_context(user_id="u1", inherit=False):
                assert extension_registry.first_worker_attr(
                    "get_notification_brand_host_fn", call=True
                ) == "brand"
