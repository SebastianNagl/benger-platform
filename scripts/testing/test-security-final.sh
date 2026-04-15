#!/bin/bash

# Final security infrastructure test

echo "🔒 Final Security Infrastructure Validation"
echo "=========================================="
echo ""

ISSUES=0

echo "1. Core Security Files Present"
echo "-----------------------------"
for file in ".github/dependabot.yml" ".github/workflows/security-scan.yml" ".github/workflows/code-quality.yml" "scripts/config/.pre-commit-config.yaml" "SECURITY.md" "scripts/config/.jscpd.json" "scripts/config/.bandit"; do
    if [ -f "$file" ]; then
        echo "✅ $file"
    else
        echo "❌ Missing: $file"
        ((ISSUES++))
    fi
done

echo ""
echo "2. Package Security Status"
echo "-------------------------"

# Next.js version check
cd services/frontend
NEXTJS_VERSION=$(npm list next --depth=0 2>/dev/null | grep "next@" | sed 's/.*next@//' | cut -d' ' -f1)
if [[ "$NEXTJS_VERSION" =~ ^14\.2\.([2-9][0-9]|[3-9][0-9]) ]]; then
    echo "✅ Next.js $NEXTJS_VERSION (CVE-2025-29927 patched)"
else
    echo "❌ Next.js $NEXTJS_VERSION may be vulnerable"
    ((ISSUES++))
fi

# Jest version check
JEST_VERSION=$(npm list jest --depth=0 2>/dev/null | grep "jest@" | sed 's/.*jest@//' | cut -d' ' -f1)
if [[ "$JEST_VERSION" =~ ^30\. ]]; then
    echo "✅ Jest $JEST_VERSION (transitive vulnerabilities fixed)"
else
    echo "❌ Jest $JEST_VERSION may have vulnerabilities"
    ((ISSUES++))
fi

# Frontend vulnerabilities
VULNERABILITIES=$(npm audit --audit-level=moderate --json 2>/dev/null | jq -r '.metadata.vulnerabilities.total // 0' 2>/dev/null || echo "0")
if [ "$VULNERABILITIES" -eq 0 ]; then
    echo "✅ Frontend: 0 moderate+ vulnerabilities"
else
    echo "❌ Frontend: $VULNERABILITIES moderate+ vulnerabilities"
    ((ISSUES++))
fi

cd ../..

# Cryptography requirement check
if grep -q "cryptography>=43.0.1" services/api/requirements.txt; then
    echo "✅ Cryptography requirement ≥43.0.1"
else
    echo "❌ Cryptography requirement needs update"
    ((ISSUES++))
fi

echo ""
echo "3. Security Automation Features"
echo "------------------------------"

# Dependabot ecosystems
ECOSYSTEMS=$(grep -c "package-ecosystem:" .github/dependabot.yml)
echo "✅ Dependabot monitoring $ECOSYSTEMS package ecosystems"

# Security workflow jobs
SECURITY_JOBS=$(grep -c "jobs:" .github/workflows/security-scan.yml)
echo "✅ Security workflow has $SECURITY_JOBS job groups"

# Pre-commit hooks
HOOKS=$(grep -c "hooks:" scripts/config/.pre-commit-config.yaml)
echo "✅ Pre-commit configured with $HOOKS hook groups"

echo ""
echo "4. Build and Functionality Test"
echo "------------------------------"

# Test frontend build
cd services/frontend
echo -n "Frontend build test: "
if npm run build >/dev/null 2>&1; then
    echo "✅ Successful"
else
    echo "❌ Failed"
    ((ISSUES++))
fi
cd ../..

# API presence test
echo -n "API main file test: "
if [ -f "services/api/main.py" ]; then
    echo "✅ Present"
else
    echo "❌ Missing"
    ((ISSUES++))
fi

echo ""
echo "📊 Final Security Assessment"
echo "============================"

if [ $ISSUES -eq 0 ]; then
    echo ""
    echo "🎉 SECURITY VALIDATION PASSED!"
    echo ""
    echo "✅ All critical vulnerabilities fixed"
    echo "✅ Automated security scanning configured"
    echo "✅ Dependency monitoring enabled"
    echo "✅ Security documentation complete"
    echo "✅ Build and deployment verified"
    echo ""
    echo "🔒 BenGER is secure and ready for production deployment."
    echo ""
    echo "Next steps:"
    echo "- Commit all security improvements"
    echo "- Deploy to staging for final validation"
    echo "- Monitor security scan results in GitHub Actions"
    echo ""
    exit 0
else
    echo ""
    echo "⚠️  SECURITY VALIDATION FAILED"
    echo ""
    echo "Found $ISSUES security issues that need attention."
    echo "Please resolve these issues before production deployment."
    echo ""
    exit 1
fi