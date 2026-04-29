# BenGER Documentation

Welcome to the BenGER documentation! This guide will help you understand, use, and contribute to the BenGER project.

## 📚 Documentation Index

### Getting Started
- [**Quick Start Guide**](../README.md#-quick-start) - Get BenGER running in 5 minutes
- [**Installation Guide**](./setup/deployment/DEPLOYMENT_GUIDE.md) - Detailed setup instructions
- [**First Steps Tutorial**](./user-guides/README.md) - Your first annotation project

### User Documentation
- [**User Guide**](./user-guides/README.md) - Complete guide for annotators
- [**Admin Guide**](./user-guides/admin-guide.md) - Administration and management
- [**Organization Management**](./user-guides/organization-management.md) - Multi-tenant setup
- [**Data Import/Export**](./user-guides/data-import-export.md) - Working with data
- [**Data Formats**](./user-guides/data-formats.md) - Supported file formats
- [**Native Annotation System**](./user-guides/native-annotation-system.md) - Full annotation features

### Developer Documentation
- [**Development Setup**](./development/README.md) - Development environment
- [**Testing Guide**](./development/TESTING.md) - Complete testing documentation
- [**Migration Management**](./development/MIGRATION_MANAGEMENT.md) - Database migrations
- [**API Documentation**](./api-docs/README.md) - API reference

### Setup & Configuration
- [**Authentication Setup**](./setup/authentication.md) - Auth configuration
- [**Email Configuration**](./setup/email.md) - Email service setup
- [**GitHub Secrets**](./setup/GITHUB_SECRETS_SETUP.md) - CI/CD secrets
- [**Deployment Guide**](./setup/deployment/DEPLOYMENT_GUIDE.md) - Production deployment

### Troubleshooting
- [**Common Issues**](./TROUBLESHOOTING.md) - Troubleshooting guide
- [**Resource Errors**](./troubleshooting/err-insufficient-resources.md) - Memory issues

## 🚀 Quick Reference

### Common Commands
```bash
# Start development environment
docker-compose -f infra/docker-compose.yml up -d
cd services/frontend && npm run dev

# Run tests
./scripts/testing/run-tests-local.sh
pytest services/api/tests/ -v --cov=.
npm test --prefix services/frontend

# Database operations
cd services/api && alembic upgrade head  # Run migrations
cd services/api && alembic revision -m "description"  # Create migration

# Production deployment
./scripts/deployment/deploy-benger.sh
```

### Key Endpoints
- **Frontend**: `http://localhost:3000`
- **API**: `http://localhost:8000`
- **API Docs**: `http://localhost:8000/docs`
- **Database**: `localhost:5432`
- **Redis**: `localhost:6379`

### Environment Variables
Per-service env files live at `services/{api,workers,frontend}/.env(.local)`. Bootstrap them from the committed `.env.example` templates: `bash scripts/bootstrap-env.sh`. LLM provider API keys (OpenAI/Anthropic/Google/DeepInfra) are configured per-organization in the app UI — not in env files. See `docs/setup/environment-variables.md` for the full variable reference.

## 📂 Documentation Structure

```
docs/
├── README.md                    # This file - main index
├── user-guides/                 # End-user documentation
├── api-docs/                    # API reference
├── features/                    # Feature guides
├── setup/                       # Setup & deployment guides
├── development/                 # Developer guides
└── troubleshooting/             # Problem resolution
```

## 🔍 Finding Information

### By Role
- **Annotator**: Start with [User Guide](./user-guides/README.md)
- **Administrator**: See [Admin Guide](./user-guides/admin-guide.md)
- **Developer**: Check [Development Setup](./development/README.md) and [API Docs](./api-docs/README.md)
- **DevOps**: Read [Deployment Guide](./DEPLOYMENT_GUIDE.md)

### By Task
- **Set up development**: [Development Setup](./development/README.md)
- **Deploy to production**: [Deployment Guide](./DEPLOYMENT_GUIDE.md)
- **Import data**: [Data Import/Export](./user-guides/data-import-export.md)
- **Debug issues**: [Troubleshooting](./TROUBLESHOOTING.md)

## 📊 Documentation Coverage

| Section | Status | Last Updated |
|---------|--------|--------------|
| User Guides | ✅ Complete | August 2024 |
| API Reference | ✅ Complete | August 2024 |
| Deployment | ✅ Complete | August 2024 |
| Testing | 🔄 In Progress | August 2024 |

## 🤝 Contributing to Documentation

Found an issue or want to improve the docs?
- [Open an Issue](https://github.com/SebastianNagl/BenGER/issues)
- [Submit a PR](https://github.com/SebastianNagl/BenGER/pulls)
- [Ask Questions](https://github.com/SebastianNagl/BenGER/discussions)