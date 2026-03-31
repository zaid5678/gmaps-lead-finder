#!/usr/bin/env python3
"""
Google Maps Lead Scraper — finds UK businesses WITHOUT websites.
Emails new leads daily to a configured recipient.

Usage:
    python scraper.py
    python scraper.py --keywords "barber,cafe" --cities "London, UK|Manchester, UK" --min-reviews 30
    python scraper.py --send-email   # scrape + email new leads
"""

import argparse
import csv
import hashlib
import json
import logging
import os
import random
import re
import smtplib
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

from playwright.sync_api import sync_playwright, Page, Playwright, Browser, TimeoutError as PwTimeout

# ─────────────────────────────────────────────────────────────
# CONFIGURATION — edit these defaults or override via CLI args
# ─────────────────────────────────────────────────────────────
DEFAULT_KEYWORDS = [
    "barber",
    "plumber",
    "electrician",
    "restaurant",
    "cafe",
    "dentist",
    "personal trainer",
    "car mechanic",
]

DEFAULT_LOCATIONS = [
    "London, UK",
    "Manchester, UK",
    "Birmingham, UK",
    "Leeds, UK",
    "Liverpool, UK",
    "Bristol, UK",
    "Sheffield, UK",
    "Nottingham, UK",
    "Leicester, UK",
    "Newcastle, UK",
]

DEFAULT_MIN_REVIEWS = 50
DEFAULT_MIN_RATING = 0.0
DEFAULT_MAX_RESULTS_PER_SEARCH = 15
OUTPUT_DIR = Path("output")
HEADLESS = True

# Email
EMAIL_RECIPIENT = "zfkhan321@gmail.com"
SEEN_LEADS_PATH = OUTPUT_DIR / "seen_leads.json"

# Anti-detection tuning
MIN_DELAY = 1.0
MAX_DELAY = 3.0
SCROLL_PAUSE = 1.5
MAX_SCROLL_ATTEMPTS = 60

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("gmaps_scraper")


# ─────────────────────────────────────────────────────────────
# DATA MODEL
# ─────────────────────────────────────────────────────────────
@dataclass
class Business:
    name: str = ""
    address: str = ""
    phone: str = ""
    rating: float = 0.0
    review_count: int = 0
    website: str = ""
    category: str = ""
    instagram: str = ""
    third_party_only: str = ""
    search_keyword: str = ""
    search_location: str = ""
    maps_url: str = ""

    @property
    def fingerprint(self) -> str:
        """Deduplication key based on name + address."""
        raw = f"{self.name.lower().strip()}|{self.address.lower().strip()}"
        return hashlib.md5(raw.encode()).hexdigest()

    @property
    def has_website(self) -> bool:
        """True if the business has a real website (not a food delivery portal)."""
        if not self.website:
            return False
        aggregators = [
            "ubereats", "just-eat", "justeat", "deliveroo",
            "foodhub", "hungryhouse", "menulog",
        ]
        return not any(agg in self.website.lower() for agg in aggregators)


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
def human_delay(lo: float = MIN_DELAY, hi: float = MAX_DELAY):
    time.sleep(random.uniform(lo, hi))


def parse_review_count(text: str) -> int:
    if not text:
        return 0
    text = text.strip().strip("()")
    text = text.replace(",", "").replace(" ", "")
    m = re.match(r"([\d.]+)[kK]", text)
    if m:
        return int(float(m.group(1)) * 1000)
    m = re.search(r"(\d+)", text)
    return int(m.group(1)) if m else 0


def parse_rating(text: str) -> float:
    if not text:
        return 0.0
    text = text.replace(",", ".")
    m = re.search(r"(\d+\.?\d*)", text)
    return float(m.group(1)) if m else 0.0


def detect_third_party(page: Page) -> str:
    aggregators_found = []
    try:
        body_text = page.locator('[role="main"]').inner_text(timeout=2000)
        for name in ["Uber Eats", "Just Eat", "Deliveroo", "Foodhub"]:
            if name.lower() in body_text.lower():
                aggregators_found.append(name)
    except Exception:
        pass
    return ", ".join(aggregators_found)


def extract_instagram(page: Page) -> str:
    try:
        links = page.locator('a[href*="instagram.com"]').all()
        if links:
            return links[0].get_attribute("href") or ""
    except Exception:
        pass
    return ""


