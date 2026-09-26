#!/usr/bin/env python3
"""Build the local D2 pack: Martin Heidebach's Polizeirecht exam, his 46-step
Bewertungsbogen, and every human- or model-graded script of that exam.

Two cohorts of the same case (the Hinterwalde festival; only dates and two
words differ between the yearly versions):

  D2a  15 typed PDF scripts from the 2024/2025 runs (H01-H15), each with
       Martin's per-step BE in the matching Korrekturbogen xlsx ("Ihre BE").
  D2b  25 submissions written on the platform in September 2026 (P01-P25),
       with the stored instant rubric-judge grades and Martin's human
       Korrektur where it exists. Read from a read-only prod pull that lives
       in data/raw (the pull itself is not scripted in this public repo).

Everything this script writes is personal data or third-party exam text and
stays in data/interim/human/ (git-ignored). E-mail addresses are removed
from every text; D2b user ids are replaced by P-codes (key kept in raw/).

Inputs  (data/raw/human/heidebach_polr/, git-ignored):
  rubric/Korrekturbogen_BE.xlsx, scripts/H??.{pdf,xlsx},
  platform_2026/prod_2ad6d500_pull_*.jsonl
Outputs (data/interim/human/, git-ignored):
  heidebach_exam.json     case text, Musterloesung, sheet structure, key
  heidebach_scripts.json  40 scripts: text + human and stored model grades
Needs: pdftotext (poppler).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
PLATFORM = HERE.parent.parent
sys.path[:0] = [str(PLATFORM / "services" / "shared"), str(PLATFORM / "services" / "api")]

from services.rubric_import import _read_xlsx_grid, parse_rubric_file  # noqa: E402

RAW = HERE / "data" / "raw" / "human" / "heidebach_polr"
OUT = HERE / "data" / "interim" / "human"
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Martin's key (identical to the prod project's custom key): BE thresholds
# for 1..18 Notenpunkte, totals rounded down ("bei 0,5 BE wird abgerundet").
MARTIN_THRESHOLDS = [10, 20, 30, 40, 44, 48, 52, 56, 60, 64, 68, 72, 76, 80, 84, 88, 92, 96]
PASS_GRADE = 4


def scrub(text: str) -> str:
    return EMAIL.sub("[E-Mail entfernt]", text or "")


def grade(total_be: float) -> int:
    return sum(1 for t in MARTIN_THRESHOLDS if int(total_be) >= t)


def sheet_steps():
    res = parse_rubric_file("Korrekturbogen_BE.xlsx", (RAW / "rubric" / "Korrekturbogen_BE.xlsx").read_bytes())
    nodes = res["structure"]["nodes"]
    steps = [n for n in nodes if n["kind"] == "step"]
    assert len(steps) == 46 and res["total_points"] == 100, (len(steps), res["total_points"])
    return res, steps


def human_grades(xlsx: Path, steps):
    """Per-step 'Ihre BE' aligned to the sheet's 46 step rows (blank = 0).

    Martin revised his allocation between years: the 2024 scripts were graded
    on an earlier version with the same 46 steps and 100 BE but different
    maxima on several steps. The maxima of the sheet actually used are kept
    per script, and ``sheet_version`` says whether they match the current one.
    """
    rows = []
    total_cell = None
    for _r, cells in _read_xlsx_grid(xlsx.read_bytes()):
        label = str(cells.get(0, "")).strip()
        if label.startswith("Gesamt-BE"):
            total_cell = float(str(cells.get(2) or 0))
            break
        try:
            mx = float(str(cells.get(1)))
        except (TypeError, ValueError):
            continue
        got = str(cells.get(2) or "").strip()
        rows.append((mx, float(got) if got else 0.0))
    assert len(rows) == len(steps), (xlsx.name, len(rows))
    maxima = [mx for mx, _ in rows]
    assert abs(sum(maxima) - 100) < 1e-9, (xlsx.name, sum(maxima))
    current = all(abs(mx - float(st["max_score"])) < 1e-9 for mx, st in zip(maxima, steps))
    per_step = {step["key"]: be for (_, be), step in zip(rows, steps)}
    for (mx, be), step in zip(rows, steps):
        assert 0 <= be <= mx, (xlsx.name, step["key"], be, mx)
    total = sum(per_step.values())
    assert total_cell is not None and abs(total - total_cell) < 1e-9, (xlsx.name, total, total_cell)
    return {"steps": per_step, "total": total, "grade_points": grade(total),
            "passed": grade(total) >= PASS_GRADE, "grader": "martin_heidebach",
            "sheet_version": "current" if current else "earlier",
            "step_maxima": {step["key"]: mx for mx, step in zip(maxima, steps)}}


def pdf_text(pdf: Path):
    text = subprocess.run(["pdftotext", "-enc", "UTF-8", str(pdf), "-"],
                          capture_output=True, text=True, check=True).stdout
    pages = text.count("\f") + 1
    text = text.replace("\f", "\n")
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n[ ]*\d{1,2}[ ]*\n", "\n", text)       # bare page numbers
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return scrub(text), pages


def cohort_hint(text: str) -> str | None:
    m = re.search(r"\b(2024|2025)\b", text[:400])
    return m.group(1) if m else None


def stored_scores(details, keys_in_order):
    scores = details.get("scores") or {}
    out = {}
    for key in keys_in_order:
        s = scores.get(key) or {}
        entry = {"score": s.get("score"), "max": s.get("max")}
        for extra in ("evidence_verified", "model_score"):
            if extra in s:
                entry[extra] = s[extra]
        out[key] = entry
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    res, steps = sheet_steps()
    keys = [s["key"] for s in steps]

    # ---- D2a: PDF scripts + Martin's xlsx grades --------------------------------
    scripts = []
    for pdf in sorted((RAW / "scripts").glob("H??.pdf")):
        text, pages = pdf_text(pdf)
        scripts.append({"script_id": pdf.stem, "cohort": "D2a", "year_hint": cohort_hint(text),
                        "source": "pdf", "pages": pages, "chars": len(text), "text": text,
                        "human": human_grades(pdf.with_suffix(".xlsx"), steps), "llm_prod": None})

    # ---- D2b: prod pull ------------------------------------------------------------
    pulls = sorted((RAW / "platform_2026").glob("prod_2ad6d500_pull_*.jsonl"))
    rows = [json.loads(line) for line in pulls[-1].read_text().splitlines() if line.strip()]
    end = next(r for r in rows if r["kind"] == "end")
    exam = next(r for r in rows if r["kind"] == "exam")
    annotations = sorted((r for r in rows if r["kind"] == "annotation"), key=lambda r: r["created_at"])
    evaluations = [r for r in rows if r["kind"] == "evaluation"]
    assert len(annotations) == end["n_annotations"] and len(evaluations) == end["n_evaluations"]

    rubric = exam["rubric"]
    prod_steps = [n for n in (rubric.get("structure") or {}).get("nodes", []) if n.get("kind") == "step"]
    prod_keys = [n["key"] for n in prod_steps]
    assert [float(n["max_score"]) for n in prod_steps] == [float(s["max_score"]) for s in steps], \
        "prod sheet differs from Martin's xlsx"
    key_map = dict(zip(prod_keys, keys))  # prod key -> xlsx key (same order, same maxima)

    pseudonyms = {a["annotation_id"]: f"P{i:02d}" for i, a in enumerate(annotations, 1)}
    (RAW / "platform_2026" / "KEY.local.json").write_text(json.dumps(
        {"note": "LOCAL ONLY. P-code -> prod annotation/user id. Never share.",
         "codes": {pseudonyms[a["annotation_id"]]: {"annotation_id": a["annotation_id"], "user_id": a["user_id"]}
                   for a in annotations}}, indent=1))

    by_annotation = {}
    for ev in evaluations:
        by_annotation.setdefault(ev["annotation_id"], []).append(ev)
    for a in annotations:
        answer = next((e["value"].get("markdown") for e in a["result"]
                       if e.get("from_name") == "loesung" and isinstance(e.get("value"), dict)), "") or ""
        text = scrub(answer)
        llm, human = None, None
        for ev in by_annotation.get(a["annotation_id"], []):
            metrics = ev["metrics"] or {}
            if "llm_judge_rubric" in metrics:
                d = metrics["llm_judge_rubric"].get("details") or {}
                llm = {"judge_model_id": ev.get("judge_model_id"), "created_at": ev["created_at"],
                       "total": d.get("total_score"), "grade_points": d.get("grade_points"),
                       "passed": d.get("passed"), "rubric_id": d.get("rubric_id"),
                       "steps": {key_map[k]: v for k, v in stored_scores(d, prod_keys).items()}}
            if "korrektur_custom" in metrics:
                d = metrics["korrektur_custom"].get("details") or {}
                per_step = {key_map[k]: (v.get("score") or 0.0) for k, v in stored_scores(d, prod_keys).items()}
                human = {"steps": per_step, "total": d.get("total_score"),
                         "grade_points": d.get("grade_points"), "passed": d.get("passed"),
                         "grader": "martin_heidebach" if ev.get("created_by") == "<user-id>"
                         else "other", "created_at": ev["created_at"]}
        scripts.append({"script_id": pseudonyms[a["annotation_id"]], "cohort": "D2b", "year_hint": "2026",
                        "source": "platform", "chars": len(text), "text": text,
                        "submitted_at": a["created_at"][:10], "human": human, "llm_prod": llm})

    data = exam["data"]
    (OUT / "heidebach_exam.json").write_text(json.dumps({
        "note": "D2 exam (2026 version, as graded on the platform). bewertungsbogen_text is Martin's "
                "sheet rendered into task data: NEVER give it to a generator or a holistic judge.",
        "sachverhalt": scrub(data.get("sachverhalt", "")),
        "musterloesung": scrub(data.get("musterloesung", "")),
        "bewertungsbogen_text": scrub(data.get("bewertungsbogen", "")),
        "sheet": {"total_points": res["total_points"], "structure": res["structure"],
                  "step_keys": keys, "prod_rubric_id": rubric["id"]},
        "grade_scale": {"thresholds_be": MARTIN_THRESHOLDS, "rounding": "floor", "pass_grade": PASS_GRADE},
    }, ensure_ascii=False, indent=1))
    (OUT / "heidebach_scripts.json").write_text(json.dumps(scripts, ensure_ascii=False, indent=1))

    graded = [s for s in scripts if s["human"]]
    print(f"sheet: {len(keys)} steps / {res['total_points']} BE")
    print(f"D2a: {sum(s['cohort'] == 'D2a' for s in scripts)} scripts, all human-graded; "
          f"D2b: {sum(s['cohort'] == 'D2b' for s in scripts)} submissions, "
          f"{sum(1 for s in scripts if s['cohort'] == 'D2b' and s['human'])} human-graded, "
          f"{sum(1 for s in scripts if s['llm_prod'])} with stored LLM grades")
    totals = sorted(s["human"]["total"] for s in graded)
    earlier = [s["script_id"] for s in graded if s["human"].get("sheet_version") == "earlier"]
    print(f"graded on the earlier sheet version: {', '.join(earlier) or 'none'}")
    print(f"human totals {totals[0]}-{totals[-1]} BE; pass rate "
          f"{sum(s['human']['passed'] for s in graded)}/{len(graded)}")
    print(f"-> {OUT.relative_to(HERE)}/heidebach_exam.json, heidebach_scripts.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
