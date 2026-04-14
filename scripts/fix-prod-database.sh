#!/bin/bash
# Fix production database migration issues by resetting database

echo "🚨 WARNING: This will reset the production database!"
echo "⏳ Waiting 5 seconds before proceeding..."
sleep 5

echo "📦 Resetting production database..."

# Scale down API and workers to prevent connections
echo "🔄 Scaling down services..."
kubectl scale deployment benger-api --replicas=0 -n benger
kubectl scale deployment benger-workers --replicas=0 -n benger

# Wait for pods to terminate
sleep 10

# Drop and recreate database
echo "🗑️ Dropping and recreating database..."
kubectl exec -n benger benger-postgresql-0 -- psql -U postgres -c "DROP DATABASE IF EXISTS benger;"
kubectl exec -n benger benger-postgresql-0 -- psql -U postgres -c "CREATE DATABASE benger;"

# Run migrations fresh
echo "🔧 Running migrations..."
kubectl exec -n benger deployment/benger-api -- alembic upgrade head

# Initialize demo data
echo "📝 Initializing demo data..."
kubectl exec -n benger deployment/benger-api -- python init_complete.py

# Scale services back up
echo "🚀 Scaling services back up..."
kubectl scale deployment benger-api --replicas=2 -n benger
kubectl scale deployment benger-workers --replicas=1 -n benger

# Wait for rollout
echo "⏳ Waiting for services to be ready..."
kubectl rollout status deployment/benger-api -n benger --timeout=120s
kubectl rollout status deployment/benger-workers -n benger --timeout=120s

echo "✅ Database reset complete!"