# ─────────────────────────────────────────────────────────────
# CORE SCRAPER
# ─────────────────────────────────────────────────────────────
class GoogleMapsScraper:
    """Drives a headless Chromium browser to scrape Google Maps listings."""

    MAPS_URL = "https://www.google.com/maps"

    def __init__(self, pw: Playwright, headless: bool = HEADLESS):
        self.pw = pw
        self.browser: Browser = pw.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        self.context = self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="en-GB",
            timezone_id="Europe/London",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            geolocation={"latitude": 51.5074, "longitude": -0.1278},
            permissions=["geolocation"],
        )
        self.page: Page = self.context.new_page()
        self.page.add_init_script("""
            const observer = new MutationObserver(() => {
                const btn = document.querySelector(
                    'button[aria-label="Accept all"], form[action*="consent"] button'
                );
                if (btn) { btn.click(); observer.disconnect(); }
            });
            observer.observe(document.body || document.documentElement, {
                childList: true, subtree: true
            });
        """)

    # ── navigation ──────────────────────────────────────────
    def _accept_cookies(self):
        try:
            for selector in [
                'button:has-text("Accept all")',
                'button:has-text("Reject all")',
                'button[aria-label="Accept all"]',
                '[action*="consent"] button:first-child',
                'form[action*="consent"] button',
            ]:
                btn = self.page.locator(selector).first
                if btn.is_visible(timeout=2000):
                    btn.click()
                    human_delay(2, 3)
                    self.page.wait_for_load_state("domcontentloaded", timeout=15000)
                    human_delay(1, 2)
                    return
        except Exception:
            pass

    def _handle_consent_redirect(self):
        if "consent.google" in self.page.url:
            log.info("Google consent page detected — accepting…")
            self._accept_cookies()
            human_delay(2, 4)

    def navigate_to_maps(self):
        log.info("Loading Google Maps…")
        self.page.goto(self.MAPS_URL, wait_until="domcontentloaded", timeout=30000)
        human_delay(1, 2)
        self._handle_consent_redirect()
        self._accept_cookies()
        human_delay(1, 2)

    # ── searching ───────────────────────────────────────────
    def search(self, query: str):
        """Navigate directly to the Maps search URL for the given query."""
        log.info(f"Searching: {query}")
        search_url = f"{self.MAPS_URL}/search/{quote_plus(query)}/"
        self.page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        human_delay(1, 2)
        self._handle_consent_redirect()
        self._accept_cookies()
        human_delay(3, 5)

    # ── scrolling results panel ─────────────────────────────
    def _get_results_panel(self):
        selectors = [
            'div[role="feed"]',
            'div.m6QErb[aria-label]',
            'div.m6QErb.DxyBCb',
        ]
        for sel in selectors:
            el = self.page.locator(sel).first
            try:
                if el.is_visible(timeout=3000):
                    return el
            except Exception:
                continue
        return None

    def scroll_results(self, max_results: int) -> int:
        panel = self._get_results_panel()
        if not panel:
            log.warning("Could not find results panel — may be a single-result page")
            return 0

        prev_count = 0
        stale_rounds = 0

        for attempt in range(MAX_SCROLL_ATTEMPTS):
            items = self.page.locator('div[role="feed"] > div > div[jsaction]').all()
            count = len(items)

            if count >= max_results:
                log.info(f"Reached target of {max_results} visible results ({count} loaded)")
                break

            try:
                end_marker = self.page.locator('span.HlvSq').first
                if end_marker.is_visible(timeout=500):
                    log.info(f"End of results reached ({count} loaded)")
                    break
            except Exception:
                pass

            panel.evaluate("el => el.scrollTop = el.scrollHeight")
            time.sleep(SCROLL_PAUSE + random.uniform(0, 0.8))

            if count == prev_count:
                stale_rounds += 1
                if stale_rounds >= 5:
                    log.info(f"No new results after {stale_rounds} scrolls — stopping ({count} loaded)")
                    break
            else:
                stale_rounds = 0

            prev_count = count

            if attempt % 10 == 0 and attempt > 0:
                log.info(f"  …scrolled {attempt} times, {count} results so far")

        final_count = len(self.page.locator('div[role="feed"] > div > div[jsaction]').all())
        log.info(f"Scroll complete — {final_count} results loaded")
        return final_count

    # ── extracting a single business ────────────────────────
    def _extract_detail_from_panel(self) -> dict:
        data = {}

        try:
            data["name"] = self.page.locator('h1.DUwDvf').first.inner_text(timeout=3000)
        except Exception:
            data["name"] = ""

        try:
            data["category"] = self.page.locator(
                'button[jsaction="pane.rating.category"]'
            ).first.inner_text(timeout=2000)
        except Exception:
            data["category"] = ""

        try:
            rating_el = self.page.locator('div.F7nice span[aria-hidden="true"]').first
            data["rating"] = parse_rating(rating_el.inner_text(timeout=2000))
        except Exception:
            data["rating"] = 0.0

        try:
            review_el = self.page.locator('div.F7nice span[aria-label*="review"]').first
            label = review_el.get_attribute("aria-label") or ""
            data["review_count"] = parse_review_count(label)
        except Exception:
            data["review_count"] = 0

        try:
            addr_btn = self.page.locator('button[data-item-id="address"]').first
            data["address"] = addr_btn.get_attribute("aria-label") or ""
            data["address"] = re.sub(r"^Address:\s*", "", data["address"])
        except Exception:
            data["address"] = ""

        try:
            phone_btn = self.page.locator('button[data-item-id*="phone"]').first
            data["phone"] = phone_btn.get_attribute("aria-label") or ""
            data["phone"] = re.sub(r"^Phone:\s*", "", data["phone"])
        except Exception:
            data["phone"] = ""

        try:
            website_link = self.page.locator('a[data-item-id="authority"]').first
            data["website"] = website_link.get_attribute("href") or ""
        except Exception:
            data["website"] = ""

        data["instagram"] = extract_instagram(self.page)
        data["third_party_only"] = detect_third_party(self.page)

        return data

    # ── main extraction loop ────────────────────────────────
    def extract_businesses(self, keyword: str, location: str, max_results: int) -> list[Business]:
        query = f"{keyword} in {location}"
        self.search(query)

        loaded = self.scroll_results(max_results)
        if loaded == 0:
            log.warning(f"No results found for '{query}'")
            return []

        listing_links: list[str] = []
        items = self.page.locator('div[role="feed"] a[href*="/maps/place/"]').all()
        for item in items:
            try:
                href = item.get_attribute("href")
                if href and href not in listing_links:
                    listing_links.append(href)
            except Exception:
                continue

        listing_links = listing_links[:max_results]
        log.info(f"Collected {len(listing_links)} unique place links for '{query}'")

        businesses: list[Business] = []
        for idx, link in enumerate(listing_links):
            try:
                log.debug(f"  [{idx+1}/{len(listing_links)}] Opening listing…")
                self.page.goto(link, wait_until="domcontentloaded", timeout=20000)
                human_delay(1.5, 3.0)

                data = self._extract_detail_from_panel()
                biz = Business(
                    name=data.get("name", ""),
                    address=data.get("address", ""),
                    phone=data.get("phone", ""),
                    rating=data.get("rating", 0.0),
                    review_count=data.get("review_count", 0),
                    website=data.get("website", ""),
                    category=data.get("category", ""),
                    instagram=data.get("instagram", ""),
                    third_party_only=data.get("third_party_only", ""),
                    search_keyword=keyword,
                    search_location=location,
                    maps_url=link,
                )
                businesses.append(biz)

                if (idx + 1) % 10 == 0:
                    log.info(f"  Extracted {idx+1}/{len(listing_links)} businesses")

            except PwTimeout:
                log.warning(f"  Timeout on listing {idx+1} — skipping")
                continue
            except Exception as exc:
                log.warning(f"  Error on listing {idx+1}: {exc} — skipping")
                continue

            if random.random() < 0.05:
                pause = random.uniform(5, 10)
                log.info(f"  Anti-detection pause ({pause:.1f}s)…")
                time.sleep(pause)

        log.info(f"Extracted {len(businesses)} total businesses for '{query}'")
        return businesses

    # ── cleanup ─────────────────────────────────────────────
    def close(self):
        try:
            self.context.close()
            self.browser.close()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────
