#!/usr/bin/env python3
"""Set up the probe battery on the temp0 clone (WP2.2).

1. Register + verify the three probe users (one per probe type — one user
   can hold only one active annotation per task).
2. Insert the 45 probe annotations by direct DB INSERT. The API path is
   blocked for this purpose: the importer always creates fresh tasks, the
   clone enforces maximum_annotations=1 per task, and there is no member-add
   endpoint — while the eval worker and the run endpoint's annotator
   validation read the annotations table directly. Local dev DB only.
3. Install the three probe-only judge configs (replace-by-id merge, exact
   copies of the tailored-arm configs' judge/temperature layout, but
   prediction_fields ["human:loesung"] — zero generation fan-out).
4. Write probe_run_filters.json (driver format) and probe_picks.json
   (picks schema, so extract_judge_results.py works unchanged).

Idempotent: refuses to re-insert if probe_annotations.json exists
(--cleanup deletes exactly the recorded ids first).

Usage:
  uv run python scripts/ops/setup_probe_battery.py --base-url http://api.localhost [--cleanup]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
INTERIM = HERE / "data" / "interim"
PROBES = INTERIM / "probes"
CLONE_PROJECT = "81e474b8-d226-4bf8-bc2e-fb744d25cba5"

sys.path.insert(0, str(HERE / "scripts" / "ops"))
from setup_audit_project import Client  # noqa: E402

# Probe configs copy the tailored-arm layout (see DESIGN.md pre-registration):
# panel = msc0vokl-mmdi (T=0, mini x3 + four flagships x1), gem = -gem1 (T=1),
# luna = msewfvty-24qr (T=1, x3).
TEMPLATE_IDS = {
    "llm_judge_rubric-probe-panel": "llm_judge_rubric-msc0vokl-mmdi",
    "llm_judge_rubric-probe-gem": "llm_judge_rubric-msc0vokl-mmdi-gem1",
    "llm_judge_rubric-probe-luna": "llm_judge_rubric-msewfvty-24qr",
}

# Holistic-arm probe configs (pre-registered 2026-08-09): byte-identical
# clones of the matched holistic arms, scoped to the probe annotations.
TEMPLATE_IDS_HOLISTIC = {
    "llm_judge_falloesung-probe-luna3": "llm_judge_falloesung-luna3-matched",
    "llm_judge_falloesung-probe-mini3": "llm_judge_falloesung-mini3-matched",
}


def psql(sql: str) -> str:
    return subprocess.run(
        ["docker", "exec", "-i", "benger-db-1", "psql", "-U", "postgres", "-d", "benger",
         "-v", "ON_ERROR_STOP=1", "-tA", "-f", "-"],
        input=sql, capture_output=True, text=True, check=True,
    ).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--cleanup", action="store_true",
                        help="Delete previously inserted probe annotations first")
    parser.add_argument("--add-types",
                        help="Additive mode (comma-separated probe types, e.g. "
                             "'musterloesung'): register only these types' users, "
                             "insert only their annotations (appending to "
                             "probe_annotations.json — existing rows untouched), "
                             "install the holistic probe configs, and write the "
                             "extension filter files. The published negative-probe "
                             "fixtures are never modified.")
    args = parser.parse_args()
    add_types = tuple(t.strip() for t in args.add_types.split(",")) if args.add_types else None

    texts = json.load(open(PROBES / "probe_texts.json"))
    users = json.load(open(PROBES / "probe_users.json"))
    ann_path = PROBES / "probe_annotations.json"
    if add_types:
        assert not args.cleanup, "--cleanup would delete the published probe rows; refuse in --add-types mode"
        missing = [t for t in add_types if t not in users]
        assert not missing, f"probe types without users (run build_probe_battery.py first): {missing}"

    admin = Client(args.base_url)
    admin.login(os.environ.get("BENGER_ADMIN_EMAIL", "admin@example.com"),
                os.environ.get("BENGER_ADMIN_PASSWORD", "admin"))

    # --- 1. users: register -> verify -> login (id) --------------------------
    for ptype, u in users.items():
        if add_types and ptype not in add_types and u.get("user_id"):
            print(f"user probe-{ptype}: {u['user_id']} (existing, skipped)")
            continue
        real_id = None
        try:
            created = admin.request("POST", "/api/auth/register", {
                "username": u["username"], "email": u["email"], "name": u["name"],
                "password": u["password"],
                "legal_expertise_level": "layperson", "german_proficiency": "native",
            })
            real_id = created.get("id") or (created.get("user") or {}).get("id")
        except RuntimeError as exc:
            if "400" not in str(exc) and "409" not in str(exc):
                raise
        if real_id:
            admin.request("PATCH", f"/api/users/{real_id}/verify-email", {})
        probe_client = Client(args.base_url)
        login = probe_client.login(u["email"], u["password"])
        real_id = real_id or (login.get("user") or {}).get("id")
        if not real_id:
            profile = probe_client.request("GET", "/api/auth/profile")
            real_id = profile.get("id") or (profile.get("user") or {}).get("id")
        assert real_id, f"no user id for {ptype}"
        u["user_id"] = real_id
        print(f"user probe-{ptype}: {real_id}")
    (PROBES / "probe_users.json").write_text(json.dumps(users, indent=1), encoding="utf-8")

    # --- 2. annotations -------------------------------------------------------
    existing_records = []
    if add_types:
        existing_records = json.load(open(ann_path)) if ann_path.exists() else []
        already = sorted({r["probe_type"] for r in existing_records} & set(add_types))
        assert not already, f"probe types already inserted: {already} — nothing to add"
    else:
        if args.cleanup and ann_path.exists():
            old = json.load(open(ann_path))
            ids = "','".join(a["annotation_id"] for a in old)
            n = psql(f"delete from annotations where id in ('{ids}') returning id;")
            print(f"cleanup: deleted {len(n.splitlines())} probe annotations")
            ann_path.unlink()
        if ann_path.exists():
            print("probe_annotations.json exists — refusing to re-insert (use --cleanup)")
            return 1

    records, stmts = [], []
    for row in texts:
        for ptype, text in row["probes"].items():
            if add_types and ptype not in add_types:
                continue
            ann_id = str(uuid.uuid4())
            result = [
                {"type": "angabe", "from_name": "sachverhalt", "to_name": "sachverhalt",
                 "value": {"spans": [], "comments": []}},
                {"type": "loesung", "from_name": "loesung", "to_name": "sachverhalt",
                 "value": {"markdown": text}},
            ]
            payload = json.dumps(result, ensure_ascii=False)
            tag = "probe_dq"
            while f"${tag}$" in payload:
                tag += "x"
            stmts.append(
                "insert into annotations (id, task_id, project_id, completed_by, result, "
                "was_cancelled, ground_truth, auto_submitted, tab_switches, ai_assisted, created_at) "
                f"values ('{ann_id}', '{row['clone_task_id']}', '{CLONE_PROJECT}', "
                f"'{users[ptype]['user_id']}', ${tag}${payload}${tag}$::jsonb, "
                "false, false, false, 0, false, now());"
            )
            records.append({
                "probe_id": f"PB{row['exam_inner_id']:02d}-{ptype}",
                "probe_type": ptype,
                "exam_inner_id": row["exam_inner_id"],
                "clone_task_id": row["clone_task_id"],
                "annotation_id": ann_id,
                "user_id": users[ptype]["user_id"],
            })
    psql("begin;\n" + "\n".join(stmts) + "\ncommit;")
    check = psql(
        "select count(*) from annotations where id in ('"
        + "','".join(r["annotation_id"] for r in records) + "');")
    assert check == str(len(records)), f"inserted {check}/{len(records)}"
    all_records = existing_records + records
    ann_path.write_text(json.dumps(all_records, indent=1), encoding="utf-8")
    print(f"inserted {check} probe annotations"
          + (f" (appended to {len(existing_records)} existing)" if existing_records else ""))

    # --- 3. probe configs (replace-by-id merge) -------------------------------
    project = admin.request("GET", f"/api/projects/{CLONE_PROJECT}")
    configs = (project.get("evaluation_config") or {}).get("evaluation_configs") or []
    by_id = {c["id"]: c for c in configs}
    backup = INTERIM / "clone_eval_config_backup_2026-08-09.json"
    if add_types and not backup.exists():
        backup.write_text(json.dumps(project.get("evaluation_config"), indent=1,
                                     ensure_ascii=False), encoding="utf-8")
        print(f"pre-PUT config backup -> {backup.name}")
    if add_types:
        # Additive mode installs ONLY the holistic probe configs; the three
        # published rubric probe configs are left byte-identical.
        template_map = {new_id: (tpl_id, "llm_judge_falloesung")
                        for new_id, tpl_id in TEMPLATE_IDS_HOLISTIC.items()}
    else:
        template_map = {new_id: (tpl_id, "llm_judge_rubric")
                        for new_id, tpl_id in TEMPLATE_IDS.items()}
    new_cfgs = []
    for new_id, (tpl_id, metric) in template_map.items():
        tpl = by_id[tpl_id]
        new_cfgs.append({
            "id": new_id,
            "metric": metric,
            "display_name": f"PROBE {new_id.rsplit('-', 1)[-1]} (layout of {tpl_id})",
            "enabled": True,
            "prediction_fields": ["human:loesung"],
            "reference_fields": tpl.get("reference_fields") or ["musterlösung"],
            "metric_parameters": json.loads(json.dumps(tpl["metric_parameters"])),
        })
    merged = [c for c in configs if c["id"] not in template_map] + new_cfgs
    admin.request("PUT", f"/api/evaluations/projects/{CLONE_PROJECT}/evaluation-config",
                  {"evaluation_configs": merged})
    after = admin.request("GET", f"/api/projects/{CLONE_PROJECT}")
    after_ids = {c["id"] for c in (after["evaluation_config"]["evaluation_configs"])}
    assert set(template_map) <= after_ids, "probe configs missing after PUT"
    assert set(by_id) <= after_ids, "pre-existing configs lost!"
    print(f"probe configs installed ({sorted(template_map)}); {len(after_ids)} configs total")

    # --- 4. filters + picks ---------------------------------------------------
    def write_filters(recs, path):
        filters = {}
        for row in texts:
            t = row["clone_task_id"]
            anns = [r for r in recs if r["clone_task_id"] == t]
            if not anns:
                continue
            filters[t] = {
                "model_ids": [],
                "annotator_ids": sorted({r["user_id"] for r in anns}),
                "targets": [r["annotation_id"] for r in anns],
            }
        path.write_text(json.dumps(filters, indent=1), encoding="utf-8")
        return len(filters)

    if add_types:
        n_new = write_filters(records, INTERIM / "probe_run_filters_positive.json")
        n_all = write_filters(all_records, INTERIM / "probe_run_filters_all.json")
        print(f"filters: positive ({n_new} exams), all-types ({n_all} exams)")
    else:
        write_filters(records, INTERIM / "probe_run_filters.json")
    picks = [{"pick_id": r["probe_id"], "provenance": r["probe_type"],
              "task_id": r["clone_task_id"], "target_type": "annotation",
              "target_id": r["annotation_id"], "system": None} for r in all_records]
    (INTERIM / "probe_picks.json").write_text(
        json.dumps({"clone_id": CLONE_PROJECT, "resolved": picks, "misses": []}, indent=1),
        encoding="utf-8")
    print(f"probe_picks ({len(picks)}) written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
