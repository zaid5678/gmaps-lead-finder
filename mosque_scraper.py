#!/usr/bin/env python3
"""
One-off scraper: finds UK mosques/masjids with no website on Google Maps.
Results saved to output/mosque_leads.csv and emailed to zfkhan321@gmail.com.
Does NOT touch roofers_leads.csv.
"""

import csv
import os
import smtplib
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from scraper import (
    GoogleMapsScraper,
    TOP_50_UK_CITIES,
    deduplicate,
    filter_leads,
    sort_by_opportunity,
)

# Disable review extraction for this one-off run — keeps each listing visit fast
GoogleMapsScraper._extract_recent_reviews = lambda self, max_reviews=5: []

load_dotenv()

KEYWORDS   = ["mosque", "masjid"]
OUTPUT_CSV = Path("output/mosque_leads.csv")
RECIPIENT  = "zfkhan321@gmail.com"
MAX_RESULTS_PER_SEARCH = 20
RESUME_FROM_CITY = ""  # set to a city name to resume, e.g. "Cardiff, UK"


def build_email_html(leads, timestamp):
    rows = ""
    for b in leads:
        name_cell = (
            f'<a href="{b.maps_url}" style="color:#1a73e8;text-decoration:none;">{b.name}</a>'
            if b.maps_url else b.name
        )
        rows += f"""
        <tr>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;">{name_cell}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;">{b.search_location.replace(", UK","")}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;">{b.address}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;">{b.phone}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;text-align:right;">{b.review_count}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;text-align:center;">{b.rating:.1f}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Mosque Leads — {timestamp}</title></head>
<body style="font-family:Arial,sans-serif;color:#202124;margin:0;padding:20px;background:#f8f9fa;">
  <div style="max-width:1000px;margin:0 auto;background:#fff;border-radius:8px;
              padding:28px 32px;box-shadow:0 1px 4px rgba(0,0,0,.15);">
    <h2 style="margin:0 0 4px;color:#1a73e8;font-size:20px;">
      UK Mosques &amp; Masjids — No Website Found
    </h2>
    <p style="margin:0 0 24px;color:#5f6368;font-size:13px;">
      Scraped: <strong>{timestamp}</strong> &nbsp;·&nbsp;
      <strong>{len(leads)}</strong> mosques/masjids with no website across all UK cities
    </p>
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      <thead>
        <tr style="background:#f1f3f4;">
          <th style="padding:9px 12px;text-align:left;font-weight:600;color:#3c4043;">Name</th>
          <th style="padding:9px 12px;text-align:left;font-weight:600;color:#3c4043;">City</th>
          <th style="padding:9px 12px;text-align:left;font-weight:600;color:#3c4043;">Address</th>
          <th style="padding:9px 12px;text-align:left;font-weight:600;color:#3c4043;">Phone</th>
          <th style="padding:9px 12px;text-align:right;font-weight:600;color:#3c4043;">Reviews</th>
          <th style="padding:9px 12px;text-align:center;font-weight:600;color:#3c4043;">Rating</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    <p style="margin:24px 0 0;font-size:11px;color:#80868b;border-top:1px solid #f1f3f4;padding-top:12px;">
      One-off scrape — results not added to the main leads pipeline.
    </p>
  </div>
</body>
</html>"""


