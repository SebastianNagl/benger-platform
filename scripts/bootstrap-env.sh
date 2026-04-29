#!/usr/bin/env bash
# Copy .env.example -> .env (and .env.local) for each service. Never overwrites.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cp -n "$ROOT/services/api/.env.example"       "$ROOT/services/api/.env"        || true
cp -n "$ROOT/services/workers/.env.example"   "$ROOT/services/workers/.env"    || true
cp -n "$ROOT/services/frontend/.env.example"  "$ROOT/services/frontend/.env.local" || true

echo "Env files ready:"
echo "  services/api/.env"
echo "  services/workers/.env"
echo "  services/frontend/.env.local"
echo
echo "LLM provider keys (OpenAI/Anthropic/Google/DeepInfra) are set per organization in the app UI."
