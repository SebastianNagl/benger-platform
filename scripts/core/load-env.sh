#!/bin/bash

# Script to load environment configuration

# Usage: source scripts/core/load-env.sh [environment]
# Example: source scripts/core/load-env.sh development

ENVIRONMENT=${1:-development}
CONFIG_DIR="infra/config"

echo "🔧 Loading configuration for: $ENVIRONMENT"

# Check if running from project root
if [ ! -f "$CONFIG_DIR/base.env" ]; then
    echo "❌ Error: Must run from project root directory"
    return 1 2>/dev/null || exit 1
fi

# Check if environment file exists
if [ ! -f "$CONFIG_DIR/$ENVIRONMENT.env" ]; then
    echo "❌ Error: Configuration not found for environment: $ENVIRONMENT"
    echo "Available environments:"
    ls -1 $CONFIG_DIR/*.env | grep -v base.env | sed 's/.*\///' | sed 's/\.env//'
    return 1 2>/dev/null || exit 1
fi

# Function to load env file
load_env_file() {
    local file=$1
    if [ -f "$file" ]; then
        echo "  Loading: $file"
        set -a  # Mark variables for export
        source "$file"
        set +a  # Stop marking for export
    fi
}

# Load configuration in order
echo "📋 Loading configuration files:"
load_env_file "$CONFIG_DIR/base.env"
load_env_file "$CONFIG_DIR/$ENVIRONMENT.env"

# Load local overrides if they exist
if [ -f ".env.local" ]; then
    echo "  Loading: .env.local (local overrides)"
    load_env_file ".env.local"
fi

# Load secrets if available
SECRETS_FILE="$CONFIG_DIR/secrets/$ENVIRONMENT.env"
if [ -f "$SECRETS_FILE" ]; then
    echo "  Loading: $SECRETS_FILE (secrets)"
    load_env_file "$SECRETS_FILE"
else
    echo "  ⚠️  No secrets file found at: $SECRETS_FILE"
fi

# Generate derived values
export DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"
export REDIS_URL="redis://${REDIS_HOST}:${REDIS_PORT}/${REDIS_DB}"

# Validation
echo ""
echo "✅ Configuration loaded for: $ENVIRONMENT"
echo "   API URL: $API_BASE_URL"
echo "   Frontend URL: $FRONTEND_URL"
echo "   Database: $POSTGRES_HOST:$POSTGRES_PORT/$POSTGRES_DB"
echo "   Redis: $REDIS_HOST:$REDIS_PORT"

# Check for missing required secrets
MISSING_SECRETS=()
[ -z "$POSTGRES_PASSWORD" ] && MISSING_SECRETS+=("POSTGRES_PASSWORD")
[ -z "$JWT_SECRET_KEY" ] && MISSING_SECRETS+=("JWT_SECRET_KEY")

if [ ${#MISSING_SECRETS[@]} -gt 0 ]; then
    echo ""
    echo "⚠️  Warning: Missing required secrets:"
    printf '   - %s\n' "${MISSING_SECRETS[@]}"
    echo "   Add these to .env.local or $SECRETS_FILE"
fi