#!/usr/bin/env python3
"""
One-off: finds NHS GP surgeries, dentists, and pharmacies with an email
address but no website, using NHS.uk's public sitemaps + structured
JSON-LD data on each practice page. No Google Maps / Playwright involved —
plain HTTP, much faster and not subject to anti-bot measures.

Source: https://www.nhs.uk/sitemap-profiles-{gp,dentist,pharmacy}.xml
Each practice page embeds a <script id="json-ld-script"> block with
schema.org Physician/Dentist/Pharmacy data including "email" and "url".

Run in background:
    nohup .venv/bin/python nhs_clinic_scraper.py > output/nhs_scrape.log 2>&1 &
"""

import csv
import json
import os
import re
import smtplib
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

from email_validation import has_valid_mx

load_dotenv()

UK_TZ = ZoneInfo("Europe/London")


def _within_business_hours() -> bool:
    """Mon-Fri, 9am-5pm UK local time — outreach emails only go out during these hours."""
    now = datetime.now(UK_TZ)
    return now.weekday() < 5 and 9 <= now.hour < 17

SITEMAPS = {
    "GP surgery":  "https://www.nhs.uk/sitemap-profiles-gp.xml",
    "dentist":     "https://www.nhs.uk/sitemap-profiles-dentist.xml",
    "pharmacy":    "https://www.nhs.uk/sitemap-profiles-pharmacy.xml",
}

OUTPUT_CSV  = Path("output/nhs_clinic_leads.csv")
DONE_FILE   = OUTPUT_CSV.with_suffix(".done")
OWNER_EMAIL = "zfkhan321@gmail.com"
HEADERS     = {"User-Agent": "Mozilla/5.0 (compatible; lead-research/1.0)"}
WORKERS     = 8
JSON_LD_RE  = re.compile(r'id="json-ld-script"[^>]*>(.*?)</script>', re.S)

FIELDNAMES = [
    "name", "category", "address", "phone", "email",
    "maps_url", "outreach_sent", "scraped_at",
]


# ─── Sitemap + page fetching ───────────────────────────────────────────────

