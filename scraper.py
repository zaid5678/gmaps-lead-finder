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
import math
import os
import random
import re
import smtplib
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
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
    "roofer",
    "roofing company",
    "roofing contractor",
]

DEFAULT_LOCATIONS = [
    "London, UK",
    "Manchester, UK",
]

# Use with --all-categories flag
ALL_BUSINESS_CATEGORIES = [
    "barber",
    "hairdresser",
    "nail salon",
    "beauty salon",
    "restaurant",
    "cafe",
    "takeaway",
    "pub",
    "plumber",
    "electrician",
    "roofer",
    "builder",
    "painter decorator",
    "locksmith",
    "cleaner",
    "handyman",
    "car mechanic",
    "MOT centre",
    "car wash",
    "dentist",
    "physiotherapist",
    "personal trainer",
    "gym",
    "tattoo studio",
    "dog groomer",
]

# Use with --all-cities flag
TOP_50_UK_CITIES = [
    "London, UK",
    "Manchester, UK",
    "Birmingham, UK",
    "Leeds, UK",
    "Glasgow, UK",
    "Edinburgh, UK",
    "Bristol, UK",
    "Liverpool, UK",
    "Sheffield, UK",
    "Newcastle upon Tyne, UK",
    "Nottingham, UK",
    "Leicester, UK",
    "Cardiff, UK",
    "Aberdeen, UK",
    "Southampton, UK",
    "Portsmouth, UK",
    "Oxford, UK",
    "Cambridge, UK",
    "Reading, UK",
    "Brighton, UK",
    "Coventry, UK",
    "Stoke-on-Trent, UK",
    "Wolverhampton, UK",
    "Derby, UK",
    "Sunderland, UK",
    "York, UK",
    "Middlesbrough, UK",
    "Bradford, UK",
    "Huddersfield, UK",
    "Milton Keynes, UK",
    "Norwich, UK",
    "Swansea, UK",
    "Northampton, UK",
    "Luton, UK",
    "Peterborough, UK",
    "Warrington, UK",
    "Hull, UK",
    "Plymouth, UK",
    "Exeter, UK",
    "Blackpool, UK",
    "Bolton, UK",
    "Oldham, UK",
    "Wigan, UK",
    "Stockport, UK",
    "Salford, UK",
    "Ipswich, UK",
    "Crawley, UK",
    "Guildford, UK",
    "Chelmsford, UK",
    "Preston, UK",
]

DEFAULT_MIN_REVIEWS = 0
DEFAULT_MIN_RATING = 0.0
DEFAULT_MAX_RESULTS_PER_SEARCH = 100
OUTPUT_DIR = Path("output")
ROOFERS_CSV = OUTPUT_DIR / "roofers_leads.csv"
ROOFERS_FIELDNAMES = [
    "fingerprint", "name", "city", "address", "phone", "email",
    "rating", "review_count", "maps_url", "scraped_at",
    "contacted", "contacted_date",
]
README_PATH = Path("README.md")
HEADLESS = True

# Email / outreach
EMAIL_RECIPIENT = "zfkhan321@gmail.com"
SEEN_LEADS_PATH = OUTPUT_DIR / "seen_leads.json"
OUTREACH_SENT_PATH = OUTPUT_DIR / "outreach_sent.json"

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
    email: str = ""
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

        try:
            email_link = self.page.locator('a[href^="mailto:"]').first
            raw = email_link.get_attribute("href") or ""
            data["email"] = re.sub(r"^mailto:", "", raw).strip()
        except Exception:
            data["email"] = ""

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
                    email=data.get("email", ""),
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
# README EXPORT
# ─────────────────────────────────────────────────────────────
_LEADS_HEADER = "## Leads"
_LEGAL_MARKER = "## Legal Note"


def _table_rows(businesses) -> str:
    """Build markdown table rows from Business objects or CSV dicts."""
    rows = ""
    for b in businesses:
        if isinstance(b, Business):
            name     = b.name
            category = b.category
            location = b.search_location
            phone    = b.phone
            reviews  = str(b.review_count)
            rating   = f"{b.rating:.1f}"
            maps_url = b.maps_url
        else:
            name     = b.get("name", "")
            category = b.get("category", "")
            location = b.get("search_location", "")
            phone    = b.get("phone", "")
            reviews  = b.get("review_count", "")
            rating   = b.get("rating", "")
            maps_url = b.get("maps_url", "")

        name     = name.replace("|", "\\|").replace("\n", " ").strip()
        phone    = phone.replace("|", "\\|").strip()
        category = category.replace("|", "\\|").strip()
        link     = f"[Maps]({maps_url})" if maps_url else ""

        rows += (
            f"| {name} | {category} | {location} | {phone} "
            f"| {reviews} | {rating} | {link} |\n"
        )
    return rows


