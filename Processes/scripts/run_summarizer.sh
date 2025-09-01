#!/usr/bin/env bash
set -euo pipefail

# ---------- config ----------
PROJECT_DIR="$HOME/habit-lifestyle-tracker"
POETRY_BIN="/usr/local/bin/poetry"          # adjust if: which poetry
TO_EMAIL="samellgass@gmail.com"                  # set this
FROM_EMAIL="samellgass@gmail.com"                # for sendmail fallback
LOG_DIR="$HOME/Library/Logs/habits"

# ---------- env for cron ----------
export PATH="/usr/local/bin:/usr/bin:/bin"
# If you rely on Homebrew env vars for poetry, uncomment:
# eval "$(/usr/local/bin/brew shellenv)"

mkdir -p "$LOG_DIR"
cd "$PROJECT_DIR"

ts="$(date '+%F_%H-%M-%S')"
LOG_FILE="$LOG_DIR/summarizer_$ts.log"
LATEST="$LOG_DIR/summarizer_latest.log"

{
  echo "=== summarizer run @ $(date -u '+%F %T')Z on $(hostname) ==="
  echo "whoami: $(whoami)"
  echo "pwd: $(pwd)"
  command -v "$POETRY_BIN" >/dev/null 2>&1 && echo "poetry: $("$POETRY_BIN" --version)" || echo "poetry: NOT FOUND"
  echo "python: $(python3 --version 2>&1 || true)"
  echo "PATH: $PATH"
  echo
} | tee "$LOG_FILE"

# Run summarizer and capture BOTH stdout+stderr
set +e
"$POETRY_BIN" run python Processes/Summarizer.py -vv 2>&1 | tee -a "$LOG_FILE"
status=${PIPESTATUS[0]}
set -e

echo "=== exit status: $status ===" | tee -a "$LOG_FILE"

# Keep a handy symlink
ln -sf "$LOG_FILE" "$LATEST"

# ---------- email the full log every run ----------
SUBJECT="[habits] summarizer $( [ $status -eq 0 ] && echo OK || echo FAIL:$status ) $(date '+%F %T')"

MSMTP_CFG="${XDG_CONFIG_HOME:-$HOME/.config}/msmtp/config"
MSMTP_LOG="${XDG_CONFIG_HOME:-$HOME/.config}/msmtp/msmtp.log"

echo "Email diagnostics:" | tee -a "$LOG_FILE"
echo "  HOME=$HOME" | tee -a "$LOG_FILE"
echo "  XDG_CONFIG_HOME=${XDG_CONFIG_HOME:-<unset>}" | tee -a "$LOG_FILE"
echo "  msmtp path: $(command -v msmtp || echo 'NOT FOUND')" | tee -a "$LOG_FILE"
echo "  msmtp cfg:  $MSMTP_CFG $( [ -f "$MSMTP_CFG" ] && echo '(present)' || echo '(MISSING)' )" | tee -a "$LOG_FILE"
if command -v security >/dev/null 2>&1; then
  if security find-generic-password -a YOU@gmail.com -s msmtp-gmail -w >/dev/null 2>&1; then
    echo "  keychain credential: PRESENT" | tee -a "$LOG_FILE"
  else
    echo "  keychain credential: MISSING/INACCESSIBLE" | tee -a "$LOG_FILE"
  fi
fi

send_log() {
  if command -v msmtp >/dev/null 2>&1; then
    {
      echo "Subject: $SUBJECT"
      echo "To: $TO_EMAIL"
      echo
      cat "$LOG_FILE"
    } | msmtp -t -v 2>&1 | tee -a "$LOG_FILE"
    return ${PIPESTATUS[1]}   # return msmtp's exit code (2nd pipe)
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

send_log || echo "[WARN] Email send to $TO_EMAIL returned non-zero" | tee -a "$LOG_FILE"

# Optional macOS banner on failure
# if [[ $status -ne 0 ]] && command -v terminal-notifier >/dev/null 2>&1; then
#   terminal-notifier -title "Summarizer failed" -message "See $(basename "$LOG_FILE")" -open "file://$LOG_FILE" || true
# fi

exit $status
