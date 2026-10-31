"""OPEN-CORE CONTRACT TEST — platform-side extension loader / version handshake.

`extensions.load_extended()` is the gate that decides whether the extended
overlay loads. Its handshake logic is what CrashLoops a prod pod on a version
mismatch (with BENGER_REQUIRE_EXTENDED set) or silently degrades to the
community edition (without it). The extended repo already asserts its
COMPATIBLE_CORE_VERSIONS includes the platform version; this test exercises the
PLATFORM half — the actual branch behavior — which nothing covered before.

Community-edition runnable: a fake ``benger_extended`` module is injected into
sys.modules; no real extended package needed.
"""

import logging
import sys
import types

import pytest

import celery_queues
import extension_registry as registry
import extensions
from core_version import CORE_API_VERSION


def _fake_extended(compatible):
    mod = types.ModuleType("benger_extended")
    mod.COMPATIBLE_CORE_VERSIONS = list(compatible)
    # No get_field_type_registrations / get_routers: the loader guards on
    # hasattr, so a minimal module is enough to exercise the handshake.
    return mod


def _fake_package(
    name,
    *,
    compatible=(CORE_API_VERSION,),
    api_version=None,
    requires=None,
    hooks=None,
    ext_id=None,
    task_queues=None,
    scopes=None,
    v1_routers=None,
):
    """A stand-in extension package with the core 2.37 contract attributes."""
    mod = types.ModuleType(name)
    mod.__file__ = f"/fake/{name}/__init__.py"
    if compatible is not None:
        mod.COMPATIBLE_CORE_VERSIONS = list(compatible)
    if api_version is not None:
        mod.EXTENSION_API_VERSION = api_version
    if requires is not None:
        mod.REQUIRES_EXTENSIONS = requires
    if ext_id is not None:
        mod.EXTENSION_ID = ext_id
    if hooks is not None:
        mod.get_hooks = lambda: dict(hooks)
    if task_queues is not None:
        mod.get_task_queues = lambda: dict(task_queues)
    if scopes is not None:
        mod.get_api_scopes = lambda: dict(scopes)
    if v1_routers is not None:
        mod.get_v1_routers = lambda: list(v1_routers)
    return mod


@pytest.fixture(autouse=True)
def _reset_loader_state(monkeypatch):
    # load_extended() mutates a module global and the shared registry;
    # isolate each test.
    monkeypatch.setattr(extensions, "_extended", None, raising=False)
    monkeypatch.delenv("BENGER_REQUIRE_EXTENDED", raising=False)
    monkeypatch.delenv("BENGER_EXTENSIONS", raising=False)
    monkeypatch.delenv("BENGER_REQUIRE_EXTENSIONS", raising=False)
    registry.reset()
    yield
    registry.reset()
    extensions._extended = None


@pytest.fixture
def isolated_task_queues(monkeypatch):
    """Copies of the routing containers so registered fakes never leak."""
    monkeypatch.setattr(celery_queues, "TASK_QUEUES", dict(celery_queues.TASK_QUEUES))
    monkeypatch.setattr(
        celery_queues,
        "EXTENSION_REGISTERED_TASK_NAMES",
        set(celery_queues.EXTENSION_REGISTERED_TASK_NAMES),
    )
    monkeypatch.setattr(celery_queues, "_TASK_OWNERS", dict(celery_queues._TASK_OWNERS))


