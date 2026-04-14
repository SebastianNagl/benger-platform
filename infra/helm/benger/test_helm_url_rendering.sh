#!/bin/bash

# Test script for Helm template URL rendering
# This script validates that Helm templates properly evaluate nested template expressions
# specifically for URL environment variables that reference .Values.global.domain

set -e

echo "Testing Helm template URL rendering..."
echo "======================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# Navigate to Helm chart directory
cd "$(dirname "$0")"

# Test function
test_url_rendering() {
    local service=$1
    local env_var=$2
    local expected_value=$3
    
    echo -n "Testing $service - $env_var: "
    
    # Render the template and check for the environment variable
    result=$(helm template . --name-template=benger 2>/dev/null | \
             grep -A 1 "name: $env_var" | \
             grep "value:" | \
             sed 's/.*value: "\(.*\)"/\1/' | \
             head -1)
    
    if [[ "$result" == "$expected_value" ]]; then
        echo -e "${GREEN}✓ PASS${NC} (got: $result)"
        return 0
    else
        echo -e "${RED}✗ FAIL${NC} (expected: $expected_value, got: $result)"
        return 1
    fi
}

# Run tests
echo ""
echo "Running tests..."
echo "----------------"

failed=0

# Test API deployment
if ! test_url_rendering "API" "FRONTEND_URL" "https://what-a-benger.net"; then
    failed=$((failed + 1))
fi

# Test Workers deployment  
if ! test_url_rendering "Workers" "FRONTEND_URL" "https://what-a-benger.net"; then
    failed=$((failed + 1))
fi

# Test Frontend deployment
if ! test_url_rendering "Frontend" "NEXT_PUBLIC_API_URL" "https://api.what-a-benger.net"; then
    failed=$((failed + 1))
fi

# Check for any remaining template syntax (should not find any)
echo ""
echo -n "Checking for unprocessed template syntax: "
if helm template . --name-template=benger 2>/dev/null | grep -q "{{ .Values"; then
    echo -e "${RED}✗ FAIL${NC} - Found unprocessed template syntax in rendered output"
    failed=$((failed + 1))
else
    echo -e "${GREEN}✓ PASS${NC} - No unprocessed template syntax found"
fi

# Summary
echo ""
echo "======================================="
if [[ $failed -eq 0 ]]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}$failed test(s) failed${NC}"
    exit 1
fi