# Runner Reliability Documentation

## Overview

This document outlines the performance requirements, monitoring, and reliability mechanisms for self-hosted GitHub Actions runners in the BenGER project.

## Performance Requirements

### Minimum System Requirements
- **CPU**: 4 cores minimum, 8+ cores recommended
- **RAM**: 8GB minimum, 16GB+ recommended  
- **Storage**: 50GB minimum free space
- **Network**: Stable internet connection with < 100ms latency to GitHub

### Performance Targets
- **Job startup time**: < 30 seconds from trigger to start
- **Build completion time**: < 10 minutes for typical builds
- **Uptime**: 99.5% availability target
- **Concurrent jobs**: Support for 2+ concurrent jobs

## Monitoring

### Health Checks
- Runner service status monitoring every 5 minutes
- System resource monitoring (CPU, RAM, disk)
- Network connectivity checks to GitHub
- Log rotation and cleanup monitoring

### Alerts
- High CPU usage (> 80% for 10+ minutes)
- Low disk space (< 10GB free)
- Runner disconnection from GitHub
- Failed job execution patterns

## Maintenance

### Daily Maintenance
- Docker container cleanup
- Log file rotation
- Temporary file cleanup
- System resource monitoring

### Weekly Maintenance
- Runner software updates
- System package updates
- Performance metrics review

### Emergency Procedures
- Runner emergency cleanup script
- Service restart procedures
- Failover to backup runners if available

## Reliability Mechanisms

### Service Management
- Systemd service configuration for auto-restart
- Graceful shutdown handling
- Job cancellation on service stop

### Resource Management
- Automatic cleanup of build artifacts
- Docker image pruning
- Temporary file management

### Backup & Recovery
- Configuration backup procedures
- Runner re-registration scripts
- System state recovery documentation

## Scripts

### Monitor Runners (`scripts/monitor-runners.sh`)
Monitors runner health and system resources.

### Automated Maintenance (`scripts/automated-maintenance.sh`)
Performs routine cleanup and maintenance tasks.

### Emergency Cleanup (`scripts/runner-emergency-cleanup.sh`)
Emergency cleanup procedures for stuck or problematic runners.

## Configuration

### Environment Variables
- `RUNNER_NAME`: Unique name for the runner instance
- `GITHUB_TOKEN`: Personal access token for runner registration
- `RUNNER_WORK_DIRECTORY`: Working directory for runner jobs

### Service Configuration
- Systemd service files for automatic startup
- User permissions and security settings
- Network and firewall configuration

## Troubleshooting

### Common Issues
1. **Runner offline**: Check network connectivity and GitHub token
2. **High resource usage**: Review active jobs and system load
3. **Disk space**: Run cleanup scripts and check log rotation
4. **Job failures**: Review runner logs and job output

### Log Locations
- Runner logs: `/var/log/github-actions-runner/`
- System logs: `/var/log/syslog`
- Application logs: Service-specific locations

## Security

### Best Practices
- Regular security updates
- Minimal privilege configuration
- Network security hardening
- Secure token management

### Access Control
- Restricted SSH access
- Service account permissions
- GitHub repository access controls