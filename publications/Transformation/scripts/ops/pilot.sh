#!/usr/bin/env bash
# Host wrapper for the checklist pilot runner (run_checklist_pilot.py).
#
#   scripts/ops/pilot.sh <phase> [runner options]
#
# What it does, per run:
#   1. takes a lock on the ledger (one run at a time);
#   2. copies the runner's helper module, the phase's inputs and the ledger
#      (data/interim/pilot/ledger.json) into a fresh run dir in the worker
#      container (/tmp/pilot/run-<id>/);
#   3. records the git SHAs (this checkout, the checkout mounted into the
#      container, benger-extended) and passes them in;
#   4. runs the phase inside the container;
#   5. on exit, also after a failure: writes the ledger back (the old copy
#      stays as ledger.json.bak), appends the output rows to
#      data/interim/pilot/ (D1 phases) or data/interim/human/pilot/ (d2-*),
#      and deletes the run dir in the container, so no student text stays there.
#
# Environment:
#   PILOT_DRY_RUN=1        stop every provider call before it is sent (no spend)
#   PILOT_CANARY=warn      leakage guard only warns (refused without PILOT_DRY_RUN=1)
#   PILOT_DATA_ROOT        default: the main checkout's publications/Transformation/data
#   PILOT_CONTAINER        default: benger-worker-1
#   PILOT_EXTENDED_REPO    default: /home/pschorr95/Code/BenGER/benger-extended
#
# Examples:
#   scripts/ops/pilot.sh selftest
#   PILOT_DRY_RUN=1 scripts/ops/pilot.sh probes --lane checklist --unit bullet --exams 1 --judges gpt-5.6-luna
#   scripts/ops/pilot.sh d2-judge --cap 35 --judges gpt-5.6-luna --arms martin:step martin:rating --passes 3

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="$HERE/run_checklist_pilot.py"
LIB="$HERE/pilot_lib.py"
DATA_ROOT="${PILOT_DATA_ROOT:-/home/pschorr95/Code/BenGER/benger-platform/publications/Transformation/data}"
CONTAINER="${PILOT_CONTAINER:-benger-worker-1}"
EXTENDED_REPO="${PILOT_EXTENDED_REPO:-/home/pschorr95/Code/BenGER/benger-extended}"

if [ $# -lt 1 ]; then
  sed -n '2,32p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
fi
PHASE="$1"
shift

case "$PHASE" in
  selftest)    INPUTS=(interim/human/heidebach_exam.json interim/human/canary_phrases.json) ;;
  probes)      INPUTS=(interim/probes/probe_texts.json interim/clone_d6_actives.json interim/human/canary_phrases.json) ;;
  generate)    INPUTS=(interim/human/canary_phrases.json) ;;
  checklist)   INPUTS=(interim/picks_temp0.json interim/human/canary_phrases.json) ;;
  d2-setup)    INPUTS=(interim/human/heidebach_exam.json) ;;
  d2-generate) INPUTS=(interim/human/canary_phrases.json) ;;
  d2-judge)    INPUTS=(interim/human/heidebach_exam.json interim/human/heidebach_scripts.json interim/human/canary_phrases.json) ;;
  ledger)      INPUTS=() ;;
  *) echo "pilot.sh: unknown phase '$PHASE'" >&2; exit 2 ;;
esac
case "$PHASE" in
  d2-*) DEST="$DATA_ROOT/interim/human/pilot" ;;   # student data: never interim/pilot
  *)    DEST="$DATA_ROOT/interim/pilot" ;;
esac

[ -d "$DATA_ROOT/interim" ] || { echo "pilot.sh: no data root at $DATA_ROOT" >&2; exit 2; }
docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null | grep -q true \
  || { echo "pilot.sh: container $CONTAINER is not running" >&2; exit 2; }

LEDGER_DIR="$DATA_ROOT/interim/pilot"
LEDGER="$LEDGER_DIR/ledger.json"
mkdir -p "$LEDGER_DIR" "$DEST"
exec 9>"$LEDGER.lock"
flock -n 9 || { echo "pilot.sh: another pilot run holds $LEDGER.lock" >&2; exit 2; }

# --- provenance: git state of the code that runs -----------------------------
git_state() {  # <repo dir> <pathspec...>: HEAD sha, "-dirty" when the paths have changes
  local repo="$1"; shift
  local sha
  sha="$(git -C "$repo" rev-parse HEAD 2>/dev/null)" || { echo unknown; return; }
  if [ -n "$(git -C "$repo" status --porcelain --untracked-files=no -- "$@" 2>/dev/null)" ]; then
    sha="$sha-dirty"
  fi
  echo "$sha"
}
mount_source() {  # <container path> -> host path of that bind mount
  docker inspect -f "{{range .Mounts}}{{if eq .Destination \"$1\"}}{{.Source}}{{end}}{{end}}" "$CONTAINER"
}
RUNNER_REPO="$(git -C "$HERE" rev-parse --show-toplevel)"
PLATFORM_SHA="$(git_state "$RUNNER_REPO" publications/Transformation/scripts)"
APP_SRC="$(mount_source /app)"
if [ -n "$APP_SRC" ] && MOUNTED_REPO="$(git -C "$APP_SRC" rev-parse --show-toplevel 2>/dev/null)"; then
  PLATFORM_MOUNTED_SHA="$(git_state "$MOUNTED_REPO" services/workers services/shared)"
