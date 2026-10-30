# Full API (access keys on every route)

> **Kurz auf Deutsch:** Seit Core 2.45 funktionieren Zugangsschlüssel
> (`bgr_...`) nicht nur unter `/api/v1`, sondern auf allen Routen der App,
> die eine Regel für Schlüssel öffnet: eigene Modelle registrieren,
> Generierung und Evaluation starten, Ergebnisse lesen, annotieren,
> Projekte und Organisationen verwalten. Jede Route nennt die nötigen
> Scopes; die Rechte der Rolle gelten wie im Browser. Anmeldung, Passwort,
> Registrierung und ähnliche Routen bleiben dem Browser vorbehalten. Diese
> Routen sind nicht versioniert und können sich mit jedem Release ändern.
> Der Rest dieser Seite ist auf Englisch.

The [public API](public-api.md) under `/api/v1` is the small, versioned
contract. Everything else the app can do is reachable with the same access
keys through the **full API**: the routes the browser itself uses, each
opened for keys by a rule that names the scopes it needs.

* Live reference: `GET /api/v1/reference` (Swagger UI) and
  `GET /api/v1/reference/openapi.json` on any deployment. Each operation
  lists its scopes under `x-benger-scopes`, and `x-benger-project-bound`
  marks routes a project-limited key may call only for its projects.
* Every route and its rule: [full-api-routes.md](full-api-routes.md)
  (generated from `services/api/app/core/key_routes.py`).
* Key model, scopes, service accounts, usage log: [API keys](api-keys.md).
* Python client: [`clients/python`](../clients/python/README.md)
  (`pip install ./clients/python`, `from benger_client import BengerClient`).

## Stability

The full API is **not versioned**. Routes, payloads and responses follow
the web app and can change with any release. Use `/api/v1` where it covers
your need, pin your scripts to what the reference shows today, and expect
to adapt them. Responses carry `X-Request-ID`; quote it when you report a
problem.

## Authentication and rules

Send the key as `Authorization: Bearer bgr_<env>_<id>_<secret>`, never as a
cookie or query parameter. For every request with a key outside `/api/v1`
the API checks, in this order:

| Check | Failure |
|---|---|
| the route accepts keys at all | `401 api_key_not_allowed_here` |
| the key is valid, active and of this deployment | `401 invalid_api_key`, `api_key_revoked`, `api_key_expired` |
| the API feature is switched on for the key | `404 feature_disabled` |
| the key holds the route's scopes | `403 insufficient_scope` (`required_scopes` in the body) |
| the projects the request names are visible to the key (project list, group, no Safe Exam Browser project) | `404 not_found` |
| a project- or group-limited key names a project on a project-level route | `403 key_project_restricted` |
| rate limit | `429 rate_limited` with `Retry-After` |

After these checks the route runs as it does for a browser session of the
key's user: a personal key has exactly its owner's rights, an organisation
key the rights of its role (ANNOTATOR, CONTRIBUTOR or ORG_ADMIN) in its
organisation and, for group keys, its group. A key keeps its owner's
superadmin rights only with the scope `admin:platform`.

Errors on these routes use FastAPI's shape, usually
`{"detail": {"code": "...", "message": "..."}}` and sometimes
`{"detail": "text"}` or a validation list; the v1 error envelope applies to
`/api/v1` only.

### What keys can never do

Sign in, refresh or end sessions, change or reset passwords, register,
verify e-mail addresses, change the profile (it carries the e-mail
address), accept invitations, launch through an LMS (LTI), download Safe
Exam Browser configurations, use billing and checkout, seed test data or
call diagnostics. Projects that require the Safe Exam Browser are never
reachable with a key. WebSocket progress streams do not accept keys; poll
the status routes instead.

## Scopes on the full API

| Scope | Opens |
|---|---|
| `account:read`, `account:write` | own account (`/api/auth/me`), notifications, display settings, joining and leaving projects through share links |
| `org:read`, `org:manage` | organisations, members, groups, invitations, storage connections, LMS registrations |
| `projects:read`, `projects:write` | projects, label configuration, members, shares, reports, imports (with `tasks:write`) |
| `tasks:read_reference` | every route that returns task content (task lists, single tasks, rubrics, next task) |
| `tasks:write` | creating, editing, assigning, archiving, deleting tasks and rubrics |
| `annotations:read`, `annotations:write` | annotations, drafts, checkpoints, questionnaires, reviews, human evaluation, grading |
| `models:read`, `models:manage` | model catalog, own OpenAI-compatible models (BYOM), provider API keys of the user or organisation |
| `runs:read`, `runs:write` | generation configuration, prompt structures, starting and controlling generation, generation results |
| `evaluations:read`, `evaluations:run` | evaluation configuration, starting, pausing, cancelling evaluations, their status |
| `results:read` | evaluation results, statistics, significance, leaderboards, dashboards, reports |
| `exports:read` | exports (with `tasks:read_reference`, because exports are unblinded) |
| `files:read`, `files:write` | uploaded files and object-storage uploads |
| `keys:manage` | access keys of the owner and, for org admins, the organisation |
| `admin:platform` | superadmin routes (personal keys of superadmins only) |

