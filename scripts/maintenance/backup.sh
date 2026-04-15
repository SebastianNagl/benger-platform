#!/bin/bash
set -e

# BenGER Manual Database Backup (Kubernetes)
# For automated daily backups, see the K8s CronJob in the Helm chart.
#
# Usage: ./backup.sh [namespace] [backup-dir]

NAMESPACE="${1:-benger}"
BACKUP_DIR="${2:-/opt/benger-backups}"
DATE=$(date +%Y-%m-%d_%H-%M-%S)
DAILY_DIR="${BACKUP_DIR}/daily"

mkdir -p "${DAILY_DIR}"

BACKUP_FILE="${DAILY_DIR}/benger_db_backup_${DATE}.sql.gz"

echo "[$(date)] Starting manual PostgreSQL backup..."
echo "[$(date)] Namespace: ${NAMESPACE}"
echo "[$(date)] Target: ${BACKUP_FILE}"

# Verify PostgreSQL pod is ready
if ! kubectl wait --for=condition=ready pod/benger-postgresql-0 -n "${NAMESPACE}" --timeout=30s >/dev/null 2>&1; then
    echo "[$(date)] ERROR: PostgreSQL pod is not ready"
    exit 1
fi

# Run pg_dump via kubectl, compress locally
kubectl exec -n "${NAMESPACE}" benger-postgresql-0 -- \
    env PGPASSWORD="$(kubectl get secret benger-postgres-credentials -n "${NAMESPACE}" -o jsonpath='{.data.password}' | base64 -d)" \
    pg_dump -U postgres --no-owner --no-acl benger | gzip > "${BACKUP_FILE}"

BACKUP_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
echo "[$(date)] Backup created: ${BACKUP_FILE} (${BACKUP_SIZE})"

# Verify gzip integrity
if ! gunzip -t "${BACKUP_FILE}"; then
    echo "[$(date)] ERROR: Backup failed gzip integrity check!"
    rm -f "${BACKUP_FILE}"
    exit 1
fi

# Verify table count
TABLE_COUNT=$(kubectl exec -n "${NAMESPACE}" benger-postgresql-0 -- \
    env PGPASSWORD="$(kubectl get secret benger-postgres-credentials -n "${NAMESPACE}" -o jsonpath='{.data.password}' | base64 -d)" \
    psql -U postgres -d benger -t -c \
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';" | tr -d ' \n')

echo "[$(date)] Live database has ${TABLE_COUNT} tables"

if [ "${TABLE_COUNT}" -lt 5 ]; then
    echo "[$(date)] WARNING: Suspiciously low table count"
fi

echo "[$(date)] Manual backup completed successfully"
