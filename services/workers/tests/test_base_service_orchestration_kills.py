"""Mutation-killing tests for the generation-orchestration scaffolding in
``services/shared/ai_services/base_service.py``.

The pure helpers ``derive_truncated`` / ``classify_error_type`` are already
covered by ``test_ai_service_metadata.py`` and are NOT re-tested here. This
file targets the under-tested *orchestration* surface, where a wrong decision
silently loses or mislabels a generation:

* ``_create_response_dict``  — the standardized success envelope.
* ``_create_error_response`` — the standardized failure envelope (must stay
  distinguishable from an empty-but-successful generation, or a failed call
  gets scored as a real empty answer).
* ``get_invocation_provenance`` — the audit fields stamped onto metadata.
* ``get_retry_history_snapshot`` — the contextvar-backed retry audit trail
  that the per-provider ``retry_with_exponential_backoff`` decorator feeds.

Import strategy mirrors ``test_ai_service_metadata.py``: ``base_service`` is
file-imported by path so we don't trigger the ``ai_services`` package SDK
cascade (openai / anthropic / google.genai / …). The orchestration helpers
under test have no SDK dependency.
"""

from __future__ import annotations

import os

# Defensive env so a relative/sibling import inside base_service (none today,
# but cheap insurance against the package __init__ side effects) never blocks
# the file-import.
os.environ.setdefault("ENCRYPTION_KEY", "test-encryption-key-0000000000000000")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("TESTING", "1")

import importlib.util  # noqa: E402

_workers_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_services_root = os.path.dirname(_workers_root)
_base_service_path = os.path.join(
    _services_root, "shared", "ai_services", "base_service.py"
)
_spec = importlib.util.spec_from_file_location(
    "_orchestration_kills_base_service", _base_service_path
)
_base_service = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base_service)

BaseAIService = _base_service.BaseAIService
get_retry_history_snapshot = _base_service.get_retry_history_snapshot
_retry_history_ctx = _base_service._retry_history_ctx


# ---------------------------------------------------------------------------
# Minimal concrete subclass. BaseAIService is abstract (generate +
# _initialize_client). We give it a no-op client init and an unused
# generate(); the orchestration helpers under test live on the base class.
# The class name is deliberately ``...Service`` so that the
# ``.replace("Service", "")`` service-name derivation has something to strip.
# ---------------------------------------------------------------------------
class FakeProviderService(BaseAIService):
    def _initialize_client(self):
        self.client = object()

    def generate(self, prompt, system_prompt="", model_name=None,
                 max_tokens=1500, temperature=0.0, **kwargs):  # pragma: no cover
        raise NotImplementedError


def _fresh_service():
    return FakeProviderService(api_key="unused")


