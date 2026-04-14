#!/bin/bash
set -e

# Comprehensive Health Check Script for BenGER Deployment
# This script validates the health of all system components before and after deployments

NAMESPACE="${1:-benger}"
CHECK_TYPE="${2:-full}"  # full, quick, or specific component
TIMEOUT="${3:-300}"      # Default 5 minute timeout
VERBOSE="${4:-false}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Health check results
HEALTH_STATUS=0
FAILED_CHECKS=()
WARNING_CHECKS=()

log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
    WARNING_CHECKS+=("$1")
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
    FAILED_CHECKS+=("$1")
    HEALTH_STATUS=1
}

log_verbose() {
    if [ "$VERBOSE" = "true" ]; then
        echo -e "🔍 $1"
    fi
}

# Print header
print_header() {
    echo ""
    echo "=================================="
    echo "🏥 BenGER Health Check"
    echo "=================================="
    echo "Namespace: $NAMESPACE"
    echo "Check Type: $CHECK_TYPE"
    echo "Timeout: ${TIMEOUT}s"
    echo "Started: $(date)"
    echo ""
}

# Check if namespace exists
check_namespace() {
    log_info "Checking namespace '$NAMESPACE'..."
    if kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then
        log_success "Namespace '$NAMESPACE' exists"
    else
        log_error "Namespace '$NAMESPACE' does not exist"
        return 1
    fi
}

