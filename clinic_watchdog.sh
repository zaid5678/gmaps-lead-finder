#!/usr/bin/env bash
# Watchdog for clinic_scraper.py — restarts on crash until it exits 0 (fully done).
LOG="output/clinic_scrape.log"
PYTHON=".venv/bin/python"

echo "[watchdog] Starting clinic scraper watchdog — $(date)" >> "$LOG"

while true; do
    "$PYTHON" clinic_scraper.py >> "$LOG" 2>&1
    EXIT=$?
    if [ $EXIT -eq 0 ]; then
        echo "[watchdog] Scraper finished cleanly (exit 0). Done." >> "$LOG"
        break
    fi
    echo "[watchdog] Scraper exited with code $EXIT at $(date) — restarting in 30s…" >> "$LOG"
    sleep 30
done
