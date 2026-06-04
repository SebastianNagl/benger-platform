#!/bin/bash
#
# Disk-usage alert for the BenGER prod host.
#
# Emails via SendGrid (reusing the app's benger-email-config secret) when the root
# filesystem exceeds a threshold. Runs daily via benger-disk-alert.timer. This
# guards the failure mode that prompted it: the Docker/K3s image stores filled the
# root fs to 84% unnoticed because nothing actively alerted. Routine reclamation is
# handled by scheduled-prune.sh + the BuildKit cap in /etc/docker/daemon.json; this
# script is purely the "tell a human before it hits 100%" backstop.
#
# Force a test send regardless of current usage:
#   disk-alert.sh test
#
set -euo pipefail

THRESHOLD=80
RECIPIENT="sebastiannagl@icloud.com"
SECRET_NS="benger"
SECRET_NAME="benger-email-config"
LOG_FILE="/var/log/github-actions-runner/disk-alert.log"

mkdir -p "$(dirname "$LOG_FILE")"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] DISK-ALERT: $*" | tee -a "$LOG_FILE"; }

USAGE=$(df --output=pcent / | tail -1 | tr -dc '0-9')
HOST=$(hostname)
FORCE=0
[ "${1:-}" = "test" ] && FORCE=1

if [ "$FORCE" -eq 0 ] && [ "$USAGE" -lt "$THRESHOLD" ]; then
    log "root fs ${USAGE}% < ${THRESHOLD}% — OK, no alert."
    exit 0
fi

# Pull SendGrid creds from the same secret the API uses (key stays out of any file).
get_secret() { kubectl get secret "$SECRET_NAME" -n "$SECRET_NS" -o "jsonpath={.data.$1}" 2>/dev/null | base64 -d; }
API_KEY=$(get_secret SENDGRID_API_KEY)
FROM_RAW=$(get_secret EMAIL_FROM_ADDRESS)
FROM_NAME=$(get_secret EMAIL_FROM_NAME)
# EMAIL_FROM_ADDRESS may be "Name <addr>" — extract the bare address for SendGrid.
FROM_EMAIL=$(printf '%s' "$FROM_RAW" | grep -oE '[^<> ]+@[^<> ]+' | head -1)
[ -z "$FROM_EMAIL" ] && FROM_EMAIL="noreply@what-a-benger.net"
[ -z "$FROM_NAME" ] && FROM_NAME="BenGER Platform"

if [ -z "$API_KEY" ]; then
    log "ERROR: could not read SENDGRID_API_KEY from ${SECRET_NS}/${SECRET_NAME} — cannot send (root fs ${USAGE}%)."
    exit 1
fi

SUBJECT="[BenGER prod] disk at ${USAGE}% on ${HOST}"
BODY="Root filesystem on ${HOST} (178.105.26.90) is at ${USAGE}% used (threshold ${THRESHOLD}%).\n\nLikely cause: container image / build-cache accumulation. Check:\n  df -h /\n  docker system df\n  k3s crictl images | grep -c sebastiannagl\n\nThe weekly benger-prune.timer handles routine cleanup; for an immediate reclaim run /usr/local/sbin/benger-scheduled-prune.sh."

HTTP=$(curl -s -o "/tmp/sg_resp.$$" -w '%{http_code}' --max-time 15 \
    -X POST https://api.sendgrid.com/v3/mail/send \
    -H "Authorization: Bearer ${API_KEY}" \
    -H "Content-Type: application/json" \
    --data-binary @- <<JSON
{
  "personalizations": [{"to": [{"email": "${RECIPIENT}"}]}],
  "from": {"email": "${FROM_EMAIL}", "name": "${FROM_NAME}"},
  "subject": "${SUBJECT}",
  "content": [{"type": "text/plain", "value": "${BODY}"}]
}
JSON
)
RESP=$(cat "/tmp/sg_resp.$$" 2>/dev/null || true); rm -f "/tmp/sg_resp.$$"
if [ "$HTTP" = "202" ]; then
    log "ALERT sent to ${RECIPIENT} (root fs ${USAGE}%, SendGrid 202)."
else
    log "ERROR: SendGrid returned ${HTTP} (root fs ${USAGE}%): ${RESP}"
    exit 1
fi
