"""List measures: an answer's list of items compared with a gold list.

``{"kind": "list", "field": "cited", "gold": {"path": "gold.cited"},
"statistic": "recall"}`` reads the list an answer gives (a multi-select
``choices`` field, a Repeater array, or a text) and the gold list of the task
(a task data path or fixed ``values``), turns both into sets of items and
reports one statistic per answer.

Items. A list value gives one raw item per element (numbers and booleans as
their canonical text, objects skipped); a text gives one raw item, or one per
part when ``split`` (a regex) is set. ``items`` extracts canonical items from
the raw ones: ``{"pattern": "\\bB\\s*([1-5])\\b", "template": "B{1}",
"flags": ["IGNORECASE"]}`` turns every match in every raw item into an item
(``template`` fills ``{0}``, ``{1}``, ... from the match groups; without it the
whole match). ``normalize`` then applies, in order, ``strip``,
``collapse_whitespace``, ``casefold`` and ``nfc``/``nfkc``. Empty items are
dropped and the result is a set: duplicates count once. The gold list goes
through the same steps, so both sides compare in one canonical form.

Statistics (A the answer's items, G the gold items):

=============== ======================================================
``n_answer``    ``|A|`` (needs no gold)
``n_gold``      ``|G|``
``hits``        ``|A ∩ G|``
``misses``      ``|G \\ A|``
``extras``      ``|A \\ G|``
``precision``   ``|A ∩ G| / |A|``, missing when A is empty
``recall``      ``|A ∩ G| / |G|``, missing when G is empty
``f1``          ``2PR / (P + R)``, missing when P or R is, 0 when both are 0
``jaccard``     ``|A ∩ G| / |A ∪ G|``, missing when both are empty
``exact``       1 when A equals G, else 0
``any``         1 when A and G share an item, else 0
``all``         1 when every gold item is in A, else 0
=============== ======================================================

A missing answer value (the field is absent or null) or a missing gold value
gives a missing statistic; an empty list is a list with no items.
"""

from __future__ import annotations

import math
import re
import unicodedata
from functools import lru_cache
from typing import Any, FrozenSet, Mapping, Optional, Sequence, Tuple

STATISTICS = (
    "n_answer",
    "n_gold",
    "hits",
    "misses",
    "extras",
    "precision",
    "recall",
    "f1",
    "jaccard",
    "exact",
    "any",
    "all",
)
NORMALIZERS = ("strip", "collapse_whitespace", "casefold", "nfc", "nfkc")
_TEMPLATE_REF = re.compile(r"\{(\d+)\}")
FLAG_BITS = {
    "IGNORECASE": re.IGNORECASE,
    "MULTILINE": re.MULTILINE,
    "DOTALL": re.DOTALL,
    "ASCII": re.ASCII,
}


class ListMeasureError(ValueError):
    pass


@lru_cache(maxsize=256)
def _compile(pattern: str, flags: Tuple[str, ...]) -> "re.Pattern[str]":
    bits = 0
    for f in flags:
        bits |= FLAG_BITS[f]
    return re.compile(pattern, bits)


def check_list_measure(m: Mapping[str, Any], where: str) -> list:
    """Semantic problems of a list measure (the schema checks the shape)."""
    errors = []
    items = m.get("items") or {}
    if items.get("pattern"):
        try:
            rx = _compile(items["pattern"], tuple(items.get("flags") or ()))
        except re.error as exc:
            errors.append(f"{where}/items/pattern: does not compile: {exc}")
            rx = None
        template = items.get("template")
        if rx is not None and template is not None:
            for ref in _TEMPLATE_REF.findall(template):
                if int(ref) > rx.groups:
                    errors.append(f"{where}/items/template: group {{{ref}}} does not exist in the pattern")
    if m.get("split"):
        try:
            re.compile(m["split"])
        except re.error as exc:
            errors.append(f"{where}/split: does not compile: {exc}")
    if "gold" not in m and m.get("statistic") != "n_answer":
        errors.append(f"{where}: statistic {m.get('statistic')!r} needs 'gold'")
    return errors


