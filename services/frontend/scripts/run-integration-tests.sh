#!/bin/bash
# Integration Test Runner Script
# Issue #366: Run comprehensive integration tests across services

set -e

echo "🧪 Starting Integration Test Suite"
echo "=================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
TEST_ENV_FILE="infra/docker-compose.test.yml"
API_SERVICE="api-test"
TEST_DB_SERVICE="db-test"
REDIS_SERVICE="redis-test"

# Function to check if service is healthy
check_service_health() {
    local service=$1
    local max_attempts=30
    local attempt=1

    echo "⏳ Waiting for $service to be healthy..."
    
    while [ $attempt -le $max_attempts ]; do
        if docker-compose -f $TEST_ENV_FILE ps $service | grep -q "healthy"; then
            echo "✅ $service is healthy"
            return 0
        fi
        
        echo "   Attempt $attempt/$max_attempts - waiting..."
        sleep 2
        ((attempt++))
    done
    
    echo "❌ $service failed to become healthy"
    return 1
}

# Function to run test category
run_test_category() {
    local category=$1
    local test_pattern=$2
    
    echo ""
    echo "🔬 Running $category Tests"
    echo "------------------------"
    
    docker-compose -f $TEST_ENV_FILE exec -T $API_SERVICE \
        pytest services/api/tests/integration/$test_pattern \
        -v \
        --tb=short \
        --maxfail=5 \
        -x
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ $category tests passed${NC}"
    else
        echo -e "${RED}❌ $category tests failed${NC}"
        return 1
    fi
}

# Main execution
main() {
    echo "🚀 Setting up test environment..."
    
    # Start test services
    echo "🐳 Starting test containers..."
    docker-compose -f $TEST_ENV_FILE up -d --build
    
    # Wait for services to be healthy
    check_service_health $TEST_DB_SERVICE || exit 1
    check_service_health $REDIS_SERVICE || exit 1
    check_service_health $API_SERVICE || exit 1
    
    echo ""
    echo "🧪 Running Integration Test Categories"
    echo "====================================="
    
    # Track test results
    FAILED_TESTS=()
    
    # Authentication Integration Tests
    if ! run_test_category "Authentication" "test_auth_integration.py"; then
        FAILED_TESTS+=("Authentication")
    fi
    
    # Database Integration Tests
    if ! run_test_category "Database" "test_database_integration.py"; then
        FAILED_TESTS+=("Database")
    fi
    
    # Worker Integration Tests
    if ! run_test_category "Worker" "test_worker_integration.py"; then
        FAILED_TESTS+=("Worker")
    fi
    
    # WebSocket Integration Tests
    if ! run_test_category "WebSocket" "test_websocket_integration.py"; then
        FAILED_TESTS+=("WebSocket")
    fi
    
    # Generate Test Report
    echo ""
    echo "📊 Integration Test Report"
    echo "========================="
    
    if [ ${#FAILED_TESTS[@]} -eq 0 ]; then
        echo -e "${GREEN}🎉 All integration tests passed!${NC}"
        echo ""
        echo "✅ Authentication Integration: PASSED"
        echo "✅ Database Integration: PASSED"
        echo "✅ Worker Integration: PASSED"
        echo "✅ WebSocket Integration: PASSED"
        
        # Run comprehensive test
        echo ""
        echo "🚀 Running comprehensive integration test..."
        docker-compose -f $TEST_ENV_FILE exec -T $API_SERVICE \
            pytest services/api/tests/integration/ \
            -v \
            --tb=short \
            --cov=app \
            --cov-report=term-missing \
            --cov-report=html:coverage/integration \
            -m "integration"
        
        echo ""
        echo -e "${GREEN}🏆 Integration test suite completed successfully!${NC}"
        
    else
        echo -e "${RED}❌ Some integration tests failed:${NC}"
        for test in "${FAILED_TESTS[@]}"; do
            echo -e "${RED}   - $test Integration${NC}"
        done
        echo ""
        echo "💡 Check logs above for details on failed tests"
        exit 1
    fi
}

# Cleanup function
cleanup() {
    echo ""
    echo "🧹 Cleaning up test environment..."
    docker-compose -f $TEST_ENV_FILE down -v
    echo "✅ Cleanup completed"
}

# Trap cleanup on exit
trap cleanup EXIT

# Help message
if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    echo "Integration Test Runner"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -h, --help     Show this help message"
    echo "  --auth         Run only authentication tests"
    echo "  --db           Run only database tests"
    echo "  --worker       Run only worker tests"
    echo "  --websocket    Run only WebSocket tests"
    echo ""
    echo "Examples:"
    echo "  $0                Run all integration tests"
    echo "  $0 --auth         Run only authentication tests"
    echo "  $0 --db          Run only database tests"
    exit 0
fi

# Handle specific test categories
case "$1" in
    --auth)
        docker-compose -f $TEST_ENV_FILE up -d --build
        check_service_health $TEST_DB_SERVICE && check_service_health $API_SERVICE
        run_test_category "Authentication" "test_auth_integration.py"
        ;;
    --db)
        docker-compose -f $TEST_ENV_FILE up -d --build
        check_service_health $TEST_DB_SERVICE && check_service_health $API_SERVICE
        run_test_category "Database" "test_database_integration.py"
        ;;
    --worker)
        docker-compose -f $TEST_ENV_FILE up -d --build
        check_service_health $TEST_DB_SERVICE && check_service_health $REDIS_SERVICE && check_service_health $API_SERVICE
        run_test_category "Worker" "test_worker_integration.py"
        ;;
    --websocket)
        docker-compose -f $TEST_ENV_FILE up -d --build
        check_service_health $API_SERVICE
        run_test_category "WebSocket" "test_websocket_integration.py"
        ;;
    "")
        main
        ;;
    *)
        echo "Unknown option: $1"
        echo "Use -h or --help for usage information"
        exit 1
        ;;
esac
