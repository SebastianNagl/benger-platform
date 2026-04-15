# API Service

FastAPI backend for the BenGER platform with comprehensive schema validation and migration integrity system.

## Features

- RESTful API with FastAPI
- JWT-based authentication
- Multi-organization support
- Database schema validation
- Migration health monitoring
- Automatic schema drift detection

## Setup

See main project README for general setup instructions.

## Schema Validation

The API includes a comprehensive schema validation system that prevents deployment with database inconsistencies.

### Configuration

Set the validation mode via environment variable:

```bash
# Strict mode (recommended for production) - fails on schema errors
SCHEMA_VALIDATION_MODE=strict

# Lenient mode - logs warnings but continues
SCHEMA_VALIDATION_MODE=lenient  

# Disabled - skip validation (not recommended)
SCHEMA_VALIDATION_MODE=disabled
```

### Startup Validation

The API automatically validates the database schema on startup:
- Checks for missing tables and columns
- Verifies foreign key type consistency
- Validates migration history
- Reports issues before accepting requests

### Manual Validation

Run schema validation manually:

```bash
# Check migration health
python scripts/check_migration_health.py

# Monitor for schema drift
python scripts/monitor_schema_drift.py

# Compare models with migrations
python scripts/compare_schemas.py
```

## Database Migrations

### Creating Migrations

```bash
# Generate migration from model changes
alembic revision --autogenerate -m "descriptive_name"

# Create manual migration
alembic revision -m "descriptive_name"
```

### Testing Migrations

Always test migrations before deployment:

```bash
# Run migration tests
pytest tests/test_migrations.py

# Test up/down/up cycle
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```

### Best Practices

See [Migration Best Practices](docs/MIGRATION_BEST_PRACTICES.md) for detailed guidelines.

## Monitoring

### Production Schema Monitoring

Set up daily monitoring for schema drift:

```bash
# Add to crontab
0 2 * * * python /app/scripts/monitor_schema_drift.py --email admin@example.com
```

### Health Endpoints

- `/health` - Basic health check
- `/health/schema` - Schema validation status

## Testing

```bash
# Run all tests
pytest

# Run specific test categories
pytest tests/test_migrations.py  # Migration tests
pytest tests/test_schema_validator.py  # Schema validation tests
```

## Troubleshooting

### Schema Validation Fails on Startup

1. Check the error message for specific issues
2. Run `python scripts/check_migration_health.py` to diagnose
3. Apply missing migrations: `alembic upgrade head`
4. If needed, set `SCHEMA_VALIDATION_MODE=lenient` temporarily

### Migration Issues

See [Migration Best Practices](docs/MIGRATION_BEST_PRACTICES.md#troubleshooting) for common issues and solutions.
