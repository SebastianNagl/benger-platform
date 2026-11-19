"""Coder plugins: versioned code functions with a recorded code hash.

Some codes cannot be written as a regex set (a sentence-level rule that
decides which party an answer blames, a parser of a domain-specific
citation format). A coder plugin is a pure function of one answer that
returns named outputs; an overlay registers it with :data:`coder_registry`
and analysis measures (``{"kind": "coder"}``) and code validations run it.

Contract::

    from analysis.coders import Coder

    class BlameDirection(Coder):
        name = "blame_direction"
        version = "3"
        outputs = {"direction": "text", "confidence": "number"}

        def code(self, text, context):
            ...
            return {"direction": "P", "confidence": 0.8}

* ``name`` is an identifier, ``version`` a short token; a new behaviour
  needs a new version.
* ``outputs`` maps each output to ``number``, ``text`` or ``bool``; values
  are coerced like parsed fields (:func:`analysis.measures.coerce`), and an
  output the coder does not return is missing.
* ``code(text, context)`` gets the text (the full answer or one parsed
  field, ``None`` when missing) and a :class:`CoderContext` with the
  answer's typed parsed fields, the task data, the task's design factors and
  the measure's ``parameters``. It must not do I/O and must be
  deterministic: the same inputs give the same outputs.
* ``source_modules`` (optional) names further modules whose source the
  coder depends on; the module defining the coder class always counts.

On registration the registry computes the code hash: SHA-256 over the name,
version, outputs and the source text of every counted module. Analysis runs
and validations record name, version, hash and the registering package, so a
result always says which code produced it; a validation is only accepted for
the code hash it was computed with.

Overlays register in their workers module::

    def register_coders(registry):
        registry.register(BlameDirection())

The workers call :func:`load_overlay_coders` before an analysis or a
validation. A coder of a package that is switched off for the run's
project or user does not run (the run fails naming the package).
"""

from __future__ import annotations

import hashlib
import inspect
import logging
import re
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from analysis.canonical import json_hash

logger = logging.getLogger(__name__)

#: Version of the coder contract and of how code hashes are computed.
CODER_FORMAT_VERSION = 1

OUTPUT_TYPES = ("number", "text", "bool")
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_VERSION = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.:-]*$")


class CoderError(ValueError):
    """A coder that cannot be registered or run."""


@dataclass(frozen=True)
class CoderContext:
    fields: Mapping[str, Any] = field(default_factory=dict)
    task_data: Mapping[str, Any] = field(default_factory=dict)
    factors: Mapping[str, Any] = field(default_factory=dict)
    parameters: Mapping[str, Any] = field(default_factory=dict)


class Coder(ABC):
    name: str = ""
    version: str = ""
    outputs: Mapping[str, str] = {}
    source_modules: Sequence[str] = ()

    @abstractmethod
    def code(self, text: Optional[str], context: CoderContext) -> Mapping[str, Any]:
        """The outputs for one answer."""


class FunctionCoder(Coder):
    """A coder made from a plain function ``fn(text, context) -> dict``."""

    def __init__(
        self,
        name: str,
        version: str,
        outputs: Mapping[str, str],
        fn: Callable[[Optional[str], CoderContext], Mapping[str, Any]],
        source_modules: Sequence[str] = (),
    ):
        self.name = name
        self.version = version
        self.outputs = dict(outputs)
        self.fn = fn
        self.source_modules = tuple(source_modules) + (fn.__module__,)

    def code(self, text, context):
        return self.fn(text, context)


@dataclass(frozen=True)
class RegisteredCoder:
    coder: Coder
    name: str
    version: str
    outputs: Mapping[str, str]
    code_hash: str
    sources: Sequence[Mapping[str, str]]
    owner: Optional[str]

    @property
    def ref(self) -> str:
        return f"{self.name}@{self.version}"

    def describe(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "ref": self.ref,
            "outputs": dict(self.outputs),
            "code_hash": self.code_hash,
            "sources": [dict(s) for s in self.sources],
            "owner": self.owner,
        }

    def active(self) -> bool:
        if not self.owner:
            return True
        try:
            import extension_activation
        except ImportError:  # pragma: no cover - /shared always ships it
            return True
        return extension_activation.package_active(self.owner)

    def run(self, text: Optional[str], context: CoderContext) -> Dict[str, Any]:
        """The coder's outputs, each coerced to its declared type (missing
        when absent). Raises :class:`CoderError` when the coder fails or
        returns something that is not a mapping."""
        from analysis.measures import coerce

        try:
            raw = self.coder.code(text, context)
        except Exception as exc:  # noqa: BLE001 - a coder bug is reported per run
            raise CoderError(f"coder {self.ref} failed: {type(exc).__name__}: {exc}") from None
        if raw is None:
            raw = {}
        if not isinstance(raw, Mapping):
            raise CoderError(f"coder {self.ref} returned {type(raw).__name__}, not a mapping")
        return {out: coerce(raw.get(out), kind) for out, kind in self.outputs.items()}


