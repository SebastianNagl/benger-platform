# ADR-007: Versioned public API (`/api/v1`)

## Status

Accepted (October 2026). Supersedes ADR-006 "API Versioning Deferral"
(October 2025, removed from the tree; see `git show 9fb6c35f^:docs/architecture/adr-006-api-versioning-deferral.md`).

## Context

ADR-006 deferred API versioning because the only consumer of the API was
the BenGER frontend, deployed atomically with the API. It named the trigger
for revisiting the decision: external API consumers.

That trigger has fired. Benchmark pipelines of partner organisations fetch
tasks and exports from scripts, overlay products (the extended edition and
the compliance overlay) need a stable surface they can build on, and access
keys (`bgr_...`, migration 118) exist so that these clients no longer
borrow browser sessions. Such clients are deployed on their own schedule,
so a breaking change in the browser API would break them without warning.

## Decision

1. **Two surfaces.** The browser API (`/api/...`) stays internal and
   unversioned; it may change with any release, as ADR-006 allowed. The
   public API lives under `/api/v1` and is the only surface access keys may
   use (keys are refused everywhere else).
2. **URL versioning.** The major version is part of the path. A breaking
   change ships as `/api/v2` next to `/api/v1`; both run in the same
   process and share services, models and permission helpers.
3. **Compatibility rules for v1.** Only additive changes: new endpoints,
   optional parameters, response fields, error codes. Clients must ignore
   unknown fields. Removing or renaming anything, changing a type, or
   tightening validation requires a new version.
4. **Deprecation.** A deprecated operation answers with
   `X-API-Deprecated: true; sunset=<date>` (configured in
   `routers/v1/_middleware.py`), is announced in the changelog and keeps
   working for at least six months. Every v1 response carries
   `X-API-Version: 1`.
5. **One app, no sub-application.** The v1 routers are included into the
   main FastAPI app (`routers/v1/__init__.install_v1`). Mounting a separate
   ASGI app would bypass dependency overrides, the usage middleware and the
   startup checks.
6. **Deny by default.** Every v1 route declares its scopes
   (`require_scope` / `v1_project_access`); startup fails otherwise.
7. **Contract artefacts.** The spec of the v1 routes is served at
   `/api/v1/openapi.json` (public, independent of `INTERNAL_DOCS_ENABLED`)
   and committed as `docs/api-docs/openapi-v1.json`. A unit test compares the
   two, so every contract change is visible in review.
8. **Uniform conventions.** One error envelope
   (`{"error": {"code", "message", "request_id", "details"}}`), cursor
   pagination, `Idempotency-Key` on every POST, weak ETags on reads, key
   rate limits with `X-RateLimit-*`, and CORS for any origin without
   credentials. They apply to `/api/v1` only, so the browser API keeps its
   `{"detail": ...}` contract.
9. **Overlays.** Extension packages contribute v1 routers through
   `get_v1_routers()`; they mount under `/api/v1/<prefix>`, follow the same
   conventions and are checked for path collisions at startup.

## Consequences

* Positive: external clients get a contract with explicit change rules;
  the internal API keeps its freedom; reviews see contract changes in the
  snapshot diff; overlays share one public surface and one key model.
* Negative: v1 handlers duplicate some read logic of the browser API (thin
  serializers over the same helpers); two versions have to be maintained in
  parallel during a deprecation window; the snapshot must be regenerated
  (`make generate-public-api-docs`) with every contract change.
* Follow-ups: submissions, systems, runs, evaluations and results endpoints
  (the reserved scopes) and the key management UI.

## References

* [Public API guide](../public-api.md), [scope table](../public-api-scopes.md)
* [API keys](../api-keys.md)
* `services/api/routers/v1/`
