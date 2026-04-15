#!/bin/bash
#
# GitHub Actions Runner Monitoring Script
# Monitors runner health, system resources, and connectivity
#

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="/var/log/github-actions-runner/monitor.log"
ALERT_THRESHOLD_CPU=80
ALERT_THRESHOLD_MEMORY=80
ALERT_THRESHOLD_DISK=90
CHECK_INTERVAL=300  # 5 minutes

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# Check if runner service is running
check_runner_service() {
    log "Checking runner service status..."
    
    if systemctl is-active --quiet actions-runner-deploy; then
        log "✓ Runner service is active"
        return 0
    else
        log "✗ Runner service is not active"
        return 1
    fi
}

# Check system resources
check_system_resources() {
    log "Checking system resources..."
    
    # CPU usage
    CPU_USAGE=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1)
    CPU_USAGE_INT=${CPU_USAGE%.*}
    
    if [ "$CPU_USAGE_INT" -gt "$ALERT_THRESHOLD_CPU" ]; then
        log "⚠ High CPU usage: ${CPU_USAGE}%"
    else
        log "✓ CPU usage normal: ${CPU_USAGE}%"
    fi
    
    # Memory usage
    MEMORY_USAGE=$(free | grep Mem | awk '{printf "%.0f", $3/$2 * 100.0}')
    
    if [ "$MEMORY_USAGE" -gt "$ALERT_THRESHOLD_MEMORY" ]; then
        log "⚠ High memory usage: ${MEMORY_USAGE}%"
    else
        log "✓ Memory usage normal: ${MEMORY_USAGE}%"
    fi
    
    # Disk usage
    DISK_USAGE=$(df / | tail -1 | awk '{print $5}' | cut -d'%' -f1)
    
    if [ "$DISK_USAGE" -gt "$ALERT_THRESHOLD_DISK" ]; then
        log "⚠ High disk usage: ${DISK_USAGE}%"
    else
        log "✓ Disk usage normal: ${DISK_USAGE}%"
    fi
}

# Check GitHub connectivity
check_github_connectivity() {
    log "Checking GitHub connectivity..."
    
    if curl -s --max-time 10 https://api.github.com/rate_limit > /dev/null; then
        log "✓ GitHub API accessible"
        return 0
    else
        log "✗ GitHub API not accessible"
        return 1
    fi
}

# Check runner registration status
check_runner_registration() {
    log "Checking runner registration status..."
    
    # This would need to be customized based on actual runner setup
    if [ -f "/opt/actions-runner/_diag/Runner_*.log" ]; then
        LATEST_LOG=$(ls -t /opt/actions-runner/_diag/Runner_*.log | head -1)
        if grep -q "Connected to GitHub" "$LATEST_LOG" 2>/dev/null; then
            log "✓ Runner connected to GitHub"
            return 0
        fi
    fi
    
    log "⚠ Unable to verify runner registration"
    return 1
}

# Check for stuck jobs
check_stuck_jobs() {
    log "Checking for stuck jobs..."
    
    # Look for long-running processes that might indicate stuck jobs
    LONG_RUNNING=$(ps aux | awk '$10 > 3600' | wc -l)
    
    if [ "$LONG_RUNNING" -gt 5 ]; then
        log "⚠ Found $LONG_RUNNING processes running > 1 hour"
    else
        log "✓ No stuck jobs detected"
    fi
}

# Main monitoring function
run_health_check() {
    log "=== Starting health check ==="
    
    local exit_code=0
    
    check_runner_service || exit_code=1
    check_system_resources
    check_github_connectivity || exit_code=1
    check_runner_registration || exit_code=1
    check_stuck_jobs
    
    log "=== Health check completed (exit code: $exit_code) ==="
    
    return $exit_code
}

# Continuous monitoring mode
continuous_monitor() {
    log "Starting continuous monitoring (interval: ${CHECK_INTERVAL}s)"
    
    while true; do
        run_health_check
        sleep "$CHECK_INTERVAL"
    done
}

# Main script logic
main() {
    case "${1:-check}" in
        "continuous")
            continuous_monitor
            ;;
        "check")
            run_health_check
            ;;
        "help")
            echo "Usage: $0 [check|continuous|help]"
            echo "  check      - Run single health check (default)"
            echo "  continuous - Run continuous monitoring"
            echo "  help       - Show this help"
            ;;
        *)
            log "Unknown command: $1"
            exit 1
            ;;
    esac
}

# Execute main function with all arguments
main "$@"