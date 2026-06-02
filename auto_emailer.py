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
_TRADE_KEYWORDS    = {
    "roofer", "roofing", "plumber", "plumbing", "electrician", "electrical",
    "carpenter", "carpentry", "joiner", "joinery", "bricklayer", "bricklaying",
    "scaffolder", "scaffolding", "groundworker", "groundwork",
    "heating engineer", "gas engineer", "hvac", "hvac engineer",
    "painter", "decorator", "painter decorator", "builder", "building",
    "plasterer", "plastering", "tiler", "tiling", "dryliner", "dry liner",
    "floor layer", "carpet fitter", "carpet fitting",
    "glazier", "glazing", "window fitter", "window fitting",
    "window cleaner", "window cleaning", "cleaner", "cleaning",
    "gardener", "gardening", "landscaper", "landscaping",
    "stone mason", "stonemason", "locksmith", "paviour", "paving",
    "handyman",
}
_BEAUTY_KEYWORDS   = {"barber", "barber shop", "hairdresser", "hair salon", "beautician",
                      "beauty salon", "nail salon", "nail technician", "dog groomer", "groomer"}
_FOOD_KEYWORDS     = {"restaurant", "cafe", "coffee shop", "takeaway", "pizza", "kebab",
                      "indian restaurant", "chinese restaurant", "fish and chips"}
_HEALTH_KEYWORDS   = {"dentist", "dental", "optician", "optometrist", "personal trainer",
                      "gym", "physio", "physiotherapist", "chiropractor", "osteopath"}
_PROFESSIONAL_KEYWORDS = {"accountant", "solicitor", "lawyer", "estate agent", "letting agent",
                           "financial advisor", "bookkeeper", "mortgage broker",
                           "driving instructor", "driving school"}


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
        return f"{name} — missing out on {city} searches?"
    if sector == "beauty":
        return f"Quick question about {name}'s bookings"
    if sector == "food":
        return f"{name} — are you losing orders to competitors?"
    if sector == "health":
        return f"Quick question for {name}"
    if sector == "professional":
        return f"{name} — 3-5 leads a month you might be missing"
    return f"Quick question about {name}"


def _subject_follow_up_1(name: str, industry: str, city: str) -> str:
    return f"Re: {name}"


def _subject_follow_up_2(name: str, industry: str, city: str) -> str:
    return f"Last message — {name}"


