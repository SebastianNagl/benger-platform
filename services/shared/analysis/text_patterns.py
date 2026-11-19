"""Text-pattern codes: named, versioned regular-expression sets.

A pattern set codes a text (a full answer or one parsed field) into named
codes, for example whether an answer mentions a phrase, how often it uses a
term, or which of several sides it names first. The set is data: it is
validated against ``schemas/text_pattern_set.schema.json``, normalized and
hashed (:func:`pattern_set_hash`), so every result can say exactly which
version of which set produced it. The same set runs as an analysis measure
(``{"kind": "text_pattern"}``), as the ``text_pattern`` evaluation metric and
in code validations.

Format (version :data:`TEXT_PATTERN_FORMAT_VERSION`)::

    {"name": "signals", "version": "2",
     "flags": ["IGNORECASE"],
     "normalize": "none",
     "codes": {
       "canary":  {"mode": "any",   "patterns": ["beyond\\\\s+doubt"]},
       "terms":   {"mode": "count", "patterns": ["\\\\bstatute\\\\b"]},
       "own_id":  {"mode": "any",   "patterns": ["{{task.case_ref|spaces}}"]},
       "side":    {"mode": "first", "default": "none",
                   "rules": [{"value": "P", "patterns": ["claimant"]},
                             {"value": "D", "patterns": ["respondent"]}]}}}

Modes:

``any``
    1.0 when at least one pattern matches somewhere in the text, else 0.0.
``all``
    1.0 when every pattern matches, else 0.0.
``count``
    the number of non-overlapping matches (``re.finditer``), summed over the
    patterns.
``first``
    the ``value`` of the first rule (in order) with a matching pattern, else
    ``default`` (``null``: missing). A text code.

Patterns use Python's ``re`` syntax and are searched anywhere in the text.
``flags`` (``IGNORECASE``, ``MULTILINE``, ``DOTALL``, ``ASCII``, ``VERBOSE``)
apply to every code unless a code lists its own. ``normalize`` (``NFC`` or
``NFKC``) normalizes the text's Unicode form before matching.

Task-parameterised literals: ``{{task.<path>}}`` in a pattern is replaced by
the value at that task data path (dotted, a numeric segment indexes a list),
regex-escaped, so a pattern can look for something only the task knows (a
case reference, a party's name). ``{{task.<path>|spaces}}`` matches the value
with any number of spaces between its characters (the value's own spaces
dropped), ``|whitespace`` the same for any whitespace. A list value matches
any of its elements. A code whose literal does not resolve (path missing, an
empty value) is missing for that task, never silently false.

A missing text (no answer, a field the answer does not have, a non-text
field) gives missing codes; an empty text is coded (no match).
"""

from __future__ import annotations

import copy
import json
import os
import re
import unicodedata
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from analysis.canonical import json_hash

#: Version of the pattern-set format and of its matching rules. It is part of
#: every set hash, so a change to how sets are applied changes every hash.
TEXT_PATTERN_FORMAT_VERSION = 1

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schemas", "text_pattern_set.schema.json")

FLAGS: Dict[str, int] = {
    "IGNORECASE": re.IGNORECASE,
    "MULTILINE": re.MULTILINE,
    "DOTALL": re.DOTALL,
    "ASCII": re.ASCII,
    "VERBOSE": re.VERBOSE,
}

NUMBER_MODES = ("any", "all", "count")
TEXT_MODES = ("first",)

PLACEHOLDER = re.compile(r"\{\{task\.([^{}|\s]+)(?:\|([a-z]+))?\}\}")
_OPEN = re.compile(r"(?<!\\)\{\{")
TRANSFORMS = ("literal", "spaces", "whitespace")
_PATH = re.compile(r"^[^.\s]+(\.[^.\s]+)*$")


class PatternSetError(ValueError):
    """An invalid pattern set. ``errors`` lists every problem found."""

    def __init__(self, errors: List[str]):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors) if self.errors else "invalid pattern set")


