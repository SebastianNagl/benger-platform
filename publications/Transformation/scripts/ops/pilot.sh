#!/usr/bin/env bash
# Host wrapper for the checklist pilot runner (run_checklist_pilot.py).
#
#   scripts/ops/pilot.sh <phase> [runner options]
#   scripts/ops/pilot.sh recover <run-id> [--use-staged]
#
# What it does, per run:
#   1. takes a lock on the ledger (one run at a time) and looks for runs an
#      earlier wrapper left behind: a run dir in the container
#      (/tmp/pilot/run-<id>/) or a staging dir on the host
#      (.pilot-run-<id>/ next to the rows). Their spend may not be in the
#      host ledger yet, so a live spending phase refuses to start while one
#      exists. Leftovers of runs already imported (imported_runs.log) are
#      deleted;
#   2. copies the runner's helper module, the phase's inputs and the ledger
#      (data/interim/pilot/ledger.json, plus ledger.base.json, the copy the
#      run starts from) into a fresh run dir in the worker container;
#   3. records the git SHAs (this checkout, the checkout mounted into the
#      container, benger-extended) and passes them in;
#   4. runs the phase inside the container; every 30 s it copies the ledger
#      and the rows out to the host staging dir, so a recreated container
#      loses at most 30 s;
#   5. on Ctrl-C (SIGINT), SIGTERM or SIGHUP: stops the in-container run
#      first (by its pid file, else by run id) and waits for it. From then on
#      further Ctrl-C is ignored until the ledger and the rows are safe on
#      the host; the docker commands of the cleanup run in their own session,
#      so a Ctrl-C from the terminal cannot cut them off either;
#   6. on exit, also after a failure: copies the run's ledger and rows out
#      and checks every copy, merges the run's ledger into the host ledger
#      (host + run - base; the old copy stays as ledger.json.bak), appends
#      the rows to data/interim/pilot/ (D1 phases) or data/interim/human/pilot/
#      (d2-*), records the run id in data/interim/pilot/imported_runs.log, and
#      only then deletes the run dir in the container (inputs incl. student
#      text, rows, ledger) and the host staging dir. When any step fails,
#      nothing is deleted, the wrapper prints what is left where, and exits 9;
#      `recover <run-id>` finishes the job later.
#
# recover <run-id>: stops that run if it still runs, then does step 6 for it.
#   The container's run dir is the source; the host staging copy (up to 30 s
#   older, so its ledger may be low) is used only when the container is up
#   and the run dir is gone, or with --use-staged when the container is gone.
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
# The leakage guard needs data/interim/human/canary_phrases.json and
# canary_terms.json (both git-ignored); a live guarded phase does not start
# without them.
#
# Exit codes: the runner's (see run_checklist_pilot.py), 2 refused to start,
# 9 the cleanup is incomplete (see the printed list; then `recover`).
#
# Examples:
#   scripts/ops/pilot.sh selftest
#   PILOT_DRY_RUN=1 scripts/ops/pilot.sh d2-probes --judges gpt-5.6-luna --arms martin:step
#   scripts/ops/pilot.sh d2-judge --cap 35 --judges gpt-5.6-luna --arms martin:step martin:rating --passes 3
#   scripts/ops/pilot.sh recover 20260927T081500Z-12345

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
SPENDING_PHASES=" probes generate checklist d2-generate d2-judge d2-probes "
for n in "$SYNC_EVERY" "$STOP_GRACE"; do
  [[ "$n" =~ ^[1-9][0-9]*$ ]] || { echo "pilot.sh: PILOT_SYNC_SECONDS and PILOT_STOP_GRACE take whole seconds (got '$n')" >&2; exit 2; }
done

