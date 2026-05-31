#!/usr/bin/env python3
"""
Automated email outreach for the gmaps-lead-finder system.

Reads leads from output/all_leads.csv and automatically sends:
  - Initial email  (first contact)
  - Follow-up 1    (Day 3 — if no reply)
  - Follow-up 2    (Day 7 — if no reply)

Skips leads already contacted via the appropriate template.
Logs every action to output/logs/email_log.txt.

Usage:
    python auto_emailer.py                       # send all pending emails
    python auto_emailer.py --dry-run             # preview without sending
    python auto_emailer.py --phase initial       # only initial outreach
    python auto_emailer.py --phase follow_up_1   # only Day-3 follow-ups
    python auto_emailer.py --phase follow_up_2   # only Day-7 follow-ups
    python auto_emailer.py --limit 20            # cap emails this run

Credentials via .env:
    GMAIL_EMAIL=zfkhan321@gmail.com
    GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
"""

import argparse
import csv
import logging
import os
import random
import smtplib
import sys
import time
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

# Load .env if python-dotenv is installed
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

OUTPUT_DIR   = Path("output")
ALL_LEADS    = OUTPUT_DIR / "all_leads.csv"
LOG_DIR      = OUTPUT_DIR / "logs"
EMAIL_LOG    = LOG_DIR / "email_log.txt"

SENDER_EMAIL = "zfkhan321@gmail.com"
SMTP_SERVER  = "smtp.gmail.com"
SMTP_PORT    = 587

# Multi-account: set GMAIL_ACCOUNTS=email1:pass1,email2:pass2 in .env
# Each account can send ~400/day safely. 3 accounts = ~1,200/day.
DAILY_LIMIT_PER_ACCOUNT = 400

DEFAULT_DELAY_MIN = 60   # seconds between emails — spreads 400 emails over ~8 hours
DEFAULT_DELAY_MAX = 90

INITIAL_TEMPLATE    = "initial"
FOLLOW_UP_1_TEMPLATE = "follow_up_1"
FOLLOW_UP_2_TEMPLATE = "follow_up_2"

FOLLOW_UP_1_DAYS = 3  # send follow-up 1 N days after initial
FOLLOW_UP_2_DAYS = 7  # send follow-up 2 N days after initial


# ─────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────

def _setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = "%(asctime)s  %(levelname)-8s  %(message)s"
    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(EMAIL_LOG, encoding="utf-8"),
    ]
    logging.basicConfig(level=logging.INFO, format=fmt, datefmt="%Y-%m-%d %H:%M:%S", handlers=handlers)

_setup_logging()
log = logging.getLogger("auto_emailer")


# ─────────────────────────────────────────────────────────────
# EMAIL TEMPLATES
# ─────────────────────────────────────────────────────────────

# Map raw category/keyword strings to a broad sector for personalised copy
_TRADE_KEYWORDS    = {"roofer", "roofing", "plumber", "plumbing", "electrician", "electrical",
                      "carpenter", "carpentry", "painter", "decorator", "builder", "building",
                      "window cleaner", "window cleaning", "cleaner", "cleaning", "gardener",
                      "landscaper", "handyman", "plasterer", "tiler", "locksmith", "glazier"}
_BEAUTY_KEYWORDS   = {"barber", "barber shop", "hairdresser", "hair salon", "beautician",
                      "beauty salon", "nail salon", "nail technician", "dog groomer", "groomer"}
_FOOD_KEYWORDS     = {"restaurant", "cafe", "coffee shop", "takeaway", "pizza", "kebab",
                      "indian restaurant", "chinese restaurant", "fish and chips"}
_HEALTH_KEYWORDS   = {"dentist", "dental", "optician", "optometrist", "personal trainer",
                      "gym", "physio", "physiotherapist", "chiropractor", "osteopath"}
_PROFESSIONAL_KEYWORDS = {"accountant", "solicitor", "lawyer", "estate agent", "letting agent",
                           "financial advisor", "bookkeeper", "mortgage broker"}


