#!/usr/bin/env python3
"""Write the public API snapshot files.

* ``docs/api-docs/openapi-v1.json``: the /api/v1 OpenAPI document (platform
  routes only), checked by ``tests/unit/test_v1_openapi_snapshot.py``.
* ``docs/public-api-scopes.md``: the scope table.
* ``docs/full-api-routes.md``: the access-key rule of every platform route
  outside /api/v1 (``app/core/key_routes.py``), checked by
  ``tests/unit/test_key_routes.py``.

Run ``make generate-public-api-docs`` (or this script from ``services/api``)
after changing a v1 route, schema or scope, and commit both files.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import warnings
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = API_DIR.parents[1]
SPEC_PATH = REPO_ROOT / "docs" / "api-docs" / "openapi-v1.json"
SCOPES_PATH = REPO_ROOT / "docs" / "public-api-scopes.md"
ROUTES_PATH = REPO_ROOT / "docs" / "full-api-routes.md"


def _bootstrap() -> None:
    """Import the app outside a deployment: test mode, no services, and
    placeholder secrets (only the route table is read)."""
    os.environ.setdefault("TESTING", "true")
    os.environ.setdefault("JWT_SECRET_KEY", "public-api-docs-generation-only")
    os.environ.setdefault("SECRET_KEY", "public-api-docs-generation-only")
    os.environ.setdefault("CELERY_BROKER_URL", "memory://")
    os.environ.setdefault("CELERY_RESULT_BACKEND", "cache+memory://")
    for path in (str(API_DIR.parent / "shared"), str(API_DIR)):
        if path not in sys.path:
            sys.path.insert(0, path)
    logging.disable(logging.WARNING)
    warnings.simplefilter("ignore")


def spec_text(spec: dict) -> str:
    return json.dumps(spec, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    _bootstrap()
    from main import app
    from routers.v1.docs import scopes_markdown, snapshot_spec
    from routers.v1.reference import routes_markdown

    SPEC_PATH.parent.mkdir(parents=True, exist_ok=True)
    SPEC_PATH.write_text(spec_text(snapshot_spec(app)), encoding="utf-8")
    SCOPES_PATH.write_text(scopes_markdown(), encoding="utf-8")
    ROUTES_PATH.write_text(routes_markdown(app), encoding="utf-8")
    for path in (SPEC_PATH, SCOPES_PATH, ROUTES_PATH):
        print(f"Wrote {path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
