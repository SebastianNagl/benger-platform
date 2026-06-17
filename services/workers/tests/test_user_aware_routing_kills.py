"""Mutation-kill / pinning tests for the PROVIDER ROUTING in
``ai_services/user_aware_ai_service.py``.

WHY THIS FILE EXISTS
--------------------
``UserAwareAIService.get_ai_service_for_user`` (and its thin alias
``get_ai_service_for_model``) is the single point that turns a *provider
string* + the invoking user's stored API key into the concrete
``UserSpecific*`` service object that will actually run a generation.

On a research-grade benchmarking platform the worst silent failure here
is a **mis-route**: a provider string mapped to the WRONG ``UserSpecific*``
class means the wrong vendor's SDK/key/base-url is used for a model, so a
generation is attributed to (and billed against) the wrong provider — and
nothing downstream can tell, because the Generation row only records the
provider *name* we claimed, not which client truly ran. The second-worst
failure is a key-propagation bug: the returned service silently carries a
*global* key instead of THIS user's key, so one user's quota/identity is
used for another's benchmark run.

The routing logic is only exercised incidentally by the orchestration
integration tests (which patch ``get_ai_service_for_user`` wholesale via
``conftest.patch_ai_service``), so the contract below was never pinned
directly. This file pins it.

THE EXACT CONTRACT (hand-read from source, 2026-06-17)
------------------------------------------------------
``get_ai_service_for_user(db, user_id, provider, organization_id=None)``:

1. Resolve a key. With no ``organization_id`` it calls
   ``user_api_key_service.get_user_api_key(db, user_id, provider)`` — THIS
   is the seam we mock (the DB/decryption is behind it). With an
   ``organization_id`` it tries ``org_api_key_service.resolve_api_key(...)``.
2. If the resolved key is falsy → return ``None`` (NOT a keyless service).
3. Map ``provider.lower()`` through ``service_class_map`` to one of the
   seven ``UserSpecific*`` classes. Unknown provider → return ``None``.
   The match is **case-insensitive** (``provider.lower()``) and is an
   **exact dict-key lookup** — NOT a prefix/substring match.
4. Instantiate ``cls(user_api_key)`` — the user's key lands on
   ``service.api_key`` — and stamp four audit attrs:
   ``_key_resolution_route`` / ``_provider_name`` (== ``provider.lower()``)
   / ``_invocation_user_id`` / ``_invocation_organization_id``.

``get_ai_service_for_model(db, user_id, model_provider)`` just delegates to
``get_ai_service_for_user(db, user_id, model_provider)`` — its third arg is
a PROVIDER string, despite the ``model_*`` name. The model-id→provider
mapping happens upstream (worker/catalog), not in this module, so we pin it
on representative provider strings for every provider the platform offers.

ENV NOTE: importing ``user_aware_ai_service`` eagerly imports every
``UserSpecific*`` subclass (pulling provider SDKs) and constructs the
module-level ``EncryptionService`` singleton, which refuses to start
without a key/sentinel. The workers ``conftest.py`` already sets
``BENGER_TEST_MODE=1``, but we belt-and-braces the documented env vars at
the very TOP — BEFORE the import — so the file is runnable in isolation.
"""

from __future__ import annotations

import os

# --- MUST run before importing the module under test (see module docstring) ---
os.environ.setdefault("ENCRYPTION_KEY", "dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcw==")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("BENGER_TEST_MODE", "1")

from unittest.mock import MagicMock  # noqa: E402

import pytest  # noqa: E402

# Import the SUBMODULE object (not just the symbols) so we can monkeypatch
# the key-resolution seam exactly where the routing code looks it up. The
# routing module binds ``user_api_key_service`` by name at import time
# (``from user_api_key_service import user_api_key_service``), so the seam to
# replace is ``uaas_mod.user_api_key_service`` — patching the source singleton
# elsewhere would NOT be seen by the routing code.
#
# NB: ``from ai_services import user_aware_ai_service`` does NOT give the
# submodule — ``ai_services/__init__.py`` rebinds that name to the
# ``UserAwareAIService`` *instance* (``from .user_aware_ai_service import
# user_aware_ai_service``), shadowing the submodule. We import the module via
# its dotted path and grab it from ``sys.modules`` to be unambiguous.
import ai_services.user_aware_ai_service  # noqa: E402,F401
import sys  # noqa: E402

