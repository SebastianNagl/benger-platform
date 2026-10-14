"""The committed public API spec and scope table match the code.

On failure run ``make generate-public-api-docs`` and review the diff: a
removed or renamed field or operation is a breaking change and needs a new
API version (docs/public-api.md, "Versioning")."""

import json
from pathlib import Path

import pytest

from main import app
from routers.v1.docs import CANONICAL_SERVER_URL, scopes_markdown, snapshot_spec


def _docs_dir():
    """The repository's docs/ folder. The Docker test runner mounts only
    services/api; it finds the folder when ../docs is mounted at /docs."""
    parents = Path(__file__).resolve().parents
    # In the container the file sits at /app/tests/unit, three levels deep, so
    # the repository root (parents[4] in a checkout) does not exist there.
    repo_docs = [parents[4] / "docs"] if len(parents) > 4 else []
    for candidate in (*repo_docs, Path("/docs")):
        if (candidate / "api-docs").is_dir():
            return candidate
    return None


DOCS = _docs_dir()
needs_docs = pytest.mark.skipif(DOCS is None, reason="repository docs/ folder not mounted")
SPEC = DOCS / "api-docs" / "openapi-v1.json" if DOCS else None
SCOPES = DOCS / "public-api-scopes.md" if DOCS else None


@needs_docs
def test_committed_spec_matches_build():
    committed = json.loads(SPEC.read_text(encoding="utf-8"))
    built = json.loads(json.dumps(snapshot_spec(app)))
    assert committed == built, "run `make generate-public-api-docs` and commit the result"


@needs_docs
def test_committed_scope_table_matches_registry():
    assert SCOPES.read_text(encoding="utf-8") == scopes_markdown()


def test_spec_shape():
    spec = snapshot_spec(app)
    assert spec["info"]["title"] == "BenGER Public API"
    assert spec["info"]["version"] == "1.0.0"
    assert spec["servers"] == [{"url": CANONICAL_SERVER_URL}]
    assert spec["components"]["securitySchemes"]["accessKey"]["bearerFormat"] == (
        "bgr_<env>_<id>_<secret>"
    )
    paths = spec["paths"]
    assert all(p.startswith("/api/v1/") for p in paths)
    assert "/api/v1/openapi.json" not in paths and "/api/v1/docs" not in paths
    assert paths["/api/v1/me"]["get"]["x-benger-scopes"] == []
    assert paths["/api/v1/projects/{project_id}/tasks"]["get"]["x-benger-scopes"] == [
        "tasks:read"
    ]
    assert paths["/api/v1/projects/{project_id}/exports"]["post"]["x-benger-scopes"] == [
        "exports:read",
        "tasks:read_reference",
    ]


async def test_served_spec_and_swagger_ui(async_test_client, monkeypatch):
    from app.core.config import get_settings
    from routers.v1 import docs

    docs.reset_cache()
    monkeypatch.setattr(get_settings(), "public_api_url", "https://api.example.org/")
    r = await async_test_client.get("/api/v1/openapi.json")
    assert r.status_code == 200
    assert r.json()["servers"] == [{"url": "https://api.example.org"}]
    assert r.headers["access-control-allow-origin"] == "*"
    r = await async_test_client.get("/api/v1/docs")
    assert r.status_code == 200
    assert "/api/v1/openapi.json" in r.text
    docs.reset_cache()


def test_public_api_url_derivation():
    from app.core.config import Settings

    assert Settings(frontend_url="https://what-a-benger.net").public_api_base_url == (
        "https://api.what-a-benger.net"
    )
    assert Settings(frontend_url="https://www.example.org").public_api_base_url == (
        "https://api.example.org"
    )
    assert Settings(frontend_url="http://localhost:3000").public_api_base_url is None
    assert Settings(frontend_url="http://benger.localhost").public_api_base_url is None
    assert (
        Settings(public_api_url="https://x.test/", frontend_url="http://localhost").public_api_base_url
        == "https://x.test"
    )
