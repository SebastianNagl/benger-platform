#!/bin/bash

# Script to validate configuration

ENVIRONMENT=${1:-development}
CONFIG_DIR="infra/config"

echo "🔍 Validating configuration for: $ENVIRONMENT"
echo "========================================"

# Load configuration
source scripts/core/load-env.sh $ENVIRONMENT > /dev/null 2>&1

ERRORS=0
WARNINGS=0

# Function to check required variable
check_required() {
    local var_name=$1
    local var_value=${!var_name}
    
    if [ -z "$var_value" ]; then
        echo "❌ Missing required: $var_name"
        ((ERRORS++))
        return 1
    else
        echo "✅ $var_name is set"
        return 0
    fi
}

# Function to check optional variable
check_optional() {
    local var_name=$1
    local var_value=${!var_name}
    
    if [ -z "$var_value" ]; then
        echo "⚠️  Missing optional: $var_name"
        ((WARNINGS++))
    else
        echo "✅ $var_name is set"
    fi
}

# Function to validate format
validate_format() {
    local var_name=$1
    local pattern=$2
    local var_value=${!var_name}
    
    if [ -n "$var_value" ] && ! [[ "$var_value" =~ $pattern ]]; then
        echo "❌ Invalid format for $var_name: $var_value"
        ((ERRORS++))
        return 1
    fi
    return 0
}

echo ""
echo "📋 Required Variables:"
echo "--------------------"
check_required "ENVIRONMENT"
check_required "POSTGRES_HOST"
check_required "POSTGRES_PORT"
check_required "POSTGRES_DB"
check_required "POSTGRES_USER"
check_required "POSTGRES_PASSWORD"
check_required "REDIS_HOST"
check_required "REDIS_PORT"
check_required "JWT_SECRET_KEY"
check_required "API_BASE_URL"
check_required "FRONTEND_URL"

echo ""
echo "📋 Optional Variables:"
echo "--------------------"
check_optional "OPENAI_API_KEY"
check_optional "ANTHROPIC_API_KEY"
check_optional "GOOGLE_API_KEY"
check_optional "LABEL_STUDIO_API_KEY"
check_optional "SENTRY_DSN"
check_optional "SMTP_HOST"

echo ""
echo "🔍 Format Validation:"
echo "-------------------"
validate_format "API_PORT" "^[0-9]+$"
validate_format "POSTGRES_PORT" "^[0-9]+$"
validate_format "REDIS_PORT" "^[0-9]+$"
validate_format "JWT_EXPIRATION_HOURS" "^[0-9]+$"
validate_format "DEBUG" "^(true|false)$"

echo ""
echo "🔒 Security Checks:"
echo "------------------"

# Check for hardcoded secrets
if grep -q "password\|secret\|key" "$CONFIG_DIR/$ENVIRONMENT.env" 2>/dev/null; then
    echo "⚠️  Warning: Possible secrets in $ENVIRONMENT.env"
    ((WARNINGS++))
else
    echo "✅ No obvious secrets in environment file"
fi

# Check JWT secret strength
if [ -n "$JWT_SECRET_KEY" ] && [ ${#JWT_SECRET_KEY} -lt 32 ]; then
    echo "⚠️  Warning: JWT_SECRET_KEY should be at least 32 characters"
    ((WARNINGS++))
else
    echo "✅ JWT_SECRET_KEY length is sufficient"
fi

# Production-specific checks
if [ "$ENVIRONMENT" = "production" ]; then
    echo ""
    echo "🏭 Production Checks:"
    echo "-------------------"
    
    if [ "$DEBUG" = "true" ]; then
        echo "❌ DEBUG must be false in production"
        ((ERRORS++))
    else
        echo "✅ DEBUG is false"
    fi
    
    if [ "$USE_MOCK_EMAIL" = "true" ]; then
        echo "⚠️  Warning: Mock email enabled in production"
        ((WARNINGS++))
    fi
    
    if [ "$ENABLE_SWAGGER" = "true" ]; then
        echo "⚠️  Warning: Swagger enabled in production"
        ((WARNINGS++))
    fi
fi

echo ""
echo "📊 Summary:"
echo "----------"
echo "Environment: $ENVIRONMENT"
echo "Errors: $ERRORS"
echo "Warnings: $WARNINGS"

if [ $ERRORS -gt 0 ]; then
    echo ""
    echo "❌ Configuration validation failed!"
    exit 1
else
    echo ""
    echo "✅ Configuration is valid!"
    if [ $WARNINGS -gt 0 ]; then
        echo "   (with $WARNINGS warnings - review above)"
    fi
    exit 0
fi