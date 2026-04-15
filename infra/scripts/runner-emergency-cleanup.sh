#!/bin/bash
#
# Emergency Cleanup Script for GitHub Actions Runners
# Handles stuck, corrupted, or problematic runner states
#

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="/var/log/github-actions-runner/emergency.log"
RUNNER_SERVICE="actions-runner-deploy"
RUNNER_HOME="/opt/actions-runner"
FORCE_MODE=false
BACKUP_DIR="/var/backups/github-actions-runner/emergency"

# Ensure log and backup directories exist
mkdir -p "$(dirname "$LOG_FILE")" "$BACKUP_DIR"

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] EMERGENCY: $*" | tee -a "$LOG_FILE"
}

# Confirmation prompt for destructive operations
confirm_action() {
    local message="$1"
    
    if [ "$FORCE_MODE" = true ]; then
        log "Force mode enabled, skipping confirmation for: $message"
        return 0
    fi
    
    echo "⚠️  EMERGENCY ACTION: $message"
    read -p "Are you sure? (yes/no): " -r
    if [[ $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        return 0
    else
        log "Action cancelled by user: $message"
        return 1
    fi
}

# Stop runner service forcefully
emergency_stop_service() {
    log "Attempting emergency stop of runner service..."
    
    if confirm_action "Stop runner service forcefully"; then
        # Try graceful stop first
        if systemctl is-active --quiet "$RUNNER_SERVICE"; then
            log "Attempting graceful stop..."
            systemctl stop "$RUNNER_SERVICE" || true
            sleep 5
        fi
        
        # If still running, kill forcefully
        if systemctl is-active --quiet "$RUNNER_SERVICE"; then
            log "Service still running, attempting force kill..."
            systemctl kill --signal=SIGKILL "$RUNNER_SERVICE" || true
            sleep 2
        fi
        
        # Kill any remaining runner processes
        pkill -f "Runner.Listener" || true
        pkill -f "Runner.Worker" || true
        
        log "✓ Emergency service stop completed"
    fi
}

# Clean up stuck processes
cleanup_stuck_processes() {
    log "Cleaning up stuck processes..."
    
    if confirm_action "Kill stuck runner and build processes"; then
        # Kill long-running build processes
        log "Killing processes running longer than 2 hours..."
        
        # Find and kill processes older than 2 hours (7200 seconds)
        while IFS= read -r line; do
            if [ -n "$line" ]; then
                PID=$(echo "$line" | awk '{print $2}')
                COMMAND=$(echo "$line" | awk '{for(i=11;i<=NF;i++) printf "%s ", $i; print ""}')
                log "Killing stuck process: PID=$PID CMD=$COMMAND"
                kill -TERM "$PID" 2>/dev/null || true
                sleep 1
                kill -KILL "$PID" 2>/dev/null || true
            fi
        done < <(ps -eo pid,etime,cmd | awk '$2 ~ /-/ || $2 ~ /[0-9][0-9]:[0-9][0-9]:[0-9][0-9]/ {if ($2 !~ /^[0-9][0-9]:[0-9][0-9]$/) print}')
        
        log "✓ Stuck process cleanup completed"
    fi
}

# Remove corrupted runner state
cleanup_runner_state() {
    log "Cleaning up potentially corrupted runner state..."
    
    if confirm_action "Remove runner state files and working directories"; then
        # Backup current state first
        BACKUP_TIMESTAMP=$(date +%Y%m%d_%H%M%S)
        BACKUP_PATH="${BACKUP_DIR}/state_${BACKUP_TIMESTAMP}"
        mkdir -p "$BACKUP_PATH"
        
        # Backup important files
        local files_to_backup=(
            "${RUNNER_HOME}/.runner"
            "${RUNNER_HOME}/.credentials"
            "${RUNNER_HOME}/.credentials_rsaparams"
        )
        
        for file in "${files_to_backup[@]}"; do
            if [ -f "$file" ]; then
                cp "$file" "$BACKUP_PATH/" 2>/dev/null || true
                log "Backed up: $file"
            fi
        done
        
        # Clean up working directories
        if [ -d "${RUNNER_HOME}/_work" ]; then
            log "Removing work directory contents..."
            rm -rf "${RUNNER_HOME}/_work"/* 2>/dev/null || true
        fi
        
        # Clean up diagnostic logs
        if [ -d "${RUNNER_HOME}/_diag" ]; then
            log "Cleaning diagnostic logs..."
            find "${RUNNER_HOME}/_diag" -name "*.log" -type f -delete 2>/dev/null || true
        fi
        
        # Remove lock files
        find "${RUNNER_HOME}" -name "*.lock" -type f -delete 2>/dev/null || true
        
        # Clean up temp directories
        find "${RUNNER_HOME}" -name "_temp" -type d -exec rm -rf {} \; 2>/dev/null || true
        
        log "✓ Runner state cleanup completed"
    fi
}

# Reset runner registration
reset_runner_registration() {
    log "Resetting runner registration..."
    
    if confirm_action "Remove runner registration and re-register"; then
        # Stop service first
        systemctl stop "$RUNNER_SERVICE" 2>/dev/null || true
        
        # Remove registration files
        local reg_files=(
            "${RUNNER_HOME}/.runner"
            "${RUNNER_HOME}/.credentials"
            "${RUNNER_HOME}/.credentials_rsaparams"
        )
        
        for file in "${reg_files[@]}"; do
            if [ -f "$file" ]; then
                log "Removing registration file: $file"
                rm -f "$file"
            fi
        done
        
        log "⚠️  Runner registration removed. Manual re-registration required."
        log "   Use the GitHub repository settings to generate a new token"
        log "   and run the configuration script again."
        
        log "✓ Runner registration reset completed"
    fi
}

# Emergency Docker cleanup
emergency_docker_cleanup() {
    log "Performing emergency Docker cleanup..."
    
    if ! command -v docker >/dev/null 2>&1; then
        log "Docker not found, skipping Docker cleanup"
        return 0
    fi
    
    if confirm_action "Perform aggressive Docker cleanup (removes all containers and images)"; then
        log "Stopping all running containers..."
        docker stop $(docker ps -q) 2>/dev/null || true
        
        log "Removing all containers..."
        docker rm $(docker ps -aq) 2>/dev/null || true
        
        log "Removing all images..."
        docker rmi $(docker images -q) -f 2>/dev/null || true
        
        log "Removing all volumes..."
        docker volume rm $(docker volume ls -q) 2>/dev/null || true
        
        log "Removing all networks..."
        docker network rm $(docker network ls -q) 2>/dev/null || true
        
        log "Performing system prune..."
        docker system prune -a -f --volumes 2>/dev/null || true
        
        log "✓ Emergency Docker cleanup completed"
    fi
}

# Clean up filesystem issues
cleanup_filesystem() {
    log "Performing emergency filesystem cleanup..."
    
    if confirm_action "Clean up disk space and filesystem issues"; then
        # Remove large temporary files
        log "Removing large temporary files..."
        find /tmp -type f -size +100M -delete 2>/dev/null || true
        find /var/tmp -type f -size +100M -delete 2>/dev/null || true
        
        # Clean up log files
        log "Truncating large log files..."
        find /var/log -name "*.log" -size +100M -exec truncate -s 10M {} \; 2>/dev/null || true
        
        # Clean up core dumps
        log "Removing core dumps..."
        find / -name "core.*" -type f -delete 2>/dev/null || true
        
        # Clean up package manager caches
        if command -v apt-get >/dev/null 2>&1; then
            apt-get clean 2>/dev/null || true
        fi
        
        if command -v yum >/dev/null 2>&1; then
            yum clean all 2>/dev/null || true
        fi
        
        log "✓ Filesystem cleanup completed"
    fi
}

# Restart all runner services
restart_runner_services() {
    log "Restarting runner services..."
    
    if confirm_action "Restart all runner-related services"; then
        # Stop service
        systemctl stop "$RUNNER_SERVICE" 2>/dev/null || true
        sleep 3
        
        # Kill any remaining processes
        pkill -f "Runner" || true
        sleep 2
        
        # Start service
        systemctl start "$RUNNER_SERVICE"
        sleep 5
        
        # Check status
        if systemctl is-active --quiet "$RUNNER_SERVICE"; then
            log "✓ Runner service restarted successfully"
        else
            log "✗ Failed to restart runner service"
            systemctl status "$RUNNER_SERVICE" || true
        fi
    fi
}

# Full emergency reset
full_emergency_reset() {
    log "=== PERFORMING FULL EMERGENCY RESET ==="
    
    if confirm_action "Perform FULL emergency reset (destructive operation)"; then
        emergency_stop_service
        cleanup_stuck_processes
        cleanup_runner_state
        emergency_docker_cleanup
        cleanup_filesystem
        reset_runner_registration
        
        log "=== FULL EMERGENCY RESET COMPLETED ==="
        log "⚠️  Manual intervention required:"
        log "   1. Re-register the runner with GitHub"
        log "   2. Restart the runner service"
        log "   3. Verify runner connectivity"
    fi
}

# Show current system status
show_status() {
    log "=== RUNNER SYSTEM STATUS ==="
    
    # Service status
    log "Service status:"
    systemctl status "$RUNNER_SERVICE" --no-pager || true
    
    # Process status
    log "Runner processes:"
    ps aux | grep -E "(Runner|actions)" | grep -v grep || log "No runner processes found"
    
    # Disk usage
    log "Disk usage:"
    df -h / || true
    
    # Memory usage
    log "Memory usage:"
    free -h || true
    
    # Docker status
    if command -v docker >/dev/null 2>&1; then
        log "Docker status:"
        docker system df 2>/dev/null || log "Docker system info not available"
    fi
    
    log "=== STATUS CHECK COMPLETED ==="
}

# Main script logic
main() {
    # Parse force flag
    if [[ "${*}" == *"--force"* ]]; then
        FORCE_MODE=true
        log "Force mode enabled - will skip confirmations"
    fi
    
    case "${1:-help}" in
        "stop")
            emergency_stop_service
            ;;
        "processes")
            cleanup_stuck_processes
            ;;
        "state")
            cleanup_runner_state
            ;;
        "registration")
            reset_runner_registration
            ;;
        "docker")
            emergency_docker_cleanup
            ;;
        "filesystem")
            cleanup_filesystem
            ;;
        "restart")
            restart_runner_services
            ;;
        "full")
            full_emergency_reset
            ;;
        "status")
            show_status
            ;;
        "help")
            echo "GitHub Actions Runner Emergency Cleanup Script"
            echo ""
            echo "Usage: $0 [COMMAND] [--force]"
            echo ""
            echo "Commands:"
            echo "  stop         - Emergency stop of runner service"
            echo "  processes    - Kill stuck processes"
            echo "  state        - Clean up corrupted runner state"
            echo "  registration - Reset runner registration"
            echo "  docker       - Emergency Docker cleanup"
            echo "  filesystem   - Clean up filesystem issues"
            echo "  restart      - Restart runner services"
            echo "  full         - Perform full emergency reset (destructive)"
            echo "  status       - Show current system status"
            echo "  help         - Show this help"
            echo ""
            echo "Options:"
            echo "  --force      - Skip confirmation prompts"
            echo ""
            echo "Examples:"
            echo "  $0 status                    # Check current status"
            echo "  $0 processes                 # Kill stuck processes"
            echo "  $0 full --force             # Full reset without prompts"
            ;;
        *)
            log "Unknown command: $1"
            echo "Use '$0 help' for usage information"
            exit 1
            ;;
    esac
}

# Execute main function with all arguments
main "$@"