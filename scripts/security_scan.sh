#!/bin/bash

# Automated Security Scanning Script for BenGER
# Issue #368: Implement security and performance testing suite

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
REPORTS_DIR="$PROJECT_ROOT/security-reports-$TIMESTAMP"

echo "🔒 Starting BenGER Security Scan - $(date)"
echo "📁 Reports will be saved to: $REPORTS_DIR"

# Create reports directory
mkdir -p "$REPORTS_DIR"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# 1. Python dependency security scanning with Safety
scan_python_dependencies() {
    print_status "Scanning Python dependencies for known vulnerabilities..."
    
    cd "$PROJECT_ROOT/services/api"
    
    if command_exists safety; then
        safety check --json > "$REPORTS_DIR/python-security-report.json" 2>&1 || {
            print_warning "Safety scan found vulnerabilities"
        }
        
        # Also generate human-readable report
        safety check > "$REPORTS_DIR/python-security-report.txt" 2>&1 || {
            print_warning "Safety scan found vulnerabilities"
        }
        
        print_success "Python dependency scan completed"
    else
        print_error "Safety not installed. Run: pip install safety"
        return 1
    fi
}

# 2. Python static code analysis with Bandit
scan_python_code() {
    print_status "Running static code analysis on Python code..."
    
    cd "$PROJECT_ROOT/services/api"
    
    if command_exists bandit; then
        bandit -r . -f json -o "$REPORTS_DIR/bandit-security-report.json" 2>&1 || {
            print_warning "Bandit found security issues"
        }
        
        # Also generate human-readable report
        bandit -r . > "$REPORTS_DIR/bandit-security-report.txt" 2>&1 || {
            print_warning "Bandit found security issues"
        }
        
        print_success "Python static analysis completed"
    else
        print_error "Bandit not installed. Run: pip install bandit"
        return 1
    fi
}

# 3. Node.js dependency scanning with npm audit
scan_nodejs_dependencies() {
    print_status "Scanning Node.js dependencies for vulnerabilities..."
    
    cd "$PROJECT_ROOT/services/frontend"
    
    if [ -f "package.json" ]; then
        # Run npm audit and capture output
        npm audit --audit-level=moderate --json > "$REPORTS_DIR/npm-audit-report.json" 2>&1 || {
            print_warning "npm audit found vulnerabilities"
        }
        
        # Generate human-readable report
        npm audit > "$REPORTS_DIR/npm-audit-report.txt" 2>&1 || {
            print_warning "npm audit found vulnerabilities"
        }
        
        print_success "Node.js dependency scan completed"
    else
        print_error "package.json not found in frontend directory"
        return 1
    fi
}

# 4. Docker image security scanning (if available)
scan_docker_images() {
    print_status "Scanning Docker images for vulnerabilities..."
    
    if command_exists docker; then
        cd "$PROJECT_ROOT"
        
        # List of Docker images to scan
        images=("api" "frontend" "workers")
        
        for image in "${images[@]}"; do
            if docker images | grep -q "$image"; then
                print_status "Scanning $image image..."
                
                # Use docker scout if available (new Docker feature)
                if docker scout --help >/dev/null 2>&1; then
                    docker scout cves "$image" > "$REPORTS_DIR/docker-scout-$image.txt" 2>&1 || {
                        print_warning "Docker Scout found issues in $image"
                    }
                fi
                
                # Use Trivy if available
                if command_exists trivy; then
                    trivy image --format json --output "$REPORTS_DIR/trivy-$image.json" "$image" 2>&1 || {
                        print_warning "Trivy found vulnerabilities in $image"
                    }
                fi
            fi
        done
        
        print_success "Docker image scanning completed"
    else
        print_warning "Docker not available, skipping image scans"
    fi
}

