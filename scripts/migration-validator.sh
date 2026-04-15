#!/bin/bash

# BenGER Migration Validator Script
# Usage: ./migration-validator.sh

set -e

echo "🔍 BenGER Migration Validator"
echo "================================"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Function to check Python and dependencies
check_dependencies() {
    echo "📦 Checking dependencies..."
    
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}❌ Python3 is not installed${NC}"
        exit 1
    fi
    
    if ! python3 -c "import alembic" 2>/dev/null; then
        echo -e "${YELLOW}⚠️ Alembic not found, trying to install...${NC}"
        pip install alembic sqlalchemy psycopg2-binary
    fi
    
    echo -e "${GREEN}✅ Dependencies OK${NC}"
}

# Function to validate migration files
validate_migration_files() {
    echo "📂 Validating migration files..."
    
    cd services/api
    
    # Check if alembic directory exists
    if [ ! -d "alembic/versions" ]; then
        echo -e "${RED}❌ Alembic versions directory not found${NC}"
        exit 1
    fi
    
    # Check for Python syntax errors in migration files
    local errors=0
    for file in alembic/versions/*.py; do
        if [ -f "$file" ]; then
            if ! python3 -m py_compile "$file" 2>/dev/null; then
                echo -e "${RED}❌ Syntax error in: $(basename $file)${NC}"
                ((errors++))
            fi
        fi
    done
    
    if [ "$errors" -eq 0 ]; then
        echo -e "${GREEN}✅ All migration files have valid syntax${NC}"
    else
        echo -e "${RED}❌ Found $errors migration files with syntax errors${NC}"
        return 1
    fi
}

# Function to check for migration heads
check_migration_heads() {
    echo "📊 Checking migration heads..."
    
    cd services/api
    
    # Set database URL for testing
    export DATABASE_URI=${DATABASE_URI:-"postgresql://postgres:changeme123!@localhost:5432/benger"}
    
    # Try to get heads (may fail if DB not accessible)
    if alembic heads 2>/dev/null | grep -q "head"; then
        local head_count=$(alembic heads 2>/dev/null | grep -c "head" || echo "0")
        
        if [ "$head_count" -eq 1 ]; then
            echo -e "${GREEN}✅ Single migration head found${NC}"
            alembic heads
        else
            echo -e "${RED}❌ Multiple migration heads detected ($head_count heads)${NC}"
            echo "Migration heads:"
            alembic heads
            return 1
        fi
    else
        echo -e "${YELLOW}⚠️ Could not check migration heads (database may be unavailable)${NC}"
    fi
}

# Function to validate migration dependencies
check_migration_dependencies() {
    echo "📋 Checking migration dependencies..."
    
    cd services/api
    
    # Check for circular dependencies
    local circular_deps=$(python3 -c "
import os
import re
from collections import defaultdict

def check_circular_deps():
    deps = defaultdict(list)
    versions_dir = 'alembic/versions'
    
    for filename in os.listdir(versions_dir):
        if filename.endswith('.py'):
            filepath = os.path.join(versions_dir, filename)
            with open(filepath, 'r') as f:
                content = f.read()
                
                # Extract revision
                rev_match = re.search(r\"revision\s*=\s*['\\\"]([^'\\\"]+)['\\\"]\", content)
                if not rev_match:
                    continue
                revision = rev_match.group(1)
                
                # Extract down_revision(s)
                down_match = re.search(r\"down_revision\s*=\s*(.+)\", content)
                if down_match:
                    down_str = down_match.group(1).strip()
                    if 'None' not in down_str:
                        # Handle tuples and single values
                        down_revs = re.findall(r\"['\\\"]([^'\\\"]+)['\\\"]\", down_str)
                        deps[revision].extend(down_revs)
    
    # Simple cycle detection
    def has_cycle(node, visited, rec_stack):
        visited.add(node)
        rec_stack.add(node)
        
        for neighbor in deps.get(node, []):
            if neighbor not in visited:
                if has_cycle(neighbor, visited, rec_stack):
                    return True
            elif neighbor in rec_stack:
                return True
        
        rec_stack.remove(node)
        return False
    
    for node in deps:
        if has_cycle(node, set(), set()):
            return True
    return False

print('circular' if check_circular_deps() else 'ok')
" 2>/dev/null || echo "error")
    
    if [ "$circular_deps" = "ok" ]; then
        echo -e "${GREEN}✅ No circular dependencies found${NC}"
    elif [ "$circular_deps" = "circular" ]; then
        echo -e "${RED}❌ Circular dependencies detected in migrations${NC}"
        return 1
    else
        echo -e "${YELLOW}⚠️ Could not check dependencies${NC}"
    fi
}

# Function to test migration in Docker
test_migration_docker() {
    echo "🐳 Testing migrations in Docker..."
    
    # Check if API container is running
    if docker ps --format "{{.Names}}" | grep -q "infra-api-1"; then
        echo "📦 Found running API container"
        
        # Test current migration status
        if docker exec infra-api-1 alembic current 2>/dev/null; then
            echo -e "${GREEN}✅ Migration check successful in Docker${NC}"
            
            # Show current revision
            echo "Current revision:"
            docker exec infra-api-1 alembic current 2>&1 | grep -v "INFO"
        else
            echo -e "${RED}❌ Migration check failed in Docker${NC}"
            return 1
        fi
    else
        echo -e "${YELLOW}⚠️ API container not running, skipping Docker test${NC}"
    fi
}

# Main validation logic
main() {
    local overall_status=true
    
    echo ""
    check_dependencies || overall_status=false
    echo ""
    validate_migration_files || overall_status=false
    echo ""
    check_migration_heads || overall_status=false
    echo ""
    check_migration_dependencies || overall_status=false
    echo ""
    test_migration_docker || overall_status=false
    
    echo ""
    echo "================================"
    if [ "$overall_status" = "true" ]; then
        echo -e "${GREEN}✅ Migration validation passed!${NC}"
        exit 0
    else
        echo -e "${RED}❌ Migration validation failed!${NC}"
        echo ""
        echo "💡 Recommendations:"
        echo "  1. Fix any syntax errors in migration files"
        echo "  2. Resolve multiple heads with: alembic merge -m 'merge heads'"
        echo "  3. Fix circular dependencies by adjusting down_revision values"
        echo "  4. Test migrations locally before pushing"
        exit 1
    fi
}

# Change to project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/.."

# Execute main function
main "$@"