# Migration Rollback Strategy

## Overview
This document outlines the rollback strategy for the BenGER database migrations after the major task system refactoring. 

## Current State
- **Migration Head**: `final_single_head_20250819_202125`
- **Total Migrations**: 75+ migration files
- **Backup Location**: `/Users/sebastiannagl/Code/BenGer/migration_backup_20250819_195759/`

## Rollback Scenarios

### 1. Pre-Deployment Rollback
If issues are discovered before production deployment:

```bash
# 1. Restore migrations from backup
cp -r migration_backup_20250819_195759/alembic/versions/* services/api/alembic/versions/

# 2. Reset git to previous state
git reset --hard HEAD~1

# 3. Restart services
docker-compose -f infra/docker-compose.yml restart
```

### 2. Post-Deployment Rollback (Critical)
If critical issues occur after production deployment:

```bash
# 1. Stop all services immediately
docker-compose -f infra/docker-compose.yml stop api worker scheduler

# 2. Restore database from backup
docker exec infra-db-1 psql -U postgres -c "DROP DATABASE IF EXISTS benger;"
docker exec infra-db-1 psql -U postgres -c "CREATE DATABASE benger;"
docker exec -i infra-db-1 psql -U postgres -d benger < migration_backup_20250819_195759/database_backup.sql

# 3. Restore migration files
cp -r migration_backup_20250819_195759/alembic/versions/* services/api/alembic/versions/

# 4. Checkout previous code version
git checkout 8d127b18  # Last known good commit

# 5. Rebuild and restart services
docker-compose -f infra/docker-compose.yml build api worker
docker-compose -f infra/docker-compose.yml up -d
```

### 3. Partial Rollback (Non-Critical Issues)
For non-critical issues that don't require full rollback:

```bash
# 1. Create hotfix migrations to address specific issues
cd services/api
alembic revision -m "hotfix_issue_description"

# 2. Edit the migration to fix the issue
# 3. Apply the hotfix
alembic upgrade head

# 4. Restart affected services
docker-compose -f infra/docker-compose.yml restart api
```

## Verification Steps

### Pre-Rollback Checks
1. **Backup Current State**:
   ```bash
   docker exec infra-db-1 pg_dump -U postgres benger > rollback_backup_$(date +%Y%m%d_%H%M%S).sql
   ```

2. **Document Current Migration**:
   ```bash
   docker exec infra-api-1 alembic current > current_migration.txt
   ```

3. **Check Application Status**:
   ```bash
   curl http://localhost:8000/health
   ```

### Post-Rollback Verification
1. **Verify Database State**:
   ```bash
   docker exec infra-api-1 alembic current
   docker exec infra-db-1 psql -U postgres -d benger -c "\dt"
   ```

2. **Test Core Functionality**:
   - Login functionality
   - Project creation/viewing
   - User management
   - API endpoints

3. **Check Logs**:
   ```bash
   docker-compose -f infra/docker-compose.yml logs -f api | grep ERROR
   ```

## Emergency Contacts
- Database Admin: [Contact Info]
- DevOps Lead: [Contact Info]
- On-Call Engineer: [Contact Info]

## Recovery Time Objectives
- **Detection**: < 5 minutes (via monitoring)
- **Decision**: < 15 minutes (assess severity)
- **Rollback Execution**: < 30 minutes
- **Verification**: < 15 minutes
- **Total RTO**: < 1 hour

## Monitoring During Rollback
1. Monitor error rates
2. Check database connections
3. Verify user sessions
4. Monitor system resources

## Post-Rollback Actions
1. Create incident report
2. Document root cause
3. Plan fix for next deployment
4. Update this rollback strategy if needed

## Important Notes
- Always backup before rollback
- Test rollback procedure in staging first if possible
- Keep communication channels open during rollback
- Document all actions taken during rollback