def _module_source(name: str) -> str:
    module = sys.modules.get(name)
    if module is None:
        import importlib

        try:
            module = importlib.import_module(name)
        except ImportError as exc:
            raise CoderError(f"source module {name!r} does not import: {exc}") from None
    try:
        return inspect.getsource(module)
    except (OSError, TypeError) as exc:
        raise CoderError(f"the source of module {name!r} is not readable, so no code hash: {exc}") from None


def coder_code_hash(coder: Coder) -> tuple:
    """``(hash, sources)`` of a coder: SHA-256 over its identity and the
    source text of every counted module, and ``[{module, sha256}]``."""
    modules = []
    for name in (type(coder).__module__, *getattr(coder, "source_modules", ())):
        if name and name not in modules:
            modules.append(name)
    sources = []
    for name in modules:
        text = _module_source(name)
        sources.append({"module": name, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()})
    digest = json_hash(
        {
            "format": CODER_FORMAT_VERSION,
            "name": coder.name,
            "version": coder.version,
            "outputs": dict(coder.outputs),
            "sources": sources,
        }
    )
    return digest, sources


def _owner() -> Optional[str]:
    try:
        from extension_registry import current_owner
    except ImportError:  # pragma: no cover
        return None
    return current_owner()


class CoderRegistry:
    """Coder name -> registered coder (one version per name and process)."""

    def __init__(self) -> None:
        self._coders: Dict[str, RegisteredCoder] = {}

    def register(self, coder: Coder) -> RegisteredCoder:
        name, version, outputs = coder.name, coder.version, getattr(coder, "outputs", None)
        if not isinstance(name, str) or not _NAME.match(name) or len(name) > 100:
            raise CoderError(f"coder name {name!r} must be an identifier")
        if not isinstance(version, str) or not _VERSION.match(version) or len(version) > 100:
            raise CoderError(f"coder {name}: version {version!r} must be a short token such as '1' or '2.1'")
        if not isinstance(outputs, Mapping) or not outputs:
            raise CoderError(f"coder {name}: outputs must name at least one output")
        for out, kind in outputs.items():
            if not isinstance(out, str) or not _NAME.match(out):
                raise CoderError(f"coder {name}: output {out!r} must be an identifier")
            if kind not in OUTPUT_TYPES:
                raise CoderError(f"coder {name}: output {out!r} has type {kind!r} (use {', '.join(OUTPUT_TYPES)})")
        code_hash, sources = coder_code_hash(coder)
        owner = _owner()
        entry = RegisteredCoder(
            coder=coder,
            name=name,
            version=version,
            outputs=dict(outputs),
            code_hash=code_hash,
            sources=sources,
            owner=owner,
        )
        previous = self._coders.get(name)
        if previous is not None and previous.code_hash != code_hash:
            logger.warning(
                "coder %r registered by %s replaces %s's (%s -> %s)",
                name,
                owner or "the platform",
                previous.owner or "the platform",
                previous.ref,
                entry.ref,
            )
        self._coders[name] = entry
        return entry

    def unregister(self, name: str) -> None:
        self._coders.pop(name, None)

    def get(self, name: str) -> Optional[RegisteredCoder]:
        return self._coders.get(name)

    def names(self) -> List[str]:
        return sorted(self._coders)

    def describe(self) -> List[Dict[str, Any]]:
        return [self._coders[n].describe() for n in self.names()]

    def resolve(self, name: str, version: Optional[str] = None) -> RegisteredCoder:
        """The coder ``name`` (pinned to ``version`` when given), active in
        the current context. Raises :class:`CoderError` otherwise."""
        entry = self._coders.get(name)
        if entry is None:
            raise CoderError(f"no coder {name!r} is registered (an overlay registers coders)")
        if version is not None and entry.version != version:
            raise CoderError(f"coder {name!r} is version {entry.version!r}, the spec pins {version!r}")
        if not entry.active():
            raise CoderError(f"coder {name!r} belongs to {entry.owner!r}, which is switched off here")
        return entry


coder_registry = CoderRegistry()

_overlays_loaded = False


def load_overlay_coders(registry: Optional[CoderRegistry] = None, *, force: bool = False) -> List[str]:
    """Call ``register_coders(registry)`` of every loaded extension
    package's workers module (once per process unless ``force``), each under
    its package as owner. Returns the packages that registered."""
    global _overlays_loaded
    registry = registry or coder_registry
    if _overlays_loaded and not force and registry is coder_registry:
        return []
    import extension_registry

    done = []
    for ext in extension_registry.load_all():
        workers = extension_registry.worker_module(ext.name, strict=True)
        if workers is None:
            continue
        hook = getattr(workers, "register_coders", None)
        if hook is None:
            continue
        with extension_registry.owner(ext.name):
            hook(registry)
        done.append(ext.name)
    if registry is coder_registry:
        _overlays_loaded = True
    return done


__all__ = [
    "CODER_FORMAT_VERSION",
    "Coder",
    "CoderContext",
    "CoderError",
    "CoderRegistry",
    "FunctionCoder",
    "RegisteredCoder",
    "coder_code_hash",
    "coder_registry",
    "load_overlay_coders",
]