def _body_initial(name: str, industry: str, city: str, review_count: str = "", pain_signals: str = "") -> str:
    sector = _sector(industry)
    has_pain = bool(pain_signals)

    try:
        rc = int(review_count)
    except (ValueError, TypeError):
        rc = 0

    high_reviews = rc >= 20

    # ── TRADES ────────────────────────────────────────────────
    if sector == "trade":
        if has_pain:
            body = (
                f"{name} has great reviews, but I'm seeing comments from customers saying they "
                f"couldn't find info online. That's probably costing you 3-5 enquiries a week — "
                f"basically one job a week you're not getting.\n\n"
                f"Is that something worth fixing, or are you fully booked from word-of-mouth?"
            )
        elif high_reviews:
            body = (
                f"Saw {name} on Google Maps — clearly doing well with {rc} reviews. "
                f"But when someone clicks through looking for a quote, there's nowhere to go except a phone number. "
                f"Most people won't call — they'll just move to the next {industry} with a proper site.\n\n"
                f"That's probably 3-5 jobs a week going elsewhere. Sound familiar?"
            )
        else:
            body = (
                f"Saw {name} on Google Maps, but when people click through there's nowhere to see your work "
                f"or get a quote — just a phone number. Most people won't call, they'll move to the next "
                f"{industry} with a proper site.\n\n"
                f"That's probably costing you 3-5 jobs a week. Sound familiar?"
            )

    # ── FOOD ──────────────────────────────────────────────────
    elif sector == "food":
        if has_pain:
            body = (
                f"I noticed customers are leaving comments saying they couldn't find {name}'s menu online. "
                f"Most people decide where to eat before they leave the house — if they can't find your menu, "
                f"they're going somewhere they can.\n\n"
                f"That's probably costing you 20-30 orders a week. Worth a quick chat?"
            )
        else:
            body = (
                f"Noticed {name} doesn't have a website with a menu. When someone's deciding between you "
                f"and the place down the road, they go with whoever makes it easiest — and right now "
                f"that's not {name}.\n\n"
                f"Most people want to browse a menu online before calling (especially when your line's busy). "
                f"That's probably costing you 20-30 orders a week. Worth discussing?"
            )

    # ── BEAUTY ────────────────────────────────────────────────
    elif sector == "beauty":
        if has_pain:
            body = (
                f"Came across {name} and noticed some customers saying they couldn't book online or find "
                f"your prices. A proper booking page would probably bring you 10-15 extra appointments "
                f"a month from people searching locally.\n\n"
                f"Worth a quick chat about that?"
            )
        else:
            body = (
                f"Most salons and barbers I work with get 10-15 extra bookings a month from people "
                f"searching '{industry} near me' once they have a proper booking page. "
                f"Is {name} missing out on that traffic, or are you fully booked?"
            )

    # ── HEALTH ────────────────────────────────────────────────
    elif sector == "health":
        if has_pain:
            body = (
                f"I noticed some reviews for {name} where people mentioned it was hard to find your "
                f"details or book online. New patients almost always check online before picking up the phone.\n\n"
                f"That's probably costing you 3-5 new patients a month. Is that something worth addressing?"
            )
        else:
            body = (
                f"Most people searching for a {industry} in {city} won't consider anyone without a "
                f"professional online presence — they do their research before making any calls.\n\n"
                f"Is {name} missing out on those searches, or are referrals keeping you fully booked?"
            )

    # ── PROFESSIONAL ──────────────────────────────────────────
    elif sector == "professional":
        body = (
            f"Most people searching for {industry} services in {city} won't even consider firms without "
            f"a professional website — they research online before contacting anyone.\n\n"
            f"That's probably costing {name} 3-5 qualified leads a month. "
            f"Are referrals keeping you busy enough, or is that worth fixing?"
        )

    # ── GENERIC ───────────────────────────────────────────────
    else:
        if has_pain:
            body = (
                f"{name} has some great reviews, but customers are mentioning they struggled to find "
                f"information online. That's likely losing you enquiries every week.\n\n"
                f"Is that something you're aware of, or are you getting enough business through word-of-mouth?"
            )
        else:
            body = (
                f"Most people in {city} looking for a {industry} will go with whoever they can find "
                f"online first. Right now, {name} isn't easy to find when people search.\n\n"
                f"Is that costing you enquiries, or are you already booked solid?"
            )

    return f"""Hi,

{body}

Best,
Zaid
zfkhan321@gmail.com

---
To stop receiving emails from me, reply with "STOP"."""


def _body_follow_up_1(name: str, industry: str, city: str, review_count: str = "", pain_signals: str = "") -> str:
    sector = _sector(industry)

    if sector == "trade":
        hook = (
            f"Just following up on my message from a few days ago about {name} missing out on "
            f"search traffic in {city}.\n\n"
            f"Still seeing {industry}s with basic sites picking up jobs that aren't findable online. "
            f"Is that something you're feeling, or are you covered?"
        )
    elif sector == "food":
        hook = (
            f"Following up on {name} — people are still deciding where to eat based on who has a "
            f"menu they can browse online.\n\n"
            f"If that's costing you orders, happy to chat. If you're fully booked, ignore this!"
        )
    elif sector == "beauty":
        hook = (
            f"Just checking in on {name}. Still getting enquiries about booking pages for "
            f"{industry}s in {city} — the ones with them are picking up a lot of the local search traffic.\n\n"
            f"Are you getting enough new clients, or is it worth a conversation?"
        )
    elif sector == "professional":
        hook = (
            f"Following up on {name}. People searching for {industry} services in {city} are still "
            f"skipping businesses without a professional online presence.\n\n"
            f"If referrals aren't keeping you as busy as you'd like, happy to talk."
        )
    else:
        hook = (
            f"Just following up on my message about {name}. "
            f"Still happy to chat if the enquiry side of things could be busier."
        )

    return f"""Hi,

{hook}

Best,
Zaid

---
To unsubscribe, reply "STOP"."""


