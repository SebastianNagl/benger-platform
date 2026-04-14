#!/bin/bash

# Local Integration Test Runner for BenGER
# 
# This script runs integration tests locally using Docker Compose
# Usage: ./scripts/run-integration-tests.sh [test-category] [options]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
TEST_CATEGORY="all"
CLEANUP=true
VERBOSE=false
REBUILD=false
PARALLEL=false

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to display usage
usage() {
    cat << EOF
Usage: $0 [TEST_CATEGORY] [OPTIONS]

TEST_CATEGORY:
    all                 Run all integration tests (default)
    frontend_api        Frontend-API integration tests
    api_database        API-Database integration tests  
    api_workers         API-Workers integration tests
    websocket           WebSocket real-time tests
    cross_service       Cross-service workflow tests

OPTIONS:
    -h, --help          Show this help message
    -v, --verbose       Enable verbose output
    -r, --rebuild       Rebuild Docker images before testing
    -p, --parallel      Run tests in parallel
    --no-cleanup        Don't cleanup Docker resources after tests
    --quick             Quick test run (skip setup, assume services running)

EXAMPLES:
    $0                              # Run all integration tests
    $0 frontend_api                 # Run only frontend-API tests
    $0 all --rebuild --verbose      # Rebuild and run all tests with verbose output
    $0 websocket --no-cleanup       # Run WebSocket tests and keep containers running

EOF
}

# Function to check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    # Check if Docker is installed and running
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed or not in PATH"
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        print_error "Docker daemon is not running"
        exit 1
    fi
    
    # Check if Docker Compose is available
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose is not installed or not in PATH"
        exit 1
    fi
    
    # Check if we're in the correct directory
    if [ ! -f "infra/docker-compose.test.yml" ]; then
        print_error "Must be run from the project root directory"
        print_error "Could not find infra/docker-compose.test.yml"
        exit 1
    fi
    
    print_success "Prerequisites check passed"
}

# Function to build Docker images
build_images() {
    if [ "$REBUILD" = true ]; then
        print_status "Building Docker images..."
        
        docker-compose -f infra/docker-compose.test.yml build --no-cache
        
        print_success "Docker images built successfully"
    else
        print_status "Using existing Docker images (use --rebuild to rebuild)"
    fi
}

# Function to start test infrastructure
start_infrastructure() {
    print_status "Starting test infrastructure..."
    
    # Create network if it doesn't exist
    docker network create benger-integration-test 2>/dev/null || true
    
    # Start infrastructure services
    docker-compose -f infra/docker-compose.test.yml up -d db redis
    
    # Wait for services to be healthy
    print_status "Waiting for infrastructure services to be ready..."
    timeout=60
    
    while [ $timeout -gt 0 ]; do
        if docker-compose -f infra/docker-compose.test.yml ps | grep -q "healthy"; then
            print_success "Infrastructure services are ready"
            break
        fi
        sleep 2
        timeout=$((timeout - 2))
    done
    
    if [ $timeout -le 0 ]; then
        print_error "Infrastructure services failed to start within timeout"
        print_status "Showing service logs:"
        docker-compose -f infra/docker-compose.test.yml logs db redis
        exit 1
    fi
}

# Function to start application services
start_application() {
    print_status "Starting application services..."
    
    # Start application services
    docker-compose -f infra/docker-compose.test.yml up -d api worker frontend
    
    # Wait for API to be ready
    print_status "Waiting for application services to be ready..."
    timeout=120
    
    while [ $timeout -gt 0 ]; do
        if curl -s http://localhost:8002/health > /dev/null 2>&1; then
            print_success "Application services are ready"
            break
        fi
        sleep 3
        timeout=$((timeout - 3))
    done
    
    if [ $timeout -le 0 ]; then
        print_error "Application services failed to start within timeout"
        print_status "Showing API logs:"
        docker-compose -f infra/docker-compose.test.yml logs api
        exit 1
    fi
}

# Function to run database migrations
run_migrations() {
    print_status "Running database migrations..."
    
    docker-compose -f infra/docker-compose.test.yml exec -T api alembic upgrade head
    
    if [ $? -eq 0 ]; then
        print_success "Database migrations completed"
    else
        print_error "Database migrations failed"
        exit 1
    fi
}

# Function to seed test data
seed_test_data() {
    print_status "Seeding test data..."
    
    docker-compose -f infra/docker-compose.test.yml exec -T api python -c "
from database import get_db
from auth_module import create_user

db = next(get_db())

# Create test users
users = [
    {'username': 'admin', 'email': 'admin@test.com', 'password': 'admin', 'is_superadmin': True},
    {'username': 'contributor', 'email': 'contributor@test.com', 'password': 'admin', 'is_superadmin': False},
    {'username': 'annotator', 'email': 'annotator@test.com', 'password': 'admin', 'is_superadmin': False}
]

for user_data in users:
    try:
        create_user(db, user_data)
        db.commit()
        print(f'Created user: {user_data[\"username\"]}')
    except Exception as e:
        db.rollback()
        print(f'User {user_data[\"username\"]} already exists or error: {e}')

db.close()
print('Test data seeding completed')
"
    
    print_success "Test data seeded"
}