if [ $# -lt 1 ]; then
  awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"
  exit 2
fi
PHASE="$1"
shift

CANARIES=(interim/human/canary_phrases.json interim/human/canary_terms.json)
case "$PHASE" in
  selftest)    INPUTS=(interim/human/heidebach_exam.json "${CANARIES[@]}") ;;
  probes)      INPUTS=(interim/probes/probe_texts.json interim/clone_d6_actives.json "${CANARIES[@]}") ;;
  generate)    INPUTS=("${CANARIES[@]}") ;;
  checklist)   INPUTS=(interim/picks_temp0.json "${CANARIES[@]}") ;;
  d2-setup)    INPUTS=(interim/human/heidebach_exam.json) ;;
  d2-generate) INPUTS=(interim/human/heidebach_exam.json "${CANARIES[@]}") ;;
  d2-judge)    INPUTS=(interim/human/heidebach_exam.json interim/human/heidebach_scripts.json "${CANARIES[@]}") ;;
  d2-probes)   INPUTS=(interim/human/heidebach_exam.json interim/probes/probe_texts.json "${CANARIES[@]}") ;;
  ledger)      INPUTS=() ;;
  recover)     INPUTS=() ;;
  *) echo "pilot.sh: unknown phase '$PHASE'" >&2; exit 2 ;;
esac
dest_of() {  # <phase> -> where its rows go
  case "$1" in
    d2-*) echo "$DATA_ROOT/interim/human/pilot" ;;   # student data: never interim/pilot
    *)    echo "$DATA_ROOT/interim/pilot" ;;
  esac
}
live_spending() {  # is this a live run of a spending phase?
  [[ "$SPENDING_PHASES" == *" $1 "* ]] && [ "${PILOT_DRY_RUN:-}" != "1" ]
}

