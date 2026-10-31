"""Every platform symbol the extended overlay imports still exists.

``tests/contracts/overlay_imports.json`` lists each ``from X import Y`` /
``import X`` in ``benger_extended`` that targets a platform module (most of
them lazy imports inside functions). Platform PR CI never runs the extended
suites, so a renamed or removed helper would otherwise pass here and only fail
at request time in production. This test resolves the ``api_shared`` section
in the api environment; ``services/workers/tests/test_overlay_surface.py``
does the same for the worker image.

If an entry fails, either keep the symbol (or a compatible alias) or land the
matching change in benger-extended first, then regenerate the list there.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

CONTRACT = Path(__file__).resolve().parent.parent / "contracts" / "overlay_imports.json"
REGENERATE = "make update-overlay-surface PLATFORM_DIR=<path to benger-platform> (run in benger-extended)"


def _entries(section: str) -> list[dict]:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))[section]


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


def _check(entry: dict) -> None:
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


def test_contract_file_is_present_and_non_empty():
    assert CONTRACT.is_file(), f"{CONTRACT} is missing; regenerate it: {REGENERATE}"
    assert _entries("api_shared"), "the api_shared section is empty"


@pytest.mark.parametrize(
    "entry",
    _entries("api_shared"),
    ids=lambda e: e["module"] if e["name"] is None else f"{e['module']}:{e['name']}",
)
def test_overlay_import_resolves(entry):
    _check(entry)
