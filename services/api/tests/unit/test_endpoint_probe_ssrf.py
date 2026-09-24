"""SSRF pins for the two BYOM endpoint probes.

validate_openai_compatible_endpoint (user_api_key_service) and _chat_ping
(routers.custom_models) both talk to a USER-CONTROLLED base_url. The url_guard
only validates the host the caller supplied; if the probe followed a 3xx it
would be replayed to the redirect target (internal / cloud-metadata host),
bypassing the guard and turning the probe into an SSRF/port-scan oracle.

These tests pin two mitigations: allow_redirects=False is passed (a 3xx is
reported as a generic failure, never followed), and — DNS-rebinding immunity —
each probe re-resolves+validates base_url and PINS the aiohttp connection to
the validated IPs before connecting. url_guard is faked here so no real DNS
runs; the pinned connector is captured to assert the session was pinned.
"""

import asyncio

import aiohttp
import pytest

PINNED_IP = "203.0.113.9"


class _FakePinned:
    """Stand-in for url_guard.pinned_connector's return; records the IPs."""

    last_ips = None

    def __init__(self, ips):
        self.ips = ips
        _FakePinned.last_ips = ips


def _fake_pinned_connector(ips):
    return _FakePinned(ips)


class _FakeStream:
    """Stand-in for ``ClientResponse.content``; records bytes pulled."""

    def __init__(self, chunks):
        self._chunks = list(chunks)
        self.bytes_read = 0

    async def iter_chunked(self, n):
        for chunk in self._chunks:
            self.bytes_read += len(chunk)
            yield chunk


class _FakeResponse:
    def __init__(self, status, chunks=None):
        self.status = status
        self.content_length = None
        if chunks is None:
            chunks = [b'{"data": []}']
        self._raw = b"".join(chunks)
        self.content = _FakeStream(chunks)

    async def json(self):
        import json

        return json.loads(self._raw)

    async def text(self):
        return self._raw.decode()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _RecordingSession:
    """Captures the kwargs of the outbound call (and the connector) and
    returns a canned status."""

    last_kwargs = None
    last_connector = None
    status_code = 302

    def __init__(self, *a, **k):
        _RecordingSession.last_connector = k.get("connector")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    chunks = None
    last_response = None

    def _respond(self):
        resp = _FakeResponse(_RecordingSession.status_code, _RecordingSession.chunks)
        _RecordingSession.last_response = resp
        return resp

    def get(self, url, **kwargs):
        _RecordingSession.last_kwargs = kwargs
        return self._respond()

    def post(self, url, **kwargs):
        _RecordingSession.last_kwargs = kwargs
        return self._respond()


@pytest.fixture()
def recording_aiohttp(monkeypatch):
    monkeypatch.setattr(aiohttp, "ClientSession", _RecordingSession)

    # Fake the SSRF guard so no real DNS runs and the pinned connector is a
    # capturable stand-in (both probes call resolve_and_validate + pinned_connector).
    import url_guard

    monkeypatch.setattr(
        url_guard, "resolve_and_validate", lambda u, **k: (u, [PINNED_IP])
    )
    monkeypatch.setattr(url_guard, "pinned_connector", _fake_pinned_connector)

    _RecordingSession.last_kwargs = None
    _RecordingSession.last_connector = None
    _RecordingSession.status_code = 302
    _RecordingSession.chunks = None
    _RecordingSession.last_response = None
    _FakePinned.last_ips = None
    return _RecordingSession


def test_models_probe_disables_redirects_and_refuses_3xx(recording_aiohttp):
    from user_api_key_service import validate_openai_compatible_endpoint

    ok, message, error_type = asyncio.run(
        validate_openai_compatible_endpoint("https://models.example.org/v1")
    )
    # allow_redirects=False was passed to the outbound GET.
    assert recording_aiohttp.last_kwargs.get("allow_redirects") is False
    # The 302 was reported as a generic failure, not followed.
    assert ok is False
    assert error_type == "invalid_response"


def test_chat_ping_disables_redirects_and_refuses_3xx(recording_aiohttp):
    from routers.custom_models import _chat_ping

    result = asyncio.run(
        _chat_ping("https://models.example.org/v1", "llama-3-8b", "sk-key")
    )
    assert recording_aiohttp.last_kwargs.get("allow_redirects") is False
    assert result["status"] == "error"
    assert result["error_type"] == "invalid_response"