class TestVersionHandshake:
    def test_compatible_version_loads(self, monkeypatch):
        monkeypatch.setitem(
            sys.modules, "benger_extended", _fake_extended([CORE_API_VERSION])
        )
        assert extensions.load_extended() is True
        assert extensions._extended is not None

    def test_mismatch_without_require_degrades_to_community(self, monkeypatch):
        monkeypatch.setitem(
            sys.modules, "benger_extended", _fake_extended(["0.0-nope"])
        )
        # No BENGER_REQUIRE_EXTENDED → disable extended, run community, no raise.
        assert extensions.load_extended() is False
        assert extensions._extended is None

    def test_mismatch_with_require_raises(self, monkeypatch):
        monkeypatch.setitem(
            sys.modules, "benger_extended", _fake_extended(["0.0-nope"])
        )
        monkeypatch.setenv("BENGER_REQUIRE_EXTENDED", "true")
        with pytest.raises(RuntimeError, match="incompatible"):
            extensions.load_extended()

    def test_empty_namespace_package_degrades_to_community(self, monkeypatch):
        # A bare `benger_extended/` dir on sys.path (extended overlay not
        # mounted, e.g. the empty build-context dir) imports as a namespace
        # package: no __file__, no COMPATIBLE_CORE_VERSIONS, no routers.
        # It must NOT count as a loaded extended edition (2026-08-11: this
        # silently 404ed every extended route while logging "loaded").
        mod = types.ModuleType("benger_extended")
        mod.__path__ = ["/app/benger_extended"]
        monkeypatch.setitem(sys.modules, "benger_extended", mod)
        assert extensions.load_extended() is False
        assert extensions._extended is None

    def test_empty_namespace_package_with_require_raises(self, monkeypatch):
        mod = types.ModuleType("benger_extended")
        mod.__path__ = ["/app/benger_extended"]
        monkeypatch.setitem(sys.modules, "benger_extended", mod)
        monkeypatch.setenv("BENGER_REQUIRE_EXTENDED", "true")
        with pytest.raises(RuntimeError, match="namespace package"):
            extensions.load_extended()

    def test_import_failure_without_require_degrades(self, monkeypatch):
        def _boom(name):
            raise ImportError("no extended overlay in this build")

        monkeypatch.setattr(extensions.importlib, "import_module", _boom)
        assert extensions.load_extended() is False

    def test_import_failure_with_require_raises(self, monkeypatch):
        def _boom(name):
            raise ImportError("no extended overlay in this build")

        monkeypatch.setattr(extensions.importlib, "import_module", _boom)
        monkeypatch.setenv("BENGER_REQUIRE_EXTENDED", "true")
        with pytest.raises(RuntimeError, match="Refusing to start"):
            extensions.load_extended()


class TestHookGracefulNoOp:
    """Community edition (no extended loaded): every hook the platform calls
    must be a graceful no-op, never raise, and return its documented default.
    This is the other half of the hook contract — the extended repo asserts it
    REGISTERS the keys; this asserts the platform SURVIVES their absence."""

    def test_void_hooks_no_op_without_extended(self, monkeypatch):
        monkeypatch.setattr(extensions, "_extended", None, raising=False)
        # None of these should raise or do anything when extended is absent.
        assert extensions.on_annotation_created(None, "t", "u", "a", "p") is None
        assert extensions.on_draft_saved(None, "t", "u", "p", {}) is None
        assert extensions.run_after_eval_config_save(None, object(), {}) is None
        assert extensions.validate_signup(None, object()) is None

    def test_tasks_with_feedback_defaults_to_empty_set(self, monkeypatch):
        monkeypatch.setattr(extensions, "_extended", None, raising=False)
        assert extensions.tasks_with_feedback_for_user(None, "p", "u", ["t1"]) == set()
        # Empty input short-circuits to an empty set regardless.
        assert extensions.tasks_with_feedback_for_user(None, "p", "u", []) == set()


