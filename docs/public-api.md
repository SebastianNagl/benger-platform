# Public API (`/api/v1`)

> **Kurz auf Deutsch:** Die öffentliche API unter `/api/v1` erlaubt Skripten
> und anderen Systemen den Zugriff auf BenGER ohne Browser-Sitzung. Man
> authentifiziert sich mit einem Zugangsschlüssel (`bgr_...`), den
> Organisations-Admins in den Organisationseinstellungen und alle Nutzenden
> im eigenen Profil anlegen. Jeder Schlüssel trägt Berechtigungen (Scopes)
> und sieht nur die Projekte, die seine Rolle sehen darf. Musterlösungen
> bleiben verborgen, solange der Schlüssel nicht ausdrücklich
> `tasks:read_reference` besitzt und seine Rolle die vollen Aufgabendaten
> sehen darf. Die Schnittstelle ist versioniert; Änderungen, die bestehende
> Clients brechen, kommen nur mit einer neuen Version und mindestens sechs
> Monaten Vorlauf. Alles Weitere, was die App kann (eigene Modelle,
Generierung, Evaluation, Annotation, Verwaltung), erreichen dieselben
Schlüssel über die [vollständige API](full-api.md). Der Rest dieser Seite
ist auf Englisch.

The public API is the stable, versioned contract for integrations: benchmark
pipelines that fetch tasks, scripts that export projects, and overlay
products built on top of BenGER. Everything else the app can do is reachable
with the same keys through the [full API](full-api.md): the routes the
browser uses, each opened for keys by a scope rule. Those routes are not
versioned and may change with any release, so prefer `/api/v1` where it
covers your need.

* Live reference: `GET /api/v1/docs` (Swagger UI) and
  `GET /api/v1/openapi.json` on any deployment. Both are public.
* Committed snapshot: [`api-docs/openapi-v1.json`](api-docs/openapi-v1.json)
  (regenerate with `make generate-public-api-docs`).
* Key model, service accounts and the usage log: [API keys](api-keys.md).
* Everything beyond v1 (models, generation, evaluation, annotation,
  administration): [Full API](full-api.md), live reference
  `GET /api/v1/reference`.
* Why the API is versioned: [ADR-007](architecture/adr-007-api-versioning-adopted.md).

## Authentication

Every request (except the two documentation endpoints) carries an access key:

```
Authorization: Bearer bgr_<env>_<id>_<secret>
```

* `env` is `live` in production and `test` everywhere else. A key only works
  on a deployment with the same tag.
* `bgr_<env>_<id>` is the key prefix. It is shown in key lists and in
  `GET /api/v1/me` and identifies a key without revealing it.
* The full key is shown once, when it is created. Store it in a secret
  manager; a lost key is replaced, not recovered.
* Keys are never accepted in a cookie or a query string. Outside `/api/v1`
  they work only where a rule opens the route ([full API](full-api.md));
  sign-in, password and similar routes answer
  `401 api_key_not_allowed_here`.

**Personal keys** act as their owner and see what the owner sees.
**Organisation keys** act as their own service account with the role chosen
at creation (ANNOTATOR or CONTRIBUTOR, never admin), optionally restricted to
one group of the organisation. Either kind can be limited to a list of
projects. A browser session also works on `/api/v1` (the session token is
read from the `Authorization` header first); it passes every scope check.

`GET /api/v1/me` tells a client what its key may do:

```json
{
  "principal": {
    "kind": "api_key",
    "key_prefix": "bgr_live_k3Yx9Q2a",
    "scopes": ["projects:read", "tasks:read"],
    "project_ids": ["2b7c..."],
    "organization": {"id": "f1e0...", "name": "Lehrstuhl X", "slug": "lehrstuhl-x"},
    "group": null,
    "expires_at": "2027-03-31T00:00:00+00:00",
    "rate_limit": {"per_minute": 120, "per_day": 20000}
  },
  "user": {"id": "9a4d...", "username": "svc-k3Yx9Q2a", "name": "API-Zugang: pipeline", "is_service_account": true}
}
```

`scopes` lists the granted scopes including the ones they imply.
`project_ids` is `null` when the key has no project list. For a session,
`kind` is `session`, `scopes` is `["*"]` and `organization` is the user's
oldest active membership. A personal key reports `organization: null`
because it acts across all of its owner's organisations.

## Scopes