else
  MOUNTED_REPO="unknown"; PLATFORM_MOUNTED_SHA="unknown"
fi
EXT_SRC="$(mount_source /app/benger_extended)"
if [ -n "$EXT_SRC" ]; then
  EXT_MOUNTED_REPO="$(git -C "$EXT_SRC" rev-parse --show-toplevel 2>/dev/null || echo unknown)"
  if [ "$EXT_MOUNTED_REPO" != "$(git -C "$EXTENDED_REPO" rev-parse --show-toplevel 2>/dev/null || echo "$EXTENDED_REPO")" ]; then
    echo "pilot.sh: WARNING the container mounts extended from $EXT_MOUNTED_REPO, not $EXTENDED_REPO" >&2
  fi
fi
EXTENDED_SHA="$(git_state "$EXTENDED_REPO" benger_extended)"
RUNNER_SHA256="$(sha256sum "$RUNNER" | cut -d' ' -f1)"

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
CWORK="/tmp/pilot/run-$RUN_ID"
TMP="$(mktemp -d "$DEST/.pilot-run.XXXXXX")"
SPENT_BEFORE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("spent", 0.0))' "$LEDGER" 2>/dev/null || echo 0)"

cleanup() {
  local rc=$?
  set +e
  if docker exec "$CONTAINER" test -f "$CWORK/ledger.json" 2>/dev/null; then
    docker cp "$CONTAINER:$CWORK/ledger.json" "$TMP/ledger.json" >/dev/null 2>&1
    if python3 - "$TMP/ledger.json" "$SPENT_BEFORE" <<'PY'
import json, sys
state = json.load(open(sys.argv[1]))
assert float(state["spent"]) >= float(sys.argv[2]) - 1e-9, "ledger went down"
PY
    then
      [ -f "$LEDGER" ] && cp "$LEDGER" "$LEDGER.bak"
      cp "$TMP/ledger.json" "$LEDGER"
    else
      echo "pilot.sh: the container ledger is unreadable or lower than the host copy; host ledger kept" >&2
    fi
  fi
  mkdir -p "$TMP/out"
  docker cp "$CONTAINER:$CWORK/out/." "$TMP/out/" >/dev/null 2>&1
  for f in "$TMP"/out/*.jsonl; do
    [ -e "$f" ] || continue
    cat "$f" >> "$DEST/$(basename "$f")"
    echo "pilot.sh: +$(wc -l < "$f") rows -> $DEST/$(basename "$f")"
  done
  docker exec "$CONTAINER" rm -rf "$CWORK" >/dev/null 2>&1
  if docker exec "$CONTAINER" test -e "$CWORK" 2>/dev/null; then
    echo "pilot.sh: WARNING could not delete $CWORK in $CONTAINER" >&2
  fi
  rm -rf "$TMP"
  python3 - "$LEDGER" "$SPENT_BEFORE" <<'PY' 2>/dev/null
import json, sys
spent = float(json.load(open(sys.argv[1])).get("spent", 0.0))
print(f"pilot.sh: ledger ${spent:.4f} (this run +${spent - float(sys.argv[2]):.4f})")
PY
  exit $rc
}
trap cleanup EXIT

docker exec "$CONTAINER" mkdir -p "$CWORK/in" "$CWORK/out"
docker cp "$LIB" "$CONTAINER:$CWORK/in/pilot_lib.py" >/dev/null
for rel in "${INPUTS[@]}"; do
  if [ -f "$DATA_ROOT/$rel" ]; then
    docker cp "$DATA_ROOT/$rel" "$CONTAINER:$CWORK/in/$(basename "$rel")" >/dev/null
  else
    echo "pilot.sh: input $rel not found under $DATA_ROOT" >&2
  fi
done
[ -f "$LEDGER" ] && docker cp "$LEDGER" "$CONTAINER:$CWORK/ledger.json" >/dev/null

echo "pilot.sh: run $RUN_ID phase $PHASE; runner $PLATFORM_SHA; mounted platform $PLATFORM_MOUNTED_SHA ($MOUNTED_REPO); extended $EXTENDED_SHA"
docker exec -i -e PILOT_DRY_RUN="${PILOT_DRY_RUN:-}" -e PILOT_CANARY="${PILOT_CANARY:-}" "$CONTAINER" \
  python - "$PHASE" --work "$CWORK" --run-id "$RUN_ID" \
  --platform-sha "$PLATFORM_SHA" --platform-mounted-sha "$PLATFORM_MOUNTED_SHA" \
  --extended-sha "$EXTENDED_SHA" --runner-sha256 "$RUNNER_SHA256" "$@" < "$RUNNER"