uaas_mod = sys.modules["ai_services.user_aware_ai_service"]
from ai_services.user_aware_ai_service import (  # noqa: E402
    UserAwareAIService,
    UserSpecificAnthropicService,
    UserSpecificCohereService,
    UserSpecificDeepInfraService,
    UserSpecificGoogleService,
    UserSpecificGrokService,
    UserSpecificMistralService,
    UserSpecificOpenAIService,
)


# A sentinel key value that is unmistakably "this user's key", so a
# global-vs-user key bug is visible: we assert the returned service carries
# THIS exact string on ``.api_key``.
USER_KEY = "sk-user-specific-DEADBEEF-0123456789"

# (provider-string-as-seen-by-caller, expected UserSpecific* class).
# Provider strings are intentionally varied in case to also pin the
# case-insensitivity contract (provider.lower() lookup). Each row stands in
# for "a model of this vendor was requested": e.g. an OpenAI model (gpt-*),
# an Anthropic model (claude-*), a Google model (gemini-*), a Mistral model,
# a Grok model (xAI), a Cohere model (command-*), a DeepInfra-hosted model
# (DeepSeek/Qwen/Llama/Kimi/GLM/...).
PROVIDER_TO_CLASS = [
    ("openai", UserSpecificOpenAIService),
    ("anthropic", UserSpecificAnthropicService),
    ("google", UserSpecificGoogleService),
    ("mistral", UserSpecificMistralService),
    ("grok", UserSpecificGrokService),
    ("cohere", UserSpecificCohereService),
    ("deepinfra", UserSpecificDeepInfraService),
]


@pytest.fixture()
def patched_key_service(monkeypatch):
    """Mock the key-resolution seam so routing is deterministic + offline.

    Replaces ``get_user_api_key`` on the singleton the routing module
    actually consults (``uaas_mod.user_api_key_service``) with a stub that
    returns ``USER_KEY`` for any (db, user_id, provider). No DB, no
    decryption, no network. Returns a recorder so tests can assert the
    provider string was forwarded verbatim to the key lookup.
    """
    calls = []

    def _fake_get_user_api_key(db, user_id, provider):
        calls.append((user_id, provider))
        return USER_KEY

    monkeypatch.setattr(
        uaas_mod.user_api_key_service,
        "get_user_api_key",
        _fake_get_user_api_key,
    )
    return calls


@pytest.fixture()
def svc():
    return UserAwareAIService()


# ---------------------------------------------------------------------------
# MODEL/PROVIDER → CORRECT PROVIDER CLASS
# ---------------------------------------------------------------------------
class TestProviderRoutesToCorrectClass:
    """Each provider string must map to its OWN ``UserSpecific*`` class.

    A row mapped to a sibling class is the headline mis-route bug: the wrong
    vendor SDK/key/base-url runs the generation. Asserting exact ``__class__``
    identity (not ``isinstance``, which would pass for a shared base) kills
    any mutation that swaps one ``service_class_map`` value for another.
    """

    @pytest.mark.parametrize("provider, expected_cls", PROVIDER_TO_CLASS)
    def test_get_ai_service_for_user_routes_to_right_class(
        self, svc, patched_key_service, provider, expected_cls
    ):
        service = svc.get_ai_service_for_user(MagicMock(), "user-1", provider)

        assert service is not None, f"{provider!r} routed to None with a valid key"
        # Exact class identity — not a base-class isinstance — so a
        # value-swap in service_class_map cannot pass.
        assert type(service) is expected_cls, (
            f"provider {provider!r} mis-routed to {type(service).__name__}, "
            f"expected {expected_cls.__name__}"
        )
        assert service.__class__.__name__ == expected_cls.__name__

    @pytest.mark.parametrize("provider, expected_cls", PROVIDER_TO_CLASS)
    def test_get_ai_service_for_model_delegates_identically(
        self, svc, patched_key_service, provider, expected_cls
    ):
        """``get_ai_service_for_model`` is a pass-through alias; its third
        positional arg is the PROVIDER string. Pin that it routes the same
        as the user variant (kills a mutation that drops/rewrites the
        delegation)."""
        service = svc.get_ai_service_for_model(MagicMock(), "user-1", provider)
        assert type(service) is expected_cls, (
            f"get_ai_service_for_model({provider!r}) mis-routed to "
            f"{type(service).__name__}"
        )

    def test_no_two_providers_share_a_class(self, svc, patched_key_service):
        """Defense-in-depth against a map mutation that points two distinct
        providers at the SAME class (which the per-row tests could miss if
        the duplicated class happened to be the expected one for both)."""
        classes = {}
        for provider, _expected in PROVIDER_TO_CLASS:
            service = svc.get_ai_service_for_user(MagicMock(), "u", provider)
            classes[provider] = type(service)
        # Seven providers → seven distinct classes.
        assert len(set(classes.values())) == len(PROVIDER_TO_CLASS), (
            f"provider→class map collapsed two providers onto one class: {classes}"
        )


