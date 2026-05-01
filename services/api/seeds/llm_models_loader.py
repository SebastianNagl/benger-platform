"""Loader for the LLM model catalog YAML.

This is the single source of truth for the llm_models table content.
The seed function in database.py and the cost lookup in
shared.ai_services.provider_capabilities both consume this loader's output,
so a single edit to llm_models.yaml propagates to both.

Extension hook: if benger_extended ships an `llm_models_extended.yaml`
alongside its package and exposes `get_llm_models_yaml_path()`, those
entries are merged on top of the platform list (extended entries with the
same `id` override platform entries).
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


def _extended_yaml_path() -> Optional[Path]:
    """Resolve the extended model YAML path if benger_extended provides one."""
    try:
        ext = importlib.import_module("benger_extended")
    except ImportError:
        return None
    getter = getattr(ext, "get_llm_models_yaml_path", None)
    if not getter:
        return None
    try:
        path = getter()
    except Exception:
        logger.exception("benger_extended.get_llm_models_yaml_path() raised; ignoring")
        return None
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        logger.warning("benger_extended declared %s but it does not exist; ignoring", p)
        return None
    return p


def load_catalog() -> CatalogLoadResult:
    """Load and merge the model catalog.

    Returns a CatalogLoadResult with the merged model list and a content
    hash that callers can use to gate "did anything change since last seed".
    """
    sources: List[str] = []
    raw_chunks: List[bytes] = []
    by_id: Dict[str, Dict[str, Any]] = {}

    for path in [PLATFORM_YAML, _extended_yaml_path()]:
        if path is None:
            continue
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
