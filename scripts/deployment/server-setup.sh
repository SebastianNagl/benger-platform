#!/bin/bash
set -e

echo "🚀 BenGER Server Setup Script"
echo "=============================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   print_error "This script should not be run as root"
   exit 1
fi

# Update system
print_status "Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install prerequisites
print_status "Installing prerequisites..."
sudo apt install -y curl wget gnupg2 software-properties-common apt-transport-https ca-certificates

# Install Docker
print_status "Installing Docker..."
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io

# Add user to docker group
sudo usermod -aG docker $USER
print_warning "You'll need to log out and back in for Docker group changes to take effect"

# Install kubectl
print_status "Installing kubectl..."
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
rm kubectl

# Install helm
print_status "Installing Helm..."
curl https://baltocdn.com/helm/signing.asc | gpg --dearmor | sudo tee /usr/share/keyrings/helm.gpg > /dev/null
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/helm.gpg] https://baltocdn.com/helm/stable/debian/ all main" | sudo tee /etc/apt/sources.list.d/helm-stable-debian.list
sudo apt update
sudo apt install -y helm

# Install k3s (lightweight Kubernetes)
print_status "Installing k3s Kubernetes..."
curl -sfL https://get.k3s.io | sh -s - --write-kubeconfig-mode 644

# Set up kubectl config
print_status "Setting up kubectl configuration..."
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown $USER:$USER ~/.kube/config

# Verify installations
print_status "Verifying installations..."
echo "Docker version:"
docker --version
echo "kubectl version:"
kubectl version --client
echo "Helm version:"
helm version --short
echo "k3s status:"
sudo systemctl status k3s --no-pager -l

# Check if k3s is ready
print_status "Waiting for k3s to be ready..."
kubectl wait --for=condition=Ready nodes --all --timeout=300s

print_status "✅ Server setup complete!"
print_status "Next steps:"
print_status "1. Log out and back in to apply Docker group changes"
print_status "2. Run the BenGER deployment script"
print_status "3. Configure DNS to point what-a-benger.net to this server"

echo ""
print_status "Server IP address:"
curl -s ifconfig.me && echo "" 