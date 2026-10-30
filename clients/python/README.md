# benger-client

A Python client for the [BenGER](https://what-a-benger.net) API. It uses access
keys (`bgr_<env>_<id>_<secret>`) and covers both API surfaces:

* **`/api/v1`**: the small, versioned contract (`me`, projects, tasks,
  exports). See `docs/public-api.md`.
* **The full API**: every other route an access key may call, unversioned.
  `docs/full-api-routes.md` lists each route with the scopes it needs.

Requires Python 3.10 or newer; the only dependency is `httpx`.

## Install

```bash
pip install ./clients/python          # from a checkout of benger-platform
# or, for development
cd clients/python && python -m venv .venv && .venv/bin/pip install -e '.[dev]'
```

## Quickstart

Create an access key in your profile (personal key) or in the organisation
settings (organisation key), give it the scopes you need, and export it:

```bash
export BENGER_API_KEY=bgr_live_...                    # from your secret store
export BENGER_BASE_URL=https://api.what-a-benger.net  # the default; set it for other deployments
```

```python
from benger_client import BengerClient

with BengerClient() as benger:
    me = benger.me()
    print(me["principal"]["scopes"], me["principal"]["rate_limit"])

    for project in benger.projects.list():
        tasks = benger.tasks.list(project["id"])
        print(project["title"], len(tasks), "blinded" if project["access"]["blinded"] else "full")
```

`BengerClient(api_key=None, base_url=None, *, timeout=60, max_retries=3)`
reads the key from `BENGER_API_KEY` and the deployment from
`BENGER_BASE_URL` (default `https://api.what-a-benger.net`). The key is never
shown in `repr`, logs or exception messages; `client.key_prefix` gives the
public part (`bgr_live_k3Yx9Q2a_***`).

### Any route

Every full-API route is callable through the generic methods, which return
the decoded JSON:

```python
benger.get("/api/evaluations/supported-metrics")
benger.post("/api/llm-models/cost-estimate", json={...})
benger.request("PATCH", "/api/projects/<id>", json={"description": "..."})
benger.raw_request("GET", "/api/v1/exports/<id>/download")  # httpx.Response, redirects not followed
```

Paths are relative to the deployment root. Absolute URLs are accepted only
for the configured host, so the key cannot leak to another server.

### Errors

Failed requests raise `BengerAPIError` with `status`, `code`, `message`,
`request_id` and `details`. Both error shapes are understood: the v1
envelope `{"error": {...}}` and the full API's `{"detail": ...}`. Branch on
`code`, not on `message`.

| Exception | When |
|---|---|
| `AuthenticationError` | 401 (`invalid_api_key`, `api_key_expired`, `api_key_not_allowed_here` ...) |
| `InsufficientScopeError` | 403 `insufficient_scope`; `.required_scopes` lists what is missing |
| `PermissionDeniedError` | other 403 (role, time window, `key_project_restricted`) |
| `NotFoundError` | 404, including projects the key may not see |
| `ValidationError` | 422; `details["errors"]` holds FastAPI field errors |
| `RateLimitError` | 429 after the retries were used up; `.retry_after` |
| `ServerError` | 5xx |
| `BengerJobError` | an import, export, generation or evaluation job failed |
| `BengerTimeoutError` | a `wait` helper ran out of time |

### Retries and idempotency

* A `429` is retried up to `max_retries` times, waiting as long as
  `Retry-After` says.
* `5xx` answers and connection errors are retried with exponential backoff
  for GET/HEAD/OPTIONS and for requests that carry an `Idempotency-Key`.
* Every `POST` to `/api/v1/...` carries an `Idempotency-Key` (a fresh UUID
  per call, kept across its retries). Pass `idempotency_key="nightly-2026-10-30"`
  to make reruns of a script return the same job.

## Research workflow: your own model, generation and evaluation

The scopes this needs: `models:manage`, `projects:write`, `tasks:write`,
`runs:write`, `evaluations:run`, `results:read` (and `projects:read`,
`runs:read`, `evaluations:read` for polling). The key's user needs the
CONTRIBUTOR or ORG_ADMIN role on the project. The full script is
[`examples/research_pipeline.py`](examples/research_pipeline.py).

```python
from benger_client import BengerClient

with BengerClient() as benger:
    # 1. Register an OpenAI-compatible endpoint as a private model.
    model = benger.models.register_custom(
        name="our-legal-llm-7b",
        base_url="https://inference.example.org/v1",  # serves /chat/completions
        endpoint_model_name="our-legal-llm-7b",
        api_key=ENDPOINT_KEY,  # the endpoint's key, stored encrypted
    )
    print(benger.models.test(model["id"], chat_ping=True))

    # 2. A project with one input and one reference field, and its tasks.
    project = benger.projects.create(
        "Contract law QA",
        label_config=(
            '<View><Text name="question" value="$question"/>'
            '<TextArea name="answer" toName="question"/></View>'
        ),
    )
    benger.imports.upload(
        project["id"],
        [
            {"data": {"question": "Ist ein Vertrag ohne Form wirksam?", "reference_answer": "..."}},
        ],
    )

    # 3. Generate.
    benger.generation.configure(project["id"], models=[model["id"]])
    started = benger.generation.start(project["id"], mode="missing", temperature=0.0, seed=42)
    print(benger.generation.wait(project["id"], started)["counts"])

    # 4. Evaluate and read the scores.
    benger.evaluations.configure(
        project["id"],
        [
            {
                "id": "bleu-answer",
                "metric": "bleu",
                "prediction_fields": ["__all_model__"],
                "reference_fields": ["reference_answer"],
            }
        ],
    )
    run = benger.evaluations.run(project["id"])
    benger.evaluations.wait(run)
    print(benger.evaluations.results(run["evaluation_id"])["aggregated_metrics"])
```

## Helpers

| Helper | Routes |
|---|---|
| `me()` | `GET /api/v1/me` |
| `projects.list() / page() / get(id, full=False)` | `/api/v1/projects` (cursor-paginated); `full=True` uses `GET /api/projects/{id}` |
| `projects.create(title, ...) / update(id, **fields) / delete(id)` | `POST /api/projects/`, `PATCH/DELETE /api/projects/{id}` (config fields deep-merge) |
| `tasks.iter(project_id) / list / page / get` | `/api/v1/projects/{id}/tasks` |
| `imports.upload(project_id, source, wait=True)` | presigned upload, `POST /api/projects/{id}/imports`, poll |
| `imports.create_project(source, organization_id=None)` | `/api/projects/project-imports` (comprehensive export file) |
| `models.catalog() / list_custom() / register_custom(...) / test(id) / test_endpoint(url) / set_credential / credential_status / set_visibility / update_custom / delete` | `/api/llm_models/public/models`, `/api/custom-models/...` |
| `generation.configure / set_structure / start / status / wait / job / task_status / result` | `PATCH /api/projects/{id}`, `/api/projects/{id}/generation-config/structures/{key}`, `/api/generation-tasks/...`, `/api/projects/{id}/generation-status` |
| `evaluations.configure / get_config / run / status / wait / results / project_results / by_task_model / cancel / supported_metrics` | `/api/evaluations/...` |
| `exports.create / get / wait / download(job, path=None)` | `/api/v1/projects/{id}/exports`, `/api/v1/exports/{id}[/download]` |
| `wait_until(callable, timeout, interval)` | polls any callable until it returns something truthy |

Notes:

* **Imports** go straight to object storage: the client asks for a
  presigned POST, uploads the file there (without the BenGER key), then
  starts the import job and polls it. The nested task format is
  `{"data": [{"data": {...}, "meta": {...}}, ...]}`; a plain list of task
  items is wrapped for you.
* **Generation config**: `generation.configure` patches the project, which
  deep-merges `generation_config`. `PUT /api/projects/{id}/generation-config`
  replaces the whole document, so prefer the helper.
* **Keys limited to a project list** cannot call routes that name no
  project, such as `GET /api/evaluations/evaluation/status/{id}`. Pass
  `project_id=` to `evaluations.status` / `evaluations.wait` to poll through
  the project-scoped run list instead. Generation polling is always
  project-scoped.
* **Downloads**: `exports.download` follows the `302` to the presigned URL
  itself, without the access key, and streams to `path`.

## Development

```bash
cd clients/python
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

The tests use `httpx.MockTransport` and never touch the network.

## License

Apache-2.0, like the rest of BenGER. See [LICENSE](LICENSE).
