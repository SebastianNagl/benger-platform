# Environment Variables Reference

This document outlines all environment variables used in BenGER and their purpose across different environments.

## Frontend Environment Variables

### Required for Production
| Variable | Development Value | Production Value | Description |
|----------|------------------|------------------|-------------|
| `NEXT_PUBLIC_API_URL` | `http://api.localhost` | `https://api.what-a-benger.net` | API base URL for frontend requests |
| `NEXT_PUBLIC_ANNOTATION_SYSTEM` | `native` | `native` | Annotation system type (native) |

### Development Only
| Variable | Value | Description |
|----------|-------|-------------|
| `API_BASE_URL` | `http://localhost:8000` | Backend URL for API proxy |
| `NEXT_PRIVATE_LOCAL_WEBPACK` | `1` | Development optimization |
| `NEXT_PRIVATE_SKIP_SIZE_LIMIT_CHECK` | `1` | Skip bundle size checks |
| `WATCHPACK_POLLING` | `true` | Improve hot reloading |

## Backend Environment Variables

### Database Configuration
| Variable | Development Value | Production Value | Description |
|----------|------------------|------------------|-------------|
| `DATABASE_URI` | Auto-configured | From secrets | PostgreSQL connection string |
| `POSTGRES_HOST` | `db` | `db` | Database host |
| `POSTGRES_PORT` | `5432` | `5432` | Database port |
| `POSTGRES_USER` | `postgres` | From env | Database username |
| `POSTGRES_PASSWORD` | From env | From env | Database password |
| `POSTGRES_DB` | `benger` | `benger` | Database name |

### External Services
| Variable | Development Value | Production Value | Description |
|----------|------------------|------------------|-------------|
| `ANNOTATION_WEBSOCKET_ENABLED` | `true` | `true` | Enable WebSocket for real-time collaboration |
| `ANNOTATION_CACHE_TTL` | `3600` | `3600` | Cache TTL for annotation data |
| `REDIS_URL` | `redis://redis:6379/0` | From secrets | Redis connection string |

### Security
| Variable | Development Value | Production Value | Description |
|----------|------------------|------------------|-------------|
| `SECRET_KEY` | Auto-generated | From secrets | JWT signing key |
| `ENVIRONMENT` | `development` | `production` | Runtime environment |

## Workers Environment Variables

### Task Processing
| Variable | Development Value | Production Value | Description |
|----------|------------------|------------------|-------------|
| `CELERY_BROKER_URL` | `redis://redis:6379/0` | From env | Redis broker URL |
| `CELERY_RESULT_BACKEND` | `redis://redis:6379/0` | From env | Redis results backend |

### LLM API Keys
| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key for GPT models |
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude models |

## Environment-Aware Configuration

### Development (.env.local)
```bash
NEXT_PUBLIC_API_URL=http://api.localhost
API_BASE_URL=http://localhost:8000
```

### Production (Helm values.yaml)
```yaml
frontend:
  env:
    - name: NEXT_PUBLIC_API_URL
      value: "https://api.{{ .Values.global.domain }}"
```

### Production (Docker Compose)
```yaml
environment:
  - NEXT_PUBLIC_API_URL=https://api.${DOMAIN}
```

## CORS Configuration

### Development CORS Origins
- `http://benger.localhost`
- `http://localhost:3000`
- `http://127.0.0.1:3000`

### Production CORS Origins
Should be configured to match the actual production domains.

## Common Issues

### Native Annotation System
The native annotation system is automatically configured and requires no external routing:
1. Check `NEXT_PUBLIC_ANNOTATION_SYSTEM` is set to `native`
2. Verify WebSocket connections are enabled
3. Clear browser cache after changes

### API Connection Issues
If frontend can't connect to API:
1. Verify `NEXT_PUBLIC_API_URL` matches API domain
2. Check CORS configuration in backend
3. Ensure API is accessible from frontend container

### Environment Variable Priority
1. Build-time variables take precedence over runtime
2. Docker environment variables override .env files
3. Kubernetes secrets override configmap values

## Testing Environment Variables

For testing, use separate database and Redis instances:
```bash
REDIS_URL=redis://localhost:6379/1
DATABASE_URI=postgresql://user:pass@localhost/test_db
``` 