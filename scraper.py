#!/usr/bin/env python3
"""
Google Maps Lead Scraper — finds UK businesses WITHOUT websites.
Ideal for generating web development sales leads.

Usage:
    python scraper.py
    python scraper.py --keywords "barber,cafe" --cities "London,Manchester" --min-reviews 30
"""

import argparse
import csv
import hashlib
import logging
import random
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

from playwright.sync_api import sync_playwright, Page, Playwright, Browser, TimeoutError as PwTimeout

# ─────────────────────────────────────────────────────────────
# CONFIGURATION — edit these defaults or override via CLI args
# ─────────────────────────────────────────────────────────────
DEFAULT_KEYWORDS = ["barber", "takeaway", "nail salon"]
DEFAULT_LOCATIONS = [
    "London, UK",
    "Manchester, UK",
    "Birmingham, UK",
]
DEFAULT_MIN_REVIEWS = 50
DEFAULT_MIN_RATING = 0.0            # set to 4.0 to only keep highly-rated
DEFAULT_MAX_RESULTS_PER_SEARCH = 100 # Google Maps caps ~120 visible results
OUTPUT_DIR = Path("output")
HEADLESS = True                      # set False to watch the browser

# Anti-detection tuning
MIN_DELAY = 1.0   # seconds — minimum pause between actions
MAX_DELAY = 3.0   # seconds — maximum pause between actions
SCROLL_PAUSE = 1.5 # seconds — wait after each scroll for results to load
MAX_SCROLL_ATTEMPTS = 60  # give up scrolling after this many attempts with no new results

# Logging
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
    third_party_only: str = ""  # e.g. "Uber Eats", "Just Eat"
    search_keyword: str = ""
    search_location: str = ""

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
        # Treat food delivery aggregator links as "no real website"
        aggregators = [
            "ubereats", "just-eat", "justeat", "deliveroo",
            "foodhub", "hungryhouse", "menulog",
        ]
        url_lower = self.website.lower()
        return not any(agg in url_lower for agg in aggregators)


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
def human_delay(lo: float = MIN_DELAY, hi: float = MAX_DELAY):
    """Sleep for a random human-like interval."""
    time.sleep(random.uniform(lo, hi))


def parse_review_count(text: str) -> int:
    """Extract numeric review count from strings like '(1,234)' or '1.2K'."""
    if not text:
        return 0
    text = text.strip().strip("()")
    text = text.replace(",", "").replace(" ", "")
    # Handle "1.2K" style
    m = re.match(r"([\d.]+)[kK]", text)
    if m:
        return int(float(m.group(1)) * 1000)
    m = re.search(r"(\d+)", text)
    return int(m.group(1)) if m else 0


def parse_rating(text: str) -> float:
    """Extract numeric rating from strings like '4.5' or '4,5'."""
    if not text:
        return 0.0
    text = text.replace(",", ".")
    m = re.search(r"(\d+\.?\d*)", text)
    return float(m.group(1)) if m else 0.0