def _body_follow_up_2(name: str, industry: str, city: str, review_count: str = "", pain_signals: str = "") -> str:
    sector = _sector(industry)

    if sector in ("trade", "beauty", "food"):
        close = (
            f"If things ever slow down or you want to stop relying purely on word-of-mouth, "
            f"just reply and I'll pick up where we left off."
        )
    else:
        close = (
            f"If the enquiry pipeline ever needs a boost, just reply to this and I'll be in touch."
        )

    return f"""Hi,

Last one from me — I won't follow up again after this.

{close}

All the best,
Zaid
zfkhan321@gmail.com

---
To unsubscribe, reply "STOP"."""


TEMPLATES = {
    INITIAL_TEMPLATE:      (_subject_initial,     _body_initial),
    FOLLOW_UP_1_TEMPLATE:  (_subject_follow_up_1, _body_follow_up_1),
    FOLLOW_UP_2_TEMPLATE:  (_subject_follow_up_2, _body_follow_up_2),
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
                "follow_up_2_sent", "follow_up_2_date", "replied", "unsubscribed",
                "send_status", "notes", "digest_sent"]:
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
    if row.get("unsubscribed"):
        return False
    if row.get("replied") == "yes":
        return False  # they replied — no follow-up needed
    if row.get("follow_up_1_sent"):
        return False
    if not row.get("contacted"):
        return False
    if not row.get("email", "").strip():
        return False
    days = _days_since(row.get("contacted_date", ""))
    return days is not None and days >= FOLLOW_UP_1_DAYS


