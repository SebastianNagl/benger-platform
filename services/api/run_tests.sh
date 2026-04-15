#!/bin/bash

# BenGER API Test Runner
# This script runs the complete test suite for the BenGER API

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
COVERAGE_THRESHOLD=80
POSTGRES_URL=${DATABASE_URL:-"postgresql://postgres:changeme@localhost:5432/postgres"}
REDIS_URL=${REDIS_URL:-"redis://localhost:6379/0"}

# Functions
print_header() {
    echo -e "${BLUE}================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}================================${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

check_dependencies() {
    print_header "Checking Dependencies"
    
    # Check if pytest is installed
    if ! command -v pytest &> /dev/null; then
        print_error "pytest not found. Please install test dependencies:"
        echo "pip install -r requirements-test.txt"
        exit 1
    fi
    
    # Check if database is accessible
    if ! python -c "import psycopg2; psycopg2.connect('$POSTGRES_URL')" 2>/dev/null; then
        print_warning "PostgreSQL not accessible. Some tests may fail."
        print_warning "Make sure PostgreSQL is running and DATABASE_URL is correct."
    else
        print_success "PostgreSQL connection verified"
    fi
    
    # Check if Redis is accessible
    if ! python -c "import redis; redis.Redis.from_url('$REDIS_URL').ping()" 2>/dev/null; then
        print_warning "Redis not accessible. Some tests may fail."
        print_warning "Make sure Redis is running and REDIS_URL is correct."
    else
        print_success "Redis connection verified"
    fi
}

setup_test_environment() {
    print_header "Setting Up Test Environment"
    
    # Create test database if it doesn't exist
    export DATABASE_URL="$POSTGRES_URL"
    
    # Run migrations
    if [ -f "migration_utils.py" ]; then
        print_success "Running database migrations..."
        python migration_utils.py init || print_warning "Migration failed, continuing..."
    fi
    
    print_success "Test environment ready"
}

run_unit_tests() {
    print_header "Running Unit Tests"
    
    pytest tests/unit/ \
        -v \
        --cov=. \
        --cov-report=term-missing \
        --cov-report=html:htmlcov \
        --cov-report=xml:coverage.xml \
        --cov-fail-under=$COVERAGE_THRESHOLD \
        -m "not slow" \
        --tb=short
    
    if [ $? -eq 0 ]; then
        print_success "Unit tests passed"
    else
        print_error "Unit tests failed"
        return 1
    fi
}

run_integration_tests() {
    print_header "Running Integration Tests"
    
    pytest tests/integration/ \
        -v \
        --cov=. \
        --cov-append \
        --cov-report=term-missing \
        --cov-report=html:htmlcov \
        --cov-report=xml:coverage.xml \
        -m "not slow" \
        --tb=short
    
    if [ $? -eq 0 ]; then
        print_success "Integration tests passed"
    else
        print_error "Integration tests failed"
        return 1
    fi
}

run_security_tests() {
    print_header "Running Security Tests"
    
    # Run security-specific tests
    pytest tests/unit/test_security.py \
        -v \
        -m "security" \
        --tb=short
    
    if [ $? -eq 0 ]; then
        print_success "Security tests passed"
    else
        print_error "Security tests failed"
        return 1
    fi
    
    # Run bandit security scan
    if command -v bandit &> /dev/null; then
        print_success "Running bandit security scan..."
        bandit -r . -f txt -ll || print_warning "Bandit found potential security issues"
    else
        print_warning "Bandit not installed, skipping security scan"
    fi
    
    # Run safety check for dependencies
    if command -v safety &> /dev/null; then
        print_success "Running safety dependency check..."
        safety check || print_warning "Safety found vulnerable dependencies"
    else
        print_warning "Safety not installed, skipping dependency check"
    fi
}

run_performance_tests() {
    print_header "Running Performance Tests"
    
    pytest tests/e2e/test_performance.py \
        -v \
        -m "not slow" \
        --benchmark-json=benchmark.json \
        --tb=short
    
    if [ $? -eq 0 ]; then
        print_success "Performance tests passed"
    else
        print_error "Performance tests failed"
        return 1
    fi
}

run_e2e_tests() {
    print_header "Running End-to-End Tests"
    
    pytest tests/e2e/ \
        -v \
        -m "e2e and not slow" \
        --tb=short
    
    if [ $? -eq 0 ]; then
        print_success "E2E tests passed"
    else
        print_error "E2E tests failed"
        return 1
    fi
}

run_sanity_tests() {
    print_header "Running Task Sanity Tests"
    
    pytest tests/test_task_sanity.py \
        -v \
        -m "sanity" \
        --tb=short
    
    if [ $? -eq 0 ]; then
        print_success "Sanity tests passed"
    else
        print_error "Sanity tests failed"
        return 1
    fi
}

run_code_quality_checks() {
    print_header "Running Code Quality Checks"
    
    # Black formatting check
    if command -v black &> /dev/null; then
        print_success "Checking code formatting with Black..."
        black --check . || {
            print_error "Code formatting issues found. Run 'black .' to fix."
            return 1
        }
    else
        print_warning "Black not installed, skipping formatting check"
    fi
    
    # isort import sorting check
    if command -v isort &> /dev/null; then
        print_success "Checking import sorting with isort..."
        isort --check-only . || {
            print_error "Import sorting issues found. Run 'isort .' to fix."
            return 1
        }
    else
        print_warning "isort not installed, skipping import check"
    fi
    
    # flake8 linting
    if command -v flake8 &> /dev/null; then
        print_success "Running flake8 linting..."
        flake8 . || {
            print_error "Linting issues found"
            return 1
        }
    else
        print_warning "flake8 not installed, skipping linting"
    fi
    
    # mypy type checking
    if command -v mypy &> /dev/null; then
        print_success "Running mypy type checking..."
        mypy . --ignore-missing-imports || print_warning "Type checking issues found"
    else
        print_warning "mypy not installed, skipping type checking"
    fi
}

generate_test_report() {
    print_header "Generating Test Report"
    
    # Create test report directory
    mkdir -p test-reports
    
    # Copy coverage reports
    if [ -f "coverage.xml" ]; then
        cp coverage.xml test-reports/
        print_success "Coverage report saved to test-reports/coverage.xml"
    fi
    
    if [ -d "htmlcov" ]; then
        cp -r htmlcov test-reports/
        print_success "HTML coverage report saved to test-reports/htmlcov/"
    fi
    
    # Copy benchmark results
    if [ -f "benchmark.json" ]; then
        cp benchmark.json test-reports/
        print_success "Benchmark results saved to test-reports/benchmark.json"
    fi
    
    # Generate summary
    cat > test-reports/summary.txt << EOF
BenGER API Test Summary
======================
Generated: $(date)
Coverage Threshold: ${COVERAGE_THRESHOLD}%

Test Results:
- Unit Tests: $([ -f ".pytest_cache/unit_result" ] && echo "PASSED" || echo "FAILED")
- Integration Tests: $([ -f ".pytest_cache/integration_result" ] && echo "PASSED" || echo "FAILED")
- Security Tests: $([ -f ".pytest_cache/security_result" ] && echo "PASSED" || echo "FAILED")
- Performance Tests: $([ -f ".pytest_cache/performance_result" ] && echo "PASSED" || echo "FAILED")
- E2E Tests: $([ -f ".pytest_cache/e2e_result" ] && echo "PASSED" || echo "FAILED")

Files:
- Coverage Report: coverage.xml
- HTML Coverage: htmlcov/index.html
- Benchmark Results: benchmark.json
EOF
    
    print_success "Test summary saved to test-reports/summary.txt"
}

cleanup() {
    print_header "Cleaning Up"
    
    # Remove temporary files
    rm -f .pytest_cache/*_result 2>/dev/null || true
    
    print_success "Cleanup completed"
}

# Main execution
main() {
    local test_type="${1:-all}"
    local failed_tests=0
    
    print_header "BenGER API Test Suite"
    echo "Test type: $test_type"
    echo "Coverage threshold: ${COVERAGE_THRESHOLD}%"
    echo ""
    
    # Always check dependencies and setup
    check_dependencies
    setup_test_environment
    
    case $test_type in
        "unit")
            run_unit_tests || ((failed_tests++))
            ;;
        "integration")
            run_integration_tests || ((failed_tests++))
            ;;
        "security")
            run_security_tests || ((failed_tests++))
            ;;
        "performance")
            run_performance_tests || ((failed_tests++))
            ;;
        "e2e")
            run_e2e_tests || ((failed_tests++))
            ;;
        "sanity")
            run_sanity_tests || ((failed_tests++))
            ;;
        "quality")
            run_code_quality_checks || ((failed_tests++))
            ;;
        "all")
            run_unit_tests || ((failed_tests++))
            run_integration_tests || ((failed_tests++))
            run_security_tests || ((failed_tests++))
            run_sanity_tests || ((failed_tests++))
            run_code_quality_checks || ((failed_tests++))
            
            # Only run performance and E2E tests if basic tests pass
            if [ $failed_tests -eq 0 ]; then
                run_performance_tests || ((failed_tests++))
                run_e2e_tests || ((failed_tests++))
            else
                print_warning "Skipping performance and E2E tests due to earlier failures"
            fi
            ;;
        *)
            print_error "Unknown test type: $test_type"
            echo "Usage: $0 [unit|integration|security|performance|e2e|sanity|quality|all]"
            exit 1
            ;;
    esac
    
    # Generate report
    generate_test_report
    
    # Final summary
    print_header "Test Results Summary"
    if [ $failed_tests -eq 0 ]; then
        print_success "All tests passed! 🎉"
        cleanup
        exit 0
    else
        print_error "$failed_tests test suite(s) failed"
        cleanup
        exit 1
    fi
}

# Handle script arguments
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    echo "BenGER API Test Runner"
    echo ""
    echo "Usage: $0 [test_type]"
    echo ""
    echo "Test types:"
    echo "  unit         Run unit tests only"
    echo "  integration  Run integration tests only"
    echo "  security     Run security tests only"
    echo "  performance  Run performance tests only"
    echo "  e2e          Run end-to-end tests only"
    echo "  sanity       Run task sanity checks only"
    echo "  quality      Run code quality checks only"
    echo "  all          Run all tests (default)"
    echo ""
    echo "Environment variables:"
    echo "  DATABASE_URL    PostgreSQL connection string"
    echo "  REDIS_URL       Redis connection string"
    echo ""
    exit 0
fi

# Run main function
main "$@" 