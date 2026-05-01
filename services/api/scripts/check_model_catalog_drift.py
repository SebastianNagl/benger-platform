#!/usr/bin/env python3
"""Diff seeds/llm_models.yaml against the live llm_models table.

Exits 0 if catalog matches DB; non-zero if any of:
  - YAML model is missing from DB
  - DB has an active row not in YAML (or vice versa for is_active)
  - Per-model fields (price, name, capabilities, default_config, parameter_constraints) differ
  - DB has a row whose id is in YAML but with mismatched fields

Designed to run in three places:
  1. PR CI: spin up a fresh DB, seed it, run this — catches "I edited
     the YAML but my edit is malformed / the upsert dropped a column".
  2. Nightly cron in staging/prod: catches drift caused by manual
     UPDATEs, half-applied migrations, or stale flag files.
  3. Local dev: `make check-model-drift` after editing the YAML.

Usage:
  python check_model_catalog_drift.py             # uses DATABASE_URL env
  python check_model_catalog_drift.py --json      # machine-readable output
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Make the api source importable when run from inside the container or repo root
_HERE = Path(__file__).resolve()
for candidate in (_HERE.parent.parent, Path("/app")):
    if candidate.exists() and (candidate / "database.py").exists():
        sys.path.insert(0, str(candidate))
        break

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Field names to compare (DB column names)
COMPARE_FIELDS = (
    "name",
    "description",
    "provider",
    "model_type",
    "capabilities",
    "is_active",
    "input_cost_per_million",
    "output_cost_per_million",
    "default_config",
    "parameter_constraints",
)


def _yaml_to_db_row(m: dict) -> dict:
    row = {k: m.get(k) for k in COMPARE_FIELDS}
    if "constraints" in m:
        row["parameter_constraints"] = m["constraints"]
    return row


def _normalize(value):
    """Make YAML scalars comparable to DB values (e.g. int/float, list ordering)."""
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in sorted(value.items())}
    if isinstance(value, float) and value.is_integer():
        return float(value)
    return value


def diff(db_url: str) -> dict:
    from seeds.llm_models_loader import load_catalog
    from models import LLMModel as DBLLMModel

    catalog = load_catalog()
    yaml_by_id = {m["id"]: _yaml_to_db_row(m) for m in catalog.models}

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        rows = session.query(DBLLMModel).all()
    finally:
        session.close()

    db_by_id = {
        r.id: {k: getattr(r, k) for k in COMPARE_FIELDS}
        for r in rows
    }

    missing_in_db = sorted(set(yaml_by_id) - set(db_by_id))
    # DB rows that no longer have a YAML entry. We tolerate them if they're
    # already is_active=False (historical-eval rows kept for referential
    # integrity). Active rows here are real drift — flag them.
    extra_in_db = sorted(
        mid for mid in set(db_by_id) - set(yaml_by_id)
        if db_by_id[mid].get("is_active")
    )

    field_mismatches = []
    for mid in sorted(set(yaml_by_id) & set(db_by_id)):
        y = yaml_by_id[mid]
        d = db_by_id[mid]
        per_field = {}
        for f in COMPARE_FIELDS:
            yv = _normalize(y.get(f))
            dv = _normalize(d.get(f))
            if yv != dv:
                per_field[f] = {"yaml": y.get(f), "db": d.get(f)}
        if per_field:
            field_mismatches.append({"id": mid, "fields": per_field})

    return {
        "catalog_version": catalog.content_hash[:8],
        "yaml_count": len(yaml_by_id),
        "db_count": len(db_by_id),
        "missing_in_db": missing_in_db,
        "extra_in_db": extra_in_db,
        "field_mismatches": field_mismatches,
        "ok": not (missing_in_db or extra_in_db or field_mismatches),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--db-url", default=os.environ.get("DATABASE_URL"),
                        help="DB URL (default: $DATABASE_URL)")
    args = parser.parse_args()

    if not args.db_url:
        print("ERROR: no DB URL — set DATABASE_URL or pass --db-url", file=sys.stderr)
        return 2

    result = diff(args.db_url)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"Catalog version: {result['catalog_version']}")
        print(f"YAML models: {result['yaml_count']} | DB rows: {result['db_count']}")
        if result["missing_in_db"]:
            print(f"\n[!] {len(result['missing_in_db'])} model(s) in YAML but missing from DB:")
            for mid in result["missing_in_db"]:
                print(f"    - {mid}")
        if result["extra_in_db"]:
            print(f"\n[!] {len(result['extra_in_db'])} row(s) in DB but absent from YAML:")
            for mid in result["extra_in_db"]:
                print(f"    - {mid}")
        if result["field_mismatches"]:
            print(f"\n[!] {len(result['field_mismatches'])} model(s) with field mismatches:")
            for entry in result["field_mismatches"]:
                print(f"    - {entry['id']}:")
                for f, vals in entry["fields"].items():
                    print(f"        {f}: yaml={vals['yaml']!r} db={vals['db']!r}")
        if result["ok"]:
            print("\nOK: no drift detected.")

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