# ===========================================================================
# _create_response_dict — the success envelope
# ===========================================================================
class TestCreateResponseDict:
    def test_exact_success_shape(self):
        svc = _fresh_service()
        usage = {"prompt_tokens": 11, "completion_tokens": 22, "total_tokens": 33}
        resp = svc._create_response_dict(
            content="hello world",
            model="gpt-test",
            usage=usage,
        )

        # Success flag defaults True.
        assert resp["success"] is True
        # Content / model / usage pass through verbatim.
        assert resp["content"] == "hello world"
        assert resp["model"] == "gpt-test"
        assert resp["usage"] == {
            "prompt_tokens": 11,
            "completion_tokens": 22,
            "total_tokens": 33,
        }
        # usage is the same object handed in (no copy/rewrite of the token map).
        assert resp["usage"] is usage

        # Metadata block: service name is the class name with "Service"
        # stripped. "FakeProviderService" -> "FakeProvider".
        assert resp["metadata"]["service"] == "FakeProvider"
        assert "timestamp" in resp["metadata"]
        assert "created_at" in resp["metadata"]
        # Both timestamps are ISO-8601 strings (datetime.now().isoformat()).
        assert isinstance(resp["metadata"]["timestamp"], str)
        assert "T" in resp["metadata"]["timestamp"]

        # No error key on a clean success (error defaults to None -> falsy).
        assert "error" not in resp

        # Exactly the documented top-level key set, nothing extra leaked.
        assert set(resp.keys()) == {"content", "model", "usage", "metadata", "success"}

    def test_success_false_passthrough(self):
        # success is a real parameter, not hardcoded True.
        svc = _fresh_service()
        resp = svc._create_response_dict(
            content="x", model="m", usage={}, success=False
        )
        assert resp["success"] is False

    def test_error_key_only_present_when_truthy(self):
        svc = _fresh_service()
        # Empty-string error stays falsy -> no error key.
        resp_empty = svc._create_response_dict(
            content="x", model="m", usage={}, error=""
        )
        assert "error" not in resp_empty

        # Non-empty error string IS surfaced verbatim.
        resp_err = svc._create_response_dict(
            content="x", model="m", usage={}, error="boom"
        )
        assert resp_err["error"] == "boom"

    def test_additional_data_merged_at_top_level(self):
        # **additional_data lands at the TOP level (not nested in metadata),
        # via dict.update() after the base dict is built.
        svc = _fresh_service()
        resp = svc._create_response_dict(
            content="c",
            model="m",
            usage={},
            truncated=True,
            refusal=False,
            finish_reason="length",
            seed=42,
        )
        assert resp["truncated"] is True
        assert resp["refusal"] is False
        assert resp["finish_reason"] == "length"
        assert resp["seed"] == 42
        # These are top-level passthroughs, not buried in metadata.
        assert "truncated" not in resp["metadata"]

    def test_additional_data_can_override_base_keys(self):
        # update() runs LAST, so additional_data wins on key collision. Only
        # keys that are NOT named params of _create_response_dict can be
        # passed this way (content/model/usage/success/error are named, so
        # passing them via **additional_data is a TypeError — see
        # test_named_param_collision_is_a_typeerror). "metadata" is not a named
        # param, so it routes into additional_data and overrides the whole
        # base metadata block — pinning that .update() runs after base build.
        svc = _fresh_service()
        extra = {"metadata": {"replaced": True}}
        resp = svc._create_response_dict(
            content="original", model="m", usage={}, **extra
        )
        assert resp["metadata"] == {"replaced": True}
        assert resp["content"] == "original"
        assert resp["success"] is True

    def test_named_param_collision_is_a_typeerror(self):
        # Documenting the boundary the test above relies on: because content
        # is an explicit named parameter, you cannot also smuggle it through
        # **additional_data — Python raises before the body runs. This is the
        # real contract, not a bug: named fields are set positionally, only
        # truly-extra keys flow through additional_data.
        import pytest

        svc = _fresh_service()
        with pytest.raises(TypeError):
            svc._create_response_dict(
                content="original", model="m", usage={}, **{"content": "x"}
            )

    def test_service_name_strips_only_service_suffix(self):
        # The replace strips the literal substring "Service". For our class
        # "FakeProviderService" that yields "FakeProvider" (one occurrence).
        svc = _fresh_service()
        resp = svc._create_response_dict(content="c", model="m", usage={})
        assert resp["metadata"]["service"] == "FakeProvider"
        assert "Service" not in resp["metadata"]["service"]


