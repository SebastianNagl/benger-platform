#!/bin/sh
# Docker entrypoint script for Next.js application with stability improvements

# Exit on any error
set -e

# Set memory limits for Node.js to prevent OOM issues (only if not already set)
if [ -z "$NODE_OPTIONS" ]; then
    export NODE_OPTIONS="--max-old-space-size=2048"
fi

# Enable graceful shutdown
trap 'echo "Shutting down gracefully..."; kill -TERM $PID; wait $PID' TERM INT

# Health check function with retry logic
health_check() {
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        # Check the root endpoint which Next.js should respond to
        if curl -f -s --max-time 5 http://localhost:3000/ > /dev/null 2>&1; then
            echo "Health check passed on attempt $attempt"
            return 0
        fi
        echo "Health check attempt $attempt/$max_attempts failed, retrying in 5s..."
        sleep 5
        attempt=$((attempt + 1))
    done
    
    echo "Health check failed after $max_attempts attempts"
    return 1
}

# Start the application
echo "Starting Next.js application..."
echo "NODE_ENV: ${NODE_ENV}"
echo "NODE_OPTIONS: ${NODE_OPTIONS}"
echo "Memory limit: $(echo $NODE_OPTIONS | sed -n 's/.*max-old-space-size=\([0-9]*\).*/\1/p')MB"
echo "Timestamp: $(date)"

# Start npm in background - use dev mode if NODE_ENV is development
if [ "$NODE_ENV" = "development" ]; then
    echo "Starting in development mode..."
    npm run dev &
else
    echo "Starting in production mode..."
    # Use standalone server if available, otherwise fall back to npm start
    if [ -f "server.js" ]; then
        echo "Using Next.js standalone server"
        HOSTNAME="0.0.0.0" node server.js &
    else
        echo "Using standard npm start"
        npm start &
    fi
fi
PID=$!

# Wait for the application to be ready with health checks
echo "Waiting for application to be ready..."
if health_check; then
    echo "Application is ready and healthy!"
else
    echo "Application failed to start properly"
    kill -TERM $PID 2>/dev/null || true
    exit 1
fi

# Keep the container running and forward signals
wait $PID