def _get_sitemap_urls(sitemap_url: str) -> list:
    resp = requests.get(sitemap_url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return re.findall(r"<loc>(.*?)</loc>", resp.text)


def _fetch_practice(url: str, category: str) -> dict | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        m = JSON_LD_RE.search(resp.text)
        if not m:
            return None
        raw = m.group(1).replace("&#x2B;", "+").replace("&amp;", "&")
        data = json.loads(raw)
    except Exception:
        return None

    email = (data.get("email") or "").strip()
    website = (data.get("url") or "").strip()
    if not email or website:
        return None   # need email present AND no website

    addr = data.get("address", {}) or {}
    address = ", ".join(filter(None, [
        addr.get("streetAddress", ""), addr.get("postalCode", ""),
    ]))

    return {
        "name":          data.get("name", "").strip(),
        "category":      category,
        "address":       address,
        "phone":         data.get("telephone", "").strip(),
        "email":         email,
        "maps_url":      url,
        "outreach_sent": "",
        "scraped_at":    datetime.now().isoformat(),
    }


# ─── Email helpers ──────────────────────────────────────────────────────────

def _gmail_creds():
    user = os.environ.get("GMAIL_EMAIL", os.environ.get("GMAIL_USER", "")).strip()
    pw   = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    return user, pw


def _subject(name: str, category: str) -> str:
    if category == "dentist":
        return f"Quick question about {name}'s new patient bookings"
    if category == "pharmacy":
        return f"Quick idea for {name} — reaching more local customers"
    return f"Helping {name} reach more patients online"


def _body(name: str, category: str) -> str:
    if category == "dentist":
        hook = (
            f"I found {name} listed on the NHS website, but couldn't find a website for the practice.\n\n"
            f"When a new patient searches for a dentist nearby and clicks through hoping to see your "
            f"services, team, or how to book, there's nowhere to land — so they often call the next "
            f"practice instead. That's likely costing a handful of new patient enquiries every week."
        )
        cta = "I build websites specifically for dental practices — focused on turning local searches into booked appointments."
    elif category == "pharmacy":
        hook = (
            f"I found {name} listed on the NHS website, but no website for the pharmacy itself.\n\n"
            f"Customers looking for click-and-collect, prescription queries, or services like flu jabs "
            f"usually check online first — without a website, that's a steady trickle of people going elsewhere."
        )
        cta = "I build simple, clear websites for independent pharmacies — built around local visibility."
    else:
        hook = (
            f"I found {name} listed on the NHS website, but couldn't find a website for the practice itself.\n\n"
            f"Patients increasingly expect to check opening hours, services, and how to get in touch online "
            f"before calling — without that, you're relying entirely on word of mouth and the NHS listing alone."
        )
        cta = "I build websites for GP practices and clinics — straightforward ones designed to make it easy for patients to find and contact you."

    return f"""Hi {name},

{hook}

{cta}

I can put together a quick mock-up specifically for {name} — no commitment, just so you can see how it would look.

Would that be useful?

Thanks,
Zaid
zfkhan321@gmail.com"""


def send_outreach(row: dict, gmail_user: str, app_pw: str) -> bool:
    to = row["email"]
    if not has_valid_mx(to):
        print(f"  ✗ Skipping {row['name']} — {to} has no valid mail domain (likely typo in NHS listing)")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = _subject(row["name"], row["category"])
        msg["From"]    = gmail_user
        msg["To"]      = to
        msg.attach(MIMEText(_body(row["name"], row["category"]), "plain", "utf-8"))
        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.ehlo(); s.starttls(); s.ehlo()
            s.login(gmail_user, app_pw)
            s.sendmail(gmail_user, to, msg.as_string())
        print(f"  ✓ Emailed {row['name']} <{to}>")
        return True
    except Exception as exc:
        print(f"  ✗ Email failed for {row['name']} ({to}): {exc}")
        return False


def send_owner_digest(rows: list, emailed: list, gmail_user: str, app_pw: str):
    timestamp = datetime.now().strftime("%d %b %Y %H:%M")
    table_rows = ""
    for r in rows:
        tag = ' <span style="background:#e6f4ea;color:#137333;padding:1px 6px;border-radius:3px;font-size:11px;">Emailed ✓</span>' if r.get("outreach_sent") else ""
        table_rows += f"""
        <tr>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;">{r.get("name","")}{tag}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;">{r.get("category","")}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;">{r.get("address","")}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;">{r.get("email","")}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;">{r.get("phone","")}</td>
        </tr>"""

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;color:#202124;margin:0;padding:20px;background:#f8f9fa;">
  <div style="max-width:1100px;margin:0 auto;background:#fff;border-radius:8px;padding:28px 32px;box-shadow:0 1px 4px rgba(0,0,0,.15);">
    <h2 style="margin:0 0 4px;color:#1a73e8;font-size:20px;">NHS Clinic Leads — Email + No Website</h2>
    <p style="margin:0 0 24px;color:#5f6368;font-size:13px;">
      Source: NHS.uk public directory &nbsp;·&nbsp; Scraped: <strong>{timestamp}</strong> &nbsp;·&nbsp;
      <strong>{len(rows)}</strong> found &nbsp;·&nbsp;
      <strong style="color:#137333;">{len(emailed)} auto-emailed</strong>
    </p>
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      <thead><tr style="background:#f1f3f4;">
        <th style="padding:9px 12px;text-align:left;">Name</th>
        <th style="padding:9px 12px;text-align:left;">Type</th>
        <th style="padding:9px 12px;text-align:left;">Address</th>
        <th style="padding:9px 12px;text-align:left;">Email</th>
        <th style="padding:9px 12px;text-align:left;">Phone</th>
      </tr></thead>
      <tbody>{table_rows}</tbody>
    </table>
    <p style="margin:24px 0 0;font-size:11px;color:#80868b;border-top:1px solid #f1f3f4;padding-top:12px;">
      One-off NHS directory scrape — not added to the main leads pipeline.
    </p>
  </div>
</body></html>"""

    subject = f"[NHS Clinic Leads] {len(rows)} found — {len(emailed)} auto-emailed — {timestamp}"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = gmail_user
    msg["To"]      = OWNER_EMAIL
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP("smtp.gmail.com", 587) as s:
        s.ehlo(); s.starttls(); s.ehlo()
        s.login(gmail_user, app_pw)
        s.sendmail(gmail_user, OWNER_EMAIL, msg.as_string())
    print(f"Digest sent — {len(rows)} leads, {len(emailed)} emailed.")


# ─── CSV / progress helpers ─────────────────────────────────────────────────

def _load_done() -> set:
    return set(DONE_FILE.read_text().splitlines()) if DONE_FILE.exists() else set()


def _existing_emails() -> set:
    if not OUTPUT_CSV.exists():
        return set()
    with open(OUTPUT_CSV, newline="", encoding="utf-8") as f:
        return {r["email"].strip().lower() for r in csv.DictReader(f) if r.get("email")}


def _append_row(row: dict):
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    write_header = not OUTPUT_CSV.exists()
    with open(OUTPUT_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        if write_header:
            w.writeheader()
        w.writerow(row)


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
            time.sleep(5)

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_rows)

    print(f"Backlog: {sent_count}/{len(pending)} sent.")
    return sent_count


# ─── Main ───────────────────────────────────────────────────────────────────

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-pages", type=int, default=0, help="Stop after this many pages this run (0 = unlimited)")
    args = ap.parse_args()

    gmail_user, app_pw = _gmail_creds()
    if not gmail_user or not app_pw:
        print("ERROR: GMAIL_EMAIL / GMAIL_APP_PASSWORD not set — aborting.")
        return

    if _within_business_hours():
        _send_backlog(gmail_user, app_pw)
    else:
        print("Outside business hours (Mon-Fri 9am-5pm UK) — skipping backlog send for now.")

    print("Fetching NHS sitemaps…")
    all_tasks = []
    for category, sitemap_url in SITEMAPS.items():
        urls = _get_sitemap_urls(sitemap_url)
        print(f"  {category}: {len(urls)} pages")
        all_tasks.extend((u, category) for u in urls)

    total = len(all_tasks)
    done_keys = _load_done()
    existing_emails = _existing_emails()
    remaining = [(u, c) for u, c in all_tasks if u not in done_keys]
    if args.max_pages:
        remaining = remaining[:args.max_pages]

    print(f"Total pages: {total}  |  Already done: {len(done_keys)}  |  This run: {len(remaining)}\n")

    session_rows, emailed_rows = [], []

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(_fetch_practice, u, c): (u, c) for u, c in remaining}
        processed = 0
        for fut in as_completed(futures):
            url, category = futures[fut]
            processed += 1
            try:
                row = fut.result()
            except Exception as exc:
                row = None
                print(f"  ERROR fetching {url}: {exc}")

            if row and row["email"].lower() not in existing_emails:
                if _within_business_hours():
                    sent = send_outreach(row, gmail_user, app_pw)
                    if sent:
                        row["outreach_sent"] = datetime.now().strftime("%Y-%m-%d")
                        emailed_rows.append(row)
                        time.sleep(5)
                else:
                    print(f"  ⏸ Queued {row['name']} <{row['email']}> — outside business hours, will send next run")
                _append_row(row)
                session_rows.append(row)
                existing_emails.add(row["email"].lower())

            with open(DONE_FILE, "a") as f:
                f.write(url + "\n")

            if processed % 200 == 0:
                print(f"  …{processed}/{len(remaining)} pages checked, {len(session_rows)} leads found so far")

    print(f"\n{'─'*50}")
    print(f"New leads found: {len(session_rows)}  |  Auto-emailed: {len(emailed_rows)}")

    if session_rows:
        send_owner_digest(session_rows, emailed_rows, gmail_user, app_pw)
    else:
        print("No qualifying NHS leads found this run.")

    done_now = _load_done()
    if len(done_now) >= total:
        DONE_FILE.unlink(missing_ok=True)
        print("All NHS pages processed — .done file removed.")

    print("Done.")


if __name__ == "__main__":
    main()
