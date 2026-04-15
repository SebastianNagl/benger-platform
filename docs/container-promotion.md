# Container Promotion Strategy

## Overview

BenGer uses a **container promotion strategy** for deployments, following the industry-standard DevOps principle of "build once, deploy everywhere". This ensures that the exact same container images tested in staging are promoted to production, eliminating build inconsistencies and reducing deployment risks.

## Benefits

- **Consistency**: The exact containers tested in staging run in production - no build variations
- **Speed**: Production deployments take ~5 minutes instead of ~20 minutes (no rebuild required)
- **Safety**: Issues are caught in staging before production
- **Auditability**: Clear trail of which specific images are running where
- **Rollback**: Easy to revert to previous known-good images

## Architecture

```
┌─────────────┐     Build      ┌──────────────┐     Promote     ┌────────────┐
│   GitHub    │ ───────────▶   │   Staging    │ ──────────────▶ │ Production │
│   PR/Push   │                 │ Environment  │                  │Environment │
└─────────────┘                 └──────────────┘                  └────────────┘
     (dev)                    (benger-staging)                    (benger)
                                namespace                         namespace
```

## Deployment Flow

### 1. Staging Deployment (Automated)

When code is pushed to a PR or the dev branch:

1. GitHub Actions triggers the staging deployment workflow
2. Containers are built with tags like `staging-dev-afd2ccdbc`
3. Images are pushed to GitHub Container Registry (`ghcr.io`)
4. Helm deploys to the `benger-staging` namespace with staging configuration
5. Automated tests and manual verification occur in staging

### 2. Production Promotion (Manual)

Once staging is verified, promote the same containers to production:

```bash
# SSH to production server
ssh user@production-server

# Extract the current staging image tags
API_TAG=$(kubectl get deployment benger-staging-api \
  -n benger-staging \
  -o jsonpath='{.spec.template.spec.containers[0].image}' | cut -d: -f2)

FRONTEND_TAG=$(kubectl get deployment benger-staging-frontend \
  -n benger-staging \
  -o jsonpath='{.spec.template.spec.containers[0].image}' | cut -d: -f2)

WORKERS_TAG=$(kubectl get deployment benger-staging-workers \
  -n benger-staging \
  -o jsonpath='{.spec.template.spec.containers[0].image}' | cut -d: -f2)

# Verify the tags look correct
echo "API: $API_TAG"
echo "Frontend: $FRONTEND_TAG"
echo "Workers: $WORKERS_TAG"

# Deploy to production using production values but staging images
cd /path/to/benger
helm upgrade --install benger ./infra/helm/benger \
  --namespace benger \
  --values ./infra/helm/benger/values.yaml \
  --set api.image.tag=$API_TAG \
  --set frontend.image.tag=$FRONTEND_TAG \
  --set workers.image.tag=$WORKERS_TAG \
  --wait --timeout=600s
```

## Configuration Differences

While the **container images are identical**, the configuration differs between environments:

### Staging (`values-staging.yaml`)
- Domain: `staging.what-a-benger.net`
- Replicas: 1 (reduced resources)
- Database: Separate staging database
- Environment: `staging`
- Debug logging enabled

### Production (`values.yaml`)
- Domain: `what-a-benger.net`
- Replicas: 2+ (high availability)
- Database: Production database
- Environment: `production`
- Production logging levels

## Quick Promotion Script

Create a reusable script for promotion:

```bash
#!/bin/bash
# promote-to-production.sh

set -e

echo "🚀 Promoting staging to production..."

# Get staging tags
API_TAG=$(kubectl get deployment benger-staging-api -n benger-staging -o jsonpath='{.spec.template.spec.containers[0].image}' | cut -d: -f2)
FRONTEND_TAG=$(kubectl get deployment benger-staging-frontend -n benger-staging -o jsonpath='{.spec.template.spec.containers[0].image}' | cut -d: -f2)
WORKERS_TAG=$(kubectl get deployment benger-staging-workers -n benger-staging -o jsonpath='{.spec.template.spec.containers[0].image}' | cut -d: -f2)

echo "📦 Container versions to promote:"
echo "  API: $API_TAG"
echo "  Frontend: $FRONTEND_TAG"
echo "  Workers: $WORKERS_TAG"

read -p "Continue with promotion? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Promotion cancelled"
    exit 1
fi

echo "🔄 Deploying to production..."
helm upgrade --install benger ./infra/helm/benger \
  --namespace benger \
  --values ./infra/helm/benger/values.yaml \
  --set api.image.tag=$API_TAG \
  --set frontend.image.tag=$FRONTEND_TAG \
  --set workers.image.tag=$WORKERS_TAG \
  --wait --timeout=600s

echo "✅ Production deployment complete!"
kubectl get pods -n benger
```

## Rollback Strategy

If issues occur in production, rollback to previous images:

```bash
# View helm release history
helm history benger -n benger

# Rollback to previous release
helm rollback benger -n benger

# Or deploy specific known-good tags
helm upgrade --install benger ./infra/helm/benger \
  --namespace benger \
  --values ./infra/helm/benger/values.yaml \
  --set api.image.tag=<previous-good-tag> \
  --set frontend.image.tag=<previous-good-tag> \
  --set workers.image.tag=<previous-good-tag>
```

## Best Practices

1. **Always test in staging first** - Never promote untested containers
2. **Document promotions** - Keep a log of what was promoted when
3. **Monitor after promotion** - Watch metrics and logs after deployment
4. **Keep staging running** - Don't tear down staging after promotion
5. **Tag releases** - Consider creating Git tags for promoted versions

## Comparison with Direct Production Builds

| Aspect | Container Promotion | Direct Production Build |
|--------|-------------------|------------------------|
| Deployment Time | ~5 minutes | ~20 minutes |
| Risk | Lower (tested artifacts) | Higher (untested build) |
| Consistency | Exact match | Potential variations |
| Rollback | Simple (previous tags) | Requires rebuild |
| Resource Usage | Lower | Higher (build resources) |
| Complexity | Simple | More complex |

## Troubleshooting

### Issue: Staging images not accessible
**Solution**: Ensure GitHub Container Registry credentials are configured:
```bash
kubectl get secret ghcr-secret -n benger
```

### Issue: Different behavior in production
**Cause**: Configuration differences (not container differences)
**Solution**: Review environment variables and secrets between namespaces

### Issue: Promotion fails with "image not found"
**Solution**: Ensure staging deployment completed successfully and images were pushed to registry

## Future Enhancements

Consider implementing:
- Automated promotion pipelines with approval gates
- Blue-green deployments for zero-downtime updates
- Canary deployments for gradual rollouts
- GitOps with ArgoCD for declarative deployments