"""services/shared must not import API-only modules.

/shared is on sys.path in both the api and the workers containers, but the
worker image only carries services/workers plus /shared. An unguarded import
of an API-only package (``routers``, ``app``, ``auth_module``, ...) from
shared code therefore raises ModuleNotFoundError in the worker at call time.
That is how every Label Studio export job failed: export_stream imported
``routers.projects.import_export`` inside the generator the export worker runs.

The test parses every services/shared/**/*.py with ``ast`` and fails on any
import of an API-only top-level module, at module level or inside a function.

Optional imports stay allowed when they are written as optional: an import
inside the body of a ``try`` whose handlers catch ImportError (or a broader
class) and fall back to something that works in the worker. ``if
TYPE_CHECKING:`` blocks are allowed too, they never execute.
"""

import ast
from pathlib import Path

import pytest

API_DIR = Path(__file__).resolve().parents[2]
SERVICES_DIR = API_DIR.parent
SHARED_DIR = SERVICES_DIR / "shared"
WORKERS_DIR = SERVICES_DIR / "workers"

# Top-level names the workers image also provides. Used when services/workers
# is not visible (the api test container mounts only /app and /shared).
_WORKERS_FALLBACK = {"database", "email_service", "notification_service", "sendgrid_client"}

# Directories under services/api that are not importable application code or
# that shadow a third-party distribution of the same name (alembic/ holds the
# migrations; ``import alembic`` means the library).
_NOT_MODULES = {"tests", "scripts", "alembic", "__pycache__"}

_CATCHES_IMPORT_ERROR = {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}


def _top_level_modules(directory: Path) -> set:
    names = set()
    for entry in directory.iterdir():
        if entry.name in _NOT_MODULES or entry.name.startswith("."):
            continue
        if entry.is_dir() and any(entry.glob("*.py")):
            names.add(entry.name)
        elif entry.suffix == ".py":
            names.add(entry.stem)
    return names


def _api_only_modules() -> set:
    workers = _top_level_modules(WORKERS_DIR) if WORKERS_DIR.is_dir() else _WORKERS_FALLBACK
    return _top_level_modules(API_DIR) - _top_level_modules(SHARED_DIR) - workers


def _handler_names(handler: ast.ExceptHandler) -> set:
    if handler.type is None:
        return {"BaseException"}
    nodes = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    return {n.id if isinstance(n, ast.Name) else getattr(n, "attr", "") for n in nodes}


def _is_type_checking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _unguarded_imports(tree: ast.AST):
    """Yield (lineno, module) for imports not inside an optional-import guard."""

    def visit(node, guarded):
        if isinstance(node, ast.Import):
            if not guarded:
                for alias in node.names:
                    yield node.lineno, alias.name
            return
        if isinstance(node, ast.ImportFrom):
            if not guarded and node.level == 0 and node.module:
                yield node.lineno, node.module
            return
        if isinstance(node, ast.Try) or type(node).__name__ == "TryStar":
            body_guarded = guarded or any(
                _handler_names(h) & _CATCHES_IMPORT_ERROR for h in node.handlers
            )
            for child in node.body:
                yield from visit(child, body_guarded)
            for child in node.handlers + node.orelse + node.finalbody:
                yield from visit(child, guarded)
            return
        if isinstance(node, ast.If) and _is_type_checking(node.test):
            for child in node.body:
                yield from visit(child, True)
            for child in node.orelse:
                yield from visit(child, guarded)
            return
        for child in ast.iter_child_nodes(node):
            yield from visit(child, guarded)

    yield from visit(tree, False)


def test_api_only_set_is_derived_sensibly():
    api_only = _api_only_modules()
    for name in ("routers", "app", "auth_module", "celery_client", "redis_cache"):
        assert name in api_only
    # Present in shared or workers, so importing them from shared is fine.
    for name in ("models", "database", "utils", "feature_flags"):
        assert name not in api_only


def test_guard_detects_lazy_and_ignores_optional_imports():
    api_only = {"routers"}
    src = (
        "def f():\n"
        "    from routers.x import y\n"
        "try:\n"
        "    from routers.z import w\n"
        "except ImportError:\n"
        "    w = None\n"
        "try:\n"
        "    import routers.q\n"
        "except KeyError:\n"
        "    pass\n"
    )
    hits = [m for _, m in _unguarded_imports(ast.parse(src)) if m.split(".")[0] in api_only]
    assert hits == ["routers.x", "routers.q"]


@pytest.mark.skipif(not SHARED_DIR.is_dir(), reason="services/shared not visible")
def test_shared_does_not_import_api_only_modules():
    api_only = _api_only_modules()
    offenders = []
    for path in sorted(SHARED_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for lineno, module in _unguarded_imports(tree):
            if module.split(".")[0] in api_only:
                offenders.append(f"{path.relative_to(SHARED_DIR)}:{lineno} imports {module}")
    assert not offenders, (
        "services/shared imports API-only modules (the worker image has none of "
        "them). Move the code into /shared or guard the import with "
        "try/except ImportError and a worker-safe fallback:\n" + "\n".join(offenders)
    )