USE_STAGED=0
if [ "$PHASE" = recover ]; then
  [ $# -ge 1 ] || { echo "pilot.sh: recover needs a run id" >&2; exit 2; }
  RECOVER_ID="$1"
  shift
  [ "${1:-}" = "--use-staged" ] && USE_STAGED=1
fi

[ -d "$DATA_ROOT/interim" ] || { echo "pilot.sh: no data root at $DATA_ROOT (set PILOT_DATA_ROOT or data_root in .pilot.local.json)" >&2; exit 2; }
if [ "$USE_STAGED" != 1 ]; then
  docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null | grep -q true \
    || { echo "pilot.sh: container $CONTAINER is not running" >&2; exit 2; }
fi
if live_spending "$PHASE"; then
  for rel in "${CANARIES[@]}"; do
    [ -f "$DATA_ROOT/$rel" ] || { echo "pilot.sh: $rel missing under $DATA_ROOT: the leakage guard needs it for a live run" >&2; exit 2; }
  done
fi

LEDGER_DIR="$DATA_ROOT/interim/pilot"
LEDGER="$LEDGER_DIR/ledger.json"
IMPORTED="$LEDGER_DIR/imported_runs.log"
mkdir -p "$LEDGER_DIR"
exec 9>"$LEDGER.lock"
flock -n 9 || { echo "pilot.sh: another pilot run holds $LEDGER.lock" >&2; exit 2; }

# Docker commands of the stop and cleanup path run in their own session, so a
# Ctrl-C from the terminal (sent to the whole foreground process group) cannot
# interrupt them; the docker CLI would otherwise re-enable SIGINT for itself.
if command -v setsid >/dev/null 2>&1 && setsid --help 2>&1 | grep -q -- '--wait'; then
  nosig() { setsid -w "$@"; }
else
  nosig() { "$@"; }
fi
cexec() { nosig docker exec "$CONTAINER" "$@"; }

# --- leftovers of earlier runs ---------------------------------------------------
imported_before() { [ -f "$IMPORTED" ] && grep -qxF -- "$1" "$IMPORTED"; }
container_runs() {  # run ids with a run dir in the container
  cexec sh -c 'for d in /tmp/pilot/run-*; do [ -d "$d" ] && echo "${d#/tmp/pilot/run-}"; done; true' 2>/dev/null || true
}
staged_runs() {  # host staging dirs: "<run id> <dir>" (legacy mktemp dirs: "- <dir>")
  local d name
  for d in "$DATA_ROOT"/interim/pilot/.pilot-run[-.]* "$DATA_ROOT"/interim/human/pilot/.pilot-run[-.]*; do
    [ -d "$d" ] || continue
    name="$(basename "$d")"
    case "$name" in
      .pilot-run-*) echo "${name#.pilot-run-} $d" ;;
      *) echo "- $d" ;;
    esac
  done
}
check_leftovers() {
  local pending=() id dir phase alive
  for id in $(container_runs); do
    if imported_before "$id"; then
      if cexec rm -rf "/tmp/pilot/run-$id" >/dev/null 2>&1 && cexec test ! -e "/tmp/pilot/run-$id" >/dev/null 2>&1; then
        echo "pilot.sh: deleted the leftover run dir of the imported run $id in $CONTAINER" >&2
      else
        echo "pilot.sh: WARNING could not delete /tmp/pilot/run-$id in $CONTAINER (run already imported; it still holds its inputs and rows): docker exec $CONTAINER rm -rf /tmp/pilot/run-$id" >&2
      fi
      continue
    fi
    phase="$(cexec cat "/tmp/pilot/run-$id/phase" 2>/dev/null || echo unknown)"
    alive="stopped"
    cexec pgrep -f -- "--run-id $id" >/dev/null 2>&1 && alive="STILL RUNNING"
    pending+=("run $id (phase $phase) in $CONTAINER:/tmp/pilot/run-$id, $alive")
  done
  while read -r id dir; do
    [ -n "${dir:-}" ] || continue
    if [ "$id" != "-" ] && imported_before "$id"; then
      rm -rf "$dir" && echo "pilot.sh: deleted the staging dir of the imported run $id ($dir)" >&2
      continue
    fi
    if [ "$id" = "-" ]; then
      pending+=("staging dir $dir of an older wrapper (no run id): compare its sync/ledger.json with the host ledger by hand, then delete it")
    else
      pending+=("staging dir $dir")
    fi
  done < <(staged_runs)
  [ ${#pending[@]} -eq 0 ] && return 0
  echo "pilot.sh: earlier runs were not imported; their spend may be missing from $LEDGER:" >&2
  printf 'pilot.sh:   - %s\n' "${pending[@]}" >&2
  echo "pilot.sh: finish them with: scripts/ops/pilot.sh recover <run-id>" >&2
  return 1
}

if [ "$PHASE" != recover ] && ! check_leftovers; then
  if live_spending "$PHASE"; then
    echo "pilot.sh: refusing to start a live $PHASE run before those are recovered (the cap counts only the host ledger)" >&2
    exit 2
  fi
  echo "pilot.sh: WARNING continuing: $PHASE spends nothing" >&2
fi

# --- run identity and staging ---------------------------------------------------------
if [ "$PHASE" = recover ]; then
  RUN_ID="$RECOVER_ID"
  CWORK="/tmp/pilot/run-$RUN_ID"
  RUN_PHASE="$(cexec cat "$CWORK/phase" 2>/dev/null || true)"
  if [ -z "$RUN_PHASE" ]; then
    for d in "$DATA_ROOT/interim/pilot/.pilot-run-$RUN_ID" "$DATA_ROOT/interim/human/pilot/.pilot-run-$RUN_ID"; do
      [ -f "$d/phase" ] && RUN_PHASE="$(cat "$d/phase")"
    done
  fi
  [ -n "$RUN_PHASE" ] || { echo "pilot.sh: no run $RUN_ID in $CONTAINER or in a host staging dir" >&2; exit 2; }
  DEST="$(dest_of "$RUN_PHASE")"
  TMP="$DEST/.pilot-run-$RUN_ID"
  mkdir -p "$TMP/sync/out"
else
  RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
  CWORK="/tmp/pilot/run-$RUN_ID"
  RUN_PHASE="$PHASE"
  DEST="$(dest_of "$PHASE")"
  TMP="$DEST/.pilot-run-$RUN_ID"
  mkdir -p "$DEST" "$TMP/sync/out"
  echo "$PHASE" > "$TMP/phase"
fi
RUN_PID=""
SYNC_PID=""
CLEANUP_ARMED=0

# --- in-container run control ----------------------------------------------------
run_alive() {  # is the runner of this run id still running in the container?
  cexec pgrep -f -- "--run-id $RUN_ID" >/dev/null 2>&1
}
stop_container_run() {
  run_alive || return 0
  local pid
  pid="$(cexec cat "$CWORK/pid" 2>/dev/null || true)"
  if [ -n "$pid" ]; then
    cexec kill -INT "$pid" >/dev/null 2>&1 || true
  else
    cexec pkill -INT -f -- "--run-id $RUN_ID" >/dev/null 2>&1 || true
  fi
  local waited=0
  while run_alive && [ "$waited" -lt "$STOP_GRACE" ]; do
    sleep 1
    waited=$((waited + 1))
  done
  if run_alive; then
    echo "pilot.sh: run $RUN_ID still alive after ${STOP_GRACE}s; SIGKILL" >&2
    cexec pkill -KILL -f -- "--run-id $RUN_ID" >/dev/null 2>&1 || true
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
sync_loop() {  # copy out every SYNC_EVERY s; stops at $TMP/sync.stop or when the wrapper is gone
  local i
  while :; do
    for ((i = 0; i < SYNC_EVERY; i++)); do
      { [ -e "$TMP/sync.stop" ] || ! kill -0 "$WRAPPER_PID" 2>/dev/null; } && return 0
      sleep 1
    done
    { [ -e "$TMP/sync.stop" ] || ! kill -0 "$WRAPPER_PID" 2>/dev/null; } && return 0
    sync_once
  done
}
container_dir_state() {  # present | absent (container up, dir gone) | unreachable
  local out
  out="$(cexec sh -c "if [ -d '$CWORK' ]; then echo present; else echo absent; fi" 2>/dev/null)" || out=""
  case "$out" in
    present|absent) echo "$out" ;;
    *) echo unreachable ;;
  esac
}
cfile() {  # <container path>: 0 a file, 1 no file, 2 could not tell
  local out
  out="$(cexec sh -c "if [ -f '$1' ]; then echo yes; else echo no; fi" 2>/dev/null)" || return 2
  case "$out" in
    yes) return 0 ;;
    no) return 1 ;;
    *) return 2 ;;
  esac
}
copy_out() {  # <container file> <host file>: absent is fine, a failed copy is not
  local have=0
  cfile "$1" || have=$?
  case "$have" in
    0) nosig docker cp "$CONTAINER:$1" "$2" >/dev/null 2>&1 ;;
    1) return 0 ;;
    *) return 1 ;;
  esac
}