def needs_follow_up_2(row: dict) -> bool:
    if row.get("unsubscribed"):
        return False
    if row.get("replied") == "yes":
        return False  # they replied — no follow-up needed
    if row.get("follow_up_2_sent"):
        return False
    if not row.get("follow_up_1_sent"):
        return False
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

    # Build a global set of email addresses already contacted across ALL rows —
    # prevents double-emailing if the same address appears in multiple CSV rows.
    globally_contacted: set = {
        r.get("email", "").strip().lower()
        for r in rows
        if r.get("contacted") == "yes" and r.get("email", "").strip()
    }

    # For follow-up phases, also collect addresses that have already received that follow-up.
    if template == FOLLOW_UP_1_TEMPLATE:
        globally_sent_phase: set = {
            r.get("email", "").strip().lower()
            for r in rows
            if r.get("follow_up_1_sent") == "yes" and r.get("email", "").strip()
        }
    elif template == FOLLOW_UP_2_TEMPLATE:
        globally_sent_phase = {
            r.get("email", "").strip().lower()
            for r in rows
            if r.get("follow_up_2_sent") == "yes" and r.get("email", "").strip()
        }
    else:
        globally_sent_phase = set()

    to_send = [r for r in rows if checker(r)]

    # Global dedup: skip rows whose email was already contacted in a previous run
    # (handles duplicate CSV entries with different fingerprints but same email)
    deduped, global_dup_count = [], 0
    seen_this_run: set = set()
    for r in to_send:
        addr = r.get("email", "").strip().lower()
        if not addr:
            continue
        if addr in globally_contacted and template == INITIAL_TEMPLATE:
            global_dup_count += 1
            continue
        if addr in globally_sent_phase:
            global_dup_count += 1
            continue
        if addr in seen_this_run:
            global_dup_count += 1
            continue
        seen_this_run.add(addr)
        deduped.append(r)

    if global_dup_count:
        log.info(f"[{template}] Skipped {global_dup_count} already-contacted address(es).")
    to_send = deduped

    if limit > 0:
        to_send = to_send[:limit]

    stats = {"phase": template, "to_send": len(to_send), "sent": 0, "failed": 0, "skipped": 0}

    if not to_send:
        log.info(f"[{template}] Nothing to send.")
        return stats

    log.info(f"[{template}] {len(to_send)} emails queued.")
    if template != INITIAL_TEMPLATE:
        replied_count = sum(1 for r in rows if r.get("replied") == "yes")
        log.info(f"[{template}] {replied_count} lead(s) skipped because they replied — follow-ups suppressed.")

    if sender and not dry_run:
        sender.connect()

    try:
        for i, row in enumerate(to_send):
            to_email = row.get("email", "").strip()

            # Extract and validate all template variables before rendering
            name     = row.get("name", "").strip()
            city     = (row.get("city") or row.get("search_location") or "").replace(", UK", "").strip()
            industry = (row.get("industry") or row.get("category") or row.get("search_keyword") or "").strip()

            if not name:
                log.warning(f"  SKIP [{i+1}] <{to_email}> — name is blank, would send a broken email")
                stats["skipped"] += 1
                continue
            if not city:
                log.warning(f"  SKIP [{i+1}] {name} <{to_email}> — city is blank")
                stats["skipped"] += 1
                continue
            if not industry:
                industry = "business"  # safe generic fallback

            review_count = row.get("review_count", "")
            pain_signals = row.get("pain_keywords_found", "")

            subject = subj_fn(name, industry, city)
            body    = body_fn(name, industry, city, review_count, pain_signals)

            # Final sanity check — catch any unreplaced placeholder that slipped through
            for placeholder in ("[Name]", "[Business Name]", "[City]", "[Industry]", "{name}", "{city}"):
                if placeholder in subject or placeholder in body:
                    log.warning(f"  SKIP [{i+1}] {name} — unreplaced placeholder found in template: {placeholder}")
                    stats["skipped"] += 1
                    break
            else:
                if dry_run:
                    log.info(f"  [DRY-RUN {i+1}/{len(to_send)}] → {name} <{to_email}>")
                    log.info(f"    Subject: {subject}")
                    log.info(f"    Preview: {body[:120].replace(chr(10), ' ')}…")
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
                    time.sleep(delay)

    finally:
        if sender and not dry_run:
            sender.close()

    return stats


# ─────────────────────────────────────────────────────────────
# PHONE DIGEST — leads with no email, sent to owner daily
# ─────────────────────────────────────────────────────────────

DIGEST_RECIPIENT = "zfkhan321@gmail.com"

def _is_mobile(phone: str) -> bool:
    """Returns True for UK mobile numbers (07xxx or +447xxx)."""
    p = phone.strip().replace(" ", "").replace("-", "")
    return p.startswith("07") or p.startswith("+447") or p.startswith("447")


