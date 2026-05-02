# BenGer Infrastructure

Modern, secure, and clean Docker Compose setup for the BenGer legal technology platform following 2024 best practices.

## 📋 **Quick Summary of Modern Changes**

**🎯 What Was Rebuilt:**
- ✅ **Clean Traefik Routing**: All web services route through Traefik (no direct ports in production)
- ✅ **Security First**: HTTPS, security headers, rate limiting, CORS
- ✅ **Modern Docker**: Traefik v3.0, health checks, resource limits, multi-stage builds
- ✅ **Environment Separation**: Development vs Production configurations
- ✅ **Best Practices**: Read-only volumes, network segmentation, proper dependencies

**🌐 Access Points:**
- Frontend: `http://benger.localhost`
- API: `http://api.localhost` 
- Native Annotation: Integrated within frontend
- Traefik Dashboard: `http://traefik.localhost`

**⚡ Quick Commands:**
```bash
# Development (with hot reload)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Status
docker compose ps
```

## 🏗️ Architecture Overview

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Traefik       │    │    Frontend      │    │      API        │
│ (Load Balancer) │◄──►│   (React/Next)   │◄──►│   (FastAPI)     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │                       │
                                ▼                       ▼
                        ┌──────────────────┐    ┌─────────────────┐
                        │    PostgreSQL    │    │      Redis      │
                        │    (Database)    │    │   (Cache/MQ)    │
                        └──────────────────┘    └─────────────────┘
                                │                       │
                                └───────┬───────────────┘
                                        ▼
                                ┌─────────────────┐
                                │ Celery Workers  │
                                │  (Background)   │
                                └─────────────────┘
```

## 🚀 Quick Start

### Development Setup
```bash
# From the repo root, create env files from templates (one time)
bash scripts/bootstrap-env.sh

# Then bring up the stack
cd infra/
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# View logs
docker compose logs -f

# Stop all services
docker compose down
```

### Production Deployment
Production is deployed via Kubernetes / Helm — see `infra/helm/` and `docs/setup/deployment/DEPLOYMENT.md`. The Compose files in this directory are for local development only.

## 🌐 Service Access

### Development URLs (localhost)
- **Frontend Application**: http://benger.localhost
- **API Documentation**: http://api.localhost/docs
- **Native Annotation**: Integrated within frontend
- **Traefik Dashboard**: http://traefik.localhost

### Direct Access (Development Only)
- **PostgreSQL Database**: localhost:5432
- **Redis Cache**: localhost:6379

### Production URLs
- **Frontend**: https://${FRONTEND_DOMAIN}
- **API**: https://${API_DOMAIN}
- **Native Annotation**: Integrated within frontend

## 🔧 Configuration

### Environment Variables (.env)

**Required for all environments:**
```bash
# Database Configuration
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your-secure-password
POSTGRES_DB=benger

# Redis Configuration  
REDIS_PASSWORD=your-redis-password

# JWT Configuration
JWT_SECRET_KEY=your-32-character-minimum-secret-key
ACCESS_TOKEN_EXPIRE_MINUTES=60

# Native Annotation
ANNOTATION_WEBSOCKET_ENABLED=true
ANNOTATION_CACHE_TTL=3600

