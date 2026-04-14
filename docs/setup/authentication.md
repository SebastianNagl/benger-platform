# Authentication Configuration Guide

## Overview
BenGER's authentication system is controlled by the `ENVIRONMENT` variable. When set to `development`, certain authentication checks may be bypassed for local development. **Production and staging environments MUST have proper environment settings to ensure authentication is enforced.**

## Current Configuration

### Production Environment (namespace: benger)
- **ENVIRONMENT**: `production`
- **Authentication**: FULLY ENABLED
- **URL**: https://what-a-benger.net
- **API**: https://api.what-a-benger.net

### Staging Environment (namespace: benger-staging)  
- **ENVIRONMENT**: `staging`
- **Authentication**: FULLY ENABLED
- **URL**: https://staging.what-a-benger.net
- **API**: https://api.staging.what-a-benger.net

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
- Production: Rate limiting enforced
- Development: Can be disabled with `DEBUG_DISABLE_RATE_LIMITING=true`

## Deployment Configuration

### Helm Values
Production deployments use `/infra/helm/benger/values.yaml`:
```yaml
api:
  env:
    - name: ENVIRONMENT
      value: "production"  # IMPORTANT: Must be 'production' for proper authentication
```

Staging deployments use `/infra/helm/benger/values-staging.yaml`:
```yaml
api:
  env:
    - name: ENVIRONMENT
      value: "staging"  # Override to staging
```

### Rolling Deployment Script
The `/scripts/deploy-rolling.sh` script automatically sets the correct environment:
```bash
# Ensure proper environment is set based on namespace
if [[ "$NAMESPACE" == *"staging"* ]]; then
    kubectl set env deployment/"$deployment" ENVIRONMENT=staging -n "$NAMESPACE"
elif [[ "$NAMESPACE" == "benger" ]]; then
    kubectl set env deployment/"$deployment" ENVIRONMENT=production -n "$NAMESPACE"
fi
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