#!/usr/bin/env python3
"""
Email automation for gmaps-lead-finder.

Reads leads from a CSV file, sends personalized cold emails via Gmail SMTP,
and tracks contacted leads by adding columns to the CSV.

Usage:
    # Preview emails without sending (dry-run)
    python email_sender.py --dry-run

    # Send initial outreach (uses latest leads_*.csv automatically)
    python email_sender.py --email you@gmail.com --password "xxxx xxxx xxxx xxxx"

    # Send follow-ups using a specific CSV
    python email_sender.py --csv-file output/leads_20260420.csv \\
                           --template follow_up \\
                           --email you@gmail.com --password "xxxx xxxx xxxx xxxx"

    # Load credentials from .env and override delay
    python email_sender.py --delay 15

Gmail app password: myaccount.google.com → Security → 2-Step Verification → App passwords
"""

import argparse
import csv
import logging
import os
import random
import smtplib
import sys
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

from email_templates import get_template, TEMPLATE_FUNCTIONS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("email_sender")

OUTPUT_DIR = Path("output")
CONFIG_PATH = Path("config.yaml")

DEFAULT_SMTP_SERVER = "smtp.gmail.com"
DEFAULT_SMTP_PORT = 587
DEFAULT_DELAY_MIN = 5.0
DEFAULT_DELAY_MAX = 10.0
DEFAULT_TEMPLATE = "initial"

# Columns added/managed by this script
TRACKING_COLUMNS = ["contacted", "contacted_date", "template_used", "send_status"]


def load_config() -> dict:
    if YAML_AVAILABLE and CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def find_latest_csv() -> Optional[Path]:
    """Return the most recently created leads_*.csv in the output directory."""
    csvs = sorted(OUTPUT_DIR.glob("leads_*.csv"))
    return csvs[-1] if csvs else None


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict]):
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def ensure_tracking_columns(rows: list[dict]) -> list[dict]:
    """Add tracking columns to any rows missing them."""
    for row in rows:
        for col in TRACKING_COLUMNS:
            row.setdefault(col, "")
    return rows


def already_sent_template(row: dict, template: str) -> bool:
    """True if this exact template was already sent to this lead."""
    if not row.get("contacted"):
        return False
    return template in row.get("template_used", "").split("|")