def _build_section(title: str, date_str: str, businesses) -> str:
    header = (
        f"\n### {title} — {date_str} ({len(businesses)} leads)\n\n"
        "| Business | Category | City | Phone | Reviews | Rating | Maps |\n"
        "|----------|----------|------|-------|---------|--------|------|\n"
    )
    return header + _table_rows(businesses) + "\n"


def _migrate_existing_csvs() -> str:
    """Read all existing leads_*.csv files and return a combined markdown block."""
    csv_files = sorted(OUTPUT_DIR.glob("leads_*.csv"))
    if not csv_files:
        return ""

    block = ""
    for csv_file in csv_files:
        stem = csv_file.stem.replace("leads_", "")
        try:
            dt = datetime.strptime(stem, "%Y%m%d_%H%M%S")
            date_str = dt.strftime("%d %b %Y %H:%M")
        except ValueError:
            date_str = stem

        try:
            with open(csv_file, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
        except Exception as exc:
            log.warning(f"Could not read {csv_file}: {exc}")
            continue

        if rows:
            block += _build_section(f"Previous leads ({csv_file.name})", date_str, rows)
            block += "\n---\n"

    return block


def update_readme(new_leads: list[Business], section_title: str, readme_path: Path = README_PATH):
    """
    Append new_leads as a dated section to README.md just before ## Legal Note.
    On the first call (no ## Leads section yet), migrates existing CSV files first.
    """
    content = readme_path.read_text(encoding="utf-8")
    date_str = datetime.now().strftime("%d %b %Y %H:%M")

    # First-time: create ## Leads section and migrate any existing CSVs
    if _LEADS_HEADER not in content:
        migration = _migrate_existing_csvs()
        leads_block = (
            f"{_LEADS_HEADER}\n\n"
            "All leads are appended here automatically after each run.\n"
            + migration
        )
        insert_at = content.find(_LEGAL_MARKER)
        if insert_at == -1:
            content += f"\n\n{leads_block}"
        else:
            content = content[:insert_at] + leads_block + "\n---\n\n" + content[insert_at:]

    # Append new leads before ## Legal Note
    if new_leads:
        new_section = _build_section(section_title, date_str, new_leads)
        insert_at = content.find(_LEGAL_MARKER)
        if insert_at == -1:
            content += new_section
        else:
            content = content[:insert_at] + new_section + "\n---\n\n" + content[insert_at:]

    readme_path.write_text(content, encoding="utf-8")
    log.info(f"Updated README.md — {len(new_leads)} leads added under '{section_title}'")


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
# OUTREACH TRACKING
# ─────────────────────────────────────────────────────────────
def load_outreach_sent(path: Path = OUTREACH_SENT_PATH) -> dict:
    """Load outreach registry: {fingerprint: ISO-timestamp}."""
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError) as exc:
        log.warning(f"Could not read outreach_sent.json: {exc} — treating as empty")
        return {}


def save_outreach_sent(sent: dict, path: Path = OUTREACH_SENT_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sent, f, indent=2, ensure_ascii=False)
    log.info(f"Saved outreach registry ({len(sent)} total) → {path}")


def filter_not_yet_contacted(leads: list[Business], sent: dict) -> list[Business]:
    return [biz for biz in leads if biz.fingerprint not in sent]


def mark_outreach_sent(leads: list[Business], sent: dict) -> dict:
    now_iso = datetime.now(timezone.utc).isoformat()
    for biz in leads:
        fp = biz.fingerprint
        if fp not in sent:
            sent[fp] = now_iso
    return sent


# ─────────────────────────────────────────────────────────────
# OUTREACH HELPERS
# ─────────────────────────────────────────────────────────────
def normalize_uk_phone(phone: str) -> Optional[str]:
    """Convert a UK phone string to E.164 format (+44...) for Twilio."""
    if not phone:
        return None
    digits = re.sub(r"[^\d+]", "", phone)
    if digits.startswith("+44") and len(digits) >= 12:
        return digits
    if digits.startswith("44") and len(digits) >= 12:
        return "+" + digits
    if digits.startswith("0") and len(digits) >= 10:
        return "+44" + digits[1:]
    return None


