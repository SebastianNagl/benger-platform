#!/bin/bash

# Quick Test Script - Fast checks for development
# Use this for rapid feedback during development

set -e

echo "⚡ BenGER Quick Test"
echo "=================="

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_status() { echo -e "🔍 $1"; }
print_success() { echo -e "${GREEN}✅ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
print_error() { echo -e "${RED}❌ $1${NC}"; }

FAILED=0

# 1. Python Syntax Check
print_status "Checking Python syntax..."
for service in api workers; do
    if find services/$service -name "*.py" -not -path "*/tests/*" -exec python -m py_compile {} \; 2>/dev/null; then
        print_success "Python syntax OK for $service"
    else
        print_error "Python syntax errors in $service"
        FAILED=1
    fi
done

# 2. Import Check  
print_status "Checking critical imports..."
cd services/api
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi
# Check if main.py exists
if [ -f "main.py" ]; then
    # Test the import - just check if python can import main without errors
    # Allow warnings but catch actual import errors
    if python -c "import main" 2>&1 | grep -q "Error\|Exception\|ImportError\|ModuleNotFoundError"; then
        print_error "API import issues"
        FAILED=1
    else
        print_success "API imports OK"
    fi
else
    print_error "main.py not found in services/api"
    FAILED=1
fi
if command -v deactivate &> /dev/null; then
    deactivate
fi
cd ../..

cd services/workers
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi  
if python -c "import tasks; print('Workers imports OK')" 2>/dev/null; then
    print_success "Workers imports OK"
else
    print_error "Workers import issues"
    FAILED=1
fi
if command -v deactivate &> /dev/null; then
    deactivate
fi
cd ../..

# 3. Frontend Lint (if available)
if [ -f "services/frontend/package.json" ]; then
    print_status "Checking frontend..."
    cd services/frontend
    if [ -d "node_modules" ] && npm run lint:check &>/dev/null; then
        print_success "Frontend lint OK"
    else
        print_warning "Frontend lint issues (run full test for details)"
    fi
    cd ../..
fi

# 4. Quick API test (no DB needed)
print_status "Quick API test..."
cd services/api
if python -c "
from fastapi.testclient import TestClient
import main
client = TestClient(main.app)
response = client.get('/')
assert response.status_code == 200
print('API basic endpoint OK')
" 2>/dev/null; then
    print_success "API basic test OK"
else
    print_warning "API basic test failed"
fi
cd ../..

echo ""
if [ $FAILED -eq 0 ]; then
    print_success "Quick checks passed! ⚡"
    echo "For full testing run: ./scripts/run-tests-local.sh"
else
    print_error "Quick checks failed - fix issues above"
    exit 1
fi 