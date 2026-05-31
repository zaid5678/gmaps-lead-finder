#!/bin/bash
# Daily email sender — runs Mon–Fri at 09:00 via cron.
# Sends up to 400 emails spread over ~8 hours (60–90s between each).
# No one is ever emailed twice — the CSV tracks who has been contacted.

cd "$(dirname "$0")" || exit 1

LOG_DIR="output/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/email_cron.log"

echo "" >> "$LOG"
echo "======================================" >> "$LOG"
echo "Run started: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG"
echo "======================================" >> "$LOG"

.venv/bin/python auto_emailer.py \
    --phase initial \
    --limit 400 \
    --delay-min 60 \
    --delay-max 90 \
    >> "$LOG" 2>&1

echo "Run finished: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG"
