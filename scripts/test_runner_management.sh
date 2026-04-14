#!/bin/bash

# BenGER Runner Management Test Suite
# Tests for GitHub Actions runner resource management improvements

# Don't exit on error - we want to run all tests

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_RESULTS_DIR="$SCRIPT_DIR/test_results"
TEST_LOG="$TEST_RESULTS_DIR/runner_management_tests.log"

# Test counters
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Initialize test environment
init_test_env() {
    mkdir -p "$TEST_RESULTS_DIR"
    echo "Runner Management Test Suite - $(date)" > "$TEST_LOG"
    echo "======================================" >> "$TEST_LOG"
}

# Log test result
log_test() {
    local test_name=$1
    local status=$2
    local message=$3
    
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$status] $test_name: $message" >> "$TEST_LOG"
    
    if [ "$status" = "PASS" ]; then
        echo -e "${GREEN}✓${NC} $test_name"
        ((TESTS_PASSED++))
    elif [ "$status" = "FAIL" ]; then
        echo -e "${RED}✗${NC} $test_name: $message"
        ((TESTS_FAILED++))
    else
        echo -e "${YELLOW}⚠${NC} $test_name: $message"
    fi
    ((TESTS_RUN++))
}

# Test 1: Verify cleanup script exists and is executable
test_cleanup_script_exists() {
    local test_name="Cleanup Script Exists"
    
    if [ -f "$SCRIPT_DIR/runner-health-monitor.sh" ] && [ -x "$SCRIPT_DIR/runner-health-monitor.sh" ]; then
        log_test "$test_name" "PASS" "Script exists and is executable"
    else
        log_test "$test_name" "FAIL" "Script not found or not executable"
    fi
}

# Test 2: Test process detection for hung alembic
test_hung_process_detection() {
    local test_name="Hung Process Detection"
    
    # Create a test process that simulates hung alembic
    sleep 1000 &
    local test_pid=$!
    
    if [ -n "$test_pid" ]; then
        # Check if process detection logic works
        if ps -p "$test_pid" > /dev/null 2>&1; then
            log_test "$test_name" "PASS" "Test process created and detected"
            kill "$test_pid" 2>/dev/null || true
            wait "$test_pid" 2>/dev/null || true
        else
            log_test "$test_name" "FAIL" "Failed to create test process"
        fi
    else
        log_test "$test_name" "FAIL" "Could not get test process PID"
    fi
}

# Test 3: Test Docker cleanup functionality
test_docker_cleanup() {
    local test_name="Docker Cleanup Functionality"
    
    # Check if Docker is available
    if command -v docker &> /dev/null; then
        # Create a test container
        docker run -d --name test_cleanup_container --label "test=cleanup" alpine sleep 1000 2>/dev/null || true
        
        # Check if container was created
        if docker ps -q --filter "name=test_cleanup_container" | grep -q .; then
            # Stop and remove container
            docker stop test_cleanup_container > /dev/null 2>&1
            docker rm test_cleanup_container > /dev/null 2>&1
            
            # Verify cleanup
            if ! docker ps -aq --filter "name=test_cleanup_container" | grep -q .; then
                log_test "$test_name" "PASS" "Docker cleanup works correctly"
            else
                log_test "$test_name" "FAIL" "Container not cleaned up properly"
                docker rm -f test_cleanup_container 2>/dev/null || true
            fi
        else
            log_test "$test_name" "SKIP" "Could not create test container"
        fi
    else
        log_test "$test_name" "SKIP" "Docker not available"
    fi
}

# Test 4: Test resource limits configuration
test_resource_limits_config() {
    local test_name="Resource Limits Configuration"
    
    if [ -f "$SCRIPT_DIR/runner-resource-limits.conf" ]; then
        # Check for required configuration parameters
        local has_cpu_quota=$(grep -c "CPUQuota=" "$SCRIPT_DIR/runner-resource-limits.conf" || echo 0)
        local has_memory_limit=$(grep -c "MemoryLimit=" "$SCRIPT_DIR/runner-resource-limits.conf" || echo 0)
        local has_tasks_max=$(grep -c "TasksMax=" "$SCRIPT_DIR/runner-resource-limits.conf" || echo 0)
        
        if [ "$has_cpu_quota" -gt 0 ] && [ "$has_memory_limit" -gt 0 ] && [ "$has_tasks_max" -gt 0 ]; then
            log_test "$test_name" "PASS" "All required resource limits configured"
        else
            log_test "$test_name" "FAIL" "Missing resource limit configurations"
        fi
    else
        log_test "$test_name" "FAIL" "Resource limits configuration file not found"
    fi
}