def _sector(industry: str) -> str:
    kw = industry.lower().strip()
    if any(k in kw for k in _TRADE_KEYWORDS):     return "trade"
    if any(k in kw for k in _BEAUTY_KEYWORDS):    return "beauty"
    if any(k in kw for k in _FOOD_KEYWORDS):      return "food"
    if any(k in kw for k in _HEALTH_KEYWORDS):    return "health"
    if any(k in kw for k in _PROFESSIONAL_KEYWORDS): return "professional"
    return "generic"


def _subject_initial(name: str, industry: str, city: str) -> str:
    sector = _sector(industry)
    if sector == "trade":
        return f"More {industry} work in {city} — quick question"
    if sector == "beauty":
        return f"Getting more bookings for {name} — quick idea"
    if sector == "food":
        return f"Are you getting enough walk-ins from {city}?"
    if sector == "health":
        return f"New patients/clients finding {name} online"
    if sector == "professional":
        return f"More enquiries for {name} in {city}"
    return f"Quick idea for {name} in {city}"


def _subject_follow_up_1(name: str, industry: str, city: str) -> str:
    return f"Re: {name} — just checking in"


def _subject_follow_up_2(name: str, industry: str, city: str) -> str:
    return f"Last one from me — {name}"


def _body_initial(name: str, industry: str, city: str) -> str:
    sector = _sector(industry)

    if sector == "trade":
        pain = (
            f"Most people in {city} searching for a {industry} on Google will call whoever comes up first. "
            f"If {name} isn't showing up, those calls are going straight to your competitors."
        )
    elif sector == "beauty":
        pain = (
            f"New clients almost always search online before booking. "
            f"If they can't find {name} easily, they'll book with whoever shows up first."
        )
    elif sector == "food":
        pain = (
            f"When people in {city} search for somewhere to eat, the first thing they look for is a menu online. "
            f"If they can't find yours, they'll pick somewhere they can."
        )
    elif sector == "health":
        pain = (
            f"New patients and clients in {city} check online before picking up the phone. "
            f"Without a clear web presence, {name} is invisible to anyone searching right now."
        )
    elif sector == "professional":
        pain = (
            f"Most people looking for {industry} services in {city} do their research online before contacting anyone. "
            f"If {name} doesn't show up, those enquiries go elsewhere."
        )
    else:
        pain = (
            f"Most people in {city} looking for {industry} services search online first. "
            f"If {name} isn't easy to find, those enquiries are going to whoever is."
        )

    return f"""Hi there,

{pain}

I build simple, professional websites for local businesses like {name} — starting from £500, everything included.

I can put together a free no-obligation mock-up for {name} so you can see exactly what it would look like before committing to anything.

Worth a quick look?

Best,
Zaid
zfkhan321@gmail.com

---
To stop receiving emails from me, reply with "STOP"."""


def _body_follow_up_1(name: str, industry: str, city: str) -> str:
    sector = _sector(industry)

    if sector == "trade":
        hook = f"Every day without an online presence is another day those {city} searches go to someone else."
    elif sector == "beauty":
        hook = f"A lot of new bookings in {city} start with a quick Google search — just wanted to make sure {name} isn't missing out."
    elif sector == "food":
        hook = f"People in {city} decide where to eat online before they leave the house — just wanted to make sure {name} is showing up."
    else:
        hook = f"Just wanted to make sure {name} isn't missing out on enquiries from {city} searches."

    return f"""Hi,

Following up on my message from a few days ago.

{hook}

I build straightforward websites for local businesses — £500 all-in, free mock-up first so there's no risk.

If the timing isn't right, no problem at all — just let me know.

Best,
Zaid

---
To unsubscribe, reply "STOP"."""


def _body_follow_up_2(name: str, industry: str, city: str) -> str:
    return f"""Hi,

Last one from me, I promise.

If {name} ever decides it's the right time to start getting more enquiries online, just reply to this email and I'll pick up where we left off — free mock-up, no pressure.

All the best,
Zaid
zfkhan321@gmail.com

---
To unsubscribe, reply "STOP"."""


TEMPLATES = {
    INITIAL_TEMPLATE:     (_subject_initial,    _body_initial),
    FOLLOW_UP_1_TEMPLATE: (_subject_follow_up_1, _body_follow_up_1),
    FOLLOW_UP_2_TEMPLATE: (_subject_follow_up_2, _body_follow_up_2),
}