def _outreach_email_body(biz: Business) -> str:
    greeting = f"Hi {biz.name}," if biz.name else "Hi,"
    return f"""{greeting}

I hope you're well.

I came across your business on Google and wanted to reach out with a quick idea that could help bring in more enquiries.

At the moment, many customers searching for services like yours tend to compare a few options online before making a decision. If there isn't a clear, professional website, they often move on to competitors who make it easier to view services, pricing, and contact details in one place.

A simple, well-structured website can help you:
- show what you offer more clearly
- build trust with new customers instantly
- and turn more online searches into actual enquiries

I build clean, straightforward websites designed specifically to generate enquiries for local businesses, so I thought it might be useful to connect.

If you're open to it, I can put together a quick example for your business so you can see how it would look before making any decision.

Thanks,
Zaid"""


def _outreach_sms_body(biz: Business) -> str:
    greeting = f"Hi {biz.name}," if biz.name else "Hi,"
    return (
        f"{greeting} hope you're well.\n\n"
        "I came across your business and wanted to reach out — quick idea that could "
        "help bring in more enquiries.\n\n"
        "At the moment, a lot of people searching online compare a few options before "
        "choosing, and without a simple website they often go with competitors who make "
        "it easier to view services and contact details.\n\n"
        "A clean, simple website can help you show what you do more clearly and turn "
        "more of those searches into actual customers.\n\n"
        "If you're open to it, I can show you a quick example for your business 👍"
    )


# ─────────────────────────────────────────────────────────────
# OUTREACH SENDERS
# ─────────────────────────────────────────────────────────────
def send_email_outreach(leads: list[Business], gmail_user: str, app_password: str) -> list[Business]:
    """Send cold-outreach emails FROM gmail_user TO each lead that has an email address.
    Returns the list of leads successfully emailed."""
    if not gmail_user or not app_password:
        raise RuntimeError("Set GMAIL_USER and GMAIL_APP_PASSWORD to send outreach emails.")

    emailable = [b for b in leads if b.email]
    if not emailable:
        log.info("No leads have email addresses — skipping email outreach.")
        return []

    succeeded: list[Business] = []
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(gmail_user, app_password)

        for biz in emailable:
            try:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = "Quick idea to bring in more local customers"
                msg["From"] = gmail_user
                msg["To"] = biz.email
                msg.attach(MIMEText(_outreach_email_body(biz), "plain", "utf-8"))
                server.sendmail(gmail_user, biz.email, msg.as_string())
                log.info(f"  Outreach email → {biz.name} <{biz.email}>")
                succeeded.append(biz)
            except Exception as exc:
                log.warning(f"  Email failed for {biz.name} ({biz.email}): {exc}")

    log.info(f"Email outreach: {len(succeeded)}/{len(emailable)} sent.")
    return succeeded


def send_sms_outreach(leads: list[Business], account_sid: str, auth_token: str, from_number: str) -> list[Business]:
    """Send SMS outreach via Twilio to each lead with a phone number.
    Returns the list of leads successfully messaged."""
    try:
        from twilio.rest import Client  # type: ignore
    except ImportError:
        raise RuntimeError("twilio package not installed. Run: pip install twilio")

    client = Client(account_sid, auth_token)
    dialable = [(b, normalize_uk_phone(b.phone)) for b in leads]
    dialable = [(b, e164) for b, e164 in dialable if e164]

    if not dialable:
        log.info("No leads have dialable phone numbers — skipping SMS outreach.")
        return []

    succeeded: list[Business] = []
    for biz, e164 in dialable:
        try:
            client.messages.create(
                body=_outreach_sms_body(biz),
                from_=from_number,
                to=e164,
            )
            log.info(f"  SMS → {biz.name} ({e164})")
            succeeded.append(biz)
        except Exception as exc:
            log.warning(f"  SMS failed for {biz.name} ({e164}): {exc}")

    log.info(f"SMS outreach: {len(succeeded)}/{len(dialable)} sent.")
    return succeeded