Each operation needs the scopes listed under `x-benger-scopes` in the spec.
A key without them gets `403 insufficient_scope` (with
`WWW-Authenticate: Bearer error="insufficient_scope", scope="..."`). The
full table, generated from the code, is in
[public-api-scopes.md](public-api-scopes.md). The scopes used by the
endpoints on this page:

| Scope | Needed for |
|---|---|
| (none) | `GET /api/v1/me` |
| `projects:read` | listing and reading projects |
| `tasks:read` | reading tasks (blinded, see below) |
| `tasks:read_reference` | reading tasks with reference solutions; also required for exports. Only grantable to personal keys and CONTRIBUTOR organisation keys |
| `exports:read` | starting, polling and downloading exports |

The other scopes (`runs:*`, `evaluations:*`, `results:read`, `models:*`,
`projects:write`, `tasks:write`, `annotations:*`, `account:*`, `org:*`,
`files:*`, `keys:manage`, `admin:platform`) open routes of the
[full API](full-api.md); `submissions:*` and `systems:*` are reserved for
endpoints that follow in later releases of version 1. Overlays (extension
packages) can add scopes and endpoints of their own under `/api/v1/<overlay>`.

## Endpoints

| Method and path | Scopes | Purpose |
|---|---|---|
| `GET /api/v1/me` | none | the calling key or session |
| `GET /api/v1/projects` | `projects:read` | projects the key may read (paginated) |
| `GET /api/v1/projects/{project_id}` | `projects:read` | one project |
| `GET /api/v1/projects/{project_id}/tasks` | `tasks:read` | the project's tasks (paginated, ETag) |
| `GET /api/v1/projects/{project_id}/tasks/{task_id}` | `tasks:read` | one task (ETag) |
| `POST /api/v1/projects/{project_id}/exports` | `exports:read`, `tasks:read_reference` | start an export job (idempotent) |
| `GET /api/v1/exports/{job_id}` | `exports:read`, `tasks:read_reference` | poll an export job |
| `GET /api/v1/exports/{job_id}/download` | `exports:read`, `tasks:read_reference` | `302` to a presigned download URL (valid 5 minutes) |
| `GET /api/v1/openapi.json`, `GET /api/v1/docs` | public | the spec and Swagger UI |
| `GET /api/v1/reference/openapi.json`, `GET /api/v1/reference` | public | spec and Swagger UI of the [full API](full-api.md) |

### Projects

The list contains the projects the key's user can read (public projects,
own projects and projects of its organisations), narrowed by the key's
project list and group, never including projects that require the Safe Exam
Browser. A project the key may not see answers `404`, whether or not it
exists. Projects a user only reaches as a participant (shared exams,
enrolments, org exams) or through an own submission are listed as well;
`access.tier` is then `participant` or `attempted`.

```json
{
  "id": "2b7c...",
  "title": "Zivilrecht Klausur 3",
  "description": "...",
  "kind": "exam",
  "task_count": 12,
  "bound_fields": ["sachverhalt"],
  "answer_fields": [{"name": "antwort", "type": "TextArea", "to_name": "sv", "options": null}],
  "created_at": "2026-09-01T10:00:00+00:00",
  "updated_at": "2026-10-01T08:30:00+00:00",
  "access": {"tier": "full", "effective_role": "ANNOTATOR", "blinded": true}
}
```

`bound_fields` are the task data keys the project's labeling configuration
renders; `answer_fields` are the inputs an answer fills in.
`access.blinded` says whether this key receives reduced task data.

### Tasks

```json
{
  "id": "8e21...",
  "inner_id": 4,
  "data": {"sachverhalt": "A verkauft B ..."},
  "meta": {"tags": ["zivilrecht"], "benchmark": {"rechtsgebiet": "BGB AT"}},
  "updated_at": "2026-10-01T08:30:00+00:00"
}
```

**Blinding.** For a key, `data` is reduced to the project's `bound_fields`
and `meta` to its tags and public benchmark descriptors (legal area, type,
audience, origin, working time) unless the key holds
`tasks:read_reference` **and** the role of the key's user on that project
sees full task data (ORG_ADMIN or CONTRIBUTOR, or the project creator). A
personal key of an annotator therefore stays blinded whatever scopes it
holds. The reference solution, the editing history (`meta.audit_log`) and
grading internals never reach a blinded key. Unlike the browser, a key
never gets the "show the solution after submitting" reveal. Sessions see
what the browser shows them.