# ─────────────────────────────────────────────────────────────
# CSV HELPERS
# ─────────────────────────────────────────────────────────────

def read_csv(path: Path) -> tuple:
    """Return (fieldnames, rows). rows is a list of dicts."""
    if not path.exists():
        return [], []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        return list(reader.fieldnames or []), rows


def write_csv(path: Path, fieldnames: list, rows: list):
    if not rows:
        return
    # Ensure all tracking columns exist in fieldnames
    for col in ["contacted", "contacted_date", "follow_up_1_sent", "follow_up_1_date",
                "follow_up_2_sent", "follow_up_2_date", "replied", "unsubscribed", "send_status", "notes"]:
        if col not in fieldnames:
            fieldnames.append(col)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def _parse_date(s: str) -> Optional[datetime]:
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.fromisoformat(s[:len(fmt)])
        except Exception:
            continue
    return None


def _days_since(date_str: str) -> Optional[int]:
    dt = _parse_date(date_str)
    if dt is None:
        return None
    return (datetime.now() - dt).days


# ─────────────────────────────────────────────────────────────
# PHASE LOGIC — which leads need what
# ─────────────────────────────────────────────────────────────

def needs_initial(row: dict) -> bool:
    if row.get("unsubscribed"):
        return False
    if row.get("contacted"):
        return False
    if not row.get("email", "").strip():
        return False
    return True


def needs_follow_up_1(row: dict) -> bool:
    if row.get("unsubscribed") or row.get("replied"):
        return False
    if row.get("follow_up_1_sent"):
        return False
    if not row.get("contacted"):
        return False
    if not row.get("email", "").strip():
        return False
    days = _days_since(row.get("contacted_date", ""))
    return days is not None and days >= FOLLOW_UP_1_DAYS


def needs_follow_up_2(row: dict) -> bool:
    if row.get("unsubscribed") or row.get("replied"):
        return False
    if row.get("follow_up_2_sent"):
        return False
    if not row.get("follow_up_1_sent"):
        return False  # must have sent follow-up 1 first
    if not row.get("email", "").strip():
        return False
    days = _days_since(row.get("contacted_date", ""))
    return days is not None and days >= FOLLOW_UP_2_DAYS


PHASE_FILTERS = {
    INITIAL_TEMPLATE:     needs_initial,
    FOLLOW_UP_1_TEMPLATE: needs_follow_up_1,
    FOLLOW_UP_2_TEMPLATE: needs_follow_up_2,
}


