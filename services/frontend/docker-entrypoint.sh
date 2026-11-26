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

# Keep node_modules in step with the lockfile in development. The dev compose
# file keeps node_modules in an anonymous volume, and Docker carries that
# volume over when the container is recreated from a rebuilt image, so a stale
# install (for example a Next.js release with known advisories) would
# otherwise keep running after the lockfile moved on. Dockerfile.dev stamps
# the lockfile hash into node_modules; on a mismatch the dependencies are
# installed afresh with npm ci in a staging directory and swapped in. Neither
# npm ci nor npm install can run in place, because overlays bind-mount
# packages inside node_modules and npm would try to delete those mounts.

# True when $1 is a mount point or contains one.
holds_mount() {
    printf '%s\n' "$node_modules_mounts" | grep -q -e "^$1\$" -e "^$1/"
}

# Delete everything under directory $1 except mount points and their parents.
clear_except_mounts() {
    for entry in "$1"/* "$1"/.[!.]* "$1"/..?*; do
        [ -e "$entry" ] || [ -L "$entry" ] || continue
        if holds_mount "$entry"; then
            if [ -d "$entry" ] && ! printf '%s\n' "$node_modules_mounts" | grep -q "^$entry\$"; then
                clear_except_mounts "$entry"
            fi
        else
            rm -rf "$entry"
        fi
    done
}

sync_node_modules() {
    wanted_lock=$(sha256sum package-lock.json | cut -d' ' -f1)
    installed_lock=$(cat node_modules/.lockfile-sha256 2>/dev/null || true)
    [ "$wanted_lock" = "$installed_lock" ] && return 0

    echo "node_modules does not match package-lock.json, reinstalling dependencies..."
    staging=$(mktemp -d)
    cp package.json package-lock.json "$staging"/
    [ -f .npmrc ] && cp .npmrc "$staging"/
    (cd "$staging" && npm ci --no-audit --no-fund)

    node_modules_mounts=$(awk -v dir="$PWD/node_modules" \
        'index($5, dir "/") == 1 { sub("^" dir, "node_modules", $5); print $5 }' \
        /proc/self/mountinfo)
    clear_except_mounts node_modules
    cp -a "$staging"/node_modules/. node_modules/
    rm -rf "$staging"
    echo "$wanted_lock" > node_modules/.lockfile-sha256
    echo "Dependencies reinstalled from package-lock.json"
}

if [ "$NODE_ENV" = "development" ] && [ -f package-lock.json ] && [ -d node_modules ]; then
    sync_node_modules
fi

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