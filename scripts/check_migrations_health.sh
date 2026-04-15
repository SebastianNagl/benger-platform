#!/bin/bash
# Pre-deployment migration health check
# This script ensures migrations are in a healthy state before deployment

set -e

echo "🔍 Checking Alembic Migration Health..."
echo "========================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if we're in the right directory
if [ ! -d "services/api/alembic/versions" ]; then
    echo -e "${RED}❌ Error: Not in project root directory${NC}"
    echo "Please run from the BenGer project root"
    exit 1
fi

cd services/api

# Check if alembic is available
ALEMBIC_AVAILABLE=false
if command -v alembic &> /dev/null; then
    ALEMBIC_AVAILABLE=true
    # Only check heads if we have a database connection configured
    if [ -n "$DATABASE_URL" ] || [ -f "alembic.ini" ]; then
        # Check for single head (with timeout to prevent hanging)
        echo "Checking for migration heads..."
        HEADS=$(timeout 5 alembic heads 2>/dev/null | wc -l)
        if [ "$HEADS" -eq 0 ]; then
            echo -e "${YELLOW}⚠️  No migration heads found (database may not be configured)${NC}"
            echo "Proceeding with file-based checks only"
        elif [ "$HEADS" -eq 1 ]; then
            echo -e "${GREEN}✅ Single migration head found${NC}"
        else
            echo -e "${RED}❌ Multiple heads detected ($HEADS heads)${NC}"
            echo "Run: python scripts/fix_migration_chain.py"
            exit 1
        fi
    else
        echo -e "${YELLOW}⚠️  No database configured - skipping runtime migration checks${NC}"
        echo "Will perform file-based checks only"
    fi
else
    echo -e "${YELLOW}⚠️  Alembic not installed - running in CI mode${NC}"
    echo "Performing file-based migration checks only"
fi

# Check current revision (only if alembic is available AND database is configured)
# Skip in CI environment where database is not available
if command -v alembic &> /dev/null && [ -n "$DATABASE_URL" ]; then
    echo ""
    echo "Current database revision:"
    timeout 5 alembic current 2>/dev/null || echo -e "${YELLOW}⚠️  No revision set or database unavailable${NC}"
fi

# Check for uncommitted and untracked migration files
echo ""
echo "Checking for uncommitted migrations..."
UNCOMMITTED=$(git status --porcelain alembic/versions/*.py 2>/dev/null | wc -l)
UNTRACKED=$(git status --porcelain alembic/versions/*.py 2>/dev/null | grep "^??" | wc -l)

if [ "$UNCOMMITTED" -eq 0 ]; then
    echo -e "${GREEN}✅ All migrations committed${NC}"
else
    echo -e "${RED}❌ Found $UNCOMMITTED uncommitted migration files${NC}"
    if [ "$UNTRACKED" -gt 0 ]; then
        echo -e "${RED}   Including $UNTRACKED UNTRACKED files (not in Git!)${NC}"
        echo "   These files will NOT be deployed!"
    fi
    git status --porcelain alembic/versions/*.py
    echo ""
    echo "   Fix with: git add services/api/alembic/versions/*.py"
fi

# Run Python analysis
echo ""
echo "Running detailed migration analysis..."
cd ../..
python scripts/fix_migration_chain.py 2>/dev/null | grep -E "❌|⚠️|✅" || true

# Check if all files exist
echo ""
echo "Verifying migration file integrity..."
MISSING=0
for file in services/api/alembic/versions/*.py; do
    if [ ! -f "$file" ]; then
        echo -e "${RED}❌ Missing file: $file${NC}"
        MISSING=$((MISSING + 1))
    fi
done

if [ "$MISSING" -eq 0 ]; then
    echo -e "${GREEN}✅ All migration files present${NC}"
fi

# Summary
echo ""
echo "========================================"

# Determine overall health status
HEALTH_PASSED=true

# Check file-based criteria (always checked)
if [ "$UNCOMMITTED" -ne 0 ] || [ "$MISSING" -ne 0 ]; then
    HEALTH_PASSED=false
fi

# Check alembic criteria (only if available)
if [ "$ALEMBIC_AVAILABLE" = true ] && [ -n "$HEADS" ] && [ "$HEADS" -ne 1 ]; then
    HEALTH_PASSED=false
fi

if [ "$HEALTH_PASSED" = true ]; then
    echo -e "${GREEN}✅ Migration health check PASSED${NC}"
    echo "Safe to deploy!"
    exit 0
else
    echo -e "${RED}❌ Migration health check FAILED${NC}"
    echo "Please fix issues before deploying"
    exit 1
fi