def _mark_sent(row: dict, template: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    if template == INITIAL_TEMPLATE:
        row["contacted"]      = "yes"
        row["contacted_date"] = now
    elif template == FOLLOW_UP_1_TEMPLATE:
        row["follow_up_1_sent"] = "yes"
        row["follow_up_1_date"] = now
    elif template == FOLLOW_UP_2_TEMPLATE:
        row["follow_up_2_sent"] = "yes"
        row["follow_up_2_date"] = now
    row["send_status"] = f"sent:{template}:{now}"


def _mark_failed(row: dict, template: str, error: str):
    row["send_status"] = f"failed:{template}:{str(error)[:80]}"


# ─────────────────────────────────────────────────────────────
# SMTP SENDER (supports multiple accounts with round-robin rotation)
# ─────────────────────────────────────────────────────────────

def _load_accounts(primary_user: str, primary_pass: str) -> list:
    """
    Return list of (email, password) tuples.
    Reads GMAIL_ACCOUNTS=email1:pass1,email2:pass2 from env if set,
    always includes the primary account as a fallback.
    """
    accounts = []
    raw = os.environ.get("GMAIL_ACCOUNTS", "").strip()
    if raw:
        for entry in raw.split(","):
            entry = entry.strip()
            if ":" in entry:
                email, pw = entry.split(":", 1)
                accounts.append((email.strip(), pw.strip()))
    if primary_user and primary_pass and not any(a[0] == primary_user for a in accounts):
        accounts.insert(0, (primary_user, primary_pass))
    return accounts


class _SingleSender:
    """SMTP connection for one Gmail account."""
    def __init__(self, user: str, password: str):
        self.user = user
        self.password = password
        self._server: Optional[smtplib.SMTP] = None
        self.sent_today = 0

    def connect(self):
        self._server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        self._server.ehlo(); self._server.starttls(); self._server.ehlo()
        self._server.login(self.user, self.password)

    def send(self, to: str, subject: str, body: str, from_name: str = "Zaid") -> bool:
        if self._server is None:
            raise RuntimeError("Not connected")
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"{from_name} <{self.user}>"
        msg["To"]      = to
        msg.attach(MIMEText(body, "plain", "utf-8"))
        self._server.sendmail(self.user, to, msg.as_string())
        self.sent_today += 1
        return True

    def close(self):
        if self._server:
            try: self._server.quit()
            except Exception: pass
            self._server = None

    def reconnect_if_needed(self):
        try:
            self._server.noop()  # type: ignore[union-attr]
        except Exception:
            self.connect()

    def at_limit(self) -> bool:
        return self.sent_today >= DAILY_LIMIT_PER_ACCOUNT


class GmailSender:
    """
    Round-robin sender across multiple Gmail accounts.
    Pass a single (user, password) for single-account mode.
    Set GMAIL_ACCOUNTS=email1:pass1,email2:pass2 in .env for multi-account.
    """
    def __init__(self, user: str, app_password: str):
        accounts = _load_accounts(user, app_password)
        self._senders = [_SingleSender(u, p) for u, p in accounts]
        self._idx = 0
        if len(self._senders) > 1:
            log.info(f"Multi-account mode: {len(self._senders)} Gmail accounts loaded.")
        else:
            log.info(f"Single-account mode: {self._senders[0].user}")

    def _current(self) -> _SingleSender:
        return self._senders[self._idx % len(self._senders)]

    def connect(self):
        for s in self._senders:
            log.info(f"Connecting SMTP as {s.user}…")
            s.connect()
        log.info("All SMTP accounts connected.")

    def send(self, to: str, subject: str, body: str) -> bool:
        # Rotate to next account if current one hit its daily limit
        for _ in range(len(self._senders)):
            sender = self._current()
            if not sender.at_limit():
                break
            log.warning(f"Account {sender.user} hit daily limit ({DAILY_LIMIT_PER_ACCOUNT}) — rotating.")
            self._idx += 1
        else:
            raise RuntimeError("All Gmail accounts have hit their daily send limit.")

        sender = self._current()
        sender.reconnect_if_needed()
        result = sender.send(to, subject, body)
        # Rotate to next account for the next email (round-robin)
        self._idx = (self._idx + 1) % len(self._senders)
        return result

    def close(self):
        for s in self._senders:
            s.close()

    def reconnect_if_needed(self):
        pass  # handled per-send now


# ─────────────────────────────────────────────────────────────
# CORE SEND LOOP
# ─────────────────────────────────────────────────────────────

def run_phase(
    rows: list,
    template: str,
    sender: Optional[GmailSender],
    delay_min: float,
    delay_max: float,
    dry_run: bool,
    limit: int,
) -> dict:
    """Send one phase of emails. Returns stats dict."""
    checker = PHASE_FILTERS[template]
    subj_fn, body_fn = TEMPLATES[template]

    to_send = [r for r in rows if checker(r)]

    # Deduplicate by email address — never send two emails to the same address in one run
    seen_emails: set = set()
    deduped = []
    dup_count = 0
    for r in to_send:
        addr = r.get("email", "").strip().lower()
        if addr and addr not in seen_emails:
            seen_emails.add(addr)
            deduped.append(r)
        elif addr:
            dup_count += 1
    if dup_count:
        log.info(f"[{template}] Skipped {dup_count} duplicate email address(es).")
    to_send = deduped

    if limit > 0:
        to_send = to_send[:limit]

    stats = {"phase": template, "to_send": len(to_send), "sent": 0, "failed": 0, "skipped": 0}

    if not to_send:
        log.info(f"[{template}] Nothing to send.")
        return stats

    log.info(f"[{template}] {len(to_send)} emails queued.")

    if sender and not dry_run:
        sender.connect()

    try:
        for i, row in enumerate(to_send):
            name     = row.get("name", "there").strip() or "there"
            city     = (row.get("city") or row.get("search_location") or "your city").replace(", UK", "").strip()
            industry = (row.get("industry") or row.get("category") or row.get("search_keyword") or "business").strip()
            to_email = row.get("email", "").strip()

            subject = subj_fn(name, industry, city)
            body    = body_fn(name, industry, city)

            if dry_run:
                log.info(f"  [DRY-RUN {i+1}/{len(to_send)}] → {name} <{to_email}>")
                log.info(f"    Subject: {subject}")
                log.info(f"    Preview: {body[:100].replace(chr(10), ' ')}…")
                _mark_sent(row, template)
                stats["sent"] += 1
            else:
                try:
                    sender.reconnect_if_needed()  # type: ignore[union-attr]
                    sender.send(to_email, subject, body)  # type: ignore[union-attr]
                    log.info(f"  SENT [{i+1}/{len(to_send)}] {template} → {name} <{to_email}>")
                    _mark_sent(row, template)
                    stats["sent"] += 1
                except Exception as exc:
                    log.warning(f"  FAILED {name} <{to_email}>: {exc}")
                    _mark_failed(row, template, str(exc))
                    stats["failed"] += 1

            if i < len(to_send) - 1:
                delay = random.uniform(delay_min, delay_max)
                if not dry_run:
                    log.debug(f"  Waiting {delay:.1f}s…")
                    time.sleep(delay)

    finally:
        if sender and not dry_run:
            sender.close()

    return stats


# ─────────────────────────────────────────────────────────────
# STATS REPORT
# ─────────────────────────────────────────────────────────────

def print_campaign_stats(rows: list):
    total        = len(rows)
    with_email   = sum(1 for r in rows if r.get("email"))
    contacted    = sum(1 for r in rows if r.get("contacted") == "yes")
    fu1          = sum(1 for r in rows if r.get("follow_up_1_sent") == "yes")
    fu2          = sum(1 for r in rows if r.get("follow_up_2_sent") == "yes")
    replied      = sum(1 for r in rows if r.get("replied") == "yes")
    unsub        = sum(1 for r in rows if r.get("unsubscribed"))
    pending_init = sum(1 for r in rows if needs_initial(r))
    pending_fu1  = sum(1 for r in rows if needs_follow_up_1(r))
    pending_fu2  = sum(1 for r in rows if needs_follow_up_2(r))
    rate         = f"{replied/contacted*100:.1f}%" if contacted else "n/a"

    log.info("=" * 60)
    log.info("CAMPAIGN STATS")
    log.info("=" * 60)
    log.info(f"  Total leads:          {total}")
    log.info(f"  Leads with email:     {with_email}")
    log.info(f"  Initial sent:         {contacted}")
    log.info(f"  Follow-up 1 sent:     {fu1}")
    log.info(f"  Follow-up 2 sent:     {fu2}")
    log.info(f"  Replies:              {replied}")
    log.info(f"  Unsubscribed:         {unsub}")
    log.info(f"  Response rate:        {rate}")
    log.info(f"  Pending initial:      {pending_init}")
    log.info(f"  Pending follow-up 1:  {pending_fu1}")
    log.info(f"  Pending follow-up 2:  {pending_fu2}")
    log.info("=" * 60)


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Automated cold-email outreach from output/all_leads.csv.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
phases:
  initial     — first contact (only leads not yet emailed)
  follow_up_1 — Day-3 reminder (only leads emailed 3+ days ago with no follow-up yet)
  follow_up_2 — Day-7 final   (only leads emailed 7+ days ago with both prior templates sent)

examples:
  python auto_emailer.py --dry-run              # preview everything
  python auto_emailer.py                        # run all phases (live)
  python auto_emailer.py --phase initial        # initial only
  python auto_emailer.py --limit 30             # cap at 30 emails this run
  python auto_emailer.py --stats-only           # just show campaign stats
        """,
    )
    p.add_argument("--csv",      default=str(ALL_LEADS), help=f"Path to leads CSV (default: {ALL_LEADS})")
    p.add_argument("--email",    default=os.environ.get("GMAIL_EMAIL", os.environ.get("GMAIL_USER", SENDER_EMAIL)))
    p.add_argument("--password", default=os.environ.get("GMAIL_APP_PASSWORD", ""))
    p.add_argument(
        "--phase", choices=[INITIAL_TEMPLATE, FOLLOW_UP_1_TEMPLATE, FOLLOW_UP_2_TEMPLATE],
        default=None, help="Run only this phase (default: all phases)",
    )
    p.add_argument("--delay-min", type=float, default=DEFAULT_DELAY_MIN, help=f"Min seconds between emails (default {DEFAULT_DELAY_MIN})")
    p.add_argument("--delay-max", type=float, default=DEFAULT_DELAY_MAX, help=f"Max seconds between emails (default {DEFAULT_DELAY_MAX})")
    p.add_argument("--limit",     type=int, default=400, help="Max emails per run (default 400 — ~8hrs at 72s avg)")
    p.add_argument("--dry-run",   action="store_true",  help="Preview without sending")
    p.add_argument("--stats-only", action="store_true", help="Print campaign stats and exit")
    return p


def main():
    args = build_parser().parse_args()
    csv_path = Path(args.csv)

    if not csv_path.exists():
        log.error(
            f"Leads file not found: {csv_path}\n"
            "  Run scraper_master.py first, or run_all.py"
        )
        sys.exit(1)

    fieldnames, rows = read_csv(csv_path)
    if not rows:
        log.warning("CSV is empty — nothing to do.")
        return

    # Ensure tracking columns exist in fieldnames list
    for col in ["contacted", "contacted_date", "follow_up_1_sent", "follow_up_1_date",
                "follow_up_2_sent", "follow_up_2_date", "replied", "unsubscribed", "send_status", "notes"]:
        if col not in fieldnames:
            fieldnames.append(col)
        for r in rows:
            r.setdefault(col, "")

    log.info(f"Loaded {len(rows)} leads from {csv_path}")

    if args.stats_only:
        print_campaign_stats(rows)
        return

    gmail_user = args.email.strip()
    app_pw     = args.password.strip()

    if not args.dry_run and not app_pw:
        log.error(
            "Gmail app password required.\n"
            "  Set GMAIL_APP_PASSWORD in .env, or pass --password 'xxxx xxxx xxxx xxxx'"
        )
        sys.exit(1)

    sender = GmailSender(gmail_user, app_pw) if not args.dry_run else None

    phases = (
        [args.phase] if args.phase
        else [INITIAL_TEMPLATE, FOLLOW_UP_1_TEMPLATE, FOLLOW_UP_2_TEMPLATE]
    )

    log.info("=" * 60)
    log.info("Auto Emailer — gmaps-lead-finder")
    log.info("=" * 60)
    log.info(f"  CSV:      {csv_path}")
    log.info(f"  From:     {gmail_user}")
    log.info(f"  Phases:   {phases}")
    log.info(f"  Delay:    {args.delay_min}–{args.delay_max}s")
    log.info(f"  Limit:    {args.limit or 'unlimited'}")
    log.info(f"  Mode:     {'DRY-RUN' if args.dry_run else 'LIVE'}")
    log.info("=" * 60)

    all_stats = []
    remaining_limit = args.limit

    for phase in phases:
        phase_limit = remaining_limit if remaining_limit > 0 else 0
        stats = run_phase(
            rows=rows,
            template=phase,
            sender=sender,
            delay_min=args.delay_min,
            delay_max=args.delay_max,
            dry_run=args.dry_run,
            limit=phase_limit,
        )
        all_stats.append(stats)
        if remaining_limit > 0:
            remaining_limit = max(0, remaining_limit - stats["sent"])
            if remaining_limit == 0:
                log.info(f"Email limit ({args.limit}) reached — stopping.")
                break

    # Persist changes back to CSV
    write_csv(csv_path, fieldnames, rows)
    log.info(f"CSV updated: {csv_path}")

    print_campaign_stats(rows)

    total_sent   = sum(s["sent"]   for s in all_stats)
    total_failed = sum(s["failed"] for s in all_stats)
    log.info(f"\nThis run: {total_sent} sent, {total_failed} failed")
    if args.dry_run:
        log.info("Dry-run — no emails were actually sent.")


if __name__ == "__main__":
    main()
