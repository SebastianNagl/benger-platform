"""Upload the BenGER benchmark to Hugging Face Hub.

USAGE
-----
    export HF_TOKEN=hf_…              # write-permission token
    export ZJS_RELEASE_VARIANT=strict  # or 'optimistic' — set by legal review
    python scripts/upload_hf.py        # add --dry-run to skip the upload step

Layout staged for upload:
    benger/
    ├── benchathon/
    │   ├── tasks.json                 # data/raw/benchathon/Benchathon-tasks-<latest>.json
    │   ├── users.json                 # data/raw/benchathon/benchathon_users.json
    │   ├── korrektur_grades_sidecar.json
    │   └── human_grades.json          # data/processed/benchathon_human_grades.json
    ├── zjs/
    │   ├── source/                    # data/raw/zjs/source_<variant>/
    │   ├── merged.json                # data/raw/zjs/zjs_merged_<variant>.json
    │   ├── tasks.json                 # data/raw/zjs/ZJS Fälle-tasks-<variant>.json
    │   (no ip_clearance file — internal roster, not published)
    ├── grundprinzipien/
    │   └── tasks.json                 # data/raw/grundprinzipien/Grundprinzipien-tasks-<latest>.json
    ├── processed/                     # the small derived JSONs (mirror of data/processed/)
    └── README.md                      # the HF dataset card (see DATASET_CARD below)

The HF dataset configuration is built so:
    load_dataset("SebastianNagl/benger")             # all three subsets + `subset` column
    load_dataset("SebastianNagl/benger", "benchathon")
    load_dataset("SebastianNagl/benger", "zjs")
    load_dataset("SebastianNagl/benger", "grundprinzipien")

This script is a SKELETON. Before running:
  - Fill in the `REPO_ID` and double-check the HF org you want.
  - Decide what to do with the per-grader todo CSVs (likely skip — they're
    internal working files, not part of the released benchmark).
  - The `Benchathon-tasks-*.json` files contain anonymized UUIDs but are 350 MB
    each — verify you really want them shipped (or pick the latest only).
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
DATA = HERE / "data"

REPO_ID = "SebastianNagl/benger"  # TODO: confirm; consider creating an `benger` org

DATASET_CARD = """\
---
license: cc-by-4.0
task_categories:
  - text-generation       # ZJS + Benchathon long-form Falllösung (dominant pattern)
  - text2text-generation  # broad: structured case prompt → analysis
  - question-answering    # Doctrinal Principles Ja/Nein decisions
task_ids:
  - language-modeling
  - multiple-choice-qa
language:
  - de
pretty_name: "BenGER: Benchmarking LLM Systems on Subsumption-Based Legal Reasoning in German Law"
size_categories:
  - 1K<n<10K
tags:
  - benger
  - legal-nlp
  - german-law
  - llm-as-a-judge
  - human-evaluation
configs:
  - config_name: benchathon
    data_files: "benchathon/tasks.json"
  - config_name: zjs
    data_files: "zjs/tasks.json"
  - config_name: grundprinzipien
    data_files: "grundprinzipien/tasks.json"
  - config_name: default
    data_files:
      - "benchathon/tasks.json"
      - "zjs/tasks.json"
      - "grundprinzipien/tasks.json"
---

# BenGER: Benchmarking LLM Systems on Subsumption-Based Legal Reasoning in German Law

**Authors**: Sebastian Nagl¹, Ann-Kristin Mayrhofer², Martin Heidebach², Aleyna Koçak³, Anne Zettelmeier⁴, Elly Breu¹, Angelina Greiner¹, Sofija Milijas¹, Matthias Grabmair¹
¹ Technical University of Munich · ² Ludwig Maximilian University of Munich · ³ University of Konstanz · ⁴ University of Saarbrücken

## Links

- **Repository (source code, platform, manuscript)**: <https://github.com/SebastianNagl/benger-platform>
- **Paper (arXiv preprint)**: *(arXiv link to be filled in after upload)*
- **Companion ICAIL system-demo paper**: Nagl & Grabmair, ICAIL 2026 — *(citation will be linked once Anthology entry is live)*

BenGER is a single benchmark comprising three thematic subsets covering legal
reasoning across civil, criminal, and public German law:

- **`benchathon`** — collaboratively graded long-form analyses with seven blind
  human reviewers.
- **`zjs`** — published exam-style cases from the *Zeitschrift für das
  Juristische Studium*. Case texts (`Aufgabe`, `Musterlösung`) are released
  only for entries with author IP clearance; others link to the ZJS search.
- **`grundprinzipien`** — foundational legal-principle items.

## Loading

```python
from datasets import load_dataset
ds = load_dataset("SebastianNagl/benger")              # full benchmark
ds_zjs = load_dataset("SebastianNagl/benger", "zjs")   # one subset
```

## License

CC BY 4.0. Attribution: cite the paper and link this dataset card.

