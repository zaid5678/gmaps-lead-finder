#!/usr/bin/env python3
"""
notify_leads.py — Email a summary of today's new leads to the owner.

Reads all_leads.csv, finds leads scraped today, and sends a formatted
summary email via Gmail SMTP.

Usage:
    python notify_leads.py                        # sends if new leads found
    python notify_leads.py --dry-run              # print email without sending
    python notify_leads.py --to other@email.com   # override recipient
"""

import argparse
import csv
import os
import smtplib
import sys
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

CSV_PATH       = Path("output/all_leads.csv")
SENDER_EMAIL   = os.environ.get("GMAIL_EMAIL", os.environ.get("GMAIL_USER", "zfkhan321@gmail.com"))
SENDER_NAME    = "Lead Finder"
RECIPIENT      = "zfkhan321@gmail.com"
APP_PASSWORD   = os.environ.get("GMAIL_APP_PASSWORD", "")


def get_todays_leads(rows: list[dict]) -> list[dict]:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return [r for r in rows if r.get("scraped_at", "").startswith(today) and r.get("name", "").strip()]


TRADE_KEYWORDS = {
    "bricklayer", "carpenter", "joiner", "roofer", "scaffolder",
    "groundworker", "electrician", "plumber", "heating engineer",
    "gas engineer", "hvac engineer", "hvac", "plasterer",
    "painter decorator", "painter", "decorator", "tiler", "dryliner",
    "floor layer", "carpet fitter", "glazier", "window fitter",
    "landscaper", "stone mason", "stonemason", "locksmith", "paviour",
    "builder", "handyman", "window cleaner",
}


def _sector(industry: str) -> str:
    kw = industry.lower().strip()
    if any(k in kw for k in TRADE_KEYWORDS):
        return "Tradesmen"
    if any(k in kw for k in ("barber", "hair", "beauty", "nail", "salon", "groomer")):
        return "Beauty & Personal Care"
    if any(k in kw for k in ("restaurant", "cafe", "takeaway", "pub", "bar", "pizza")):
        return "Food & Hospitality"
    if any(k in kw for k in ("dentist", "physio", "chiropractor", "gym", "trainer", "vet")):
        return "Health & Fitness"
    if any(k in kw for k in ("accountant", "solicitor", "estate agent", "financial")):
        return "Professional Services"
    if "driving" in kw:
        return "Driving Instructors"
    return "Other"


def build_email(new_leads: list[dict], total_leads: int, cities: str) -> tuple[str, str]:
    n = len(new_leads)
    subject = f"{n} new lead{'s' if n != 1 else ''} found today — {cities}"

    # Group by broad sector, then by specific industry within each sector
    by_sector: dict[str, dict[str, list]] = {}
    for r in new_leads:
        ind    = r.get("industry", "unknown").strip().title()
        sector = _sector(r.get("industry", ""))
        by_sector.setdefault(sector, {}).setdefault(ind, []).append(r)

    lines = [
        "Hi Zaid,",
        "",
        f"The daily scraper found {n} new lead{'s' if n != 1 else ''} without a website.",
        f"Cities scraped today: {cities}",
        f"Total leads in database: {total_leads}",
        "",
    ]

    # Tradesmen first, then other sectors alphabetically
    sector_order = ["Tradesmen", "Driving Instructors", "Beauty & Personal Care",
                    "Food & Hospitality", "Health & Fitness", "Professional Services", "Other"]

    for sector in sector_order:
        if sector not in by_sector:
            continue
        industries = by_sector[sector]
        total_in_sector = sum(len(v) for v in industries.values())
        lines.append(f"━━━ {sector.upper()} ({total_in_sector}) ━━━━━━━━━━━━━━━━━━━━━")
        for ind, leads in sorted(industries.items()):
            lines.append(f"  ── {ind} ({len(leads)})")
            for r in leads:
                name  = r.get("name", "")
                city  = r.get("city", "")
                phone = r.get("phone", "") or "No phone listed"
                maps  = r.get("maps_url", "")
                lines.append(f"     • {name} — {city}")
                lines.append(f"       📞 {phone}")
                if maps:
                    lines.append(f"       🗺  {maps}")
            lines.append("")

    lines += [
        "─────────────────────────────────────────────",
        "View all leads: https://github.com/zaid5678/gmaps-lead-finder/blob/main/output/all_leads.csv",
        "",
        "— Lead Finder Bot",
    ]

    return subject, "\n".join(lines)


def send_email(subject: str, body: str, dry_run: bool = False, recipient: str = RECIPIENT):
    if dry_run:
        print(f"Subject: {subject}")
        print("─" * 60)
        print(body)
        return

    if not APP_PASSWORD or APP_PASSWORD == "xxxx xxxx xxxx xxxx":
        print("GMAIL_APP_PASSWORD not set — skipping email notification")
        sys.exit(0)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{SENDER_NAME} <{SENDER_EMAIL}>"
    msg["To"]      = recipient
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP("smtp.gmail.com", 587) as s:
        s.ehlo()
        s.starttls()
        s.ehlo()
        s.login(SENDER_EMAIL, APP_PASSWORD)
        s.sendmail(SENDER_EMAIL, recipient, msg.as_string())

    print(f"Notification sent to {recipient}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--to", default=RECIPIENT)
    ap.add_argument("--csv", default=str(CSV_PATH))
    args = ap.parse_args()

    if not Path(args.csv).exists():
        print(f"No CSV at {args.csv} — nothing to notify")
        sys.exit(0)

    with open(args.csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    new_leads = get_todays_leads(rows)

    if not new_leads:
        print("No new leads scraped today — skipping notification")
        sys.exit(0)

    cities = ", ".join(sorted({r.get("city", "") for r in new_leads if r.get("city")}))
    subject, body = build_email(new_leads, len(rows), cities)
    send_email(subject, body, dry_run=args.dry_run, recipient=args.to)


if __name__ == "__main__":
    main()