# 5. Check for secrets in code
scan_for_secrets() {
    print_status "Scanning for potential secrets in code..."
    
    cd "$PROJECT_ROOT"
    
    # Simple grep-based secret detection
    {
        echo "=== Potential Secrets Detection ==="
        echo "Scanning for common secret patterns..."
        echo ""
        
        # API keys
        echo "--- Potential API Keys ---"
        grep -r -i "api[_-]key" --include="*.py" --include="*.js" --include="*.ts" --include="*.env*" . || echo "None found"
        echo ""
        
        # Passwords
        echo "--- Potential Passwords ---"
        grep -r -i "password\s*=" --include="*.py" --include="*.js" --include="*.ts" . | grep -v "hashed_password" | head -10 || echo "None found"
        echo ""
        
        # Tokens
        echo "--- Potential Tokens ---"
        grep -r -i "token\s*=" --include="*.py" --include="*.js" --include="*.ts" . | head -10 || echo "None found"
        echo ""
        
        # Private keys
        echo "--- Potential Private Keys ---"
        grep -r "BEGIN.*PRIVATE KEY" . || echo "None found"
        echo ""
        
        # Database URLs
        echo "--- Potential Database URLs ---"
        grep -r -i "database.*url" --include="*.py" --include="*.js" --include="*.ts" --include="*.env*" . || echo "None found"
        
    } > "$REPORTS_DIR/secrets-scan.txt"
    
    print_success "Secret scanning completed"
}

# 6. Check file permissions
check_file_permissions() {
    print_status "Checking file permissions..."
    
    cd "$PROJECT_ROOT"
    
    {
        echo "=== File Permissions Analysis ==="
        echo "Checking for files with overly permissive permissions..."
        echo ""
        
        # World-writable files
        echo "--- World-writable files ---"
        find . -type f -perm -002 2>/dev/null || echo "None found"
        echo ""
        
        # Executable scripts
        echo "--- Executable files ---"
        find . -type f -perm -100 -name "*.sh" -o -name "*.py" -perm -100 2>/dev/null | head -20
        echo ""
        
        # Config files
        echo "--- Config files permissions ---"
        find . -name "*.env*" -o -name "config.*" -o -name "*.conf" 2>/dev/null | while read -r file; do
            ls -la "$file"
        done
        
    } > "$REPORTS_DIR/file-permissions.txt"
    
    print_success "File permission check completed"
}

# 7. Network security analysis
analyze_network_config() {
    print_status "Analyzing network configuration..."
    
    cd "$PROJECT_ROOT"
    
    {
        echo "=== Network Configuration Analysis ==="
        echo "Checking Docker Compose and configuration files..."
        echo ""
        
        # Check for exposed ports
        echo "--- Exposed Ports in Docker Compose ---"
        find . -name "docker-compose*.yml" -exec grep -H "ports:" {} \; 2>/dev/null || echo "No Docker Compose files found"
        echo ""
        
        # Check for SSL/TLS configuration
        echo "--- SSL/TLS Configuration ---"
        grep -r -i "ssl\|tls" --include="*.yml" --include="*.yaml" --include="*.conf" . || echo "None found"
        echo ""
        
        # Check CORS configuration
        echo "--- CORS Configuration ---"
        grep -r -i "cors" --include="*.py" --include="*.js" --include="*.ts" . | head -10 || echo "None found"
        
    } > "$REPORTS_DIR/network-config.txt"
    
    print_success "Network analysis completed"
}

