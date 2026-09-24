"""
Unit tests for the size-capped body reader (services/shared/bounded_http.py).

Pure-unit: responses are fakes exposing ``content.iter_chunked`` like an
aiohttp StreamReader. One test runs against a real aiohttp server with a
gzip-compressed body to prove the cap counts DECOMPRESSED bytes.
"""

import asyncio
import gzip
import json

import pytest

from bounded_http import (
    ResponseTooLargeError,
    read_capped,
    read_capped_json,
    read_capped_text,
)


class _FakeStream:
    def __init__(self, chunks):
        self._chunks = list(chunks)
        self.bytes_read = 0

    async def iter_chunked(self, n):
        for chunk in self._chunks:
            self.bytes_read += len(chunk)
            yield chunk


class _FakeResponse:
    def __init__(self, chunks, content_length=None):
        self.content = _FakeStream(chunks)
        self.content_length = content_length


@pytest.mark.unit
class TestReadCapped:
    def test_under_cap_returns_all_bytes(self):
        resp = _FakeResponse([b"ab", b"cd", b"ef"])
        assert asyncio.run(read_capped(resp, 6)) == b"abcdef"

    def test_over_cap_raises_and_stops_reading(self):
        resp = _FakeResponse([b"a" * 10] * 100)
        with pytest.raises(ResponseTooLargeError) as excinfo:
            asyncio.run(read_capped(resp, 25))
        assert excinfo.value.limit == 25
        # Stopped on the chunk that crossed the cap, not at the end.
        assert resp.content.bytes_read == 30

    def test_declared_content_length_over_cap_rejected_before_reading(self):
        resp = _FakeResponse([b"x"], content_length=1000)
        with pytest.raises(ResponseTooLargeError):
            asyncio.run(read_capped(resp, 100))
        assert resp.content.bytes_read == 0

    def test_truncate_returns_head_without_error(self):
        resp = _FakeResponse([b"a" * 10] * 100, content_length=1000)
        out = asyncio.run(read_capped(resp, 25, truncate=True))
        assert out == b"a" * 25
        assert resp.content.bytes_read == 30

    def test_error_message_is_generic(self):
        resp = _FakeResponse([b"secret-host.example" * 100])
        with pytest.raises(ResponseTooLargeError) as excinfo:
            asyncio.run(read_capped(resp, 10))
        assert "secret-host" not in str(excinfo.value)
        assert "too large" in str(excinfo.value).lower()


@pytest.mark.unit
class TestDecoders:
    def test_json_under_cap_parses(self):
        payload = json.dumps({"data": [{"id": "m"}]}).encode()
        resp = _FakeResponse([payload[:5], payload[5:]])
        assert asyncio.run(read_capped_json(resp, 1024)) == {"data": [{"id": "m"}]}

    def test_json_over_cap_raises_typed_error(self):
        resp = _FakeResponse([b'{"a": "' + b"x" * 2000 + b'"}'])
        with pytest.raises(ResponseTooLargeError):
            asyncio.run(read_capped_json(resp, 1024))

    def test_bad_json_raises_value_error(self):
        resp = _FakeResponse([b"not json"])
        with pytest.raises(ValueError):
            asyncio.run(read_capped_json(resp, 1024))

    def test_text_decodes_invalid_utf8_without_raising(self):
        resp = _FakeResponse([b"ok \xff\xfe"])
        assert asyncio.run(read_capped_text(resp, 1024)).startswith("ok ")


@pytest.mark.unit
class TestRealAiohttpDecompression:
    """A small gzip body that inflates past the cap is rejected: the cap
    applies to decompressed bytes, which is what protects memory."""

    async def test_gzip_bomb_rejected(self):
        aiohttp = pytest.importorskip("aiohttp")
        from aiohttp import web

        inflated = 4 * 1024 * 1024
        compressed = gzip.compress(b"0" * inflated)
        assert len(compressed) < 64 * 1024

        async def handler(_request):
            return web.Response(
                body=compressed,
                headers={"Content-Encoding": "gzip", "Content-Type": "application/json"},
            )

        app = web.Application()
        app.router.add_get("/", handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://127.0.0.1:{port}/") as resp:
                    with pytest.raises(ResponseTooLargeError):
                        await read_capped(resp, 1024 * 1024)
                async with session.get(f"http://127.0.0.1:{port}/") as resp:
                    body = await read_capped(resp, inflated)
                    assert len(body) == inflated
        finally:
            await runner.cleanup()