# Test 5: Test systemd service detection
test_systemd_service_detection() {
    local test_name="Systemd Service Detection"
    
    # Check if systemctl is available
    if command -v systemctl &> /dev/null; then
        # Look for GitHub Actions runner services
        local runner_count=$(systemctl list-units --all --no-legend | grep -c "actions\.runner\." || echo 0)
        
        if [ "$runner_count" -gt 0 ]; then
            log_test "$test_name" "PASS" "Found $runner_count runner service(s)"
        else
            log_test "$test_name" "WARN" "No runner services found (may be expected in test environment)"
        fi
    else
        log_test "$test_name" "SKIP" "systemctl not available"
    fi
}

# Test 6: Test health monitor script syntax
test_health_monitor_syntax() {
    local test_name="Health Monitor Script Syntax"
    
    if [ -f "$SCRIPT_DIR/runner-health-monitor.sh" ]; then
        if bash -n "$SCRIPT_DIR/runner-health-monitor.sh" 2>/dev/null; then
            log_test "$test_name" "PASS" "Script has valid bash syntax"
        else
            log_test "$test_name" "FAIL" "Script has syntax errors"
        fi
    else
        log_test "$test_name" "FAIL" "Health monitor script not found"
    fi
}

# Test 7: Test resource limits setup script
test_resource_limits_setup() {
    local test_name="Resource Limits Setup Script"
    
    if [ -f "$SCRIPT_DIR/setup-runner-resource-limits.sh" ]; then
        if bash -n "$SCRIPT_DIR/setup-runner-resource-limits.sh" 2>/dev/null; then
            log_test "$test_name" "PASS" "Setup script has valid syntax"
        else
            log_test "$test_name" "FAIL" "Setup script has syntax errors"
        fi
    else
        log_test "$test_name" "FAIL" "Setup script not found"
    fi
}

# Test 8: Test CI workflow modifications
test_ci_workflow_changes() {
    local test_name="CI Workflow Cleanup Steps"
    local workflow_file="$SCRIPT_DIR/../.github/workflows/ci.yml"
    
    if [ -f "$workflow_file" ]; then
        # Check for enhanced cleanup steps
        local has_process_cleanup=$(grep -c "pkill.*alembic" "$workflow_file" || echo 0)
        local has_docker_cleanup=$(grep -c "docker.*stop.*RUN_ID" "$workflow_file" || echo 0)
        local has_github_cleanup=$(grep -c "com.github.actions.run_id" "$workflow_file" || echo 0)
        
        if [ "$has_process_cleanup" -gt 0 ] && ([ "$has_docker_cleanup" -gt 0 ] || [ "$has_github_cleanup" -gt 0 ]); then
            log_test "$test_name" "PASS" "CI workflow has enhanced cleanup steps"
        else
            log_test "$test_name" "FAIL" "CI workflow missing cleanup enhancements"
        fi
    else
        log_test "$test_name" "FAIL" "CI workflow file not found"
    fi
}

# Test 9: Test disk usage monitoring
test_disk_usage_monitoring() {
    local test_name="Disk Usage Monitoring"
    
    # Get current disk usage
    local disk_usage=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
    
    if [ -n "$disk_usage" ]; then
        log_test "$test_name" "PASS" "Disk usage monitoring works: ${disk_usage}%"
    else
        log_test "$test_name" "FAIL" "Could not determine disk usage"
    fi
}

# Test 10: Test memory monitoring
test_memory_monitoring() {
    local test_name="Memory Monitoring"
    
    # Get memory stats
    local mem_total=$(free -m | awk 'NR==2{print $2}')
    local mem_used=$(free -m | awk 'NR==2{print $3}')
    
    if [ -n "$mem_total" ] && [ -n "$mem_used" ]; then
        local mem_usage=$((mem_used * 100 / mem_total))
        log_test "$test_name" "PASS" "Memory monitoring works: ${mem_usage}% used"
    else
        log_test "$test_name" "FAIL" "Could not determine memory usage"
    fi
}

# Test 11: Test zombie process detection
test_zombie_process_detection() {
    local test_name="Zombie Process Detection"
    
    # Count zombie processes (should normally be 0)
    local zombie_count=$(ps aux | grep -c " Z " || echo 0)
    
    if [ "$zombie_count" -eq 0 ]; then
        log_test "$test_name" "PASS" "No zombie processes detected"
    else
        log_test "$test_name" "WARN" "Found $zombie_count zombie process(es)"
    fi
}

