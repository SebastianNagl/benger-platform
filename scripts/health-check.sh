#!/bin/bash

# BenGER Health Check Script
# Usage: ./health-check.sh <namespace> <check-type> <timeout> <verbose>

set -e

NAMESPACE=${1:-benger}
CHECK_TYPE=${2:-full}
TIMEOUT=${3:-180}
VERBOSE=${4:-false}

echo "🏥 BenGER Health Check"
echo "📍 Namespace: $NAMESPACE"
echo "🔍 Check type: $CHECK_TYPE"
echo "⏱️ Timeout: ${TIMEOUT}s"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to check pod health
check_pods() {
    echo "📊 Checking pod health..."
    
    local unhealthy_pods=$(kubectl get pods -n "$NAMESPACE" --field-selector=status.phase!=Running,status.phase!=Succeeded -o name 2>/dev/null | wc -l)
    
    if [ "$unhealthy_pods" -eq 0 ]; then
        echo -e "${GREEN}✅ All pods are healthy${NC}"
        return 0
    else
        echo -e "${RED}❌ Found $unhealthy_pods unhealthy pods${NC}"
        if [ "$VERBOSE" = "true" ]; then
            kubectl get pods -n "$NAMESPACE" --field-selector=status.phase!=Running,status.phase!=Succeeded
        fi
        return 1
    fi
}

# Function to check deployments
check_deployments() {
    echo "📊 Checking deployments..."
    
    local deployments=$(kubectl get deployments -n "$NAMESPACE" -o json 2>/dev/null)
    local all_ready=true
    
    if [ -z "$deployments" ]; then
        echo -e "${YELLOW}⚠️ No deployments found${NC}"
        return 1
    fi
    
    while IFS= read -r deployment; do
        local name=$(echo "$deployment" | jq -r '.metadata.name')
        local ready=$(echo "$deployment" | jq -r '.status.conditions[] | select(.type=="Available") | .status')
        
        if [ "$ready" = "True" ]; then
            echo -e "${GREEN}✅ $name is ready${NC}"
        else
            echo -e "${RED}❌ $name is not ready${NC}"
            all_ready=false
        fi
    done < <(echo "$deployments" | jq -c '.items[]')
    
    if [ "$all_ready" = "true" ]; then
        return 0
    else
        return 1
    fi
}

# Function to check services
check_services() {
    echo "📊 Checking services..."
    
    local services=$(kubectl get services -n "$NAMESPACE" -o name 2>/dev/null | wc -l)
    
    if [ "$services" -gt 0 ]; then
        echo -e "${GREEN}✅ Found $services services${NC}"
        if [ "$VERBOSE" = "true" ]; then
            kubectl get services -n "$NAMESPACE"
        fi
        return 0
    else
        echo -e "${YELLOW}⚠️ No services found${NC}"
        return 1
    fi
}

# Function to check API health
check_api() {
    echo "📊 Checking API health endpoint..."
    
    # Try to get API service endpoint
    local api_endpoint=""
    
    # Check if running in cluster
    if [ -f "/var/run/secrets/kubernetes.io/serviceaccount/token" ]; then
        api_endpoint="http://benger-api.$NAMESPACE.svc.cluster.local:8000/health"
    else
        # Check for port-forward or ingress
        api_endpoint="https://api.what-a-benger.net/health"
    fi
    
    if curl -f -s --max-time 10 "$api_endpoint" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ API health check passed${NC}"
        return 0
    else
        echo -e "${YELLOW}⚠️ API health check failed or timed out${NC}"
        return 1
    fi
}

# Function to check database connectivity
check_database() {
    echo "📊 Checking database connectivity..."
    
    # Check if PostgreSQL pod is running (try multiple label selectors)
    local pg_pods=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=postgresql -o name 2>/dev/null | wc -l)
    
    if [ "$pg_pods" -eq 0 ]; then
        # Try alternative label selector
        pg_pods=$(kubectl get pods -n "$NAMESPACE" -l app=postgresql -o name 2>/dev/null | wc -l)
    fi
    
    if [ "$pg_pods" -gt 0 ]; then
        echo -e "${GREEN}✅ PostgreSQL pod found${NC}"
        return 0
    else
        # Check for external database service
        local pg_service=$(kubectl get service -n "$NAMESPACE" -l app.kubernetes.io/name=postgresql -o name 2>/dev/null | wc -l)
        if [ "$pg_service" -eq 0 ]; then
            # Try alternative label selector
            pg_service=$(kubectl get service -n "$NAMESPACE" -l app=postgresql -o name 2>/dev/null | wc -l)
        fi
        
        if [ "$pg_service" -gt 0 ]; then
            echo -e "${GREEN}✅ PostgreSQL service found${NC}"
            return 0
        else
            echo -e "${YELLOW}⚠️ PostgreSQL not found (may be external)${NC}"
            return 1
        fi
    fi
}

# Function to check external endpoints
check_external() {
    echo "📊 Checking external endpoints..."
    
    local endpoints=(
        "https://what-a-benger.net"
        "https://api.what-a-benger.net/health"
    )
    
    local all_healthy=true
    for endpoint in "${endpoints[@]}"; do
        if curl -f -s --max-time 10 "$endpoint" > /dev/null 2>&1; then
            echo -e "${GREEN}✅ $endpoint is accessible${NC}"
        else
            echo -e "${YELLOW}⚠️ $endpoint is not accessible${NC}"
            all_healthy=false
        fi
    done
    
    if [ "$all_healthy" = "true" ]; then
        return 0
    else
        return 1
    fi
}

# Main health check logic
main() {
    local overall_health=true
    
    case "$CHECK_TYPE" in
        "full")
            check_pods || overall_health=false
            check_deployments || overall_health=false
            check_services || overall_health=false
            check_api || overall_health=false
            check_database || overall_health=false
            check_external || overall_health=false
            ;;
        "api")
            check_api || overall_health=false
            ;;
        "database")
            check_database || overall_health=false
            ;;
        "pods")
            check_pods || overall_health=false
            ;;
        "external")
            check_external || overall_health=false
            ;;
        *)
            echo "❌ Unknown check type: $CHECK_TYPE"
            echo "Valid types: full, api, database, pods, external"
            exit 1
            ;;
    esac
    
    echo ""
    if [ "$overall_health" = "true" ]; then
        echo -e "${GREEN}✅ Health check passed!${NC}"
        exit 0
    else
        echo -e "${RED}❌ Health check failed!${NC}"
        exit 1
    fi
}

# Execute main function
main "$@"