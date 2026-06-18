#!/usr/bin/env python3
"""
International lead scraper — finds businesses without websites on Google Maps
across Ireland, Australia, Canada and the USA.

For each lead found:
  - If the business has an email address → sends a personalised cold email directly to them
  - All leads (with or without email) → saved to output/international_leads.csv
  - A daily digest of all new leads is sent to the owner (zfkhan321@gmail.com)

Keeps its own CSV and .done sidecar — completely separate from UK leads.

Usage:
    python international_scraper.py
    python international_scraper.py --dry-run
    python international_scraper.py --country Ireland
    python international_scraper.py --max-results 15
"""

import argparse
import csv
import os
import smtplib
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

from email_validation import has_valid_mx
from playwright.sync_api import sync_playwright

from scraper import GoogleMapsScraper, TOP_50_UK_CITIES, deduplicate, filter_leads
from scraper_master import INTERNATIONAL_CITIES, INTERNATIONAL_CITIES_FLAT, COUNTRY_CURRENCY, city_country

# Disable review extraction for speed
GoogleMapsScraper._extract_recent_reviews = lambda self, max_reviews=5: []

load_dotenv()

OUTPUT_CSV   = Path("output/international_leads.csv")
DONE_FILE    = Path("output/international_leads.done")
OWNER_EMAIL  = "zfkhan321@gmail.com"
FIELDNAMES   = [
    "name", "country", "city", "address", "phone", "email",
    "rating", "review_count", "maps_url", "category", "scraped_at",
    "outreach_sent", "digest_sent",
]

# Niche trades over generic services — small/local operators in these categories
# are far less likely to have a website than plumbers/restaurants/salons in big metros
# (the original generic list returned zero no-website leads across 4 runs in major cities).
KEYWORDS = [
    "roofer", "bricklayer", "tiler", "plasterer", "landscaper",
    "locksmith", "handyman", "driving instructor", "tree surgeon",
    "carpet cleaner", "window cleaner", "gardener",
]


# ─────────────────────────────────────────────────────────────
# EMAIL HELPERS
# ─────────────────────────────────────────────────────────────

def _gmail_creds():
    user = os.environ.get("GMAIL_EMAIL", os.environ.get("GMAIL_USER", "")).strip()
    pw   = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    return user, pw


