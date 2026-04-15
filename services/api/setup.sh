#!/bin/bash

# BenGER API Service Setup Script
# This script sets up the development environment using uv for dependency management

set -e  # Exit on any error

echo "🚀 Setting up BenGER API Service..."

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "❌ uv is not installed. Please install it first:"
    echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Create virtual environment with uv
echo "📦 Creating virtual environment with uv..."
uv venv

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source .venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
uv pip install -e .

# Install development and test dependencies
echo "🧪 Installing development and test dependencies..."
uv pip install -e ".[dev,test]"

# Check if .env file exists
if [ ! -f .env ]; then
    echo "⚙️  Creating .env file from template..."
    cat > .env << EOF
# Database Configuration
DATABASE_URL=sqlite:///./benger.db
POSTGRES_URL=postgresql://benger:benger@localhost:5432/benger

# Label Studio Configuration - REMOVED (Issue #108: Using native annotation system)
# Legacy Label Studio configuration removed - using native annotation system

# JWT Configuration
SECRET_KEY=your-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Celery Configuration
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Environment
ENVIRONMENT=development
DEBUG=true
EOF
    echo "📝 Created .env file. Please update it with your configuration."
else
    echo "✅ .env file already exists."
fi

# Initialize database
echo "🗄️  Initializing database..."
python init_db.py

# Run database migrations
echo "🔄 Running database migrations..."
alembic upgrade head

echo ""
echo "✅ Setup complete!"
echo ""
echo "🎯 Next steps:"
echo "   1. Update .env file with your Label Studio API key"
echo "   2. Start the development server: uvicorn main:app --reload"
echo "   3. Run tests: pytest"
echo "   4. Check coverage: pytest --cov=. --cov-report=html"
echo ""
echo "📚 Available commands:"
echo "   • Start server:     uvicorn main:app --reload --port 8000"
echo "   • Run tests:        pytest"
echo "   • Run with coverage: pytest --cov=. --cov-report=html"
echo "   • Format code:      black ."
echo "   • Sort imports:     isort ."
echo "   • Type checking:    mypy ."
echo "   • Security scan:    bandit -r ."
echo ""
echo "🌐 Server will be available at: http://localhost:8000"
echo "📖 API docs will be available at: http://localhost:8000/docs" 