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

## Models — the two divergent `models.py` files

The repo currently has **two** independently-maintained SQLAlchemy `Base`-bound model files:

- `services/api/models.py` — 43 classes (the more complete view).
- `services/workers/models.py` — 28 classes (a subset, plus 5 classes the API doesn't have).

23 classes appear in both. **They have drifted.** Spot-check: the API's `User` carries the email-verification, password-reset, invitation, and pseudonym columns; the worker's `User` is missing all of them. A worker query like `db.query(User).filter(User.email_verified == True)` would raise `AttributeError` at runtime — the column doesn't exist on the worker side of the metadata.

This is the underlying cause of the `ProjectReport` duplicate-Table footgun I tripped on 2026-05-19 when moving `report_models.py` to `/shared`.

### Why it persists

Refactoring the 48 unique classes (23 duplicated + 20 API-only + 5 worker-only) into a single canonical source on `/shared/models.py` would touch ~50 files (every `from models import X`) plus require relationship-resolution ordering verification on the worker side. It needs its own planning session and a careful rollout.

### Rules until consolidation

1. **When you add or modify a column on a shared class** (e.g., User, Organization, Project, EvaluationRun), update **both** files. Add the change to the worker file even if the worker doesn't immediately read the column — divergence creates the next ProjectReport-style footgun.
2. **When you add a model to `/shared`**, make sure every relationship target it references (`relationship("Project", …)`, etc.) is on the metadata before the first query. Eager-import via `import project_models  # noqa` in the worker's `tasks.py` top-level, mirroring the pattern at `tasks.py:262`.
3. **When you delete a parallel class** (as I did with worker `ProjectReport` on 2026-05-19), grep for every remaining `from models import <classname>` worker-side and re-point it at the canonical `/shared` module.
4. Before raising an MR that touches a class declared on both sides, run a quick diff:
   ```
   diff <(grep -A60 "^class FOO(Base):" services/api/models.py) \
        <(grep -A60 "^class FOO(Base):" services/workers/models.py)
   ```
   to see the current divergence and decide whether your change widens or narrows it.

### Planned consolidation (deferred)

Future migration to a single `/shared/models/` package:

| Step | Action | Risk |
|---|---|---|
| 1 | Schema-diff the 23 duplicated classes; document differences | low — read-only |
| 2 | Pick the API-side version as canonical for each | med — needs review |
| 3 | Move canonical files to `/shared/models/<class>.py` | low — copy |
| 4 | Update worker's `from models import X` to `from shared.models.X import X` | high — ~50 files |
| 5 | Delete worker's `models.py` duplicates | high — verify no runtime path lost |
| 6 | Add the worker-only 5 classes (`Prompt`, `LLMResponse`, `SyntheticDataGeneration`, `AnnotationStatus`, `TaskVisibility`) to `/shared/models/` | low |
| 7 | Add the API-only 20 classes to `/shared/models/` for worker visibility | low — worker doesn't query them but having them on the same Base avoids future relationship-resolution gaps |

Estimate: 2–3 focused days. The right time is during a quiet release window with full test coverage in place; piecemeal moves risk the relationship-resolution footgun without the safety of a single sweep.

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