def send_whatsapp_outreach(leads: list[Business], account_sid: str, auth_token: str, from_whatsapp: str) -> list[Business]:
    """Send WhatsApp outreach via Twilio to each lead with a phone number.
    from_whatsapp should be in the form 'whatsapp:+14155238886' (Twilio sandbox)
    or 'whatsapp:+44XXXXXXXXXX' (approved production number).
    Returns the list of leads successfully messaged."""
    try:
        from twilio.rest import Client  # type: ignore
    except ImportError:
        raise RuntimeError("twilio package not installed. Run: pip install twilio")

    client = Client(account_sid, auth_token)
    dialable = [(b, normalize_uk_phone(b.phone)) for b in leads]
    dialable = [(b, e164) for b, e164 in dialable if e164]

    if not dialable:
        log.info("No leads have dialable phone numbers — skipping WhatsApp outreach.")
        return []

    succeeded: list[Business] = []
    for biz, e164 in dialable:
        try:
            client.messages.create(
                body=_outreach_sms_body(biz),
                from_=from_whatsapp,
                to=f"whatsapp:{e164}",
            )
            log.info(f"  WhatsApp → {biz.name} ({e164})")
            succeeded.append(biz)
        except Exception as exc:
            log.warning(f"  WhatsApp failed for {biz.name} ({e164}): {exc}")

    log.info(f"WhatsApp outreach: {len(succeeded)}/{len(dialable)} sent.")
    return succeeded


# ─────────────────────────────────────────────────────────────
# EMAIL (digest notification to self)
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
# PARALLEL SCRAPING
# ─────────────────────────────────────────────────────────────
def _worker_scrape(task: tuple) -> list[dict]:
    """
    Worker function executed in a subprocess.
    Each worker starts its own Playwright browser to avoid thread-safety issues.
    Returns a list of plain dicts (Business dataclass fields) for safe pickling.
    """
    keyword, location, max_results, headless = task
    # Re-configure logging for this subprocess so output appears in terminal
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [worker] %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )
    with sync_playwright() as pw:
        scraper = GoogleMapsScraper(pw, headless=headless)
        try:
            businesses = scraper.extract_businesses(keyword, location, max_results)
            return [asdict(b) for b in businesses]
        finally:
            scraper.close()


# ─────────────────────────────────────────────────────────────
# CSV EXPORT
# ─────────────────────────────────────────────────────────────
def write_leads_csv(path: Path, businesses: list[Business]):
    """Write a list of Business objects to a CSV file."""
    if not businesses:
        log.info(f"No records to write → {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(asdict(businesses[0]).keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for biz in businesses:
            writer.writerow(asdict(biz))
    log.info(f"Saved {len(businesses)} records → {path}")


# ─────────────────────────────────────────────────────────────
# ROOFERS CSV — persistent, deduped across runs
# ─────────────────────────────────────────────────────────────

def load_roofers_csv(path: Path = ROOFERS_CSV) -> dict:
    """Return {fingerprint: row_dict} from roofers_leads.csv."""
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {r["fingerprint"]: r for r in csv.DictReader(f) if r.get("fingerprint")}


def save_roofers_csv(leads: dict, path: Path = ROOFERS_CSV):
    """Write the full leads dict back to roofers_leads.csv."""
    rows = list(leads.values())
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    extra = sorted(set().union(*[r.keys() for r in rows]) - set(ROOFERS_FIELDNAMES))
    fieldnames = ROOFERS_FIELDNAMES + extra
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})
    log.info(f"Saved {len(rows)} leads → {path}")


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
    p.add_argument(
        "--send-outreach", action="store_true",
        help=(
            "Automatically send cold-outreach to each new lead via email "
            "(if they have an address), SMS, and WhatsApp. "
            "Requires GMAIL_USER, GMAIL_APP_PASSWORD, TWILIO_ACCOUNT_SID, "
            "TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER, and TWILIO_WHATSAPP_FROM env vars."
        ),
    )
    p.add_argument(
        "--workers", type=int, default=1,
        help=(
            "Number of parallel browser instances (default: 1 = sequential). "
            "Each worker runs in a separate process. Recommended: 2-3 max."
        ),
    )
    p.add_argument(
        "--all-cities", action="store_true",
        help=f"Use the built-in list of top 50 UK cities instead of --cities ({len(TOP_50_UK_CITIES)} cities).",
    )
    p.add_argument(
        "--all-categories", action="store_true",
        help=f"Use the built-in list of 25 business categories instead of --keywords ({len(ALL_BUSINESS_CATEGORIES)} categories).",
    )
    return p