def detect_third_party(page: Page) -> str:
    """Check if the business detail panel mentions food aggregators only."""
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
    """Try to find an Instagram link in the business panel."""
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

    def __init__(
        self,
        pw: Playwright,
        headless: bool = HEADLESS,
    ):
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
        # Dismiss cookie banners automatically
        self.page.add_init_script("""
            // Auto-accept Google consent if it appears
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
        """Click through the Google consent dialog if present."""
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
        """If Google redirected to consent.google.com, handle it."""
        if "consent.google" in self.page.url:
            log.info("Google consent page detected — accepting…")
            self._accept_cookies()
            human_delay(2, 4)

    def navigate_to_maps(self):
        """Load Google Maps and handle any consent screen."""
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
        human_delay(3, 5)  # wait for results to render

    # ── scrolling results panel ─────────────────────────────
    def _get_results_panel(self):
        """Return the scrollable results container."""
        # Google Maps uses a role="feed" container for search results
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
        """Scroll the results panel to load more listings.
        Returns the number of listing elements found."""
        panel = self._get_results_panel()
        if not panel:
            log.warning("Could not find results panel — may be a single-result page")
            return 0

        prev_count = 0
        stale_rounds = 0

        for attempt in range(MAX_SCROLL_ATTEMPTS):
            # Count current result items
            items = self.page.locator('div[role="feed"] > div > div[jsaction]').all()
            count = len(items)

            if count >= max_results:
                log.info(f"Reached target of {max_results} visible results ({count} loaded)")
                break

            # Check if Google says "You've reached the end of the list"
            try:
                end_marker = self.page.locator('span.HlvSq').first
                if end_marker.is_visible(timeout=500):
                    log.info(f"End of results reached ({count} loaded)")
                    break
            except Exception:
                pass

            # Scroll down inside the panel
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
        """Extract business details from the currently-open detail panel."""
        data = {}

        # Name
        try:
            data["name"] = self.page.locator('h1.DUwDvf').first.inner_text(timeout=3000)
        except Exception:
            data["name"] = ""

        # Category
        try:
            data["category"] = self.page.locator(
                'button[jsaction="pane.rating.category"]'
            ).first.inner_text(timeout=2000)
        except Exception:
            data["category"] = ""

        # Rating
        try:
            rating_el = self.page.locator('div.F7nice span[aria-hidden="true"]').first
            data["rating"] = parse_rating(rating_el.inner_text(timeout=2000))
        except Exception:
            data["rating"] = 0.0

        # Review count
        try:
            review_el = self.page.locator('div.F7nice span[aria-label*="review"]').first
            label = review_el.get_attribute("aria-label") or ""
            data["review_count"] = parse_review_count(label)
        except Exception:
            data["review_count"] = 0

        # Address — look for the address data attribute
        try:
            addr_btn = self.page.locator(
                'button[data-item-id="address"]'
            ).first
            data["address"] = addr_btn.get_attribute("aria-label") or ""
            # Clean prefix like "Address: "
            data["address"] = re.sub(r"^Address:\s*", "", data["address"])
        except Exception:
            data["address"] = ""

        # Phone
        try:
            phone_btn = self.page.locator(
                'button[data-item-id*="phone"]'
            ).first
            data["phone"] = phone_btn.get_attribute("aria-label") or ""
            data["phone"] = re.sub(r"^Phone:\s*", "", data["phone"])
        except Exception:
            data["phone"] = ""

        # Website
        try:
            website_link = self.page.locator(
                'a[data-item-id="authority"]'
            ).first
            data["website"] = website_link.get_attribute("href") or ""
        except Exception:
            data["website"] = ""

        # Instagram
        data["instagram"] = extract_instagram(self.page)

        # Third-party ordering platforms
        data["third_party_only"] = detect_third_party(self.page)

        return data

    # ── main extraction loop ────────────────────────────────
    def extract_businesses(
        self,
        keyword: str,
        location: str,
        max_results: int,
    ) -> list[Business]:
        """Run a full search → scroll → extract cycle for one keyword + location."""
        query = f"{keyword} in {location}"
        self.search(query)

        # Scroll to load results
        loaded = self.scroll_results(max_results)
        if loaded == 0:
            log.warning(f"No results found for '{query}'")
            return []

        # Collect all result links BEFORE clicking any
        # (clicking changes the DOM, so snapshot href list first)
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

            # Random longer pause every 15–25 listings to reduce detection risk
            if random.random() < 0.05:
                pause = random.uniform(5, 10)
                log.info(f"  Anti-detection pause ({pause:.1f}s)…")
                time.sleep(pause)

        log.info(f"Extracted {len(businesses)} total businesses for '{query}'")
        return businesses

    # ── cleanup ─────────────────────────────────────────────
    def close(self):
        """Shut down browser."""
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
    """Keep only businesses that have NO website and meet review/rating thresholds."""
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
    """Remove duplicates based on name + address fingerprint."""
    seen: set[str] = set()
    unique: list[Business] = []
    for biz in businesses:
        fp = biz.fingerprint
        if fp not in seen:
            seen.add(fp)
            unique.append(biz)
    return unique


def sort_by_opportunity(businesses: list[Business]) -> list[Business]:
    """Sort leads by review count descending — highest demand first."""
    return sorted(businesses, key=lambda b: b.review_count, reverse=True)


# ─────────────────────────────────────────────────────────────
# CSV EXPORT
# ─────────────────────────────────────────────────────────────
def save_csv(businesses: list[Business], filepath: Path):
    """Write leads to a CSV file."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "name", "address", "phone", "rating", "review_count",
        "website", "category", "instagram", "third_party_only",
        "search_keyword", "search_location",
    ]
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for biz in businesses:
            row = asdict(biz)
            writer.writerow({k: row[k] for k in fieldnames})

    log.info(f"Saved {len(businesses)} leads → {filepath}")


