# BenGER Scripts

This directory contains essential automation scripts for the BenGER platform.

## 📁 Directory Structure

### `testing/`
Essential testing and code quality scripts for development:
- **`quick-test.sh`** - Fast syntax and import checks for development
- **`run-tests-local.sh`** - Comprehensive local testing suite (unit, integration, frontend)
- **`format-code.sh`** - Code formatting with black, isort, autoflake for Python and prettier for frontend

### `deployment/`
Production deployment and infrastructure setup:
- **`deploy-benger.sh`** - Main production deployment script (Kubernetes with Helm)
- **`server-setup.sh`** - Initial server setup (k3s, Docker, kubectl, Helm)
- **`validate-deployment.sh`** - Comprehensive deployment validation with multiple test types
- **`setup-github-cicd.sh`** - GitHub Actions setup helper with SSH keys and secrets

### `maintenance/`
System monitoring, maintenance, and operational scripts:
- **`health-check.sh`** - System health monitoring for all components
- **`backup.sh`** - Database and application data backup system
- **`automated-maintenance.sh`** - Scheduled maintenance (Docker cleanup, log rotation, resource monitoring)
- **`monitor-runners.sh`** - Runner monitoring and reliability checks

### `core/`
System service definitions and core configurations:
- **`benger-maintenance.service`** - Systemd service file for maintenance
- **`benger-maintenance.timer`** - Systemd timer for maintenance scheduling
- **`runner-monitor.service`** - Systemd service for runner monitoring

## 🚀 Common Usage

### Development
```bash
# Quick development checks
./testing/quick-test.sh

# Full local test suite
./testing/run-tests-local.sh

# Format all code
./testing/format-code.sh
```

### Deployment
```bash
# Initial server setup
./deployment/server-setup.sh

# Deploy to production
./deployment/deploy-benger.sh

# Validate deployment
./deployment/validate-deployment.sh
```

### Maintenance
```bash
# Check system health
./maintenance/health-check.sh

# Create backup
./maintenance/backup.sh

# Monitor runners
./maintenance/monitor-runners.sh
```

## 📝 Notes

- All scripts are designed to be run from the repository root directory
- Scripts require appropriate permissions and may need to be made executable: `chmod +x script-name.sh`
- Production scripts should be run with caution and proper access credentials
- For detailed usage of individual scripts, check the script headers for documentation

---

*This consolidated scripts directory contains only actively maintained automation tools for the current BenGER platform.*