def send_email_from_csv(rows, timestamp):
    """Send all leads from CSV rows (dicts) in a single email."""
    gmail_user   = os.environ.get("GMAIL_USER", "").strip()
    app_password = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    if not gmail_user or not app_password:
        print("ERROR: GMAIL_USER / GMAIL_APP_PASSWORD not set — skipping email.")
        return

    table_rows = ""
    for r in rows:
        name     = r.get("name", "")
        maps_url = r.get("maps_url", "")
        name_cell = f'<a href="{maps_url}" style="color:#1a73e8;text-decoration:none;">{name}</a>' if maps_url else name
        table_rows += f"""
        <tr>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;">{name_cell}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;">{r.get("city","")}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;">{r.get("address","")}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;">{r.get("phone","")}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;text-align:right;">{r.get("review_count","")}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;text-align:center;">{r.get("rating","")}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Mosque Leads — {timestamp}</title></head>
<body style="font-family:Arial,sans-serif;color:#202124;margin:0;padding:20px;background:#f8f9fa;">
  <div style="max-width:1000px;margin:0 auto;background:#fff;border-radius:8px;
              padding:28px 32px;box-shadow:0 1px 4px rgba(0,0,0,.15);">
    <h2 style="margin:0 0 4px;color:#1a73e8;font-size:20px;">
      UK Mosques &amp; Masjids — No Website Found
    </h2>
    <p style="margin:0 0 24px;color:#5f6368;font-size:13px;">
      Scraped: <strong>{timestamp}</strong> &nbsp;·&nbsp;
      <strong>{len(rows)}</strong> mosques/masjids with no website across all UK cities
    </p>
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      <thead>
        <tr style="background:#f1f3f4;">
          <th style="padding:9px 12px;text-align:left;font-weight:600;color:#3c4043;">Name</th>
          <th style="padding:9px 12px;text-align:left;font-weight:600;color:#3c4043;">City</th>
          <th style="padding:9px 12px;text-align:left;font-weight:600;color:#3c4043;">Address</th>
          <th style="padding:9px 12px;text-align:left;font-weight:600;color:#3c4043;">Phone</th>
          <th style="padding:9px 12px;text-align:right;font-weight:600;color:#3c4043;">Reviews</th>
          <th style="padding:9px 12px;text-align:center;font-weight:600;color:#3c4043;">Rating</th>
        </tr>
      </thead>
      <tbody>{table_rows}</tbody>
    </table>
    <p style="margin:24px 0 0;font-size:11px;color:#80868b;border-top:1px solid #f1f3f4;padding-top:12px;">
      One-off scrape — results not added to the main leads pipeline.
    </p>
  </div>
</body>
</html>"""

    subject = f"[Mosque Leads] {len(rows)} UK mosques/masjids with no website — {timestamp}"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = gmail_user
    msg["To"]      = RECIPIENT
    msg.attach(MIMEText(html, "html", "utf-8"))

    print(f"Sending email to {RECIPIENT}…")
    with smtplib.SMTP("smtp.gmail.com", 587) as s:
        s.ehlo(); s.starttls(); s.ehlo()
        s.login(gmail_user, app_password)
        s.sendmail(gmail_user, RECIPIENT, msg.as_string())
    print(f"Email sent — {len(rows)} leads.")


def send_email(leads, timestamp):
    gmail_user   = os.environ.get("GMAIL_USER", "").strip()
    app_password = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    if not gmail_user or not app_password:
        print("ERROR: GMAIL_USER / GMAIL_APP_PASSWORD not set — skipping email.")
        return

    subject  = f"[Mosque Leads] {len(leads)} UK mosques/masjids with no website — {timestamp}"
    html     = build_email_html(leads, timestamp)
    msg      = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = gmail_user
    msg["To"]      = RECIPIENT
    msg.attach(MIMEText(html, "html", "utf-8"))

    print(f"Sending email to {RECIPIENT}…")
    with smtplib.SMTP("smtp.gmail.com", 587) as s:
        s.ehlo(); s.starttls(); s.ehlo()
        s.login(gmail_user, app_password)
        s.sendmail(gmail_user, RECIPIENT, msg.as_string())
    print(f"Email sent — {len(leads)} leads.")


