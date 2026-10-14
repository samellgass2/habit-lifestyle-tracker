#!/usr/bin/env bash
set -euo pipefail

# ---------- config ----------
PROJECT_DIR="$HOME/habit-lifestyle-tracker"
POETRY_BIN="/usr/local/bin/poetry"         # adjust if needed: which poetry
TO_EMAIL="samellgass@gmail.com"
FROM_EMAIL="samellgass@gmail.com"
LOG_DIR="$HOME/Library/Logs/habits"

# ---------- env for cron ----------
export PATH="/usr/local/bin:/usr/bin:/bin"

mkdir -p "$LOG_DIR"
cd "$PROJECT_DIR"

ts="$(date '+%F_%H-%M-%S')"
LOG_FILE="$LOG_DIR/motivation_$ts.log"
LATEST="$LOG_DIR/motivation_latest.log"

{
  echo "=== motivation run @ $(date -u '+%F %T')Z on $(hostname) ==="
  echo "whoami: $(whoami)"
  echo "pwd: $(pwd)"
  command -v "$POETRY_BIN" >/dev/null 2>&1 && echo "poetry: $("$POETRY_BIN" --version)" || echo "poetry: NOT FOUND"
  echo "python: $(python3 --version 2>&1 || true)"
  echo "PATH: $PATH"
  echo
} | tee "$LOG_FILE"

# Run the daily generator
set +e
"$POETRY_BIN" run python Processes/Daily_motivation.py -vv 2>&1 | tee -a "$LOG_FILE"
status=${PIPESTATUS[0]}
set -e

echo "=== exit status: $status ===" | tee -a "$LOG_FILE"
ln -sf "$LOG_FILE" "$LATEST"

# ---------- email the full log every run ----------
SUBJECT="[habits] motivation $( [ $status -eq 0 ] && echo OK || echo FAIL:$status ) $(date '+%F %T')"

MSMTP_CFG="${XDG_CONFIG_HOME:-$HOME/.config}/msmtp/config"
MSMTP_LOG="${XDG_CONFIG_HOME:-$HOME/.config}/msmtp/msmtp.log"

echo "Email diagnostics:" | tee -a "$LOG_FILE"
echo "  HOME=$HOME" | tee -a "$LOG_FILE"
echo "  XDG_CONFIG_HOME=${XDG_CONFIG_HOME:-<unset>}" | tee -a "$LOG_FILE"
echo "  msmtp path: $(command -v msmtp || echo 'NOT FOUND')" | tee -a "$LOG_FILE"
echo "  msmtp cfg:  $MSMTP_CFG $( [ -f "$MSMTP_CFG" ] && echo '(present)' || echo '(MISSING)' )" | tee -a "$LOG_FILE"

send_log() {
  if command -v msmtp >/dev/null 2>&1; then
    {
      echo "Subject: $SUBJECT"
      echo "To: $TO_EMAIL"
      echo
      cat "$LOG_FILE"
    } | msmtp -t -v 2>&1 | tee -a "$LOG_FILE"
    return ${PIPESTATUS[1]}
  elif command -v sendmail >/dev/null 2>&1; then
    {
      echo "Subject: $SUBJECT"
      echo "To: $TO_EMAIL"
      echo "From: $FROM_EMAIL"
      echo
      cat "$LOG_FILE"
    } | sendmail -t
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
