"""Pure helpers for the checklist pilot runner (``run_checklist_pilot.py``).

Nothing here touches the database or a provider at import time, so the
runner's ``selftest`` phase can exercise every piece without either:

- the spend ledger and the metered provider wrapper (spend cap, catalog
  prices, reserve charge on a failed call, dry run);
- the leakage guard (canary terms from the D2 exam against every prompt that
  must not have seen Martin's sheet);
- the spec adapter (any platform rubric or Martin's sheet as a checklist spec
  for the step and rating units);
- the probe builders ``negation_flip`` and ``keyword_salad``;
- arm parsing and the exam's grade key.

The runner copies this file next to itself into the container
(``scripts/ops/pilot.sh``) and imports it from there.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import time
import unicodedata
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Stop signals. All derive from BaseException on purpose: the judge and the
# generator wrap provider calls in ``except Exception`` and retry, which would
# swallow an ordinary exception and let the run continue.
# ---------------------------------------------------------------------------


class BudgetExceeded(BaseException):
    """The next call could push the cumulative spend over the cap."""


class ProviderBlocked(BaseException):
    """A provider refuses on billing grounds (no credits, spending limit)."""


class PriceMissing(BaseException):
    """The model has no catalog price, so its spend cannot be metered."""


class LeakageDetected(BaseException):
    """A canary term of the D2 exam reached a prompt that must not see it."""


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


def sha256_text(text: str | None) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def sha256_file(path: Any) -> str | None:
    p = Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None


def code_version(file_hashes: dict[str, str | None]) -> str:
    """Short id over the instrument files' content hashes (the gate filters on it)."""
    payload = "\n".join(f"{name}={file_hashes[name]}" for name in sorted(file_hashes))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Ledger and metered provider calls
# ---------------------------------------------------------------------------

# Worst plausible single call, checked before dispatch and charged in full
# when a call raises (its real usage is then unknown).
RESERVE_USD = {
    "gpt-5.6-luna": 0.06,
    "deepseek-ai/DeepSeek-V4-Pro": 0.15,
    "gpt-5.4-mini": 0.25,
    "gpt-5.4": 0.80,
}
# Models without an explicit reserve get this call priced at catalog rates.
RESERVE_TOKENS = (80_000, 32_000)
MIN_RESERVE_USD = 0.05

_BLOCKED_MARKERS = ("credit_balance_exhausted", "insufficient_quota", "no credits remaining",
                    "user-set limit", "HTTP 402", "billing")


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def load_catalog_prices(path: Any = "/shared/seeds/llm_models.yaml") -> dict[str, tuple[float | None, float | None]]:
    import yaml

    catalog = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    rows = catalog["models"] if isinstance(catalog, dict) and "models" in catalog else catalog
    return {
        r["id"]: (_number(r.get("input_cost_per_million")), _number(r.get("output_cost_per_million")))
        for r in rows or [] if isinstance(r, dict) and r.get("id")
    }


def check_blocked(model: str, response: dict[str, Any]) -> None:
    text = f"{(response or {}).get('error')} {(response or {}).get('content') or ''}"
    if not (response or {}).get("success") and any(m in text for m in _BLOCKED_MARKERS):
        raise ProviderBlocked(f"{model}: provider refuses on billing grounds: {str(response.get('error'))[:200]}")


class Ledger:
    """Cumulative spend across runs, persisted after every booking.

    ``cap`` is the cumulative ceiling for this run (``--cap``). Without a cap
    every paid call is refused; a dry run needs none.
    """

    def __init__(self, path: Any, cap: float | None = None, catalog: Any = "/shared/seeds/llm_models.yaml",
                 prices: dict[str, tuple[float | None, float | None]] | None = None):
        self.path = Path(path)
        self.cap = cap
        self.prices = prices if prices is not None else load_catalog_prices(catalog)
        self.state: dict[str, Any] = json.loads(self.path.read_text()) if self.path.exists() else {}
        self.state.setdefault("spent", 0.0)
        self.state.setdefault("calls", 0)
        self.state.setdefault("by_model", {})
        self.state.setdefault("reserve_charges", 0)
        self.state.setdefault("runs", [])
        self.start_spent = float(self.state["spent"])

    def price(self, model: str) -> tuple[float, float]:
        pin, pout = self.prices.get(model, (None, None))
        if not pin and not pout:
            raise PriceMissing(f"{model}: no catalog price in llm_models.yaml, refusing to call it")
        return float(pin or 0.0), float(pout or 0.0)

    def reserve(self, model: str) -> float:
        if model in RESERVE_USD:
            return RESERVE_USD[model]
        pin, pout = self.price(model)
        return max(MIN_RESERVE_USD, round((RESERVE_TOKENS[0] * pin + RESERVE_TOKENS[1] * pout) / 1e6, 3))

    def check(self, model: str) -> None:
        reserve = self.reserve(model)
        if self.cap is None:
            raise BudgetExceeded(f"stop: no --cap given, refusing a paid call to {model}")
        if self.state["spent"] + reserve > self.cap:
            raise BudgetExceeded(
                f"stop: spent ${self.state['spent']:.3f} + reserve ${reserve:.2f} for {model} exceeds cap ${self.cap:.2f}"
            )

    def _book(self, model: str, usd: float, tokens_in: int, tokens_out: int) -> float:
        self.state["spent"] += usd
        self.state["calls"] += 1
        m = self.state["by_model"].setdefault(model, {"calls": 0, "usd": 0.0, "in": 0, "out": 0})
        m["calls"] += 1
        m["usd"] += usd
        m["in"] += tokens_in
        m["out"] += tokens_out
        self.save()
        return usd

    def add(self, model: str, usage: dict[str, Any]) -> float:
        pin, pout = self.price(model)
        tin, tout = int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
        return self._book(model, tin * pin / 1e6 + tout * pout / 1e6, tin, tout)

    def charge_reserve(self, model: str, reason: str) -> float:
        usd = self.reserve(model)
        self.state["reserve_charges"] += 1
        m = self.state["by_model"].setdefault(model, {"calls": 0, "usd": 0.0, "in": 0, "out": 0})
        m["reserve_charges"] = m.get("reserve_charges", 0) + 1
        self.state.setdefault("reserve_log", []).append(
            {"model": model, "usd": usd, "reason": reason[:200], "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        )
        return self._book(model, usd, 0, 0)

    def added(self) -> float:
        return float(self.state["spent"]) - self.start_spent

    def record_run(self, info: dict[str, Any]) -> None:
        self.state["runs"].append(info)
        self.save()

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=1))
        tmp.replace(self.path)