# 8. Generate comprehensive security report
generate_summary_report() {
    print_status "Generating comprehensive security report..."
    
    {
        echo "======================================"
        echo "BenGER Security Scan Summary Report"
        echo "======================================"
        echo "Generated: $(date)"
        echo "Scan ID: $TIMESTAMP"
        echo ""
        
        echo "📊 SCAN OVERVIEW"
        echo "=================="
        echo "✅ Python dependency scan: $([ -f "$REPORTS_DIR/python-security-report.json" ] && echo "Completed" || echo "Failed")"
        echo "✅ Python static analysis: $([ -f "$REPORTS_DIR/bandit-security-report.json" ] && echo "Completed" || echo "Failed")"
        echo "✅ Node.js dependency scan: $([ -f "$REPORTS_DIR/npm-audit-report.json" ] && echo "Completed" || echo "Failed")"
        echo "✅ Secret detection: $([ -f "$REPORTS_DIR/secrets-scan.txt" ] && echo "Completed" || echo "Failed")"
        echo "✅ File permissions: $([ -f "$REPORTS_DIR/file-permissions.txt" ] && echo "Completed" || echo "Failed")"
        echo "✅ Network analysis: $([ -f "$REPORTS_DIR/network-config.txt" ] && echo "Completed" || echo "Failed")"
        echo ""
        
        echo "🔍 CRITICAL FINDINGS"
        echo "===================="
        
        # Check for critical issues in Python dependencies
        if [ -f "$REPORTS_DIR/python-security-report.json" ]; then
            critical_python=$(python3 -c "
import json
try:
    with open('$REPORTS_DIR/python-security-report.json', 'r') as f:
        data = json.load(f)
    if isinstance(data, list):
        critical = [v for v in data if v.get('vulnerability', {}).get('cve', '').startswith('CVE')]
        print(len(critical))
    else:
        print('0')
except:
    print('0')
" 2>/dev/null || echo "0")
            echo "🐍 Python vulnerabilities: $critical_python"
        fi
        
        # Check for high severity Node.js issues
        if [ -f "$REPORTS_DIR/npm-audit-report.json" ]; then
            high_npm=$(python3 -c "
import json
try:
    with open('$REPORTS_DIR/npm-audit-report.json', 'r') as f:
        data = json.load(f)
    high_count = data.get('metadata', {}).get('vulnerabilities', {}).get('high', 0)
    critical_count = data.get('metadata', {}).get('vulnerabilities', {}).get('critical', 0)
    print(high_count + critical_count)
except:
    print('0')
" 2>/dev/null || echo "0")
            echo "📦 Node.js high/critical: $high_npm"
        fi
        
        # Check for potential secrets
        if [ -f "$REPORTS_DIR/secrets-scan.txt" ]; then
            secret_count=$(grep -c "api[_-]key\|password.*=\|token.*=" "$REPORTS_DIR/secrets-scan.txt" || echo "0")
            echo "🔐 Potential secrets: $secret_count"
        fi
        
        echo ""
        echo "📋 RECOMMENDATIONS"
        echo "=================="
        echo "1. Review all HIGH and CRITICAL severity vulnerabilities"
        echo "2. Update dependencies with known security issues"
        echo "3. Verify that detected 'secrets' are not actual credentials"
        echo "4. Ensure sensitive files have proper permissions"
        echo "5. Run security tests: pytest tests/test_security_*.py"
        echo "6. Review network configurations for security best practices"
        echo ""
        
        echo "📁 DETAILED REPORTS"
        echo "==================="
        echo "All detailed reports are available in: $REPORTS_DIR"
        echo "- python-security-report.json/txt"
        echo "- bandit-security-report.json/txt"
        echo "- npm-audit-report.json/txt"
        echo "- secrets-scan.txt"
        echo "- file-permissions.txt"
        echo "- network-config.txt"
        echo ""
        
        echo "🔧 NEXT STEPS"
        echo "============="
        echo "1. Address critical and high severity issues first"
        echo "2. Run performance tests: cd services/api && python -m pytest tests/load/"
        echo "3. Execute comprehensive security tests"
        echo "4. Update this scan result in GitHub Issue #368"
        
    } > "$REPORTS_DIR/SECURITY_SUMMARY.md"
    
    print_success "Summary report generated: $REPORTS_DIR/SECURITY_SUMMARY.md"
}

# Main execution
main() {
    echo "🚀 Starting comprehensive security scan..."
    echo ""
    
    # Create report header
    echo "# BenGER Security Scan Report" > "$REPORTS_DIR/README.md"
    echo "Generated on: $(date)" >> "$REPORTS_DIR/README.md"
    echo "" >> "$REPORTS_DIR/README.md"
    
    # Run all scans
    scan_python_dependencies || print_error "Python dependency scan failed"
    echo ""
    
    scan_python_code || print_error "Python static analysis failed"
    echo ""
    
    scan_nodejs_dependencies || print_error "Node.js dependency scan failed"
    echo ""
    
    scan_docker_images || print_warning "Docker image scanning skipped"
    echo ""
    
    scan_for_secrets || print_error "Secret scanning failed"
    echo ""
    
    check_file_permissions || print_error "File permission check failed"
    echo ""
    
    analyze_network_config || print_error "Network analysis failed"
    echo ""
    
    generate_summary_report
    echo ""
    
    print_success "🎉 Security scan completed!"
    print_status "📊 View summary: cat $REPORTS_DIR/SECURITY_SUMMARY.md"
    print_status "📁 Full reports: ls $REPORTS_DIR/"
    
    # Display quick summary
    echo ""
    echo "📋 QUICK SUMMARY:"
    if [ -f "$REPORTS_DIR/SECURITY_SUMMARY.md" ]; then
        grep -A 10 "🔍 CRITICAL FINDINGS" "$REPORTS_DIR/SECURITY_SUMMARY.md" || echo "Summary not available"
    fi
}

# Trap to cleanup on exit
trap 'print_status "Scan interrupted"' INT TERM

# Run main function
main "$@"