class TestConfiguredNames:
    def test_default_is_the_extended_package(self):
        assert registry.configured_names() == ["benger_extended"]
        assert registry.required_names() == []

    def test_list_is_ordered_trimmed_and_deduplicated(self, monkeypatch):
        monkeypatch.setenv("BENGER_EXTENSIONS", " benger_b , benger_a,,benger_b ")
        assert registry.configured_names() == ["benger_b", "benger_a"]

    def test_required_subset_comes_from_its_own_variable(self, monkeypatch):
        monkeypatch.setenv("BENGER_EXTENSIONS", "benger_a,benger_b")
        monkeypatch.setenv("BENGER_REQUIRE_EXTENSIONS", "benger_b")
        assert registry.required_names() == ["benger_b"]
        assert registry.requirement_source("benger_b") == "BENGER_REQUIRE_EXTENSIONS"
        assert registry.requirement_source("benger_a") is None

    def test_legacy_variable_requires_every_configured_package(self, monkeypatch):
        monkeypatch.setenv("BENGER_EXTENSIONS", "benger_a,benger_b")
        monkeypatch.setenv("BENGER_REQUIRE_EXTENDED", "true")
        assert registry.required_names() == ["benger_a", "benger_b"]
        assert registry.requirement_source("benger_a") == "BENGER_REQUIRE_EXTENDED"

    def test_empty_require_list_overrides_the_legacy_variable(self, monkeypatch):
        monkeypatch.setenv("BENGER_REQUIRE_EXTENDED", "true")
        monkeypatch.setenv("BENGER_REQUIRE_EXTENSIONS", "")
        assert registry.required_names() == []
        assert registry.requirement_source("benger_extended") is None

    def test_short_name_prefers_the_declared_id(self):
        assert registry.short_name("benger_compliance") == "compliance"
        assert registry.short_name("other_pkg") == "other_pkg"
        assert registry.short_name("benger_x", _fake_package("benger_x", ext_id="risky")) == "risky"


class TestMultiPackageLoading:
    def test_packages_load_in_configured_order(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "benger_b", _fake_package("benger_b"))
        monkeypatch.setitem(sys.modules, "benger_a", _fake_package("benger_a", ext_id="aa"))
        monkeypatch.setenv("BENGER_EXTENSIONS", "benger_b,benger_a")

        assert extensions.load_extended() is True
        assert registry.loaded_names() == ["benger_b", "benger_a"]
        assert [ext.short for ext in registry.loaded()] == ["b", "aa"]
        # benger_extended is not configured, so its alias stays empty.
        assert extensions._extended is None
        assert extensions.is_loaded("benger_a") is True
        assert extensions.is_loaded("benger_extended") is False
        assert extensions._packages() == [
            ("benger_b", sys.modules["benger_b"]),
            ("benger_a", sys.modules["benger_a"]),
        ]

    def test_extended_alias_and_hook_order(self, monkeypatch):
        extended = _fake_package("benger_extended")
        other = _fake_package("benger_other")
        monkeypatch.setitem(sys.modules, "benger_extended", extended)
        monkeypatch.setitem(sys.modules, "benger_other", other)
        # Configured after the other package, but it still comes first in
        # hook order: the alias is authoritative.
        monkeypatch.setenv("BENGER_EXTENSIONS", "benger_other,benger_extended")

        assert extensions.load_extended() is True
        assert extensions._extended is extended
        assert registry.loaded_names() == ["benger_other", "benger_extended"]
        assert [name for name, _ in extensions._packages()] == [
            "benger_extended",
            "benger_other",
        ]

    def test_load_all_is_idempotent(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "benger_extended", _fake_package("benger_extended"))
        first = registry.load_all()
        monkeypatch.setitem(sys.modules, "benger_extended", None)
        assert registry.load_all() == first
        assert registry.loaded_names() == ["benger_extended"]

    def test_namespace_guard_applies_per_package(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "benger_extended", _fake_package("benger_extended"))
        empty = types.ModuleType("benger_empty")
        empty.__path__ = ["/app/benger_empty"]
        monkeypatch.setitem(sys.modules, "benger_empty", empty)
        monkeypatch.setenv("BENGER_EXTENSIONS", "benger_extended,benger_empty")

        assert extensions.load_extended() is True
        assert registry.loaded_names() == ["benger_extended"]
        assert registry.rejected()["benger_empty"].reason == "namespace"

    def test_namespace_guard_raises_for_a_required_package(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "benger_extended", _fake_package("benger_extended"))
        empty = types.ModuleType("benger_empty")
        empty.__path__ = ["/app/benger_empty"]
        monkeypatch.setitem(sys.modules, "benger_empty", empty)
        monkeypatch.setenv("BENGER_EXTENSIONS", "benger_extended,benger_empty")
        monkeypatch.setenv("BENGER_REQUIRE_EXTENSIONS", "benger_empty")
        with pytest.raises(RuntimeError, match="namespace package.*BENGER_REQUIRE_EXTENSIONS"):
            extensions.load_extended()


