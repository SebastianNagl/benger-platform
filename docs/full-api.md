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
  `GET /api/v1/reference/openapi.json`. They need no login but answer
  `404 feature_disabled` unless the `public_api` feature flag lets the caller
  in; anonymous callers pass only while it is set to everyone
  ([Availability](api-keys.md#availability)). Each operation
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
| the API feature is switched on for the key ([Availability](api-keys.md#availability)) | `404 feature_disabled` |
| the key holds the route's scopes | `403 insufficient_scope` (`required_scopes` in the body) |
| the projects the request names are visible to the key (project list, group, no Safe Exam Browser project) | `404 not_found` |
| a project- or group-limited key names a project on a project-level route | `403 key_project_restricted` |
| rate limit | `429 rate_limited` with `Retry-After` |

After these checks the route runs as it does for a browser session of the
key's user: a personal key has exactly its owner's rights, an organisation
key the rights of its role (ANNOTATOR, CONTRIBUTOR or ORG_ADMIN) in its
organisation and, for group keys, its group. A key keeps its owner's
superadmin rights only with the scope `admin:platform`.

A script that signs in with a password instead of a key can call
`POST /api/auth/token` with `{"username": ..., "password": ...}` and send the
`access_token` from the answer as `Authorization: Bearer <access_token>`. The
token is valid for 60 minutes, comes without a refresh token and carries the
user's full rights with no scopes: it acts like a browser session, so the
key checks above do not apply to it. Request a new one when it expires. Prefer a key for
anything that runs unattended.

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
CONTRIBUTOR or ORG_ADMIN organisation key) with the `full_access` preset.

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
  "api_key": "sk-...",
  "max_concurrent_requests": 2
}'
# -> {"id": "custom-...", ...}; check it once with a short chat request:
curl -s -H "$H" -H "Content-Type: application/json" -X POST \
  "$API/api/custom-models/$MODEL_ID/test" -d '{"chat_ping": true}'

# 3. Select the model for the project (PATCH deep-merges generation_config)
curl -s -H "$H" -H "Content-Type: application/json" -X PATCH "$API/api/projects/$PROJECT_ID" -d '{
  "generation_config": {"selected_configuration": {"models": ["'$MODEL_ID'"]}}
}'

# 4. Create the prompt structure the model answers with ({{field}} = a task field)
curl -s -H "$H" -H "Content-Type: application/json" -X PUT \
  "$API/api/projects/$PROJECT_ID/generation-config/structures/default" -d '{
  "name": "Default",
  "system_prompt": "You answer questions on German law.",
  "instruction_prompt": "{{question}}"
}'

# 5. Estimate the cost first
curl -s -H "$H" -H "Content-Type: application/json" -X POST "$API/api/llm-models/cost-estimate" -d '{
  "project_id": "'$PROJECT_ID'", "mode": "generation", "model_ids": ["'$MODEL_ID'"],
  "generation_mode": "missing", "structure_keys": ["default"]
}'

# 6. Generate answers for every task still missing one, then poll
curl -s -H "$H" -H "Content-Type: application/json" -X POST \
  "$API/api/generation-tasks/projects/$PROJECT_ID/generate" \
  -d '{"mode": "missing", "model_ids": ["'$MODEL_ID'"], "structure_keys": ["default"]}'
curl -s -H "$H" "$API/api/projects/$PROJECT_ID/generation-status"

# 7. Evaluate the new answers against the reference field and poll
curl -s -H "$H" -H "Content-Type: application/json" -X POST "$API/api/evaluations/run" -d '{
  "project_id": "'$PROJECT_ID'",
  "model_ids": ["'$MODEL_ID'"],
  "structure_keys": ["default"],
  "evaluation_configs": [{"id": "bleu-1", "metric": "bleu",
    "prediction_fields": ["__all_model__"], "reference_fields": ["musterloesung"]}]
}'
curl -s -H "$H" "$API/api/evaluations/evaluation/status/$EVALUATION_ID"

