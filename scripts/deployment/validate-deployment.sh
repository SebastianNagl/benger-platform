#!/bin/bash
set -e

# Enhanced Deployment Validation Script for BenGER
# This script performs comprehensive validation of deployments

NAMESPACE="${1:-benger}"
VALIDATION_TYPE="${2:-full}"  # full, quick, api, database
TIMEOUT="${3:-600}"           # 10 minute timeout
VERBOSE="${4:-false}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

# Validation results
VALIDATION_STATUS=0
FAILED_VALIDATIONS=()
WARNING_VALIDATIONS=()
PASSED_VALIDATIONS=()

log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
    PASSED_VALIDATIONS+=("$1")
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
    WARNING_VALIDATIONS+=("$1")
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
    FAILED_VALIDATIONS+=("$1")
    VALIDATION_STATUS=1
}

log_test() {
    echo -e "${PURPLE}🧪 $1${NC}"
}

print_header() {
    echo ""
    echo "========================================"
    echo "🧪 BenGER Deployment Validation"
    echo "========================================"
    echo "Namespace: $NAMESPACE"
    echo "Validation Type: $VALIDATION_TYPE"
    echo "Timeout: ${TIMEOUT}s"
    echo "Verbose: $VERBOSE"
    echo "Started: $(date)"
    echo ""
}

# Validate API functionality
validate_api() {
    log_test "API Functionality Validation"
    
    # Test health endpoint
    log_info "Testing API health endpoint..."
    if kubectl exec -n "$NAMESPACE" deployment/benger-api -- timeout 30s curl -s http://localhost:8000/healthz | grep -q "healthy" 2>/dev/null; then
        log_success "API health endpoint responding"
    else
        log_error "API health endpoint not responding"
        return 1
    fi
    
    # Test docs endpoint
    log_info "Testing API documentation endpoint..."
    if kubectl exec -n "$NAMESPACE" deployment/benger-api -- timeout 30s curl -f -s http://localhost:8000/docs >/dev/null 2>&1; then
        log_success "API docs endpoint accessible"
    else
        log_warning "API docs endpoint not accessible"
    fi
    
    # Test database connection from API
    log_info "Testing database connectivity from API..."
    if kubectl exec -n "$NAMESPACE" deployment/benger-api -- timeout 30s python -c "
import os
from sqlalchemy import create_engine, text
try:
    engine = create_engine(os.getenv('DATABASE_URI'))
    with engine.connect() as conn:
        result = conn.execute(text('SELECT 1'))
        assert result.fetchone()[0] == 1
    print('Database connection successful')
    exit(0)
except Exception as e:
    print(f'Database connection failed: {e}')
    exit(1)
" >/dev/null 2>&1; then
        log_success "API database connectivity verified"
    else
        log_error "API database connectivity failed"
        return 1
    fi
    
    # Test Label Studio connectivity from API
    log_info "Testing Label Studio connectivity from API..."
    if kubectl exec -n "$NAMESPACE" deployment/benger-api -- timeout 30s curl -s -o /dev/null -w "%{http_code}" http://benger-label-studio:8080/health | grep -q "200" 2>/dev/null; then
        log_success "API to Label Studio connectivity verified"
    else
        log_warning "API to Label Studio connectivity failed"
    fi
    
    return 0
}

# Validate database functionality
validate_database() {
    log_test "Database Validation"
    
    # Test PostgreSQL connectivity
    log_info "Testing PostgreSQL connectivity..."
    if kubectl exec -n "$NAMESPACE" benger-postgresql-0 -- timeout 30s pg_isready -h localhost -p 5432 -U postgres >/dev/null 2>&1; then
        log_success "PostgreSQL is ready"
    else
        log_error "PostgreSQL is not ready"
        return 1
    fi
    
    # Test database schema
    log_info "Validating database schema..."
    if kubectl exec -n "$NAMESPACE" deployment/benger-api -- timeout 30s python schema_validator.py >/dev/null 2>&1; then
        log_success "Database schema validation passed"
    else
        log_warning "Database schema validation failed (may be expected during development)"
    fi
    
    return 0
}

# Validate external endpoints
validate_external_endpoints() {
    log_test "External Endpoint Validation"
    
    local endpoints=(
        "https://what-a-benger.net"
        "https://api.what-a-benger.net/healthz"
        "https://api.what-a-benger.net/docs"
        "https://label.what-a-benger.net/health"
    )
    
    for endpoint in "${endpoints[@]}"; do
        log_info "Testing external endpoint: $endpoint"
        
        local response_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 "$endpoint" 2>/dev/null || echo "000")
        
        if [ "$response_code" = "200" ]; then
            log_success "External endpoint healthy: $endpoint"
        else
            log_warning "External endpoint issues: $endpoint (HTTP $response_code)"
        fi
    done
}

# Generate validation report
generate_validation_report() {
    echo ""
    echo "========================================"
    echo "📊 Validation Report"
    echo "========================================"
    echo "Completed: $(date)"
    echo "Namespace: $NAMESPACE"
    echo "Validation Type: $VALIDATION_TYPE"
    echo ""
    
    # Summary
    local total_tests=$((${#PASSED_VALIDATIONS[@]} + ${#WARNING_VALIDATIONS[@]} + ${#FAILED_VALIDATIONS[@]}))
    echo "📈 Summary:"
    echo "  Total Tests: $total_tests"
    echo "  Passed: ${#PASSED_VALIDATIONS[@]}"
    echo "  Warnings: ${#WARNING_VALIDATIONS[@]}"
    echo "  Failed: ${#FAILED_VALIDATIONS[@]}"
    echo ""
    
    # Overall result
    if [ $VALIDATION_STATUS -eq 0 ]; then
        if [ ${#WARNING_VALIDATIONS[@]} -eq 0 ]; then
            log_success "🎉 ALL VALIDATIONS PASSED - Deployment is fully validated!"
        else
            log_warning "⚠️  VALIDATIONS PASSED WITH WARNINGS - Deployment is functional with minor issues"
        fi
    else
        log_error "❌ VALIDATION FAILED - Deployment has critical issues"
    fi
}

# Show usage information
show_usage() {
    echo "Usage: $0 [NAMESPACE] [VALIDATION_TYPE] [TIMEOUT] [VERBOSE]"
    echo ""
    echo "Parameters:"
    echo "  NAMESPACE        Kubernetes namespace (default: benger)"
    echo "  VALIDATION_TYPE  Type of validation (default: full)"
    echo "                   Options: full, quick, api, database"
    echo "  TIMEOUT          Timeout in seconds (default: 600)"
    echo "  VERBOSE          Enable verbose output (true/false, default: false)"
    echo ""
    echo "Examples:"
    echo "  $0                              # Full validation"
    echo "  $0 benger quick                 # Quick validation"
    echo "  $0 benger api 300 true          # API validation with verbose output"
}

# Main execution
main() {
    # Handle help request
    if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
        show_usage
        exit 0
    fi
    
    print_header
    
    # Run validations based on type
    case "$VALIDATION_TYPE" in
        "full")
            validate_api
            validate_database
            validate_external_endpoints
            ;;
        "quick")
            validate_api
            validate_database
            ;;
        "api")
            validate_api
            validate_external_endpoints
            ;;
        "database")
            validate_database
            ;;
        *)
            log_error "Invalid validation type: $VALIDATION_TYPE"
            show_usage
            exit 1
            ;;
    esac
    
    generate_validation_report
    exit $VALIDATION_STATUS
}

# Execute main function with all arguments
main "$@"