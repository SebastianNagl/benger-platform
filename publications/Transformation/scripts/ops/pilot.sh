#!/usr/bin/env bash
# Host wrapper for the checklist pilot runner (run_checklist_pilot.py).
#
#   scripts/ops/pilot.sh <phase> [runner options]
#
# What it does, per run:
#   1. takes a lock on the ledger (one run at a time) and refuses to start
#      when the run dir already exists in the container;
#   2. copies the runner's helper module, the phase's inputs and the ledger
#      (data/interim/pilot/ledger.json) into a fresh run dir in the worker
#      container (/tmp/pilot/run-<id>/);
#   3. records the git SHAs (this checkout, the checkout mounted into the
#      container, benger-extended) and passes them in;
#   4. runs the phase inside the container; every 30 s it copies the ledger
#      and the rows out to a host staging dir, so a recreated container
#      loses at most 30 s;
#   5. on Ctrl-C (SIGINT) or SIGTERM: stops the in-container run first (by
#      its pid file, else by run id), waits for it, then copies out;
#   6. on exit, also after a failure: writes the ledger back (the old copy
#      stays as ledger.json.bak), appends the output rows to
#      data/interim/pilot/ (D1 phases) or data/interim/human/pilot/ (d2-*),
#      and deletes the run dir in the container, so no student text stays there.
#
# Settings (environment variable, else publications/Transformation/.pilot.local.json,
# else the default; see scripts/local_config.py):
#   PILOT_DATA_ROOT        data_root      default: this checkout's publications/Transformation/data
#   PILOT_ORG              org_id         organisation whose API keys pay (passed as --org)
#   PILOT_CONTAINER        container      default: benger-worker-1
#   PILOT_EXTENDED_REPO    extended_repo  default: benger-extended next to this repo
# Environment:
#   PILOT_DRY_RUN=1        stop every provider call before it is sent (no spend, no DB writes)
#   PILOT_CANARY=warn      leakage guard only warns (refused without PILOT_DRY_RUN=1)
#   PILOT_SYNC_SECONDS     copy-out interval during a run (default 30)
#   PILOT_STOP_GRACE       seconds to wait for a stopped run before SIGKILL (default 30)
#
# Examples:
#   scripts/ops/pilot.sh selftest
#   PILOT_DRY_RUN=1 scripts/ops/pilot.sh d2-probes --judges gpt-5.6-luna --arms martin:step
#   scripts/ops/pilot.sh d2-judge --cap 35 --judges gpt-5.6-luna --arms martin:step martin:rating --passes 3

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="$HERE/run_checklist_pilot.py"
LIB="$HERE/pilot_lib.py"
CONFIG="$HERE/../local_config.py"
setting() { python3 "$CONFIG" get "$1"; }
DATA_ROOT="$(setting data_root)"
CONTAINER="$(setting container)"
EXTENDED_REPO="$(setting extended_repo)"
ORG="$(setting org_id)"
SYNC_EVERY="${PILOT_SYNC_SECONDS:-30}"
STOP_GRACE="${PILOT_STOP_GRACE:-30}"

if [ $# -lt 1 ]; then
  awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"
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
  d2-generate) INPUTS=(interim/human/heidebach_exam.json interim/human/canary_phrases.json) ;;
  d2-judge)    INPUTS=(interim/human/heidebach_exam.json interim/human/heidebach_scripts.json interim/human/canary_phrases.json) ;;
  d2-probes)   INPUTS=(interim/human/heidebach_exam.json interim/probes/probe_texts.json interim/human/canary_phrases.json) ;;
  ledger)      INPUTS=() ;;
  *) echo "pilot.sh: unknown phase '$PHASE'" >&2; exit 2 ;;
esac
case "$PHASE" in
  d2-*) DEST="$DATA_ROOT/interim/human/pilot" ;;   # student data: never interim/pilot
  *)    DEST="$DATA_ROOT/interim/pilot" ;;
esac

[ -d "$DATA_ROOT/interim" ] || { echo "pilot.sh: no data root at $DATA_ROOT (set PILOT_DATA_ROOT or data_root in .pilot.local.json)" >&2; exit 2; }
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
if docker exec "$CONTAINER" test -e "$CWORK"; then
  echo "pilot.sh: $CWORK already exists in $CONTAINER; refusing to start" >&2
  exit 2
fi
TMP="$(mktemp -d "$DEST/.pilot-run.XXXXXX")"
mkdir -p "$TMP/sync/out"
SPENT_BEFORE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("spent", 0.0))' "$LEDGER" 2>/dev/null || echo 0)"
RUN_PID=""
SYNC_PID=""

