#!/bin/bash
# Install pre-commit hooks for BenGER project

set -e

echo "📦 Installing BenGER pre-commit hooks..."

# Check if we're in the right directory
if [ ! -d ".git" ]; then
    echo "❌ Error: Not in a Git repository root directory"
    exit 1
fi

# Check if pre-commit is installed
if ! command -v pre-commit &> /dev/null; then
    echo "❌ Error: pre-commit is not installed"
    echo ""
    echo "Install pre-commit first:"
    echo "  pip install pre-commit"
    echo "  # or"
    echo "  brew install pre-commit"
    exit 1
fi

# Install pre-commit hooks
echo "  Installing pre-commit hooks..."
pre-commit install
pre-commit install --hook-type pre-push

echo ""
echo "✅ Pre-commit hooks installation complete!"
echo ""
echo "📚 Installed hooks:"
echo "  - pre-commit: Python & frontend formatting, linting, and code quality"
echo "  - pre-push: Security audits, type checking, migration validation, smoke tests"
echo ""
echo "💡 To run hooks manually:"
echo "  pre-commit run --all-files          # Run all pre-commit hooks"
echo "  pre-commit run --hook-stage pre-push # Run pre-push hooks"
echo ""
echo "💡 To bypass hooks temporarily (not recommended):"
echo "  git commit --no-verify"
echo "  git push --no-verify"
echo ""
echo "📖 For more information, see Hook & CI/CD Strategy in CLAUDE.md"