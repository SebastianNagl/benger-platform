"""The platform flag registry and evaluation rules (core 2.42): owners,
master flags, owner coupling, the anonymous rule, and a registry sync that
never deletes."""

from __future__ import annotations

import pytest
from sqlalchemy.sql.dml import Delete

from feature_flags import registry, service
from feature_flags.registry import (
    PLATFORM_OWNER,
    STATE_ALLOWLIST,
    STATE_EVERYONE,
    STATE_OFF,
    FlagDefinition,
)


@pytest.fixture(autouse=True)
def _isolated_registry():
    yield
    registry.unregister_flags("benger_fake")
    registry.unregister_flags("benger_other")
    registry.reset_master_flags()


def _fake_flags(*names, default=STATE_EVERYONE):
    registry.register_flags(
        "benger_fake", [FlagDefinition(n, f"{n} description", default) for n in names]
    )


class TestRegistry:
    def test_public_api_is_a_platform_flag(self):
        assert registry.flag("public_api") is not None
        assert registry.flag_owner("public_api") == PLATFORM_OWNER

    def test_owner_conflicts_are_refused(self):
        _fake_flags("fake_one")
        with pytest.raises(ValueError):
            registry.register_flags(
                "benger_other", [FlagDefinition("fake_one", "x", STATE_OFF)]
            )
        # Same owner again replaces the definition.
        registry.register_flags("benger_fake", [FlagDefinition("fake_one", "new", STATE_OFF)])
        assert registry.flag("fake_one").description == "new"

    def test_invalid_state_is_refused(self):
        with pytest.raises(ValueError):
            registry.register_flags("benger_fake", [FlagDefinition("bad", "x", "sometimes")])
        assert registry.flag("bad") is None

    def test_master_flag_belongs_to_the_package(self):
        name = registry.register_master_flag("benger_fake", "fake", STATE_OFF)
        assert name == "extension.fake"
        assert registry.flag_owner(name) == "benger_fake"
        assert registry.is_master(name)
        assert registry.master_for_owner("benger_fake") == name
        assert registry.master_for_owner(PLATFORM_OWNER) is None
        # The master flag is not coupled to itself.
        assert registry.coupled_master(name) is None

    def test_default_state_from_the_package_or_the_fallback(self):
        class Pkg:
            DEFAULT_RUNTIME_STATE = "allowlist"

        assert registry.master_default_state("benger_fake", Pkg) == STATE_ALLOWLIST
        assert registry.master_default_state("benger_extended", object()) == STATE_EVERYONE
        assert registry.master_default_state("benger_compliance", object()) == STATE_OFF

        class Bad:
            DEFAULT_RUNTIME_STATE = "maybe"

        with pytest.raises(ValueError):
            registry.master_default_state("benger_fake", Bad)

    def test_reset_master_flags_keeps_the_package_flags(self):
        _fake_flags("fake_one")
        registry.register_master_flag("benger_fake", "fake", STATE_OFF)
        registry.reset_master_flags()
        assert registry.flag("extension.fake") is None
        assert registry.flag("fake_one") is not None


class TestEvaluation:
    def _eval(self, snapshot, names, user_id=None, orgs=()):
        return service.evaluate_names(snapshot, names, user_id, lambda: set(orgs))

    def test_anonymous_callers_get_everyone_only(self):
        _fake_flags("fake_on", "fake_list")
        snapshot = {
            "fake_on": {"state": STATE_EVERYONE, "users": [], "orgs": []},
            "fake_list": {"state": STATE_ALLOWLIST, "users": ["u1"], "orgs": ["o1"]},
        }
        assert self._eval(snapshot, ["fake_on", "fake_list"]) == {
            "fake_on": True,
            "fake_list": False,
        }
        assert self._eval(snapshot, ["fake_list"], "u1") == {"fake_list": True}
        assert self._eval(snapshot, ["fake_list"], "u2", orgs=["o1"]) == {"fake_list": True}
        assert self._eval(snapshot, ["fake_list"], "u2", orgs=["o2"]) == {"fake_list": False}

    def test_owner_coupling(self):
        _fake_flags("fake_on")
        master = registry.register_master_flag("benger_fake", "fake", STATE_OFF)
        snapshot = {
            "fake_on": {"state": STATE_EVERYONE, "users": [], "orgs": []},
            master: {"state": STATE_OFF, "users": [], "orgs": []},
        }
        assert self._eval(snapshot, ["fake_on", master], "u1") == {
            "fake_on": False,
            master: False,
        }
        snapshot[master] = {"state": STATE_ALLOWLIST, "users": ["u1"], "orgs": []}
        assert self._eval(snapshot, ["fake_on"], "u1") == {"fake_on": True}
        assert self._eval(snapshot, ["fake_on"], "u2") == {"fake_on": False}
        # The platform's flags are never coupled.
        assert registry.coupled_master("public_api") is None

    def test_missing_entries_fall_back_to_the_registered_default(self):
        _fake_flags("fake_on")
        registry.register_master_flag("benger_fake", "fake", STATE_EVERYONE)
        assert self._eval({}, ["fake_on", "unknown"]) == {"fake_on": True, "unknown": False}

    def test_extensions_view(self):
        master = registry.register_master_flag("benger_fake", "fake", STATE_OFF)
        assert service.extensions_view({master: True}) == {"fake": True}


class TestSync:
    def test_sync_never_deletes(self):
        _fake_flags("fake_on")
        statements = service._sync_statements()
        assert statements
        assert not any(isinstance(stmt, Delete) for stmt in statements)

    def test_invalidation_drops_the_legacy_key(self, mock_redis):
        mock_redis.set(service.SNAPSHOT_KEY, "{}")
        mock_redis.set(service.LEGACY_SNAPSHOT_KEY, "{}")
        service.invalidate_cache()
        assert mock_redis.get(service.SNAPSHOT_KEY) is None
        assert mock_redis.get(service.LEGACY_SNAPSHOT_KEY) is None
