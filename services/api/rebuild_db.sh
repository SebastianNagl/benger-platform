#!/bin/bash
# Quick database rebuild script for development

echo "🔄 BenGER Database Rebuild"
echo "=========================="
echo ""
echo "⚠️  WARNING: This will DROP all data and rebuild from scratch!"
echo "Press Ctrl+C to cancel, or Enter to continue..."
read

echo "📦 Dropping all tables..."
psql -U postgres -d benger -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO postgres; GRANT ALL ON SCHEMA public TO public;" 2>&1 | grep -v NOTICE

echo "🔧 Applying migrations..."
alembic upgrade head

echo "🌱 Initializing demo data..."
python init_complete.py

echo ""
echo "✅ Database rebuild complete!"
echo ""
echo "You can now login with:"
echo "  Username: admin"
echo "  Password: admin"