Tasks are ordered by `inner_id`. The usual access rules apply: annotators
in manual or auto assignment mode see their open assignments, a timed
project answers `403 project_window_upcoming` before its window opens, and
a user who only holds the read-only "attempted" tier sees their own
submissions.

### Exports

An export contains the complete, unblinded project data, so it needs
`exports:read`, `tasks:read_reference` and the ORG_ADMIN or CONTRIBUTOR
role on the project, checked again on every poll and download.

```http
POST /api/v1/projects/{project_id}/exports
Idempotency-Key: nightly-2026-10-13
Content-Type: application/json

{"format": "json"}
```

`format` is one of `json` (default), `ndjson`, `ndjson_gz`, `csv`, `tsv`,
`comprehensive`, `label_studio`; `task_ids` restricts a `json` export to a
subset. The answer is `202` with the job and a `Location` header. Poll
`GET /api/v1/exports/{id}` until `status` is `completed`, then follow
`download_url` (a `302` to object storage, valid for 5 minutes). Finished
exports expire after 7 days (`410 export_expired`).

## Pagination

Lists take `?limit=` (1 to 200, default 50) and `?cursor=` and answer

```json
{"items": [...], "next_cursor": "eyJpZCI6Ii4uLiJ9"}
```

Pass `next_cursor` unchanged to fetch the next page; it is `null` on the
last page. Cursors are opaque (do not build or parse them) and belong to one
list; a foreign or damaged cursor answers `400 invalid_cursor`.

## Conditional requests (ETags)

Task reads carry a weak `ETag` and `Last-Modified`. Send the ETag back as
`If-None-Match` to get `304 Not Modified` with an empty body when nothing
changed. The tag covers the project, the number and newest change of the
visible tasks, the page position and the blinding decision, so a key that
gains `tasks:read_reference` does not reuse a blinded cache entry.

## Idempotency

Every `POST` accepts an optional `Idempotency-Key` header (1 to 255
characters, for example a UUID or a job name). For 24 hours, a retry with the
same key and the same request (method, path, query and body) returns the
first response again with `Idempotent-Replayed: true` instead of creating a
second job. Reusing a key for a different request answers
`422 idempotency_key_reused`; a retry while the first request is still
running answers `409 idempotency_in_progress`. Failed requests are not
stored, so they can be retried with the same key. Keys are scoped to the
calling key (or session user) and route.

## Rate limits

Each key has a per-minute and a per-day budget (shown in `/api/v1/me`).
Every answer to a key request carries `X-RateLimit-Limit`, `X-RateLimit-Remaining` and
`X-RateLimit-Reset` (Unix time of the window end). An exhausted budget
answers `429 rate_limited` with `Retry-After` in seconds. Back off for that
long; do not retry in a tight loop. Sessions are not limited here.

## Errors

All errors on `/api/v1` use one envelope:

```json
{
  "error": {
    "code": "insufficient_scope",
    "message": "This API key lacks the scope(s): exports:read",
    "request_id": "c0ffee...",
    "details": {"required_scopes": ["exports:read"]}
  }
}
```

Branch on `code`, not on `message` (which is for humans and may change).
`request_id` equals the `X-Request-ID` response header; send your own
`X-Request-ID` to correlate logs, and quote it when reporting a problem.
Common codes:

| Status | Code | Meaning |
|---|---|---|
| 400 | `invalid_cursor`, `invalid_idempotency_key` | malformed parameter |
| 401 | `unauthorized`, `invalid_api_key`, `api_key_revoked`, `api_key_expired`, `api_key_owner_inactive` | no usable credential |
| 403 | `insufficient_scope` | the key lacks a scope |
| 403 | `forbidden`, `organization_inactive`, `project_window_upcoming` | role, organisation or time window forbids it |
| 404 | `not_found`, `task_not_found`, `export_not_found`, `export_not_ready` | unknown, invisible or not ready |
| 409 | `idempotency_in_progress` | duplicate POST still running |
| 410 | `export_expired` | start a new export |
| 422 | `validation_error`, `idempotency_key_reused` | invalid body or query (`details.errors` lists the fields) |
| 429 | `rate_limited` | budget exhausted, see `Retry-After` |
| 503 | `service_unavailable` | temporary, retry with backoff |

## CORS