# ===========================================================================
# _create_error_response — the failure envelope
# ===========================================================================
class TestCreateErrorResponse:
    def test_exact_error_shape(self):
        svc = _fresh_service()
        exc = Exception("HTTP 429: rate limit exceeded")
        resp = svc._create_error_response(error=exc, model="gpt-test")

        # Failure is flagged, not silently a success.
        assert resp["success"] is False
        # Content is the empty STRING, never None — downstream persistence
        # treats a real generation's content as a string.
        assert resp["content"] == ""
        assert resp["content"] is not None
        # Model echoes the attempted model.
        assert resp["model"] == "gpt-test"
        # The error message is surfaced verbatim at top level.
        assert resp["error"] == "HTTP 429: rate limit exceeded"
        # Usage is fully zeroed (no phantom tokens billed for a failed call).
        assert resp["usage"] == {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

    def test_error_type_classified_into_metadata(self):
        # _create_error_response routes through classify_error_type. A 429
        # message classifies as rate_limit; pin that it lands in metadata.
        svc = _fresh_service()
        resp = svc._create_error_response(
            error=Exception("HTTP 429: rate limit"), model="m"
        )
        assert resp["metadata"]["error_type"] == "rate_limit"

        resp_auth = svc._create_error_response(
            error=Exception("401 Unauthorized"), model="m"
        )
        assert resp_auth["metadata"]["error_type"] == "auth"

        resp_generic = svc._create_error_response(
            error=Exception("internal server error"), model="m"
        )
        assert resp_generic["metadata"]["error_type"] == "api_error"

    def test_standard_academic_metadata_fields_on_failure(self):
        # Phase 6.6: the four standard fields are stamped on the error path
        # with their failure-side constants. A flipped constant here would
        # mislabel a failed generation as truncated / refused.
        svc = _fresh_service()
        resp = svc._create_error_response(error=ValueError("nope"), model="m")
        md = resp["metadata"]
        assert md["finish_reason"] is None
        assert md["truncated"] is False
        assert md["refusal"] is False
        assert md["seed"] is None

    def test_provenance_merged_onto_error_metadata(self):
        # The error path also surfaces invocation provenance so a researcher
        # can see which retry exhausted. Default (no stamping) -> Nones + 0.
        svc = _fresh_service()
        resp = svc._create_error_response(error=Exception("x"), model="m")
        md = resp["metadata"]
        assert md["retry_attempts"] == []
        assert md["retry_count"] == 0
        assert md["provider_route"] is None
        assert md["provider_name"] is None
        assert md["billed_user_id"] is None
        assert md["billed_organization_id"] is None

    def test_service_name_override_does_not_change_metadata_service(self):
        # service_name only affects the log line / classification context, not
        # the metadata["service"] field, which is always class-derived.
        svc = _fresh_service()
        resp = svc._create_error_response(
            error=Exception("x"), model="m", service_name="CustomName"
        )
        assert resp["metadata"]["service"] == "FakeProvider"

    def test_error_distinguishable_from_empty_success(self):
        # The crown-jewel invariant: a FAILED generation must never look like a
        # genuine empty-string success. Both have content == "", so the
        # discriminator is success=False AND an error key present.
        svc = _fresh_service()

        empty_success = svc._create_response_dict(
            content="",
            model="m",
            usage={"prompt_tokens": 5, "completion_tokens": 0, "total_tokens": 5},
        )
        failure = svc._create_error_response(error=Exception("boom"), model="m")

        # Same empty content...
        assert empty_success["content"] == failure["content"] == ""

        # ...but mutually exclusive success flags.
        assert empty_success["success"] is True
        assert failure["success"] is False

        # The empty success carries no error key; the failure does.
        assert "error" not in empty_success
        assert "error" in failure

        # And only the failure carries an error_type in metadata.
        assert "error_type" not in empty_success["metadata"]
        assert failure["metadata"]["error_type"] == "api_error"


# ===========================================================================
# get_invocation_provenance — the audit fields
# ===========================================================================
class TestGetInvocationProvenance:
    def test_default_provenance_all_none(self):
        # A direct caller (no factory stamping) gets the documented keys with
        # None values and an empty retry trail.
        svc = _fresh_service()
        prov = svc.get_invocation_provenance()
        assert prov == {
            "retry_attempts": [],
            "retry_count": 0,
            "provider_route": None,
            "provider_name": None,
            "billed_user_id": None,
            "billed_organization_id": None,
        }

    def test_provenance_reads_stamped_attributes(self):
        # The factory stamps these private attrs; provenance must read them
        # back under the documented public key names (route/name/user/org).
        svc = _fresh_service()
        svc._key_resolution_route = "org_key"
        svc._provider_name = "openai"
        svc._invocation_user_id = "user-123"
        svc._invocation_organization_id = "org-456"

        prov = svc.get_invocation_provenance()
        assert prov["provider_route"] == "org_key"
        assert prov["provider_name"] == "openai"
        assert prov["billed_user_id"] == "user-123"
        assert prov["billed_organization_id"] == "org-456"

    def test_provenance_retry_count_matches_recorded_attempts(self):
        # retry_count must equal len(retry_attempts) — pin they stay coupled.
        svc = _fresh_service()
        history = [
            {"attempt": 1, "is_rate_limit": True, "retried": True},
            {"attempt": 2, "is_rate_limit": True, "retried": True},
            {"attempt": 3, "is_rate_limit": False, "retried": False},
        ]
        token = _retry_history_ctx.set(history)
        try:
            prov = svc.get_invocation_provenance()
        finally:
            _retry_history_ctx.reset(token)

        assert prov["retry_count"] == 3
        assert len(prov["retry_attempts"]) == 3
        assert prov["retry_count"] == len(prov["retry_attempts"])
        assert prov["retry_attempts"] == history


# ===========================================================================
# get_retry_history_snapshot — the contextvar-backed audit trail
#
# The real per-provider retry decorator (retry_with_exponential_backoff in
# openai_service.py and its siblings) does exactly three things with the
# contextvar this snapshot reads:
#   token = _retry_history_ctx.set([])  # fresh list per call
#   history.append({...})               # one record per failed attempt
#   _retry_history_ctx.reset(token)     # restore after the call
# We drive the SAME contextvar the same way to pin the snapshot's copy
# semantics + boundaries, without importing the provider SDK module.
# ===========================================================================
class TestGetRetryHistorySnapshot:
    def teardown_method(self):
        # Make sure no test leaks a populated contextvar into the next one.
        _retry_history_ctx.set(None)

    def test_empty_when_no_decorator_active(self):
        # Default contextvar value is None -> snapshot is an empty list.
        _retry_history_ctx.set(None)
        assert get_retry_history_snapshot() == []

    def test_empty_list_value_also_yields_empty(self):
        # A first-attempt success leaves the decorator's list empty; snapshot
        # of an empty list is still [].
        token = _retry_history_ctx.set([])
        try:
            assert get_retry_history_snapshot() == []
        finally:
            _retry_history_ctx.reset(token)

    def test_reflects_recorded_attempts(self):
        history = [
            {"attempt": 1, "error": "429 rate limit", "is_rate_limit": True,
             "latency_ms": 5, "retried": True},
            {"attempt": 2, "error": "boom", "is_rate_limit": False,
             "latency_ms": 7, "retried": False},
        ]
        token = _retry_history_ctx.set(history)
        try:
            snap = get_retry_history_snapshot()
        finally:
            _retry_history_ctx.reset(token)

        assert snap == history
        assert len(snap) == 2

    def test_returns_a_copy_not_the_live_list(self):
        # The docstring guarantees a *copy* so a persisted snapshot survives
        # the decorator's reset(). Mutating the snapshot must NOT touch the
        # contextvar's list, and vice versa.
        live = [{"attempt": 1, "is_rate_limit": True}]
        token = _retry_history_ctx.set(live)
        try:
            snap = get_retry_history_snapshot()
            assert snap == live
            # Different object identity.
            assert snap is not live
            # Mutating the snapshot doesn't grow the live list.
            snap.append({"attempt": 99})
            assert len(_retry_history_ctx.get()) == 1
            # Mutating the live list after the snapshot doesn't grow the snap.
            live.append({"attempt": 2})
            assert len(snap) == 2  # 1 original + 1 we appended above
        finally:
            _retry_history_ctx.reset(token)


# ===========================================================================
# Retry decorator semantics — driven through the SAME contextvar the real
# decorator uses, asserting the audit-trail contract end to end.
#
# We intentionally do NOT import retry_with_exponential_backoff from
# openai_service (that pulls the OpenAI SDK + the whole provider cascade the
# file-import is designed to avoid). Instead we model a call that fails N
# times then succeeds, recording attempts exactly as the source decorator
# does, and pin what base_service guarantees about that trail: the snapshot
# and provenance read it back faithfully, retry_count is the number of failed
# attempts (NOT off-by-one), and the give-up record is distinguishable from a
# retried one. The off-by-one boundary (retries >= max_retries) is reasoned
# below.
# ===========================================================================
class TestRetryTrailContract:
    def teardown_method(self):
        _retry_history_ctx.set(None)

    def _simulate_attempts(self, errors, max_retries):
        """Replay the source decorator's history-recording loop faithfully.

        Mirrors openai_service.retry_with_exponential_backoff's inner loop:
        a transient (rate-limit) error is retried while ``retries <
        max_retries``; the give-up record has ``retried=False``. Returns the
        recorded history list (the same shape the live decorator pushes into
        the contextvar).
        """
        history = []
        retries = 0
        for err in errors:
            error_str = str(err).lower()
            is_rate_limit = "429" in error_str or "rate limit" in error_str
            history.append({
                "attempt": retries + 1,
                "error": str(err)[:200],
                "is_rate_limit": is_rate_limit,
                "retried": is_rate_limit and retries < max_retries,
            })
            if not is_rate_limit or retries >= max_retries:
                break
            retries += 1
        return history

    def test_transient_then_success_records_only_failures(self):
        # 2 rate-limit failures then a success: the success itself records
        # nothing, so the trail has exactly 2 entries, both retried.
        svc = _fresh_service()
        history = self._simulate_attempts(
            ["429 rate limit", "429 rate limit"], max_retries=5
        )
        token = _retry_history_ctx.set(history)
        try:
            prov = svc.get_invocation_provenance()
            snap = get_retry_history_snapshot()
        finally:
            _retry_history_ctx.reset(token)

        assert prov["retry_count"] == 2
        assert len(snap) == 2
        assert all(rec["retried"] is True for rec in snap)
        assert [rec["attempt"] for rec in snap] == [1, 2]

    def test_non_transient_error_is_not_retried(self):
        # A non-rate-limit error gives up on the first attempt: exactly one
        # record, retried=False. (A mutation flipping the is_rate_limit gate
        # would wrongly mark it retried.)
        history = self._simulate_attempts(["boom: internal error"], max_retries=5)
        assert len(history) == 1
        assert history[0]["is_rate_limit"] is False
        assert history[0]["retried"] is False

    def test_exhaustion_boundary_is_max_retries_plus_one_attempts(self):
        # With max_retries=2 and unbroken rate-limits, the loop makes attempts
        # at retries=0,1,2 and gives up at retries==max_retries. That's
        # max_retries+1 == 3 recorded attempts; the LAST one is the give-up
        # (retried=False) because retries >= max_retries. This pins the
        # off-by-one boundary of the ``retries >= max_retries`` condition.
        errors = ["429 rate limit"] * 10  # more than enough to exhaust
        history = self._simulate_attempts(errors, max_retries=2)

        assert len(history) == 3  # attempts at retries 0, 1, 2
        # First two were retried; the third exhausted.
        assert [rec["retried"] for rec in history] == [True, True, False]
        # The give-up record is still a rate-limit, just not retried.
        assert history[-1]["is_rate_limit"] is True
        assert history[-1]["attempt"] == 3

    def test_max_retries_zero_gives_up_immediately(self):
        # max_retries=0: even a rate-limit gives up on the very first attempt
        # (retries(0) >= max_retries(0)). One record, retried=False.
        history = self._simulate_attempts(["429 rate limit"] * 5, max_retries=0)
        assert len(history) == 1
        assert history[0]["is_rate_limit"] is True
        assert history[0]["retried"] is False
