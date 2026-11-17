"""Every platform symbol the extended overlay imports in the worker image
still exists.

``tests/contracts/overlay_imports.json`` (the same document as the api
copy under services/api/tests/contracts/, duplicated because this container
mounts only services/workers and services/shared) lists each import in
``benger_extended`` that targets a platform module. The ``workers`` section
holds worker-only roots (``tasks``, ``ml_evaluation``, the worker
``database``); shared modules imported from ``benger_extended/workers/`` are
resolved here too, because they run in this image. sys.path is set up by
tests/conftest.py (workers root and services/shared first).

If an entry fails, either keep the symbol (or a compatible alias) or land the
matching change in benger-extended first, then regenerate the list there.
"""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path

import pytest

CONTRACT = Path(__file__).resolve().parent / "contracts" / "overlay_imports.json"
REGENERATE = "make update-overlay-surface PLATFORM_DIR=<path to benger-platform> (run in benger-extended)"
WORKER_IMPORTER_PREFIX = "benger_extended/workers/"

_WORKERS_ROOT = Path(__file__).resolve().parent.parent
_SHARED_DIR = Path("/shared") if os.path.isdir("/shared") else _WORKERS_ROOT.parent / "shared"


def _document() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def _is_shared(module: str) -> bool:
    root = module.split(".", 1)[0]
    return (_SHARED_DIR / root).is_dir() or (_SHARED_DIR / f"{root}.py").is_file()


def _worker_entries() -> list[dict]:
    doc = _document()
    shared_from_workers = [
        entry
        for entry in doc["api_shared"]
        if _is_shared(entry["module"])
        and any(importer.startswith(WORKER_IMPORTER_PREFIX) for importer in entry["importers"])
    ]
    return doc["workers"] + shared_from_workers


def resolve(module: str, name: str | None) -> None:
    """Import ``module`` and look up ``name`` the way ``from module import
    name`` does, including the fallback to a submodule of a package."""
    mod = importlib.import_module(module)
    if name is None or hasattr(mod, name):
        return
    try:
        importlib.import_module(f"{module}.{name}")
    except ModuleNotFoundError as exc:
        if exc.name != f"{module}.{name}":
            raise
        raise AttributeError(f"module {module!r} has no attribute {name!r}") from None


def test_contract_file_is_present_and_non_empty():
    assert CONTRACT.is_file(), f"{CONTRACT} is missing; regenerate it: {REGENERATE}"
    assert _document()["workers"], "the workers section is empty"


@pytest.mark.parametrize(
    "entry",
    _worker_entries(),
    ids=lambda e: e["module"] if e["name"] is None else f"{e['module']}:{e['name']}",
)
def test_overlay_import_resolves(entry):
    module, name = entry["module"], entry["name"]
    target = module if name is None else f"{module}:{name}"
    try:
        resolve(module, name)
    except (ImportError, AttributeError) as exc:
        importers = "\n  ".join(entry["importers"])
        pytest.fail(
            f"benger_extended imports {target}, which no longer resolves ({type(exc).__name__}: {exc}).\n"
            f"Importers:\n  {importers}\n"
            "Keep the symbol (or an alias) or change the extended importers first, then regenerate "
            f"tests/contracts/overlay_imports.json: {REGENERATE}"
        )
