#!/usr/bin/env python3
"""Create the Bewertungsbogen-Audit project on a BenGER instance.

Drives ONLY deployed API surfaces (verified against origin/dev HEAD):
superadmin user registration + email verification, per-user profile-name
self-set, project creation with label config, eval-config write, nested
async import (presigned POST upload), and per-item korrektur assignment.

Inputs (from ``build_audit_import.py``): audit_import.json (tasks +
annotations with placeholder ``completed_by`` ids) and audit_users.json
(Kandidat spec incl. passwords). The placeholders are rewritten to the
REAL user ids after registration, so annotation authorship — the blind
code the graders see — is correct by construction.

Usage:
  uv run python scripts/ops/setup_audit_project.py \
      --base-url http://benger.localhost \
      [--admin-email admin@example.com] [--admin-password admin] \
      [--org-id <id>] [--assign auditor@x:1,2,3]  # user gets exams 1,2,3

Idempotence: safe to re-run user registration (409s tolerated); the
project is created fresh each run — delete a failed attempt in the UI
before retrying, or pass --project-id to reuse one.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
AUDIT = HERE / "data" / "interim" / "audit"

AUDIT_CRITERIA = {
    "vollstaendigkeit": {
        "name": "Vollständigkeit",
        "description": "Deckt der Bogen alle wesentlichen Prüfungsschritte der Musterlösung ab?",
        "rubric": "5 = keine wesentlichen Schritte fehlen; 1 = zentrale Prüfungsschritte fehlen.",
        "max_score": 5,
    },
    "treue": {
        "name": "Keine erfundenen Inhalte",
        "description": "Sind alle Schritte durch Sachverhalt/Musterlösung gedeckt (keine erfundenen Inhalte, Normen oder Zitate)?",
        "rubric": "5 = vollständig gedeckt; 1 = erfundene oder sachfremde Inhalte mit Punktgewicht.",
        "max_score": 5,
    },
    "externe_ergaenzungen": {
        "name": "Externe Ergänzungen",
        "description": "Sind als 'extern ergänzt' gekennzeichnete Inhalte fachlich zutreffend und begründet? (5, wenn keine vorhanden und keine nötig)",
        "rubric": "5 = Ergänzungen korrekt/begründet oder zu Recht keine; 1 = fachlich falsche oder unbegründete Ergänzungen.",
        "max_score": 5,
    },
    "gewichtung": {
        "name": "Gewichtung",
        "description": "Ist die Punktverteilung angemessen (Schwerpunkte deutlich gewichtet, Nebenpunkte nicht überbewertet)?",
        "rubric": "5 = überzeugende Schwerpunktsetzung; 1 = grobe Fehlgewichtung.",
        "max_score": 5,
    },
    "alternativen": {
        "name": "Vertretbare Alternativen",
        "description": "Werden vertretbare abweichende Lösungswege zutreffend erkannt und fair behandelt?",
        "rubric": "5 = einschlägige Alternativen erkannt und sachgerecht bepunktbar; 1 = vertretbare Wege fehlen oder werden bestraft.",
        "max_score": 5,
    },
    "teilpunkte": {
        "name": "Teilpunktstufen",
        "description": "Sind die Teilpunktstufen brauchbar formuliert (konkret, kumulativ, korrekturtauglich)?",
        "rubric": "5 = unmittelbar korrekturtauglich; 1 = Leerformeln oder unbrauchbare Stufen.",
        "max_score": 5,
    },
    "gesamturteil": {
        "name": "Gesamturteil",
        "description": "Würde ich nach diesem Bogen eine echte Klausur korrigieren?",
        "rubric": "5 = uneingeschränkt ja; 3 = mit Überarbeitung; 1 = nein.",
        "max_score": 5,
    },
}


class Client:
    """Talks DIRECTLY to the API host (api.localhost / api.what-a-benger.net)
    — the frontend's /api/auth proxy only implements a handful of handlers
    (register/verify are not among them), so all calls bypass it. Direct
    login is OAuth2 form-encoded; auth then rides the session cookie."""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )

    def request(self, method, path, payload=None, ok=(200, 201, 202), form=False, headers=None):
        if form:
            data = urllib.parse.urlencode(payload or {}).encode()
            ctype = "application/x-www-form-urlencoded"
        else:
            data = json.dumps(payload).encode() if payload is not None else None
            ctype = "application/json"
        req = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={"Content-Type": ctype, **(headers or {})},
        )
        try:
            with self.opener.open(req, timeout=180) as resp:
                body = resp.read().decode()
                if resp.status not in ok:
                    raise RuntimeError(f"{method} {path} -> {resp.status}: {body[:300]}")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            body = exc.read().decode()[:300]
            raise RuntimeError(f"{method} {path} -> {exc.code}: {body}") from exc

    def login(self, email, password):
        return self.request(
            "POST",
            "/api/auth/login",
            {"username": email, "password": password},
        )


def upload_presigned(presigned: dict, file_path: Path):
    """multipart/form-data POST: fields first, file LAST (S3 contract)."""
    boundary = uuid.uuid4().hex
    parts = []
    for k, v in (presigned.get("fields") or {}).items():
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
        )
    ctype = mimetypes.guess_type(str(file_path))[0] or "application/json"
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
        f"filename=\"{file_path.name}\"\r\nContent-Type: {ctype}\r\n\r\n".encode()
    )
    body = b"".join(parts) + file_path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        presigned["upload_url"],
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        if resp.status not in (200, 201, 204):
            raise RuntimeError(f"upload -> {resp.status}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--admin-email", default=os.environ.get("BENGER_ADMIN_EMAIL", "admin@example.com"))
    parser.add_argument("--admin-password", default=os.environ.get("BENGER_ADMIN_PASSWORD", "admin"))
    parser.add_argument("--org-id", default=None)
    parser.add_argument("--project-id", default=None, help="Reuse an existing project")
    parser.add_argument("--title", default="Bewertungsbogen-Audit")
    parser.add_argument("--skip-import", action="store_true",
                        help="Config-only rerun: leave existing tasks untouched")
    args = parser.parse_args()

    spec = json.loads((AUDIT / "audit_users.json").read_text(encoding="utf-8"))
    import_payload = json.loads((AUDIT / "audit_import.json").read_text(encoding="utf-8"))

    admin = Client(args.base_url)
    admin.login(args.admin_email, args.admin_password)
    print("logged in as admin")

    # --- 1. Kandidat users: register (superadmin) → verify → self-name ----
    id_map = {}
    for code, u in spec["users"].items():
        try:
            created = admin.request(
                "POST",
                "/api/auth/register",
                {
                    "username": u["username"],
                    "email": u["email"],
                    "name": u["name"],
                    "password": u["password"],
                    # Stub graders-of-record, never real annotators — profile
                    # fields are required by UserCreate but carry no meaning.
                    "legal_expertise_level": "layperson",
                    "german_proficiency": "native",
                },
            )
            real_id = created.get("id") or created.get("user", {}).get("id")
        except RuntimeError as exc:
            if "400" not in str(exc) and "409" not in str(exc):
                raise
            # already exists — look it up via login below
            real_id = None
        kandidat = Client(args.base_url)
        try:
            admin_lookup_needed = real_id is None
            if real_id:
                admin.request("PATCH", f"/api/users/{real_id}/verify-email", {})
            login = kandidat.login(u["email"], u["password"])
            real_id = real_id or (login.get("user") or {}).get("id")
            if real_id is None:
                profile = kandidat.request("GET", "/api/auth/profile")
                real_id = profile.get("id") or profile.get("user", {}).get("id")
            kandidat.request(
                "PUT", "/api/auth/profile", {"name": u["name"], "use_pseudonym": False}
            )
        except RuntimeError as exc:
            raise SystemExit(f"Kandidat {code} setup failed: {exc}")
        if not real_id:
            raise SystemExit(f"could not determine user id for {code}")
        id_map[u["user_id"]] = real_id
        print(f"  {code}: {u['name']} -> {real_id}")

    # Rewrite placeholder completed_by ids to real ids.
    for task in import_payload["data"]:
        for ann in task["annotations"]:
            ann["completed_by"] = id_map[ann["completed_by"]]

    # --- 2. Project --------------------------------------------------------
    if args.project_id:
        project_id = args.project_id
        print(f"reusing project {project_id}")
    else:
        body = {
            "title": args.title,
            "description": (
                "RQ1-Audit: 170 automatisch erzeugte Bewertungsbögen, blind "
                "codiert (Kandidat A–L). Bitte je Element den Reiter "
                "'Bewertung (Custom Rubrik)' verwenden."
            ),
            "label_config": spec["label_config"],
        }
        headers_extra = (
            {"X-Organization-Context": args.org_id} if args.org_id else {}
        )
        created = admin.request("POST", "/api/projects/", body, headers=headers_extra)
        project_id = created.get("id") or created.get("project", {}).get("id")
        print(f"created project {project_id}")

    # --- 3. Eval config (korrektur_custom, manual assignment, blinding) ---
    # The dedicated eval-config endpoint (NOT the generic project PATCH):
    # only this path runs the extended after_eval_config_save hook that
    # derives project.korrektur_enabled from the configs.
    admin.request(
        "PUT",
        f"/api/evaluations/projects/{project_id}/evaluation-config",
        {
            "evaluation_configs": [
                    {
                        "id": "korrektur_custom-audit",
                        "metric": "korrektur_custom",
                        "enabled": True,
                        "display_name": "Bewertungsbogen-Audit",
                        # EvaluationBuilder maps over prediction_fields
                        # unguarded — wizard-created entries always carry it,
                        # scripted ones must too or the eval-config UI crashes.
                        "prediction_fields": ["bogen"],
                        "reference_fields": ["musterlösung"],
                        "metric_parameters": {
                            "custom_criteria": AUDIT_CRITERIA,
                            "assignment_mode": "manual",
                            "blind_to_llm_judge": True,
                            "blind_to_non_judge_metrics": True,
                            "blind_to_peer_correctors": True,
                            "keep_blind_after_submit": True,
                            "allow_self_correction": False,
                            "instruction_markdown": (
                                "Bitte bewerten Sie jeden Bewertungsbogen "
                                "anhand der Dimensionen. Vergleichsmaßstab "
                                "sind Sachverhalt und Musterlösung (Reiter "
                                "oben). Bitte jedes Element einzeln "
                                "abschließen (Zwischenstände werden nicht "
                                "gespeichert)."
                            ),
                        },
                    }
            ]
        },
    )
    print("eval config written (korrektur_custom, manual, blind)")

    # --- 4. Nested import --------------------------------------------------
    if args.skip_import:
        print("skipping import (--skip-import)")
        print(f"DONE. Project: {args.base_url}/projects/{project_id}/korrektur")
        return 0
    tmp = AUDIT / "audit_import.resolved.json"
    tmp.write_text(json.dumps(import_payload, ensure_ascii=False), encoding="utf-8")
    presigned = admin.request(
        "POST",
        f"/api/projects/{project_id}/imports/upload-url?filename=audit_import.json",
    )
    upload_presigned(presigned, tmp)
    job = admin.request(
        "POST",
        f"/api/projects/{project_id}/imports",
        {"object_key": presigned["file_key"]},
    )
    job_id = job.get("job_id") or job.get("id")
    print(f"import job {job_id} started")
    for _ in range(120):
        time.sleep(5)
        status = admin.request("GET", f"/api/projects/{project_id}/imports/{job_id}")
        state = status.get("status")
        if state in ("completed", "failed", "error"):
            print(f"import {state}: {json.dumps(status.get('result') or status)[:300]}")
            if state != "completed":
                return 1
            break
    else:
        print("import still running after 10 min — check manually")
        return 1

    print(f"DONE. Project: {args.base_url}/projects/{project_id}/korrektur")
    print("Next: add graders as CONTRIBUTORs, then run assign_audit_items.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
