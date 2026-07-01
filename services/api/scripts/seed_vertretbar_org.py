#!/usr/bin/env python3
"""Seed the "Vertretbar" organization that holds the owner's grading key.

Vertretbar students grade their exams on the platform owner's LLM key. That
works by reusing the existing org-key mechanism: a dedicated organization with
``settings.require_private_keys = False`` plus the owner's provider key stored as
that org's ``organization_api_keys`` row. ``get_ai_service_for_user`` then
resolves the org key for any grading dispatched against this org — which is
exactly what the extended billing gate does for a metered student grading.

The default exam judge is ``gpt-5.4-mini`` (``DEFAULT_EXAM_JUDGE_MODEL`` in the
extended student_exams router), whose provider is **openai** — so by default
this stores the owner's OpenAI key. Override with ``--provider`` if you change
the judge model to another provider (e.g. ``anthropic``).

This script is idempotent: it creates the org if missing, forces
``require_private_keys = False``, and upserts the key. Re-running it is safe
(e.g. to rotate the key).

Key resolution order (first hit wins), for the chosen --provider (default openai):
  1. --api-key <key>
  2. $OPENAI_API_KEY   (or $<PROVIDER>_API_KEY)
  3. the owner's own stored key for that provider (user_api_key_service)

Owner resolution order:
  1. --owner-username / --owner-id
  2. the single is_superadmin=True user (errors if there are 0 or >1)

Usage:
  # Preview (no writes):
  python seed_vertretbar_org.py
  # Apply, pulling the owner's stored OpenAI key (the gpt-5.4-mini judge):
  python seed_vertretbar_org.py --apply --owner-username pschOrr95
  # Apply with an explicit key / env:
  OPENAI_API_KEY=sk-... python seed_vertretbar_org.py --apply

After --apply, set VERTRETBAR_ORG_ID to the printed id (docker-compose .env /
Helm) so the extended billing gate scopes metering to this org.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (
    "/shared",
    "/app",
    os.path.dirname(_HERE),  # services/api when run from the repo
    os.path.join(os.path.dirname(os.path.dirname(_HERE)), "shared"),  # services/shared
):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

import models  # noqa: E402,F401 — register User/... before relationships
import project_models  # noqa: E402,F401
from database import SessionLocal  # noqa: E402
from models import Organization, User  # noqa: E402

VERTRETBAR_SLUG = "vertretbar"
# The default exam judge (gpt-5.4-mini) is an OpenAI model, so the Vertretbar org
# needs the owner's OpenAI key. Override with --provider if you change the judge.
DEFAULT_PROVIDER = "openai"


def _resolve_owner(db, args) -> User:
    if args.owner_id:
        owner = db.query(User).filter(User.id == args.owner_id).first()
        if not owner:
            raise SystemExit(f"No user with id={args.owner_id!r}")
        return owner
    if args.owner_username:
        owner = db.query(User).filter(User.username == args.owner_username).first()
        if not owner:
            raise SystemExit(f"No user with username={args.owner_username!r}")
        return owner
    supers = db.query(User).filter(User.is_superadmin == True).all()  # noqa: E712
    if not supers:
        raise SystemExit("No is_superadmin user found; pass --owner-username/--owner-id")
    if len(supers) > 1:
        names = ", ".join(u.username for u in supers)
        raise SystemExit(
            f"Multiple superadmins ({names}); disambiguate with --owner-username"
        )
    return supers[0]


def _resolve_key(db, owner, args) -> str | None:
    if args.api_key:
        return args.api_key
    env_key = os.getenv(f"{args.provider.upper()}_API_KEY")
    if env_key:
        return env_key
    # Fall back to the owner's own stored key for this provider.
    try:
        try:
            from services.user_api_key_service import user_api_key_service
        except ImportError:
            from user_api_key_service import user_api_key_service

        return user_api_key_service.get_user_api_key(db, owner.id, args.provider)
    except Exception:
        return None


def _get_or_create_org(db, apply: bool) -> tuple[Organization, bool]:
    org = db.query(Organization).filter(Organization.slug == VERTRETBAR_SLUG).first()
    created = False
    if org is None:
        org = Organization(
            id=str(uuid.uuid4()),
            name="Vertretbar",
            display_name="Vertretbar",
            slug=VERTRETBAR_SLUG,
            description="Holds the owner's grading key for vertretbar.net students.",
            settings={"require_private_keys": False},
            is_active=True,
        )
        created = True
        if apply:
            db.add(org)
    else:
        settings = dict(org.settings or {})
        if settings.get("require_private_keys") is not False:
            settings["require_private_keys"] = False
            org.settings = settings
    return org, created


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write changes (default: preview)")
    parser.add_argument("--owner-username", help="username of the key-owning superadmin")
    parser.add_argument("--owner-id", help="id of the key-owning superadmin")
    parser.add_argument(
        "--provider",
        default=DEFAULT_PROVIDER,
        help="provider key to store, matching the judge model (default: openai)",
    )
    parser.add_argument("--api-key", help="key to store (else env, else owner's stored key)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        owner = _resolve_owner(db, args)
        api_key = _resolve_key(db, owner, args)
        org, created = _get_or_create_org(db, args.apply)

        print(f"Owner:        {owner.username} ({owner.id})")
        print(f"Vertretbar org: {'CREATE' if created else 'EXISTS'} id={org.id} slug={org.slug}")
        print(f"  require_private_keys -> False")
        if api_key:
            masked = api_key[:7] + "…" + api_key[-4:] if len(api_key) > 12 else "***"
            print(f"  {args.provider} key: {masked} (source resolved)")
        else:
            env_name = f"{args.provider.upper()}_API_KEY"
            print(f"  {args.provider} key: NONE FOUND — pass --api-key or set ${env_name},")
            print("                 or store one on the owner account first.")

        if not args.apply:
            print("\nPreview only. Re-run with --apply to write.")
            return 0

        # Org must be flushed so the FK on organization_api_keys resolves.
        db.flush()

        wrote_key = False
        if api_key:
            from services.org_api_key_service import org_api_key_service

            if org_api_key_service is None:
                raise SystemExit("org_api_key_service unavailable (encryption_service missing)")
            wrote_key = org_api_key_service.set_org_api_key(
                db, org.id, args.provider, api_key, created_by=owner.id
            )
            if not wrote_key:
                raise SystemExit(
                    f"Failed to store the org key — check the {args.provider} key format."
                )

        db.commit()
        print("\nApplied.")
        print(f"  -> set VERTRETBAR_ORG_ID={org.id}")
        if not wrote_key:
            print("  -> org key NOT set (no key resolved); set it before grading works.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