def save_csv(leads, append=False):
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "name", "city", "address", "phone", "rating", "review_count",
        "maps_url", "category", "scraped_at",
    ]
    mode = "a" if append else "w"
    with open(OUTPUT_CSV, mode, newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if not append:
            w.writeheader()
        for b in leads:
            w.writerow({
                "name":         b.name,
                "city":         b.search_location.replace(", UK", "").strip(),
                "address":      b.address,
                "phone":        b.phone,
                "rating":       b.rating,
                "review_count": b.review_count,
                "maps_url":     b.maps_url,
                "category":     b.category,
                "scraped_at":   datetime.now().isoformat(),
            })
    print(f"{'Appended' if append else 'Saved'} {len(leads)} leads → {OUTPUT_CSV}")


def main():
    # Resume from a specific city if set
    cities = TOP_50_UK_CITIES
    if RESUME_FROM_CITY:
        try:
            start_idx = cities.index(RESUME_FROM_CITY)
            cities = cities[start_idx:]
            print(f"Resuming from '{RESUME_FROM_CITY}' ({len(cities)} cities remaining)")
        except ValueError:
            pass

    tasks = [(kw, city) for city in cities for kw in KEYWORDS]
    total = len(tasks)
    print(f"Starting mosque scrape: {len(KEYWORDS)} keywords × {len(cities)} cities = {total} searches")
    print(f"Output: {OUTPUT_CSV}")

    # Auto-resume: figure out which searches already have results saved
    done_keys = set()
    if OUTPUT_CSV.exists():
        with open(OUTPUT_CSV, newline="", encoding="utf-8") as f:
            saved = list(csv.DictReader(f))
        # Re-derive which (keyword, city) combos were saved by checking scraped cities
        # We track this via a sidecar file
        done_file = OUTPUT_CSV.with_suffix(".done")
        if done_file.exists():
            done_keys = set(done_file.read_text().splitlines())
        print(f"Resuming — {len(done_keys)} searches already done, {len(saved)} leads saved")
    else:
        done_file = OUTPUT_CSV.with_suffix(".done")

    all_businesses = []

    with sync_playwright() as pw:
        scraper = GoogleMapsScraper(pw, headless=True)
        try:
            for i, (keyword, city) in enumerate(tasks):
                key = f"{keyword}|{city}"
                if key in done_keys:
                    print(f"[{i+1}/{total}] Skipping (already done): '{keyword}' in '{city}'")
                    continue

                print(f"\n[{i+1}/{total}] '{keyword}' in '{city}'")
                results = scraper.extract_businesses(keyword, city, MAX_RESULTS_PER_SEARCH)
                all_businesses.extend(results)

                # Save this search's no-website leads immediately
                unique_so_far = deduplicate(all_businesses)
                leads_so_far  = filter_leads(unique_so_far, min_reviews=0)
                # Only write new ones (not previously saved)
                existing_urls = set()
                if OUTPUT_CSV.exists():
                    with open(OUTPUT_CSV, newline="", encoding="utf-8") as f:
                        existing_urls = {r.get("maps_url","") for r in csv.DictReader(f)}
                new_leads = [b for b in leads_so_far if b.maps_url not in existing_urls]
                if new_leads:
                    save_csv(new_leads, append=OUTPUT_CSV.exists())

                # Mark this search as done
                with open(done_file, "a") as f:
                    f.write(key + "\n")
                done_keys.add(key)

                if i < total - 1:
                    time.sleep(5)
        except KeyboardInterrupt:
            print("\nInterrupted — progress saved, re-run to continue.")
        finally:
            scraper.close()

    # Read full CSV and email everything in one go
    if not OUTPUT_CSV.exists():
        print("No leads found.")
        return

    with open(OUTPUT_CSV, newline="", encoding="utf-8") as f:
        all_rows = list(csv.DictReader(f))
    print(f"\nTotal leads across all cities: {len(all_rows)}")

    timestamp = datetime.now().strftime("%d %b %Y %H:%M")
    send_email_from_csv(all_rows, timestamp)

    # Clean up sidecar file
    if done_file.exists():
        done_file.unlink()

    print("\nDone.")


if __name__ == "__main__":
    main()