# Email (SendGrid — used by api + workers for transactional + notification mail)
SENDGRID_API_KEY=your-sendgrid-key
EMAIL_FROM_ADDRESS=noreply@what-a-benger.net
EMAIL_FROM_NAME=BenGER Platform
```

Production env (Helm / K8s) is managed under `infra/helm/benger/` — see the deployment guide.

### Docker Compose Files Structure
```
infra/
├── docker-compose.yml              # Base configuration (services + Traefik)
├── docker-compose.dev.yml          # Development overrides (hot reload)
├── docker-compose.local.yml        # Optional local routing tweaks
├── docker-compose.test.yml         # Isolated test stack
├── docker-compose.test.ci.yml      # CI override (use prebuilt images)
├── traefik/                        # Traefik config & TLS certs
├── redis/redis.conf                # Redis performance tuning
├── helm/                           # Production Kubernetes Helm charts
```

## 🔒 Security Features & Modern Standards

### ✅ **What's Been Modernized:**

**Network Security:**
- All web traffic routes through Traefik (single entry point)
- No direct port exposure in production
- Custom bridge network with subnet isolation
- TLS termination with automatic Let's Encrypt certificates

**Security Headers Pipeline:**
```
Request → Traefik → Security Headers → Rate Limiting → CORS → Compression → Service
```

**Applied Security Headers:**
- `X-Frame-Options: DENY` (Clickjacking protection)
- `X-XSS-Protection: 1; mode=block` (XSS protection)
- `X-Content-Type-Options: nosniff` (MIME sniffing protection)
- `Strict-Transport-Security` (HTTPS enforcement)
- `Content-Security-Policy` headers for XSS prevention

**Rate Limiting:**
- 50 requests/minute average, 100 burst per IP
- Applied to all public endpoints
- Configurable per service

**Container Security:**
- Read-only volumes where possible
- Resource limits for all containers
- Non-root users in containers
- Minimal attack surface with Alpine images

### 🔄 **Development vs Production Differences**

| Feature | Development | Production |
|---------|-------------|------------|
| **Port Exposure** | DB:5432, Redis:6379 | None (Traefik only) |
| **Dashboard** | Traefik dashboard enabled | Disabled |
| **TLS/SSL** | HTTP only | HTTPS with Let's Encrypt |
| **Replicas** | Single instance | Multiple replicas |
| **Volume Mounts** | Live code reloading | Read-only production images |
| **Logging** | INFO level | WARN level |
| **Resource Limits** | Minimal | Production-grade limits |

## 📊 Resource Management

### Container Limits (Production)
| Service | Memory Limit | CPU Limit | Replicas | Purpose |
|---------|--------------|-----------|----------|---------|
| **Frontend** | 512M | 0.25 | 2 | React/Next.js app |
| **API** | 1G | 0.5 | 2 | FastAPI backend |
| **Workers** | 1G | 0.5 | 3 | Celery background tasks |
| **Database** | 1G | 0.5 | 1 | PostgreSQL |
| **Redis** | 512M | 0.25 | 1 | Cache & message queue |
| **Native Annotation** | - | - | - | Integrated within frontend |
| **Traefik** | 256M | 0.1 | 1 | Load balancer |

### Storage Volumes
- `postgres-data`: Database persistence
- `redis-data`: Redis persistence with AOF
- `annotation-data`: Native annotation data (PostgreSQL)
- `api-uploads`: File uploads (development)
- `frontend-cache`: Next.js build cache (development)

## 🔄 Development Workflow

### Live Development Features
```bash
# Start with live reloading
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# View real-time logs
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f frontend
```

**Volume Mounts for Development:**
- `../services/api:/app` - Live API code reloading
- `../services/workers:/app` - Live worker code reloading  
- `../services/frontend:/app` - Live frontend reloading
- `/app/node_modules` - Anonymous volume for dependencies

### Database Development
```bash
# Connect with psql
psql -h localhost -p 5432 -U postgres -d benger

# Or use your favorite GUI tool:
# Host: localhost, Port: 5432, DB: benger, User: postgres
```

### Redis Development
```bash
# Connect with Redis CLI
redis-cli -h localhost -p 6379 -a "your-redis-password"

# Monitor Redis activity
redis-cli -h localhost -p 6379 -a "your-redis-password" monitor
```

## 🔍 Monitoring & Health Checks

### Service Health Monitoring
All services include comprehensive health checks:

```bash
# Check all service health
docker-compose ps

