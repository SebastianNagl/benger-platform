# BenGER Configuration Management

This directory contains centralized configuration for all BenGER environments.

## Structure

```
config/
├── base.env                 # Common configuration (all environments)
├── development.env          # Development-specific overrides
├── staging.env             # Staging-specific overrides
├── production.env          # Production-specific overrides
├── secrets/                # Encrypted secrets (not in git)
│   ├── development.env.enc
│   ├── staging.env.enc
│   └── production.env.enc
└── README.md              # This file
```

## Usage

### Local Development
```bash
# Load configuration
export $(cat infra/config/base.env infra/config/development.env | grep -v '^#' | xargs)

# Or use the helper script
source scripts/core/load-env.sh development
```

### Docker Compose
```yaml
# docker-compose.yml
services:
  api:
    env_file:
      - ./infra/config/base.env
      - ./infra/config/${ENVIRONMENT:-development}.env
```

### Production Deployment
Configuration is loaded from Kubernetes ConfigMaps and Secrets.

## Configuration Hierarchy

1. **Base configuration** (base.env) - Common settings
2. **Environment overrides** (development.env, etc.) - Environment-specific
3. **Local overrides** (.env.local) - Personal developer settings (gitignored)
4. **Runtime overrides** - Environment variables

Later values override earlier ones.

## Adding New Configuration

1. Add to `base.env` if it's common to all environments
2. Add to specific environment files for overrides
3. Document in the configuration schema below
4. Update validation in `scripts/core/validate-config.sh`

## Configuration Schema

### Application Settings
- `APP_NAME` - Application name (default: BenGER)
- `APP_VERSION` - Application version
- `ENVIRONMENT` - Current environment (development/staging/production)
- `DEBUG` - Debug mode (true/false)

### Database Configuration
- `POSTGRES_HOST` - PostgreSQL host
- `POSTGRES_PORT` - PostgreSQL port (default: 5432)
- `POSTGRES_DB` - Database name
- `POSTGRES_USER` - Database user
- `POSTGRES_PASSWORD` - Database password (use secrets)
- `DATABASE_URL` - Full connection string (generated)

### Redis Configuration
- `REDIS_HOST` - Redis host
- `REDIS_PORT` - Redis port (default: 6379)
- `REDIS_PASSWORD` - Redis password (optional)
- `REDIS_URL` - Full connection string (generated)

### Authentication
- `JWT_SECRET_KEY` - JWT signing key (use secrets)
- `JWT_ALGORITHM` - JWT algorithm (default: HS256)
- `JWT_EXPIRATION_HOURS` - Token expiration (default: 24)

### API Keys (use secrets)
- `OPENAI_API_KEY` - OpenAI API key
- `ANTHROPIC_API_KEY` - Anthropic API key
- `GOOGLE_API_KEY` - Google API key
- `DEEPINFRA_API_KEY` - DeepInfra API key

### Native Annotation System
BenGER now uses a native annotation system. No external annotation service configuration required.

### Email Configuration
- `EMAIL_ENABLED` - Enable email sending (true/false)
- `SMTP_HOST` - SMTP server host
- `SMTP_PORT` - SMTP server port
- `SMTP_USER` - SMTP username
- `SMTP_PASSWORD` - SMTP password (use secrets)

## Security

### Secrets Management
- Never commit secrets to git
- Use encrypted files or external secret managers
- Rotate secrets regularly
- Use different secrets per environment

### Best Practices
1. Use strong, unique passwords
2. Rotate API keys quarterly
3. Audit configuration access
4. Use least privilege principle

## Validation

Run configuration validation:
```bash
./scripts/core/validate-config.sh development
```

This checks:
- Required variables are set
- Values are in valid format
- No secrets in plain text
- Environment consistency