## Anonymisation

Human-grader identities are replaced with stable codes (`grader_01..grader_07`)
across every released file. The real-name mapping is kept private.

## Companion software

The platform that produced this benchmark is open-source (Apache 2.0) at
<https://github.com/SebastianNagl/benger-platform>. That repository also
holds the LaTeX/Quarto source for the manuscript, the rubric and judge
prompts, and the analysis pipeline that reproduces every figure and table.
"""


def main() -> int:
    """Stage files into a temp dir matching the HF layout, then upload."""
    import argparse

    ap = argparse.ArgumentParser(description="Upload BenGER dataset to Hugging Face Hub.")
    ap.add_argument("--dry-run", action="store_true", help="Stage files only, skip the upload.")
    args = ap.parse_args()

    # Default to `strict` (the IP-conservative variant: only ZJS cases with an
    # explicit `Genehmigt` clearance keep full text). Override with
    # ZJS_RELEASE_VARIANT=optimistic if/when legal greenlights the looser cut.
    variant = os.environ.get("ZJS_RELEASE_VARIANT", "strict")
    if variant not in ("strict", "optimistic"):
        sys.exit(f"ZJS_RELEASE_VARIANT must be 'strict' or 'optimistic' (got: {variant!r})")
    if not args.dry_run and not os.environ.get("HF_TOKEN"):
        sys.exit("Set HF_TOKEN env var (write-permission HF token).")

    staging = Path(tempfile.mkdtemp(prefix="benger_hf_"))
    print(f"Staging to {staging}")

    # --- benchathon --------------------------------------------------------
    (staging / "benchathon").mkdir()
    # Pick the latest Benchathon-tasks export
    bench_exports = sorted((DATA / "raw" / "benchathon").glob("Benchathon-tasks-*.json"))
    if bench_exports:
        shutil.copy2(bench_exports[-1], staging / "benchathon" / "tasks.json")
    shutil.copy2(DATA / "raw" / "benchathon" / "benchathon_users.json",
                 staging / "benchathon" / "users.json")
    shutil.copy2(DATA / "raw" / "benchathon" / "korrektur_grades_sidecar.json",
                 staging / "benchathon" / "korrektur_grades_sidecar.json")
    shutil.copy2(DATA / "processed" / "benchathon_human_grades.json",
                 staging / "benchathon" / "human_grades.json")

    # --- zjs ---------------------------------------------------------------
    (staging / "zjs").mkdir()
    shutil.copytree(DATA / "raw" / "zjs" / f"source_{variant}",
                    staging / "zjs" / "source")
    shutil.copy2(DATA / "raw" / "zjs" / f"zjs_merged_{variant}.json",
                 staging / "zjs" / "merged.json")
    shutil.copy2(DATA / "raw" / "zjs" / f"ZJS Fälle-tasks-{variant}.json",
                 staging / "zjs" / "tasks.json")
    # The IP-clearance roster (CSV and JSON) stays out of the public bundle.
    # ZJS cases that were not cleared are already redacted in `source/` and
    # `merged.json` to a placeholder URL — that's the only IP-state signal
    # downstream consumers need. The roster itself is internal accounting.

    # --- grundprinzipien ---------------------------------------------------
    (staging / "grundprinzipien").mkdir()
    gp_exports = sorted((DATA / "raw" / "grundprinzipien").glob("Grundprinzipien-tasks-*.json"))
    if gp_exports:
        shutil.copy2(gp_exports[-1], staging / "grundprinzipien" / "tasks.json")

    # --- processed (small derivatives) ------------------------------------
    shutil.copytree(DATA / "processed", staging / "processed",
                    ignore=shutil.ignore_patterns("*.bak"))

    # --- DATASET CARD -----------------------------------------------------
    (staging / "README.md").write_text(DATASET_CARD)

    # Summary
    print("\nStaged layout:")
    for p in sorted(staging.rglob("*")):
        if p.is_file():
            print(f"  {p.relative_to(staging)}  ({p.stat().st_size:,} bytes)")

    if args.dry_run:
        print(f"\n[dry-run] staged at {staging}. Remove with `rm -rf {staging}`.")
        return 0

    # --- upload -----------------------------------------------------------
    try:
        from huggingface_hub import HfApi, create_repo
    except ImportError:
        sys.exit("pip install huggingface_hub")
    api = HfApi(token=os.environ["HF_TOKEN"])
    create_repo(REPO_ID, repo_type="dataset", exist_ok=True, token=os.environ["HF_TOKEN"])
    print(f"\nUploading to {REPO_ID} …")
    api.upload_folder(
        folder_path=str(staging),
        repo_id=REPO_ID,
        repo_type="dataset",
        commit_message=f"Initial release — BenGER v1.0 (zjs variant: {variant})",
    )
    print("Done.")
    print(f"Verify: huggingface.co/datasets/{REPO_ID}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
