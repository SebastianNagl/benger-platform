"""Build a normalized IP-clearance lookup from the author-outreach CSV.

Input
-----
data/raw/zjs/ip_clearance_<DATE>.csv
    Columns: Name, E-Mail, Fachgebiet, Fundstelle, Komplexität,
             Rechtsbereich, Status, Urheber.
    Status is multi-valued (comma-separated tags), e.g.
    "Genehmigt", "Angefragt, Genehmigt", "Genehmigt aber anonymisiert",
    "Abgelehnt", "" (empty).
    Two Fundstelle formats coexist:
      - Modern: "ZJS 2/2008 163"
      - Old   : "3. Jahrgang, Ausgabe 4-5/2011, S. 342 - 350"

Output
------
data/raw/zjs/ip_clearance.json
    Mapping <filename-key> -> {
        status_tags: [str],
        urheber: str,
        anonymize_author: bool,   # True iff "Genehmigt aber anonymisiert" in tags
        ip_cleared_strict: bool,  # True iff "Genehmigt" in tags
        ip_cleared_optimistic: bool,  # True iff "Abgelehnt" NOT in tags
        csv_name: str,
        csv_fundstelle: str,
    }

The <filename-key> matches the per-case JSON filename (without .json) under
data/raw/zjs/source/<bereich>/.  Two key shapes occur, mirroring the two
Fundstelle formats:
  - "ZJS_2008_2_S163"      (modern)
  - "2011_4-5_342"          (old)
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
DATA_DIR = HERE / "data" / "raw" / "zjs"
SOURCE_DIR = DATA_DIR / "source"
BEREICHE = ("allgemeines", "oeffentliches_recht", "rechtsgeschichte", "strafrecht", "zivilrecht")
OUT_PATH = DATA_DIR / "ip_clearance.json"

MODERN_RE = re.compile(r"^ZJS\s+(\d+)/(\d+)\s+(\d+)$")
OLD_RE = re.compile(r"^\d+\.\s+Jahrgang,\s+Ausgabe\s+([\d\-]+)/(\d+),\s+S\.\s+(\d+)")

GENEHMIGT_TAG = "Genehmigt"
ANON_TAG = "Genehmigt aber anonymisiert"
REJECTED_TAG = "Abgelehnt"


def fundstelle_to_key(s: str) -> str | None:
    """Normalize a CSV Fundstelle to a JSON filename key. None if unparseable."""
    s = (s or "").strip()
    m = MODERN_RE.match(s)
    if m:
        issue, year, page = m.groups()
        return f"ZJS_{year}_{issue}_S{page}"
    m = OLD_RE.match(s)
    if m:
        issue, year, page = m.groups()
        return f"{year}_{issue}_{page}"
    return None


def parse_status_tags(raw: str) -> list[str]:
    """Split the multi-valued Status field into trimmed tags. Order preserved."""
    if not raw:
        return []
    return [t.strip() for t in raw.split(",") if t.strip()]


def find_csv() -> Path:
    """Pick the most recent ip_clearance_*.csv in data/raw/zjs/."""
    candidates = sorted(DATA_DIR.glob("ip_clearance_*.csv"))
    if not candidates:
        sys.exit(f"No ip_clearance_*.csv found in {DATA_DIR}")
    return candidates[-1]


def collect_file_keys() -> set[str]:
    """All per-case JSON filename keys under source/<bereich>/."""
    keys: set[str] = set()
    for bereich in BEREICHE:
        d = SOURCE_DIR / bereich
        if not d.is_dir():
            continue
        for entry in os.listdir(d):
            if entry.endswith(".json") and not entry.startswith("zjs_merged"):
                keys.add(entry[:-5])
    return keys


def main() -> int:
    csv_path = find_csv()
    print(f"Reading {csv_path.name}")

    with csv_path.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    print(f"  {len(rows)} CSV rows")

    file_keys = collect_file_keys()
    print(f"  {len(file_keys)} case JSON files under source/")

    out: dict[str, dict] = {}
    unparseable: list[dict] = []
    unmatched_csv: list[str] = []   # parseable but no file
    duplicates: list[str] = []

    for row in rows:
        key = fundstelle_to_key(row.get("Fundstelle", ""))
        if key is None:
            unparseable.append(row)
            continue
        if key not in file_keys:
            unmatched_csv.append(key)
            continue
        if key in out:
            duplicates.append(key)
            continue
        tags = parse_status_tags(row.get("Status", ""))
        # "Genehmigt aber anonymisiert" is approval-with-anonymization, not a
        # separate state from Genehmigt — both imply the case may ship.
        approved = (GENEHMIGT_TAG in tags) or (ANON_TAG in tags)
        out[key] = {
            "status_tags": tags,
            "urheber": row.get("Urheber", "").strip(),
            "anonymize_author": ANON_TAG in tags,
            "ip_cleared_strict": approved,
            "ip_cleared_optimistic": REJECTED_TAG not in tags,
            "csv_name": row.get("Name", "").strip(),
            "csv_fundstelle": row.get("Fundstelle", "").strip(),
        }

    missing_files = sorted(file_keys - set(out))

    # --- report --------------------------------------------------------------
    print()
    print(f"Matched (CSV row + file present): {len(out)}")
    print(f"CSV rows whose Fundstelle could not be parsed: {len(unparseable)}")
    for r in unparseable:
        print(f"  Fundstelle={r.get('Fundstelle','')!r}  Name={r.get('Name','')[:40]!r}")
    print(f"CSV rows whose key has no matching file: {len(unmatched_csv)}")
    for k in unmatched_csv:
        print(f"  {k}")
    print(f"Case files without CSV row: {len(missing_files)}")
    for k in missing_files:
        print(f"  {k}")
    if duplicates:
        print(f"DUPLICATE CSV keys (should be zero): {duplicates}")

    # Per spec: refusing to write would block the pipeline; the unparseable
    # set should always be zero (both regex passes cover every form found in
    # the 2026-05-25 data), so failure here is a real bug. unmatched_csv and
    # missing_files are expected (small numbers; not fatal) and handled
    # downstream by ip_cleared_optimistic defaulting based on the JSON-files-
    # without-CSV-row rule.
    if unparseable:
        print("\nFAIL: at least one CSV row could not be parsed.", file=sys.stderr)
        return 1

    # Summary of clearance distribution among matched cases
    n_strict = sum(1 for v in out.values() if v["ip_cleared_strict"])
    n_optimistic = sum(1 for v in out.values() if v["ip_cleared_optimistic"])
    n_anon = sum(1 for v in out.values() if v["anonymize_author"])
    print()
    print(f"  Among matched cases ({len(out)}):")
    print(f"    ip_cleared_strict (Genehmigt):           {n_strict}")
    print(f"    ip_cleared_optimistic (not Abgelehnt):   {n_optimistic}")
    print(f"    anonymize_author (Genehmigt aber anon.): {n_anon}")

    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"\nWrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
