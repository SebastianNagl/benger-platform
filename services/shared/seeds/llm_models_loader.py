"""Loader for the LLM model catalog YAML.

This is the single source of truth for the llm_models table content.
The seed function in database.py and the cost lookup in
shared.ai_services.provider_capabilities both consume this loader's output,
so a single edit to llm_models.yaml propagates to both.

Extension hook: every extension package (``BENGER_EXTENSIONS``, default
``benger_extended``) that exposes ``get_llm_models_yaml_path()`` contributes
a YAML whose entries are merged on top of the platform list, in package
order (an entry with the same ``id`` overrides the earlier source). The
loader works without the app (the drift-check script): it reads the
configured package names itself and imports each package directly.
"""

from __future__ import annotations

import hashlib
import importlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

PLATFORM_YAML = Path(__file__).parent / "llm_models.yaml"

REQUIRED_FIELDS = {"id", "name", "provider", "model_type", "capabilities", "is_active"}


@dataclass
class CatalogLoadResult:
    models: List[Dict[str, Any]]
    content_hash: str
    sources: List[str] = field(default_factory=list)


def _load_yaml_file(path: Path) -> Dict[str, Any]:
    with path.open() as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict) or "models" not in data:
        raise ValueError(f"{path}: missing top-level 'models' list")
    if not isinstance(data["models"], list):
        raise ValueError(f"{path}: 'models' must be a list")
    return data


def _validate(model: Dict[str, Any], source: str) -> None:
    missing = REQUIRED_FIELDS - model.keys()
    if missing:
        raise ValueError(f"{source}: model {model.get('id')!r} missing required fields: {sorted(missing)}")
    if not isinstance(model["capabilities"], list):
        raise ValueError(f"{source}: model {model['id']!r} 'capabilities' must be a list")
    # The "custom-" id namespace is reserved for user-registered BYOM rows
    # (generated PKs, migration 080). A YAML/overlay entry there could
    # collide with a user's model or get swept by the official-only
    # deactivation pass — reject it outright.
    if str(model["id"]).startswith("custom-"):
        raise ValueError(
            f"{source}: model id {model['id']!r} uses the reserved 'custom-' prefix"
        )


def _extension_package_names() -> List[str]:
    """The configured extension packages, in order (``BENGER_EXTENSIONS``)."""
    try:
        from extension_registry import configured_names
    except ImportError:  # /shared not on sys.path (bare script run)
        return ["benger_extended"]
    return configured_names()


def _extension_yaml_path(package_name: str) -> Optional[Path]:
    """Resolve the model YAML path of one package, if it provides one."""
    try:
        ext = importlib.import_module(package_name)
    except ImportError:
        return None
    getter = getattr(ext, "get_llm_models_yaml_path", None)
    if not getter:
        return None
    try:
        path = getter()
    except Exception:
        logger.exception("%s.get_llm_models_yaml_path() raised; ignoring", package_name)
        return None
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        logger.warning("%s declared %s but it does not exist; ignoring", package_name, p)
        return None
    return p


def _extension_yaml_paths() -> List[Path]:
    """The extension packages' model YAMLs, in package order."""
    paths: List[Path] = []
    for name in _extension_package_names():
        path = _extension_yaml_path(name)
        if path is not None and path not in paths:
            paths.append(path)
    return paths


def load_catalog() -> CatalogLoadResult:
    """Load and merge the model catalog.

    Returns a CatalogLoadResult with the merged model list and a content
    hash that callers can use to gate "did anything change since last seed".
    """
    sources: List[str] = []
    raw_chunks: List[bytes] = []
    by_id: Dict[str, Dict[str, Any]] = {}

    for path in [PLATFORM_YAML, *_extension_yaml_paths()]:
        sources.append(str(path))
        raw_chunks.append(path.read_bytes())
        data = _load_yaml_file(path)
        for m in data["models"]:
            _validate(m, str(path))
            by_id[m["id"]] = m  # later sources override

    if not by_id:
        raise RuntimeError(f"No models found in {PLATFORM_YAML}")

    models = list(by_id.values())
    h = hashlib.sha256(b"\n--\n".join(raw_chunks)).hexdigest()
    return CatalogLoadResult(models=models, content_hash=h, sources=sources)
