# BenGER Consolidated Deployment Guide

**Version**: 2.0  
**Last Updated**: December 17, 2024  
**Target Audience**: DevOps, System Administrators, Development Team  

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Infrastructure Requirements](#infrastructure-requirements)
3. [Initial Server Setup](#initial-server-setup)
4. [Automated Deployment (Recommended)](#automated-deployment-recommended)
5. [Manual Deployment (Advanced)](#manual-deployment-advanced)
6. [CI/CD Pipeline Setup](#ci-cd-pipeline-setup)
7. [Critical Components](#critical-components)
8. [Troubleshooting & Resolution](#troubleshooting--resolution)
9. [Production Operations](#production-operations)
10. [Future Deployment Procedures](#future-deployment-procedures)

---

## 📖 Overview

This guide consolidates all deployment knowledge gained from successfully deploying BenGER to production, including resolution of critical issues like GHCR authentication, SSL certificates, and service port configurations.

### Architecture Overview
```
┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│     Frontend        │    │        API          │    │      Workers        │
│   (Next.js:3000)   │    │   (FastAPI:8000)    │    │   (Python/Celery)  │
│     2-5 pods        │    │     2-5 pods        │    │     2-10 pods       │
└─────────────────────┘    └─────────────────────┘    └─────────────────────┘
         │                           │                           │
         └───────────────────────────┼───────────────────────────┘
                                     │
┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│   Native Annotation System      │    │    PostgreSQL      │    │       Redis         │
│  (Annotation:8080)  │    │   (Database:5432)  │    │   (Queue:6379)      │
│     1-2 pods        │    │      1 pod          │    │    1+3 pods         │
└─────────────────────┘    └─────────────────────┘    └─────────────────────┘
```

### Production URLs
- **Main Application**: https://what-a-benger.net
- **API Documentation**: https://api.what-a-benger.net/docs
- **Native Annotation System**: https://label.what-a-benger.net
- **Monitoring**: https://grafana.what-a-benger.net

---

## 🏗️ Infrastructure Requirements

### Minimum Server Specifications
- **OS**: Ubuntu 20.04 LTS or newer
- **CPU**: 4+ cores (8+ recommended for production)
- **Memory**: 8GB+ RAM (16GB+ recommended)
- **Storage**: 50GB+ SSD (100GB+ recommended)
- **Network**: Public IP with domain access

### Required Domains & DNS
```bash
# A Records pointing to your server IP
what-a-benger.net         → YOUR_SERVER_IP
api.what-a-benger.net     → YOUR_SERVER_IP
label.what-a-benger.net   → YOUR_SERVER_IP
grafana.what-a-benger.net → YOUR_SERVER_IP

# Wildcard (optional but recommended)
*.what-a-benger.net       → YOUR_SERVER_IP
```

### Software Dependencies
- **Kubernetes**: K3s (lightweight) or managed K8s
- **Container Runtime**: Docker
- **Package Manager**: Helm 3.x
- **Ingress**: Traefik (included with K3s)
- **SSL**: cert-manager + Let's Encrypt

---

## 🚀 Initial Server Setup

### 1. Automated Server Setup (Recommended)
```bash
# Clone the repository
git clone https://github.com/sebastiannagl/benger.git
cd benger

# Run automated server setup
chmod +x scripts/server-setup.sh
sudo ./scripts/server-setup.sh
```

**What this installs:**
- K3s Kubernetes cluster
- Docker and Docker Compose
- kubectl and Helm
- Basic security configuration
- System monitoring tools

### 2. Manual Setup (If needed)
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install K3s
curl -sfL https://get.k3s.io | sh -s - --write-kubeconfig-mode 644

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Install kubectl (if not included)
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl

# Install Helm
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# Verify installations
kubectl get nodes
docker --version
helm version
```

---

## 🎯 Automated Deployment (Recommended)

### Quick Start (5 minutes)
```bash
# 1. Server setup (one-time)
./scripts/server-setup.sh

# 2. Deploy BenGER application
./scripts/deploy-benger.sh

# 3. Setup CI/CD (optional but recommended)
./scripts/setup-github-cicd.sh
```

### What Gets Deployed
- ✅ **BenGER Platform**: Complete application stack
- ✅ **Database**: PostgreSQL with persistent storage
- ✅ **Cache**: Redis cluster (master + replicas)
- ✅ **Monitoring**: Prometheus + Grafana
- ✅ **SSL**: Automatic Let's Encrypt certificates
- ✅ **Ingress**: Traefik with proper routing

### Verification Commands
```bash
# Check all pods
kubectl get pods -n benger

# Check services and ingress
kubectl get svc,ingress -n benger

# Check SSL certificates
kubectl get certificates -n benger

# Test endpoints
curl -f https://what-a-benger.net
curl -f https://api.what-a-benger.net/healthz
```

---

## 🔧 Manual Deployment (Advanced)

### 1. Prerequisites Setup
```bash
# Create namespace
kubectl create namespace benger

# Add Helm repositories
helm repo add jetstack https://charts.jetstack.io
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update
```

### 2. Install cert-manager
```bash
helm upgrade --install cert-manager jetstack/cert-manager \
    --namespace cert-manager \
    --create-namespace \
    --version v1.13.0 \
    --set installCRDs=true \
    --wait
```

### 3. Create ClusterIssuer
```bash
kubectl apply -f - <<EOF
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: sebastian.nagl@tum.de
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          class: traefik
EOF
```

### 4. Deploy BenGER
```bash
# Update Helm dependencies
cd infra/helm/benger
helm dependency update
cd ../../..

# Deploy application
helm upgrade --install benger ./infra/helm/benger \
    --namespace benger \
    --set global.environment=production \
    --set global.domain=what-a-benger.net \
    --wait --timeout=15m
```

---

## 🔄 CI/CD Pipeline Setup

### GitHub Actions Self-Hosted Runner

#### 1. Setup Runner on Production Server
```bash
# Run the setup script
./scripts/setup-github-runner.sh

# Configure runner with GitHub token
# Get token from: https://github.com/YOUR_USERNAME/BenGER/settings/actions/runners/new
sudo -u github-runner /opt/actions-runner/config.sh \
  --url https://github.com/YOUR_USERNAME/BenGER \
  --token YOUR_TOKEN_HERE \
  --name production-runner

# Install as service
sudo /opt/actions-runner/svc.sh install github-runner
sudo /opt/actions-runner/svc.sh start
```

#### 2. GitHub Container Registry Setup
```bash
# Create Personal Access Token with packages permissions
# Login to GHCR
echo YOUR_PAT_TOKEN | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin

# Create Kubernetes secret for image pulls
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username=YOUR_GITHUB_USERNAME \
  --docker-password=YOUR_PAT_TOKEN \
  --namespace=benger
```

#### 3. Workflow Configuration
The repository includes two main workflows:

**`.github/workflows/ci.yml`** (Testing):
- Runs on GitHub-hosted runners
- Executes tests, linting, build validation
- Triggers on all pushes and PRs

**`.github/workflows/deploy-self-hosted.yml`** (Deployment):
- Runs on self-hosted runner
- Builds and pushes Docker images
- Deploys to Kubernetes
- Triggers only on main/master branch

### Benefits of Self-Hosted CI/CD
- ✅ **Free unlimited deployment minutes**
- ✅ **Faster builds** (local Docker cache)
- ✅ **Direct cluster access** (no SSH needed)
- ✅ **Correct architecture** (native AMD64)
- ✅ **Better security** (no secrets in GitHub)

---

## 🔑 Critical Components

### 1. Image Pull Authentication
**Critical Issue Resolved**: GHCR authentication failures

```bash
# Create image pull secret (MANDATORY)
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username=YOUR_GITHUB_USERNAME \
  --docker-password=YOUR_PAT_TOKEN \
  --namespace=benger

# Verify secret
kubectl get secret ghcr-secret -o yaml -n benger
```

### 2. Service Port Configuration
**Critical Issue Resolved**: Frontend port mismatch

```yaml
# Correct frontend service configuration
frontend:
  service:
    type: ClusterIP
    port: 3000        # External port
    targetPort: 3000  # Container port (Next.js default)
    protocol: TCP
```

### 3. SSL Certificate Management
**Critical Issue Resolved**: Certificate issuer configuration

```yaml
# Correct ingress annotations
ingress:
  annotations:
    kubernetes.io/ingress.class: traefik
    cert-manager.io/cluster-issuer: letsencrypt-prod  # NOT letsencrypt-staging
```

### 4. Image Pull Policy
**Best Practice**: Always pull latest images in production

```yaml
image:
  repository: ghcr.io/sebastiannagl/benger/frontend
  tag: latest
  pullPolicy: Always  # Ensures latest image is used
```

---

## 🚨 Troubleshooting & Resolution

### Common Issues and Solutions

#### 1. Pods in ImagePullBackOff State
**Symptoms**: Pods stuck in `ImagePullBackOff` or `ErrImagePull`

**Solution**:
```bash
# Check image pull secret exists
kubectl get secrets -n benger | grep ghcr

# Recreate if missing
kubectl delete secret ghcr-secret -n benger
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username=YOUR_GITHUB_USERNAME \
  --docker-password=YOUR_PAT_TOKEN \
  --namespace=benger

# Test image pull manually
docker pull ghcr.io/sebastiannagl/benger/frontend:latest
```

#### 2. Frontend Shows Default/Maintenance Page
**Symptoms**: Website accessible but shows nginx default or maintenance page

**Solution**:
```bash
# Check if real BenGER image is deployed
kubectl describe deployment benger-frontend -n benger | grep Image

# Update deployment with correct image
helm upgrade benger ./infra/helm/benger \
  --namespace benger \
  --set frontend.image.repository=ghcr.io/sebastiannagl/benger/frontend \
  --set frontend.image.tag=latest \
  --set frontend.image.pullPolicy=Always
```

#### 3. SSL Certificate Issues
**Symptoms**: HTTPS not working, certificate warnings

**Solution**:
```bash
# Check certificate status
kubectl get certificates -n benger
kubectl describe certificate frontend-tls -n benger

# Force certificate renewal
kubectl delete certificate frontend-tls -n benger
kubectl annotate ingress benger-frontend cert-manager.io/cluster-issuer=letsencrypt-prod -n benger
```

#### 4. Service Connection Issues
**Symptoms**: Services can't communicate with each other

**Solution**:
```bash
# Check service endpoints
kubectl get endpoints -n benger

# Test service connectivity from inside pod
kubectl exec -it deployment/benger-frontend -n benger -- wget -qO- http://benger-api:8000/healthz
```

### Emergency Recovery Procedures

#### Quick Rollback
```bash
# Rollback to previous Helm release
helm rollback benger -n benger

# Check rollback status
helm list -n benger
kubectl get pods -n benger
```

#### Complete Redeployment
```bash
# Remove current deployment
helm uninstall benger -n benger

# Wait for cleanup
kubectl wait --for=delete pod -l app.kubernetes.io/part-of=benger -n benger --timeout=300s

# Redeploy
helm install benger ./infra/helm/benger \
  --namespace benger \
  --set global.environment=production \
  --set global.domain=what-a-benger.net
```

#### Database Recovery
```bash
# If database issues occur
kubectl get pvc -n benger  # Check persistent volumes
kubectl logs deployment/benger-postgresql -n benger  # Check database logs

# Restart database if needed
kubectl rollout restart deployment/benger-postgresql -n benger
```

---

## 📊 Production Operations

### Health Monitoring

#### Automated Health Checks
```bash
# Create monitoring script
cat > /usr/local/bin/benger-health-check.sh << 'EOF'
#!/bin/bash
DOMAIN="what-a-benger.net"

echo "$(date): Starting health checks..."

# Frontend check
if curl -f -s --max-time 30 "https://$DOMAIN" > /dev/null; then
    echo "✅ Frontend: OK"
else
    echo "❌ Frontend: FAILED"
    exit 1
fi

# API check
if curl -f -s --max-time 30 "https://api.$DOMAIN/healthz" > /dev/null; then
    echo "✅ API: OK"
else
    echo "❌ API: FAILED"
    exit 1
fi

# Native Annotation System check
if curl -f -s --max-time 30 "https://label.$DOMAIN/health/" > /dev/null; then
    echo "✅ Native Annotation System: OK"
else
    echo "❌ Native Annotation System: FAILED"
    exit 1
fi

echo "$(date): All health checks passed!"
EOF

chmod +x /usr/local/bin/benger-health-check.sh

# Add to crontab for regular monitoring
echo "*/5 * * * * /usr/local/bin/benger-health-check.sh >> /var/log/benger-health.log 2>&1" | crontab -
```

#### Manual Health Verification
```bash
# Check all pods
kubectl get pods -n benger

# Check services
kubectl get svc -n benger

# Check ingress and SSL
kubectl get ingress,certificates -n benger

# Test endpoints
curl -I https://what-a-benger.net
curl -I https://api.what-a-benger.net/healthz
curl -I https://label.what-a-benger.net
```

### Backup Procedures

#### Database Backup
```bash
# Create backup script
cat > /usr/local/bin/backup-benger.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/backup/benger"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Database backup
kubectl exec deployment/benger-postgresql -n benger -- pg_dump -U postgres benger | gzip > $BACKUP_DIR/benger_db_$DATE.sql.gz

# Keep only last 7 days
find $BACKUP_DIR -name "benger_db_*.sql.gz" -mtime +7 -delete

echo "Backup completed: $BACKUP_DIR/benger_db_$DATE.sql.gz"
EOF

chmod +x /usr/local/bin/backup-benger.sh

# Schedule daily backups
echo "0 3 * * * /usr/local/bin/backup-benger.sh" | crontab -
```

#### Configuration Backup
```bash
# Backup Kubernetes resources
kubectl get all,secrets,configmaps,ingress,certificates -n benger -o yaml > benger-k8s-backup.yaml

# Backup Helm configuration
helm get values benger -n benger > benger-helm-values.yaml
```

### Performance Optimization

#### Resource Scaling
```bash
# Scale frontend for high traffic
kubectl scale deployment benger-frontend --replicas=5 -n benger

# Scale API for high load
kubectl scale deployment benger-api --replicas=5 -n benger

# Scale workers for background processing
kubectl scale deployment benger-workers --replicas=10 -n benger
```

#### Auto-scaling Configuration
```yaml
# HPA example (included in Helm chart)
autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
  targetMemoryUtilizationPercentage: 80
```

---

## 🚀 Future Deployment Procedures

### Standard Deployment Workflow

#### 1. Automated Deployment (Recommended)
```bash
# Simply push to main branch
git add .
git commit -m "feat: your changes"
git push origin main

# Or trigger manually via GitHub UI
# Go to Actions → Deploy to Production (Self-Hosted) → Run workflow
```

#### 2. Manual Deployment (When needed)
```bash
# Pull latest changes
git pull origin main

# Build and push new images (if self-hosted runner not available)
docker build -t ghcr.io/sebastiannagl/benger/frontend:latest ./services/frontend
docker push ghcr.io/sebastiannagl/benger/frontend:latest

# Update deployment
helm upgrade benger ./infra/helm/benger \
  --namespace benger \
  --set frontend.image.tag=latest
```

### Pre-Deployment Checklist

#### Before Any Deployment
- [ ] **Backup database** (automated daily, manual for major changes)
- [ ] **Check disk space** (`df -h` - ensure <90% usage)
- [ ] **Verify runner status** (GitHub repository → Settings → Actions → Runners)
- [ ] **Test in staging** (if available)
- [ ] **Review changes** (code review completed)

#### During Deployment
- [ ] **Monitor GitHub Actions** (real-time deployment logs)
- [ ] **Watch pod status** (`kubectl get pods -n benger -w`)
- [ ] **Check ingress status** (`kubectl get ingress -n benger`)
- [ ] **Verify SSL certificates** (`kubectl get certificates -n benger`)

#### Post-Deployment Verification
- [ ] **Health checks pass** (automated in workflow)
- [ ] **Frontend accessible** (https://what-a-benger.net)
- [ ] **API responding** (https://api.what-a-benger.net/healthz)
- [ ] **SSL valid** (no certificate warnings)
- [ ] **Performance normal** (response times <500ms)

### Release Management

#### Version Tagging Strategy
```bash
# Semantic versioning for releases
git tag -a v1.2.3 -m "Release version 1.2.3"
git push origin v1.2.3

# Docker images are automatically tagged with:
# - latest (for main branch)
# - v20241217-abc1234 (date + commit SHA)
# - Manual tags for releases
```

#### Rollback Procedures
```bash
# Quick rollback via Helm
helm rollback benger -n benger

# Rollback to specific version
helm history benger -n benger
helm rollback benger 3 -n benger  # Rollback to revision 3

# Emergency: Scale down problematic service
kubectl scale deployment benger-frontend --replicas=0 -n benger
```

### Environment Management

#### Production Environment Variables
**Secrets that MUST be configured**:
```bash
# Database credentials
kubectl create secret generic benger-postgres-credentials \
  --from-literal=uri="postgresql://..." \
  --namespace=benger

# API secrets
kubectl create secret generic benger-api-secrets \
  --from-literal=secret_key="your-super-secret-key" \
  --namespace=benger

# LLM API keys
kubectl create secret generic benger-llm-credentials \
  --from-literal=openai_api_key="sk-..." \
  --from-literal=anthropic_api_key="sk-ant-..." \
  --namespace=benger
```

#### Configuration Updates
```bash
# Update secrets (example: new OpenAI API key)
kubectl patch secret benger-llm-credentials -n benger \
  -p '{"data":{"openai_api_key":"'$(echo -n "sk-new-key" | base64)'"}}'

# Restart pods to pick up new secrets
kubectl rollout restart deployment/benger-api -n benger
kubectl rollout restart deployment/benger-workers -n benger
```

### Monitoring and Alerting

#### Grafana Dashboard Access
- **URL**: https://grafana.what-a-benger.net
- **Default Login**: admin/admin (change immediately)
- **Key Metrics**: CPU, Memory, Request Rate, Response Time

#### Log Monitoring
```bash
# Tail application logs
kubectl logs -f deployment/benger-frontend -n benger
kubectl logs -f deployment/benger-api -n benger
kubectl logs -f deployment/benger-workers -n benger

# Filter logs by error level
kubectl logs deployment/benger-api -n benger | grep ERROR

# Export logs for analysis
kubectl logs deployment/benger-api -n benger --since=1h > api-logs.txt
```

### Security Updates

#### Regular Maintenance Tasks

**Monthly**:
- [ ] Update Kubernetes cluster
- [ ] Update container images with security patches
- [ ] Review and rotate secrets
- [ ] Check SSL certificate expiration

**Quarterly**:
- [ ] Security audit of dependencies
- [ ] Review access permissions
- [ ] Update documentation
- [ ] Disaster recovery testing

#### Security Best Practices
```bash
# Network policies (limit pod-to-pod communication)
kubectl apply -f infra/security/network-policies.yaml

# Pod security standards
kubectl apply -f infra/security/pod-security.yaml

# External secrets management (if using external secret manager)
kubectl apply -f infra/security/external-secrets.yaml
```

---

## 📚 Documentation Updates

### Keeping Documentation Current

#### When to Update This Guide
- **After resolving new deployment issues**
- **When infrastructure changes significantly**
- **After adding new services or components**
- **When changing deployment procedures**
- **After security updates or configuration changes**

#### How to Update
1. **Edit this file** (`docs/CONSOLIDATED_DEPLOYMENT_GUIDE.md`)
2. **Update version and date** at the top
3. **Add new procedures** to relevant sections
4. **Update troubleshooting** with new known issues
5. **Test all documented procedures** before publishing
6. **Commit and push** to version control

### Related Documentation
- **[Main README](../README.md)** - Project overview
- **[Development Guide](./development/README.md)** - Local development
- **[API Documentation](./api/README.md)** - Backend API reference
- **[User Guides](./user-guides/)** - End-user documentation
- **[Troubleshooting](./TROUBLESHOOTING.md)** - Common issues

---

## 🎯 Success Metrics

### Deployment Success Criteria
- ✅ **All pods running** (`kubectl get pods -n benger`)
- ✅ **Frontend accessible** (https://what-a-benger.net returns 200)
- ✅ **API healthy** (https://api.what-a-benger.net/healthz returns 200)
- ✅ **SSL valid** (No certificate warnings)
- ✅ **Performance good** (Response times <1s)
- ✅ **No error logs** (Check application logs)

### Operational Excellence
- 🎯 **Uptime target**: 99.9% (8.77 hours downtime/year)
- 🎯 **Response time**: <500ms for 95% of requests
- 🎯 **Deployment time**: <15 minutes end-to-end
- 🎯 **Recovery time**: <5 minutes for rollbacks
- 🎯 **Zero data loss** during deployments

---

## 👥 Support and Escalation

### Getting Help

#### Self-Service Resources
1. **Check this guide** for common procedures
2. **Review troubleshooting section** for known issues
3. **Check GitHub Actions logs** for deployment issues
4. **Examine pod logs** for application errors

#### Support Channels
- **GitHub Issues**: Report bugs and request features
- **Team Slack**: Real-time support during business hours
- **Emergency Contact**: For production incidents

#### Escalation Path
1. **Level 1**: Self-service using this documentation
2. **Level 2**: Development team assistance
3. **Level 3**: Infrastructure/DevOps team
4. **Level 4**: External vendor support (for K8s/cloud issues)

---

## 🏁 Conclusion

This consolidated guide represents the complete knowledge gained from successfully deploying BenGER to production. It includes:

- ✅ **Proven procedures** that work in practice
- ✅ **Real issue resolution** from actual deployment experience
- ✅ **Complete automation** for efficient future deployments
- ✅ **Comprehensive troubleshooting** for common problems
- ✅ **Production-ready operations** for ongoing maintenance

### Key Takeaways
1. **Automation saves time** - Use the provided scripts whenever possible
2. **Documentation is critical** - Keep this guide updated with new learnings
3. **Testing is essential** - Always verify deployments with health checks
4. **Security matters** - Follow the security procedures consistently
5. **Monitoring prevents issues** - Set up proactive monitoring and alerting

### Next Steps
1. **Use this guide** for all future deployments
2. **Update procedures** when you encounter new scenarios
3. **Train team members** on these documented procedures
4. **Implement monitoring** and alerting as described
5. **Regular maintenance** following the operational procedures

---

**🎉 Happy Deploying! Your BenGER platform is now production-ready with professional-grade deployment procedures.**

---

*Document maintained by: TUM Legal Tech Team*  
*Last major update: December 17, 2024*  
*Next review: March 17, 2025* 