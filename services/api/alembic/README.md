# Alembic Database Migrations

## Overview
This directory contains Alembic database migrations for the BenGER API. As of September 2025, all migrations have been consolidated into a single baseline migration for cleaner database rebuilds.

## Current State
- **Baseline Migration**: `331953c37025_complete_baseline_squashed.py`
- **Created**: 2025-09-05
- **Purpose**: Contains complete database schema for fresh installations

## Common Commands

### Apply all migrations
```bash
docker-compose exec api alembic upgrade head
```

### Generate new migration
```bash
docker-compose exec api alembic revision --autogenerate -m "description"
```

### Check current migration status
```bash
docker-compose exec api alembic current
```

### View migration history
```bash
docker-compose exec api alembic history
```

## Fresh Database Setup

For a completely fresh database setup:

```bash
# 1. Drop and recreate database (optional - only if starting completely fresh)
docker-compose exec db psql -U postgres -c "DROP DATABASE IF EXISTS benger;"
docker-compose exec db psql -U postgres -c "CREATE DATABASE benger;"

# 2. Apply migrations
docker-compose exec api alembic upgrade head

# 3. Initialize demo data
docker-compose exec api python init_complete.py
```

## Quick Rebuild

For development, use the complete initialization script:

```bash
docker-compose exec api python init_complete.py
```

This script will:
1. Apply any pending migrations
2. Create demo users (admin, contributor, annotator)
3. Set up TUM organization
4. Initialize feature flags

## Important Notes

- **No Manual Table Creation**: All tables are created via Alembic migrations
- **Data Seeding**: Demo data is added via `init_complete.py`, not in migrations
- **Baseline**: The current baseline includes all tables as of September 2025
- **Future Migrations**: Add incremental migrations on top of the baseline

## Troubleshooting

### Multiple migration heads
```bash
# Check for multiple heads
docker-compose exec api alembic heads

# If multiple heads exist, merge them
docker-compose exec api alembic merge -m "merge heads"
```

### Migration conflicts
```bash
# Check current database state
docker-compose exec api alembic current

# Compare database to models
docker-compose exec api alembic check
```

### Reset to baseline
```bash
# WARNING: This will drop all data!
docker-compose exec db psql -U postgres -d benger -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
docker-compose exec api alembic upgrade head
docker-compose exec api python init_complete.py
```