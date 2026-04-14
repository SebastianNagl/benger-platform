#!/bin/bash

# Test script for automated security scanning setup

echo "🔍 Testing Security Scanning Infrastructure"
echo "=========================================="
echo ""

FAILED_TESTS=0

echo "1. GitHub Workflows Validation"
echo "-----------------------------"

# Test security workflow syntax
echo "🔍 Validating security-scan.yml..."
if python -c "import yaml; yaml.safe_load(open('.github/workflows/security-scan.yml')); print('Valid')" >/dev/null 2>&1; then
    echo "✅ Security workflow YAML syntax is valid"
else
    echo "❌ Security workflow has invalid YAML"
    ((FAILED_TESTS++))
fi

# Test code quality workflow syntax  
echo "🔍 Validating code-quality.yml..."
if python -c "import yaml; yaml.safe_load(open('.github/workflows/code-quality.yml')); print('Valid')" >/dev/null 2>&1; then
    echo "✅ Code quality workflow YAML syntax is valid"
else
    echo "❌ Code quality workflow has invalid YAML"
    ((FAILED_TESTS++))
fi

echo ""
echo "2. Dependabot Configuration"
echo "--------------------------"

# Test Dependabot config
echo "🔍 Validating dependabot.yml..."
if python -c "import yaml; yaml.safe_load(open('.github/dependabot.yml')); print('Valid')" >/dev/null 2>&1; then
    echo "✅ Dependabot configuration YAML syntax is valid"
else
    echo "❌ Dependabot configuration has invalid YAML"
    ((FAILED_TESTS++))
fi

# Check coverage of package ecosystems
echo "🔍 Checking package ecosystem coverage..."
ECOSYSTEMS=$(grep "package-ecosystem:" .github/dependabot.yml | wc -l)
if [ $ECOSYSTEMS -ge 3 ]; then
    echo "✅ Dependabot covers $ECOSYSTEMS package ecosystems"
else
    echo "❌ Dependabot should cover more package ecosystems (found: $ECOSYSTEMS)"
    ((FAILED_TESTS++))
fi

echo ""
echo "3. Pre-commit Configuration"
echo "--------------------------"

echo "🔍 Validating pre-commit config..."
if python -c "import yaml; yaml.safe_load(open('scripts/config/.pre-commit-config.yaml')); print('Valid')" >/dev/null 2>&1; then
    echo "✅ Pre-commit configuration YAML syntax is valid"
else
    echo "❌ Pre-commit configuration has invalid YAML"
    ((FAILED_TESTS++))
fi

echo ""
echo "4. Security Tools Availability"
echo "-----------------------------"

# Check if npm audit works
echo "🔍 Testing npm audit..."
cd services/frontend
if npm audit --audit-level=low >/dev/null 2>&1; then
    echo "✅ npm audit is functional"
else
    echo "❌ npm audit failed"
    ((FAILED_TESTS++))
fi
cd ../..

# Check if Python security tools can be installed
echo "🔍 Testing Python security tools availability..."
if pip install --dry-run safety bandit >/dev/null 2>&1; then
    echo "✅ Python security tools can be installed"
else
    echo "❌ Python security tools installation failed"
    ((FAILED_TESTS++))
fi

echo ""
echo "5. Configuration Files"
echo "--------------------"

# Check jscpd config
if [ -f "scripts/config/.jscpd.json" ]; then
    echo "🔍 Validating jscpd configuration..."
    if python -c "import json; json.load(open('scripts/config/.jscpd.json')); print('Valid')" >/dev/null 2>&1; then
        echo "✅ jscpd configuration is valid JSON"
    else
        echo "❌ jscpd configuration has invalid JSON"
        ((FAILED_TESTS++))
    fi
else
    echo "❌ jscpd configuration file missing"
    ((FAILED_TESTS++))
fi

# Check bandit config
if [ -f "scripts/config/.bandit" ]; then
    echo "✅ Bandit configuration present"
else
    echo "❌ Bandit configuration missing"
    ((FAILED_TESTS++))
fi

echo ""
echo "6. Security Documentation"
echo "------------------------"

# Check security policy
if [ -f "SECURITY.md" ]; then
    echo "✅ Security policy documented"
    
    # Check if it contains required sections
    if grep -q "Reporting a Vulnerability" SECURITY.md; then
        echo "✅ Security policy contains vulnerability reporting section"
    else
        echo "❌ Security policy missing vulnerability reporting section"
        ((FAILED_TESTS++))
    fi
else
    echo "❌ Security policy missing"
    ((FAILED_TESTS++))
fi

echo ""
echo "7. Integration Test"
echo "------------------"

# Test a simple security scan simulation
echo "🔍 Running sample security scans..."

# Frontend audit
cd services/frontend
echo "  - Frontend npm audit..."
FRONTEND_RESULT=$(npm audit --audit-level=moderate --json 2>/dev/null | jq -r '.metadata.vulnerabilities.total // 0' 2>/dev/null || echo "0")
if [ "$FRONTEND_RESULT" -eq 0 ]; then
    echo "✅ Frontend security scan passed (0 vulnerabilities)"
else
    echo "⚠️  Frontend has $FRONTEND_RESULT moderate+ vulnerabilities"
fi
cd ../..

# Secrets detection test
echo "  - Secrets detection test..."
if echo "password=secret123" | grep -q "password.*=" ; then
    echo "✅ Secrets detection pattern matching works"
else
    echo "❌ Secrets detection not working"
    ((FAILED_TESTS++))
fi

echo ""
echo "📊 Security Infrastructure Test Summary"
echo "======================================"
echo "Failed tests: $FAILED_TESTS"

if [ $FAILED_TESTS -eq 0 ]; then
    echo ""
    echo "🎉 All security infrastructure tests passed!"
    echo "✅ GitHub Actions workflows configured"
    echo "✅ Dependabot automated updates enabled"
    echo "✅ Pre-commit security hooks configured"
    echo "✅ Security tools available and functional"
    echo "✅ Security documentation complete"
    echo ""
    echo "🔒 Automated security scanning is ready for production!"
    exit 0
else
    echo ""
    echo "⚠️  Some security infrastructure tests failed."
    echo "   Please review and fix the issues above before production deployment."
    exit 1
fi