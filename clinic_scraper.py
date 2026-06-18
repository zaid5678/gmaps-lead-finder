#!/usr/bin/env python3
"""
One-off: finds UK clinics/practices with an email address but no website on Google Maps.
Sends a personalised cold email directly to each one, then emails a digest to owner.

Run in background:
    nohup .venv/bin/python clinic_scraper.py > output/clinic_scrape.log 2>&1 &
"""

import csv
import os
import re
import smtplib
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from email_validation import has_valid_mx
from scraper import (
    GoogleMapsScraper,
    TOP_50_UK_CITIES,
    deduplicate,
)

UK_TZ = ZoneInfo("Europe/London")


def _within_business_hours() -> bool:
    """Mon-Fri, 9am-5pm UK local time — outreach emails only go out during these hours."""
    now = datetime.now(UK_TZ)
    return now.weekday() < 5 and 9 <= now.hour < 17

# Skip review extraction — not needed for this one-off
GoogleMapsScraper._extract_recent_reviews = lambda self, max_reviews=5: []

load_dotenv()

KEYWORDS = [
    "GP surgery",
    "dental practice",
    "dentist",
    "optician",
    "optometrist",
    "physiotherapist",
    "chiropractor",
    "osteopath",
    "podiatrist",
    "pharmacy",
    "private clinic",
    "medical centre",
    "health clinic",
    "veterinary practice",
    "vet surgery",
]

OUTPUT_CSV   = Path("output/clinic_leads.csv")
DONE_FILE    = OUTPUT_CSV.with_suffix(".done")
OWNER_EMAIL  = "zfkhan321@gmail.com"
MAX_PER_SEARCH = 20


# ─── Email helpers ─────────────────────────────────────────────────────────────

def _gmail_creds():
    user = os.environ.get("GMAIL_EMAIL", os.environ.get("GMAIL_USER", "")).strip()
    pw   = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    return user, pw


def _subject(name: str, city: str, category: str) -> str:
    cat = category.lower()
    if "dental" in cat or "dentist" in cat:
        return f"Quick question about {name}'s new patient bookings"
    if "gp" in cat or "medical" in cat or "health" in cat or "clinic" in cat:
        return f"Helping {name} reach more patients in {city}"
    if "vet" in cat:
        return f"Quick idea for {name} — attracting more pet owners in {city}"
    if "physio" in cat or "osteo" in cat or "chiro" in cat:
        return f"{name} — missing out on {city} searches?"
    if "optician" in cat or "optom" in cat:
        return f"Quick question for {name} in {city}"
    return f"{name} — quick idea to reach more patients in {city}"


