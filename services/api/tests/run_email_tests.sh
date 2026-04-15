#!/bin/bash

# Run Email Service Tests
# This script runs all email-related tests including unit, integration, and e2e tests
# Tests are configured for the final email setup where both production and staging
# use the same verified sender address (noreply@what-a-benger.net) with different sender names

set -e

echo "Running Email Service Tests..."
echo "=============================="

# Change to API directory
cd "$(dirname "$0")/.."

# Run unit tests for SendGrid client
echo ""
echo "1. Running SendGrid Client Unit Tests..."
echo "-----------------------------------------"
pytest tests/unit/test_sendgrid_client.py -v --tb=short

# Run unit tests for email service
echo ""
echo "2. Running Email Service Unit Tests..."
echo "---------------------------------------"
pytest tests/unit/test_email_service.py -v --tb=short

# Run integration tests for email service
echo ""
echo "3. Running Email Service Integration Tests..."
echo "----------------------------------------------"
pytest tests/integration/test_email_service_integration.py -v --tb=short

# Run e2e tests for email verification
echo ""
echo "4. Running Email Verification E2E Tests..."
echo "-------------------------------------------"
pytest tests/e2e/test_email_verification_e2e.py -v --tb=short

# Run existing email verification tests
echo ""
echo "5. Running Existing Email Verification Tests..."
echo "------------------------------------------------"
pytest tests/test_email_verification*.py -v --tb=short

echo ""
echo "=============================="
echo "All Email Tests Completed!"
echo "=============================="

# Generate coverage report if coverage is installed
if command -v coverage &> /dev/null; then
    echo ""
    echo "Generating Coverage Report..."
    echo "-----------------------------"
    coverage run -m pytest tests/unit/test_sendgrid_client.py tests/unit/test_email_service.py tests/e2e/test_email_verification_e2e.py
    coverage report -m --include="*email*,*sendgrid*"
fi