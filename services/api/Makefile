# BenGER API Makefile
# Common development tasks using uv

.PHONY: help setup install test test-cov format lint clean dev migrate reset-db

# Default target
help:
	@echo "BenGER API Development Commands"
	@echo "==============================="
	@echo ""
	@echo "Setup & Installation:"
	@echo "  setup      - Full setup with uv (recommended for first time)"
	@echo "  install    - Install dependencies only"
	@echo ""
	@echo "Development:"
	@echo "  dev        - Start development server"
	@echo "  test       - Run all tests"
	@echo "  test-cov   - Run tests with coverage report"
	@echo "  format     - Format code with black and isort"
	@echo "  lint       - Run type checking and security scan"
	@echo ""
	@echo "Database:"
	@echo "  migrate    - Run database migrations"
	@echo "  reset-db   - Reset database (development only)"
	@echo ""
	@echo "Maintenance:"
	@echo "  clean      - Clean up generated files"

# Setup everything
setup:
	@echo "🚀 Setting up BenGER API..."
	./setup.sh

# Install dependencies
install:
	@echo "📥 Installing dependencies..."
	uv pip install -e .
	uv pip install -e ".[dev,test]"

# Start development server
dev:
	@echo "🌐 Starting development server..."
	uvicorn main:app --reload --port 8000

# Run tests
test:
	@echo "🧪 Running API tests..."
	pytest tests/ -v --tb=short

# Run tests with coverage
test-cov:
	@echo "📊 Running tests with coverage..."
	pytest tests/ -v --cov=. --cov-report=html --cov-report=xml --cov-report=term-missing

# Format code
format:
	@echo "🎨 Formatting code..."
	black .
	isort .

# Lint code
lint:
	@echo "🔍 Running linters..."
	mypy .
	bandit -r . -x tests/

# Run database migrations
migrate:
	@echo "🔄 Running database migrations..."
	alembic upgrade head

# Reset database (development only)
reset-db:
	@echo "⚠️  Resetting database..."
	@read -p "Are you sure? This will delete all data (y/N): " confirm && [ "$$confirm" = "y" ]
	rm -f benger.db
	python init_db.py
	alembic upgrade head

# Clean up generated files
clean:
	@echo "🧹 Cleaning up..."
	rm -rf __pycache__/
	rm -rf .pytest_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf coverage.xml
	rm -rf test-reports/
	rm -rf .benchmarks/
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

# Quality check (format + lint + test)
check: format lint test
	@echo "✅ Quality check completed successfully" 