# ---------------------------------------------------------------------------
# USER-KEY PROPAGATION (no global-key leak)
# ---------------------------------------------------------------------------
class TestUserKeyPropagation:
    """The returned service must carry THIS user's resolved key, and the
    four Phase-6.5 audit attrs must reflect the real route/provider/user."""

    @pytest.mark.parametrize("provider, expected_cls", PROVIDER_TO_CLASS)
    def test_service_carries_the_users_key(
        self, svc, patched_key_service, provider, expected_cls
    ):
        service = svc.get_ai_service_for_user(MagicMock(), "user-42", provider)
        # Every UserSpecific* __init__ stores the passed key on .api_key
        # (regardless of whether SDK client construction succeeded with a
        # fake key). A global-key bug would show a different value here.
        assert service.api_key == USER_KEY, (
            f"{provider!r} service did not carry the user's key; "
            f"got {service.api_key!r}"
        )

    def test_provider_forwarded_verbatim_to_key_lookup(self, svc, patched_key_service):
        """The provider string the caller passed must be the one handed to
        the key resolver — a model's provider mustn't be silently rewritten
        before the key is fetched (that would fetch the wrong vendor's key)."""
        svc.get_ai_service_for_user(MagicMock(), "user-7", "anthropic")
        assert ("user-7", "anthropic") in patched_key_service

    def test_audit_attributes_stamped(self, svc, patched_key_service):
        service = svc.get_ai_service_for_user(MagicMock(), "user-9", "OpenAI")
        # _provider_name is the lower-cased provider, NOT the raw input.
        assert service._provider_name == "openai"
        assert service._invocation_user_id == "user-9"
        assert service._invocation_organization_id is None
        # No org context → route is the plain user-key route.
        assert service._key_resolution_route == "user_key"


# ---------------------------------------------------------------------------
# CASE-INSENSITIVITY + EXACT (non-prefix) MATCH AT A PROVIDER BOUNDARY
# ---------------------------------------------------------------------------
class TestMatchSemantics:
    """The lookup is ``provider.lower()`` against EXACT dict keys."""

    @pytest.mark.parametrize(
        "raw_provider, expected_cls",
        [
            ("OpenAI", UserSpecificOpenAIService),
            ("OPENAI", UserSpecificOpenAIService),
            ("Anthropic", UserSpecificAnthropicService),
            ("ANTHROPIC", UserSpecificAnthropicService),
            ("Google", UserSpecificGoogleService),
            ("Mistral", UserSpecificMistralService),
            ("Grok", UserSpecificGrokService),
            ("Cohere", UserSpecificCohereService),
            ("DeepInfra", UserSpecificDeepInfraService),
        ],
    )
    def test_case_insensitive_match(
        self, svc, patched_key_service, raw_provider, expected_cls
    ):
        """Mixed/upper case must route the same as lowercase (kills a
        mutation that drops the ``.lower()``)."""
        service = svc.get_ai_service_for_user(MagicMock(), "u", raw_provider)
        assert type(service) is expected_cls, (
            f"{raw_provider!r} did not case-fold to {expected_cls.__name__}"
        )

    def test_prefix_is_not_a_match(self, svc, patched_key_service):
        """A string that is a PREFIX of (or contains) a real provider key,
        but is not an exact key, must NOT route — proving the lookup is an
        exact dict-key match, not ``startswith``/substring. ``'open'`` is a
        prefix of ``'openai'``; a substring matcher would mis-route it to
        OpenAI. Boundary chosen to distinguish two providers: ``'co'`` is a
        prefix of ``'cohere'`` too."""
        assert svc.get_ai_service_for_user(MagicMock(), "u", "open") is None
        assert svc.get_ai_service_for_user(MagicMock(), "u", "openai-chat") is None
        assert svc.get_ai_service_for_user(MagicMock(), "u", "co") is None
        assert svc.get_ai_service_for_user(MagicMock(), "u", "anthropic-claude") is None

    def test_surrounding_whitespace_is_not_trimmed(self, svc, patched_key_service):
        """The code does not ``.strip()`` — a provider with stray whitespace
        is NOT an exact key and routes to None. Pinning this documents the
        real (strict) behavior so a future ``.strip()`` is a deliberate,
        test-visible change rather than silent."""
        assert svc.get_ai_service_for_user(MagicMock(), "u", " openai") is None


