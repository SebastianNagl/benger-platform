#!/bin/bash
#
# Automated Maintenance Script for GitHub Actions Runners
# Performs routine cleanup and maintenance tasks
#

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="/var/log/github-actions-runner/maintenance.log"
BACKUP_DIR="/var/backups/github-actions-runner"
MAX_LOG_SIZE_MB=100
MAX_LOG_AGE_DAYS=30
DOCKER_CLEANUP_THRESHOLD_GB=5

# Ensure log and backup directories exist
mkdir -p "$(dirname "$LOG_FILE")" "$BACKUP_DIR"

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# Check if running as correct user
check_permissions() {
    if [ "$EUID" -eq 0 ]; then
        log "Warning: Running as root. Some operations may need different permissions."
    fi
}

# Clean up old log files
cleanup_logs() {
    log "Starting log cleanup..."
    
    # Rotate current log if it's too large
    if [ -f "$LOG_FILE" ]; then
        LOG_SIZE=$(du -m "$LOG_FILE" | cut -f1)
        if [ "$LOG_SIZE" -gt "$MAX_LOG_SIZE_MB" ]; then
            log "Rotating large log file (${LOG_SIZE}MB)"
            mv "$LOG_FILE" "${LOG_FILE}.$(date +%Y%m%d_%H%M%S)"
        fi
    fi
    
    # Remove old log files
    find "$(dirname "$LOG_FILE")" -name "*.log*" -type f -mtime +${MAX_LOG_AGE_DAYS} -delete 2>/dev/null || true
    
    # Clean up runner diagnostic logs
    if [ -d "/opt/actions-runner/_diag" ]; then
        find "/opt/actions-runner/_diag" -name "*.log" -type f -mtime +7 -delete 2>/dev/null || true
    fi
    
    log "✓ Log cleanup completed"
}

# Clean up temporary files
cleanup_temp_files() {
    log "Starting temporary file cleanup..."
    
    # Clean up common temp directories
    local temp_dirs=(
        "/tmp"
        "/var/tmp"
        "/opt/actions-runner/_work/_temp"
    )
    
    for temp_dir in "${temp_dirs[@]}"; do
        if [ -d "$temp_dir" ]; then
            # Remove files older than 1 day
            find "$temp_dir" -type f -mtime +1 -delete 2>/dev/null || true
            # Remove empty directories
            find "$temp_dir" -type d -empty -delete 2>/dev/null || true
        fi
    done
    
    log "✓ Temporary file cleanup completed"
}

# Docker cleanup
cleanup_docker() {
    log "Starting Docker cleanup..."
    
    # Check if Docker is available
    if ! command -v docker >/dev/null 2>&1; then
        log "Docker not found, skipping Docker cleanup"
        return 0
    fi
    
    # Check available disk space
    AVAILABLE_GB=$(df / | tail -1 | awk '{print int($4/1024/1024)}')
    
    if [ "$AVAILABLE_GB" -lt "$DOCKER_CLEANUP_THRESHOLD_GB" ]; then
        log "Low disk space detected (${AVAILABLE_GB}GB), performing aggressive Docker cleanup"
        
        # Remove stopped containers
        docker container prune -f 2>/dev/null || true
        
        # Remove unused images
        docker image prune -f 2>/dev/null || true
        
        # Remove unused volumes
        docker volume prune -f 2>/dev/null || true
        
        # Remove unused networks
        docker network prune -f 2>/dev/null || true
        
        # If still low on space, remove all unused data
        if [ "$AVAILABLE_GB" -lt 2 ]; then
            log "Still low on space, performing system prune"
            docker system prune -a -f 2>/dev/null || true
        fi
    else
        log "Sufficient disk space (${AVAILABLE_GB}GB), performing light Docker cleanup"
        
        # Only remove stopped containers and dangling images
        docker container prune -f 2>/dev/null || true
        docker image prune -f 2>/dev/null || true
    fi
    
    log "✓ Docker cleanup completed"
}