class TestDependencies:
    def test_missing_dependency_rejects_the_dependent(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "benger_extended", None)
        monkeypatch.setitem(
            sys.modules,
            "benger_comp",
            _fake_package("benger_comp", requires={"benger_extended": ["1"]}),
        )
        monkeypatch.setenv("BENGER_EXTENSIONS", "benger_extended,benger_comp")

        assert extensions.load_extended() is False
        assert registry.loaded_names() == []
        assert registry.rejected()["benger_extended"].reason == "import"
        rejected = registry.rejected()["benger_comp"]
        assert rejected.reason == "dependency"
        assert "not loaded" in rejected.message

    def test_dependency_version_mismatch_rejects_the_dependent(self, monkeypatch):
        monkeypatch.setitem(
            sys.modules, "benger_extended", _fake_package("benger_extended", api_version="2")
        )
        monkeypatch.setitem(
            sys.modules,
            "benger_comp",
            _fake_package("benger_comp", requires={"benger_extended": ["1"]}),
        )
        monkeypatch.setenv("BENGER_EXTENSIONS", "benger_extended,benger_comp")

        assert extensions.load_extended() is True
        assert registry.loaded_names() == ["benger_extended"]
        rejected = registry.rejected()["benger_comp"]
        assert rejected.reason == "dependency"
        assert "EXTENSION_API_VERSION" in rejected.message and "'2'" in rejected.message

    def test_dependency_version_mismatch_raises_when_required(self, monkeypatch):
        monkeypatch.setitem(
            sys.modules, "benger_extended", _fake_package("benger_extended", api_version="2")
        )
        monkeypatch.setitem(
            sys.modules,
            "benger_comp",
            _fake_package("benger_comp", requires={"benger_extended": ["1"]}),
        )
        monkeypatch.setenv("BENGER_EXTENSIONS", "benger_extended,benger_comp")
        monkeypatch.setenv("BENGER_REQUIRE_EXTENSIONS", "benger_comp")
        with pytest.raises(RuntimeError, match="EXTENSION_API_VERSION.*BENGER_REQUIRE_EXTENSIONS"):
            extensions.load_extended()

    def test_satisfied_dependency_loads_the_dependent(self, monkeypatch):
        monkeypatch.setitem(
            sys.modules, "benger_extended", _fake_package("benger_extended", api_version="1")
        )
        monkeypatch.setitem(
            sys.modules,
            "benger_comp",
            _fake_package(
                "benger_comp", requires={"benger_extended": ["1", "2"]}, ext_id="compliance"
            ),
        )
        monkeypatch.setenv("BENGER_EXTENSIONS", "benger_extended,benger_comp")

        assert extensions.load_extended() is True
        assert registry.loaded_names() == ["benger_extended", "benger_comp"]
        assert registry.loaded()[1].short == "compliance"
        assert registry.loaded()[0].api_version == "1"
        assert registry.module("benger_comp") is sys.modules["benger_comp"]

    def test_dependency_must_come_first(self, monkeypatch):
        monkeypatch.setitem(
            sys.modules, "benger_extended", _fake_package("benger_extended", api_version="1")
        )
        monkeypatch.setitem(
            sys.modules,
            "benger_comp",
            _fake_package("benger_comp", requires={"benger_extended": ["1"]}),
        )
        monkeypatch.setenv("BENGER_EXTENSIONS", "benger_comp,benger_extended")

        assert extensions.load_extended() is True
        assert registry.loaded_names() == ["benger_extended"]
        assert "must come before" in registry.rejected()["benger_comp"].message