def _smtp_send(gmail_user: str, app_pw: str, to: str, subject: str, body: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"Zaid <{gmail_user}>"
    msg["To"]      = to
    msg.attach(MIMEText(body, "plain", "utf-8"))
    with smtplib.SMTP("smtp.gmail.com", 587) as s:
        s.ehlo(); s.starttls(); s.ehlo()
        s.login(gmail_user, app_pw)
        s.sendmail(gmail_user, to, msg.as_string())


def _cold_email_subject(name: str, industry: str, city: str, country: str) -> str:
    if any(k in industry.lower() for k in ("barber", "hair", "beauty", "nail", "groomer")):
        return f"Quick question about {name}'s bookings"
    if any(k in industry.lower() for k in ("restaurant", "cafe", "takeaway", "pizza")):
        return f"{name} — losing orders to competitors?"
    if any(k in industry.lower() for k in ("accountant", "solicitor", "lawyer", "financial")):
        return f"{name} — 3-5 leads a month you might be missing"
    return f"{name} — missing out on {city} searches?"


def _cold_email_body(name: str, industry: str, city: str, country: str, review_count: str = "") -> str:
    try:
        rc = int(review_count)
    except (ValueError, TypeError):
        rc = 0

    high_reviews = rc >= 20

    if any(k in industry.lower() for k in ("barber", "hair", "beauty", "nail", "groomer")):
        if high_reviews:
            body = (
                f"{name} clearly has a loyal following with {rc} reviews. But most new clients "
                f"search '{industry} near me' and book whoever has a proper site they can browse — "
                f"right now that's not {name}.\n\n"
                f"That's probably 10-15 bookings a month going elsewhere. Is that something you're feeling?"
            )
        else:
            body = (
                f"Most salons and barbers I work with pick up 10-15 extra bookings a month from people "
                f"searching '{industry} near me' once they have a proper booking page. "
                f"Is {name} missing out on that traffic, or are you fully booked?"
            )

    elif any(k in industry.lower() for k in ("restaurant", "cafe", "takeaway")):
        body = (
            f"Noticed {name} doesn't have a website with a menu. When someone's deciding where to eat "
            f"in {city}, they go with whoever makes it easiest to browse — and right now that's not {name}.\n\n"
            f"Most people want to see a menu before calling (especially when the line's busy). "
            f"That's probably 20-30 orders a week going elsewhere. Worth discussing?"
        )

    elif any(k in industry.lower() for k in ("plumber", "electrician", "roofer", "builder",
                                               "painter", "locksmith", "gardener", "cleaner",
                                               "window", "handyman")):
        if high_reviews:
            body = (
                f"{name} has {rc} reviews — clearly doing well. But when someone clicks through on "
                f"Google Maps looking for a quote, there's nowhere to go except a phone number. "
                f"Most people won't call — they'll move to the next {industry} with a proper site.\n\n"
                f"That's probably 3-5 jobs a week going elsewhere. Sound familiar?"
            )
        else:
            body = (
                f"Saw {name} on Google Maps, but when people click through there's nowhere to see your "
                f"work or get a quote — just a phone number. Most people won't call, they'll move to the "
                f"next {industry} with a proper site.\n\n"
                f"That's probably costing you 3-5 jobs a week. Sound familiar?"
            )

    elif "driving" in industry.lower():
        body = (
            f"Most learner drivers search '{industry} in {city}' and go with whoever has a proper site "
            f"where they can see rates and book a lesson. Right now {name} isn't giving them anywhere to do that.\n\n"
            f"That's probably 5-8 new learners a month going to someone else. Is that worth addressing?"
        )

    elif any(k in industry.lower() for k in ("accountant", "solicitor", "lawyer", "financial", "mortgage")):
        body = (
            f"Most people searching for {industry} services in {city} won't consider anyone without a "
            f"professional website — they research online before contacting anyone.\n\n"
            f"That's probably costing {name} 3-5 qualified leads a month. "
            f"Are referrals keeping you busy enough, or is that worth fixing?"
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
{OWNER_EMAIL}

---
To stop receiving emails from me, reply with "STOP"."""


def send_outreach_email(biz_dict: dict, gmail_user: str, app_pw: str, dry_run: bool = False) -> bool:
    """Send cold email directly to a business. Returns True if sent."""
    to_email = biz_dict.get("email", "").strip()
    if not to_email:
        return False
    if not has_valid_mx(to_email):
        print(f"  ✗ Skipping {biz_dict.get('name','')} — {to_email} has no valid mail domain (likely typo in source listing)")
        return False

    name         = biz_dict.get("name", "there")
    industry     = biz_dict.get("category", "business")
    city         = biz_dict.get("city", "")
    country      = biz_dict.get("country", "")
    review_count = biz_dict.get("review_count", "")

    subject = _cold_email_subject(name, industry, city, country)
    body    = _cold_email_body(name, industry, city, country, review_count)

    if dry_run:
        print(f"  [DRY-RUN] Would email {name} <{to_email}>: {subject}")
        return True

    try:
        _smtp_send(gmail_user, app_pw, to_email, subject, body)
        print(f"  Emailed {name} <{to_email}>")
        return True
    except Exception as exc:
        print(f"  FAILED emailing {name} <{to_email}>: {exc}")
        return False


def send_owner_digest(new_rows: list, gmail_user: str, app_pw: str, dry_run: bool = False):
    """Email the owner a digest of all new international leads found today."""
    if not new_rows:
        return

    today = datetime.now().strftime("%d %b %Y")
    emailed  = [r for r in new_rows if r.get("outreach_sent") == "yes"]
    no_email = [r for r in new_rows if r.get("outreach_sent") != "yes"]

    rows_html = ""
    for r in new_rows:
        maps_url  = r.get("maps_url", "")
        name_cell = (
            f'<a href="{maps_url}" style="color:#1a73e8;text-decoration:none;">{r["name"]}</a>'
            if maps_url else r["name"]
        )
        outreach = (
            '<span style="color:#1a5e20;font-weight:bold;">✓ Emailed</span>'
            if r.get("outreach_sent") == "yes" else ""
        )
        rows_html += f"""<tr>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;">{name_cell}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;">{r.get("country","")}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;">{r.get("city","")}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;">{r.get("category","")}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;">{r.get("phone","")}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;">{r.get("email","")}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;">{r.get("review_count","")}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;">{outreach}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;color:#202124;margin:0;padding:20px;background:#f8f9fa;">
  <div style="max-width:1100px;margin:0 auto;background:#fff;border-radius:8px;
              padding:28px 32px;box-shadow:0 1px 4px rgba(0,0,0,.15);">
    <h2 style="margin:0 0 4px;color:#1a73e8;font-size:20px;">International Leads — {today}</h2>
    <p style="margin:0 0 24px;color:#5f6368;font-size:13px;">
      <strong>{len(new_rows)}</strong> new leads &nbsp;·&nbsp;
      <strong style="color:#1a5e20;">{len(emailed)} auto-emailed</strong> &nbsp;·&nbsp;
      {len(no_email)} phone-only
    </p>
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      <thead>
        <tr style="background:#f1f3f4;">
          <th style="padding:9px 12px;text-align:left;font-weight:600;">Business</th>
          <th style="padding:9px 12px;text-align:left;font-weight:600;">Country</th>
          <th style="padding:9px 12px;text-align:left;font-weight:600;">City</th>
          <th style="padding:9px 12px;text-align:left;font-weight:600;">Category</th>
          <th style="padding:9px 12px;text-align:left;font-weight:600;">Phone</th>
          <th style="padding:9px 12px;text-align:left;font-weight:600;">Email</th>
          <th style="padding:9px 12px;text-align:right;font-weight:600;">Reviews</th>
          <th style="padding:9px 12px;text-align:left;font-weight:600;">Outreach</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
    <p style="margin:24px 0 0;font-size:11px;color:#80868b;border-top:1px solid #f1f3f4;padding-top:12px;">
      Leads marked "Emailed" had an email address on Google Maps and were contacted automatically.
      Phone-only leads require manual outreach.
    </p>
  </div>
</body>
</html>"""

    subject = f"[International Leads] {len(new_rows)} new — {len(emailed)} auto-emailed — {today}"

    if dry_run:
        print(f"[DRY-RUN] Would send digest of {len(new_rows)} leads to {OWNER_EMAIL}")
        return

    try:
        _smtp_send(gmail_user, app_pw, OWNER_EMAIL, subject, html)
        print(f"Digest sent to {OWNER_EMAIL} — {len(new_rows)} leads.")
    except Exception as exc:
        print(f"Failed to send digest: {exc}")


# ─────────────────────────────────────────────────────────────
# CSV HELPERS
# ─────────────────────────────────────────────────────────────

def _load_done() -> set:
    if DONE_FILE.exists():
        return set(DONE_FILE.read_text().splitlines())
    return set()


def _mark_done(key: str):
    with open(DONE_FILE, "a") as f:
        f.write(key + "\n")


def _existing_urls() -> set:
    if not OUTPUT_CSV.exists():
        return set()
    with open(OUTPUT_CSV, newline="", encoding="utf-8") as f:
        return {r.get("maps_url", "") for r in csv.DictReader(f)}


def _append_rows(rows: list):
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if OUTPUT_CSV.exists() else "w"
    with open(OUTPUT_CSV, mode, newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        if mode == "w":
            w.writeheader()
        w.writerows(rows)


def _update_rows(updated: list):
    """Rewrite the full CSV (used to update outreach_sent/digest_sent flags)."""
    if not OUTPUT_CSV.exists():
        return
    with open(OUTPUT_CSV, newline="", encoding="utf-8") as f:
        all_rows = list(csv.DictReader(f))
    updated_urls = {r["maps_url"]: r for r in updated if r.get("maps_url")}
    for row in all_rows:
        if row.get("maps_url") in updated_urls:
            row.update(updated_urls[row["maps_url"]])
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_rows)


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Scrape international leads and email them.")
    p.add_argument("--country",      default=None, help="Limit to one country (Ireland/Australia/Canada/USA)")
    p.add_argument("--max-results",  type=int, default=10, help="Results per search (default 10)")
    p.add_argument("--max-searches", type=int, default=120, help="Max searches per run, then stop and email (default 120)")
    p.add_argument("--dry-run",      action="store_true")
    args = p.parse_args()

    gmail_user, app_pw = _gmail_creds()
    if not gmail_user or not app_pw:
        print("ERROR: GMAIL_EMAIL / GMAIL_APP_PASSWORD not set in .env")
        return

    # Build task list
    if args.country:
        cities_by_country = {args.country: INTERNATIONAL_CITIES.get(args.country, [])}
    else:
        cities_by_country = INTERNATIONAL_CITIES

    tasks = [
        (kw, city, country)
        for country, cities in cities_by_country.items()
        for city in cities
        for kw in KEYWORDS
    ]
    total = len(tasks)
    done_keys = _load_done()
    existing  = _existing_urls()

    print(f"International scrape: {total} searches across {sum(len(c) for c in cities_by_country.values())} cities")
    print(f"Already done: {len(done_keys)} / {total}  |  Cap this run: {args.max_searches} searches")

    session_new: list = []
    searches_this_run = 0

    with sync_playwright() as pw:
        scraper = GoogleMapsScraper(pw, headless=True)
        try:
            for i, (keyword, city, country) in enumerate(tasks):
                if searches_this_run >= args.max_searches:
                    print(f"\nReached --max-searches cap ({args.max_searches}). Stopping to commit progress.")
                    break

                key = f"{keyword}|{city}|{country}"
                if key in done_keys:
                    continue

                location = f"{city}, {country}"
                print(f"\n[{i+1}/{total}] '{keyword}' in '{location}'")

                try:
                    results = scraper.extract_businesses(keyword, location, args.max_results)
                except Exception as exc:
                    print(f"  ERROR: {exc} — skipping")
                    _mark_done(key)
                    try: scraper.close()
                    except Exception: pass
                    scraper = GoogleMapsScraper(pw, headless=True)
                    time.sleep(10)
                    continue

                # Filter: no website only
                no_site = [b for b in results if not b.website]
                new     = [b for b in no_site if b.maps_url not in existing]
                print(f"  {len(results)} results → {len(no_site)} no-website → {len(new)} new")

                for b in new:
                    row = {
                        "name":         b.name,
                        "country":      country,
                        "city":         city,
                        "address":      b.address,
                        "phone":        b.phone,
                        "email":        b.email if hasattr(b, "email") else "",
                        "rating":       b.rating,
                        "review_count": b.review_count,
                        "maps_url":     b.maps_url,
                        "category":     keyword,
                        "scraped_at":   datetime.now().isoformat(),
                        "outreach_sent": "",
                        "digest_sent":   "",
                    }
                    # Email the business directly if they have an email
                    if row["email"]:
                        sent = send_outreach_email(row, gmail_user, app_pw, dry_run=args.dry_run)
                        if sent:
                            row["outreach_sent"] = datetime.now().strftime("%Y-%m-%d")
                            time.sleep(5)  # brief pause between outreach sends

                    session_new.append(row)
                    existing.add(b.maps_url)

                if new:
                    new_urls = {b.maps_url for b in new}
                    _append_rows([r for r in session_new if r.get("maps_url") in new_urls])

                _mark_done(key)
                done_keys.add(key)
                searches_this_run += 1
                time.sleep(5)

        except KeyboardInterrupt:
            print("\nInterrupted — progress saved.")
        finally:
            try: scraper.close()
            except Exception: pass

    # Update any outreach_sent flags written during this session
    if session_new:
        _update_rows(session_new)

    print(f"\n{len(session_new)} new leads found this run.")

    # Send owner digest for all new leads found this session
    if session_new:
        send_owner_digest(session_new, gmail_user, app_pw, dry_run=args.dry_run)

    print("Done.")


if __name__ == "__main__":
    main()
