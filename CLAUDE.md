# BenGER Platform — local notes for contributors

This file documents conventions specific to `benger-platform/`. For the broader workspace context (open-core split, CI/CD, infra), see the parent-level CLAUDE.md at `../CLAUDE.md`.

## Database — sync vs async

The API has two database engines, both backed by the same Postgres instance:

| Use | Engine | Session | Dependency |
|---|---|---|---|
| **New code (default)** | `database.async_engine` (asyncpg) | `AsyncSession` | `db: AsyncSession = Depends(get_async_db)` |
| Existing sync code | `database.engine` (psycopg2) | `Session` | `db: Session = Depends(get_db)` |

The async lane is the target. The sync lane stays in place during the migration so nothing breaks; existing handlers convert one PR at a time. See `/Users/sebastiannagl/.claude/plans/double-check-your-findings-wild-pillow.md` for the multi-phase migration plan.

### Writing a new handler (async, the default)

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_async_db
from models import LLMModel

@router.get("/models/{model_id}")
async def get_model(
    model_id: str,
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(select(LLMModel).where(LLMModel.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Not found")
    return model
```

Key differences from the sync style:
- `select(M).where(...)` instead of `db.query(M).filter(...)`
- `await db.execute(stmt)` instead of `stmt.first()` / `stmt.all()`
- `result.scalar_one_or_none()` / `result.scalars().all()` to unpack
- `await db.commit()` instead of `db.commit()`

### Converting an existing sync service to dual-mode (Phase 2 pattern)

Services with `db: Session` parameters are the bottleneck for converting routers. Expose **both** sync and async entry points sharing the SQL builder:

```python
def _build_select_active_tokens(user_id: str):
    return select(RefreshToken).where(RefreshToken.user_id == user_id)

# Legacy sync callers
def get_active_refresh_tokens_sync(db: Session, user_id: str):
    return db.execute(_build_select_active_tokens(user_id)).scalars().all()

# New async callers
async def get_active_refresh_tokens(db: AsyncSession, user_id: str):
    result = await db.execute(_build_select_active_tokens(user_id))
    return result.scalars().all()
```

The sync entry point stays until every caller migrates.

### What stays sync forever

- **Workers (`services/workers/`)** — Celery process pool, no event loop. Use `SessionLocal()` directly.
- **Scripts (`services/api/scripts/`)** — CLI one-shots.
- **Alembic** — the migration runner in `main.py:lifespan()` uses its own short-lived sync engine + advisory lock.
- **Schema validator** (`main.py`) — runs once on startup.

### Why `application_name=benger-api-async` matters

The async engine's connections show `application_name='benger-api-async'` in `pg_stat_activity`; the sync engine uses `'benger-api'`. During the migration window, this lets us tell at a glance how much traffic each lane is taking, and gates Phase 5 (decommissioning the sync engine) — we need a clean canary window with zero `benger-api` traffic before deleting the sync code.

### Tests

- `test_db: Session` — sync legacy (unchanged)
- `async_test_db: AsyncSession` — async, SAVEPOINT-isolated, fresh engine per test
- `async_test_client: AsyncClient` — wires `Depends(get_async_db)` to `async_test_db`

Use the async fixtures when testing async handlers. Example: `services/api/tests/integration/test_async_db_foundation.py`.

## Models — single canonical source in `/shared`

Three model files have been consolidated to `/shared` (2026-05-19):

| File | Location | Contains |
|---|---|---|
| `models.py` | `services/shared/models.py` | Users, Orgs, Notifications, EvaluationRun/Type, Generation, etc. — 43 classes |
| `project_models.py` | `services/shared/project_models.py` | Project, Task, Annotation, TaskAssignment, TimerSession, KorrekturComment, etc. — 13 classes |
| `report_models.py` | `services/shared/report_models.py` | ProjectReport |

All resolved automatically by `from models import X` / `from project_models import X` / `from report_models import X` because `/shared` is first on `sys.path` in both containers (`api/main.py` and `workers/tasks.py` insert it at position 0 during startup; `workers/tests/conftest.py` adds it for pytest too).

The repo previously had independently-maintained parallel copies in `services/api/` and `services/workers/` that had actively drifted. Most notably the worker's `User` was missing 45 columns the API carried (email verification, invitation tokens, password reset, pseudonym, …) — a worker query like `db.query(User).filter(User.email_verified == True)` would `AttributeError` at runtime. The consolidation also caught three model classes (`EvaluationType`, `Invitation`, `UserNotificationPreference`) where the worker carried stale/wrong column or table names that no longer matched the DB, and 5 worker-only classes that were entirely dead code. project_models.py had a similar story: API was a clean superset everywhere.

### Rules

1. **Touch `/shared/models.py` / `/shared/project_models.py` / `/shared/report_models.py`**, not the (now-deleted) per-service copies. There is no longer a second place to also update.
2. **Don't put model files into `services/api/` or `services/workers/`** — the import system will resolve to the `/shared` versions regardless, but redundant copies just reintroduce the drift problem.
3. **When you add a model that declares `relationship("Project", …)`** or similar, `project_models` must be on the metadata before the first query. The worker's `tasks.py` already eagerly imports `project_models` at module load (see `tasks.py:~262`); follow that pattern in any other entry point that wants to query relationship-bearing models.
4. **For one-shot scripts and `python -c` exploration**, import in the correct order: `models` first (registers `User`, `Notification`, etc.), then `project_models` (which references `User` via relationships). Reverse order raises `InvalidRequestError: expression 'User' failed to locate a name`.

## Health checks — what `/health` covers and what it doesn't

`/health` (`services/api/routers/health.py`) is the K8s liveness probe and Docker healthcheck. It checks the deps the API itself needs to function:

| Dep | Mode | On failure | Why |
|---|---|---|---|
| Redis | required | 503 (K8s evicts) | WS pub/sub, rate limiter, session cache |
| Postgres | required | 503 (K8s evicts) | every request reads / writes |
| Celery workers | soft | 200, `status="degraded"` | API still serves sync; async tasks just queue |

**Not in `/health`:** third-party providers (SendGrid, OpenAI, Anthropic, etc.).

The reasoning: those are dependencies of *features* (notification email, model generation) rather than the app process itself, and pinging them on every K8s liveness probe (every 30 s × N replicas) would burn third-party quota — SendGrid's free tier is 100/day; two replicas at 30 s would consume the day's budget in 25 minutes. Treat third-party uptime as **operational monitoring**, not application liveness:

- `/health/email` exists as a superadmin-only diagnostic — run on demand when investigating a delivery issue.
- For continuous monitoring, point an external uptime tool (Grafana Synthetic, Better Uptime, the SendGrid status dashboard, etc.) at the provider directly. The result lives outside the API process so a provider outage doesn't change our pod's eviction state.
- If you ever do add a third-party check to `/health`, cache its result in Redis with a multi-minute TTL so K8s probes don't proxy through to the third party.

## Object storage (MinIO) — required, both editions

Project import and export run **exclusively** through object storage (issue #158 + follow-up). There is no synchronous fallback in either edition:

- **No silent local fallback.** `services/shared/storage/object_storage.py` raises at init if `STORAGE_TYPE` is `s3`/`minio` but boto3 is missing or the backend can't initialize — the pod CrashLoops instead of writing exports to `/tmp`. The filesystem `local` backend survives only as an explicit **test/dev double**, reached when `STORAGE_TYPE=local` (tests, bare runs). Deployed Helm always sets `minio` (`minio.enabled` defaults to `true` in `infra/helm/benger/values.yaml`).
- **Async-only API surface.** Export: `POST /{id}/exports` (202, optional `{"task_ids":[...]}` for a json-only subset) → worker streams to storage → poll `GET .../{job_id}` → `GET .../download` (presigned 302). Import: `POST /{id}/imports/upload-url` (nested) or `POST /project-imports/upload-url` (create-new) → client uploads straight to storage → `POST .../imports {object_key}` → poll the job. The old `GET /{id}/export`, `POST /{id}/import`, `POST /import-project` are **deleted**.
- **Bulk bytes never transit the API thread or the Next proxy.** The Next route proxy (`app/api/[...path]/route.ts`) no longer has an export-specific undici long-timeout path; its generic attachment/streamable branch stays for report CSV/zip/PDF downloads.
- **Deployment pre-requisite:** the `benger-minio-credentials` Secret (`access-key` + `secret-key`) must exist in the target namespace before deploy, or api/workers CrashLoop on the missing `secretKeyRef`. Multi-project admin exports (`POST /bulk-export`, `/bulk-export-full`) are a separate feature and remain synchronous.