# FILTERING & DEDUPLICATION
# ─────────────────────────────────────────────────────────────
def filter_leads(
    businesses: list[Business],
    min_reviews: int = DEFAULT_MIN_REVIEWS,
    min_rating: float = DEFAULT_MIN_RATING,
) -> list[Business]:
    leads = []
    for biz in businesses:
        if biz.has_website:
            continue
        if biz.review_count < min_reviews:
            continue
        if biz.rating < min_rating:
            continue
        leads.append(biz)
    return leads


def deduplicate(businesses: list[Business]) -> list[Business]:
    seen: set[str] = set()
    unique: list[Business] = []
    for biz in businesses:
        fp = biz.fingerprint
        if fp not in seen:
            seen.add(fp)
            unique.append(biz)
    return unique


def sort_by_opportunity(businesses: list[Business]) -> list[Business]:
    return sorted(businesses, key=lambda b: b.review_count, reverse=True)


# ─────────────────────────────────────────────────────────────
# CSV EXPORT
# ─────────────────────────────────────────────────────────────
def save_csv(businesses: list[Business], filepath: Path):
    filepath.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "name", "address", "phone", "rating", "review_count",
        "website", "category", "instagram", "third_party_only",
        "search_keyword", "search_location", "maps_url",
    ]
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for biz in businesses:
            row = asdict(biz)
            writer.writerow({k: row[k] for k in fieldnames})
    log.info(f"Saved {len(businesses)} rows → {filepath}")


