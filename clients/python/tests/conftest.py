from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from benger_client import BengerClient

BASE = "https://api.test.example"
KEY = "bgr_test_k3Yx9Q2a_s3cr3tS3cr3tS3cr3t"


class Router:
    """A tiny request router for httpx.MockTransport that records calls."""

    def __init__(self) -> None:
        self.routes: list[tuple[str, str, Callable[[httpx.Request], httpx.Response]]] = []
        self.calls: list[httpx.Request] = []

    def add(self, method: str, url_prefix: str, handler) -> None:
        if not callable(handler):
            payload = handler

            def handler(_req, payload=payload):
                return httpx.Response(200, json=payload)

        self.routes.append((method.upper(), url_prefix, handler))

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        url = str(request.url.copy_with(query=None))
        for method, prefix, handler in self.routes:
            if request.method == method and (url == prefix or url == BASE + prefix):
                return handler(request)
        return httpx.Response(404, json={"detail": f"no mock for {request.method} {url}"})

    def bodies(self, method: str, path: str) -> list:
        out = []
        for r in self.calls:
            if r.method == method and str(r.url.copy_with(query=None)) == BASE + path:
                out.append(json.loads(r.content) if r.content else None)
        return out


@pytest.fixture
def router() -> Router:
    return Router()


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def client(router: Router, sleeps: list[float]) -> BengerClient:
    c = BengerClient(api_key=KEY, base_url=BASE, transport=httpx.MockTransport(router))
    c._sleep = sleeps.append
    yield c
    c.close()
