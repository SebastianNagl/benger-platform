#!/usr/bin/env python3
"""Structure of Gregor Roth's grading sheet (Z2).

Reads the private grading workbook (data/raw/human/roth_z2/rubric/*.xlsx,
git-ignored) and writes aggregate facts only (data/processed/cslaw/z2_sheet.json):
the parts and their shares, the number of weighting levels below a part, the
weighted leaves and parents, the largest and smallest absolute leaf weight,
how many parents state child shares that do not sum to 100 %, the leaf grade
range, the pass mark, and the workbook's grading fields. No titles, no text.

The workbook holds one sheet per candidate (all with the same weights) and an
overview. In a candidate sheet column B is the share of the parent, column C
the absolute share of the total grade and column D the grade in points. A
leaf's contribution is E = D * C; a parent's E sums its children's E. The
tree is read from these SUM formulas, not from the layout.
"""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parent.parent.parent
RAW = HERE / "data" / "raw" / "human" / "roth_z2" / "rubric"
OUT = HERE / "data" / "processed" / "cslaw" / "z2_sheet.json"
M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
PCT = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*%")
SUM = re.compile(r"^SUM\(([^)]*)\)$")
REF = re.compile(r"^([A-Z]+)(\d+)$")


def _float(v: str | None) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def read_workbook(path: Path) -> tuple[list[str], list[tuple[str, dict, ET.Element]]]:
    """Shared strings, and per sheet (name, {ref: (value, formula)}, root)."""
    z = zipfile.ZipFile(path)
    ss = ["".join(t.text or "" for t in si.iter(M + "t"))
          for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(M + "si")]
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    sheets = []
    for s in wb.iter(M + "sheet"):
        part = "xl/" + rels[s.get(RID)].lstrip("/").removeprefix("xl/")
        root = ET.fromstring(z.read(part))
        cells = {}
        for c in root.iter(M + "c"):
            v, f = c.find(M + "v"), c.find(M + "f")
            val = v.text if v is not None else None
            if val is not None and c.get("t") == "s":
                val = ss[int(val)]
            cells[c.get("r")] = (val, f.text if f is not None else None)
        sheets.append((s.get("name"), cells, root))
    return ss, sheets


def candidate_structure(cells: dict, root: ET.Element) -> dict:
    col = lambda c: {int(REF.match(r).group(2)): vf for r, vf in cells.items()
                     if REF.match(r) and REF.match(r).group(1) == c}
    absw = {row: _float(v) for row, (v, _) in col("C").items() if _float(v) is not None}
    rel = {row: float(PCT.match(v).group(1).replace(",", "."))
           for row, (v, _) in col("B").items() if v and PCT.match(v)}
    children = {row: [int(REF.match(x.strip()).group(2)) for x in SUM.match(f).group(1).split(",")]
                for row, (_, f) in col("E").items() if f and SUM.match(f)}
    child_rows = {k for ks in children.values() for k in ks}
    roots = [row for row in children if row not in child_rows]
    assert len(roots) == 1, f"expected one total row, got {roots}"
    total = roots[0]
    parts = children[total]
    leaves = [row for row in absw if row not in children]

    def levels(row: int) -> int:
        # weighting levels below a part: nodes that state a share of their
        # parent (a claim heading without a share of its own is no level)
        own = 1 if row in rel and row not in parts else 0
        return own + (max(levels(k) for k in children[row]) if row in children else 0)

    inner = [row for row in children if row != total and row not in parts]
    dv = root.find(".//" + M + "dataValidation")
    return {
        "parts_pct": [round(100 * absw[p], 2) for p in parts],
        "weighting_levels_below_part": max(levels(p) for p in parts),
        "weighted_leaves": len(leaves),
        "weighted_parents": len(inner),
        "parents_child_shares_not_100": sum(
            1 for row in inner + parts if all(k in rel for k in children[row])
            and abs(sum(rel[k] for k in children[row]) - 100.0) > 0.5),
        "parents_absolute_weights_inconsistent": sum(
            1 for row in inner + parts if abs(sum(absw.get(k, 0.0) for k in children[row]) - absw[row]) > 1e-6),
        "max_leaf_weight_pct": round(100 * max(absw[r] for r in leaves), 2),
        "min_leaf_weight_pct": round(100 * min(absw[r] for r in leaves), 2),
        "leaf_weight_sum_pct": round(100 * sum(absw[r] for r in leaves), 4),
        "leaf_grade_range": [_float(dv.find(M + "formula1").text), _float(dv.find(M + "formula2").text)]
        if dv is not None else None,
        "leaf_grade_whole_numbers": dv is not None and dv.get("type") == "whole",
        # leaf weights and stated shares; two sheets carry an extra copy of
        # a part weight on the part's title row, which changes nothing
        "_signature": (sorted((r, absw[r]) for r in leaves), sorted(rel.items())),
    }


def main() -> int:
    ss, sheets = read_workbook(next(RAW.glob("*.xlsx")))
    candidates = sheets[1:]  # the first sheet is the overview
    structures = [candidate_structure(cells, root) for _, cells, root in candidates]
    signatures = [s.pop("_signature") for s in structures]
    text = " ".join(ss)
    pass_mark = re.search(r"Bestehen ab Note (\d+)", text)
    # the overview counts passed scripts per final-grade column: COUNTIF(..., ">=4")
    overview = sheets[0][1]
    countif = sorted({int(m.group(1)) for _, f in overview.values() if f
                      for m in re.finditer(r'COUNTIF\([^,]+,">=(\d+)"\)', f)})
    assert pass_mark and countif == [int(pass_mark.group(1))], (pass_mark, countif)
    out = {
        "source": "Gregor Roth's grading workbook (Z2), private; aggregates only",
        **structures[0],
        "aggregation": "weighted mean of leaf grades (absolute weights sum to 1)",
        "workbook": {
            "candidate_sheets": len(candidates),
            "weights_identical_across_candidates": all(s == signatures[0] for s in signatures),
            "pass_from_grade": int(pass_mark.group(1)) if pass_mark else None,
            "manual_bonus_malus": "Bonus/Malus" in text,
            # two manual final-grade columns, each with its own statistics (pass
            # count, mean, median); the workbook does not average them, and
            # whether they are two graders is not stated
            "final_grade_fields": sorted(set(re.findall(r"Endnote \d", text))),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
