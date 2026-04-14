#!/bin/bash

# This script adds waitForInit() calls after renderHook calls in AuthContext.test.tsx
# to fix timing issues with fake timers

FILE="/Users/sebastiannagl/Code/BenGer/services/frontend/src/contexts/__tests__/AuthContext.test.tsx"

# Create a backup
cp "$FILE" "$FILE.backup"

# Use sed to add waitForInit() after each renderHook call
# Pattern: Look for lines with "const { result } = renderHook" or just "renderHook"
# and add "await waitForInit()" on the next line if it's not already there

perl -i -pe '
  if (/renderHook\(\(\) => useAuth\(\), \{ wrapper \}\)/ && !$added) {
    $_ .= "      await waitForInit()\n" unless /<already has waitForInit>/;
  }
' "$FILE"

echo "Fixed AuthContext tests - backup saved at $FILE.backup"
