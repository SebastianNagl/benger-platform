"""Behavioral tests for OpenAICompatibleService (the BYOM generic client).

WHY THIS FILE EXISTS
--------------------
This client talks to USER-CONTROLLED endpoints, so its contract carries
security weight beyond the usual provider services:

- the remote server must receive ``endpoint_model_name``, never the
  ``custom-<uuid>`` PK;
- the Authorization header exists exactly when a credential exists
  (keyless local endpoints are a supported first-class case);
- cost comes from the row's per-million rates — the YAML cost cache never
  sees custom rows, so any regression here silently prices runs at 0;
- the base_url is re-resolved+validated (url_guard) at CALL time, the aiohttp
  connection is PINNED to the validated IPs (DNS-rebinding immunity), and
  redirects are refused — all load-bearing halves of the SSRF story;
- ``response_metadata`` must never contain the base_url (project exports
  embed it verbatim; shared results must not leak endpoint details).

All HTTP is faked at the module's ``aiohttp`` seam — no network.
"""

from __future__ import annotations

import os

# --- MUST run before importing the module under test ---
os.environ.setdefault("ENCRYPTION_KEY", "dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcw==")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("BENGER_TEST_MODE", "1")

import json  # noqa: E402
import sys  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

import pytest  # noqa: E402

import ai_services.openai_compatible_service  # noqa: E402,F401

ocs_mod = sys.modules["ai_services.openai_compatible_service"]
from ai_services.openai_compatible_service import OpenAICompatibleService  # noqa: E402

BASE_URL = "https://models.example.org/v1"
REMOTE_MODEL = "meta-llama/Llama-3.3-70B-Instruct"
PK = "custom-3f2b6a9e-0000-4111-8222-333344445555"
KEY = "ck-credential-000-DEADBEEF"
PINNED_IP = "203.0.113.7"


class _FakePinnedConnector:
    """Stand-in for url_guard.pinned_connector's return value; records the
    validated IPs it was handed so tests can assert the session was pinned."""

    last_ips = None

    def __init__(self, ips):
        self.ips = ips
        _FakePinnedConnector.last_ips = ips


def _fake_pinned_connector(ips):
    return _FakePinnedConnector(ips)


