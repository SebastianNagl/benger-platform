#!/bin/bash

# BenGER Code Formatting Script
# This script formats Python code using black, isort, and autoflake
# Run this manually before committing code

set -e

echo "🎨 Formatting BenGER codebase..."

# Change to project root
cd "$(dirname "$0")/.."

# Format API code
echo "📁 Formatting API code..."
if [ -d "services/api" ]; then
    echo "  - Running black..."
    black --line-length=88 services/api
    
    echo "  - Running isort..."
    isort --profile=black services/api
    
    echo "  - Running autoflake..."
    autoflake --remove-all-unused-imports --remove-unused-variables --in-place --recursive services/api
fi

# Format Workers code
echo "📁 Formatting Workers code..."
if [ -d "services/workers" ]; then
    echo "  - Running black..."
    black --line-length=88 services/workers
    
    echo "  - Running isort..."
    isort --profile=black services/workers
    
    echo "  - Running autoflake..."
    autoflake --remove-all-unused-imports --remove-unused-variables --in-place --recursive services/workers
fi

# Format frontend code (if npm is available)
echo "📁 Formatting Frontend code..."
if [ -d "services/frontend" ] && command -v npm &> /dev/null; then
    cd services/frontend
    if [ -f "package.json" ] && npm list prettier &> /dev/null; then
        echo "  - Running prettier..."
        npm run format 2>/dev/null || echo "  - No format script found, skipping..."
    fi
    cd ../..
fi

echo "✅ Code formatting complete!"
echo ""
echo "💡 Next steps:"
echo "   1. Review the changes with: git diff"
echo "   2. Run tests with: ./scripts/quick-test.sh"
echo "   3. Commit your changes: git add . && git commit" 