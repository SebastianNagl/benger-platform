#!/bin/bash

# Setup script for Postal mail service integration
# This script helps initialize and test the Postal mail server

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
INFRA_DIR="$PROJECT_ROOT/infra"

echo "========================================="
echo "BenGER Postal Mail Service Setup"
echo "========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running from correct directory
if [ ! -f "$INFRA_DIR/docker-compose.yml" ]; then
    echo -e "${RED}Error: Could not find docker-compose.yml in infra directory${NC}"
    echo "Please run this script from the project root or scripts directory"
    exit 1
fi

cd "$INFRA_DIR"

echo "Step 1: Starting services with Postal..."
echo "-----------------------------------------"

# Check if Postal services are already running
if docker-compose ps | grep -q "postal"; then
    echo -e "${YELLOW}Postal services appear to be running already${NC}"
    read -p "Do you want to restart them? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Stopping existing services..."
        docker-compose -f docker-compose.yml -f docker-compose.postal.yml down
    fi
fi

echo "Starting services with Postal..."
docker-compose -f docker-compose.yml -f docker-compose.postal.yml up -d

echo -e "${GREEN}✓ Services started${NC}"
echo ""

echo "Step 2: Waiting for services to be healthy..."
echo "----------------------------------------------"

# Wait for Postal to be healthy
MAX_ATTEMPTS=30
ATTEMPT=0

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    if docker-compose exec -T postal curl -f http://localhost:5000/health 2>/dev/null; then
        echo -e "${GREEN}✓ Postal is healthy${NC}"
        break
    fi
    echo "Waiting for Postal to start... (attempt $((ATTEMPT+1))/$MAX_ATTEMPTS)"
    sleep 5
    ATTEMPT=$((ATTEMPT+1))
done

if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
    echo -e "${RED}Error: Postal failed to start within expected time${NC}"
    exit 1
fi

echo ""
echo "Step 3: Initializing Postal (if needed)..."
echo "--------------------------------------------"

# Check if Postal is already initialized
if docker-compose exec -T postal postal status 2>/dev/null | grep -q "running"; then
    echo -e "${YELLOW}Postal appears to be already initialized${NC}"
else
    echo "Initializing Postal..."
    docker-compose exec -T postal postal initialize || true
    echo -e "${GREEN}✓ Postal initialized${NC}"
fi

echo ""
echo "Step 4: Creating Postal organization and server..."
echo "---------------------------------------------------"

# Note: This requires manual interaction
echo -e "${YELLOW}Manual setup required:${NC}"
echo ""
echo "1. Access Postal Web UI at: http://postal.localhost"
echo ""
echo "2. Create an admin user (if not already done):"
echo "   Run: docker-compose exec postal postal make-user"
echo ""
echo "3. Login and create:"
echo "   - Organization: 'BenGER' (permalink: 'benger')"
echo "   - Server: 'BenGER Mail' (short name: 'benger')"
echo "   - Domain: 'what-a-benger.net' or 'localhost' for dev"
echo ""
echo "4. Generate an API key:"
echo "   - Go to Server → Credentials → API Keys"
echo "   - Create new API key with full permissions"
echo "   - Copy the API key"
echo ""
echo "5. Update your .env file with:"
echo "   POSTAL_API_KEY=<your-api-key>"
echo "   POSTAL_ENABLED=true"
echo ""

read -p "Press Enter when you've completed the manual setup..."

echo ""
echo "Step 5: Running database migration for feature flag..."
echo "-------------------------------------------------------"

# Run the migration to add the Postal feature flag
docker-compose exec -T api alembic upgrade head
echo -e "${GREEN}✓ Database migrations applied${NC}"

echo ""
echo "Step 6: Enabling Postal feature flag..."
echo "----------------------------------------"

# Enable the Postal feature flag via SQL
docker-compose exec -T db psql -U postgres -d benger -c \
    "UPDATE feature_flags SET is_enabled = true WHERE name = 'API_POSTAL_MAIL_SERVICE';" 2>/dev/null || {
    echo -e "${YELLOW}Note: Feature flag will be available after first API start${NC}"
}

echo -e "${GREEN}✓ Feature flag enabled${NC}"

echo ""
echo "Step 7: Testing email configuration..."
echo "----------------------------------------"

# Test the email health endpoint
echo "Testing email health endpoint..."
HEALTH_RESPONSE=$(docker-compose exec -T api curl -s http://localhost:8000/health/email 2>/dev/null || echo "{}")

if echo "$HEALTH_RESPONSE" | grep -q '"status":"healthy"'; then
    echo -e "${GREEN}✓ Email service is healthy${NC}"
else
    echo -e "${YELLOW}⚠ Email service health check failed${NC}"
    echo "Response: $HEALTH_RESPONSE"
    echo ""
    echo "This is expected if you haven't configured the API key yet."
fi

echo ""
echo "========================================="
echo "Setup Complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. Ensure POSTAL_API_KEY is set in your .env file"
echo "2. Restart the API service: docker-compose restart api"
echo "3. Access the admin panel at http://benger.localhost/admin/feature-flags"
echo "4. Enable the 'API_POSTAL_MAIL_SERVICE' feature flag"
echo "5. Test email sending via the health endpoint:"
echo "   curl http://api.localhost/health/email?test_email=your@email.com"
echo ""
echo "Postal Web UI: http://postal.localhost"
echo "BenGER Application: http://benger.localhost"
echo ""