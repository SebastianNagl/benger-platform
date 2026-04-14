#!/bin/bash
echo "Starting Next.js dev server..."
echo "Server will be available at http://localhost:3000"
echo "Press Ctrl+C to stop"
echo "---"

# Keep the process in foreground
exec npx next dev 2>&1