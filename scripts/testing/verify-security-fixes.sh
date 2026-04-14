#!/bin/bash

# Script to verify all security fixes are properly applied

echo "🔐 BenGER Security Verification"
echo "============================="
echo ""

FAILED_CHECKS=0

# Function to check and report
check_security() {
    local check_name="$1"
    local command="$2"
    local expected="$3"
    
    echo -n "🔍 $check_name: "
    
    if eval "$command" >/dev/null 2>&1; then
        echo "✅ PASS"
    else
        echo "❌ FAIL"
        ((FAILED_CHECKS++))
    fi
}

echo "1. Next.js CVE-2025-29927 Fix Verification"
echo "------------------------------------------"

# Check Next.js version
NEXTJS_VERSION=$(cd services/frontend && npm list next --depth=0 2>/dev/null | grep "next@" | sed 's/.*next@//' | cut -d' ' -f1)
echo "Current Next.js version: $NEXTJS_VERSION"

if [[ "$NEXTJS_VERSION" =~ ^14\.2\.(2[5-9]|[3-9][0-9]) ]]; then
    echo "✅ Next.js version $NEXTJS_VERSION includes CVE-2025-29927 fix"
else
    echo "❌ Next.js version $NEXTJS_VERSION may be vulnerable to CVE-2025-29927"
    ((FAILED_CHECKS++))
fi

# Check for vulnerabilities
echo ""
echo "🔍 Frontend vulnerability scan..."
cd services/frontend
FRONTEND_VULNS=$(npm audit --audit-level=moderate --json 2>/dev/null | jq -r '.metadata.vulnerabilities.total // 0' 2>/dev/null || echo "0")
if [ "$FRONTEND_VULNS" -eq 0 ]; then
    echo "✅ No moderate+ vulnerabilities found in frontend"
else
    echo "❌ Found $FRONTEND_VULNS moderate+ vulnerabilities in frontend"
    ((FAILED_CHECKS++))
fi

cd ../..

echo ""
echo "2. Cryptography Package Fix Verification"
echo "----------------------------------------"

# Check cryptography version in requirements
echo "Checking cryptography requirement in services/api/requirements.txt..."
if grep -q "cryptography>=43.0.1" services/api/requirements.txt; then
    echo "✅ Cryptography requirement updated to >=43.0.1"
elif grep -q "cryptography>=43.0.0" services/api/requirements.txt; then
    echo "⚠️  Cryptography requirement found but should be >=43.0.1"
    ((FAILED_CHECKS++))
else
    echo "❌ Cryptography requirement not found or incorrect"
    ((FAILED_CHECKS++))
fi

echo ""
echo "3. Jest Vulnerability Fix Verification"
echo "-------------------------------------"

cd services/frontend
JEST_VERSION=$(npm list jest --depth=0 2>/dev/null | grep "jest@" | sed 's/.*jest@//' | cut -d' ' -f1)
echo "Current Jest version: $JEST_VERSION"

if [[ "$JEST_VERSION" =~ ^30\. ]]; then
    echo "✅ Jest updated to version $JEST_VERSION"
else
    echo "❌ Jest version $JEST_VERSION may have transitive vulnerabilities"
    ((FAILED_CHECKS++))
fi

cd ../..

echo ""
echo "4. Security Infrastructure Verification"
echo "--------------------------------------"

# Check Dependabot configuration
if [ -f ".github/dependabot.yml" ]; then
    echo "✅ Dependabot configuration present"
else
    echo "❌ Dependabot configuration missing"
    ((FAILED_CHECKS++))
fi

# Check security workflow
if [ -f ".github/workflows/security-scan.yml" ]; then
    echo "✅ Security scanning workflow present"
else
    echo "❌ Security scanning workflow missing"
    ((FAILED_CHECKS++))
fi

# Check pre-commit config
if [ -f "scripts/config/.pre-commit-config.yaml" ]; then
    echo "✅ Pre-commit security hooks configured"
else
    echo "❌ Pre-commit security hooks missing"
    ((FAILED_CHECKS++))
fi

# Check security policy
if [ -f "SECURITY.md" ]; then
    echo "✅ Security policy documented"
else
    echo "❌ Security policy missing"
    ((FAILED_CHECKS++))
fi

echo ""
echo "5. Build and Functionality Verification"
echo "--------------------------------------"

# Test frontend build
echo "🔍 Testing frontend build..."
cd services/frontend
if npm run build >/dev/null 2>&1; then
    echo "✅ Frontend builds successfully"
else
    echo "❌ Frontend build failed"
    ((FAILED_CHECKS++))
fi

cd ../..

# Test API syntax
echo "🔍 Testing API syntax..."
if python -m py_compile services/api/main.py; then
    echo "✅ API Python syntax valid"
else
    echo "❌ API has syntax errors"
    ((FAILED_CHECKS++))
fi

echo ""
echo "📊 Security Verification Summary"
echo "================================"
echo "Total failed checks: $FAILED_CHECKS"

if [ $FAILED_CHECKS -eq 0 ]; then
    echo ""
    echo "🎉 All security fixes verified successfully!"
    echo "✅ CVE-2025-29927 (Next.js) - FIXED"
    echo "✅ Cryptography vulnerability - FIXED" 
    echo "✅ Jest transitive dependencies - FIXED"
    echo "✅ Security infrastructure - IMPLEMENTED"
    echo "✅ Build functionality - VERIFIED"
    echo ""
    echo "🔒 BenGER is now secure and ready for production."
    exit 0
else
    echo ""
    echo "⚠️  Some security checks failed. Please review and fix the issues above."
    exit 1
fi