def meter(service: Any, method: str, model: str, ledger: Ledger, calls: list[dict[str, Any]],
          guard: CanaryGuard | None = None) -> None:
    """Wrap one provider method on ``service`` with the guard and the ledger.

    Order per call: leakage guard (raises before anything is sent), catalog
    price (raises for an unpriced model), spend cap, then the call. A dry run
    (``PILOT_DRY_RUN=1``) returns a failed response without calling the
    provider. A call that raises is charged the model's reserve and re-raises.
    Re-wrapping an already metered method replaces the old wrapper, so a call
    is never metered twice.
    """
    current = getattr(service, method)
    original = getattr(current, "__pilot_original__", current)

    def metered(*args, **kwargs):
        prompt = kwargs.get("prompt")
        if prompt is None and args:
            prompt = args[0]
        prompt = prompt if isinstance(prompt, str) else ""
        system = kwargs.get("system_prompt") or ""
        system = system if isinstance(system, str) else ""
        if guard is not None:
            guard.check(system, prompt)
        ledger.price(model)
        dry = os.environ.get("PILOT_DRY_RUN", "")
        if dry != "1" or ledger.cap is not None:
            ledger.check(model)
        entry: dict[str, Any] = {
            "model": model, "seed": kwargs.get("seed"),
            "system_sha256": sha256_text(system), "prompt_sha256": sha256_text(prompt),
            "system_chars": len(system), "prompt_chars": len(prompt),
        }
        if dry == "1":
            entry.update(dry_run=True, usd=0.0, schema_bytes=len(json.dumps(kwargs.get("json_schema") or {})))
            calls.append(entry)
            return {"success": False, "error": "dry run", "usage": {}, "metadata": {"error_type": "dry_run"}}
        if dry == "billing":  # exercises the fail-fast without a provider call
            response = {"success": False, "error": "Error code: 429 credit_balance_exhausted", "usage": {}}
            ledger.add(model, {})
            check_blocked(model, response)
        started = time.monotonic()
        try:
            response = original(*args, **kwargs)
        except BaseException as exc:
            usd = ledger.charge_reserve(model, f"provider call raised {type(exc).__name__}")
            entry.update(exception=f"{type(exc).__name__}: {str(exc)[:300]}", usd=round(usd, 5),
                         reserve_charged=True, s=round(time.monotonic() - started, 1))
            calls.append(entry)
            raise
        response = response or {}
        usage = response.get("usage") or {}
        meta = response.get("metadata") or {}
        has_usage = bool(usage.get("prompt_tokens") or usage.get("completion_tokens"))
        if not response.get("success") and not has_usage and meta.get("error_type") == "timeout":
            # The provider may have generated tokens before the timeout.
            usd = ledger.charge_reserve(model, "timeout without usage")
            entry["reserve_charged"] = True
        else:
            usd = ledger.add(model, usage)
        entry.update({"in": usage.get("prompt_tokens"), "out": usage.get("completion_tokens"),
                      "usd": round(usd, 5), "s": round(time.monotonic() - started, 1),
                      "success": bool(response.get("success")), "error_type": meta.get("error_type"),
                      "finish_reason": meta.get("finish_reason")})
        calls.append(entry)
        check_blocked(model, response)
        return response

    metered.__pilot_original__ = original  # type: ignore[attr-defined]
    setattr(service, method, metered)