def mark_contacted(row: dict, template: str, status: str):
    row["contacted"] = "yes"
    row["contacted_date"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    existing = row.get("template_used", "")
    row["template_used"] = f"{existing}|{template}" if existing else template
    row["send_status"] = status


def _city_label(row: dict) -> str:
    city = (row.get("search_location") or row.get("city", "your city")).strip()
    return city.replace(", UK", "").replace(",UK", "").strip()


def _industry_label(row: dict) -> str:
    return (row.get("category") or row.get("search_keyword", "business")).strip()


def send_emails(
    rows: list[dict],
    gmail_user: str,
    app_password: str,
    template_name: str,
    delay_min: float,
    delay_max: float,
    dry_run: bool,
    smtp_server: str = DEFAULT_SMTP_SERVER,
    smtp_port: int = DEFAULT_SMTP_PORT,
    verbose: bool = False,
) -> dict:
    """Send emails to all leads with an email address that haven't been contacted yet."""
    stats = {"sent": 0, "skipped": 0, "failed": 0, "no_email": 0}

    sendable = []
    for row in rows:
        email = row.get("email", "").strip()
        if not email:
            stats["no_email"] += 1
            continue
        if already_sent_template(row, template_name):
            log.info(f"  SKIP (already sent '{template_name}'): {row.get('name', '?')} <{email}>")
            stats["skipped"] += 1
            continue
        sendable.append(row)

    log.info(
        f"Leads with email: {len(sendable) + stats['skipped']} | "
        f"No email: {stats['no_email']} | "
        f"Already sent '{template_name}': {stats['skipped']} | "
        f"To send now: {len(sendable)}"
    )

    if not sendable:
        return stats

    server: Optional[smtplib.SMTP] = None
    if not dry_run:
        log.info(f"Connecting to {smtp_server}:{smtp_port} as {gmail_user}…")
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(gmail_user, app_password)
        log.info("Connected.")

    try:
        for i, row in enumerate(sendable):
            name = row.get("name", "there").strip() or "there"
            city = _city_label(row)
            industry = _industry_label(row)
            to_email = row["email"].strip()

            try:
                tmpl = get_template(template_name, name, city, industry)
            except ValueError as exc:
                log.error(str(exc))
                sys.exit(1)

            if dry_run:
                log.info(f"  [DRY-RUN {i+1}/{len(sendable)}] → {name} <{to_email}>")
                log.info(f"    Subject: {tmpl.subject}")
                if verbose:
                    log.info(f"    Body:\n{tmpl.body}\n")
                else:
                    preview = tmpl.body[:120].replace("\n", " ").strip()
                    log.info(f"    Preview: {preview}…")
                mark_contacted(row, template_name, "dry-run")
                stats["sent"] += 1
            else:
                try:
                    msg = MIMEMultipart("alternative")
                    msg["Subject"] = tmpl.subject
                    msg["From"] = gmail_user
                    msg["To"] = to_email
                    msg.attach(MIMEText(tmpl.body, "plain", "utf-8"))
                    server.sendmail(gmail_user, to_email, msg.as_string())  # type: ignore[union-attr]
                    log.info(f"  SENT [{i+1}/{len(sendable)}]: {name} <{to_email}>")
                    mark_contacted(row, template_name, "sent")
                    stats["sent"] += 1
                except Exception as exc:
                    log.warning(f"  FAILED: {name} <{to_email}>: {exc}")
                    mark_contacted(row, template_name, f"failed: {exc}")
                    stats["failed"] += 1

            if i < len(sendable) - 1:
                delay = random.uniform(delay_min, delay_max)
                if not dry_run:
                    log.info(f"  Pausing {delay:.1f}s before next email…")
                    time.sleep(delay)

    finally:
        if server:
            try:
                server.quit()
            except Exception:
                pass

    return stats


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Send personalized cold emails to leads from a CSV file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  # Dry-run: preview all emails without sending
  python email_sender.py --dry-run --verbose

  # Live send using latest CSV (credentials from .env)
  python email_sender.py --email you@gmail.com --password "xxxx xxxx xxxx xxxx"

  # Send follow-ups to a specific CSV
  python email_sender.py --csv-file output/leads_20260420.csv --template follow_up

  # Slow down to 20s between emails
  python email_sender.py --delay 20
        """,
    )
    p.add_argument(
        "--csv-file", type=str,
        help="Path to leads CSV (default: latest output/leads_*.csv)",
    )
    p.add_argument(
        "--email", type=str, default=os.environ.get("GMAIL_USER", ""),
        help="Gmail address to send from (or set GMAIL_USER env var)",
    )
    p.add_argument(
        "--password", type=str, default=os.environ.get("GMAIL_APP_PASSWORD", ""),
        help="Gmail app password — 16 chars, spaces OK (or set GMAIL_APP_PASSWORD env var)",
    )
    p.add_argument(
        "--template", type=str, default=DEFAULT_TEMPLATE,
        choices=list(TEMPLATE_FUNCTIONS.keys()),
        help=f"Email template to use (default: {DEFAULT_TEMPLATE})",
    )
    p.add_argument(
        "--delay", type=float, default=None,
        help="Fixed delay in seconds between emails (overrides config min/max)",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Preview emails without sending — safe to run anytime",
    )
    p.add_argument(
        "--verbose", action="store_true",
        help="Print full email body in dry-run mode",
    )
    return p


def main():
    args = build_parser().parse_args()
    cfg = load_config()

    # Resolve settings: CLI > config.yaml > hardcoded defaults
    if args.delay is not None:
        delay_min = delay_max = args.delay
    else:
        delay_min = cfg.get("outreach", {}).get("delay_min", DEFAULT_DELAY_MIN)
        delay_max = cfg.get("outreach", {}).get("delay_max", DEFAULT_DELAY_MAX)

    smtp_server = cfg.get("email", {}).get("smtp_server", DEFAULT_SMTP_SERVER)
    smtp_port = int(cfg.get("email", {}).get("smtp_port", DEFAULT_SMTP_PORT))

    # Resolve CSV file
    if args.csv_file:
        csv_path = Path(args.csv_file)
    else:
        csv_path = find_latest_csv()

    if not csv_path or not csv_path.exists():
        log.error(
            "No leads CSV found. Run the scraper first, or pass --csv-file path/to/leads.csv\n"
            "  python scraper.py --send-email"
        )
        sys.exit(1)

    gmail_user = args.email.strip()
    app_password = args.password.strip()

    if not args.dry_run and (not gmail_user or not app_password):
        log.error(
            "Credentials required for live sends.\n"
            "  --email your@gmail.com --password 'xxxx xxxx xxxx xxxx'\n"
            "  or set GMAIL_USER and GMAIL_APP_PASSWORD in .env"
        )
        sys.exit(1)

    if args.dry_run:
        gmail_user = gmail_user or "preview@example.com"

    log.info("=" * 60)
    log.info("Email Sender — gmaps-lead-finder")
    log.info("=" * 60)
    log.info(f"CSV:      {csv_path}")
    log.info(f"Template: {args.template}")
    log.info(f"Delay:    {delay_min}–{delay_max}s between emails")
    log.info(f"Mode:     {'DRY-RUN (no emails will be sent)' if args.dry_run else 'LIVE'}")
    log.info("=" * 60)

    rows = read_csv(csv_path)
    if not rows:
        log.error("CSV is empty or has no valid rows.")
        sys.exit(1)

    rows = ensure_tracking_columns(rows)
    log.info(f"Loaded {len(rows)} leads")

    stats = send_emails(
        rows=rows,
        gmail_user=gmail_user,
        app_password=app_password,
        template_name=args.template,
        delay_min=delay_min,
        delay_max=delay_max,
        dry_run=args.dry_run,
        smtp_server=smtp_server,
        smtp_port=smtp_port,
        verbose=args.verbose,
    )

    # Write updated CSV (with tracking columns) back to disk
    write_csv(csv_path, rows)
    log.info(f"CSV updated: {csv_path}")

    log.info("\n" + "=" * 60)
    log.info("SUMMARY")
    log.info("=" * 60)
    log.info(f"  Sent:         {stats['sent']}")
    log.info(f"  Skipped:      {stats['skipped']}  (already sent this template)")
    log.info(f"  Failed:       {stats['failed']}")
    log.info(f"  No email:     {stats['no_email']}  (lead has no email address)")
    if args.dry_run:
        log.info("\n  Dry-run complete — no emails were actually sent.")
        log.info("  Remove --dry-run to send for real.")


if __name__ == "__main__":
    main()
