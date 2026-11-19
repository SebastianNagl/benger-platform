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
key checks above do not apply to it. Its requests count against a per-user
limit instead (`BEARER_TOKEN_RPM`, see [Limits](#limits-and-good-practice)).
Request a new one when it expires. Prefer a key for anything that runs
unattended.

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
| `evaluations:read`, `evaluations:run` | evaluation configuration, starting, pausing, cancelling evaluations, their status; starting analysis runs |
| `results:read` | evaluation results, statistics, significance, leaderboards, dashboards, reports, analysis runs and their estimates |
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
  "max_concurrent_requests": 2,
  "request_timeout_seconds": 900
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

`request_timeout_seconds` (30-1500, default 300) is how long one request to
the endpoint may take before it is cancelled and retried (up to 5 retries).
BenGER does not stream the answer, so the whole completion has to arrive
within it: a reasoning model that decodes 125 tokens per second fits about
37,000 tokens into the default. Raise it for long reasoning outputs; the
upper bound stays below the 1,800 s time limit of a generation job.

The run's seed is sent to a custom model unless the model declares
`"parameter_constraints": {"seed": {"supported": false}}`. Declare that only
for an endpoint that rejects the `seed` field; a run then records the seed as
not sent (see the generate call below).

Generation needs a prompt structure: a project without one answers the
generate call with 422 "This project has no prompt structure for
generation". `PUT /api/projects/{id}/generation-config/structures/{key}`
creates or replaces one; `name`, `system_prompt` and `instruction_prompt`
are required, and `{{field}}` in a prompt stands for that field of the
task. `GET /api/projects/{id}/generation-config/structures` lists the
existing ones. A project with structures needs `structure_keys` in the
generate call (step 6), otherwise it answers 422 and names them.

A structure also decides the answer format. By default a generation appends
the label config's answer fields as a JSON skeleton (a Repeater block as one
example object per item of the task) to the user prompt and asks the
provider for structured output; the listing shows the appended text as
`schema_instruction_preview`. To send a fixed prompt design unchanged, set
`append_schema_instruction: false` and `structured_output: "off"` (the
answer is then parsed from free text). Optional blocks:

* `format_retry: {"message": "..."}`: when an answer yields no answer field,
  ask once again in the same conversation (the answer as assistant turn,
  `message` as user turn). The generation keeps the first answer in
  `first_response_content` and sets `retried`.
* `answer_schema: {"fields": {"<control>": {"key": "...", "values": {"...":
  "<stored value>"}}}}`: answer keys and choice values that depend on the
  task, with `{{path}}` (or `{{path|lower}}`) standing for a task field, for
  example a key named after a party of the case. The parser reads them as the
  control name and the stored value.
* `refusal_heuristic: {"pattern": "...", "flags": "i", "window": 1500}`: mark
  an answer as a refusal when the pattern matches its first `window`
  characters (the provider's own refusal signal still counts).

Every generation stores what the provider client actually sent as
`request_record` (the first request's `model`, `messages`, `response_format`
and `parameters`, and every request verbatim under `requests`, a format retry
included) and `request_sha256`, the SHA-256 of the first request's body in
canonical JSON. `GET /api/runs/generations/{id}` names per trial the hash,
`has_request_record`, `retried` and `first_response_preview`;
`GET /api/runs/generations/{id}/trials/{trial_id}/request` returns that
trial's `request_record` and `request_sha256` (404 for a missing run or trial
or a trial of another run, 403 without access to the project). Project
exports carry both; importing an export keeps every generation column,
the job's `structure_key` and each answer's `run_index`.

`POST /api/llm-models/cost-estimate` (scope `runs:read`) takes
`project_id`, `mode` (`generation` or `evaluation`), `model_ids` and, to
match what the run will queue, `generation_mode` and `structure_keys`; for
an evaluation also `evaluation_configs`, `judge_models` and
`annotator_user_ids`. It returns `total_usd`, `per_model` and the counts it
priced (`tasks_total`, `subject_count`).

The generate call (`POST /api/generation-tasks/projects/{id}/generate`)
takes, besides `mode` and `model_ids`:

* `task_ids` (default: every task), `structure_keys`, `parameters`
  (`temperature`, `max_tokens`, `seed`, default 42), `model_configs` (per-model
  settings such as `max_tokens`, merged into the stored ones),
  `runs_per_task` (1-100) and `billing_organization_id` (the organisation
  whose provider keys pay, one of the caller's billing options);
* `mode` is `missing`, `all` or `single`. `all` regenerates every cell and
  cancels pending generations of the project, so only project members may
  use it (creator, or CONTRIBUTOR or higher of an attached organisation).

It answers `{project_id, mode, tasks_queued, models_count,
generation_job_ids, estimated_time_seconds, message}`.

Every generation requests a seed: the configured one, or 42 when none is
configured. A generation stores the seed that was actually sent, both on the
answer (`seed`) and in the run's `parameters`. A model that does not accept
a seed (Anthropic, Google, a custom model declared without seed support) gets
none; its answers then store `seed: null`, and the run's `parameters` and the
answer's metadata carry `seed_not_sent: {"requested": 42, "reason":
"unsupported_by_model" | "declared_unsupported"}`, which the run view shows.

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
project. Both routes check the project the evaluation belongs to, so a
key limited to projects or a group can poll its own runs, and a run of
any other project answers 404 `not_found`.

Which metrics exist and which fields they read: `GET
/api/evaluations/supported-metrics` and `GET
/api/evaluations/projects/{id}/available-fields`. The evaluation
configuration shown in the app is stored with
`PUT /api/evaluations/projects/{id}/evaluation-config` (deep merge, send
only the keys you change); a run with inline `evaluation_configs` on a
project that has none stores them there when the caller may edit the
project.

### Re-parsing stored answers

An answer is parsed once, when generation stores it, and keeps that parse
result when the parser later learns to read more answers (for example the
`answer`/`reasoning` keys that are now read as `kurzantwort`/`begruendung`).
`POST /api/projects/{id}/generations/reparse` re-reads given stored answers
with the current parser, exactly as a new answer is parsed: the project's
current label config, the prompt structure the answer was generated with,
and the task's `text` for span positions. It is for superadmins only; an
access key needs `admin:platform`.

The body is `{"generation_ids": [...], "dry_run": false}` with 1-1,000 ids
of stored answers (`id` of a generation result, not of the run). The
answer has `{project_id, dry_run, changed, unchanged, not_found, skipped,
results}`; each result names the `generation_id`, its `outcome` and, for
answers of the project, `before` and `after` with `parse_status`,
`parse_error`, the row `status`, the parsed `fields` and the `mapped_keys`.
An id that is not an answer of this project is `not_found`; an answer whose
prompt structure was deleted since is `skipped`.

* `dry_run: true` reports the outcome and writes nothing.
* The stored answer text (`response_content`) never changes, so an answer
  the parser cannot read (invalid JSON, misspelled keys) stays as it is and
  reports `unchanged`.
* A `changed` answer gets the new `parsed_annotation`, `parse_status` and
  `parse_error`, its row status follows the parse status as in generation,
  and its label config version becomes the project's current one. The
  previous values are appended to `parse_metadata.reparse_history` with
  `reparsed_at` and `reparsed_by`, so the earlier parse stays recoverable.
* An answer whose result does not change is not written, so a second call
  with the same ids reports every answer `unchanged`.

Scores computed from the old parse result stay as they are. Grade the
re-parsed answers again with `POST /api/evaluations/run`, narrowed with
`task_ids`, `model_ids` and `structure_keys` and with `force_rerun: true`;
the new scores are stored under the new evaluation run, next to the old
rows of the earlier run.

### Relabelling stored evaluation runs

A finished evaluation run is labelled from its rows: `model_id` names the
one model whose generations the rows graded, else `"unknown"`, and
`eval_metadata.evaluated_model_ids` lists the graded models, most rows
first. Runs that finished before that rule keep older labels (`"unknown"` on
a run that graded one model, or the project's most common model on a run
that graded several models or another one).
`POST /api/admin/evaluation-runs/relabel` applies the rule to stored runs.
It is for superadmins only; an access key needs `admin:platform`.

The body is `{"project_id": "...", "run_ids": [...], "dry_run": true,
"revert": false}`: the runs of `project_id`, the runs in `run_ids` (up to
5,000, of any project), or with both only those runs of the project.
`dry_run` defaults to `true`. The answer has `{dry_run, revert, changed,
unchanged, skipped, not_found, results}`; each result
names the `run_id`, `project_id`, run `status`, its `outcome`, the rows per
graded model (`graded_rows`), and `before` and `after` with `model_id`,
`evaluated_model_ids` and `evaluated_model_id`.

* `dry_run: true` reports the outcome and writes nothing.
* A `changed` run gets the label and `evaluated_model_ids` a run finishing
  now would get. Its previous `model_id` and `eval_metadata` are appended to
  `eval_metadata.relabel_history` with `relabeled_at`, `relabeled_by` and
  what was `applied`, so the earlier label stays recoverable. A run whose
  label already follows its rows is `unchanged` and not written, so a second
  call changes nothing.
* A run that graded no generation (a run over submitted answers) keeps its
  `model_id`, as at finalization, and gets an empty `evaluated_model_ids`,
  so no view lists it as having graded the model its label names. Its
  result has empty `graded_rows` and a `reason` saying so, and it is
  `changed` or `unchanged` and kept in `relabel_history` like any other
  run. A run that has not finished, and the human-graded (`human`) and
  immediate-grading (`immediate`) runs, are `skipped`.
* `revert: true` restores the `model_id` and `eval_metadata` from before
  the last relabel of each run. A run never relabelled, or changed after its
  relabel, is `skipped`.

A merge import matches a relabelled run by its label and by every label in
its `relabel_history`, so merging an export made before the relabel (on
either instance) does not add the run a second time. Scores are not
touched and the leaderboards, statistics and report sections read the
model per row, so they do not change (statistics and reports fall back to
the run label only when no row of the project names a model, and a
relabel changes only runs with such rows). Two views count a run under its
label and change with it: the evaluated-models list (its run count,
samples, last evaluation and average over each run's aggregated `metrics`)
and the significance tests called without `evaluation_config_ids` (which
add a run's aggregated `metrics` to the scores of the model it names).

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
* A few per-user ceilings stop runaway scripts. They sit far above what
  heavy use needs (large benchmark round trips, scripted imports and exports,
  many parallel evaluation runs), apply to every caller (key, script token or
  browser) unless noted, and do not apply to superadmins. Each refusal is a
  `429` with `Retry-After` in seconds and `{"detail": {"code": ..., "message":
  ..., "retry_after": ...}}`. The deployment sets them; `0` switches one off
  ([environment variables](setup/environment-variables.md#abuse-limits)):

  | Limit | Default | Code |
  |---|---|---|
  | requests with a script token (`POST /api/auth/token`, sent as `Authorization: Bearer`), per user and minute; browser sessions and keys are not counted | 1,200 (`BEARER_TOKEN_RPM`) | `rate_limited` |
  | import upload URLs (`POST /api/projects/{id}/imports/upload-url` and `POST /api/projects/project-imports/upload-url` together), per user in the last 24 hours | 200 (`UPLOAD_URLS_PER_DAY`) | `upload_url_limit_exceeded` |
  | generation and evaluation runs queued or running at once, per user that starts them | 50 (`MAX_ACTIVE_RUNS_PER_USER`) | `too_many_active_runs` |

  For the run limit an evaluation run is one `POST /api/evaluations/run`;
  generation work on one project counts as one run however many starts it
  took, so more generation on a project that already generates is never
  refused. Starting, resuming and retrying a run are checked; the answer has
  `limit` and `active` and `Retry-After: 60`. Wait for runs to finish, or
  pause or stop some, then start again.
* Long jobs (imports, exports, generation, evaluation) are asynchronous:
  start them, then poll their status route. Poll every few seconds, not in
  a tight loop.
* Generation and LLM-judge evaluation cost money: they run on the provider
  keys that the project's billing rules select, exactly as in the browser.
* Prefer a key limited to the projects a script needs, with the narrowest
  preset that works. Revoke keys you no longer use.