class TestRequiredSubset:
    def test_only_the_required_package_can_fail_the_start(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "benger_extended", _fake_package("benger_extended"))
        monkeypatch.setitem(
            sys.modules, "benger_opt", _fake_package("benger_opt", compatible=["0.0-nope"])
        )
        monkeypatch.setenv("BENGER_EXTENSIONS", "benger_extended,benger_opt")
        monkeypatch.setenv("BENGER_REQUIRE_EXTENSIONS", "benger_extended")

        assert extensions.load_extended() is True
        assert registry.loaded_names() == ["benger_extended"]
        assert registry.rejected()["benger_opt"].reason == "handshake"

        registry.reset()
        monkeypatch.setenv("BENGER_REQUIRE_EXTENSIONS", "benger_opt")
        with pytest.raises(RuntimeError, match="incompatible.*BENGER_REQUIRE_EXTENSIONS"):
            extensions.load_extended()

    def test_required_name_must_be_configured(self, monkeypatch):
        monkeypatch.setenv("BENGER_EXTENSIONS", "benger_extended")
        monkeypatch.setenv("BENGER_REQUIRE_EXTENSIONS", "benger_elsewhere")
        with pytest.raises(RuntimeError, match="benger_elsewhere"):
            extensions.load_extended()

    def test_legacy_variable_covers_every_configured_package(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "benger_extended", _fake_package("benger_extended"))
        monkeypatch.setitem(sys.modules, "benger_opt", None)
        monkeypatch.setenv("BENGER_EXTENSIONS", "benger_extended,benger_opt")
        monkeypatch.setenv("BENGER_REQUIRE_EXTENDED", "true")
        with pytest.raises(RuntimeError, match="BENGER_REQUIRE_EXTENDED.*Refusing to start"):
            extensions.load_extended()

    def test_empty_require_list_degrades_despite_the_legacy_variable(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "benger_extended", None)
        monkeypatch.setenv("BENGER_REQUIRE_EXTENDED", "true")
        monkeypatch.setenv("BENGER_REQUIRE_EXTENSIONS", "")
        assert extensions.load_extended() is False


class TestHookOwnership:
    def test_single_owner_conflict_raises_when_an_implementer_is_required(self, monkeypatch):
        hook = lambda sync_id: True  # noqa: E731
        monkeypatch.setitem(
            sys.modules,
            "benger_extended",
            _fake_package("benger_extended", hooks={"dispatch_lti_grade_sync": hook}),
        )
        monkeypatch.setitem(
            sys.modules,
            "benger_other",
            _fake_package("benger_other", hooks={"dispatch_lti_grade_sync": hook}),
        )
        monkeypatch.setenv("BENGER_EXTENSIONS", "benger_extended,benger_other")
        monkeypatch.setenv("BENGER_REQUIRE_EXTENSIONS", "benger_extended")
        with pytest.raises(RuntimeError, match="one implementer"):
            extensions.load_extended()

    def test_single_owner_conflict_warns_and_first_wins_when_optional(self, monkeypatch, caplog):
        calls = []
        monkeypatch.setitem(
            sys.modules,
            "benger_extended",
            _fake_package(
                "benger_extended",
                hooks={"dispatch_lti_grade_sync": lambda s: calls.append(("ext", s)) or True},
            ),
        )
        monkeypatch.setitem(
            sys.modules,
            "benger_other",
            _fake_package(
                "benger_other",
                hooks={"dispatch_lti_grade_sync": lambda s: calls.append(("other", s)) or True},
            ),
        )
        monkeypatch.setenv("BENGER_EXTENSIONS", "benger_extended,benger_other")
        with caplog.at_level(logging.WARNING, logger="extensions"):
            assert extensions.load_extended() is True
        assert "one implementer" in caplog.text
        assert extensions.dispatch_lti_grade_sync("s1") is True
        assert calls == [("ext", "s1")]

    def test_unknown_hook_keys_are_logged(self, monkeypatch, caplog):
        monkeypatch.setitem(
            sys.modules,
            "benger_extended",
            _fake_package("benger_extended", hooks={"no_such_hook": lambda: None}),
        )
        with caplog.at_level(logging.WARNING, logger="extensions"):
            assert extensions.load_extended() is True
        assert "no_such_hook" in caplog.text

    def test_hook_specs_cover_every_wrapper(self):
        implemented = set(extensions.HOOK_SPECS) - extensions.PENDING_HOOK_KEYS
        assert implemented == {
            "before_annotation_write",
            "on_annotation_created",
            "on_draft_saved",
            "after_eval_config_save",
            "validate_signup",
            "after_user_signup",
            "after_user_login",
            "on_ops_event",
            "tasks_with_feedback_for_user",
            "tasks_with_evaluation_for_user",
            "privacy_protected_member_ids",
            "lti_protected_org_ids",
            "task_grade_summaries_for_user",
            "dispatch_lti_grade_sync",
            "resend_all_lti_grades",
            "project_real_name_viewer",
            "project_real_name_user_ids",
            "projects_real_name_user_ids",
            "lti_anonymization_policy",
            "public_api_enabled",
        }
        assert extensions.PENDING_HOOK_KEYS <= set(extensions.HOOK_SPECS)
        assert set(extensions.HOOK_SPECS.values()) <= {
            extensions.CALL_ALL,
            extensions.CALL_ALL_ISOLATED,
            extensions.UNION,
            extensions.DICT_FIRST_WINS,
            extensions.SINGLE_OWNER,
        }