# ---------------------------------------------------------------------------
# UNKNOWN PROVIDER + MISSING KEY → DOCUMENTED None (never a wrong service)
# ---------------------------------------------------------------------------
class TestNoSilentMisroute:
    def test_unknown_provider_returns_none(self, svc, patched_key_service):
        """An unrecognized provider must return None — never a default/first
        provider. A key IS available here (key service mocked), so this
        isolates the provider-map miss from the no-key path."""
        for unknown in ("", "zhipu", "openai2", "claude", "gpt", "unknown"):
            assert (
                svc.get_ai_service_for_user(MagicMock(), "u", unknown) is None
            ), f"unknown provider {unknown!r} did not return None"

    @pytest.mark.parametrize("provider, _expected_cls", PROVIDER_TO_CLASS)
    def test_missing_user_key_returns_none(self, svc, monkeypatch, provider, _expected_cls):
        """No stored key for the user → return None (the worker then records
        a key-missing failure). The service is NOT constructed keyless."""
        monkeypatch.setattr(
            uaas_mod.user_api_key_service,
            "get_user_api_key",
            lambda db, user_id, provider: None,
        )
        assert svc.get_ai_service_for_user(MagicMock(), "u", provider) is None

    def test_empty_string_key_returns_none(self, svc, monkeypatch):
        """An empty-string key is falsy → None, same as a missing key. Kills
        a mutation that flips the ``if not user_api_key`` guard."""
        monkeypatch.setattr(
            uaas_mod.user_api_key_service,
            "get_user_api_key",
            lambda db, user_id, provider: "",
        )
        assert svc.get_ai_service_for_user(MagicMock(), "u", "openai") is None

    def test_key_resolver_exception_returns_none(self, svc, monkeypatch):
        """If key resolution raises, the broad try/except yields None — the
        worker must not get a half-built service. Pin the swallow so a
        mutation removing the guard surfaces as a behavior change."""
        def _boom(db, user_id, provider):
            raise RuntimeError("decrypt failed")

        monkeypatch.setattr(
            uaas_mod.user_api_key_service, "get_user_api_key", _boom
        )
        assert svc.get_ai_service_for_user(MagicMock(), "u", "openai") is None


# ---------------------------------------------------------------------------
# ORG-CONTEXT KEY PATH (org resolver consulted, route recorded)
# ---------------------------------------------------------------------------
class TestOrgContextPath:
    """With an ``organization_id`` the org key resolver is consulted and the
    recorded ``_key_resolution_route`` reflects the org decision — while the
    provider→class routing is unchanged."""

    def test_org_resolved_route_and_correct_class(self, svc, monkeypatch):
        org_service = MagicMock()
        org_service.resolve_api_key.return_value = USER_KEY
        # The routing code does ``from shared_org_api_key_service import
        # org_api_key_service`` INSIDE the org branch, so patch the source
        # module attribute it imports.
        import shared_org_api_key_service as org_mod
        monkeypatch.setattr(org_mod, "org_api_key_service", org_service)

        service = svc.get_ai_service_for_user(
            MagicMock(), "user-1", "anthropic", organization_id="org-xyz"
        )
        assert type(service) is UserSpecificAnthropicService
        assert service.api_key == USER_KEY
        assert service._key_resolution_route == "org_resolved"
        assert service._invocation_organization_id == "org-xyz"
        org_service.resolve_api_key.assert_called_once()

    def test_org_resolver_returns_no_key_returns_none(self, svc, monkeypatch):
        """Org resolver yields no key → the ``if not user_api_key`` guard
        still returns None (no keyless service), even though org context was
        honored."""
        org_service = MagicMock()
        org_service.resolve_api_key.return_value = None
        import shared_org_api_key_service as org_mod
        monkeypatch.setattr(org_mod, "org_api_key_service", org_service)

        service = svc.get_ai_service_for_user(
            MagicMock(), "user-1", "openai", organization_id="org-xyz"
        )
        assert service is None
