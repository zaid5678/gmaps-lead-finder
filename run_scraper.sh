#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# run_scraper.sh
# Wrapper for cron: loads .env, activates venv, runs the scraper.
# ─────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Load .env ────────────────────────────────────────────────
ENV_FILE="$SCRIPT_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "$ENV_FILE"
    set +a
else
    echo "[run_scraper.sh] WARNING: .env not found at $ENV_FILE" >&2
fi

# ── Pick Python (prefer venv) ────────────────────────────────
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
if [[ -x "$VENV_PYTHON" ]]; then
    PYTHON="$VENV_PYTHON"
else
    PYTHON="$(command -v python3)"
fi

# ── Log file ─────────────────────────────────────────────────
LOG_DIR="$SCRIPT_DIR/output/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/run_$(date +%Y%m%d_%H%M%S).log"

echo "[run_scraper.sh] Starting at $(date)" | tee -a "$LOG_FILE"
echo "[run_scraper.sh] Python: $PYTHON"     | tee -a "$LOG_FILE"

# ── Run ──────────────────────────────────────────────────────
# Add --send-email below when you're ready to receive email alerts
"$PYTHON" "$SCRIPT_DIR/scraper.py" \
    "$@" \
    >> "$LOG_FILE" 2>&1

EXIT_CODE=$?
echo "[run_scraper.sh] Finished at $(date) — exit code $EXIT_CODE" >> "$LOG_FILE"
exit $EXIT_CODE