`/api/v1` can be called from any web origin: responses carry
`Access-Control-Allow-Origin: *` and never allow credentials (cookies are
not sent). Preflights allow `Authorization`, `Content-Type`,
`Idempotency-Key`, `If-None-Match` and `X-Request-ID`. Do not embed a key in
public web pages; anyone who can read the page can use the key.

## Versioning and deprecation

* Every response carries `X-API-Version: 1`.
* Within version 1 we only make additive changes: new endpoints, new
  optional parameters, new fields in responses, new error codes, new enum
  values in documented-as-open fields. Clients must ignore unknown fields.
* Removing or renaming a field or an endpoint, changing a type, or making a
  rule stricter needs a new version (`/api/v2`), which runs side by side
  with version 1.
* Before an operation goes away it is deprecated: its responses carry
  `X-API-Deprecated: true; sunset=<YYYY-MM-DD>`, the changelog announces it,
  and it keeps working for at least **six months** after the announcement.
  After the sunset date it may be removed.

## Data protection

* **Blinding.** Keys receive reference solutions only when both the scope
  and the role allow it (see Tasks); `seb_required` exams are invisible to
  keys.
* **Usage log.** Every request made with a key is logged with the route
  template (never the concrete URL), project id, status, duration, scope,
  a shortened client IP (`API_USAGE_IP_MODE`, default IPv4 /24 and IPv6 /48)
  and user agent. Request and response bodies are never stored.
  Organisation admins can view and export the log of their keys,
  superadmins across organisations.
* **Retention.** Usage events are deleted after `API_USAGE_RETENTION_DAYS`
  (default 400 days). Deleting a user removes their personal keys and
  unlinks their usage history; anonymising a user removes IP and user agent
  from it. Export files are deleted from object storage after 7 days.
* **Responsibility.** Data fetched through the API is subject to the same
  terms as data seen in the browser. Organisation admins decide which
  projects a key may reach and revoke keys that are no longer needed.

## Examples

### curl

```bash
export BENGER_KEY=bgr_live_...           # from your secret store
API=https://api.what-a-benger.net        # or your deployment's PUBLIC_API_URL

curl -s -H "Authorization: Bearer $BENGER_KEY" "$API/api/v1/me"

curl -s -H "Authorization: Bearer $BENGER_KEY" "$API/api/v1/projects?limit=20"

# First page of tasks, then a conditional re-fetch
curl -si -H "Authorization: Bearer $BENGER_KEY" \
  "$API/api/v1/projects/$PROJECT_ID/tasks?limit=100" | tee page.txt
curl -si -H "Authorization: Bearer $BENGER_KEY" \
  -H "If-None-Match: $(grep -i '^etag:' page.txt | cut -d' ' -f2- | tr -d '\r')" \
  "$API/api/v1/projects/$PROJECT_ID/tasks?limit=100"

# Export with an idempotency key, then download
curl -s -X POST -H "Authorization: Bearer $BENGER_KEY" \
  -H "Idempotency-Key: export-$(date +%F)" -H "Content-Type: application/json" \
  -d '{"format": "json"}' "$API/api/v1/projects/$PROJECT_ID/exports"
curl -sL -H "Authorization: Bearer $BENGER_KEY" -o export.json \
  "$API/api/v1/exports/$JOB_ID/download"
```

### Python

```python
import os
import time

import requests

API = os.environ.get("BENGER_API", "https://api.what-a-benger.net")
session = requests.Session()
session.headers["Authorization"] = f"Bearer {os.environ['BENGER_KEY']}"


def get(path, **params):
    while True:
        r = session.get(f"{API}{path}", params=params, timeout=30)
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", "5")))
            continue
        if r.status_code >= 400:
            error = r.json()["error"]
            raise RuntimeError(f"{error['code']}: {error['message']} ({error['request_id']})")
        return r.json()


def all_items(path, limit=100):
    cursor = None
    while True:
        page = get(path, limit=limit, **({"cursor": cursor} if cursor else {}))
        yield from page["items"]
        cursor = page["next_cursor"]
        if cursor is None:
            return


print(get("/api/v1/me")["principal"]["scopes"])
for project in all_items("/api/v1/projects"):
    tasks = list(all_items(f"/api/v1/projects/{project['id']}/tasks"))
    print(project["title"], len(tasks), "blinded" if project["access"]["blinded"] else "full")
```