def _body(name: str, city: str, category: str, review_count: str) -> str:
    cat = category.lower()
    rc  = f"with {review_count} Google reviews" if review_count and review_count != "0" else ""

    if "dental" in cat or "dentist" in cat:
        hook = (
            f"I came across {name} on Google Maps {rc} — clearly a well-established practice.\n\n"
            f"One thing I noticed: when a new patient in {city} searches for a dentist and clicks through, "
            f"there's no website to land on. That's usually the moment they move on to the next result — "
            f"before they've even picked up the phone.\n\n"
            f"Most new patients decide which practice to contact based on what they find online. "
            f"Without a site showing your services, team, and how to book, you're probably losing "
            f"8–12 new patient enquiries a month to practices that do."
        )
        cta = "I build websites specifically for dental practices — focused on turning local searches into booked appointments, not just a brochure online."

    elif "vet" in cat:
        hook = (
            f"I spotted {name} on Google Maps {rc}.\n\n"
            f"When a pet owner in {city} searches for a vet and can't find a website with your services, "
            f"opening hours, and emergency contacts, they'll often just go to the next result. "
            f"That's a steady stream of new clients going elsewhere — probably 5–10 a month."
        )
        cta = "I build websites for veterinary practices — straightforward ones that convert local searches into first appointments."

    elif "physio" in cat or "osteo" in cat or "chiro" in cat:
        hook = (
            f"I came across {name} on Google {rc}.\n\n"
            f"When someone in {city} searches for a {category.lower()} after an injury or referral, "
            f"the first thing they do is check who has a website they can trust. Without one, "
            f"you're invisible at the exact moment they're ready to book — costing you roughly "
            f"5–8 new patient enquiries a week."
        )
        cta = "I specialise in websites for health and therapy practices — built to bring in local patients, not just look nice."

    elif "optician" in cat or "optom" in cat:
        hook = (
            f"I came across {name} on Google Maps {rc}.\n\n"
            f"When someone in {city} searches for an optician — whether it's for an eye test, "
            f"new glasses, or contact lenses — and clicks through to find no website, they almost "
            f"always go straight to the next result. You're likely losing 6–10 bookings a month that way."
        )
        cta = "I build websites for independent opticians that make it easy for local patients to find you, see your services, and book — all in one place."

    elif "pharmacy" in cat:
        hook = (
            f"I came across {name} on Google Maps {rc}.\n\n"
            f"Customers in {city} searching for a local pharmacy — especially for click-and-collect, "
            f"medication queries, or services like flu jabs — almost always check online first. "
            f"Without a website, you're missing that first touchpoint with dozens of potential regular customers."
        )
        cta = "I build clean, simple websites for independent pharmacies — focused on local visibility and showing your services clearly."

    else:
        # Generic clinic/GP/medical centre
        hook = (
            f"I came across {name} on Google Maps {rc}.\n\n"
            f"When a patient in {city} looks for a clinic or practice and can't find a website — "
            f"somewhere to check services, read about the team, and find out how to book — "
            f"they'll typically move on to another option. That's likely costing you 5–10 new "
            f"patient enquiries every week."
        )
        cta = "I build websites for medical and health practices — straightforward ones designed to bring in local patients and make it easy for them to contact you."

    return f"""Hi {name},

{hook}

{cta}

I can put together a quick mock-up specifically for {name} — no commitment, just so you can see how it would look and decide if it's worth a conversation.

Would that be useful?

Thanks,
Zaid
zfkhan321@gmail.com"""


def send_outreach(biz_row: dict, gmail_user: str, app_pw: str) -> bool:
    to = biz_row.get("email", "").strip()
    if not to:
        return False
    if not has_valid_mx(to):
        print(f"  ✗ Skipping {biz_row.get('name','')} — {to} has no valid mail domain (likely typo in source listing)")
        return False
    name     = biz_row.get("name", "the practice")
    city     = biz_row.get("city", "")
    cat      = biz_row.get("category", "")
    rc       = biz_row.get("review_count", "")
    subject  = _subject(name, city, cat)
    body     = _body(name, city, cat, rc)

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = gmail_user
        msg["To"]      = to
        msg.attach(MIMEText(body, "plain", "utf-8"))
        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.ehlo(); s.starttls(); s.ehlo()
            s.login(gmail_user, app_pw)
            s.sendmail(gmail_user, to, msg.as_string())
        print(f"  ✓ Emailed {name} <{to}>")
        return True
    except Exception as exc:
        print(f"  ✗ Email failed for {name} ({to}): {exc}")
        return False


