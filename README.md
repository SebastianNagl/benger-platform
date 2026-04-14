# BenGER (Benchmark for German Law) - Benchmarking Platform for Legal NLP

[![CI/CD Status](https://github.com/SebastianNagl/BenGER/workflows/CI%2FCD/badge.svg)](https://github.com/SebastianNagl/BenGER/actions)
[![License: CC BY 4.0](https://img.shields.io/badge/License-CC_BY_4.0-lightgrey.svg)](https://creativecommons.org/licenses/by/4.0/)

## What is BenGER?

BenGER is an open-source web platform for end-to-end benchmarking of Large Language Models in the German legal domain. It integrates task creation, collaborative annotation, configurable LLM execution, and evaluation with lexical, semantic, factual, and judge-based metrics into a single browser-based workflow.

A public instance is available at [what-a-benger.net](https://what-a-benger.net).

Key capabilities:

- **Task Creation**: Legal experts define tasks and reference solutions directly in the platform
- **Collaborative Annotation**: Multi-format support (free-text QA, multiple choice, span annotation) with inter-annotator agreement metrics and quality control workflows
- **LLM Execution**: Batch execution across multiple providers (OpenAI, Anthropic, Google, Mistral, Cohere, DeepInfra, Zhipu AI)
- **Evaluation**: 40+ metrics spanning classification, lexical, semantic, factual, and LLM-as-a-judge categories, all with academic citations
- **Multi-Organization Support**: Tenant isolation, role-based access control (Admin, Contributor, Annotator), and invitation-based onboarding
- **Formative Feedback**: Optional LLM-based feedback comparing annotator answers to reference solutions

Developed at the Technical University of Munich for legal NLP research.

## Quick Start

```bash
# Clone the repository
git clone https://github.com/SebastianNagl/BenGER.git
cd BenGER

# Start with Docker Compose
cd infra/
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Seed initial data (admin/admin, contributor/admin, annotator/admin)
docker-compose exec api python init_complete.py

# Access the application
# Frontend: http://benger.localhost
# API Docs: http://api.localhost/docs
```

## Project Structure

```
BenGER/
├── services/
│   ├── frontend/           # Next.js 15 web application
│   │   ├── src/app/        # App Router pages
│   │   ├── src/components/ # React components
│   │   ├── src/hooks/      # Custom hooks
│   │   └── src/lib/        # Utilities and API client
│   ├── api/                # FastAPI backend service
│   │   ├── routers/        # API endpoints (projects, evaluations, etc.)
│   │   ├── app/api/v1/     # Versioned routes (auth, orgs, invitations)
│   │   └── alembic/        # Database migrations
│   ├── workers/            # Celery background workers
│   │   └── ml_evaluation/  # Evaluation metrics (40+ implementations)
│   └── shared/             # Shared utilities
├── infra/                  # Infrastructure configuration
│   ├── docker-compose*.yml # Multiple compose configs (dev, test, staging)
│   ├── helm/               # Kubernetes Helm charts
│   └── traefik/            # Reverse proxy configuration
├── scripts/                # Automation, deployment, maintenance scripts
├── publications/           # Academic manuscripts
├── docs/                   # Documentation
│   ├── architecture/       # ADRs and system design
│   ├── user-guides/        # User documentation
│   ├── api-docs/           # API documentation
│   ├── setup/              # Setup and deployment guides
│   └── operations/         # Operations and maintenance
└── .github/workflows/      # CI/CD pipelines
```

## Technology Stack

### Frontend
- **Framework**: Next.js 15 with App Router and Turbopack
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **State**: Zustand + TanStack Query
- **UI Components**: Headless UI, Heroicons, Lucide React
- **Charts**: Recharts, Plotly.js

### Backend
- **Framework**: FastAPI (Python 3.10+)
- **Database**: PostgreSQL 15 with SQLAlchemy ORM
- **Cache/Queue**: Redis with Celery
- **Auth**: JWT with role-based access control
- **Migrations**: Alembic

### ML / Evaluation
- **Deep Learning**: PyTorch, Transformers, Sentence-Transformers
- **Metrics**: BERTScore, SacreBLEU, ROUGE, METEOR, MoverScore, and more
- **LLM Judge**: GPT-4 and Claude-based evaluation

### Infrastructure
- **Containerization**: Docker and Docker Compose
- **Orchestration**: Kubernetes (k3s) with Helm
- **Reverse Proxy**: Traefik v3
- **CI/CD**: GitHub Actions with self-hosted runners

## Development Setup

### Prerequisites
- Docker and Docker Compose
- Node.js 20+ (for local frontend development)
- Python 3.10+ (for local API development)

### Docker Development (Recommended)

```bash
cd infra/
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Initialize the database with seed data
docker-compose exec api python init_complete.py
```

Access at `http://benger.localhost`. Development mode enables auto-authentication.

### Local Development (Without Docker)

1. **Start infrastructure services**
```bash
cd infra/
docker-compose -f docker-compose.yml up -d postgres redis
```

2. **Set up the API**
```bash
cd services/api
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python main.py
```

3. **Set up the frontend**
```bash
cd services/frontend
npm install
npm run dev
```

## Testing

BenGER uses isolated Docker containers for all tests to avoid conflicts with development.

```bash
# Full test suite (start, seed, test, stop, cleanup)
make test

# Individual suites (requires `make test-start` first)
make test-unit       # API + Workers + Frontend Jest
make test-e2e        # Playwright E2E tests
make test-api        # API tests only
make test-workers    # Worker tests only
make test-frontend   # Frontend Jest only

# Test infrastructure management
make test-start      # Start test containers
make test-stop       # Stop and cleanup
make test-status     # Health check
```

Test ports (isolated from dev): PostgreSQL 5433, Redis 6380, API 8002, Frontend 8090.

## Deployment

### Kubernetes (Production)

```bash
helm install benger ./infra/helm/benger -n benger --create-namespace
```

### CI/CD

GitHub Actions workflows:
- **cicd.yml**: Main pipeline (PR validation, tests, Docker builds, Kubernetes deployment)
- **staging-deploy.yml**: Staging environment deployments
- **pr-staging-cleanup.yml**: Staging environment cleanup on PR close
- **dependabot-auto-merge.yml**: Auto-merge dependency updates

Deployments run on self-hosted runners directly on the production server.

## Documentation

- [User Guide](docs/user-guides/README.md)
- [Admin Guide](docs/user-guides/admin-guide.md)
- [Developer Authentication](docs/setup/developer-auth.md)
- [Environment Variables](docs/setup/environment-variables.md)
- [Deployment Guide](docs/setup/deployment/DEPLOYMENT_GUIDE.md)
- [Testing Guide](docs/development/TESTING.md)
- [Feature Flags](docs/setup/feature-flags.md)
- [Documentation Index](docs/README.md)

## License

This project is licensed under the Creative Commons Attribution 4.0 International License (CC BY 4.0) - see the [LICENSE](LICENSE) file for details.

## Academic Publication

If you use BenGER in your research, please cite:

```bibtex
@inproceedings{nagl2026benger,
  title={{BenGER}: A Collaborative Web Platform for End-to-End Benchmarking of German Legal Tasks},
  author={Nagl, Sebastian and Grabmair, Matthias},
  booktitle={Proceedings of the International Conference on Artificial Intelligence and Law (ICAIL)},
  year={2026},
  address={Singapore}
}
```

## Acknowledgments

- Technical University of Munich for supporting this research
- Label Studio for annotation system UI/UX inspiration

## Contact

- **Issues**: [GitHub Issues](https://github.com/SebastianNagl/BenGER/issues)
- **Email**: [sebastian.nagl@tum.de](mailto:sebastian.nagl@tum.de)
