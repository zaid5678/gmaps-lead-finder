"""
Shared, persistent daily send counter across ALL outreach scripts
(auto_emailer.py, clinic_scraper.py, nhs_clinic_scraper.py) that send from
the same Gmail account. Without this, each script's self-chaining batches
(clinic/NHS scrapers can run several times a day) have no visibility into
how many emails the OTHER scripts already sent today — combined sends could
exceed Gmail's ~500/day safe threshold even though each script individually
looks capped.

State is a small JSON file committed back to the repo by each workflow's
existing commit step, so the count persists across runs and processes.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

STATE_FILE = Path("output/daily_send_count.json")
COMBINED_DAILY_LIMIT = 400   # shared across every script sending from this account


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load() -> dict:
    if not STATE_FILE.exists():
        return {"date": _today(), "count": 0}
    try:
        data = json.loads(STATE_FILE.read_text())
    except Exception:
        return {"date": _today(), "count": 0}
    if data.get("date") != _today():
        return {"date": _today(), "count": 0}
    return data


def _save(data: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(data))


def remaining_quota(limit: int = COMBINED_DAILY_LIMIT) -> int:
    data = _load()
    return max(0, limit - data.get("count", 0))


def record_send():
    data = _load()
    data["count"] = data.get("count", 0) + 1
    _save(data)
