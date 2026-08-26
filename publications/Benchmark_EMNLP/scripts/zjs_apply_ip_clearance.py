"""Apply IP clearance to the ZJS dataset.

Produces a parallel `source_<mode>/` tree, a redacted `zjs_merged_<mode>.json`,
a redacted `interim/zjs_<mode>.json`, and a redacted streaming variant of the
3.85 GB platform export `ZJS Fälle-tasks-<mode>.json`.

Modes
-----
strict
    Conservative public-release candidate. A case retains its full Aufgabe and
    Musterlösung only when the IP map says `ip_cleared_strict` is true
    (i.e. the `Genehmigt` tag is present). Every other case — Abgelehnt,
    Angefragt, E-Mailfehler, empty status, or no CSV row at all — gets the
    placeholder URL and its PDF is dropped.

optimistic
    A case is redacted only when the IP map says `ip_cleared_optimistic` is
    false (i.e. the `Abgelehnt` tag is present). Cases without a CSV row are
    treated as approved (the explicit "unknown = approved" rule).

In both modes, when `anonymize_author` is true (only set by the
`Genehmigt aber anonymisiert` tag) the `Autoren` (or `Urheber`) field is
overwritten with the literal string "Anonymisiert".

Placeholder
-----------
    Aufgabe and Musterlösung are replaced with the bare URL
        https://www.zjs-online.com/index.php?sektion=3
    (the ZJS search interface). The string is identical for both fields.

Idempotent: re-runs overwrite the variant trees in place.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

import ijson

HERE = Path(__file__).resolve().parent.parent
DATA = HERE / "data"
ZJS_RAW = DATA / "raw" / "zjs"
SOURCE = ZJS_RAW / "source"
MERGED_SRC = SOURCE / "zjs_merged.json"
INTERIM_SRC = DATA / "interim" / "zjs.json"
EXPORT_SRC = ZJS_RAW / "ZJS Fälle-tasks-2026-05-18.json"
IP_MAP_PATH = ZJS_RAW / "ip_clearance.json"

BEREICHE = ("allgemeines", "oeffentliches_recht", "rechtsgeschichte", "strafrecht", "zivilrecht")
PLACEHOLDER = "https://www.zjs-online.com/index.php?sektion=3"
ANON_AUTHOR = "Anonymisiert"


def is_cleared(entry: dict | None, mode: str) -> bool:
    """Return True when a case keeps its full text under this mode.

    Cases with no CSV row (entry is None) follow the explicit unknown-handling
    rule: not approved in strict, approved in optimistic.
    """
    if entry is None:
        return mode == "optimistic"
    if mode == "strict":
        return bool(entry["ip_cleared_strict"])
    return bool(entry["ip_cleared_optimistic"])


def anonymize(entry: dict | None) -> bool:
    return bool(entry and entry["anonymize_author"])


def redact_case(case: dict, entry: dict | None, mode: str) -> dict:
    """Return a redacted copy of one case record.

    Operates on the schema used by both per-case JSONs and merged records:
    Titel, Autoren, Fundstelle, Aufgabe, Musterlösung, Bereich, ip_cleared.
    """
    out = dict(case)
    cleared = is_cleared(entry, mode)
    if not cleared:
        out["Aufgabe"] = PLACEHOLDER
        out["Musterlösung"] = PLACEHOLDER
    if anonymize(entry):
        # Per-case JSONs use "Autoren"; ip_map csv used "Urheber". Author key
        # in the file is always "Autoren" (verified across the corpus).
        out["Autoren"] = ANON_AUTHOR
    out["ip_cleared"] = cleared
    return out


# --- per-case JSON tree ------------------------------------------------------


def mirror_source_tree(ip_map: dict[str, dict], mode: str) -> tuple[int, int, int]:
    """Mirror source/<bereich>/* into source_<mode>/<bereich>/* with redactions."""
    dest_root = ZJS_RAW / f"source_{mode}"
    if dest_root.exists():
        shutil.rmtree(dest_root)
    dest_root.mkdir(parents=True)

    n_cleared = n_redacted = n_pdfs_kept = 0
    for bereich in BEREICHE:
        src = SOURCE / bereich
        if not src.is_dir():
            continue
        dst = dest_root / bereich
        dst.mkdir(parents=True, exist_ok=True)
        for entry in sorted(os.listdir(src)):
            sp = src / entry
            dp = dst / entry
            if entry.endswith(".json") and entry != "zjs_merged.json":
                key = entry[:-5]
                ip_entry = ip_map.get(key)
                with sp.open(encoding="utf-8") as f:
                    case = json.load(f)
                # The per-case JSONs lack "Bereich"/"ip_cleared" fields
                # (merge_json.py adds them later). Preserve the original shape
                # but still apply the placeholder/anonymization logic.
                redacted = dict(case)
                cleared = is_cleared(ip_entry, mode)
                if not cleared:
                    if "Aufgabe" in redacted:
                        redacted["Aufgabe"] = PLACEHOLDER
                    if "Musterlösung" in redacted:
                        redacted["Musterlösung"] = PLACEHOLDER
                if anonymize(ip_entry) and "Autoren" in redacted:
                    redacted["Autoren"] = ANON_AUTHOR
                with dp.open("w", encoding="utf-8") as f:
                    json.dump(redacted, f, ensure_ascii=False, indent=2)
                if cleared:
                    n_cleared += 1
                else:
                    n_redacted += 1
            elif entry.endswith(".pdf"):
                key = entry[:-4]
                ip_entry = ip_map.get(key)
                if is_cleared(ip_entry, mode):
                    shutil.copy2(sp, dp)
                    n_pdfs_kept += 1
                # else: drop the PDF entirely
            # Skip other artefacts (extract_base.py, blacklist.txt, __pycache__)
            # — they're tooling, not data, and shouldn't ship in the variant tree.
    return n_cleared, n_redacted, n_pdfs_kept


# --- merged / interim JSON ---------------------------------------------------


def write_merged_variant(ip_map: dict[str, dict], mode: str) -> None:
    """Apply the same redaction to zjs_merged.json and interim/zjs.json."""
    with MERGED_SRC.open(encoding="utf-8") as f:
        merged = json.load(f)
    redacted = [redact_case(r, ip_map.get(r["Fundstelle"]), mode) for r in merged]
    out_merged = ZJS_RAW / f"zjs_merged_{mode}.json"
    out_merged.write_text(json.dumps(redacted, ensure_ascii=False, indent=2))

    # interim/zjs.json is byte-identical to merged in the current data, but we
    # don't assume that — load and redact it independently so a future drift
    # doesn't silently corrupt either file.
    with INTERIM_SRC.open(encoding="utf-8") as f:
        interim = json.load(f)
    redacted_interim = [redact_case(r, ip_map.get(r["Fundstelle"]), mode) for r in interim]
    out_interim = DATA / "interim" / f"zjs_{mode}.json"
    out_interim.write_text(json.dumps(redacted_interim, ensure_ascii=False, indent=2))


# --- platform export (3.85 GB, streamed) -------------------------------------


def stream_redact_export(ip_map: dict[str, dict], mode: str) -> None:
    """Streamed pass over the platform export.

    The file is one top-level object with several array fields. We need to
    redact `tasks[*].data` (Aufgabe, Musterlösung, Autoren, ip_cleared) and
    `tasks[*].generations[*].case_data` (a JSON-encoded copy of the same
    data). All other arrays pass through unchanged.

    Approach: parse the top-level prefix incrementally, then for each named
    array stream its items, redact tasks while echoing everything else, and
    write the output as a fresh JSON document.
    """
    if not EXPORT_SRC.exists():
        print(f"  [skip] {EXPORT_SRC.name} not present — only required at release time")
        return

    out_path = ZJS_RAW / f"ZJS Fälle-tasks-{mode}.json"
    print(f"  Streaming {EXPORT_SRC.name} -> {out_path.name} (this takes a few minutes)")

    # Pull the small scalar fields first via a single parse pass.
    # use_float keeps ijson from returning Decimal, which json.dumps can't
    # serialize. The export contains floats (metric scores, durations) and
    # rounding to IEEE-754 is fine for our use.
    scalar_fields = {}
    with EXPORT_SRC.open("rb") as fh:
        for prefix, event, value in ijson.parse(fh, use_float=True):
            if prefix in ("project_id", "project_title", "exported_at") and event in ("string", "number"):
                scalar_fields[prefix] = value
                if len(scalar_fields) == 3:
                    break

    array_keys = (
        "evaluation_runs",
        "tasks",
        "human_evaluation_configs",
        "human_evaluation_sessions",
        "human_evaluation_results",
        "preference_rankings",
        "likert_scale_evaluations",
        "korrektur_comments",
    )

    with out_path.open("w", encoding="utf-8") as out:
        out.write("{\n")
        # Scalars first, in stable order.
        for i, k in enumerate(("project_id", "project_title", "exported_at")):
            if k in scalar_fields:
                out.write(f"  {json.dumps(k)}: {json.dumps(scalar_fields[k], ensure_ascii=False)},\n")
        # Each array streamed one at a time. Reopen the source per array since
        # ijson advances a single cursor.
        for ai, arr_key in enumerate(array_keys):
            out.write(f"  {json.dumps(arr_key)}: [")
            count = 0
            with EXPORT_SRC.open("rb") as fh:
                for item in ijson.items(fh, f"{arr_key}.item", use_float=True):
                    if arr_key == "tasks":
                        item = _redact_task(item, ip_map, mode)
                    if count:
                        out.write(",")
                    out.write("\n    ")
                    out.write(json.dumps(item, ensure_ascii=False))
                    count += 1
            out.write("\n  ]")
            if ai < len(array_keys) - 1:
                out.write(",")
            out.write("\n")
            print(f"    {arr_key}: {count}")
        out.write("}\n")


def _redact_task(task: dict, ip_map: dict[str, dict], mode: str) -> dict:
    """Redact one task in-place (and its embedded generations.case_data)."""
    data = task.get("data") or {}
    fundstelle = data.get("Fundstelle")
    ip_entry = ip_map.get(fundstelle) if fundstelle else None

    new_data = redact_case(data, ip_entry, mode) if data else data
    task["data"] = new_data

    # Each generation embeds a stringified copy of the task's case data — keep
    # it consistent with the redacted task.data. The embedded format observed
    # in 2026-05 exports is `{"text": "<python-repr-of-dict>"}`, but we don't
    # rely on parsing it: we simply overwrite with a fresh JSON string of the
    # redacted data, which is both consistent and machine-readable.
    new_case_payload = json.dumps({"text": json.dumps(new_data, ensure_ascii=False)}, ensure_ascii=False)
    for gen in task.get("generations") or ():
        if "case_data" in gen:
            gen["case_data"] = new_case_payload
    return task


# --- driver ------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mode", required=True, choices=("strict", "optimistic"))
    ap.add_argument(
        "--skip-platform-export",
        action="store_true",
        help="Skip the 3.85 GB platform export pass (useful for fast iteration)",
    )
    args = ap.parse_args()
    mode = args.mode

    if not IP_MAP_PATH.exists():
        sys.exit(f"Missing {IP_MAP_PATH}; run zjs_build_ip_map.py first.")
    with IP_MAP_PATH.open(encoding="utf-8") as f:
        ip_map = json.load(f)

    print(f"Mode: {mode}")
    print(f"IP map entries: {len(ip_map)}")

    print("\n[1/3] Mirroring per-case source tree …")
    n_cleared, n_redacted, n_pdfs = mirror_source_tree(ip_map, mode)
    print(f"      {n_cleared} cleared, {n_redacted} redacted, {n_pdfs} PDFs kept")

    print("[2/3] Rebuilding merged + interim …")
    write_merged_variant(ip_map, mode)
    print(f"      wrote zjs_merged_{mode}.json and interim/zjs_{mode}.json")

    if args.skip_platform_export:
        print("[3/3] Skipping platform export pass (--skip-platform-export)")
    else:
        print("[3/3] Streaming platform export …")
        stream_redact_export(ip_map, mode)

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
