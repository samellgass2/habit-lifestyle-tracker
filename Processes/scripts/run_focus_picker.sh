#!/usr/bin/env bash
set -euo pipefail

# ---------- config ----------
PROJECT_DIR="$HOME/habit-lifestyle-tracker"
POETRY_BIN="/usr/local/bin/poetry"
TO_EMAIL="samellgass@gmail.com"
FROM_EMAIL="samellgass@gmail.com"
LOG_DIR="$HOME/Library/Logs/habits"

# ⚠️ Make sure this path matches your repo exactly:
PROCESS_PATH="Processes/Focus_picker.py"

# Verbosity passthrough to the Python script (-v / -vv)
# (We also accept VERBOSITY env to synthesize flags if you prefer)
VERBOSITY="${VERBOSITY:-}"
vflags=""
if [[ -n "$VERBOSITY" ]]; then
  if   [[ "$VERBOSITY" -ge 2 ]]; then vflags="-vv"
  elif [[ "$VERBOSITY" -ge 1 ]]; then vflags="-v"
  fi
fi

# ---------- env for cron ----------
export PATH="/usr/local/bin:/usr/bin:/bin"

mkdir -p "$LOG_DIR"
ts="$(date '+%F_%H-%M-%S')"
LOG_FILE="$LOG_DIR/focus_picker_$ts.log"
LATEST="$LOG_DIR/focus_picker_latest.log"

# ---------- preamble ----------
{
  echo "=== focus_picker run @ $(date -u '+%F %T')Z on $(hostname) ==="
  echo "whoami: $(whoami)"
  echo "pwd: $PROJECT_DIR"
  command -v "$POETRY_BIN" >/dev/null 2>&1 && echo "poetry: $("$POETRY_BIN" --version)" || echo "poetry: NOT FOUND"
  echo "system python: $(python3 --version 2>&1 || true)"
} | tee "$LOG_FILE"

# ensure project dir
cd "$PROJECT_DIR"

# ensure the processor exists
if [[ ! -f "$PROCESS_PATH" ]]; then
  echo "[ERROR] Processor not found at '$PROCESS_PATH' (cwd: $(pwd))" | tee -a "$LOG_FILE"
  exit 2
fi

# ensure Poetry uses py3.12 (no-op if already set)
if command -v "$POETRY_BIN" >/dev/null 2>&1; then
  "$POETRY_BIN" env use -q python3.12 || true
  echo "poetry python: $("$POETRY_BIN" run -q python -c 'import sys; print(sys.version)')" | tee -a "$LOG_FILE"
fi
echo "PATH: $PATH" | tee -a "$LOG_FILE"
echo | tee -a "$LOG_FILE"

# ---------- run processor ----------
set +e
# Note: we pass both synthesized vflags and raw "$@" through to the script
"$POETRY_BIN" -q run python "$PROCESS_PATH" $vflags "$@" 2>&1 | tee -a "$LOG_FILE"
status=${PIPESTATUS[0]}
set -e

echo "=== exit status: $status ===" | tee -a "$LOG_FILE"
ln -sf "$LOG_FILE" "$LATEST"

# ---------- email once ----------
SUBJECT="[habits] focus_picker $( [ $status -eq 0 ] && echo OK || echo FAIL:$status ) $(date '+%F %T')"
MSMTP_CFG="${XDG_CONFIG_HOME:-$HOME/.config}/msmtp/config"
MSMTP_LOG="${XDG_CONFIG_HOME:-$HOME/.config}/msmtp/msmtp.log"

{
  echo "Email diagnostics:"
  echo "  HOME=$HOME"
  echo "  XDG_CONFIG_HOME=${XDG_CONFIG_HOME:-<unset>}"
  echo "  msmtp path: $(command -v msmtp || echo 'NOT FOUND')"
  echo "  msmtp cfg:  $MSMTP_CFG $( [ -f "$MSMTP_CFG" ] && echo '(present)' || echo '(MISSING)' )"
} | tee -a "$LOG_FILE"

send_log() {
  if command -v msmtp >/dev/null 2>&1; then
    { echo "Subject: $SUBJECT"; echo "To: $TO_EMAIL"; echo; cat "$LOG_FILE"; } | msmtp -t
    return ${PIPESTATUS[1]:-0}
  elif command -v sendmail >/dev/null 2>&1; then
    { echo "Subject: $SUBJECT"; echo "To: $TO_EMAIL"; echo "From: $FROM_EMAIL"; echo; cat "$LOG_FILE"; } | sendmail -t
    return $?
  else
    echo "[WARN] No msmtp/sendmail found; email not sent." | tee -a "$LOG_FILE"
    return 127
  fi
}

if ! send_log; then
  echo "[WARN] Email send returned non-zero; tailing msmtp log if present:" | tee -a "$LOG_FILE"
  [ -f "$MSMTP_LOG" ] && tail -n 100 "$MSMTP_LOG" | tee -a "$LOG_FILE"
fi

exit $status