def send_owner_digest(rows: list[dict], emailed: list[dict], gmail_user: str, app_pw: str):
    timestamp = datetime.now().strftime("%d %b %Y %H:%M")

    table_rows = ""
    for r in rows:
        name     = r.get("name", "")
        maps_url = r.get("maps_url", "")
        sent     = r.get("outreach_sent", "")
        tag      = ' <span style="background:#e6f4ea;color:#137333;padding:1px 6px;border-radius:3px;font-size:11px;">Emailed ✓</span>' if sent else ""
        name_cell = f'<a href="{maps_url}" style="color:#1a73e8;text-decoration:none;">{name}</a>' if maps_url else name
        table_rows += f"""
        <tr>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;">{name_cell}{tag}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;">{r.get("category","")}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;">{r.get("city","")}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;">{r.get("email","")}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;">{r.get("phone","")}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;text-align:right;">{r.get("review_count","")}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;color:#202124;margin:0;padding:20px;background:#f8f9fa;">
  <div style="max-width:1100px;margin:0 auto;background:#fff;border-radius:8px;padding:28px 32px;box-shadow:0 1px 4px rgba(0,0,0,.15);">
    <h2 style="margin:0 0 4px;color:#1a73e8;font-size:20px;">UK Clinic Leads — Email + No Website</h2>
    <p style="margin:0 0 24px;color:#5f6368;font-size:13px;">
      Scraped: <strong>{timestamp}</strong> &nbsp;·&nbsp;
      <strong>{len(rows)}</strong> clinics found &nbsp;·&nbsp;
      <strong style="color:#137333;">{len(emailed)} auto-emailed</strong>
    </p>
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      <thead>
        <tr style="background:#f1f3f4;">
          <th style="padding:9px 12px;text-align:left;">Name</th>
          <th style="padding:9px 12px;text-align:left;">Type</th>
          <th style="padding:9px 12px;text-align:left;">City</th>
          <th style="padding:9px 12px;text-align:left;">Email</th>
          <th style="padding:9px 12px;text-align:left;">Phone</th>
          <th style="padding:9px 12px;text-align:right;">Reviews</th>
        </tr>
      </thead>
      <tbody>{table_rows}</tbody>
    </table>
    <p style="margin:24px 0 0;font-size:11px;color:#80868b;border-top:1px solid #f1f3f4;padding-top:12px;">
      One-off clinic scrape — not added to the main leads pipeline.
    </p>
  </div>
</body>
</html>"""

    subject = f"[Clinic Leads] {len(rows)} found — {len(emailed)} auto-emailed — {timestamp}"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = gmail_user
    msg["To"]      = OWNER_EMAIL
    msg.attach(MIMEText(html, "html", "utf-8"))

    print(f"\nSending digest to {OWNER_EMAIL}…")
    with smtplib.SMTP("smtp.gmail.com", 587) as s:
        s.ehlo(); s.starttls(); s.ehlo()
        s.login(gmail_user, app_pw)
        s.sendmail(gmail_user, OWNER_EMAIL, msg.as_string())
    print(f"Digest sent — {len(rows)} leads, {len(emailed)} emailed.")


# ─── CSV helpers ───────────────────────────────────────────────────────────────

FIELDNAMES = [
    "name", "category", "city", "address", "phone", "email",
    "rating", "review_count", "maps_url", "outreach_sent", "scraped_at",
]


def _load_done() -> set:
    if DONE_FILE.exists():
        return set(DONE_FILE.read_text().splitlines())
    return set()


def _mark_done(key: str):
    with open(DONE_FILE, "a") as f:
        f.write(key + "\n")


def _existing_emails() -> set:
    if not OUTPUT_CSV.exists():
        return set()
    with open(OUTPUT_CSV, newline="", encoding="utf-8") as f:
        return {r.get("email", "").strip().lower() for r in csv.DictReader(f) if r.get("email")}


def _append_rows(rows: list):
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    write_header = not OUTPUT_CSV.exists()
    with open(OUTPUT_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        if write_header:
            w.writeheader()
        w.writerows(rows)


def _update_outreach(rows_to_update: list):
    """Re-write rows where outreach_sent changed."""
    if not OUTPUT_CSV.exists() or not rows_to_update:
        return
    updated_map = {r["email"].strip().lower(): r for r in rows_to_update if r.get("email")}
    with open(OUTPUT_CSV, newline="", encoding="utf-8") as f:
        all_rows = list(csv.DictReader(f))
    for row in all_rows:
        key = row.get("email", "").strip().lower()
        if key in updated_map:
            row["outreach_sent"] = updated_map[key].get("outreach_sent", "")
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_rows)


def _send_backlog(gmail_user: str, app_pw: str) -> int:
    """Send any leads found in a previous run that were queued because it was
    outside business hours at the time. Returns count sent."""
    if not OUTPUT_CSV.exists():
        return 0
    with open(OUTPUT_CSV, newline="", encoding="utf-8") as f:
        all_rows = list(csv.DictReader(f))

    pending = [r for r in all_rows if r.get("email") and not r.get("outreach_sent")]
    if not pending:
        return 0

    print(f"Sending {len(pending)} queued lead(s) from previous run(s)…")
    sent_count = 0
    for row in pending:
        if not _within_business_hours():
            print("  Ran out of business hours — remaining backlog will send next run.")
            break
        if send_outreach(row, gmail_user, app_pw):
            row["outreach_sent"] = datetime.now().strftime("%Y-%m-%d")
            sent_count += 1
            time.sleep(8)

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_rows)

    print(f"Backlog: {sent_count}/{len(pending)} sent.")
    return sent_count


# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-searches", type=int, default=0,
                    help="Stop after this many searches this run (0 = unlimited)")
    args = ap.parse_args()

    gmail_user, app_pw = _gmail_creds()
    if not gmail_user or not app_pw:
        print("ERROR: GMAIL_EMAIL / GMAIL_APP_PASSWORD not set in .env — aborting.")
        return

    if _within_business_hours():
        _send_backlog(gmail_user, app_pw)
    else:
        print("Outside business hours (Mon-Fri 9am-5pm UK) — skipping backlog send for now.")

    tasks = [(kw, city) for city in TOP_50_UK_CITIES for kw in KEYWORDS]
    total = len(tasks)
    done_keys     = _load_done()
    existing_emails = _existing_emails()

    print(f"Clinic scrape: {len(KEYWORDS)} keywords × {len(TOP_50_UK_CITIES)} cities = {total} searches")
    print(f"Already done: {len(done_keys)}  |  Existing emails tracked: {len(existing_emails)}")
    if args.max_searches:
        print(f"Cap this run:  {args.max_searches} searches")
    print(f"Output: {OUTPUT_CSV}\n")

    session_rows: list[dict] = []
    emailed_rows: list[dict] = []
    searches_this_run = 0

    with sync_playwright() as pw:
        scraper = GoogleMapsScraper(pw, headless=True)
        try:
            for i, (keyword, city) in enumerate(tasks):
                if args.max_searches and searches_this_run >= args.max_searches:
                    print(f"\nReached --max-searches cap ({args.max_searches}). Stopping to commit progress.")
                    break

                key = f"{keyword}|{city}"
                if key in done_keys:
                    continue

                print(f"[{i+1}/{total}] '{keyword}' in '{city}'")

                try:
                    results = scraper.extract_businesses(keyword, city, MAX_PER_SEARCH)
                except Exception as exc:
                    print(f"  ERROR: {exc} — skipping, rebuilding browser")
                    _mark_done(key)
                    done_keys.add(key)
                    try: scraper.close()
                    except Exception: pass
                    scraper = GoogleMapsScraper(pw, headless=True)
                    time.sleep(10)
                    continue

                # Filter: has email AND no real website
                qualifiers = [
                    b for b in deduplicate(results)
                    if b.email and not b.website
                    and b.email.lower() not in existing_emails
                ]
                print(f"  {len(results)} results → {len(qualifiers)} with email+no-website (new)")

                for b in qualifiers:
                    row = {
                        "name":          b.name,
                        "category":      keyword,
                        "city":          city.replace(", UK", ""),
                        "address":       b.address,
                        "phone":         b.phone,
                        "email":         b.email,
                        "rating":        b.rating,
                        "review_count":  b.review_count,
                        "maps_url":      b.maps_url,
                        "outreach_sent": "",
                        "scraped_at":    datetime.now().isoformat(),
                    }
                    if _within_business_hours():
                        sent = send_outreach(row, gmail_user, app_pw)
                        if sent:
                            row["outreach_sent"] = datetime.now().strftime("%Y-%m-%d")
                            emailed_rows.append(row)
                            time.sleep(8)   # brief pause between outreach sends
                    else:
                        print(f"  ⏸ Queued {row['name']} <{row['email']}> — outside business hours, will send next run")

                    session_rows.append(row)
                    existing_emails.add(b.email.lower())

                if qualifiers:
                    _append_rows([r for r in session_rows if r["email"].lower() in
                                  {b.email.lower() for b in qualifiers}])

                _mark_done(key)
                done_keys.add(key)
                searches_this_run += 1
                time.sleep(4)

        except KeyboardInterrupt:
            print("\nInterrupted — progress saved in .done file, re-run to resume.")
        finally:
            try: scraper.close()
            except Exception: pass

    if session_rows:
        _update_outreach(session_rows)

    print(f"\n{'─'*50}")
    print(f"Total new leads found: {len(session_rows)}")
    print(f"Auto-emailed:          {len(emailed_rows)}")

    if session_rows:
        send_owner_digest(session_rows, emailed_rows, gmail_user, app_pw)
    else:
        print("No qualifying clinics found this run.")

    # Clean up .done file when fully complete
    remaining = set(f"{kw}|{city}" for kw, city in tasks) - done_keys
    if not remaining:
        DONE_FILE.unlink(missing_ok=True)
        print("All searches complete — .done file removed.")

    print("Done.")


if __name__ == "__main__":
    main()
