#!/bin/bash
set -e

echo "🎯 BenGER Deployment Script"
echo "============================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}=== $1 ===${NC}"
}

# Check if kubectl is working
print_status "Checking Kubernetes connection..."
if ! kubectl get nodes >/dev/null 2>&1; then
    print_error "Cannot connect to Kubernetes cluster. Please ensure k3s is running."
    exit 1
fi

# Add Helm repositories
print_header "Setting up Helm repositories"
helm repo add jetstack https://charts.jetstack.io
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

# Install cert-manager
print_header "Installing cert-manager"
helm upgrade --install cert-manager jetstack/cert-manager \
    --namespace cert-manager \
    --create-namespace \
    --version v1.13.0 \
    --set installCRDs=true \
    --wait

# Create Let's Encrypt ClusterIssuer
print_status "Creating Let's Encrypt ClusterIssuer..."
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

print_status "Creating Let's Encrypt staging ClusterIssuer..."
kubectl apply -f - <<EOF
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-staging
spec:
  acme:
    server: https://acme-staging-v02.api.letsencrypt.org/directory
    email: sebastian.nagl@tum.de
    privateKeySecretRef:
      name: letsencrypt-staging
    solvers:
    - http01:
        ingress:
          class: traefik
EOF

# Monitoring stack removed - use external monitoring instead
# Consider using Uptime Kuma, Datadog, or New Relic for monitoring

# Create secrets for BenGER (you'll need to update these)
print_header "Creating BenGER secrets"
kubectl create namespace benger --dry-run=client -o yaml | kubectl apply -f -

# Create database credentials secret
kubectl create secret generic benger-postgres-credentials \
    --namespace=benger \
    --from-literal=uri="postgresql://postgres:postgres_password@benger-postgresql:5432/benger" \
    --from-literal=username="postgres" \
    --from-literal=password="postgres_password" \
    --dry-run=client -o yaml | kubectl apply -f -

# Create Redis credentials secret
kubectl create secret generic benger-redis-credentials \
    --namespace=benger \
    --from-literal=uri="redis://:redis_password@benger-redis-master:6379/0" \
    --dry-run=client -o yaml | kubectl apply -f -

# Create API secrets
kubectl create secret generic benger-api-secrets \
    --namespace=benger \
    --from-literal=secret_key="your-super-secret-key-change-this-in-production" \
    --dry-run=client -o yaml | kubectl apply -f -

# Create LLM credentials (you'll need to add real keys)
kubectl create secret generic benger-llm-credentials \
    --namespace=benger \
    --from-literal=openai_api_key="your-openai-key-here" \
    --from-literal=anthropic_api_key="your-anthropic-key-here" \
    --dry-run=client -o yaml | kubectl apply -f -

print_warning "⚠️  Please update the secrets with real values:"
print_warning "   kubectl edit secret benger-llm-credentials -n benger"

# Clone BenGER repository if not exists
if [ ! -d "BenGER" ]; then
    print_status "Cloning BenGER repository..."
    git clone https://github.com/tum-legal-tech/benger.git BenGER
fi

cd BenGER

# Update Helm dependencies
print_status "Updating Helm dependencies..."
cd infra/helm/benger
helm dependency update
cd ../../..

# Deploy BenGER
print_header "Deploying BenGER application"
helm upgrade --install benger ./infra/helm/benger \
    --namespace benger \
    --values ./infra/helm/benger/values-production.yaml \
    --set global.imagePullSecrets[0].name=ghcr-secret \
    --wait --timeout=15m

# Show deployment status
print_header "Deployment Status"
kubectl get pods -n benger
kubectl get services -n benger
kubectl get ingress -n benger
kubectl get certificates -n benger

print_status "✅ BenGER deployment complete!"
print_status ""
print_status "🌐 Access your application:"
print_status "   Frontend: https://what-a-benger.net"
print_status "   API: https://api.what-a-benger.net"
print_status ""
print_warning "⚠️  Important next steps:"
print_warning "1. Update DNS records to point domains to this server"
print_warning "2. Update secrets with real API keys"
print_warning "3. Change default passwords"
print_warning "4. Configure backup systems"

echo ""
print_status "Server IP address:"
curl -s ifconfig.me && echo "" 