@lru_cache(maxsize=1)
def pattern_set_schema() -> Dict[str, Any]:
    with open(SCHEMA_PATH, encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def _validator():
    import jsonschema

    schema = pattern_set_schema()
    cls = jsonschema.validators.validator_for(schema)
    cls.check_schema(schema)
    return cls(schema)


def _schema_errors(doc: Any, where: str) -> List[str]:
    import jsonschema

    errors = []
    for err in sorted(_validator().iter_errors(doc), key=lambda e: list(map(str, e.absolute_path))):
        best = jsonschema.exceptions.best_match([err])
        path = "/".join(str(p) for p in best.absolute_path)
        errors.append(f"{where}/{path}: {best.message}" if path else f"{where or '/'}: {best.message}")
    return errors[:50]


def _code_patterns(code: Mapping[str, Any]) -> List[str]:
    if code.get("mode") in TEXT_MODES:
        return [p for rule in code.get("rules") or [] for p in rule.get("patterns") or []]
    return list(code.get("patterns") or [])


def _flag_bits(names: Iterable[str]) -> int:
    bits = 0
    for name in names:
        bits |= FLAGS[name]
    return bits


def _check_pattern(pattern: str, flags: int, where: str, errors: List[str]) -> None:
    for match in _OPEN.finditer(pattern):
        found = PLACEHOLDER.match(pattern, match.start())
        if found is None:
            errors.append(
                f"{where}: '{{{{' starts a placeholder; write {{{{task.<path>}}}} "
                "(optionally |spaces or |whitespace) or escape the braces"
            )
            return
        transform = found.group(2)
        if transform is not None and transform not in TRANSFORMS:
            errors.append(f"{where}: unknown literal transform {transform!r} (use {', '.join(TRANSFORMS)})")
            return
        if not _PATH.match(found.group(1)):
            errors.append(f"{where}: {found.group(1)!r} is not a task data path")
            return
    probe = PLACEHOLDER.sub("x", pattern)
    try:
        re.compile(probe, flags)
    except re.error as exc:
        errors.append(f"{where}: does not compile: {exc}")


def validate_pattern_set(doc: Any, where: str = "") -> None:
    """Raise :class:`PatternSetError` listing every problem of ``doc``."""
    errors = _schema_errors(doc, where)
    if errors:
        raise PatternSetError(errors)
    set_flags = doc.get("flags") or []
    for cid, code in doc["codes"].items():
        flags = _flag_bits(code.get("flags", set_flags))
        base = f"{where}/codes/{cid}"
        if code["mode"] in TEXT_MODES:
            values = [rule["value"] for rule in code["rules"]]
            if len(set(values)) != len(values):
                errors.append(f"{base}/rules: rule values repeat")
            for i, rule in enumerate(code["rules"]):
                for j, pattern in enumerate(rule["patterns"]):
                    _check_pattern(pattern, flags, f"{base}/rules/{i}/patterns/{j}", errors)
        else:
            for j, pattern in enumerate(code["patterns"]):
                _check_pattern(pattern, flags, f"{base}/patterns/{j}", errors)
    if errors:
        raise PatternSetError(errors)


def normalize_pattern_set(doc: Any, where: str = "") -> Dict[str, Any]:
    """Validate ``doc`` and return it with every default filled in: each
    code carries its resolved, sorted flags and rule-based codes their
    ``default``. Descriptions are kept but are not part of the hash."""
    validate_pattern_set(doc, where)
    out = copy.deepcopy(dict(doc))
    set_flags = sorted(set(out.get("flags") or []))
    out["flags"] = set_flags
    out.setdefault("normalize", "none")
    out.setdefault("description", "")
    codes = {}
    for cid, code in out["codes"].items():
        code = dict(code)
        code["flags"] = sorted(set(code.get("flags", set_flags)))
        code.setdefault("description", "")
        if code["mode"] in TEXT_MODES:
            code.setdefault("default", None)
            code["rules"] = [{"value": r["value"], "patterns": list(r["patterns"])} for r in code["rules"]]
        else:
            code["patterns"] = list(code["patterns"])
        codes[cid] = code
    out["codes"] = codes
    return out


def _hash_view(normalized: Mapping[str, Any]) -> Dict[str, Any]:
    codes = {}
    for cid, code in normalized["codes"].items():
        codes[cid] = {k: v for k, v in code.items() if k != "description"}
    return {
        "format": TEXT_PATTERN_FORMAT_VERSION,
        "name": normalized["name"],
        "version": normalized["version"],
        "flags": normalized["flags"],
        "normalize": normalized["normalize"],
        "codes": codes,
    }


def pattern_set_hash(normalized: Mapping[str, Any]) -> str:
    """SHA-256 of a normalized set's matching content (name, version, flags,
    normalization, codes and their patterns; not the descriptions) and the
    format version."""
    return json_hash(_hash_view(normalized))


def code_type(normalized: Mapping[str, Any], code_id: str) -> str:
    """``number`` for ``any``/``all``/``count`` codes, ``text`` for ``first``."""
    return "text" if normalized["codes"][code_id]["mode"] in TEXT_MODES else "number"


# --------------------------------------------------------------------------
# Applying a set
# --------------------------------------------------------------------------


def _literal_values(value: Any) -> List[str]:
    from analysis.measures import as_text

    items = value if isinstance(value, (list, tuple)) else [value]
    out = []
    for item in items:
        if isinstance(item, (dict, list, tuple)):
            continue
        text = as_text(item)
        if text:
            out.append(text)
    return out


def _literal_regex(values: Sequence[str], transform: str) -> Optional[str]:
    parts = []
    for v in values:
        if transform == "spaces":
            chars = [c for c in v if c != " "]
            part = "[ ]*".join(re.escape(c) for c in chars)
        elif transform == "whitespace":
            chars = [c for c in v if not c.isspace()]
            part = r"\s*".join(re.escape(c) for c in chars)
        else:
            part = re.escape(v)
        if part:
            parts.append(part)
    if not parts:
        return None
    return parts[0] if len(parts) == 1 else "(?:" + "|".join(parts) + ")"


class CompiledPatternSet:
    """A normalized set ready to code texts. Patterns without placeholders
    compile once; patterns with task literals compile per distinct literal
    value (cached)."""

    def __init__(self, normalized: Mapping[str, Any]):
        self.normalized = normalized
        self.hash = pattern_set_hash(normalized)
        self.name = normalized["name"]
        self.version = normalized["version"]
        self.ref = f"{self.name}@{self.version}"
        self._normal_form = None if normalized["normalize"] == "none" else normalized["normalize"]
        self._cache: Dict[Tuple[str, int], "re.Pattern[str]"] = {}

    def _compile(self, pattern: str, flags: int) -> "re.Pattern[str]":
        key = (pattern, flags)
        rx = self._cache.get(key)
        if rx is None:
            if len(self._cache) > 50_000:
                self._cache.clear()
            rx = re.compile(pattern, flags)
            self._cache[key] = rx
        return rx

    def _resolve(self, pattern: str, task_data: Optional[Mapping[str, Any]]) -> Optional[str]:
        from analysis.measures import lookup_path

        if "{{" not in pattern:
            return pattern
        missing = False

        def replace(match: "re.Match[str]") -> str:
            nonlocal missing
            value = lookup_path(task_data or {}, match.group(1))
            literal = _literal_regex(_literal_values(value), match.group(2) or "literal")
            if literal is None:
                missing = True
                return ""
            return literal

        resolved = PLACEHOLDER.sub(replace, pattern)
        return None if missing else resolved

    def _searchers(self, patterns: Sequence[str], flags: int, task_data) -> Optional[List["re.Pattern[str]"]]:
        out = []
        for p in patterns:
            resolved = self._resolve(p, task_data)
            if resolved is None:
                return None
            out.append(self._compile(resolved, flags))
        return out

    def evaluate(
        self, code_id: str, text: Optional[str], task_data: Optional[Mapping[str, Any]] = None
    ) -> Tuple[Any, str]:
        """``(value, status)`` of one code for ``text``. ``status`` is
        ``"matched"`` (a ``first`` rule matched), ``"coded"`` (any other
        coded value, including a ``first`` code's default), ``"no_text"`` or
        ``"unresolved"`` (a task literal is missing); the value is NaN/None
        for the last two."""
        code = self.normalized["codes"][code_id]
        number = code["mode"] in NUMBER_MODES
        missing = float("nan") if number else None
        if not isinstance(text, str):
            return missing, "no_text"
        if self._normal_form:
            text = unicodedata.normalize(self._normal_form, text)
        flags = _flag_bits(code["flags"])
        mode = code["mode"]
        if mode == "first":
            for rule in code["rules"]:
                searchers = self._searchers(rule["patterns"], flags, task_data)
                if searchers is None:
                    return missing, "unresolved"
                if any(rx.search(text) for rx in searchers):
                    return rule["value"], "matched"
            return code.get("default"), "coded"
        searchers = self._searchers(code["patterns"], flags, task_data)
        if searchers is None:
            return missing, "unresolved"
        if mode == "any":
            return (1.0 if any(rx.search(text) for rx in searchers) else 0.0), "coded"
        if mode == "all":
            return (1.0 if all(rx.search(text) for rx in searchers) else 0.0), "coded"
        return float(sum(sum(1 for _ in rx.finditer(text)) for rx in searchers)), "coded"

    def code(self, code_id: str, text: Optional[str], task_data: Optional[Mapping[str, Any]] = None) -> Any:
        """The value of one code for ``text``: a float for number codes, a
        string (or None) for ``first`` codes; NaN/None when missing."""
        return self.evaluate(code_id, text, task_data)[0]

    def codes(self, text: Optional[str], task_data: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        """Every code of the set for ``text``."""
        return {cid: self.code(cid, text, task_data) for cid in self.normalized["codes"]}

    def describe(self) -> Dict[str, Any]:
        return {"name": self.name, "version": self.version, "ref": self.ref, "hash": self.hash}


def compile_pattern_set(doc: Any, where: str = "") -> CompiledPatternSet:
    """Validate, normalize and compile ``doc``."""
    return CompiledPatternSet(normalize_pattern_set(doc, where))


__all__ = [
    "CompiledPatternSet",
    "FLAGS",
    "PatternSetError",
    "TEXT_PATTERN_FORMAT_VERSION",
    "code_type",
    "compile_pattern_set",
    "normalize_pattern_set",
    "pattern_set_hash",
    "pattern_set_schema",
    "validate_pattern_set",
]
