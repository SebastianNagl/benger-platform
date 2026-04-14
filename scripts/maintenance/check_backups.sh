#!/bin/bash

# BenGER Backup Health Check
#
# Usage: ./check_backups.sh [backup-dir]

BACKUP_DIR="${1:-/opt/benger-backups}"

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m'

echo "BenGER Backup Health Check"
echo "=========================="

# Check backup directory
if [ ! -d "$BACKUP_DIR" ]; then
    echo -e "${RED}ERROR: Backup directory not found: $BACKUP_DIR${NC}"
    exit 1
fi

# Find latest daily backup
LATEST_BACKUP=$(find "$BACKUP_DIR/daily" -maxdepth 1 -name "benger_db_backup_*.sql.gz" -type f -print0 2>/dev/null | xargs -0 ls -t 2>/dev/null | head -1)

if [ -z "$LATEST_BACKUP" ]; then
    echo -e "${RED}ERROR: No backups found in $BACKUP_DIR/daily/${NC}"
    exit 1
fi

# Calculate backup age
if [[ "$OSTYPE" == "darwin"* ]]; then
    BACKUP_TIMESTAMP=$(stat -f %m "$LATEST_BACKUP")
else
    BACKUP_TIMESTAMP=$(stat -c %Y "$LATEST_BACKUP")
fi

CURRENT_TIMESTAMP=$(date +%s)
BACKUP_AGE=$((CURRENT_TIMESTAMP - BACKUP_TIMESTAMP))
HOURS_OLD=$((BACKUP_AGE / 3600))
MINUTES_OLD=$(((BACKUP_AGE % 3600) / 60))

BACKUP_SIZE=$(du -h "$LATEST_BACKUP" | cut -f1)

# Staleness check
if [ $BACKUP_AGE -gt 129600 ]; then
    echo -e "${RED}WARNING: Last backup is $HOURS_OLD hours old!${NC}"
    echo "Last backup: $LATEST_BACKUP ($BACKUP_SIZE)"
    EXIT_CODE=1
elif [ $BACKUP_AGE -gt 86400 ]; then
    echo -e "${YELLOW}NOTICE: Last backup is $HOURS_OLD hours old${NC}"
    echo "Last backup: $LATEST_BACKUP ($BACKUP_SIZE)"
    EXIT_CODE=0
else
    echo -e "${GREEN}OK: Backup system is healthy${NC}"
    echo "Last backup: $HOURS_OLD hours $MINUTES_OLD minutes ago"
    echo "Backup file: $LATEST_BACKUP"
    echo "Backup size: $BACKUP_SIZE"
    EXIT_CODE=0
fi

# Count tiered backups
TOTAL_DAILY=$(find "$BACKUP_DIR/daily" -maxdepth 1 -name "benger_db_backup_*.sql.gz" -type f 2>/dev/null | wc -l | tr -d ' ')
TOTAL_WEEKLY=$(find "$BACKUP_DIR/weekly" -maxdepth 1 -name "benger_db_backup_weekly_*.sql.gz" -type f 2>/dev/null | wc -l | tr -d ' ')
TOTAL_MONTHLY=$(find "$BACKUP_DIR/monthly" -maxdepth 1 -name "benger_db_backup_monthly_*.sql.gz" -type f 2>/dev/null | wc -l | tr -d ' ')

echo ""
echo "Backup Summary:"
echo "  Daily backups:   $TOTAL_DAILY"
echo "  Weekly backups:  $TOTAL_WEEKLY"
echo "  Monthly backups: $TOTAL_MONTHLY"

DISK_USAGE=$(du -sh "$BACKUP_DIR" | cut -f1)
echo "  Total disk usage: $DISK_USAGE"

# Integrity check on latest backup
echo ""
echo "Testing backup integrity..."
if gunzip -t "$LATEST_BACKUP" 2>/dev/null; then
    echo -e "${GREEN}Integrity check passed${NC}"
else
    echo -e "${RED}ERROR: Backup file is corrupted!${NC}"
    EXIT_CODE=1
fi

exit $EXIT_CODE