def main():
    args = build_parser().parse_args()

    keywords  = ALL_BUSINESS_CATEGORIES if args.all_categories else [k.strip() for k in args.keywords.split(",") if k.strip()]
    locations = TOP_50_UK_CITIES        if args.all_cities      else [l.strip() for l in args.cities.split("|")    if l.strip()]
    headless  = not args.visible
    all_tasks = [(kw, loc, args.max_results, headless) for loc in locations for kw in keywords]

    log.info("=" * 60)
    log.info(f"Roofer Lead Scraper — {len(keywords)} keyword(s) × {len(locations)} city(ies) = {len(all_tasks)} searches")
    log.info(f"Max results per search: {args.max_results}  |  Target: {len(all_tasks) * args.max_results} total")
    log.info("=" * 60)

    # ── 1. SCRAPE ─────────────────────────────────────────────
    all_businesses: list[Business] = []

    with sync_playwright() as pw:
        scraper = GoogleMapsScraper(pw, headless=headless)
        try:
            for i, (keyword, location, max_r, _) in enumerate(all_tasks):
                log.info(f"\n[{i+1}/{len(all_tasks)}] '{keyword}' in '{location}'")
                results = scraper.extract_businesses(keyword, location, max_r)
                all_businesses.extend(results)
                if i < len(all_tasks) - 1:
                    pause = random.uniform(5, 12)
                    log.info(f"Pausing {pause:.1f}s before next search…")
                    time.sleep(pause)
        except KeyboardInterrupt:
            log.info("Interrupted — saving what we have…")
        finally:
            scraper.close()

    # ── 2. FILTER: no website, deduplicate ────────────────────
    unique = deduplicate(all_businesses)
    leads  = [b for b in unique if not b.has_website]
    log.info(f"Scraped: {len(all_businesses)}  |  Unique: {len(unique)}  |  No website: {len(leads)}")

    # ── 3. MERGE INTO roofers_leads.csv ───────────────────────
    existing = load_roofers_csv()
    now_iso  = datetime.now().isoformat()
    added    = 0
    for b in leads:
        fp = b.fingerprint
        if fp not in existing:
            city = b.search_location.replace(", UK", "").strip()
            existing[fp] = {
                "fingerprint":    fp,
                "name":           b.name,
                "city":           city,
                "address":        b.address,
                "phone":          b.phone,
                "email":          b.email,
                "rating":         b.rating,
                "review_count":   b.review_count,
                "maps_url":       b.maps_url,
                "scraped_at":     now_iso,
                "contacted":      "",
                "contacted_date": "",
            }
            added += 1

    save_roofers_csv(existing)

    # ── 4. OUTREACH — skip anyone already contacted ───────────
    outreach_email_count = 0
    if args.send_outreach:
        outreach_sent = load_outreach_sent()
        to_contact = [b for b in leads if b.fingerprint not in outreach_sent]

        if not to_contact:
            log.info("All leads already contacted — outreach skipped.")
        else:
            gmail_user   = os.environ.get("GMAIL_USER", "").strip()
            app_password = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
            if gmail_user and app_password:
                try:
                    emailed = send_email_outreach(to_contact, gmail_user, app_password)
                    outreach_email_count = len(emailed)
                    for b in emailed:
                        if b.fingerprint in existing:
                            existing[b.fingerprint]["contacted"]      = "yes"
                            existing[b.fingerprint]["contacted_date"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                    if emailed:
                        save_roofers_csv(existing)
                except Exception as exc:
                    log.error(f"Email outreach failed: {exc}")
            else:
                log.warning("GMAIL_USER / GMAIL_APP_PASSWORD not set — skipping outreach.")

            mark_outreach_sent(to_contact, outreach_sent)
            save_outreach_sent(outreach_sent)

    # ── 5. SUMMARY ────────────────────────────────────────────
    total           = len(existing)
    contacted_count = sum(1 for r in existing.values() if r.get("contacted") == "yes")

    log.info("\n" + "=" * 60)
    log.info("SUMMARY")
    log.info("=" * 60)
    log.info(f"  New leads added:    {added}")
    log.info(f"  Total in CSV:       {total}")
    log.info(f"  Already contacted:  {contacted_count}")
    log.info(f"  Not yet contacted:  {total - contacted_count}")
    log.info(f"  Outreach sent:      {outreach_email_count}")
    log.info(f"  CSV:                {ROOFERS_CSV}")
    log.info("=" * 60)

    uncontacted = sorted(
        [b for b in leads if b.fingerprint in existing and not existing[b.fingerprint].get("contacted")],
        key=lambda b: b.review_count, reverse=True,
    )
    if uncontacted:
        log.info(f"\nTop uncontacted leads:")
        log.info(f"  {'Name':<40} {'Phone':<16} {'City'}")
        log.info(f"  {'─'*40} {'─'*16} {'─'*20}")
        for b in uncontacted[:10]:
            city = b.search_location.replace(", UK", "")
            log.info(f"  {b.name[:39]:<40} {b.phone:<16} {city}")

    log.info("\nDone.")


if __name__ == "__main__":
    main()