# Check pod health for a specific deployment
check_pod_health() {
    local deployment=$1
    local expected_replicas=${2:-1}
    
    log_info "Checking $deployment pod health..."
    
    # Check if deployment exists
    if ! kubectl get deployment "$deployment" -n "$NAMESPACE" >/dev/null 2>&1; then
        log_error "Deployment '$deployment' not found"
        return 1
    fi
    
    # Get current replica status
    local ready_replicas=$(kubectl get deployment "$deployment" -n "$NAMESPACE" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
    local desired_replicas=$(kubectl get deployment "$deployment" -n "$NAMESPACE" -o jsonpath='{.spec.replicas}')
    
    log_verbose "$deployment: $ready_replicas/$desired_replicas replicas ready"
    
    if [ "$ready_replicas" = "$desired_replicas" ] && [ "$ready_replicas" -ge "$expected_replicas" ]; then
        log_success "$deployment: All $ready_replicas replicas healthy"
    else
        # Check for specific pod issues
        local pods=$(kubectl get pods -n "$NAMESPACE" -l app="$deployment" -o jsonpath='{.items[*].metadata.name}')
        for pod in $pods; do
            local status=$(kubectl get pod "$pod" -n "$NAMESPACE" -o jsonpath='{.status.phase}')
            if [ "$status" != "Running" ]; then
                local reason=$(kubectl get pod "$pod" -n "$NAMESPACE" -o jsonpath='{.status.conditions[?(@.type=="Ready")].reason}' 2>/dev/null || echo "Unknown")
                log_error "$deployment pod '$pod' not healthy: $status ($reason)"
                
                # Get recent logs for debugging
                log_verbose "Recent logs for $pod:"
                timeout 10 kubectl logs "$pod" -n "$NAMESPACE" --tail=5 2>/dev/null | sed 's/^/  /' || log_verbose "Could not get logs"
            fi
        done
        
        if [ "$ready_replicas" -lt "$expected_replicas" ]; then
            log_error "$deployment: Only $ready_replicas/$expected_replicas minimum replicas ready"
        else
            log_warning "$deployment: $ready_replicas/$desired_replicas replicas ready (desired: $desired_replicas)"
        fi
        return 1
    fi
}

# Check service connectivity
check_service_connectivity() {
    local service=$1
    local port=${2:-80}
    
    log_info "Checking $service service connectivity..."
    
    if ! kubectl get service "$service" -n "$NAMESPACE" >/dev/null 2>&1; then
        log_error "Service '$service' not found"
        return 1
    fi
    
    # Test service endpoint
    local cluster_ip=$(kubectl get service "$service" -n "$NAMESPACE" -o jsonpath='{.spec.clusterIP}')
    log_verbose "$service cluster IP: $cluster_ip:$port"
    
    # Try to connect from within the cluster
    # Clean up any previous health check pod first
    kubectl delete pod health-check-temp -n "$NAMESPACE" --ignore-not-found=true >/dev/null 2>&1
    
    if timeout 30 kubectl run health-check-temp --image=busybox --rm --restart=Never -n "$NAMESPACE" -- sh -c "nc -z $cluster_ip $port" >/dev/null 2>&1; then
        log_success "$service: Service connectivity verified"
    else
        log_error "$service: Service connectivity failed"
        # Clean up the pod in case --rm didn't work
        kubectl delete pod health-check-temp -n "$NAMESPACE" --ignore-not-found=true >/dev/null 2>&1
        return 1
    fi
}

# Check database connectivity
check_database() {
    log_info "Checking database connectivity..."
    
    # Check PostgreSQL pod
    if ! kubectl get statefulset benger-postgresql -n "$NAMESPACE" >/dev/null 2>&1; then
        log_error "PostgreSQL statefulset not found"
        return 1
    fi
    
    # Wait for PostgreSQL to be ready
    if kubectl wait --for=condition=ready pod/benger-postgresql-0 -n "$NAMESPACE" --timeout=30s >/dev/null 2>&1; then
        log_success "PostgreSQL pod is ready"
    else
        log_error "PostgreSQL pod not ready within 30 seconds"
        return 1
    fi
    
    # Test database connection from API pod
    local db_test_output=$(timeout 30 kubectl exec -n "$NAMESPACE" deployment/benger-api --timeout=10s -- python -c "
import os
from sqlalchemy import create_engine, text
try:
    uri = os.getenv('DATABASE_URI')
    if not uri:
        print('DATABASE_URI environment variable is not set')
        exit(1)
    print(f'Using DATABASE_URI: {uri[:30]}...{uri[-20:]}')
    engine = create_engine(uri)
    with engine.connect() as conn:
        result = conn.execute(text('SELECT 1'))
        assert result.fetchone()[0] == 1
    print('Database connection successful')
except Exception as e:
    print(f'Database connection failed: {e}')
    import traceback
    traceback.print_exc()
    exit(1)
" 2>&1)
    
    local db_test_result=$?
    
    if [ $db_test_result -eq 0 ]; then
        log_success "Database connectivity verified from API"
    else
        log_error "Database connectivity failed from API"
        log_verbose "Database test output:"
        echo "$db_test_output" | sed 's/^/  /' | head -20
        return 1
    fi
}

# Check Redis connectivity
check_redis() {
    log_info "Checking Redis connectivity..."
    
    # Check Redis master
    if ! kubectl get statefulset benger-redis-master -n "$NAMESPACE" >/dev/null 2>&1; then
        log_error "Redis master statefulset not found"
        return 1
    fi
    
    # Wait for Redis master to be ready
    if kubectl wait --for=condition=ready pod/benger-redis-master-0 -n "$NAMESPACE" --timeout=30s >/dev/null 2>&1; then
        log_success "Redis master pod is ready"
    else
        log_warning "Redis master pod not ready within 30 seconds"
    fi
    
    # Test Redis connection
    if timeout 30 kubectl exec -n "$NAMESPACE" benger-redis-master-0 --timeout=10s -- redis-cli ping >/dev/null 2>&1; then
        log_success "Redis connectivity verified"
    else
        log_error "Redis connectivity failed"
        return 1
    fi
}

# Check external endpoints
check_external_endpoints() {
    log_info "Checking external endpoints..."
    
    local endpoints=(
        "https://what-a-benger.net"
        "https://api.what-a-benger.net/health"
        # Skip Label Studio endpoint - it's disabled for CI/CD reliability
    )
    
    for endpoint in "${endpoints[@]}"; do
        if curl -f -s --max-time 10 "$endpoint" >/dev/null 2>&1; then
            log_success "External endpoint reachable: $endpoint"
        else
            log_warning "External endpoint unreachable: $endpoint"
        fi
    done
}

# Check ingress configuration
check_ingress() {
    log_info "Checking ingress configuration..."
    
    local ingresses=$(kubectl get ingress -n "$NAMESPACE" -o name 2>/dev/null)
    if [ -z "$ingresses" ]; then
        log_warning "No ingresses found in namespace"
        return 0
    fi
    
    for ingress in $ingresses; do
        local ingress_name=$(echo "$ingress" | cut -d'/' -f2)
        local ready=$(kubectl get "$ingress" -n "$NAMESPACE" -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null)
        
        if [ -n "$ready" ]; then
            log_success "Ingress '$ingress_name' has load balancer IP: $ready"
        else
            log_warning "Ingress '$ingress_name' does not have load balancer IP assigned"
        fi
    done
}

# Check resource utilization
check_resources() {
    log_info "Checking resource utilization..."
    
    # Check node resources
    local node_info=$(timeout 30 kubectl top nodes 2>/dev/null || echo "Metrics not available")
    if [ "$node_info" != "Metrics not available" ]; then
        log_verbose "Node resource usage:"
        echo "$node_info" | sed 's/^/  /'
        log_success "Node metrics available"
    else
        log_warning "Node metrics not available (metrics-server might not be running)"
    fi
    
    # Check pod resources in namespace
    local pod_info=$(timeout 30 kubectl top pods -n "$NAMESPACE" 2>/dev/null || echo "Metrics not available")
    if [ "$pod_info" != "Metrics not available" ]; then
        log_verbose "Pod resource usage in $NAMESPACE:"
        echo "$pod_info" | sed 's/^/  /'
        log_success "Pod metrics available"
    else
        log_warning "Pod metrics not available in namespace $NAMESPACE"
    fi
}

# Check persistent volumes
check_storage() {
    log_info "Checking persistent storage..."
    
    local pvcs=$(kubectl get pvc -n "$NAMESPACE" -o name 2>/dev/null)
    if [ -z "$pvcs" ]; then
        log_warning "No persistent volume claims found"
        return 0
    fi
    
    for pvc in $pvcs; do
        local pvc_name=$(echo "$pvc" | cut -d'/' -f2)
        local status=$(kubectl get "$pvc" -n "$NAMESPACE" -o jsonpath='{.status.phase}')
        
        if [ "$status" = "Bound" ]; then
            log_success "PVC '$pvc_name' is bound"
        else
            log_error "PVC '$pvc_name' status: $status"
        fi
    done
}

# Run component-specific health checks
run_component_checks() {
    case $CHECK_TYPE in
        "full")
            check_namespace
            check_pod_health "benger-api" 1
            check_pod_health "benger-frontend" 1  
            check_pod_health "benger-workers" 1
            check_database
            check_redis
            check_ingress
            check_storage
            check_resources
            check_external_endpoints
            ;;
        "quick")
            check_namespace
            check_pod_health "benger-api" 1
            check_pod_health "benger-frontend" 1
            check_pod_health "benger-workers" 1
            check_database
            ;;
        "api")
            check_pod_health "benger-api" 1
            check_database
            ;;
        "frontend")
            check_pod_health "benger-frontend" 1
            ;;
        "workers")
            check_pod_health "benger-workers" 1
            ;;
        "database")
            check_database
            ;;
        "redis")
            check_redis
            ;;
        "external")
            check_external_endpoints
            ;;
        *)
            log_error "Unknown check type: $CHECK_TYPE"
            log_info "Available types: full, quick, api, frontend, workers, database, redis, external"
            exit 1
            ;;
    esac
}