def _raw_items(value: Any, split: Optional[str]) -> Optional[list]:
    from analysis.measures import as_text

    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (list, tuple)):
        out = []
        for v in value:
            if isinstance(v, (dict, list, tuple)) or v is None:
                continue
            t = as_text(v)
            if t is not None:
                out.append(t)
        return out
    if isinstance(value, Mapping):
        return None
    text = as_text(value)
    if text is None:
        return None
    if split:
        return re.split(split, text)
    return [text]


def _normalize(item: str, steps: Sequence[str]) -> str:
    for step in steps:
        if step == "strip":
            item = item.strip()
        elif step == "collapse_whitespace":
            item = " ".join(item.split())
        elif step == "casefold":
            item = item.casefold()
        elif step == "nfc":
            item = unicodedata.normalize("NFC", item)
        elif step == "nfkc":
            item = unicodedata.normalize("NFKC", item)
    return item


def _fill(template: str, match: "re.Match[str]") -> str:
    def group(ref: "re.Match[str]") -> str:
        g = match.group(int(ref.group(1)))
        return g if g is not None else ""

    return _TEMPLATE_REF.sub(group, template)


def item_set(value: Any, m: Mapping[str, Any]) -> Optional[FrozenSet[str]]:
    """The canonical item set of ``value`` under measure ``m`` (None when
    the value is missing)."""
    raw = _raw_items(value, m.get("split"))
    if raw is None:
        return None
    items = m.get("items") or {}
    if items.get("pattern"):
        rx = _compile(items["pattern"], tuple(items.get("flags") or ()))
        template = items.get("template")
        extracted = []
        for r in raw:
            for match in rx.finditer(r):
                extracted.append(_fill(template, match) if template is not None else match.group(0))
        raw = extracted
    steps = m.get("normalize") or ()
    out = set()
    for r in raw:
        t = _normalize(r, steps)
        if t:
            out.add(t)
    return frozenset(out)


def gold_value(m: Mapping[str, Any], task_data: Mapping[str, Any]) -> Any:
    from analysis.measures import lookup_path

    gold = m.get("gold") or {}
    if "values" in gold:
        return list(gold["values"])
    if "path" in gold:
        return lookup_path(task_data, gold["path"])
    return None


def statistic(answer: Optional[FrozenSet[str]], gold: Optional[FrozenSet[str]], name: str) -> float:
    nan = math.nan
    if answer is None:
        return nan
    if name == "n_answer":
        return float(len(answer))
    if gold is None:
        return nan
    inter = len(answer & gold)
    if name == "n_gold":
        return float(len(gold))
    if name == "hits":
        return float(inter)
    if name == "misses":
        return float(len(gold - answer))
    if name == "extras":
        return float(len(answer - gold))
    if name == "precision":
        return inter / len(answer) if answer else nan
    if name == "recall":
        return inter / len(gold) if gold else nan
    if name == "f1":
        if not answer or not gold:
            return nan
        p, r = inter / len(answer), inter / len(gold)
        return 0.0 if p + r == 0 else 2 * p * r / (p + r)
    if name == "jaccard":
        union = len(answer | gold)
        return inter / union if union else nan
    if name == "exact":
        return 1.0 if answer == gold else 0.0
    if name == "any":
        return 1.0 if inter else 0.0
    if name == "all":
        return 1.0 if gold <= answer else 0.0
    raise ListMeasureError(f"unknown list statistic {name!r}")


def list_measure_value(m: Mapping[str, Any], field_value: Any, task_data: Mapping[str, Any]) -> float:
    answer = item_set(field_value, m)
    gold = item_set(gold_value(m, task_data), m) if "gold" in m else None
    return statistic(answer, gold, m["statistic"])


__all__ = [
    "ListMeasureError",
    "NORMALIZERS",
    "STATISTICS",
    "check_list_measure",
    "gold_value",
    "item_set",
    "list_measure_value",
    "statistic",
]