# --- in-container run control ----------------------------------------------------
run_alive() {  # is the runner of this run id still running in the container?
  docker exec "$CONTAINER" pgrep -f -- "--run-id $RUN_ID" >/dev/null 2>&1
}
stop_container_run() {
  run_alive || return 0
  local pid
  pid="$(docker exec "$CONTAINER" cat "$CWORK/pid" 2>/dev/null || true)"
  if [ -n "$pid" ]; then
    docker exec "$CONTAINER" kill -INT "$pid" >/dev/null 2>&1 || true
  else
    docker exec "$CONTAINER" pkill -INT -f -- "--run-id $RUN_ID" >/dev/null 2>&1 || true
  fi
  local waited=0
  while run_alive && [ "$waited" -lt "$STOP_GRACE" ]; do
    sleep 1
    waited=$((waited + 1))
  done
  if run_alive; then
    echo "pilot.sh: run $RUN_ID still alive after ${STOP_GRACE}s; SIGKILL" >&2
    docker exec "$CONTAINER" pkill -KILL -f -- "--run-id $RUN_ID" >/dev/null 2>&1 || true
  else
    echo "pilot.sh: in-container run $RUN_ID stopped after ${waited}s" >&2
  fi
}
sync_once() {  # stage the container's ledger and rows on the host (atomic swaps)
  if docker cp "$CONTAINER:$CWORK/ledger.json" "$TMP/sync/ledger.json.tmp" >/dev/null 2>&1; then
    mv -f "$TMP/sync/ledger.json.tmp" "$TMP/sync/ledger.json"
  fi
  rm -rf "$TMP/sync/out.tmp" && mkdir -p "$TMP/sync/out.tmp"
  if docker cp "$CONTAINER:$CWORK/out/." "$TMP/sync/out.tmp/" >/dev/null 2>&1; then
    rm -rf "$TMP/sync/out" && mv "$TMP/sync/out.tmp" "$TMP/sync/out"
  fi
}

cleanup() {
  local rc=$?
  set +e
  trap - INT TERM
  [ -n "$SYNC_PID" ] && kill "$SYNC_PID" 2>/dev/null && wait "$SYNC_PID" 2>/dev/null
  stop_container_run
  [ -n "$RUN_PID" ] && wait "$RUN_PID" 2>/dev/null
  # final copy; if the container is gone, the staged copy (at most SYNC_EVERY s old) is used
  local src="$TMP/sync"
  mkdir -p "$TMP/final/out"
  if docker exec "$CONTAINER" test -d "$CWORK" 2>/dev/null \
     && docker cp "$CONTAINER:$CWORK/out/." "$TMP/final/out/" >/dev/null 2>&1; then
    docker cp "$CONTAINER:$CWORK/ledger.json" "$TMP/final/ledger.json" >/dev/null 2>&1
    src="$TMP/final"
  else
    echo "pilot.sh: WARNING could not read $CWORK; using the last staged copy" >&2
  fi
  if [ -f "$src/ledger.json" ]; then
    if python3 - "$src/ledger.json" "$SPENT_BEFORE" <<'PY'
import json, sys
state = json.load(open(sys.argv[1]))
assert float(state["spent"]) >= float(sys.argv[2]) - 1e-9, "ledger went down"
PY
    then
      [ -f "$LEDGER" ] && cp "$LEDGER" "$LEDGER.bak"
      cp "$src/ledger.json" "$LEDGER"
    else
      echo "pilot.sh: the run's ledger is unreadable or lower than the host copy; host ledger kept" >&2
    fi
  fi
  for f in "$src"/out/*.jsonl; do
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
on_signal() {
  trap - INT TERM
  echo "pilot.sh: $1 received; stopping run $RUN_ID in $CONTAINER" >&2
  stop_container_run
  [ "$1" = INT ] && exit 130
  exit 143
}
trap cleanup EXIT
trap 'on_signal INT' INT
trap 'on_signal TERM' TERM

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

EXTRA=()
if [ -n "$ORG" ] && ! printf '%s\n' "$@" | grep -qx -- '--org'; then
  EXTRA=(--org "$ORG")
fi

( while sleep "$SYNC_EVERY"; do sync_once; done ) &
SYNC_PID=$!

echo "pilot.sh: run $RUN_ID phase $PHASE; runner $PLATFORM_SHA; mounted platform $PLATFORM_MOUNTED_SHA ($MOUNTED_REPO); extended $EXTENDED_SHA"
docker exec -i -e PILOT_DRY_RUN="${PILOT_DRY_RUN:-}" -e PILOT_CANARY="${PILOT_CANARY:-}" "$CONTAINER" \
  python - "$PHASE" --work "$CWORK" --run-id "$RUN_ID" \
  --platform-sha "$PLATFORM_SHA" --platform-mounted-sha "$PLATFORM_MOUNTED_SHA" \
  --extended-sha "$EXTENDED_SHA" --runner-sha256 "$RUNNER_SHA256" "${EXTRA[@]}" "$@" < "$RUNNER" &
RUN_PID=$!
RC=0
wait "$RUN_PID" || RC=$?
RUN_PID=""
exit "$RC"