# 8. Results of this run, and per task and model for the whole project
curl -s -H "$H" "$API/api/evaluations/run/results/$EVALUATION_ID"
curl -s -H "$H" "$API/api/evaluations/run/results/project/$PROJECT_ID"
```

`max_concurrent_requests` (1-256, default 2) is how many requests a
generation run keeps in flight against the endpoint at once; further jobs
wait in BenGER's queue instead of running into their time limit at a slow
server.

Generation needs a prompt structure: a project without one answers the
generate call with 422 "This project has no prompt structure for
generation". `PUT /api/projects/{id}/generation-config/structures/{key}`
creates or replaces one; `name`, `system_prompt` and `instruction_prompt`
are required, and `{{field}}` in a prompt stands for that field of the
task. `GET /api/projects/{id}/generation-config/structures` lists the
existing ones. A project with structures needs `structure_keys` in the
generate call (step 6), otherwise it answers 422 and names them.

`POST /api/llm-models/cost-estimate` (scope `runs:read`) takes
`project_id`, `mode` (`generation` or `evaluation`), `model_ids` and, to
match what the run will queue, `generation_mode` and `structure_keys`; for
an evaluation also `evaluation_configs`, `judge_models` and
`annotator_user_ids`. It returns `total_usd`, `per_model` and the counts it
priced (`tasks_total`, `subject_count`).

The generate call (`POST /api/generation-tasks/projects/{id}/generate`)
takes, besides `mode` and `model_ids`:

* `task_ids` (default: every task), `structure_keys`, `parameters`
  (`temperature`, `max_tokens`, `seed`), `model_configs` (per-model
  settings such as `max_tokens`, merged into the stored ones),
  `runs_per_task` (1-25) and `billing_organization_id` (the organisation
  whose provider keys pay, one of the caller's billing options);
* `mode` is `missing`, `all` or `single`. `all` regenerates every cell and
  cancels pending generations of the project, so only project members may
  use it (creator, or CONTRIBUTOR or higher of an attached organisation).

It answers `{project_id, mode, tasks_queued, models_count,
generation_job_ids, estimated_time_seconds, message}`.

The evaluation run (`POST /api/evaluations/run`) takes `project_id` and
`evaluation_configs`, and optionally `task_ids`, `model_ids`,
`annotator_user_ids` and `structure_keys` to narrow what is graded,
`force_rerun` (default false: only cells without a result are graded),
`batch_size`, `label_config_version`, `seed` and `billing_organization_id`.
In `prediction_fields`, `__all_model__` grades the model generations and
`human:<field>` a submitted annotation. The answer carries the
`evaluation_id`. `GET /api/evaluations/evaluation/status/{evaluation_id}`
returns `{id, status, message, progress}`, where `progress` is null until
the run is dispatched and then 0-100. `GET
/api/evaluations/run/results/{evaluation_id}` returns the results of one
run, `GET /api/evaluations/run/results/project/{id}` those of the whole
project. The status route names no project, so a key limited to projects
or a group gets 403 `key_project_restricted` there; poll with an
unrestricted key or read the run through the project's results.

Which metrics exist and which fields they read: `GET
/api/evaluations/supported-metrics` and `GET
/api/evaluations/projects/{id}/available-fields`. The evaluation
configuration shown in the app is stored with
`PUT /api/evaluations/projects/{id}/evaluation-config` (deep merge, send
only the keys you change); a run with inline `evaluation_configs` on a
project that has none stores them there when the caller may edit the
project.

### Round trip

New tasks come in through the nested import: write them as
`{"data": [{...task fields...}, ...]}`, get an upload form with
`POST /api/projects/{id}/imports/upload-url?filename=tasks.json`, upload the
file, then `POST /api/projects/{id}/imports` with `{"object_key":
"<file_key>"}` and poll `GET /api/projects/{id}/imports/{job_id}`.

To benchmark a model on a copy of a project (for example on another
deployment) and bring its results back, the steps are:

1. Export: `POST /api/projects/{id}/exports?format=ndjson_gz` (the format
   is a query parameter, not a body field) returns `{job_id, status}`.
   Poll `GET /api/projects/{id}/exports/{job_id}` until `status` is
   `completed`, then `GET .../download?json=1` returns `{url, expires_in}`.
2. Upload: `POST /api/projects/project-imports/upload-url?filename=<name>.ndjson.gz`
   returns `{upload_url, method, file_key, fields, expires_at}`. POST the
   file to `upload_url` as multipart form data with every entry of
   `fields` unchanged and the file last as `file`; never send the BenGER
   key to storage. `file_key` becomes the `object_key` of the next call.
3. Import as a new project: `POST /api/projects/project-imports` with
   `{"object_key": "<file_key>", "organization_id": "<org id>"}`
   (without `organization_id` the copy is the caller's private project;
   `model_id_map` translates model ids here too). Poll
   `GET /api/projects/project-imports/{job_id}`; its `project_id` is the
   copy.
4. Generate in the copy as above and export it as in step 1.
5. Merge into the original: upload the copy's export with
   `POST /api/projects/{id}/imports/upload-url?filename=<name>.ndjson.gz`,
   then `POST /api/projects/{id}/imports` with `{"object_key":
   "<file_key>", "mode": "merge", "dry_run": true, "model_id_map":
   {"<model id in the file>": "<model id here>"}}`. The dry run completes
   with format `merge_preview` and the preview in `result.statistics`
   without writing anything; send the same body without `dry_run` to
   merge. Custom models get a new id on every deployment, so map every
   custom model of the file; every target must exist here.
6. Poll `GET /api/projects/{id}/imports/{job_id}` until `status` is
   `completed` or `failed` (`error_code` such as `merge_task_mismatch` or
   `merge_unknown_models`).

Each uploaded file may be up to 5 GiB. The details, including what counts
as already present: [merge results back into an existing
project](project-migration.md#merge-import-results-back-into-an-existing-project).

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