# Print health check summary
print_summary() {
    echo ""
    echo "=================================="
    echo "📊 Health Check Summary"
    echo "=================================="
    echo "Completed: $(date)"
    
    if [ ${#FAILED_CHECKS[@]} -eq 0 ]; then
        if [ ${#WARNING_CHECKS[@]} -eq 0 ]; then
            log_success "All health checks passed! 🎉"
        else
            log_warning "${#WARNING_CHECKS[@]} warning(s) found:"
            for warning in "${WARNING_CHECKS[@]}"; do
                echo "  - $warning"
            done
        fi
    else
        log_error "${#FAILED_CHECKS[@]} critical issue(s) found:"
        for error in "${FAILED_CHECKS[@]}"; do
            echo "  - $error"
        done
        
        if [ ${#WARNING_CHECKS[@]} -gt 0 ]; then
            echo ""
            log_warning "${#WARNING_CHECKS[@]} warning(s) found:"
            for warning in "${WARNING_CHECKS[@]}"; do
                echo "  - $warning"
            done
        fi
    fi
    
    echo ""
    echo "Exit code: $HEALTH_STATUS"
}

# Show usage information
show_usage() {
    echo "Usage: $0 [NAMESPACE] [CHECK_TYPE] [TIMEOUT] [VERBOSE]"
    echo ""
    echo "Parameters:"
    echo "  NAMESPACE   Kubernetes namespace (default: benger)"
    echo "  CHECK_TYPE  Type of check to run (default: full)"
    echo "              Options: full, quick, api, frontend, workers, database, redis, external"
    echo "  TIMEOUT     Timeout in seconds (default: 300)"
    echo "  VERBOSE     Enable verbose output (true/false, default: false)"
    echo ""
    echo "Examples:"
    echo "  $0                          # Full health check in benger namespace"
    echo "  $0 benger-staging quick     # Quick check in staging"
    echo "  $0 benger api 60 true       # API check with 60s timeout and verbose output"
}

# Main execution
main() {
    # Handle help request
    if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
        show_usage
        exit 0
    fi
    
    print_header
    
    # Run component checks with individual timeouts instead of global timeout
    # This avoids the complexity of exporting functions and arrays to subshells
    run_component_checks
    
    print_summary
    exit $HEALTH_STATUS
}

# Execute main function with all arguments
main "$@"