def _openai_response(content="Hallo!", prompt_tokens=100, completion_tokens=50,
                     finish_reason="stop"):
    return {
        "choices": [
            {"message": {"content": content}, "finish_reason": finish_reason}
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


class _FakeResponse:
    def __init__(self, status=200, json_data=None, text_data=""):
        self.status = status
        self._json = json_data if json_data is not None else {}
        self._text = text_data

    async def json(self):
        return self._json

    async def text(self):
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class _FakeSession:
    """Records post() kwargs (and the connector) on the class; returns the
    canned response."""

    last_call = None
    last_connector = None
    response = None

    def __init__(self, *args, **kwargs):
        _FakeSession.last_connector = kwargs.get("connector")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def post(self, url, headers=None, json=None, timeout=None, allow_redirects=True):
        _FakeSession.last_call = {
            "url": url,
            "headers": headers or {},
            "json": json,
            "allow_redirects": allow_redirects,
        }
        return _FakeSession.response


@pytest.fixture()
def fake_http(monkeypatch):
    fake_aiohttp = MagicMock()
    fake_aiohttp.ClientSession = _FakeSession
    fake_aiohttp.ClientTimeout = lambda total=None: total
    monkeypatch.setattr(ocs_mod, "aiohttp", fake_aiohttp)

    # Call-time SSRF resolve+validate: no-op by default returning one pinned IP;
    # pinned_connector is faked so the session's connector is inspectable and no
    # real aiohttp connector is built. Individual tests override.
    import url_guard

    monkeypatch.setattr(
        url_guard, "resolve_and_validate", lambda u, **k: (u, [PINNED_IP])
    )
    monkeypatch.setattr(url_guard, "pinned_connector", _fake_pinned_connector)

    monkeypatch.delenv("E2E_TEST_MODE", raising=False)
    _FakeSession.last_call = None
    _FakeSession.last_connector = None
    _FakePinnedConnector.last_ips = None
    _FakeSession.response = _FakeResponse(200, _openai_response())
    return _FakeSession


def _service(**overrides):
    kwargs = dict(
        base_url=BASE_URL,
        api_key=KEY,
        endpoint_model_name=REMOTE_MODEL,
        input_cost_per_million=5.0,
        output_cost_per_million=15.0,
        supports_seed=False,
    )
    kwargs.update(overrides)
    return OpenAICompatibleService(**kwargs)


def _walk_strings(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from _walk_strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _walk_strings(v)
    elif obj is not None:
        yield str(obj)


class TestRequestShape:
    def test_remote_model_is_endpoint_name_never_pk(self, fake_http):
        svc = _service()
        result = svc.generate("frage", "system", model_name=PK, max_tokens=64)
        assert result["success"] is True
        assert fake_http.last_call["json"]["model"] == REMOTE_MODEL
        assert PK not in json.dumps(fake_http.last_call["json"])
        assert fake_http.last_call["url"] == f"{BASE_URL}/chat/completions"

    def test_bearer_header_present_with_key(self, fake_http):
        _service().generate("q", "s", model_name=PK)
        assert fake_http.last_call["headers"]["Authorization"] == f"Bearer {KEY}"

    def test_no_auth_header_without_key(self, fake_http):
        _service(api_key=None).generate("q", "s", model_name=PK)
        assert "Authorization" not in fake_http.last_call["headers"]

    def test_keyless_service_is_available(self):
        assert _service(api_key=None).is_available() is True

    def test_seed_sent_only_when_supported(self, fake_http):
        _service(supports_seed=True).generate("q", "s", model_name=PK, seed=1234)
        assert fake_http.last_call["json"]["seed"] == 1234

        _service(supports_seed=False).generate("q", "s", model_name=PK, seed=1234)
        assert "seed" not in fake_http.last_call["json"]

    def test_redirects_disabled(self, fake_http):
        _service().generate("q", "s", model_name=PK)
        assert fake_http.last_call["allow_redirects"] is False


class TestCostAndMetadata:
    def test_cost_from_row_rates(self, fake_http):
        fake_http.response = _FakeResponse(
            200, _openai_response(prompt_tokens=1_000_000, completion_tokens=1_000_000)
        )
        result = _service().generate("q", "s", model_name=PK)
        assert result["metadata"]["cost_usd"] == pytest.approx(20.0)

    def test_cost_zero_without_rates(self, fake_http):
        result = _service(
            input_cost_per_million=None, output_cost_per_million=None
        ).generate("q", "s", model_name=PK)
        assert result["metadata"]["cost_usd"] == 0.0

    def test_metadata_never_leaks_base_url(self, fake_http):
        result = _service().generate("q", "s", model_name=PK)
        assert result["success"] is True
        for s in _walk_strings(result["metadata"]):
            assert BASE_URL not in s
            assert "base_url" != s

    def test_provider_and_route_stamped(self, fake_http):
        svc = _service()
        svc._key_resolution_route = "custom_model_user_credential"
        svc._provider_name = "custom"
        result = svc.generate("q", "s", model_name=PK)
        assert result["metadata"]["provider"] == "Custom"
        assert result["metadata"]["provider_route"] == "custom_model_user_credential"


class TestFailureModes:
    def test_redirect_response_refused(self, fake_http):
        fake_http.response = _FakeResponse(302)
        result = _service().generate("q", "s", model_name=PK)
        assert result["success"] is False
        assert "redirect" in result["error"].lower()

    def test_http_error_surfaced(self, fake_http):
        fake_http.response = _FakeResponse(500, text_data="kaputt")
        result = _service().generate("q", "s", model_name=PK)
        assert result["success"] is False
        assert "HTTP 500" in result["error"]

    def test_url_guard_rejection_blocks_call(self, fake_http, monkeypatch):
        import url_guard

        def _reject(url, **kwargs):
            raise ValueError("resolves to a private address")

        monkeypatch.setattr(url_guard, "resolve_and_validate", _reject)
        result = _service().generate("q", "s", model_name=PK)
        assert result["success"] is False
        assert "private address" in result["error"]
        assert fake_http.last_call is None  # no HTTP attempt was made


class TestSSRFPinning:
    """The outbound connection is pinned to the IPs resolve_and_validate
    approved — a hostile TTL-0 rebind can't retarget it to an internal host."""

    def test_session_connector_is_pinned_to_validated_ips(self, fake_http):
        _service().generate("q", "s", model_name=PK)
        # The connector handed to ClientSession is the pinned one, built from
        # exactly the IPs resolve_and_validate returned.
        assert isinstance(fake_http.last_connector, _FakePinnedConnector)
        assert _FakePinnedConnector.last_ips == [PINNED_IP]

    def test_url_keeps_hostname_never_the_pinned_ip(self, fake_http):
        # TLS/SNI correctness: the request URL still targets the hostname, so
        # SNI + cert verification use the hostname; only the connector routes
        # the socket to the pinned IP.
        _service().generate("q", "s", model_name=PK)
        assert fake_http.last_call["url"] == f"{BASE_URL}/chat/completions"
        assert PINNED_IP not in fake_http.last_call["url"]

    def test_allow_private_forwards_empty_ips_no_pinning(self, fake_http, monkeypatch):
        # Self-hoster bypass: resolve_and_validate returns [] and the service
        # forwards it (pinned_connector([]) is a default connector upstream).
        import url_guard

        monkeypatch.setattr(url_guard, "resolve_and_validate", lambda u, **k: (u, []))
        result = _service().generate("q", "s", model_name=PK)
        assert result["success"] is True
        assert _FakePinnedConnector.last_ips == []

    def test_redirects_still_disabled_with_pinning(self, fake_http):
        _service().generate("q", "s", model_name=PK)
        assert fake_http.last_call["allow_redirects"] is False


class TestStructuredOutput:
    SCHEMA = {
        "type": "object",
        "properties": {"note": {"type": "string"}, "punkte": {"type": "integer"}},
        "required": ["note", "punkte"],
    }

    def test_schema_injected_into_system_prompt(self, fake_http):
        fake_http.response = _FakeResponse(
            200, _openai_response(content='{"note": "gut", "punkte": 11}')
        )
        result = _service().generate_structured("q", "sys", self.SCHEMA, model_name=PK)
        assert result["success"] is True
        sent_system = fake_http.last_call["json"]["messages"][0]["content"]
        # The actual schema (not a literal placeholder) must reach the model.
        assert '"punkte"' in sent_system
        assert result["metadata"]["schema_validated"] is True
        assert json.loads(result["content"]) == {"note": "gut", "punkte": 11}

    def test_invalid_json_flagged_not_crashed(self, fake_http):
        fake_http.response = _FakeResponse(
            200, _openai_response(content="kein json hier")
        )
        result = _service().generate_structured("q", "sys", self.SCHEMA, model_name=PK)
        assert result["success"] is True
        assert result["metadata"]["validation_status"] in ("invalid", "extracted_only")
        assert result["metadata"]["schema_validated"] is False


class TestE2EMode:
    def test_mock_path_skips_http(self, fake_http, monkeypatch):
        monkeypatch.setenv("E2E_TEST_MODE", "true")
        result = _service().generate("q", "s", model_name=PK)
        assert result["success"] is True
        assert result["metadata"]["e2e_test_mode"] is True
        assert fake_http.last_call is None
