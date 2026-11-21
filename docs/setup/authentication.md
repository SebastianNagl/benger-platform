# Authentication Configuration Guide

## Overview
BenGER's authentication system is controlled by the `ENVIRONMENT` variable. When set to `development`, certain authentication checks may be bypassed for local development. **Production and staging environments MUST have proper environment settings to ensure authentication is enforced.**

## Current Configuration

### Production Environment (namespace: benger)
- **ENVIRONMENT**: `production`
- **Authentication**: FULLY ENABLED
- **URL**: https://example.com
- **API**: https://api.example.com

### Staging Environment (namespace: benger-staging)  
- **ENVIRONMENT**: `staging`
- **Authentication**: FULLY ENABLED
- **URL**: https://staging.example.com
- **API**: https://api.staging.example.com

## Important Security Notes

### 1. Environment Variable Setting
The `ENVIRONMENT` variable controls authentication behavior:
- `production` - Full authentication required
- `staging` - Full authentication required
- `development` - May have relaxed authentication for local development

### 2. Cookie Security
When `ENVIRONMENT=production`:
- Cookies are set with `secure=True` (HTTPS only)
- Cookies use `httponly=True` (no JavaScript access)
- Cookies have proper `samesite` settings

When `ENVIRONMENT=development`:
- Cookies may work over HTTP for localhost development
- Less restrictive CORS settings

### 3. Rate Limiting
- Login, token and password-reset requests are limited per account and per IP (`services/api/services/auth_rate_limit.py`).
- Requests with a script token from `POST /api/auth/token` are limited per user to `BEARER_TOKEN_RPM` (default 1200 per minute); browser sessions are not. Access keys have their own per-key limits. See [Limits](../full-api.md#limits-and-good-practice) and [Abuse limits](environment-variables.md#abuse-limits).
- With `TESTING=true` (the test environments) these Redis-counted limits, and `UPLOAD_URLS_PER_DAY`, are not enforced; `MAX_ACTIVE_RUNS_PER_USER` is a database check and is.

## API and script authentication

The browser login and scripts authenticate differently:

- `POST /api/auth/login` is for the browser app. It answers with `{token_type, expires_in, user}` and puts the tokens only into HttpOnly cookies (`access_token`, 60 minutes, and `refresh_token`, 7 days). The body never contains a token, so a script cannot use the login response as a bearer token.
- `POST /api/auth/token` with `{"username": ..., "password": ...}` is for scripts. It answers with `{access_token, token_type, expires_in, user}`, sets no cookie and issues no refresh token. The token is valid for 60 minutes and carries the user's full rights (no scopes); send it as `Authorization: Bearer <access_token>` and request a new one when it expires. The app host relays this route too (`services/frontend/src/app/api/auth/token/route.ts`), so it works on both the app and the api host.
- For long-running automation use an access key (`bgr_...`) instead. Keys are scoped, can be limited to projects and revoked, and are described in [Access keys](../api-keys.md).

## Deployment Configuration

### Helm Values
Production deployments use `/infra/helm/benger/values.yaml`:
```yaml
api:
  env:
    - name: ENVIRONMENT
      value: "production"  # IMPORTANT: Must be 'production' for proper authentication
```

Staging deployments override it in their own values file:
```yaml
api:
  env:
    - name: ENVIRONMENT
      value: "staging"  # Override to staging
```

## Verification Commands

Check current environment settings:
```bash
# Production
kubectl exec -n benger deployment/benger-api -- sh -c 'echo $ENVIRONMENT'

# Staging
kubectl exec -n benger-staging deployment/benger-staging-api -- sh -c 'echo $ENVIRONMENT'
```

## CI/CD Integration

The GitHub Actions workflows should always deploy with proper environment settings:
- Production deployments → `ENVIRONMENT=production`
- Staging deployments → `ENVIRONMENT=staging`
- PR deployments → `ENVIRONMENT=staging`

## Troubleshooting

If authentication seems disabled in production:
1. Check the ENVIRONMENT variable: `kubectl exec -n benger deployment/benger-api -- env | grep ENVIRONMENT`
2. If it shows `development` or template values like `{{ .Values.global.environment }}`, fix immediately:
   ```bash
   kubectl set env deployment/benger-api ENVIRONMENT=production -n benger
   kubectl rollout restart deployment/benger-api -n benger
   ```

## Security Checklist

- [ ] Production ENVIRONMENT is set to "production"
- [ ] Staging ENVIRONMENT is set to "staging"
- [ ] No development deployments in production namespace
- [ ] Helm values files have correct environment settings
- [ ] Deployment scripts enforce proper environment
- [ ] CI/CD workflows set correct environment
- [ ] Regular audits of environment variables in running pods