class TestPackageSurfaces:
    def test_api_scopes_and_v1_routers_are_collected(self, monkeypatch, caplog):
        monkeypatch.setitem(
            sys.modules,
            "benger_extended",
            _fake_package(
                "benger_extended",
                scopes={"a:read": {"description": "a"}},
                v1_routers=[("r1", {})],
            ),
        )
        monkeypatch.setitem(
            sys.modules,
            "benger_comp",
            _fake_package(
                "benger_comp",
                scopes={"a:read": {"description": "dup"}, "c:read": {"description": "c"}},
                v1_routers=[("r2", {"prefix": "/x"})],
            ),
        )
        monkeypatch.setenv("BENGER_EXTENSIONS", "benger_extended,benger_comp")
        assert extensions.load_extended() is True
        with caplog.at_level(logging.WARNING, logger="extensions"):
            scopes = extensions.get_api_scopes_all()
        assert scopes == {"a:read": {"description": "a"}, "c:read": {"description": "c"}}
        assert "a:read" in caplog.text
        collected = extensions.get_v1_routers_all()
        # Core 2.42: each overlay v1 router also carries the package's
        # runtime gate (require_extension_active_v1).
        assert [
            (router, {k: v for k, v in kwargs.items() if k != "dependencies"})
            for router, kwargs in collected
        ] == [("r1", {}), ("r2", {"prefix": "/x"})]
        assert [
            kwargs["dependencies"][0].dependency.__name__ for _router, kwargs in collected
        ] == [
            "require_extension_active_v1_benger_extended",
            "require_extension_active_v1_benger_comp",
        ]

    def test_community_edition_has_no_scopes_or_v1_routers(self):
        assert extensions.get_api_scopes_all() == {}
        assert extensions.get_v1_routers_all() == []

    def test_task_queues_are_registered_with_the_package_as_owner(
        self, monkeypatch, isolated_task_queues
    ):
        monkeypatch.setitem(
            sys.modules,
            "benger_comp",
            _fake_package("benger_comp", task_queues={"compx.run_suite": "evaluation"}),
        )
        monkeypatch.setenv("BENGER_EXTENSIONS", "benger_comp")
        assert extensions.load_extended() is True
        assert celery_queues.TASK_QUEUES["compx.run_suite"] == "evaluation"
        assert celery_queues.task_owner("compx.run_suite") == "benger_comp"
        assert "compx.run_suite" in celery_queues.EXTENSION_REGISTERED_TASK_NAMES

    def test_bad_task_queue_fails_a_required_package_only(
        self, monkeypatch, isolated_task_queues
    ):
        monkeypatch.setitem(
            sys.modules,
            "benger_comp",
            _fake_package("benger_comp", task_queues={"compx.run_suite": "no-such-queue"}),
        )
        monkeypatch.setenv("BENGER_EXTENSIONS", "benger_comp")
        assert extensions.load_extended() is True
        assert "compx.run_suite" not in celery_queues.TASK_QUEUES

        registry.reset()
        monkeypatch.setenv("BENGER_REQUIRE_EXTENSIONS", "benger_comp")
        with pytest.raises(RuntimeError, match="get_task_queues"):
            extensions.load_extended()