# ─────────────────────────────────────────────────────────────
# SEEN-LEADS TRACKING
# ─────────────────────────────────────────────────────────────
def load_seen_leads(path: Path = SEEN_LEADS_PATH) -> dict:
    """Load seen-leads registry: {fingerprint: ISO-timestamp}."""
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            log.warning("seen_leads.json is malformed — treating as empty")
            return {}
        return data
    except (json.JSONDecodeError, OSError) as exc:
        log.warning(f"Could not read seen_leads.json: {exc} — treating as empty")
        return {}


def save_seen_leads(seen: dict, path: Path = SEEN_LEADS_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(seen, f, indent=2, ensure_ascii=False)
    log.info(f"Saved seen-leads registry ({len(seen)} total) → {path}")


def filter_new_leads(leads: list[Business], seen: dict) -> list[Business]:
    """Return only leads not already in the seen registry."""
    return [biz for biz in leads if biz.fingerprint not in seen]


def mark_leads_seen(leads: list[Business], seen: dict) -> dict:
    """Add leads to the seen registry with current UTC timestamp."""
    now_iso = datetime.now(timezone.utc).isoformat()
    for biz in leads:
        fp = biz.fingerprint
        if fp not in seen:
            seen[fp] = now_iso
    return seen


# ─────────────────────────────────────────────────────────────
# EMAIL
# ─────────────────────────────────────────────────────────────
def build_email_html(leads: list[Business], run_timestamp: str) -> str:
    rows_html = ""
    for biz in leads:
        name_cell = (
            f'<a href="{biz.maps_url}" style="color:#1a73e8;text-decoration:none;">{biz.name}</a>'
            if biz.maps_url
            else biz.name
        )
        ig_cell = (
            f'<a href="{biz.instagram}" style="color:#1a73e8;">Instagram</a>'
            if biz.instagram
            else ""
        )
        rows_html += f"""
        <tr>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;">{name_cell}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;">{biz.category}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;">{biz.search_location}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;">{biz.phone}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;text-align:right;font-weight:bold;">{biz.review_count}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;text-align:center;">{biz.rating:.1f}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;">{ig_cell}</td>
          <td style="padding:6px 12px;border-bottom:1px solid #e8eaed;">{biz.third_party_only}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>New UK Leads — {run_timestamp}</title>
</head>
<body style="font-family:Arial,sans-serif;color:#202124;margin:0;padding:20px;background:#f8f9fa;">
  <div style="max-width:1100px;margin:0 auto;background:#fff;border-radius:8px;
              padding:28px 32px;box-shadow:0 1px 4px rgba(0,0,0,.15);">

    <h2 style="margin:0 0 4px;color:#1a73e8;font-size:20px;">
      Google Maps Lead Finder — New UK Leads
    </h2>
    <p style="margin:0 0 24px;color:#5f6368;font-size:13px;">
      Run completed: <strong>{run_timestamp}</strong> &nbsp;·&nbsp;
      <strong>{len(leads)}</strong> new lead(s) — businesses with no website and high review counts
    </p>

    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      <thead>
        <tr style="background:#f1f3f4;">
          <th style="padding:9px 12px;text-align:left;font-weight:600;color:#3c4043;">Business</th>
          <th style="padding:9px 12px;text-align:left;font-weight:600;color:#3c4043;">Category</th>
          <th style="padding:9px 12px;text-align:left;font-weight:600;color:#3c4043;">City</th>
          <th style="padding:9px 12px;text-align:left;font-weight:600;color:#3c4043;">Phone</th>
          <th style="padding:9px 12px;text-align:right;font-weight:600;color:#3c4043;">Reviews</th>
          <th style="padding:9px 12px;text-align:center;font-weight:600;color:#3c4043;">Rating</th>
          <th style="padding:9px 12px;text-align:left;font-weight:600;color:#3c4043;">Social</th>
          <th style="padding:9px 12px;text-align:left;font-weight:600;color:#3c4043;">3rd Party</th>
        </tr>
      </thead>
      <tbody>{rows_html}
      </tbody>
    </table>

    <p style="margin:24px 0 0;font-size:11px;color:#80868b;border-top:1px solid #f1f3f4;padding-top:12px;">
      Sent automatically by gmaps-lead-finder. Leads are businesses with no website
      meeting the minimum review threshold — sorted by review count (highest demand first).
    </p>
  </div>
</body>
</html>"""


def send_email(leads: list[Business], run_timestamp: str):
    """Send HTML email of new leads via Gmail SMTP.
    Reads GMAIL_USER and GMAIL_APP_PASSWORD from environment variables.
    """
    gmail_user = os.environ.get("GMAIL_USER", "").strip()
    app_password = os.environ.get("GMAIL_APP_PASSWORD", "").strip()

    if not gmail_user or not app_password:
        raise RuntimeError(
            "Email credentials missing. "
            "Set GMAIL_USER and GMAIL_APP_PASSWORD environment variables."
        )

    subject = f"[Lead Finder] {len(leads)} new UK lead(s) — {run_timestamp}"
    html_body = build_email_html(leads, run_timestamp)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = EMAIL_RECIPIENT
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    log.info(f"Connecting to smtp.gmail.com:587 as {gmail_user}…")
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(gmail_user, app_password)
        server.sendmail(gmail_user, EMAIL_RECIPIENT, msg.as_string())

    log.info(f"Email sent to {EMAIL_RECIPIENT} — {len(leads)} lead(s)")


# ─────────────────────────────────────────────────────────────
# CLI ENTRY POINT
# ─────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Scrape Google Maps for UK businesses without websites.",
    )
    p.add_argument(
        "--keywords", type=str, default=",".join(DEFAULT_KEYWORDS),
        help="Comma-separated business types",
    )
    p.add_argument(
        "--cities", type=str, default="|".join(DEFAULT_LOCATIONS),
        help="Pipe-separated UK locations (e.g. 'London, UK|Manchester, UK')",
    )
    p.add_argument(
        "--min-reviews", type=int, default=DEFAULT_MIN_REVIEWS,
        help=f"Minimum review count (default: {DEFAULT_MIN_REVIEWS})",
    )
    p.add_argument(
        "--min-rating", type=float, default=DEFAULT_MIN_RATING,
        help=f"Minimum star rating (default: {DEFAULT_MIN_RATING})",
    )
    p.add_argument(
        "--max-results", type=int, default=DEFAULT_MAX_RESULTS_PER_SEARCH,
        help=f"Max results per keyword+city combo (default: {DEFAULT_MAX_RESULTS_PER_SEARCH})",
    )
    p.add_argument(
        "--visible", action="store_true",
        help="Run browser visibly for debugging",
    )
    p.add_argument(
        "--send-email", action="store_true",
        help=(
            f"Email new leads to {EMAIL_RECIPIENT} via Gmail SMTP. "
            "Requires GMAIL_USER and GMAIL_APP_PASSWORD env vars."
        ),
    )
    return p