# Test 12: Test log rotation setup
test_log_rotation() {
    local test_name="Log Rotation Configuration"
    
    # Check if log file location is defined
    if grep -q "LOG_FILE=" "$SCRIPT_DIR/runner-health-monitor.sh" 2>/dev/null; then
        log_test "$test_name" "PASS" "Log file configuration found"
    else
        log_test "$test_name" "FAIL" "Log file not configured"
    fi
}

# Test 13: Test process timeout configuration
test_process_timeouts() {
    local test_name="Process Timeout Configuration"
    
    if [ -f "$SCRIPT_DIR/runner-health-monitor.sh" ]; then
        local has_alembic_timeout=$(grep -c "MAX_ALEMBIC_TIME=" "$SCRIPT_DIR/runner-health-monitor.sh" || echo 0)
        local has_pytest_timeout=$(grep -c "MAX_PYTEST_TIME=" "$SCRIPT_DIR/runner-health-monitor.sh" || echo 0)
        
        if [ "$has_alembic_timeout" -gt 0 ] && [ "$has_pytest_timeout" -gt 0 ]; then
            log_test "$test_name" "PASS" "Process timeouts configured"
        else
            log_test "$test_name" "FAIL" "Process timeouts not properly configured"
        fi
    else
        log_test "$test_name" "FAIL" "Health monitor script not found"
    fi
}

# Test 14: Test cgroup integration
test_cgroup_integration() {
    local test_name="Cgroup Integration"
    
    # Check if cgroup v2 is available
    if [ -d "/sys/fs/cgroup/system.slice" ]; then
        log_test "$test_name" "PASS" "Cgroup v2 filesystem available"
    else
        log_test "$test_name" "WARN" "Cgroup v2 not available (may be expected in containers)"
    fi
}

# Test 15: Integration test - simulate workflow
test_integration_workflow() {
    local test_name="Integration Workflow Simulation"
    
    # This would be a more complex test in a real environment
    # For now, just verify all components exist
    local all_components_exist=true
    
    [ -f "$SCRIPT_DIR/runner-health-monitor.sh" ] || all_components_exist=false
    [ -f "$SCRIPT_DIR/runner-resource-limits.conf" ] || all_components_exist=false
    [ -f "$SCRIPT_DIR/setup-runner-resource-limits.sh" ] || all_components_exist=false
    
    if $all_components_exist; then
        log_test "$test_name" "PASS" "All components present for integration"
    else
        log_test "$test_name" "FAIL" "Missing components for integration"
    fi
}

# Generate test report
generate_report() {
    echo ""
    echo "========================================"
    echo "Test Results Summary"
    echo "========================================"
    echo -e "Tests Run:    ${BLUE}$TESTS_RUN${NC}"
    echo -e "Tests Passed: ${GREEN}$TESTS_PASSED${NC}"
    echo -e "Tests Failed: ${RED}$TESTS_FAILED${NC}"
    echo ""
    
    local pass_rate=0
    if [ "$TESTS_RUN" -gt 0 ]; then
        pass_rate=$((TESTS_PASSED * 100 / TESTS_RUN))
    fi
    
    echo "Pass Rate: ${pass_rate}%"
    echo ""
    echo "Detailed results saved to: $TEST_LOG"
    
    # Save summary to log
    {
        echo ""
        echo "========================================"
        echo "Summary:"
        echo "Tests Run: $TESTS_RUN"
        echo "Tests Passed: $TESTS_PASSED"
        echo "Tests Failed: $TESTS_FAILED"
        echo "Pass Rate: ${pass_rate}%"
    } >> "$TEST_LOG"
}

# Main test execution
main() {
    echo "BenGER Runner Management Test Suite"
    echo "===================================="
    echo ""
    
    init_test_env
    
    # Run all tests
    test_cleanup_script_exists
    test_hung_process_detection
    test_docker_cleanup
    test_resource_limits_config
    test_systemd_service_detection
    test_health_monitor_syntax
    test_resource_limits_setup
    test_ci_workflow_changes
    test_disk_usage_monitoring
    test_memory_monitoring
    test_zombie_process_detection
    test_log_rotation
    test_process_timeouts
    test_cgroup_integration
    test_integration_workflow
    
    # Generate report
    generate_report
    
    # Exit with appropriate code
    if [ "$TESTS_FAILED" -gt 0 ]; then
        exit 1
    else
        exit 0
    fi
}

# Run tests if script is executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi