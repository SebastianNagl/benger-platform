#!/bin/bash
#
# Scheduled container-store prune for the BenGER self-hosted runner / K3s host.
#
# Why this exists: CI builds three images per merge (api/frontend/workers) and
# nothing reclaimed them, so the Docker build store (/var/lib/containerd) reached
# 260G and the K3s store accumulated ~570 stale benger tags. The Docker daemon now
# caps the BuildKit cache via /etc/docker/daemon.json (builder.gc), but tagged
# images and the K3s containerd store still need periodic pruning. This is the
# non-interactive, keep-7-days counterpart to runner-emergency-cleanup.sh (a manual
# full nuke) and is deliberately narrower than automated-maintenance.sh (which also
# clears /tmp, runner work dirs, etc. and is unsafe to run blindly mid-build).
#
# Install on host (see infra/systemd/benger-prune.{service,timer}):
#   install -m 0755 scheduled-prune.sh /usr/local/sbin/benger-scheduled-prune.sh
#   systemctl enable --now benger-prune.timer
#
set -euo pipefail

LOG_FILE="/var/log/github-actions-runner/prune.log"
KEEP="168h"        # keep images / build cache from the last 7 days
DISK_WARN_PCT=80   # log a WARNING when / exceeds this after pruning

mkdir -p "$(dirname "$LOG_FILE")"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] PRUNE: $*" | tee -a "$LOG_FILE"; }

disk_pct() { df --output=pcent / | tail -1 | tr -dc '0-9'; }

# Don't prune while a CI build is in flight — avoids racing BuildKit / image pulls.
if pgrep -f "Runner.Worker" >/dev/null 2>&1; then
    log "CI build in progress (Runner.Worker active) — skipping this run."
    exit 0
fi

BEFORE=$(disk_pct)
log "=== start (root fs ${BEFORE}% used) ==="

if command -v docker >/dev/null 2>&1; then
    log "docker buildx prune (keep ${KEEP})"
    docker buildx prune -af --filter "until=${KEEP}" 2>&1 | tail -1 | sed 's/^/  /' | tee -a "$LOG_FILE" || true
    log "docker image prune (keep ${KEEP})"
    docker image prune -af --filter "until=${KEEP}" 2>&1 | tail -1 | sed 's/^/  /' | tee -a "$LOG_FILE" || true
else
    log "docker not found — skipping docker prune"
fi

if command -v k3s >/dev/null 2>&1; then
    log "k3s crictl rmi --prune (twice — bulk removes can hit containerd DeadlineExceeded)"
    k3s crictl rmi --prune >/dev/null 2>&1 || true
    k3s crictl rmi --prune >/dev/null 2>&1 || true
else
    log "k3s not found — skipping k3s image prune"
fi

AFTER=$(disk_pct)
log "=== done (root fs ${BEFORE}% -> ${AFTER}% used) ==="

if [ "${AFTER:-0}" -ge "$DISK_WARN_PCT" ]; then
    log "WARNING: root filesystem at ${AFTER}% (threshold ${DISK_WARN_PCT}%) after prune — investigate."
fi