def send_phone_digest(rows: list, gmail_user: str, app_password: str, dry_run: bool = False) -> int:
    """
    Email the owner a digest of new leads that have a phone number but no email.
    Marks each included row with digest_sent=yes so they're not repeated tomorrow.
    Returns count of leads included.
    """
    pending = [
        r for r in rows
        if r.get("phone", "").strip()
        and not r.get("email", "").strip()
        and not r.get("digest_sent", "").strip()
        and not r.get("unsubscribed", "").strip()
    ]

    if not pending:
        log.info("[digest] No new phone-only leads to send.")
        return 0

    # Sort: mobiles first, then by review count descending
    pending.sort(key=lambda r: (not _is_mobile(r.get("phone", "")), -int(r.get("review_count") or 0)))

    mobile_count  = sum(1 for r in pending if _is_mobile(r.get("phone", "")))
    landline_count = len(pending) - mobile_count

    log.info(f"[digest] {len(pending)} new phone-only leads ({mobile_count} mobiles, {landline_count} landlines).")

    if dry_run:
        for r in pending:
            log.info(f"  [DRY-RUN digest] {r.get('name')} — {r.get('phone')} ({r.get('city')})")
            r["digest_sent"] = datetime.now().strftime("%Y-%m-%d")
        return len(pending)

    # Build HTML table
    rows_html = ""
    for r in pending:
        phone = r.get("phone", "")
        is_mob = _is_mobile(phone)
        phone_style = "color:#1a5e20;font-weight:bold;" if is_mob else ""
        mob_label   = " 📱" if is_mob else ""
        maps_url = r.get("maps_url", "")
        name_cell = (
            f'<a href="{maps_url}" style="color:#1a73e8;text-decoration:none;">{r.get("name","")}</a>'
            if maps_url else r.get("name", "")
        )
        rows_html += f"""<tr>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;">{name_cell}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;">{r.get("industry") or r.get("category","")}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;">{r.get("city","")}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;{phone_style}">{phone}{mob_label}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;text-align:right;">{r.get("review_count","")}</td>
        </tr>"""

    today = datetime.now().strftime("%d %b %Y")
    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;color:#202124;margin:0;padding:20px;background:#f8f9fa;">
  <div style="max-width:900px;margin:0 auto;background:#fff;border-radius:8px;
              padding:28px 32px;box-shadow:0 1px 4px rgba(0,0,0,.15);">
    <h2 style="margin:0 0 4px;color:#1a73e8;font-size:20px;">Daily Leads — Phone Outreach</h2>
    <p style="margin:0 0 24px;color:#5f6368;font-size:13px;">
      {today} &nbsp;·&nbsp; <strong>{len(pending)}</strong> new leads &nbsp;·&nbsp;
      <strong style="color:#1a5e20;">{mobile_count} mobile</strong> &nbsp;·&nbsp;
      {landline_count} landline
    </p>
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      <thead>
        <tr style="background:#f1f3f4;">
          <th style="padding:9px 12px;text-align:left;font-weight:600;">Business</th>
          <th style="padding:9px 12px;text-align:left;font-weight:600;">Category</th>
          <th style="padding:9px 12px;text-align:left;font-weight:600;">City</th>
          <th style="padding:9px 12px;text-align:left;font-weight:600;">Phone</th>
          <th style="padding:9px 12px;text-align:right;font-weight:600;">Reviews</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
    <p style="margin:24px 0 0;font-size:11px;color:#80868b;border-top:1px solid #f1f3f4;padding-top:12px;">
      Mobile numbers highlighted in green. These leads have no website and no email on Google Maps.
    </p>
  </div>
</body>
</html>"""

    subject = f"[Leads] {len(pending)} new phone leads — {mobile_count} mobile — {today}"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = gmail_user
    msg["To"]      = DIGEST_RECIPIENT
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as s:
        s.ehlo(); s.starttls(); s.ehlo()
        s.login(gmail_user, app_password)
        s.sendmail(gmail_user, DIGEST_RECIPIENT, msg.as_string())

    now = datetime.now().strftime("%Y-%m-%d")
    for r in pending:
        r["digest_sent"] = now

    log.info(f"[digest] Sent {len(pending)} leads to {DIGEST_RECIPIENT}.")
    return len(pending)


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
    p.add_argument("--digest",    action="store_true",
                   help="Send phone-only digest to owner and run cold emails — the default combined mode")
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
                "follow_up_2_sent", "follow_up_2_date", "replied", "unsubscribed",
                "send_status", "notes", "digest_sent"]:
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

    # Send phone-only digest to owner (leads with no email but have a phone number)
    send_phone_digest(rows, gmail_user, app_pw, dry_run=args.dry_run)

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