def usage_summary(calls: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        "calls": len(calls),
        "in": sum(int(c.get("in") or 0) for c in calls),
        "out": sum(int(c.get("out") or 0) for c in calls),
        "usd": round(sum(float(c.get("usd") or 0) for c in calls), 5),
    }


# ---------------------------------------------------------------------------
# Leakage guard
# ---------------------------------------------------------------------------

# Generic terms that mark the D2 exam (review decisions, section 4). They also
# occur in Martin's Musterlösung, so the guard removes the case text, the
# answer and the rubric under test before it looks for them. The distinctive
# phrases from Martin's sheet live in the git-ignored
# data/interim/human/canary_phrases.json: they quote his sheet, and this repo
# is public.
FIXED_CANARIES = ("Zweckveranlasser", "Maßnahmerichtung", "Massnahmerichtung", "Fortsetzungsfeststellung")
SENSITIVE_TASK_KEYS = ("bewertungsbogen", "korrekturhinweise", "exemplar_rubrics")
# The generator's validator-feedback retry appends its previous output after
# this marker. The model's own output is not instruction text.
CORRECTION_MARKER = "\n\n---\nKORREKTURAUFTRAG"
_MIN_CASE_SEGMENT = 20
_MIN_RUBRIC_SEGMENT = 4


def norm_text(text: Any) -> str:
    """Casefolded, NFC, whitespace-collapsed (so ß and ss match)."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(text or ""))).strip().casefold()


def strip_task_data(data: dict[str, Any] | None) -> dict[str, Any]:
    """Task data without the sheet, the grading hints and the exemplar rubrics."""
    return {k: v for k, v in (data or {}).items()
            if not (isinstance(k, str) and k.casefold() in SENSITIVE_TASK_KEYS)}


def load_canary_phrases(path: Any) -> list[str]:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    phrases = [str(p).strip() for p in doc.get("phrases") or [] if str(p).strip()]
    if not phrases:
        raise ValueError(f"{path}: no canary phrases")
    return phrases


class CanaryGuard:
    """Asserts that no canary term reaches a guarded prompt.

    Two tiers, both case-insensitive. The distinctive sheet phrases never
    occur in the case text, so they are searched in everything except the
    Sachverhalt, the Musterlösung and the answer under test. The generic
    terms do occur in the Musterlösung and legitimately in a rubric derived
    from it, so the rubric under test (its text, step names, requirements
    and keys) is removed as well before they are searched. What remains is
    the instrument itself: system prompt, template, rules, key map.
    """

    def __init__(self, phrases: Iterable[str], fixed: Iterable[str] = FIXED_CANARIES, mode: str = "raise"):
        if mode not in ("raise", "warn"):
            raise ValueError("guard mode must be 'raise' or 'warn'")
        self.phrases = self._unique(phrases)
        self.fixed = self._unique(fixed)
        self.mode = mode
        self.label: str | None = None
        self.case: list[str] = []
        self.rubric: list[str] = []
        self.warnings: list[str] = []
        self.checked = 0

    @staticmethod
    def _unique(terms: Iterable[str]) -> list[str]:
        """Distinct after normalisation (Maßnahmerichtung == Massnahmerichtung)."""
        seen: dict[str, str] = {}
        for term in (str(x).strip() for x in terms):
            if term and norm_text(term) not in seen:
                seen[norm_text(term)] = term
        return list(seen.values())

    @property
    def armed(self) -> bool:
        return self.label is not None

    def arm(self, label: str, case_texts: Iterable[Any] = (), rubric_texts: Iterable[Any] = ()) -> None:
        self.label = label
        self.case = sorted({t for t in map(norm_text, case_texts) if len(t) >= _MIN_CASE_SEGMENT},
                           key=len, reverse=True)
        self.rubric = sorted({t for t in map(norm_text, rubric_texts) if len(t) >= _MIN_RUBRIC_SEGMENT},
                             key=len, reverse=True)

    def disarm(self) -> None:
        self.label = None
        self.case, self.rubric = [], []

    def hits(self, system: str, prompt: str) -> list[str]:
        found: list[str] = []
        for part, raw in (("system", system or ""), ("user", prompt or "")):
            cut = raw.find(CORRECTION_MARKER)
            text = norm_text(raw[:cut] if cut >= 0 else raw)
            for segment in self.case:
                text = text.replace(segment, " ")
            found += [f"{p!r} in the {part} prompt" for p in self.phrases if norm_text(p) in text]
            for segment in self.rubric:
                text = text.replace(segment, " ")
            found += [f"{t!r} in the {part} prompt" for t in self.fixed if norm_text(t) in text]
        return list(dict.fromkeys(found))

    def check(self, system: str, prompt: str) -> None:
        if not self.armed:
            return
        self.checked += 1
        found = self.hits(system, prompt)
        if not found:
            return
        message = (f"leakage guard ({self.label}): " + "; ".join(found)
                   + " (outside the case text, the answer and the rubric under test)")
        if self.mode == "warn":
            self.warnings.append(message)
            print("CANARY WARNING (dry run, not raised): " + message, flush=True)
            return
        raise LeakageDetected(message)


# ---------------------------------------------------------------------------
# Spec adapter: platform rubric or Martin's sheet -> checklist spec
# ---------------------------------------------------------------------------

SPEC_VERSION = 1
DEFAULT_ARBEITSERGEBNIS = {"id": "P1", "bezeichnung": "Gutachten", "art": "gutachten", "fundstelle_aufgabe": None}
ADAPTER_UNITS = ("step", "rating")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def spec_from_rubric(criteria: dict[str, Any] | None = None, structure: dict[str, Any] | None = None,
                     total_points: Any = None) -> dict[str, Any]:
    """A checklist spec for the step and rating units from a platform rubric.

    Same key layout as ``benger_extended.workers.bewertungsbogen_checklist.
    checklist_spec`` (work products under ``arbeitsergebnisse``), with empty
    requirement lists, no Weichenstellungen and one work product. The steps
    follow the outline: the structure's step order when there is one, else
    the ``sNN_`` ordinals (``rubric_structure.order_criteria_keys``). Without
    flat criteria (Martin's sheet) they are derived from the structure.
    """
    from rubric_structure import (
        criteria_from_structure,
        order_criteria_keys,
        validate_structure,
    )

    if not isinstance(criteria, dict) or not criteria:
        if not isinstance(structure, dict) or validate_structure(structure):
            raise ValueError("rubric has neither flat criteria nor a valid structure")
        criteria = criteria_from_structure(structure)
    order = order_criteria_keys(criteria, structure if isinstance(structure, dict) else None)
    nodes = {n.get("key"): n for n in ((structure or {}).get("nodes") or [])
             if isinstance(n, dict) and n.get("kind") == "step"} if isinstance(structure, dict) else {}
    steps: dict[str, dict[str, Any]] = {}
    for key in order:
        criterion = criteria[key]
        if not isinstance(criterion, dict) or not _is_number(criterion.get("max_score")) or criterion["max_score"] <= 0:
            raise ValueError(f"step {key!r}: no usable max_score")
        node = nodes.get(key) or {}
        steps[key] = {
            "step_id": str(node.get("id") or key),
            "name": str(criterion.get("name") or node.get("title") or key).strip(),
            "max_score": float(criterion["max_score"]),
            "anforderungen": [],
            "keine_punkte": None,
            "weichenstellung": None,
            "arbeitsergebnis_id": DEFAULT_ARBEITSERGEBNIS["id"],
            "hilfsgutachten": None,
        }
    total = sum(s["max_score"] for s in steps.values())
    if total_points is not None and abs(float(total_points) - total) > 1e-6:
        raise ValueError(f"steps sum to {total}, the rubric says {total_points}")
    return {
        "version": SPEC_VERSION,
        "allocation_mode": None,
        "total_points": float(total_points if total_points is not None else total),
        "order": list(order),
        "steps": steps,
        "loesungsweg_steps": {},
        "weichenstellungen": [],
        "arbeitsergebnisse": [dict(DEFAULT_ARBEITSERGEBNIS, step_keys=list(order))],
        "hilfsgutachten": {"verlangt": False, "wortlaut": None},
    }


def spec_from_sheet(sheet: dict[str, Any]) -> dict[str, Any]:
    """Martin's sheet (``heidebach_exam.json`` ``sheet``) as a checklist spec."""
    spec = spec_from_rubric(None, sheet["structure"], sheet.get("total_points"))
    if sheet.get("step_keys") and spec["order"] != list(sheet["step_keys"]):
        raise ValueError("sheet step order differs from its step_keys")
    return spec


def sheet_title(bewertungsbogen_text: str) -> str | None:
    first = (bewertungsbogen_text or "").splitlines()[0] if bewertungsbogen_text else ""
    match = re.match(r"BEWERTUNGSBOGEN: (.+) \(insgesamt ", first)
    return match.group(1) if match else None


def render_sheet_text(exam: dict[str, Any]) -> str:
    """The judge-facing rendering of Martin's sheet.

    ``bewertungsbogen_text`` is the task-data mirror, which appends a
    Notenschlüssel block that the judge prompt never carries. The judge text
    is rendered from the structure with the platform renderer instead, under
    the same title.
    """
    from rubric_structure import render_structure_text

    sheet = exam["sheet"]
    return render_structure_text(sheet["structure"], sheet.get("total_points"),
                                 title=sheet_title(exam.get("bewertungsbogen_text") or ""))


def exam_grade_scale(key: dict[str, Any], total_points: Any = 100) -> dict[str, Any]:
    """The exam's grade key as a platform percent scale (``grade_scale``)."""
    from rubric_structure import GRADE_SCALE_PRESETS

    thresholds = key.get("thresholds_be") or key.get("thresholds")
    total = float(total_points or 100)
    percent = [round(t / total * 100, 6) for t in thresholds]
    percent = [int(p) if float(p).is_integer() else p for p in percent]
    preset = next((name for name, values in GRADE_SCALE_PRESETS.items() if list(values) == percent), "custom")
    return {"unit": "percent", "preset": preset, "thresholds": percent,
            "rounding": key.get("rounding") or "floor", "pass_grade": int(key.get("pass_grade", 4))}


def guard_rubric_texts(rendered: str | None, spec: dict[str, Any] | None,
                       criteria: dict[str, Any] | None = None) -> list[str]:
    """Everything that belongs to the rubric under test, for the guard."""
    texts: list[str] = [rendered or ""]
    for key, crit in (criteria or {}).items():
        texts.append(key)
        if isinstance(crit, dict):
            texts += [str(crit.get(f) or "") for f in ("name", "description", "rubric")]
    if spec:
        for key, step in list((spec.get("steps") or {}).items()) + list((spec.get("loesungsweg_steps") or {}).items()):
            texts += [key, str(step.get("name") or "")]
            texts += [str(b.get("text") or "") for b in step.get("anforderungen") or []]
        for w in spec.get("weichenstellungen") or []:
            texts.append(str(w.get("bezeichnung") or ""))
            for z in w.get("loesungswege") or []:
                texts.append(str(z.get("bezeichnung") or ""))
                texts += [str(a) for a in z.get("vertretbarkeitsanforderungen") or []]
    return [t for t in texts if t]


# ---------------------------------------------------------------------------
# Probe builders
# ---------------------------------------------------------------------------

RESULT_ADJECTIVES = ("zulässig", "begründet", "gegeben", "erfüllt", "anwendbar", "einschlägig",
                     "rechtmäßig", "rechtswidrig", "wirksam", "ersatzfähig", "verletzt")
_COPULA = {"ist", "sind", "war", "waren", "wäre", "wären"}
_LIEGEN = {"liegt", "liegen", "lag", "lagen"}
_VORLIEGEN = {"vorliegt", "vorliegen", "vorlag", "vorlagen"}
_BESTEHEN = {"besteht", "bestehen", "bestand"}
_SUBORDINATORS = {"dass", "sodass", "weil", "da", "obwohl", "nachdem", "womit", "wodurch", "weshalb",
                  "wonach", "indem", "damit"}
# Clauses that ask or assume rather than state a result.
_SKIP_CLAUSE = re.compile(r"\b(?:ob|wenn|falls|sofern|soweit|fraglich|problematisch|zu prüfen|zu klären)\b")
_KEIN = re.compile(r"^kein(?:e|en|em|er|es)?$")
_EIN = re.compile(r"^ein(?:e|en|em|er|es)?$")
_MARKERS = {"(+)": "(-)", "(-)": "(+)", "(–)": "(+)", "(−)": "(+)"}
_MARKER_RE = re.compile(r"\((?:\+|-|–|−)\)")
_ABBREVIATIONS = {"abs", "art", "s", "nr", "lit", "var", "alt", "hs", "rn", "vgl", "bzw", "ggf", "gem", "sog",
                  "z.b", "u.a", "d.h", "i.s.d", "i.v.m", "ivm", "aufl", "bd", "f", "ff", "m.w.n", "str", "evtl",
                  "insb", "etc", "ca", "zb"}
_WORD_CHARS = "„“\"'()[]"


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    """Sentence spans: line breaks, and [.!?] + space unless an abbreviation."""
    spans: list[tuple[int, int]] = []
    start = 0
    for match in re.finditer(r"\n+|(?<=[.!?])\s+", text):
        if not match.group(0).startswith("\n"):
            before = text[start:match.start()].rsplit(None, 1)
            word = before[-1] if before else ""
            core = word.rstrip(".!?").lstrip(_WORD_CHARS).casefold()
            if core in _ABBREVIATIONS or len(core) <= 1 or core.isdigit() or re.fullmatch(r"[ivx]+", core):
                continue
        if match.start() > start:
            spans.append((start, match.start()))
        start = match.end()
    if start < len(text):
        spans.append((start, len(text)))
    return spans


def _flip_clause(clause: str) -> tuple[str, int]:
    """Toggle the polarity of the first result statement in one clause."""
    if _SKIP_CLAUSE.search(clause.casefold()):
        return clause, 0
    # Token spans cover the word only, so an edit never eats punctuation.
    tokens = []
    for m in re.finditer(r"\S+", clause):
        raw = m.group(0)
        core = raw.strip(_WORD_CHARS + ".!?")
        if not core:
            continue
        start = m.start() + raw.index(core)
        tokens.append((start, start + len(core), core.casefold()))
    words = [t[2] for t in tokens]
    subordinate = bool(words) and words[0] in _SUBORDINATORS

    def remove(i: int) -> str:
        s, e, _ = tokens[i]
        s = s - 1 if s > 0 and clause[s - 1] == " " else s
        return clause[:s] + clause[e:]

    def insert_before(i: int) -> str:
        s = tokens[i][0]
        return clause[:s] + "nicht " + clause[s:]

    def swap_article(i: int, add_k: bool) -> str:
        s, e, _ = tokens[i]
        word = clause[s:e]
        if add_k:
            new = ("K" if word[0].isupper() else "k") + word[0].lower() + word[1:]
        else:
            new = word[1].upper() + word[2:] if word[0].isupper() else word[1:]
        return clause[:s] + new + clause[e:]

    # 1. copula + result adjective, both orders: "ist (nicht) zulässig" / "(nicht) zulässig ist"
    for j, word in enumerate(words):
        if word not in RESULT_ADJECTIVES or j == 0:
            continue
        for i, verb in enumerate(words):
            if verb not in _COPULA or abs(i - j) > 12:
                continue
            lo, hi = (i, j) if i < j else (j - 1, i)
            window = range(max(lo, 0), hi)
            neg = next((k for k in window if words[k] == "nicht"), None)
            if any(_KEIN.match(words[k]) for k in window):
                return clause, 0
            return (remove(neg), 1) if neg is not None else (insert_before(j), 1)
    # 2. "liegt (nicht) ... vor" / "... (nicht) vorliegt"
    for i, word in enumerate(words):
        if word in _LIEGEN:
            vor = next((k for k in range(i + 1, min(i + 8, len(words))) if words[k] == "vor"), None)
            if vor is None:
                continue
            window = range(i + 1, vor)
            target = vor
        elif word in _VORLIEGEN and i > 0:
            window = range(max(0, i - 5), i)
            target = i
        else:
            continue
        neg = next((k for k in window if words[k] == "nicht"), None)
        if neg is not None:
            return remove(neg), 1
        kein = next((k for k in window if _KEIN.match(words[k])), None)
        if kein is not None:
            return swap_article(kein, add_k=False), 1
        return insert_before(target), 1
    # 3. "besteht (nicht)", "es besteht (k)ein ..."
    for i, word in enumerate(words):
        if word not in _BESTEHEN:
            continue
        before = range(max(0, i - 4), i)
        if i + 1 < len(words):
            nxt = words[i + 1]
            if nxt == "nicht":
                return remove(i + 1), 1
            if _KEIN.match(nxt):
                return swap_article(i + 1, add_k=False), 1
            if _EIN.match(nxt):
                return swap_article(i + 1, add_k=True), 1
        neg = next((k for k in before if words[k] == "nicht"), None)
        if neg is not None:
            return remove(neg), 1
        kein = next((k for k in before if _KEIN.match(words[k])), None)
        if kein is not None:
            return swap_article(kein, add_k=False), 1
        if subordinate or i + 1 < len(words):
            return insert_before(i), 1
        end = tokens[i][1]
        return clause[:end] + " nicht" + clause[end:], 1
    return clause, 0


def negation_flip(text: str) -> tuple[str, int, int]:
    """(text with result polarity flipped, sentences flipped, flips).

    Deterministic. Per clause (split at , ; :) the first result statement is
    toggled: "ist (nicht) <zulässig|begründet|…>" in either word order,
    "liegt (nicht) vor" / "(nicht) vorliegt", "besteht (nicht)" with "kein"
    and "ein" swapped where the negation sits in the article, and every
    "(+)" / "(-)" marker. Clauses that ask or assume ("ob", "wenn",
    "fraglich", …) stay as they are.
    """
    out: list[str] = []
    pos = 0
    sentences = flips = 0
    for start, end in _sentence_spans(text or ""):
        out.append(text[pos:start])
        sentence = text[start:end]
        parts = re.split(r"([,;:])", sentence)
        n = 0
        for idx in range(0, len(parts), 2):
            clause = parts[idx]
            stripped = _MARKER_RE.sub("", clause)
            if stripped != clause:
                markers = len(_MARKER_RE.findall(clause))
                clause = _MARKER_RE.sub(lambda m: _MARKERS[m.group(0)], clause)
                n += markers
            clause, k = _flip_clause(clause)
            parts[idx] = clause
            n += k
        out.append("".join(parts))
        if n:
            sentences += 1
            flips += n
        pos = end
    out.append((text or "")[pos:])
    return "".join(out), sentences, flips


# --- result swap (G0' amendment, DESIGN.md 2026-09-26) ---
_PAIRS = [("unzulässig", "zulässig"), ("unbegründet", "begründet"), ("rechtswidrig", "rechtmäßig"),
          ("unstatthaft", "statthaft"), ("erfolglos", "erfolgreich"), ("unwirksam", "wirksam"),
          ("unverhältnismäßig", "verhältnismäßig"), ("unanwendbar", "anwendbar")]
_SWAP = {}
for neg, pos in _PAIRS:
    _SWAP[neg] = pos; _SWAP[pos] = neg
_RESULT_WORDS = sorted(set(_SWAP) | {"gegeben", "erfüllt", "eröffnet", "einschlägig", "anzunehmen", "zu bejahen",
                                      "zu verneinen", "verletzt", "vorliegend"}, key=len, reverse=True)
_ENDING = r"(?:e|er|en|em|es)?"
_NICHT_RESULT = re.compile(r"\bnicht\s+(mehr\s+)?(" + "|".join(map(re.escape, _RESULT_WORDS)) + r")" + _ENDING + r"\b", re.I)
_WORD = re.compile(r"\b(" + "|".join(map(re.escape, sorted(_SWAP, key=len, reverse=True))) + r")(" + _ENDING + r")\b", re.I)
_PHRASES = [(re.compile(r"\bkeinen Erfolg\b"), "Erfolg"), (re.compile(r"\b(hat|haben|hätte|wird)((?:\s+\w+){0,2}?)\s+Erfolg\b"), r"\1\2 keinen Erfolg")]
_BEJAHEN = [(re.compile(r"\bzu bejahen\b"), "zu verneinen"), (re.compile(r"\bzu verneinen\b"), "zu bejahen"),
            (re.compile(r"\bbejaht\b"), "verneint"), (re.compile(r"\bverneint\b"), "bejaht")]
_RESULT_START = re.compile(r"^[\s#*>_\-\d.()]*?(?:[IVX]+\.|[a-z]\)|\d+\.)?\s*\**(Somit|Damit|Daher|Folglich|Also|Mithin|Demnach|Deshalb|Insgesamt|Im Ergebnis|Ergebnis|Zwischenergebnis|Gesamtergebnis|Endergebnis)\b")
_HEADING_LINE = re.compile(r"^\s*(#+\s|\*\*[^*]{1,80}\*\*\s*$|[A-HIVX]+\.\s|\d+\.\s)", re.M)

def _case(src, dst):
    return dst[0].upper() + dst[1:] if src[:1].isupper() else dst

_NOT_A_RESULT = re.compile(r"\b(wenn|soweit|sofern|falls|ob|könnte|könnten|kommt|kämen?|vertretbar|fraglich|dahinstehen|offenbleiben|offen bleiben|nicht erörtert)\b", re.I)


def swap_sentence(s):
    """Swap every result polarity in the sentence at once (consistent)."""
    n = 0
    tokens = {}
    def protect(val):
        key = f"\x00{len(tokens)}\x00"; tokens[key] = val; return key
    def drop_nicht(m):
        nonlocal n; n += 1
        return protect(("noch " if m.group(1) else "") + m.group(0)[m.group(0).lower().find(m.group(2).lower()):])
    out = _NICHT_RESULT.sub(drop_nicht, s)
    def word(m):
        nonlocal n; n += 1
        return protect(_case(m.group(1), _SWAP[m.group(1).lower()]) + m.group(2))
    out = _WORD.sub(word, out)
    for pat, rep in _PHRASES + _BEJAHEN:
        out, k = pat.subn(lambda m, rep=rep: protect(m.expand(rep)), out); n += k
    k = len(_MARKER_RE.findall(out)); out = _MARKER_RE.sub(lambda m: protect(_MARKERS[m.group(0)]), out); n += k
    if n == 0:
        parts = re.split(r"([,;:])", out)
        for i in range(0, len(parts), 2):
            parts[i], k = _flip_clause(parts[i]); n += k
            if k: break
        out = "".join(parts)
    for key, val in tokens.items(): out = out.replace(key, val)
    return out, n

def result_sentences(text):
    spans = _sentence_spans(text or "")
    heads = [m.start() for m in _HEADING_LINE.finditer(text or "")] + [len(text or "")]
    closing = set()
    for i, (a, b) in enumerate(spans):
        nxt = spans[i + 1][0] if i + 1 < len(spans) else len(text)
        if any(b <= h <= nxt for h in heads) and not _HEADING_LINE.match(text[a:b].strip() + "\n"):
            closing.add(i)
    return spans, closing

def result_swap(text: str) -> tuple[str, int, list[tuple[str, str]]]:
    """(text with every result statement swapped, swapped sentences, pairs).

    Deterministic. A result statement is the closing sentence of a section
    (the sentence before a heading: in Gutachtenstil the section's result),
    a sentence opening with a result marker (Somit, Damit, Daher, Folglich,
    Im Ergebnis, Zwischenergebnis …), a sentence under an Ergebnis heading,
    or one with a "(+)" / "(-)" mark. Obersätze and hypotheses ("wenn",
    "ob", "könnte", "kommt … in Betracht", "vertretbar") are left alone.
    Every polarity in a result sentence is swapped at once, consistently:
    "nicht X" loses its "nicht" ("nicht mehr" becomes "noch"), antonym
    pairs swap (zulässig/unzulässig, begründet/unbegründet,
    rechtmäßig/rechtswidrig …), "(keinen) Erfolg", bejahen/verneinen and the
    marks swap; only a sentence without any of these gets a "nicht" toggle.
    """
    spans, closing = result_sentences(text)
    out, pos, swapped = [], 0, []
    under = False
    for i, (a, b) in enumerate(spans):
        out.append(text[pos:a]); s = text[a:b]
        m = re.match(r"^\s*#+\s*(.*)", s)
        if m: under = "ergebnis" in m.group(1).lower()
        if _NOT_A_RESULT.search(s):
            pass  # Obersatz, hypothesis or a marked alternative: not a result statement
        elif i in closing or _RESULT_START.match(s) or under or _MARKER_RE.search(s):
            new, n = swap_sentence(s)
            if n and new != s: swapped.append((s, new)); s = new
        out.append(s); pos = b
    out.append(text[pos:])
    return "".join(out), len(swapped), swapped


NORM_RE = re.compile(
    r"(?:§§?|Art\.)\s*\d+[a-z]?\b"
    r"(?:\s*(?:Abs\.|Absatz|S\.|Satz|Nr\.|lit\.|Hs\.|Alt\.|Var\.)\s*(?:\d+[a-z]?\b|[a-z]\b)"
    r"|\s+[IVX]+\b|\s+\d+\b(?!\s*(?:BE|Punkte|NP)))*"
    r"(?:\s*ff?\.)?"
    r"(?:\s+[A-ZÄÖÜ][A-Za-zäöüß]*[A-ZÄÖÜ][A-Za-zäöüß]*)?"
)
KEY_TERM_RE = re.compile(r"\b[A-ZÄÖÜ][A-Za-zÄÖÜäöüß-]{7,}")


def keyword_salad(rubric_text: str, step_names: Iterable[str], seed_key: str) -> tuple[str, dict[str, Any]]:
    """(salad, meta): the rubric's norms and key terms, shuffled, no sentences.

    Norms are the § / Art. citations of the rubric text; key terms are the
    capitalised words of at least 8 characters in the step names. Duplicates
    are dropped (case-insensitive) and the list is shuffled with a seed
    derived from ``seed_key``, one item per line.
    """
    norms = [re.sub(r"\s+", " ", m.group(0)).strip() for m in NORM_RE.finditer(rubric_text or "")]
    terms = [t.strip("-") for name in step_names for t in KEY_TERM_RE.findall(str(name or ""))]
    items: list[str] = []
    seen = set()
    for item in norms + terms:
        folded = item.casefold()
        if item and folded not in seen:
            seen.add(folded)
            items.append(item)
    rng = random.Random(int(hashlib.sha256(seed_key.encode("utf-8")).hexdigest()[:16], 16))
    rng.shuffle(items)
    n_norms = len({n.casefold() for n in norms})
    return "\n".join(items), {"norms": n_norms, "terms": len(items) - n_norms, "items": len(items)}


# ---------------------------------------------------------------------------
# Arms and result helpers
# ---------------------------------------------------------------------------

SCORE_UNITS = ("bullet", "step", "rating")
ALTERNATIVES = ("branch", "replace")


def parse_arm(text: str) -> dict[str, Any]:
    """``martin:<unit>[:<alternatives>]`` or ``rubric:<id>:<unit>[:<alternatives>]``."""
    parts = text.split(":")
    if parts[0] == "martin" and len(parts) in (2, 3):
        arm = {"id": text, "source": "martin", "rubric_id": None, "unit": parts[1],
               "alternatives": parts[2] if len(parts) == 3 else "branch"}
    elif parts[0] == "rubric" and len(parts) in (3, 4) and parts[1]:
        arm = {"id": text, "source": "rubric", "rubric_id": parts[1], "unit": parts[2],
               "alternatives": parts[3] if len(parts) == 4 else "branch"}
    else:
        raise ValueError(f"arm {text!r}: expected martin:<unit>[:<alt>] or rubric:<id>:<unit>[:<alt>]")
    if arm["unit"] not in SCORE_UNITS:
        raise ValueError(f"arm {text!r}: unit must be one of {SCORE_UNITS}")
    if arm["alternatives"] not in ALTERNATIVES:
        raise ValueError(f"arm {text!r}: alternatives must be one of {ALTERNATIVES}")
    if arm["unit"] == "bullet" and arm["alternatives"] == "replace":
        raise ValueError(f"arm {text!r}: replace mode is not defined for the bullet unit")
    return arm


_CREDIT = {0: 0.0, 1: 0.5, 2: 1.0}


def model_total(result: dict[str, Any], spec: dict[str, Any] | None, unit: str | None) -> float | None:
    """The total the model proposed before evidence verification.

    Checklist lane: over the primary path's steps (the declared path of a
    judgment that follows the Musterlösung). Product lane: the model scores.
    """
    scores = result.get("scores") if isinstance(result, dict) else None
    if not isinstance(scores, dict):
        return None
    if spec is None or not isinstance(result.get("checklist"), dict):
        return sum(float(s.get("model_score", s.get("score", 0)) or 0) for s in scores.values() if isinstance(s, dict))
    total = 0.0
    for key in spec.get("order") or []:
        step, entry = spec["steps"][key], scores.get(key) or {}
        mx = float(step["max_score"])
        if unit == "bullet":
            bullets = entry.get("anforderungen") or {}
            total += sum(mx * float(b.get("share") or 0) * _CREDIT.get(int((bullets.get(f"b{i}") or {}).get("model_status") or 0), 0.0)
                         for i, b in enumerate(step.get("anforderungen") or [], start=1))
        elif unit == "rating":
            total += mx * float(entry.get("model_note") or 0) / 18
        else:
            total += float(entry.get("model_score") or 0)
    return total