# Clean up runner work directories
cleanup_runner_work() {
    log "Starting runner work directory cleanup..."
    
    local work_dirs=(
        "/opt/actions-runner/_work"
        "/home/runner/actions-runner/_work"
    )
    
    for work_dir in "${work_dirs[@]}"; do
        if [ -d "$work_dir" ]; then
            # Remove old build artifacts (older than 3 days)
            find "$work_dir" -type f -mtime +3 -delete 2>/dev/null || true
            
            # Remove empty directories
            find "$work_dir" -type d -empty -delete 2>/dev/null || true
            
            log "Cleaned work directory: $work_dir"
        fi
    done
    
    log "✓ Runner work directory cleanup completed"
}

# System resource monitoring
monitor_system_resources() {
    log "Monitoring system resources..."
    
    # CPU usage
    CPU_USAGE=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1)
    log "Current CPU usage: ${CPU_USAGE}%"
    
    # Memory usage
    MEMORY_USAGE=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}')
    log "Current memory usage: ${MEMORY_USAGE}%"
    
    # Disk usage
    DISK_USAGE=$(df / | tail -1 | awk '{print $5}')
    log "Current disk usage: ${DISK_USAGE}"
    
    # Load average
    LOAD_AVG=$(uptime | awk -F'load average:' '{print $2}')
    log "Load average:${LOAD_AVG}"
    
    log "✓ System resource monitoring completed"
}

# Backup critical configurations
backup_configurations() {
    log "Starting configuration backup..."
    
    local config_files=(
        "/etc/systemd/system/actions-runner*.service"
        "/opt/actions-runner/.runner"
        "/opt/actions-runner/.credentials"
    )
    
    BACKUP_TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_PATH="${BACKUP_DIR}/config_${BACKUP_TIMESTAMP}"
    
    mkdir -p "$BACKUP_PATH"
    
    for config_pattern in "${config_files[@]}"; do
        # Use shell globbing safely
        for config_file in $config_pattern; do
            if [ -f "$config_file" ]; then
                cp "$config_file" "$BACKUP_PATH/" 2>/dev/null || true
                log "Backed up: $config_file"
            fi
        done
    done
    
    # Remove old backups (keep last 7 days)
    find "$BACKUP_DIR" -type d -name "config_*" -mtime +7 -exec rm -rf {} \; 2>/dev/null || true
    
    log "✓ Configuration backup completed"
}

# Health check integration
run_health_check() {
    log "Running integrated health check..."
    
    if [ -f "${SCRIPT_DIR}/monitor-runners.sh" ]; then
        bash "${SCRIPT_DIR}/monitor-runners.sh" check
    else
        log "Monitor script not found, skipping health check"
    fi
}

# Main maintenance routine
run_maintenance() {
    log "=== Starting automated maintenance ==="
    
    check_permissions
    cleanup_logs
    cleanup_temp_files
    cleanup_docker
    cleanup_runner_work
    monitor_system_resources
    backup_configurations
    run_health_check
    
    log "=== Automated maintenance completed ==="
}

# Dry run mode for testing
run_dry_run() {
    log "=== Running maintenance in DRY RUN mode ==="
    log "This would perform the following operations:"
    log "1. Clean up log files older than ${MAX_LOG_AGE_DAYS} days"
    log "2. Remove temporary files older than 1 day"
    log "3. Clean up Docker containers and images"
    log "4. Clean up runner work directories"
    log "5. Monitor system resources"
    log "6. Backup critical configurations"
    log "7. Run health check"
    log "=== Dry run completed ==="
}

# Main script logic
main() {
    case "${1:-run}" in
        "run")
            run_maintenance
            ;;
        "dry-run")
            run_dry_run
            ;;
        "logs")
            cleanup_logs
            ;;
        "docker")
            cleanup_docker
            ;;
        "temp")
            cleanup_temp_files
            ;;
        "help")
            echo "Usage: $0 [run|dry-run|logs|docker|temp|help]"
            echo "  run     - Run full maintenance routine (default)"
            echo "  dry-run - Show what would be done without executing"
            echo "  logs    - Only clean up log files"
            echo "  docker  - Only perform Docker cleanup"
            echo "  temp    - Only clean up temporary files"
            echo "  help    - Show this help"
            ;;
        *)
            log "Unknown command: $1"
            exit 1
            ;;
    esac
}

# Execute main function with all arguments
main "$@"