# --- cleanup: copy out, check, merge, append, and only then delete -------------------
cleanup() {
  local rc=$?
  set +e
  trap '' INT TERM HUP
  if [ "$CLEANUP_ARMED" != 1 ]; then
    rmdir "$TMP/sync/out" "$TMP/sync" 2>/dev/null; rm -f "$TMP/phase"; rmdir "$TMP" 2>/dev/null
    exit "$rc"
  fi
  if [ -n "$SYNC_PID" ]; then  # let the copier finish its current copy, so it never writes after us
    touch "$TMP/sync.stop"
    wait "$SYNC_PID" 2>/dev/null
  fi
  stop_container_run
  [ -n "$RUN_PID" ] && wait "$RUN_PID" 2>/dev/null

  local problems=() src="" final_ok=0 imported=0 state
  state="$(container_dir_state)"
  rm -rf "$TMP/final" && mkdir -p "$TMP/final/out"
  case "$state" in
    present)
      if ! nosig docker cp "$CONTAINER:$CWORK/out/." "$TMP/final/out/" >/dev/null 2>&1; then
        problems+=("the final copy of the rows from $CONTAINER:$CWORK/out failed")
      elif ! copy_out "$CWORK/ledger.json" "$TMP/final/ledger.json"; then
        problems+=("the final copy of the run's ledger from $CONTAINER:$CWORK/ledger.json failed")
      elif [ ! -f "$TMP/ledger.base.json" ] && ! copy_out "$CWORK/ledger.base.json" "$TMP/ledger.base.json"; then
        problems+=("the copy of the run's base ledger failed")
      else
        final_ok=1
        src="$TMP/final"
      fi
      ;;
    absent)
      mkdir -p "$TMP/sync/out"
      src="$TMP/sync"
      if [ -f "$TMP/sync/ledger.json" ] || [ -n "$(ls -A "$TMP/sync/out" 2>/dev/null)" ]; then
        echo "pilot.sh: WARNING $CWORK is gone from $CONTAINER; importing the staged copy (up to ${SYNC_EVERY}s old: its ledger may miss the last calls)" >&2
      else
        problems+=("$CWORK is gone from $CONTAINER and nothing was staged: calls of this run (at most its first ${SYNC_EVERY}s) may be missing from the ledger")
      fi
      ;;
    unreachable)
      if [ "$USE_STAGED" = 1 ]; then
        echo "pilot.sh: WARNING $CONTAINER unreachable; importing the staged copy as asked (--use-staged; its ledger may miss up to ${SYNC_EVERY}s of calls)" >&2
        src="$TMP/sync"
      else
        problems+=("$CONTAINER is not reachable, so $CWORK could not be read")
      fi
      ;;
  esac

  if [ -n "$src" ]; then
    local ledger_ok=1 rows_ok=1 base="$TMP/ledger.base.json" f merged
    if [ -f "$src/ledger.json" ]; then
      if [ ! -f "$base" ]; then
        echo "pilot.sh: WARNING no base ledger for run $RUN_ID (started by an older wrapper): assuming the host ledger did not move since" >&2
        base="$LEDGER"
      fi
      [ -f "$LEDGER" ] && cp -p "$LEDGER" "$LEDGER.bak"
      if merged="$(python3 "$LIB" merge-ledger "$LEDGER" "$base" "$src/ledger.json" "$LEDGER")"; then
        echo "pilot.sh: ledger merged: $merged"
      else
        ledger_ok=0
        problems+=("the ledger merge failed ($merged); the host ledger is unchanged, the run's ledger is in $src/ledger.json")
      fi
    fi
    if [ "$ledger_ok" = 1 ]; then
      for f in "$src"/out/*.jsonl; do
        [ -e "$f" ] || continue
        if cat "$f" >> "$DEST/$(basename "$f")"; then
          echo "pilot.sh: +$(wc -l < "$f") rows -> $DEST/$(basename "$f")"
        else
          rows_ok=0
          problems+=("could not append $f to $DEST/$(basename "$f")")
        fi
      done
    fi
    if [ "$ledger_ok" = 1 ] && [ "$rows_ok" = 1 ]; then
      if echo "$RUN_ID" >> "$IMPORTED"; then
        imported=1
      else
        problems+=("could not record run $RUN_ID in $IMPORTED")
      fi
    fi
  fi

  if [ "$imported" = 1 ] && [ "$final_ok" = 1 ]; then
    if cexec rm -rf "$CWORK" >/dev/null 2>&1 && cexec test ! -e "$CWORK" >/dev/null 2>&1; then
      :
    else
      problems+=("could not delete $CWORK in $CONTAINER (the run is imported; the dir still holds its inputs incl. any student text, rows and ledger): docker exec $CONTAINER rm -rf $CWORK")
    fi
  elif [ "$state" != absent ] && [ "$imported" != 1 ]; then
    problems+=("left $CWORK in $CONTAINER (inputs incl. any student text, rows, ledger): not imported yet")
  elif [ "$state" = unreachable ]; then
    problems+=("could not check $CWORK in $CONTAINER (container unreachable); delete it once the container is up: docker exec $CONTAINER rm -rf $CWORK")
  fi
  if [ "$imported" = 1 ]; then
    rm -rf "$TMP"
  elif [ -d "$TMP" ]; then
    problems+=("left the host staging copy $TMP")
  fi

  if [ ${#problems[@]} -gt 0 ]; then
    echo "pilot.sh: ================ CLEANUP INCOMPLETE: run $RUN_ID ================" >&2
    printf 'pilot.sh:   - %s\n' "${problems[@]}" >&2
    [ "$imported" = 1 ] || echo "pilot.sh: finish it with: scripts/ops/pilot.sh recover $RUN_ID" >&2
    echo "pilot.sh: a live spending run refuses to start until then" >&2
    [ "$imported" = 1 ] || rc=9
    [ "$rc" = 0 ] && rc=9
  fi
  python3 - "$LEDGER" <<'PY' 2>/dev/null
import json, sys
print(f"pilot.sh: ledger ${float(json.load(open(sys.argv[1])).get('spent', 0.0)):.4f}")
PY
  exit "$rc"
}
on_signal() {
  trap '' INT TERM HUP
  echo "pilot.sh: $1 received; stopping run $RUN_ID in $CONTAINER. Further Ctrl-C is ignored until the ledger and rows are safe (kill -9 $$ forces an exit; then run scripts/ops/pilot.sh recover $RUN_ID)" >&2
  stop_container_run
  case "$1" in
    INT) exit 130 ;;
    HUP) exit 129 ;;
    *) exit 143 ;;
  esac
}
trap cleanup EXIT
trap 'on_signal INT' INT
trap 'on_signal TERM' TERM
trap 'on_signal HUP' HUP

if [ "$PHASE" = recover ]; then
  echo "pilot.sh: recovering run $RUN_ID (phase $RUN_PHASE)"
  CLEANUP_ARMED=1
  exit 0
fi

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

# --- stage the run in the container ------------------------------------------------
docker exec "$CONTAINER" mkdir -p "$CWORK/in" "$CWORK/out"
CLEANUP_ARMED=1  # from here on the container holds copies that the cleanup must bring back or delete
docker exec "$CONTAINER" sh -c "echo '$PHASE' > '$CWORK/phase'"
docker cp "$LIB" "$CONTAINER:$CWORK/in/pilot_lib.py" >/dev/null
for rel in "${INPUTS[@]}"; do
  if [ -f "$DATA_ROOT/$rel" ]; then
    docker cp "$DATA_ROOT/$rel" "$CONTAINER:$CWORK/in/$(basename "$rel")" >/dev/null
  else
    echo "pilot.sh: input $rel not found under $DATA_ROOT" >&2
  fi
done
if [ -f "$LEDGER" ]; then
  cp -p "$LEDGER" "$TMP/ledger.base.json"
  docker cp "$LEDGER" "$CONTAINER:$CWORK/ledger.json" >/dev/null
  docker cp "$LEDGER" "$CONTAINER:$CWORK/ledger.base.json" >/dev/null
else
  echo '{}' > "$TMP/ledger.base.json"
fi

EXTRA=()
if [ -n "$ORG" ] && ! printf '%s\n' "$@" | grep -qx -- '--org'; then
  EXTRA=(--org "$ORG")
fi

# Background children must not inherit the ledger lock (fd 9): a copier
# still sleeping after the run would keep the next run out.
WRAPPER_PID=$$
( sync_loop ) 9>&- &
SYNC_PID=$!

echo "pilot.sh: run $RUN_ID phase $PHASE; runner $PLATFORM_SHA; mounted platform $PLATFORM_MOUNTED_SHA ($MOUNTED_REPO); extended $EXTENDED_SHA"
nosig docker exec -i -e PILOT_DRY_RUN="${PILOT_DRY_RUN:-}" -e PILOT_CANARY="${PILOT_CANARY:-}" "$CONTAINER" \
  python - "$PHASE" --work "$CWORK" --run-id "$RUN_ID" \
  --platform-sha "$PLATFORM_SHA" --platform-mounted-sha "$PLATFORM_MOUNTED_SHA" \
  --extended-sha "$EXTENDED_SHA" --runner-sha256 "$RUNNER_SHA256" "${EXTRA[@]}" "$@" < "$RUNNER" 9>&- &
RUN_PID=$!
RC=0
wait "$RUN_PID" || RC=$?
RUN_PID=""
exit "$RC"