The preset **`full_access`** bundles what a research pipeline needs:
account, organisation read, projects, tasks with reference data, task
writes, annotations, models, runs, evaluations, results, exports and files.

## Example: register a model, generate, evaluate

The steps a research team takes to benchmark its own model on an existing
project. `$API` is the deployment's base URL, `$KEY` a personal key (or a
CONTRIBUTOR organisation key) with the `full_access` preset.

```bash
API=https://api.what-a-benger.net   # the API host; what-a-benger.net/api/... works too
H="Authorization: Bearer $KEY"

# 1. Who am I, what may this key do?
curl -s -H "$H" "$API/api/v1/me"

# 2. Register an OpenAI-compatible endpoint as a private model (BYOM)
curl -s -H "$H" -H "Content-Type: application/json" -X POST "$API/api/custom-models/" -d '{
  "name": "Our legal model v3",
  "base_url": "https://llm.example.org/v1",
  "endpoint_model_name": "legal-v3",
  "api_key": "sk-..."
}'
# -> {"id": "custom-...", ...}; check it once:
curl -s -H "$H" -X POST "$API/api/custom-models/$MODEL_ID/test"

# 3. Select the model for the project (PATCH deep-merges generation_config)
curl -s -H "$H" -H "Content-Type: application/json" -X PATCH "$API/api/projects/$PROJECT_ID" -d '{
  "generation_config": {"selected_configuration": {"models": ["'$MODEL_ID'"]}}
}'

# 4. Generate answers for every task still missing one, then poll
curl -s -H "$H" -H "Content-Type: application/json" -X POST \
  "$API/api/generation-tasks/projects/$PROJECT_ID/generate" -d '{"mode": "missing", "model_ids": ["'$MODEL_ID'"]}'
curl -s -H "$H" "$API/api/projects/$PROJECT_ID/generation-status"

# 5. Evaluate the new answers against the reference field and poll
curl -s -H "$H" -H "Content-Type: application/json" -X POST "$API/api/evaluations/run" -d '{
  "project_id": "'$PROJECT_ID'",
  "model_ids": ["'$MODEL_ID'"],
  "evaluation_configs": [{"id": "bleu-1", "metric": "bleu",
    "prediction_fields": ["antwort"], "reference_fields": ["musterloesung"]}]
}'
curl -s -H "$H" "$API/api/evaluations/evaluation/status/$EVALUATION_ID"

# 6. Results per task and model
curl -s -H "$H" "$API/api/evaluations/run/results/project/$PROJECT_ID"
```

The prompt structures of the project decide what the model sees: a project
with structures needs `structure_keys` in step 4
(`GET /api/projects/{id}/generation-config/structures` lists them). Which
metrics exist and which fields they read: `GET
/api/evaluations/supported-metrics` and `GET
/api/evaluations/projects/{id}/available-fields`. The evaluation
configuration shown in the app is stored with
`PUT /api/evaluations/projects/{id}/evaluation-config` (deep merge, send
only the keys you change). New tasks come in through the import flow:
`POST /api/projects/{id}/imports/upload-url`, upload the file to the
returned URL, then `POST /api/projects/{id}/imports` with the
`object_key` and poll `GET /api/projects/{id}/imports/{job_id}`.

The same flow with the Python client:

```python
from benger_client import BengerClient

with BengerClient() as bg:  # BENGER_API_KEY / BENGER_BASE_URL from the environment
    model = bg.models.register_custom(
        name="Our legal model v3",
        base_url="https://llm.example.org/v1",
        endpoint_model_name="legal-v3",
        api_key="sk-...",
    )
    ...
```

See the client README for the complete example.

## Limits and good practice

* Paths are used exactly as the reference lists them, including a trailing
  slash where it shows one (`/api/projects/`, `/api/custom-models/`); other
  spellings answer with a redirect, so let your HTTP client follow
  redirects or use the listed path.
* Rate limits are the key's own (per minute and per day), shared between
  `/api/v1` and the full API. Every response carries `X-RateLimit-*`.
* Long jobs (imports, exports, generation, evaluation) are asynchronous:
  start them, then poll their status route. Poll every few seconds, not in
  a tight loop.
* Generation and LLM-judge evaluation cost money: they run on the provider
  keys that the project's billing rules select, exactly as in the browser.
* Prefer a key limited to the projects a script needs, with the narrowest
  preset that works. Revoke keys you no longer use.
