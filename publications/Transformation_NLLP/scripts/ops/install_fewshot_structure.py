#!/usr/bin/env python3
"""Install the few-shot prompt structure on the clone (WP A2).

Clones the clone project's live `bewertungsbogen` structure to a new key
`bewertungsbogen_fewshot`, changing ONLY the instruction half:
  - add "exemplar_rubrics": "$exemplar_rubrics" to instruction_prompt.fields
  - splice a labeled {{exemplar_rubrics}} block into instruction_prompt.template
    after the MUSTERLOESUNG block, before "Befolge die nachstehenden Regeln."
The system prompt and every rule block are byte-identical; the format
contract is code-appended by the worker, so this is a clean single-factor
manipulation. A new structure key auto-yields a distinct prompt_version hash
(SHA-256 of the whole structure dict) → the few-shot cohort separates from
zero-shot in SQL for free.

Done by script rather than the Prompt-Strukturen form editor because the
change is a surgical insertion into a 21k-char structure that must remain
byte-identical everywhere else — a documented UI-vs-script decision (the
form CAN author structures; it is the wrong tool for a byte-exact clone).

Snapshots the installed structure + its prompt_version hash to
data/interim/fewshot/prompt_snapshot.json.

Usage: uv run python scripts/ops/install_fewshot_structure.py --base-url http://localhost:8001 [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
FEWSHOT = HERE / "data" / "interim" / "fewshot"
CLONE_PROJECT = "81e474b8-d226-4bf8-bc2e-fb744d25cba5"
NEW_KEY = "bewertungsbogen_fewshot"

sys.path.insert(0, str(HERE / "scripts" / "ops"))
from setup_audit_project import Client  # noqa: E402

# German instruction block that introduces the exemplar. ASCII-only
# placeholder name ({{exemplar_rubrics}}) so the parser's {{[a-zA-Z_]...}}
# pattern matches. En dashes per house style.
EXEMPLAR_BLOCK = (
    "\n\nBEISPIEL-BEWERTUNGSBOGEN EINER ANDEREN KLAUSUR (nur als Qualitaets- "
    "und Strukturvorlage, NICHT inhaltlich uebernehmen):\n{{exemplar_rubrics}}\n"
)
ANCHOR = "Befolge die nachstehenden Regeln."


def prompt_version_hash(structure: dict) -> str:
    canonical = json.dumps(structure or {}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--project", default=CLONE_PROJECT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    FEWSHOT.mkdir(parents=True, exist_ok=True)

    client = Client(args.base_url)
    client.login(os.environ.get("BENGER_ADMIN_EMAIL", "admin@example.com"),
                 os.environ.get("BENGER_ADMIN_PASSWORD", "admin"))
    project = client.request("GET", f"/api/projects/{args.project}")
    gen = project.get("generation_config") or {}
    structures = dict(gen.get("prompt_structures") or {})
    assert "bewertungsbogen" in structures, "source structure missing on project"

    base = json.loads(json.dumps(structures["bewertungsbogen"]))  # deep copy
    instr = base["instruction_prompt"]
    assert isinstance(instr, dict) and "template" in instr and "fields" in instr, \
        "instruction_prompt is not a template dict"

    # 1. field mapping
    instr["fields"] = dict(instr["fields"])
    instr["fields"]["exemplar_rubrics"] = "$exemplar_rubrics"

    # 2. splice the exemplar block before the rules anchor
    tmpl = instr["template"]
    assert ANCHOR in tmpl, f"anchor {ANCHOR!r} not found in template"
    assert "{{exemplar_rubrics}}" not in tmpl, "placeholder already present"
    idx = tmpl.index(ANCHOR)
    instr["template"] = tmpl[:idx] + EXEMPLAR_BLOCK.strip() + "\n\n" + tmpl[idx:]

    base["name"] = "Bewertungsbogen-Erzeugung (v3, few-shot)"
    base["description"] = (base.get("description") or "") + \
        " [Few-shot-Variante: injiziert ein Beispiel aus einer anderen Klausur desselben Rechtsgebiets.]"

    new_hash = prompt_version_hash(base)
    old_hash = prompt_version_hash(structures["bewertungsbogen"])
    print(f"source prompt_version {old_hash}  ->  few-shot {new_hash}")
    assert new_hash != old_hash, "few-shot structure hash collides with zero-shot"

    snapshot = {
        "key": NEW_KEY, "prompt_version": new_hash,
        "source_key": "bewertungsbogen", "source_prompt_version": old_hash,
        "exemplar_block": EXEMPLAR_BLOCK, "structure": base,
    }
    (FEWSHOT / "prompt_snapshot.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=1), encoding="utf-8")

    if args.dry_run:
        print("DRY RUN: structure not installed")
        print("template delta around anchor:")
        j = base["instruction_prompt"]["template"].index("BEISPIEL-BEWERTUNGSBOGEN")
        print("  ..." + base["instruction_prompt"]["template"][j-40:j+180] + "...")
        return 0

    structures[NEW_KEY] = base
    new_gen = dict(gen)
    new_gen["prompt_structures"] = structures
    client.request("PUT", f"/api/projects/{args.project}/generation-config", new_gen)

    check = client.request("GET", f"/api/projects/{args.project}")
    got = ((check.get("generation_config") or {}).get("prompt_structures") or {}).get(NEW_KEY)
    assert got is not None, "few-shot structure missing after PUT"
    assert got["instruction_prompt"]["fields"].get("exemplar_rubrics") == "$exemplar_rubrics"
    assert "{{exemplar_rubrics}}" in got["instruction_prompt"]["template"]
    assert "bewertungsbogen" in (check["generation_config"]["prompt_structures"]), \
        "source structure lost!"
    assert prompt_version_hash(got) == new_hash, "installed structure hash drifted"
    print(f"OK: installed {NEW_KEY} (prompt_version {new_hash}); "
          f"source structure intact; snapshot -> {FEWSHOT / 'prompt_snapshot.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
