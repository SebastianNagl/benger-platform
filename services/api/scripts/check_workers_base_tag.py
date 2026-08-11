#!/usr/bin/env python3
"""Guard: the workers base image tag is pinned in exactly one place.

``services/workers/Dockerfile`` builds ``FROM`` a CONTENT tag of workers-base
(e.g. ``:py313-cpu``); ``.github/workflows/build-workers-base.yml`` publishes
that same tag via its ``CONTENT_TAG`` env. Nothing but a comment keeps the two
in step, and the dangerous direction is SILENT:

* bump CONTENT_TAG only    -> the new base is published, the app still builds
  FROM the old tag, and every check stays green while shipping a stale base.
  That exact failure put a Python 3.11 + CUDA image on staging from a Python
  3.13 + CPU branch on 2026-08-11: pods healthy, pipeline green, wrong stack.
* bump the Dockerfile only -> the tag was never published, the pull fails, the
  build stops. Loud and self-correcting; not what this guards.

Also rejects a floating ``:latest``, which is the coupling this pinning
replaced — the base only rebuilds on the default branch, so ``:latest`` lets a
feature branch's app image silently resolve to whatever main last published.

Runs in CI (ci.yml "Python Lint" job) rather than pytest: the test containers
mount only ``services/workers`` and ``services/shared``, so neither the
Dockerfile's sibling workflow nor the repo root is reachable from them.

Usage:  python services/api/scripts/check_workers_base_tag.py
Exit 0 = in lockstep, 1 = drift (message explains which side to bump).
"""

from __future__ import annotations

import os
import re
import sys

_REPO = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
)
DOCKERFILE = os.path.join(_REPO, "services", "workers", "Dockerfile")
WORKFLOW = os.path.join(_REPO, ".github", "workflows", "build-workers-base.yml")
BASE_IMAGE = "ghcr.io/sebastiannagl/benger-platform/workers-base"


def _fail(msg: str) -> "None":
    print(f"::error::{msg}" if os.environ.get("GITHUB_ACTIONS") else f"ERROR: {msg}")
    sys.exit(1)


def dockerfile_base_tag() -> str:
    with open(DOCKERFILE, encoding="utf-8") as fh:
        for line in fh:
            m = re.match(r"^ARG\s+WORKERS_BASE_IMAGE=(\S+)", line)
            if m:
                ref = m.group(1)
                if not ref.startswith(BASE_IMAGE + ":"):
                    _fail(
                        f"WORKERS_BASE_IMAGE must point at {BASE_IMAGE} with an "
                        f"explicit tag, got {ref!r}"
                    )
                return ref.split(":", 1)[1]
    _fail(f"No 'ARG WORKERS_BASE_IMAGE=' line in {DOCKERFILE}")
    return ""  # unreachable


def workflow_content_tag() -> str:
    with open(WORKFLOW, encoding="utf-8") as fh:
        for line in fh:
            m = re.match(r"^\s*CONTENT_TAG:\s*(\S+)", line)
            if m:
                return m.group(1).strip("\"'")
    _fail(f"No 'CONTENT_TAG:' entry in {WORKFLOW}")
    return ""  # unreachable


def main() -> int:
    docker_tag = dockerfile_base_tag()
    workflow_tag = workflow_content_tag()

    if docker_tag == "latest":
        _fail(
            "services/workers/Dockerfile must pin a content tag, not ':latest'. "
            "A floating tag decouples the app image from the base its own branch "
            "declares — that is how a py3.13 branch shipped a py3.11 + CUDA image."
        )

    if docker_tag != workflow_tag:
        _fail(
            f"workers base tag drift: services/workers/Dockerfile builds FROM "
            f"'{BASE_IMAGE}:{docker_tag}' but build-workers-base.yml publishes "
            f"CONTENT_TAG='{workflow_tag}'. Bump BOTH in the same commit — "
            "otherwise the base rebuild lands on a tag nothing consumes and the "
            "app silently keeps building on the previous base."
        )

    print(f"workers-base tag in lockstep: {BASE_IMAGE}:{docker_tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
