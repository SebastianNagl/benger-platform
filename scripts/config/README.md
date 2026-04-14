# Configuration Files Directory

This directory contains centralized configuration files for code quality and security tools used across the BenGER project.

## Files Overview

### `.bandit`
**Purpose**: Configuration for Bandit Python security linter
**Used by**: 
- GitHub Actions security workflow (`.github/workflows/security-scan.yml`)
- Pre-commit hooks (`scripts/config/.pre-commit-config.yaml`)
- Manual security scans

**Configuration**:
- Excludes test directories from security scans
- Skips specific test IDs (B101: assert_used, B601: paramiko_calls)
- Focuses on production security vulnerabilities

**Usage**:
```bash
# Manual scan
bandit -c scripts/config/.bandit -r services/api/

# Used automatically in CI/CD and pre-commit hooks
```

### `.jscpd.json`
**Purpose**: Configuration for JSCPD (JavaScript/TypeScript Code Duplication Detector)
**Used by**:
- GitHub Actions code quality workflow (`.github/workflows/code-quality.yml`)
- Code duplication analysis script (`scripts/maintenance/analyze-code-duplication.sh`)

**Configuration**:
- Duplication threshold: 10%
- Supports JavaScript, TypeScript, JSX, TSX, and Python
- Excludes build artifacts, tests, and dependencies
- Generates HTML, console, and JSON reports

**Usage**:
```bash
# Manual analysis
npx jscpd . --config scripts/config/.jscpd.json

# Used automatically in CI/CD and maintenance scripts
```

### `.pre-commit-config.yaml`
**Purpose**: Configuration for pre-commit hooks
**Used by**: Pre-commit framework when installed locally

**Hooks included**:
- **General**: File size checks, merge conflict detection, YAML/JSON validation
- **Security**: Secret detection with detect-secrets
- **Python**: Bandit security linter 
- **JavaScript/TypeScript**: ESLint code quality

**Setup**:
```bash
# Install pre-commit (one-time setup)
pip install pre-commit

# Install hooks in repository
pre-commit install --config scripts/config/.pre-commit-config.yaml

# Run manually on all files
pre-commit run --all-files --config scripts/config/.pre-commit-config.yaml
```

### `.secrets.baseline`
**Purpose**: Baseline file for detect-secrets tool
**Used by**: Pre-commit hooks and security scanning
**Content**: Contains known false positives to reduce noise in secret detection

**Update baseline**:
```bash
detect-secrets scan --baseline scripts/config/.secrets.baseline
```

## Integration Points

### GitHub Actions
The configuration files are automatically used by:
- **Security Scan Workflow**: Uses `.bandit` for Python security analysis
- **Code Quality Workflow**: Uses `.jscpd.json` for duplication detection

### Local Development
Developers can use these configurations by:
1. Installing pre-commit: `pip install pre-commit`
2. Setting up hooks: `pre-commit install --config scripts/config/.pre-commit-config.yaml`
3. Running analysis tools manually with the centralized configs

### CI/CD Scripts
Testing and maintenance scripts automatically reference these configurations:
- `scripts/testing/test-security-*.sh` - Validates configuration syntax
- `scripts/maintenance/analyze-code-duplication.sh` - Uses jscpd config

## Benefits of Centralization

1. **Consistency**: Same rules across all environments (local, CI/CD, manual)
2. **Maintainability**: Single point of configuration updates
3. **Documentation**: Clear ownership and purpose of each configuration
4. **Clean Root**: Keeps project root directory uncluttered
5. **Modularity**: Easy to disable/enable specific tools

## Updating Configurations

When updating these files:

1. **Test locally first**: Run the tools manually to ensure configuration works
2. **Update documentation**: Modify this README if behavior changes
3. **Validate in CI**: Check that GitHub Actions workflows pass
4. **Team notification**: Inform team of configuration changes that affect their workflow

## Troubleshooting

### Pre-commit hooks fail
```bash
# Check configuration syntax
pre-commit validate-config --config scripts/config/.pre-commit-config.yaml

# Skip specific hooks if needed
SKIP=bandit pre-commit run --all-files --config scripts/config/.pre-commit-config.yaml
```

### JSCPD analysis timeouts
- Check `ignore` patterns in `.jscpd.json`
- Ensure large directories (node_modules, .next) are excluded

### Bandit false positives
- Add test IDs to `skips` array in `.bandit`
- Use `# nosec` comments in code for specific lines (sparingly)

## Security Considerations

- **`.secrets.baseline`**: Review periodically to ensure no real secrets are baseline'd
- **`.bandit`**: Don't skip security tests without careful consideration
- **File permissions**: These configs don't contain secrets, but ensure they're versioned correctly