def main():
    args = build_parser().parse_args()

    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    locations = [l.strip() for l in args.cities.split("|") if l.strip()]
    min_reviews = args.min_reviews
    min_rating = args.min_rating
    max_results = args.max_results
    headless = not args.visible
    do_email = args.send_email

    run_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    total_searches = len(keywords) * len(locations)

    log.info("=" * 60)
    log.info("Google Maps Lead Scraper")
    log.info("=" * 60)
    log.info(f"Keywords  ({len(keywords)}):  {keywords}")
    log.info(f"Locations ({len(locations)}): {locations}")
    log.info(f"Min reviews: {min_reviews}  |  Min rating: {min_rating}")
    log.info(f"Max results: {max_results} per search  |  Total searches: {total_searches}")
    log.info(f"Send email:  {do_email}")
    log.info("=" * 60)

    # ── 1. SCRAPE ─────────────────────────────────────────────
    all_businesses: list[Business] = []

    with sync_playwright() as pw:
        scraper = GoogleMapsScraper(pw, headless=headless)
        try:
            for location in locations:
                for keyword in keywords:
                    log.info(f"\n{'─'*50}")
                    log.info(f"Scraping: \"{keyword}\" in \"{location}\"")
                    log.info(f"{'─'*50}")
                    results = scraper.extract_businesses(keyword, location, max_results)
                    all_businesses.extend(results)
                    pause = random.uniform(5, 12)
                    log.info(f"Pausing {pause:.1f}s before next search…")
                    time.sleep(pause)
        except KeyboardInterrupt:
            log.info("\nInterrupted — saving what we have so far…")
        finally:
            scraper.close()

    log.info(f"\nTotal raw results: {len(all_businesses)}")

    # ── 2. DEDUPLICATE ────────────────────────────────────────
    unique = deduplicate(all_businesses)
    log.info(f"After deduplication: {len(unique)}")

    # ── 3. FILTER (no website, reviews, rating) ───────────────
    leads = filter_leads(unique, min_reviews=min_reviews, min_rating=min_rating)
    log.info(f"After filtering (no website, >= {min_reviews} reviews): {len(leads)}")
    leads = sort_by_opportunity(leads)

    # ── 4. FIND NEW LEADS ─────────────────────────────────────
    seen = load_seen_leads()
    new_leads = filter_new_leads(leads, seen)
    log.info(f"New leads (not previously seen): {len(new_leads)}")

    # ── 5. SAVE CSVs ──────────────────────────────────────────
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp_fs = datetime.now().strftime("%Y%m%d_%H%M%S")

    csv_path = OUTPUT_DIR / f"leads_{timestamp_fs}.csv"
    save_csv(leads, csv_path)

    all_path = OUTPUT_DIR / f"all_results_{timestamp_fs}.csv"
    save_csv(sort_by_opportunity(unique), all_path)

    if new_leads:
        new_csv = OUTPUT_DIR / f"new_leads_{timestamp_fs}.csv"
        save_csv(new_leads, new_csv)
        log.info(f"New leads CSV: {new_csv}")

    # ── 6. EMAIL ──────────────────────────────────────────────
    email_sent = False
    if do_email:
        if not new_leads:
            log.info("No new leads this run — email skipped.")
        else:
            try:
                send_email(new_leads, run_timestamp)
                email_sent = True
            except RuntimeError as exc:
                log.error(f"Email not sent — credential error: {exc}")
            except Exception as exc:
                log.error(f"Email send failed: {exc}")

    # ── 7. PERSIST SEEN LEADS ─────────────────────────────────
    # In email mode: only mark as seen after a successful send so that
    # failed sends retry on the next cron run.
    # In non-email mode: always mark seen to keep daily runs fresh.
    if do_email:
        if email_sent:
            mark_leads_seen(new_leads, seen)
            save_seen_leads(seen)
        else:
            log.warning(
                "Email was requested but not sent — "
                "seen_leads.json NOT updated; leads will retry next run."
            )
    else:
        mark_leads_seen(leads, seen)
        save_seen_leads(seen)

    # ── 8. SUMMARY ────────────────────────────────────────────
    log.info("\n" + "=" * 60)
    log.info("SUMMARY")
    log.info("=" * 60)
    log.info(f"Total scraped:      {len(all_businesses)}")
    log.info(f"Unique businesses:  {len(unique)}")
    log.info(f"Qualified leads:    {len(leads)}")
    log.info(f"New leads:          {len(new_leads)}")
    log.info(f"Email sent:         {email_sent}")
    log.info(f"Leads file:         {csv_path}")
    log.info(f"All results file:   {all_path}")

    if new_leads:
        log.info(f"\nTop 10 NEW leads by review count:")
        log.info(f"{'Name':<40} {'Reviews':>8} {'Rating':>6} {'City'}")
        log.info(f"{'─'*40} {'─'*8} {'─'*6} {'─'*20}")
        for biz in new_leads[:10]:
            log.info(
                f"{biz.name[:39]:<40} {biz.review_count:>8} "
                f"{biz.rating:>6.1f} {biz.search_location}"
            )

    log.info("\nDone.")


if __name__ == "__main__":
    main()
