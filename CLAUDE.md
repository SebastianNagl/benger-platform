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