def test_models_probe_still_accepts_200(recording_aiohttp):
    from user_api_key_service import validate_openai_compatible_endpoint

    recording_aiohttp.status_code = 200
    ok, _message, error_type = asyncio.run(
        validate_openai_compatible_endpoint("https://models.example.org/v1")
    )
    assert ok is True
    assert error_type == "success"


def test_models_probe_pins_connector_to_validated_ips(recording_aiohttp):
    from user_api_key_service import validate_openai_compatible_endpoint

    recording_aiohttp.status_code = 200
    asyncio.run(validate_openai_compatible_endpoint("https://models.example.org/v1"))
    # The session was created with the pinned connector built from the
    # validated IPs — no re-resolution via live DNS.
    assert isinstance(recording_aiohttp.last_connector, _FakePinned)
    assert _FakePinned.last_ips == [PINNED_IP]


def test_chat_ping_pins_connector_to_validated_ips(recording_aiohttp):
    from routers.custom_models import _chat_ping

    recording_aiohttp.status_code = 200
    asyncio.run(_chat_ping("https://models.example.org/v1", "llama-3-8b", "sk-key"))
    assert isinstance(recording_aiohttp.last_connector, _FakePinned)
    assert _FakePinned.last_ips == [PINNED_IP]


def test_models_probe_rebinding_rejection_is_generic_unreachable(monkeypatch):
    # If resolve_and_validate now rejects (a rebind flipped the host to a
    # private IP between the caller's guard and this probe), the outcome is the
    # generic "unreachable" — never an oracle, and no HTTP is attempted.
    import url_guard
    from user_api_key_service import validate_openai_compatible_endpoint

    def _reject(url, **k):
        raise ValueError("resolves to 169.254.169.254")

    monkeypatch.setattr(url_guard, "resolve_and_validate", _reject)
    ok, _message, error_type = asyncio.run(
        validate_openai_compatible_endpoint("https://models.example.org/v1")
    )
    assert ok is False
    assert error_type == "unreachable"


# ---------------------------------------------------------------------------
# Body size cap: a user-controlled endpoint must not be able to make the api
# buffer an arbitrarily large (or decompression-bomb) body.
# ---------------------------------------------------------------------------

_MIB = b"x" * (1024 * 1024)


def _oversized_chunks():
    import bounded_http

    return [_MIB] * (bounded_http.PROBE_MAX_BODY_BYTES // len(_MIB) + 20)


def test_models_probe_rejects_oversized_body(recording_aiohttp):
    import bounded_http
    from user_api_key_service import validate_openai_compatible_endpoint

    recording_aiohttp.status_code = 200
    recording_aiohttp.chunks = _oversized_chunks()
    ok, message, error_type = asyncio.run(
        validate_openai_compatible_endpoint("https://models.example.org/v1")
    )
    assert ok is False
    assert error_type == "invalid_response"
    assert "too large" in message
    # Reading stopped right after crossing the cap.
    read = recording_aiohttp.last_response.content.bytes_read
    assert read <= bounded_http.PROBE_MAX_BODY_BYTES + len(_MIB)


def test_chat_ping_rejects_oversized_body(recording_aiohttp):
    import bounded_http
    from routers.custom_models import _chat_ping

    recording_aiohttp.status_code = 200
    recording_aiohttp.chunks = _oversized_chunks()
    result = asyncio.run(
        _chat_ping("https://models.example.org/v1", "llama-3-8b", "sk-key")
    )
    assert result["status"] == "error"
    assert result["error_type"] == "invalid_response"
    assert "too large" in result["message"]
    read = recording_aiohttp.last_response.content.bytes_read
    assert read <= bounded_http.PROBE_MAX_BODY_BYTES + len(_MIB)


def test_chat_ping_under_cap_succeeds(recording_aiohttp):
    from routers.custom_models import _chat_ping

    recording_aiohttp.status_code = 200
    recording_aiohttp.chunks = [b'{"choices": [', b'{"message": {"content": "pong"}}]}']
    result = asyncio.run(
        _chat_ping("https://models.example.org/v1", "llama-3-8b", "sk-key")
    )
    assert result["status"] == "success"