# Individual service health
docker-compose exec api curl -f http://localhost:8000/health
docker-compose exec frontend curl -f http://localhost:3000
```

### Health Check Endpoints
- **API**: `GET /health` - Application health & dependencies
- **Frontend**: `GET /` - Application availability
- **Native Annotation**: Integrated health checks within API
- **Database**: `pg_isready` - Connection health
- **Redis**: `redis-cli ping` - Cache availability
- **Traefik**: `traefik healthcheck --ping` - Proxy health

### Monitoring Access
- **Traefik Dashboard**: http://traefik.localhost (development)
- **Service Logs**: `docker-compose logs -f [service]`
- **Resource Usage**: `docker stats`

## 🔧 Advanced Configuration

### Traefik Middleware (traefik/config/dynamic.yml)

**Rate Limiting:**
```yaml
rate-limit:
  rateLimit:
    burst: 100
    average: 50
    period: 1m
```

**CORS Headers:**
```yaml
cors-headers:
  headers:
    accessControlAllowOriginList:
      - "http://benger.localhost"
      - "https://benger.localhost"
    accessControlAllowCredentials: true
```

**Compression:**
```yaml
gzip-compression:
  compress: {}
```

### Redis Configuration (redis/redis.conf)
- Memory limit: 256MB with LRU eviction
- Persistence: RDB snapshots + AOF logging
- Performance: Optimized timeouts and backlogs
- Security: Password protection, bind configuration

### Database Initialization
Place SQL scripts in `db/init/` for automatic execution:
```bash
db/init/
├── 01-create-extensions.sql
├── 02-create-users.sql
└── 03-initial-data.sql
```

## 🚨 Troubleshooting

### Common Issues & Solutions

**❌ Services not accessible via .localhost domains:**
```bash
# Add to /etc/hosts (Linux/Mac) or C:\Windows\System32\drivers\etc\hosts (Windows)
echo "127.0.0.1 benger.localhost api.localhost traefik.localhost" >> /etc/hosts
```

**❌ Port conflicts (development):**
```bash
# Check what's using ports
sudo lsof -i :80
sudo lsof -i :443
sudo lsof -i :5432
sudo lsof -i :6379

# Override ports in .env
DB_PORT=5433
REDIS_PORT=6380
```

**❌ Permission denied (Linux):**
```bash
# Fix Docker socket permissions
sudo chmod 666 /var/run/docker.sock

# Or add user to docker group
sudo usermod -aG docker $USER
```

**❌ SSL certificate issues (production):**
```bash
# Check certificate storage
ls -la traefik/certs/

# View Traefik logs
docker-compose logs -f traefik

# Verify domain DNS points to server
dig +short yourdomain.com
```

**❌ Memory issues:**
```bash
# Check container memory usage
docker stats

# Increase Docker Desktop memory allocation
# Or adjust container limits in production override
```

### Health Check Debugging
```bash
# Check specific service health
docker-compose exec db pg_isready -U postgres
docker-compose exec redis redis-cli ping
docker-compose exec api curl -f http://localhost:8000/health

# View health check logs
docker inspect infra-api-1 | grep -A 20 -B 5 Health
```

### Log Analysis
```bash
# Follow all logs
docker-compose logs -f

# Service-specific logs
docker-compose logs -f --tail=100 api
docker-compose logs -f --tail=100 worker

# Search logs for errors
docker-compose logs api 2>&1 | grep -i error
```

## 🔄 Maintenance & Updates

### Regular Updates
```bash
# Update container images
docker-compose pull

# Rebuild with latest dependencies
docker-compose build --no-cache

# Restart with new images
docker-compose up -d
```

### Database Operations
```bash
# Database migrations
docker-compose exec api python manage.py migrate

# Create new migration
docker-compose exec api python manage.py makemigrations

# Database backup
docker-compose exec db pg_dump -U postgres benger > backup.sql

# Database restore
docker-compose exec -T db psql -U postgres benger < backup.sql
```

### Scaling Services
```bash
# Scale workers (development)
docker-compose up -d --scale worker=3

