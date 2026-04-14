#!/bin/bash

# Clear Next.js development cache script
echo "🧹 Clearing Next.js development caches..."

# Stop any running Next.js processes
echo "⏹️  Stopping Next.js processes..."
pkill -f "next dev" 2>/dev/null || true

# Clear Next.js cache
echo "🗑️  Removing .next directory..."
rm -rf .next

# Clear node_modules cache
echo "🗑️  Clearing node_modules cache..."
rm -rf node_modules/.cache

# Clear browser cache (instructions)
echo "🌐 Don't forget to:"
echo "   - Clear browser cache (Cmd+Shift+R on Mac, Ctrl+Shift+R on Windows/Linux)"
echo "   - Or open DevTools and right-click refresh button → 'Empty Cache and Hard Reload'"

echo ""
echo "✅ Cache cleared! You can now run:"
echo "   npm run dev:fresh"
echo "   or"
echo "   npm run dev"

echo ""
echo "🔄 Starting development server with fresh cache..."
npm run dev 