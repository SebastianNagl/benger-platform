#!/bin/bash

# Deploy script using centralized configuration

set -e

ENVIRONMENT=${1:-development}
ACTION=${2:-up}

echo "🚀 BenGER Deployment with Centralized Configuration"
echo "=================================================="
echo "Environment: $ENVIRONMENT"
echo "Action: $ACTION"
echo ""

# Validate environment
if [ ! -f "infra/config/$ENVIRONMENT.env" ]; then
    echo "❌ Error: Environment '$ENVIRONMENT' not found"
    echo "Available environments:"
    ls -1 infra/config/*.env | grep -v base.env | sed 's/.*\///' | sed 's/\.env//'
    exit 1
fi

# Load and validate configuration
echo "🔧 Loading configuration..."
source scripts/core/load-env.sh $ENVIRONMENT

echo ""
echo "🔍 Validating configuration..."
if ! ./scripts/core/validate-config.sh $ENVIRONMENT; then
    echo "❌ Configuration validation failed. Aborting deployment."
    exit 1
fi

# Create .env file for Docker Compose
echo ""
echo "📝 Generating Docker Compose .env file..."
cat > infra/.env << EOF
# Generated configuration for Docker Compose
# Environment: $ENVIRONMENT
# Generated: $(date)

# Export all configuration variables
$(env | grep -E '^(POSTGRES_|REDIS_|API_|FRONTEND_|JWT_|ENVIRONMENT|DEBUG)' | sort)
EOF

echo "✅ Docker Compose .env file created"

# Environment-specific actions
case $ENVIRONMENT in
    "development")
        echo ""
        echo "🏗️  Development deployment..."
        cd infra
        docker-compose -f docker-compose.yml -f docker-compose.development.yml $ACTION
        ;;
    "staging")
        echo ""
        echo "🔬 Staging deployment..."
        cd infra
        docker-compose -f docker-compose.yml -f docker-compose.staging.yml $ACTION
        ;;
    "production")
        echo ""
        echo "🏭 Production deployment..."
        echo "⚠️  Warning: Deploying to production!"
        read -p "Are you sure? (yes/no): " confirm
        if [ "$confirm" != "yes" ]; then
            echo "Deployment cancelled."
            exit 1
        fi
        cd infra
        docker-compose -f docker-compose.yml -f docker-compose.production.yml $ACTION
        ;;
    *)
        echo "❌ Unknown environment: $ENVIRONMENT"
        exit 1
        ;;
esac

if [ "$ACTION" = "up" ] || [ "$ACTION" = "" ]; then
    echo ""
    echo "🎯 Post-deployment checks..."
    sleep 5
    
    # Health checks
    echo "Checking API health..."
    if curl -f $API_BASE_URL/health >/dev/null 2>&1; then
        echo "✅ API is healthy"
    else
        echo "⚠️  API health check failed"
    fi
    
    echo ""
    echo "✅ Deployment complete!"
    echo ""
    echo "🔗 Access URLs:"
    echo "   Frontend: $FRONTEND_URL"
    echo "   API: $API_BASE_URL"
    echo "   Label Studio: $LABEL_STUDIO_URL"
    
    if [ "$ENVIRONMENT" = "development" ]; then
        echo ""
        echo "💡 Development Tips:"
        echo "   - View logs: docker-compose logs -f"
        echo "   - Rebuild: docker-compose build"
        echo "   - Restart service: docker-compose restart api"
    fi
fi