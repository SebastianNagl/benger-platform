#!/usr/bin/env python3
"""Machine-specific settings for the pilot tooling, kept out of tracked code.

Every setting resolves in this order: the environment variable, then the
git-ignored ``publications/Transformation/.pilot.local.json``, then the
default below. Keys of the local file:

  data_root      the data directory with the git-ignored inputs and outputs
                 (default: this checkout's publications/Transformation/data)
  org_id         the organisation whose API keys pay for pilot calls
                 (no default: paid runs need it)
  container      the dev worker container (default: benger-worker-1)
  extended_repo  the benger-extended checkout (default: next to this repo)

A worktree points ``data_root`` at the main checkout, because the ignored
data exists only there.

CLI (used by scripts/ops/pilot.sh): ``local_config.py get <key>`` prints the
value, or nothing when it is unset.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

PUB = Path(__file__).resolve().parent.parent
REPO = PUB.parent.parent
LOCAL_FILE = PUB / ".pilot.local.json"
ENV = {
    "data_root": "PILOT_DATA_ROOT",
    "org_id": "PILOT_ORG",
    "container": "PILOT_CONTAINER",
    "extended_repo": "PILOT_EXTENDED_REPO",
}
DEFAULTS: dict[str, Any] = {
    "data_root": str(PUB / "data"),
    "org_id": None,
    "container": "benger-worker-1",
    "extended_repo": str(REPO.parent / "benger-extended"),
}


def _local() -> dict[str, Any]:
    try:
        doc = json.loads(LOCAL_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(doc, dict):
        raise SystemExit(f"{LOCAL_FILE}: expected a JSON object")
    return doc


def setting(name: str, default: Any = None) -> Any:
    env = ENV.get(name)
    if env and os.environ.get(env):
        return os.environ[env]
    local = _local()
    if local.get(name) not in (None, ""):
        return local[name]
    return DEFAULTS.get(name, default) if default is None else default


def data_root() -> Path:
    return Path(str(setting("data_root"))).expanduser().resolve()


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] != "get" or argv[1] not in ENV:
        print(f"usage: local_config.py get <{'|'.join(ENV)}>", file=sys.stderr)
        return 2
    value = setting(argv[1])
    if value is not None:
        print(value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
