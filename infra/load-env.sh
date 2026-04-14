#!/bin/bash

# Centralized configuration loader for BenGER
# Usage: source infra/load-env.sh [environment]
#
# Environments: development, staging, production
# Default: development

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/config"

# Default to development if no environment specified
ENVIRONMENT="${1:-development}"

# Validate environment
case "$ENVIRONMENT" in
    development|staging|production)
        ;;
    *)
        echo "❌ Invalid environment: $ENVIRONMENT"
        echo "Valid environments: development, staging, production"
        return 1 2>/dev/null || exit 1
        ;;
esac

# Check if config directory exists
if [ ! -d "$CONFIG_DIR" ]; then
    echo "❌ Configuration directory not found: $CONFIG_DIR"
    return 1 2>/dev/null || exit 1
fi

# Load base configuration first
BASE_CONFIG="$CONFIG_DIR/base.env"
if [ -f "$BASE_CONFIG" ]; then
    echo "📄 Loading base configuration..."
    set -a  # automatically export all variables
    source "$BASE_CONFIG"
    set +a
else
    echo "❌ Base configuration not found: $BASE_CONFIG"
    return 1 2>/dev/null || exit 1
fi

# Load environment-specific configuration
ENV_CONFIG="$CONFIG_DIR/$ENVIRONMENT.env"
if [ -f "$ENV_CONFIG" ]; then
    echo "📄 Loading $ENVIRONMENT configuration..."
    set -a  # automatically export all variables
    source "$ENV_CONFIG"
    set +a
else
    echo "❌ Environment configuration not found: $ENV_CONFIG"
    return 1 2>/dev/null || exit 1
fi

# Set ENVIRONMENT variable for runtime detection
export ENVIRONMENT="$ENVIRONMENT"

echo "✅ Configuration loaded for environment: $ENVIRONMENT"

# Optional: Show loaded key variables (without sensitive values)
if [ "${SHOW_CONFIG:-false}" = "true" ]; then
    echo ""
    echo "📋 Configuration summary:"
    echo "  Environment: $ENVIRONMENT"
    echo "  Database: $POSTGRES_DB"
    echo "  API Host: $API_HOST"
    echo "  Frontend Host: $FRONTEND_HOST"
    echo "  Redis: $REDIS_HOST:$REDIS_PORT"
    echo ""
fi