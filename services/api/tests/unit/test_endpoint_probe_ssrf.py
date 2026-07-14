"""SSRF pins for the two BYOM endpoint probes.

validate_openai_compatible_endpoint (user_api_key_service) and _chat_ping
(routers.custom_models) both talk to a USER-CONTROLLED base_url. The url_guard
only validates the host the caller supplied; if the probe followed a 3xx it
would be replayed to the redirect target (internal / cloud-metadata host),
bypassing the guard and turning the probe into an SSRF/port-scan oracle.

These tests pin the mitigation: allow_redirects=False is passed, and a 3xx
response is reported as a generic failure — never followed. They fail on the
pre-fix code, which omitted allow_redirects (aiohttp defaults True).
"""

import asyncio

import aiohttp
import pytest


class _FakeResponse:
    def __init__(self, status):
        self.status = status

    async def json(self):
        return {"data": []}

    async def text(self):
        return ""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _RecordingSession:
    """Captures the kwargs of the outbound call and returns a canned status."""

    last_kwargs = None
    status_code = 302

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def get(self, url, **kwargs):
        _RecordingSession.last_kwargs = kwargs
        return _FakeResponse(_RecordingSession.status_code)

    def post(self, url, **kwargs):
        _RecordingSession.last_kwargs = kwargs
        return _FakeResponse(_RecordingSession.status_code)


@pytest.fixture()
def recording_aiohttp(monkeypatch):
    monkeypatch.setattr(aiohttp, "ClientSession", _RecordingSession)
    _RecordingSession.last_kwargs = None
    _RecordingSession.status_code = 302
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
