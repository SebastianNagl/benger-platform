#!/bin/bash

# Enhanced Test Runner for BenGER API
# Provides comprehensive testing options with coverage and reporting

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
COVERAGE=true
VERBOSE=true
MARKERS=""
PARALLEL=false
REPORT_ONLY=false

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

# Function to show usage
show_usage() {
    echo "Enhanced Test Runner for BenGER API"
    echo ""
    echo "Usage: $0 [OPTIONS] [TEST_PATH]"
    echo ""
    echo "Options:"
    echo "  -h, --help              Show this help message"
    echo "  -c, --no-coverage       Disable coverage reporting"
    echo "  -q, --quiet             Run tests in quiet mode"
    echo "  -m, --markers MARKERS   Run only tests with specific markers (unit,integration,e2e,security)"
    echo "  -p, --parallel          Run tests in parallel (requires pytest-xdist)"
    echo "  -r, --report-only       Only generate coverage report from existing data"
    echo "  -f, --fast              Fast mode: unit tests only, no coverage"
    echo "  --security              Run security tests only"
    echo "  --integration           Run integration tests only"
    echo "  --unit                  Run unit tests only"
    echo ""
    echo "Examples:"
    echo "  $0                                    # Run all tests with coverage"
    echo "  $0 --unit                            # Run only unit tests"
    echo "  $0 --security                        # Run only security tests"
    echo "  $0 -m unit,integration               # Run unit and integration tests"
    echo "  $0 tests/unit/test_core_functionality.py  # Run specific test file"
    echo "  $0 --fast                            # Quick unit tests without coverage"
    echo "  $0 --report-only                     # Generate coverage report only"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_usage
            exit 0
            ;;
        -c|--no-coverage)
            COVERAGE=false
            shift
            ;;
        -q|--quiet)
            VERBOSE=false
            shift
            ;;
        -m|--markers)
            MARKERS="$2"
            shift 2
            ;;
        -p|--parallel)
            PARALLEL=true
            shift
            ;;
        -r|--report-only)
            REPORT_ONLY=true
            shift
            ;;
        -f|--fast)
            COVERAGE=false
            MARKERS="unit"
            shift
            ;;
        --security)
            MARKERS="security"
            shift
            ;;
        --integration)
            MARKERS="integration"
            shift
            ;;
        --unit)
            MARKERS="unit"
            shift
            ;;
        -*)
            print_error "Unknown option $1"
            show_usage
            exit 1
            ;;
        *)
            TEST_PATH="$1"
            shift
            ;;
    esac
done

# Check if we're in the right directory
if [[ ! -f "pytest.ini" ]]; then
    print_error "pytest.ini not found. Please run this script from the API directory."
    exit 1
fi

# Report only mode
if [[ "$REPORT_ONLY" == "true" ]]; then
    print_status "Generating coverage report from existing data..."
    if [[ -f ".coverage" ]]; then
        coverage html
        coverage report
        print_success "Coverage report generated in htmlcov/"
        exit 0
    else
        print_error "No coverage data found. Run tests first."
        exit 1
    fi
fi

# Build pytest command
PYTEST_CMD="python -m pytest"

# Add test path if specified
if [[ -n "$TEST_PATH" ]]; then
    PYTEST_CMD="$PYTEST_CMD $TEST_PATH"
else
    PYTEST_CMD="$PYTEST_CMD tests/"
fi

# Add verbosity
if [[ "$VERBOSE" == "true" ]]; then
    PYTEST_CMD="$PYTEST_CMD -v"
else
    PYTEST_CMD="$PYTEST_CMD -q"
fi

# Add markers
if [[ -n "$MARKERS" ]]; then
    PYTEST_CMD="$PYTEST_CMD -m \"$MARKERS\""
fi

# Add coverage
if [[ "$COVERAGE" == "true" ]]; then
    PYTEST_CMD="$PYTEST_CMD --cov=. --cov-report=term-missing --cov-report=html:htmlcov"
fi

# Add parallel execution
if [[ "$PARALLEL" == "true" ]]; then
    PYTEST_CMD="$PYTEST_CMD -n auto"
fi

# Print configuration
print_status "Test Configuration:"
echo "  Coverage: $COVERAGE"
echo "  Verbose: $VERBOSE"
echo "  Markers: ${MARKERS:-'all'}"
echo "  Parallel: $PARALLEL"
echo "  Test Path: ${TEST_PATH:-'tests/'}"
echo ""

# Run tests
print_status "Running tests..."
echo "Command: $PYTEST_CMD"
echo ""

# Execute the command
if eval $PYTEST_CMD; then
    print_success "Tests completed successfully!"
    
    # Show coverage summary if enabled
    if [[ "$COVERAGE" == "true" ]]; then
        echo ""
        print_status "Coverage report generated in htmlcov/"
        print_status "Open htmlcov/index.html in your browser to view detailed coverage"
    fi
    
    # Show test summary
    echo ""
    print_status "Test Summary:"
    echo "  ✅ All tests passed"
    if [[ -n "$MARKERS" ]]; then
        echo "  🏷️  Markers: $MARKERS"
    fi
    if [[ "$COVERAGE" == "true" ]]; then
        echo "  📊 Coverage report available"
    fi
    
else
    print_error "Tests failed!"
    exit 1
fi 