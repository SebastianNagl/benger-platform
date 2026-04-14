#!/bin/bash
set -e

# BenGER Database Restore (Kubernetes)
#
# Usage: ./restore.sh <backup-file> [test|production] [namespace]
#
# Modes:
#   test       - Restore to temporary database, validate, clean up (default, safe)
#   production - DESTRUCTIVE restore to main database (requires confirmation)

BACKUP_FILE=$1
RESTORE_MODE=${2:-test}
NAMESPACE=${3:-benger}
BACKUP_DIR="/opt/benger-backups"
DB_USER="postgres"
DB_NAME="benger"

LOG_FILE="${BACKUP_DIR}/restore.log"
mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

get_pg_password() {
    kubectl get secret benger-postgres-credentials -n "${NAMESPACE}" -o jsonpath='{.data.password}' | base64 -d
}

run_psql() {
    kubectl exec -n "${NAMESPACE}" benger-postgresql-0 -- \
        env PGPASSWORD="$(get_pg_password)" psql -U "$DB_USER" "$@"
}

pipe_to_psql() {
    kubectl exec -i -n "${NAMESPACE}" benger-postgresql-0 -- \
        env PGPASSWORD="$(get_pg_password)" psql -U "$DB_USER" "$@"
}

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: $0 <backup-file> [test|production] [namespace]"
    echo ""
    echo "Modes:"
    echo "  test       - Restore to temporary database (default, safe)"
    echo "  production - Restore to main database (DESTRUCTIVE)"
    echo ""
    echo "Examples:"
    echo "  $0 /opt/benger-backups/daily/benger_db_backup_2026-03-20_02-00-00.sql.gz test"
    echo "  $0 /opt/benger-backups/daily/benger_db_backup_2026-03-20_02-00-00.sql.gz production benger"
    exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
    log "ERROR: Backup file not found: $BACKUP_FILE"
    exit 1
fi

# Verify PostgreSQL pod
if ! kubectl wait --for=condition=ready pod/benger-postgresql-0 -n "${NAMESPACE}" --timeout=30s >/dev/null 2>&1; then
    log "ERROR: PostgreSQL pod is not ready in namespace ${NAMESPACE}"
    exit 1
fi

IS_COMPRESSED=false
[[ "$BACKUP_FILE" == *.gz ]] && IS_COMPRESSED=true

log "Starting restore ($RESTORE_MODE mode, namespace: $NAMESPACE)"
log "Backup file: $BACKUP_FILE (compressed: $IS_COMPRESSED)"

# --- Test mode ---
if [ "$RESTORE_MODE" = "test" ]; then
    TEST_DB="benger_restore_test_$(date +%s)"
    log "Creating test database: $TEST_DB"
    run_psql -d postgres -c "CREATE DATABASE $TEST_DB;"

    log "Restoring backup to test database..."
    if [ "$IS_COMPRESSED" = true ]; then
        gunzip -c "$BACKUP_FILE" | pipe_to_psql -d "$TEST_DB"
    else
        pipe_to_psql -d "$TEST_DB" < "$BACKUP_FILE"
    fi

    TABLE_COUNT=$(kubectl exec -n "${NAMESPACE}" benger-postgresql-0 -- \
        env PGPASSWORD="$(get_pg_password)" \
        psql -U "$DB_USER" -d "$TEST_DB" -t -c \
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" | tr -d ' \n')

    log "Test database contains $TABLE_COUNT tables"
    [ "$TABLE_COUNT" -lt 5 ] && log "WARNING: Suspiciously low table count"

    log "Cleaning up test database..."
    run_psql -d postgres -c "DROP DATABASE $TEST_DB;"
    log "Restore test completed -- backup is valid"
    exit 0
fi

# --- Production mode ---
if [ "$RESTORE_MODE" = "production" ]; then
    echo ""
    echo "WARNING: This will DESTROY the current $DB_NAME database in namespace $NAMESPACE!"
    echo "All current data will be lost and replaced with the backup."
    echo ""
    read -p "Type 'yes' to confirm: " CONFIRM
    [ "$CONFIRM" != "yes" ] && { log "Cancelled by user"; exit 1; }

    # Safety backup
    SAFETY_FILE="${BACKUP_DIR}/daily/benger_db_safety_$(date +%Y-%m-%d_%H-%M-%S).sql.gz"
    log "Creating safety backup: $SAFETY_FILE"
    kubectl exec -n "${NAMESPACE}" benger-postgresql-0 -- \
        env PGPASSWORD="$(get_pg_password)" \
        pg_dump -U "$DB_USER" --no-owner --no-acl "$DB_NAME" | gzip > "$SAFETY_FILE"

    # Scale down dependent services
    log "Scaling down API and workers..."
    kubectl scale deployment benger-api -n "${NAMESPACE}" --replicas=0
    kubectl scale deployment benger-workers -n "${NAMESPACE}" --replicas=0
    sleep 5

    log "Dropping and recreating database..."
    run_psql -d postgres -c "DROP DATABASE IF EXISTS $DB_NAME;"
    run_psql -d postgres -c "CREATE DATABASE $DB_NAME;"

    log "Restoring backup..."
    if [ "$IS_COMPRESSED" = true ]; then
        gunzip -c "$BACKUP_FILE" | pipe_to_psql -d "$DB_NAME"
    else
        pipe_to_psql -d "$DB_NAME" < "$BACKUP_FILE"
    fi

    # Scale back up
    log "Scaling services back up..."
    kubectl scale deployment benger-api -n "${NAMESPACE}" --replicas=3
    kubectl scale deployment benger-workers -n "${NAMESPACE}" --replicas=1

    log "Production restore completed"
    log "Safety backup at: $SAFETY_FILE"
    log "NOTE: Run 'helm upgrade' to re-sync replica counts if needed"
    exit 0
fi

log "ERROR: Invalid mode: $RESTORE_MODE (expected: test or production)"
exit 1