# Function to run integration tests
run_tests() {
    print_status "Running integration tests for category: $TEST_CATEGORY"
    
    # Determine pytest marker
    case $TEST_CATEGORY in
        "frontend_api")
            MARKER="frontend_api"
            ;;
        "api_database")
            MARKER="api_database"
            ;;
        "api_workers")
            MARKER="api_workers"
            ;;
        "websocket")
            MARKER="websocket"
            ;;
        "cross_service")
            MARKER="cross_service"
            ;;
        "all")
            MARKER="integration"
            ;;
        *)
            print_error "Unknown test category: $TEST_CATEGORY"
            exit 1
            ;;
    esac
    
    # Build pytest command
    PYTEST_CMD="pytest /infra/tests/integration -m $MARKER -v --tb=short"
    
    if [ "$VERBOSE" = true ]; then
        PYTEST_CMD="$PYTEST_CMD -s"
    fi
    
    if [ "$PARALLEL" = true ]; then
        PYTEST_CMD="$PYTEST_CMD -n auto"
    fi
    
    # Add coverage reporting
    PYTEST_CMD="$PYTEST_CMD --cov=/services --cov-report=term-missing --cov-report=html:/test_results/htmlcov"
    
    # Add test results output
    PYTEST_CMD="$PYTEST_CMD --junitxml=/test_results/integration-results.xml"
    
    print_status "Running command: $PYTEST_CMD"
    
    # Run the tests
    if docker-compose -f infra/docker-compose.test.yml run --rm integration-tests $PYTEST_CMD; then
        print_success "Integration tests completed successfully"
        
        # Copy test results and coverage reports
        print_status "Copying test results..."
        docker run --rm \
            -v test_results:/source \
            -v $(pwd)/test-results:/dest \
            alpine:latest \
            sh -c "cp -r /source/* /dest/ 2>/dev/null || true"
        
        if [ -d "test-results/htmlcov" ]; then
            print_success "Coverage report available at: test-results/htmlcov/index.html"
        fi
        
        return 0
    else
        print_error "Integration tests failed"
        
        # Show service logs for debugging
        print_status "Showing recent service logs for debugging:"
        echo "=== API Logs ==="
        docker-compose -f infra/docker-compose.test.yml logs --tail=30 api
        echo "=== Worker Logs ==="
        docker-compose -f infra/docker-compose.test.yml logs --tail=20 worker
        
        return 1
    fi
}

# Function to cleanup resources
cleanup() {
    if [ "$CLEANUP" = true ]; then
        print_status "Cleaning up Docker resources..."
        
        docker-compose -f infra/docker-compose.test.yml down -v
        docker volume rm postgres_test_data redis_test_data 2>/dev/null || true
        docker network rm benger-integration-test 2>/dev/null || true
        
        print_success "Cleanup completed"
    else
        print_warning "Skipping cleanup - containers and volumes remain"
        print_status "To cleanup manually, run:"
        print_status "  docker-compose -f infra/docker-compose.test.yml down -v"
    fi
}

# Function for quick test run (assumes services are already running)
quick_test() {
    print_status "Running quick integration tests (assuming services are running)..."
    
    # Just run the tests without setup
    run_tests
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            usage
            exit 0
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -r|--rebuild)
            REBUILD=true
            shift
            ;;
        -p|--parallel)
            PARALLEL=true
            shift
            ;;
        --no-cleanup)
            CLEANUP=false
            shift
            ;;
        --quick)
            QUICK=true
            shift
            ;;
        frontend_api|api_database|api_workers|websocket|cross_service|all)
            TEST_CATEGORY=$1
            shift
            ;;
        *)
            print_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Main execution
main() {
    print_status "Starting BenGER Integration Test Runner"
    print_status "Test Category: $TEST_CATEGORY"
    
    # Trap to ensure cleanup on exit
    trap cleanup EXIT
    
    if [ "$QUICK" = true ]; then
        quick_test
    else
        check_prerequisites
        build_images
        start_infrastructure
        start_application
        run_migrations
        seed_test_data
        run_tests
    fi
    
    if [ $? -eq 0 ]; then
        print_success "Integration test run completed successfully!"
        exit 0
    else
        print_error "Integration test run failed!"
        exit 1
    fi
}

# Run main function
main