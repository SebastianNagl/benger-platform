# Development Guide

This guide covers local development setup, development workflows, and best practices for contributing to BenGER.

## 🚀 Quick Start

### Prerequisites
- **Docker & Docker Compose** (recommended)
- **Node.js 18+** (for frontend development)
- **Python 3.9+** (for backend development)
- **Git**

### Local Development Setup

#### Option 1: Full Docker Setup (Recommended)
```bash
# Clone the repository
git clone https://github.com/tum-legal-tech/benger.git
cd benger

# Start all services
docker-compose up -d

# Access applications
# BenGER Platform: http://localhost:3000
# API: http://localhost:8001
```

#### Option 2: Hybrid Development
For faster frontend development with hot reload:

```bash
# Start backend services with Docker  
docker-compose up -d db redis api

# Run frontend locally
cd services/frontend
npm install
npm run dev

# Frontend: http://localhost:3000
# API: http://localhost:8001
```

#### Option 3: Full Local Development
```bash
# Database (PostgreSQL)
docker run -d \
  --name benger-db \
  -e POSTGRES_DB=postgres \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=changeme \
  -p 5432:5432 \
  postgres:15

# Redis
docker run -d \
  --name benger-redis \
  -p 6379:6379 \
  redis:7-alpine

# Backend API
cd services/api
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8001

# Frontend
cd services/frontend
npm install
npm run dev

# Native Annotation System - already integrated with BenGER
```

## 🛠️ Development Workflow

### Branch Strategy
```bash
# Create feature branch
git checkout -b feature/your-feature-name

# Make changes and commit
git add .
git commit -m "feat: add new feature"

# Push and create PR
git push origin feature/your-feature-name
```

### Code Quality
```bash
# Frontend linting and formatting
cd services/frontend
npm run lint
npm run format

# Backend linting
cd services/api
black .
flake8 .
mypy .

# Run tests
npm test          # Frontend tests
pytest           # Backend tests
```

### Database Migrations
```bash
# Create new migration
alembic revision -m "description"

# Run migrations
alembic upgrade head

# Reset database (development only)
docker-compose down -v
docker-compose up -d
```

## 📁 Project Structure

```
benger/
├── services/
│   ├── frontend/          # Next.js frontend
│   │   ├── src/
│   │   │   ├── app/       # App router pages
│   │   │   │   ├── components/ # Reusable components
│   │   │   │   ├── lib/       # Utilities and API
│   │   │   │   └── types/     # TypeScript types
│   │   │   ├── public/        # Static assets
│   │   │   └── package.json
│   │   ├── api/               # FastAPI backend
│   │   │   ├── main.py        # API endpoints
│   │   │   ├── models.py      # Database models
│   │   │   ├── auth.py        # Authentication
│   │   │   ├── database.py    # Database connection
│   │   │   └── requirements.txt
│   │   └── evaluation/        # Evaluation workers
│   │       ├── worker.py      # Celery workers
│   │       └── tasks.py       # Evaluation tasks
│   ├── docs/                  # Documentation
│   │   ├── api/              # API documentation
│   │   ├── user-guides/      # User documentation
│   │   └── development/      # Development guides
│   ├── infra/                # Infrastructure
│   │   ├── helm/             # Kubernetes charts
│   │   ├── docker/           # Docker configurations
│   │   └── scripts/          # Deployment scripts
│   ├── docker-compose.yml    # Local development
│   └── README.md
```

## 🔧 Environment Configuration

### Backend (.env)
```bash
# Database
DATABASE_URL=postgresql://postgres:changeme@localhost:5432/postgres

# Redis
REDIS_URL=redis://localhost:6379/0

# Native Annotation System - integrated into BenGER

# JWT
SECRET_KEY=your_secret_key
ACCESS_TOKEN_EXPIRE_MINUTES=30

# OpenAI (for evaluations)
OPENAI_API_KEY=your_openai_key
```

### Frontend (.env.local)
```bash
NEXT_PUBLIC_API_URL=http://localhost:8000/api
```

## 🧪 Testing

BenGER uses isolated Docker containers for all tests. See [TESTING.md](./TESTING.md) for the full guide.

```bash
# Full test suite
make test

# Individual suites (requires `make test-start` first)
make test-api          # API tests
make test-workers      # Worker tests
make test-frontend     # Frontend Jest tests
make test-e2e          # Playwright E2E tests

# Targeted runs
make test-api GREP="bulk_export"
make test-e2e FILE="e2e/user-journeys/login.spec.ts"

# Infrastructure
make test-start        # Start test containers
make test-build        # Rebuild changed images, then start
make test-stop         # Stop and cleanup
```

### API Testing
```bash
# Start services
docker-compose up -d

# Test endpoints
curl -X GET http://localhost:8001/api/tasks
curl -X POST http://localhost:8001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin"}'
```

## 🎨 Code Style Guidelines

### TypeScript/React
- Use TypeScript strict mode
- Prefer functional components with hooks
- Use Tailwind CSS for styling
- Follow Next.js conventions
- Use absolute imports (`@/components/...`)

### Python
- Follow PEP 8 style guide
- Use type hints
- Prefer async/await for I/O operations
- Use Pydantic for data validation
- Follow FastAPI patterns

### General
- Write descriptive commit messages
- Add JSDoc/docstrings for complex functions
- Use meaningful variable names
- Keep functions small and focused
- Write tests for new features

## 🐛 Debugging

### Frontend Debugging
```bash
# Enable debug mode
NEXT_PUBLIC_DEBUG=true npm run dev

# Browser dev tools
# - React Developer Tools
# - Redux DevTools (if applicable)

# API calls debugging
# Check Network tab in browser dev tools
```

### Backend Debugging
```bash
# Enable debug logging
LOG_LEVEL=DEBUG uvicorn main:app --reload

# Database queries
# Add logging to see SQL queries
echo 'SQLALCHEMY_LOG_LEVEL=INFO' >> .env

# API debugging
# Use FastAPI automatic docs: http://localhost:8001/docs
```

### Docker Debugging
```bash
# View logs
docker-compose logs api
docker-compose logs frontend

# Access container shell
docker exec -it benger-api bash
docker exec -it benger-frontend sh

# Restart specific service
docker-compose restart api
```

## 📊 Performance Monitoring

### Local Development
```bash
# Frontend performance
npm run analyze  # Bundle analyzer

# Backend performance
pip install py-spy
py-spy record -o profile.svg -- python -m uvicorn main:app

# Database performance
# Enable query logging in PostgreSQL
# Monitor slow queries
```

### Profiling
```bash
# Python profiling
python -m cProfile -o profile.prof main.py
snakeviz profile.prof

# Node.js profiling
node --prof app.js
node --prof-process isolate-*.log > processed.txt
```

## 🚀 Deployment Testing

### Local Kubernetes
```bash
# Install k3s or minikube
# Deploy with Helm
helm install benger ./infra/helm/benger

# Test deployment
kubectl get pods
kubectl logs deployment/benger-api
```

### Docker Build Testing
```bash
# Build images locally
docker build -t benger-api ./services/api
docker build -t benger-frontend ./services/frontend

# Test built images
docker run -p 8001:8001 benger-api
docker run -p 3000:3000 benger-frontend
```

## 📚 Additional Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Next.js Documentation](https://nextjs.org/docs)
- [Native Annotation System Documentation](../native-annotation-system.md)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Docker Documentation](https://docs.docker.com/)

## 🤝 Getting Help

- Check existing [GitHub Issues](https://github.com/tum-legal-tech/benger/issues)
- Create new issue with reproduction steps
- Use discussions for questions
- Check documentation in `docs/` folder 