# ─────────────────────────────────────────────────────────────
# CLI ENTRY POINT
# ─────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Scrape Google Maps for UK businesses without websites.",
    )
    p.add_argument(
        "--keywords", type=str, default=",".join(DEFAULT_KEYWORDS),
        help="Comma-separated business types (default: barber,takeaway,nail salon)",
    )
    p.add_argument(
        "--cities", type=str, default="|".join(DEFAULT_LOCATIONS),
        help='Pipe-separated locations (default: "London, UK|Manchester, UK|Birmingham, UK")',
    )
    p.add_argument(
        "--min-reviews", type=int, default=DEFAULT_MIN_REVIEWS,
        help=f"Minimum review count to include (default: {DEFAULT_MIN_REVIEWS})",
    )
    p.add_argument(
        "--min-rating", type=float, default=DEFAULT_MIN_RATING,
        help=f"Minimum star rating to include (default: {DEFAULT_MIN_RATING})",
    )
    p.add_argument(
        "--max-results", type=int, default=DEFAULT_MAX_RESULTS_PER_SEARCH,
        help=f"Max results per keyword+city combo (default: {DEFAULT_MAX_RESULTS_PER_SEARCH})",
    )
    p.add_argument(
        "--visible", action="store_true",
        help="Run browser visibly (non-headless) for debugging",
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

    log.info("=" * 60)
    log.info("Google Maps Lead Scraper")
    log.info("=" * 60)
    log.info(f"Keywords:    {keywords}")
    log.info(f"Locations:   {locations}")
    log.info(f"Min reviews: {min_reviews}")
    log.info(f"Min rating:  {min_rating}")
    log.info(f"Max results: {max_results} per search")
    log.info(f"Headless:    {headless}")
    log.info("=" * 60)

    all_businesses: list[Business] = []

    with sync_playwright() as pw:
        scraper = GoogleMapsScraper(pw, headless=headless)

        try:
            for location in locations:
                for keyword in keywords:
                    log.info(f"\n{'─'*50}")
                    log.info(f"▶ Scraping: \"{keyword}\" in \"{location}\"")
                    log.info(f"{'─'*50}")

                    results = scraper.extract_businesses(keyword, location, max_results)
                    all_businesses.extend(results)

                    # Pause between searches to reduce detection risk
                    pause = random.uniform(5, 12)
                    log.info(f"Pausing {pause:.1f}s before next search…")
                    time.sleep(pause)

        except KeyboardInterrupt:
            log.info("\nInterrupted by user — saving what we have so far…")
        finally:
            scraper.close()

    # ── post-processing ─────────────────────────────────────
    log.info(f"\nTotal raw results: {len(all_businesses)}")

    # Deduplicate
    unique = deduplicate(all_businesses)
    log.info(f"After deduplication: {len(unique)}")

    # Filter to no-website leads
    leads = filter_leads(unique, min_reviews=min_reviews, min_rating=min_rating)
    log.info(f"After filtering (no website, ≥{min_reviews} reviews, ≥{min_rating}★): {len(leads)}")

    # Sort by opportunity
    leads = sort_by_opportunity(leads)

    # Save
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = OUTPUT_DIR / f"leads_{timestamp}.csv"
    save_csv(leads, csv_path)

    # Also save ALL results (including those with websites) for reference
    all_path = OUTPUT_DIR / f"all_results_{timestamp}.csv"
    save_csv(sort_by_opportunity(unique), all_path)

    # Summary
    log.info("\n" + "=" * 60)
    log.info("SUMMARY")
    log.info("=" * 60)
    log.info(f"Total scraped:      {len(all_businesses)}")
    log.info(f"Unique businesses:  {len(unique)}")
    log.info(f"Qualified leads:    {len(leads)}")
    log.info(f"Leads file:         {csv_path}")
    log.info(f"All results file:   {all_path}")

    if leads:
        log.info(f"\nTop 10 leads by review count:")
        log.info(f"{'Name':<40} {'Reviews':>8} {'Rating':>6} {'City'}")
        log.info(f"{'─'*40} {'─'*8} {'─'*6} {'─'*20}")
        for biz in leads[:10]:
            log.info(
                f"{biz.name[:39]:<40} {biz.review_count:>8} {biz.rating:>6.1f} "
                f"{biz.search_location}"
            )

    log.info("\nDone ✓")


if __name__ == "__main__":
    main()