# Scale in production (docker-compose.production.yml)
# Modify replicas value and restart
```

## 🌍 Production Deployment Guide

### Prerequisites
- Domain names with DNS pointing to your server
- Server with Docker & Docker Compose
- Firewall configured (ports 80, 443 open)
- Sufficient resources (4GB+ RAM recommended)

### Deployment Steps
1. **Configure DNS**: Point domains to your server IP
2. **Set environment variables**: Configure .env for production
3. **Start services**: Use production compose file
4. **Verify SSL**: Check certificate generation
5. **Monitor health**: Ensure all services are healthy

### Production Checklist
- [ ] Strong passwords for all services
- [ ] DNS records configured correctly
- [ ] Firewall allows only ports 80, 443
- [ ] SSL certificates generating automatically
- [ ] Health checks passing for all services
- [ ] Log rotation configured
- [ ] Backup strategy implemented
- [ ] Monitoring/alerting set up

### Security Hardening
```bash
# Production environment variables
ENVIRONMENT=production
DEBUG=false

# Use strong, unique passwords
POSTGRES_PASSWORD=$(openssl rand -base64 32)
REDIS_PASSWORD=$(openssl rand -base64 32)
JWT_SECRET_KEY=$(openssl rand -base64 48)
```

## 🤝 Contributing

### Development Setup for Contributors
```bash
# Fork and clone the repository
git clone https://github.com/yourusername/BenGer.git
cd BenGer/infra

# Start development environment
docker-compose -f docker-compose.yml -f docker-compose.development.yml up -d

# Make changes and test
# Submit pull request
```

### Infrastructure Changes
When modifying the infrastructure:

1. **Test locally** with development compose file
2. **Validate security** settings for production  
3. **Update documentation** for any new services/changes
4. **Test health checks** and resource limits
5. **Verify TLS/SSL** configuration works in production
6. **Update version tags** and changelog

### Code Quality
- All services must have health checks
- Resource limits required for production
- Security headers mandatory for public services
- Documentation must be updated with changes
- Tests should cover infrastructure changes

## 📋 Version History & Changelog

### v2.0.0 - Modern Infrastructure Rebuild (Current)
**🚀 Major Changes:**
- ✅ Upgraded to Traefik v3.0 (latest stable)
- ✅ All web services now route through Traefik (clean architecture)
- ✅ Removed direct port exposure for web services in production
- ✅ Added comprehensive security headers pipeline
- ✅ Implemented rate limiting on all public endpoints
- ✅ Added HTTPS/TLS with automatic Let's Encrypt certificates
- ✅ Separated development vs production configurations
- ✅ Added resource limits and health checks for all services
- ✅ Upgraded PostgreSQL to v15-alpine (from pgautoupgrade:13)
- ✅ Enhanced Redis configuration with security and performance tuning
- ✅ Added CORS middleware for proper cross-origin handling
- ✅ Implemented read-only volumes for production security
- ✅ Added comprehensive logging and monitoring
- ✅ Created proper network segmentation with custom bridge

**🔒 Security Improvements:**
- Security headers: HSTS, XSS protection, frame denial
- Password-protected Redis with configurable authentication
- No unnecessary port exposure in production
- TLS-only in production with automatic certificate renewal
- Rate limiting to prevent abuse
- Network isolation with custom subnet

**📦 Infrastructure Modernization:**
- BuildKit cache optimization for faster builds
- Multi-stage Dockerfiles with proper layer caching
- Health checks with proper start periods and retries
- Resource limits and reservations for all services
- Horizontal scaling support with multiple replicas
- Proper dependency ordering with health conditions

### v1.x.x - Legacy Setup
- Basic Docker Compose with mixed routing
- Direct port exposure for all services
- Manual SSL/TLS configuration
- Single environment configuration
- Basic health checks

---

## 📞 Support & Documentation

- **Technical Issues**: Create an issue in the repository
- **Infrastructure Questions**: Check this README first
- **Security Concerns**: Follow responsible disclosure
- **Feature Requests**: Submit detailed proposals

**Documentation Coverage:**
- ✅ Complete setup instructions
- ✅ Development workflow
- ✅ Production deployment
- ✅ Security configuration
- ✅ Troubleshooting guide
- ✅ Maintenance procedures

This infrastructure setup follows modern DevOps best practices for security, scalability, and maintainability. 🚀 