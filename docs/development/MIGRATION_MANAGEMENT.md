# Database Migration Management Guide

## Overview

BenGER uses Alembic for database migrations. This guide covers best practices, common issues, and maintenance procedures to ensure a healthy migration chain. With 80+ migration files, proper management is critical for CI/CD performance and deployment reliability.

## Table of Contents

1. [Quick Reference](#quick-reference)
2. [Understanding Alembic Migrations](#understanding-alembic-migrations)
3. [Migration Health](#migration-health)
4. [Common Issues and Solutions](#common-issues-and-solutions)
5. [Best Practices](#best-practices)
6. [Maintenance Procedures](#maintenance-procedures)
7. [CI/CD Integration](#cicd-integration)
8. [Emergency Procedures](#emergency-procedures)

## Quick Reference

### Essential Commands

```bash
# Check current migration status
cd services/api
alembic current

# View migration heads (should only be ONE)
alembic heads

# Apply migrations
alembic upgrade head

# Create new migration
alembic revision -m "description_of_changes"

# Create auto-generated migration
alembic revision --autogenerate -m "description_of_changes"

# Merge multiple heads
alembic merge -m "merge_description" <rev1> <rev2>

# Show migration history
alembic history
```

### Health Check Scripts

```bash
# Check migration chain health
./scripts/check_migrations_health.sh

# Fix migration chain issues
python scripts/fix_migration_chain.py

# Consolidate old migrations (quarterly maintenance)
python scripts/consolidate_old_migrations.py

# Install pre-push hooks
./scripts/install-hooks.sh
```

## Understanding Alembic Migrations

Alembic is our database schema version control system. Think of it like Git for your database structure.

### Key Concepts

1. **Migration Files**: Python files that describe database changes
2. **Revision Chain**: Migrations link together like Git commits
3. **alembic_version Table**: Tracks which migration is currently applied
4. **Head**: The latest migration(s) in the chain

## Migration Health

### Indicators of a Healthy Migration Chain

✅ **Single Head**: Only one migration head exists
```bash
$ alembic heads
merge_all_branches_final (head)  # Good - single head
```

✅ **Fast Resolution**: Migrations resolve within 120 seconds
✅ **Linear History**: No parallel branches in recent migrations
✅ **Clean Dependencies**: Each migration has clear down_revision

### Warning Signs

⚠️ **Multiple Heads**: Indicates parallel branches
```bash
$ alembic heads
branch_a (head)
branch_b (head)  # Bad - multiple heads
```

⚠️ **Slow Resolution**: Migration resolution >60 seconds (critical >120s)
⚠️ **Complex Dependencies**: Multiple parent revisions
⚠️ **Missing Files**: Gaps in migration chain

## Common Issues and Solutions

### Problem 1: Missing Migration Files on Server

**Symptom**: "KeyError: '017_comprehensive_legacy_cleanup'" errors

**Cause**: Migration files exist locally but weren't deployed to production

**Solution**:
```bash
# Ensure all migration files are committed
git add services/api/alembic/versions/*.py
git commit -m "Add missing migration files"
git push

# Deploy to production (CI/CD deploys automatically on merge to master)
git push origin master
```

### Problem 2: Multiple Migration Heads

**Symptom**: Multiple parallel migration branches

**Cause**: Developers creating migrations independently without merging

**Solution**:
```bash
# Run the fix script to create a merge migration
python scripts/fix_migration_chain.py

# Review and commit the merge migration
git add services/api/alembic/versions/*merge*.py
git commit -m "Merge migration heads"
```

### Problem 3: Missing Parent References

**Symptom**: Migration references non-existent parent

**Cause**: Inconsistent revision IDs or deleted migrations

**Solution**:
1. Fix the down_revision in the migration file
2. Or create the missing migration

## Best Practices

### 1. Migration Naming Convention

Use descriptive names with action verbs:
```bash
# Good examples
alembic revision -m "add_user_authentication_fields"
alembic revision -m "remove_deprecated_webhooks_table"
alembic revision -m "rename_column_task_status_to_state"

# Bad examples
alembic revision -m "fixes"
alembic revision -m "update"
```

### 2. Always Check Before Creating

```bash
# Before creating a new migration
git pull origin master
cd services/api
alembic heads  # Ensure single head
alembic current  # Check current state
```

### 3. Test Migrations Thoroughly

```bash
# Test on clean database
dropdb test_benger
createdb test_benger
alembic upgrade head

# Test from current production state
pg_dump production_db > backup.sql
createdb test_prod_state
psql test_prod_state < backup.sql
alembic upgrade head
```

### 4. Use Atomic Migrations

Each migration should be:
- **Atomic**: Complete single change
- **Reversible**: Include proper downgrade()
- **Tested**: Both upgrade and downgrade paths

### 5. Before Deploying

```bash
# Check migration status locally
cd services/api
alembic current
alembic history

# Ensure single head
alembic heads  # Should show only one

# Test migration locally
alembic upgrade head
alembic downgrade -1  # Test rollback
alembic upgrade head
```

### 4. Handling Conflicts

When multiple developers create migrations:

```bash
# Developer A creates migration
alembic revision -m "add_field_a"

# Developer B creates migration (same parent)
alembic revision -m "add_field_b"

# Result: Two heads! Fix with merge:
alembic merge -m "merge_field_migrations"
```

### 5. Production Deployment Checklist

- [ ] All migration files committed to Git
- [ ] Single migration head (no branches)
- [ ] Migration tested locally
- [ ] Backup production database
- [ ] Deploy code WITH migration files
- [ ] Run migrations on production

## Emergency Recovery

### If Production Migrations Fail

```bash
# SSH to production
ssh user@production-server

# Check current state
kubectl exec -n benger <api-pod> -- alembic current

# If needed, manually create tables
kubectl exec -n benger <api-pod> -- python
>>> from database import SessionLocal
>>> db = SessionLocal()
>>> db.execute(text("CREATE TABLE IF NOT EXISTS ..."))
>>> db.commit()

# Mark migration as complete
kubectl exec -n benger <api-pod> -- alembic stamp <revision>
```

### Reset Migration State (DANGEROUS)

Only in extreme cases:
```sql
-- Clear migration history
DELETE FROM alembic_version;

-- Set to specific revision
INSERT INTO alembic_version (version_num) VALUES ('revision_id');
```

## Monitoring Migration Health

Use the provided script:
```bash
# Check migration chain health
python scripts/fix_migration_chain.py

# This will:
# - Detect missing parents
# - Find multiple heads
# - Identify orphaned migrations
# - Optionally create merge migrations
```

## Migration File Structure

```python
"""Description of changes

Revision ID: unique_identifier
Revises: parent_migration_id  # Or tuple for merges
Create Date: timestamp
"""

from alembic import op
import sqlalchemy as sa

# Revision identifiers
revision = 'unique_identifier'
down_revision = 'parent_migration_id'  # Link to parent
branch_labels = None
depends_on = None

def upgrade():
    """Apply changes to database"""
    op.create_table(...)
    op.add_column(...)
    
def downgrade():
    """Revert changes"""
    op.drop_column(...)
    op.drop_table(...)
```

## Common Commands

```bash
# Check current migration
alembic current

# Show migration history
alembic history

# Show all heads
alembic heads

# Upgrade to latest
alembic upgrade head

# Upgrade to specific revision
alembic upgrade <revision>

# Downgrade one step
alembic downgrade -1

# Create new migration
alembic revision -m "description"

# Auto-generate migration from model changes
alembic revision --autogenerate -m "description"

# Merge multiple heads
alembic merge -m "merge description"

# Mark database as at specific revision (without running migrations)
alembic stamp <revision>
```

## Preventing Future Issues

1. **Always sync before creating migrations**
2. **Run migration health check before deploying**
3. **Use consistent naming conventions**
4. **Document complex migrations**
5. **Test migrations locally first**
6. **Keep migration files in version control**
7. **Never delete migration files from production**

## Team Workflow

1. Before creating a migration:
   ```bash
   git pull origin main
   alembic heads  # Ensure single head
   ```

2. Create your migration:
   ```bash
   alembic revision -m "your_change"
   # Edit the file
   alembic upgrade head  # Test it
   ```

3. If multiple heads detected:
   ```bash
   python scripts/fix_migration_chain.py
   git add services/api/alembic/versions/
   git commit -m "Merge migration heads"
   ```

4. Push and deploy:
   ```bash
   git push origin your-branch
   # CI/CD deploys to staging automatically on PR, production on merge to master
   ```

## Maintenance Procedures

### Regular Health Checks (Weekly)

```bash
# 1. Check migration health
./scripts/check_migrations_health.sh

# 2. Check for multiple heads
cd services/api && alembic heads

# 3. Test resolution speed
time alembic current
```

### Migration Consolidation (Quarterly)

For projects with >50 migrations:

```bash
# 1. Identify old migrations
python scripts/consolidate_old_migrations.py

# 2. Create baseline migration
# Follow script prompts

# 3. Test thoroughly before deployment
```

### Pre-deployment Checklist

- [ ] Single migration head exists
- [ ] All migrations resolve within timeout
- [ ] No missing migration files
- [ ] Migration tests pass
- [ ] Database backup created

## CI/CD Integration

### GitHub Actions Configuration

The CI pipeline includes enhanced migration validation:

```yaml
- name: Enhanced schema validation and migration tests
  timeout-minutes: 8
  run: |
    timeout 300 alembic upgrade head || {
      echo "Migration failed"
      alembic heads
      exit 1
    }
```

### Pre-push Hooks

Install hooks to prevent migration issues:

```bash
# Install hooks
./scripts/install-hooks.sh

# Hooks will:
# - Check for multiple heads
# - Validate migration chain
# - Test resolution speed
# - Prevent conflicting migrations

# To bypass hooks temporarily (not recommended):
git push --no-verify
```

## Troubleshooting

### Debug Mode

```bash
# Enable verbose logging
export ALEMBIC_CONFIG=alembic.ini
alembic --config $ALEMBIC_CONFIG upgrade head --sql
```

### Common Error Messages

| Error | Cause | Solution |
|-------|-------|----------|
| "Multiple head revisions" | Parallel branches | Create merge migration |
| "Can't locate revision" | Missing file | Restore from Git |
| "Timeout expired" | Complex chain | Run consolidation script |
| "Target database is not up to date" | Unapplied migrations | Run `alembic upgrade head` |
| "KeyError: revision_id" | Broken chain | Run fix_migration_chain.py |

## Additional Resources

- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [BenGER Development Guide](./DEVELOPMENT_GUIDE.md)
- [CI/CD Pipeline Documentation](./DEPLOYMENT_GUIDE.md)

## Support

For migration issues:
1. Check this guide first
2. Run health check scripts
3. Review recent commits to alembic/versions/
4. Contact the development team if issues persist

---

*Last updated: August 2025*