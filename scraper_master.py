#!/usr/bin/env python3
"""
Multi-source UK lead scraper.

Finds businesses WITHOUT websites across seven directories simultaneously:
  Google Maps · Yell.com · Yelp UK · Thomson Local
  TrustATrader · Checkatrade · Bark.com

All results are merged into output/all_leads.csv.

Usage:
    python scraper_master.py                          # default categories + cities
    python scraper_master.py --all-categories --all-cities
    python scraper_master.py --sources yell,checkatrade --workers 6
    python scraper_master.py --categories "plumber,barber" --cities "London,Manchester"
    python scraper_master.py --dry-run               # show tasks without scraping
"""

import argparse
import csv
import hashlib
import json
import logging
import os
import random
import re
import sys
import time
import urllib.parse
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import requests
    from bs4 import BeautifulSoup
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False
    BeautifulSoup = None  # type: ignore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("scraper_master")

# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────

OUTPUT_DIR = Path("output")
ALL_LEADS_CSV = OUTPUT_DIR / "all_leads.csv"

AGGREGATOR_DOMAINS = {
    "ubereats", "just-eat", "justeat", "deliveroo", "foodhub",
    "hungryhouse", "menulog", "thuisbezorgd", "openTable",
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

DEFAULT_CATEGORIES = [
    "barber", "plumber", "electrician", "roofer", "restaurant",
    "cafe", "beauty salon", "car mechanic", "dentist", "cleaner",
    "hairdresser", "nail salon", "locksmith", "painter decorator", "gardener",
]

ALL_CATEGORIES = [
    "restaurant", "cafe", "pub", "bar", "takeaway", "barber",
    "hair salon", "beauty salon", "nail salon", "spa",
    "plumber", "electrician", "heating engineer", "roofer", "builder",
    "painter decorator", "locksmith", "mechanic", "car wash",
    "dentist", "physiotherapist", "chiropractor", "gym", "personal trainer",
    "yoga studio", "accountant", "solicitor", "estate agent",
    "driving instructor", "tutor", "cleaner", "gardener",
    "landscaper", "pet groomer", "vet",
]

DEFAULT_CITIES = [
    "London", "Manchester", "Birmingham", "Leeds", "Liverpool",
    "Bristol", "Sheffield", "Nottingham", "Leicester", "Newcastle",
]

TOP_50_UK_CITIES = [
    "London", "Manchester", "Birmingham", "Leeds", "Glasgow",
    "Edinburgh", "Bristol", "Liverpool", "Sheffield", "Newcastle",
    "Nottingham", "Cardiff", "Leicester", "Bradford", "Coventry",
    "Belfast", "Hull", "Stoke", "Wolverhampton", "Derby",
    "Southampton", "Portsmouth", "Brighton", "Plymouth", "Reading",
    "Bolton", "Luton", "Preston", "Aberdeen", "Milton Keynes",
    "Sunderland", "Norwich", "Dundee", "Ipswich", "York",
    "Gloucester", "Oxford", "Cambridge", "Peterborough", "Swansea",
    "Blackpool", "Bournemouth", "Middlesbrough", "Swindon", "Huddersfield",
    "Warrington", "Southend", "Telford", "Exeter", "Guildford",
]

ALL_HTTP_SOURCES = ["thomson_local", "trustatrader", "checkatrade"]
ALL_PW_SOURCES   = ["yelp", "bark", "google_maps"]
ALL_SOURCES      = ALL_HTTP_SOURCES + ALL_PW_SOURCES
DEFAULT_SOURCES  = ["google_maps"]


# ─────────────────────────────────────────────────────────────
# DATA MODEL
# ─────────────────────────────────────────────────────────────

@dataclass
class BusinessLead:
    # Core business info
    fingerprint:       str = ""
    name:              str = ""
    address:           str = ""
    city:              str = ""
    phone:             str = ""
    email:             str = ""
    industry:          str = ""
    source:            str = ""
    website:           str = ""
    maps_url:          str = ""
    scraped_at:        str = ""
    # Email campaign tracking (written by auto_emailer.py)
    contacted:         str = ""
    contacted_date:    str = ""
    follow_up_1_sent:  str = ""
    follow_up_1_date:  str = ""
    follow_up_2_sent:  str = ""
    follow_up_2_date:  str = ""
    replied:           str = ""
    unsubscribed:      str = ""
    send_status:       str = ""
    notes:             str = ""

    def __post_init__(self):
        if not self.fingerprint:
            raw = f"{self.name.lower().strip()}|{self.address.lower().strip()}"
            self.fingerprint = hashlib.md5(raw.encode()).hexdigest()

    def has_real_website(self) -> bool:
        if not self.website:
            return False
        return not any(agg in self.website.lower() for agg in AGGREGATOR_DOMAINS)


LEAD_FIELDS = list(BusinessLead.__dataclass_fields__.keys())


# ─────────────────────────────────────────────────────────────
# CSV HELPERS
# ─────────────────────────────────────────────────────────────

def load_existing_leads(path: Path = ALL_LEADS_CSV) -> dict:
    """Return {fingerprint: row_dict} from existing all_leads.csv."""
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {r["fingerprint"]: r for r in csv.DictReader(f) if r.get("fingerprint")}


def save_all_leads(leads: dict, path: Path = ALL_LEADS_CSV):
    """Write the full leads dict back to all_leads.csv."""
    rows = list(leads.values())
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    # Ensure consistent column order: known fields first, then any extras
    extra = sorted(set().union(*[r.keys() for r in rows]) - set(LEAD_FIELDS))
    fieldnames = LEAD_FIELDS + extra
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})
    log.info(f"Saved {len(rows)} total leads → {path}")


def merge_leads(new_leads: list, existing: dict) -> tuple:
    """Merge new BusinessLead objects into existing dict. Returns (added_count, updated_dict)."""
    added = 0
    for lead in new_leads:
        if isinstance(lead, dict):
            bl = BusinessLead(**{k: lead.get(k, "") for k in LEAD_FIELDS if k in lead})
        else:
            bl = lead
        fp = bl.fingerprint
        if fp and fp not in existing and bl.name.strip():
            existing[fp] = asdict(bl)
            added += 1
    return added, existing


# ─────────────────────────────────────────────────────────────
# BASE HTTP SCRAPER
# ─────────────────────────────────────────────────────────────

class BaseScraper(ABC):
    name = "base"
    base_delay = 2.5

    def __init__(self):
        if not REQUESTS_OK:
            raise RuntimeError("requests + beautifulsoup4 + lxml required. Run: pip install -r requirements.txt")
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-GB,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        })
        self._last_req = 0.0

    def _throttle(self):
        gap = time.time() - self._last_req
        wait = random.uniform(self.base_delay, self.base_delay * 1.8)
        if gap < wait:
            time.sleep(wait - gap)
        self._last_req = time.time()

    def _get(self, url: str, params: Optional[dict] = None, retries: int = 3) -> Optional[BeautifulSoup]:
        self._throttle()
        self.session.headers["User-Agent"] = random.choice(USER_AGENTS)
        for attempt in range(retries):
            try:
                r = self.session.get(url, params=params, timeout=15, allow_redirects=True)
                if r.status_code == 429:
                    wait = 45 * (attempt + 1)
                    log.warning(f"[{self.name}] Rate limited — sleeping {wait}s")
                    time.sleep(wait)
                    continue
                if r.status_code in (403, 404):
                    log.warning(f"[{self.name}] HTTP {r.status_code} (blocked/not found): {url}")
                    return None
                if r.status_code != 200:
                    log.warning(f"[{self.name}] HTTP {r.status_code}: {url}")
                    time.sleep(2 ** attempt)
                    continue
                return BeautifulSoup(r.text, "lxml")
            except Exception as exc:
                log.debug(f"[{self.name}] Request error (attempt {attempt+1}): {exc}")
                time.sleep(2 ** attempt)
        return None

    @abstractmethod
    def search(self, category: str, city: str, max_results: int = 40) -> list:
        pass

    def _make_lead(self, name, address, city, phone, website, category, maps_url="") -> Optional[BusinessLead]:
        if not name.strip():
            return None
        return BusinessLead(
            name=name.strip(),
            address=address.strip(),
            city=city,
            phone=phone.strip(),
            industry=category,
            source=self.name,
            website=website.strip(),
            maps_url=maps_url,
            scraped_at=datetime.now().isoformat(),
        )


# ─────────────────────────────────────────────────────────────
# YELL.COM
# ─────────────────────────────────────────────────────────────

class YellScraper(BaseScraper):
    name = "yell"
    base_delay = 3.0
    URL = "https://www.yell.com/ucs/UcsSearchAction.do"

    def search(self, category: str, city: str, max_results: int = 40) -> list:
        leads, page = [], 1
        while len(leads) < max_results:
            soup = self._get(self.URL, params={"keywords": category, "location": f"{city}, UK", "pageNum": page})
            if soup is None:
                log.warning(f"[yell] No response for '{category}'/'{city}' page {page} — site may be blocking")
                break
            cards = (
                soup.select("div.businessCapsule--mainContents") or
                soup.select("[class*='businessCapsule']") or
                soup.select("article.row--cards")
            )
            if not cards:
                log.info(f"[yell] No cards found on page {page} for '{category}'/'{city}' — selectors may be stale")
                break
            raw = [self._parse(c, category, city) for c in cards]
            parsed = [l for l in raw if l]
            no_site = [l for l in parsed if not l.has_real_website()]
            log.info(f"[yell] p{page} '{category}'/'{city}': {len(cards)} cards, {len(parsed)} parsed, {len(no_site)} no-website")
            leads.extend(no_site)
            if not soup.select_one("a[rel='next'], a.pagination__item--next, li.next a"):
                break
            page += 1
        log.info(f"[yell] '{category}' / '{city}' → {len(leads)} leads total")
        return leads[:max_results]

    def _parse(self, card, category, city) -> Optional[BusinessLead]:
        try:
            name_el = (card.select_one("h2.businessCapsule--name") or
                       card.select_one("[class*='businessName']") or
                       card.select_one("h2, h3"))
            if not name_el:
                return None
            name = name_el.get_text(strip=True)

            # Presence of "Visit website" link = has website
            ws_el = (card.select_one("a[class*='visitWebsite']") or
                     card.select_one("a[data-taglabel='Visit Website']"))
            website = ws_el.get("href", "") if ws_el else ""

            phone_el = (card.select_one("span.businessCapsule--telephone") or
                        card.select_one("[itemprop='telephone']"))
            phone = phone_el.get_text(strip=True) if phone_el else ""

            addr_el = (card.select_one("[itemprop='address']") or
                       card.select_one("[class*='address']"))
            address = addr_el.get_text(", ", strip=True) if addr_el else city

            return self._make_lead(name, address, city, phone, website, category)
        except Exception as exc:
            log.debug(f"[yell] parse error: {exc}")
            return None


# ─────────────────────────────────────────────────────────────
# THOMSON LOCAL
# ─────────────────────────────────────────────────────────────

class ThomsonLocalScraper(BaseScraper):
    name = "thomson_local"
    base_delay = 2.5
    URL = "https://www.thomsonlocal.com/search"

    def search(self, category: str, city: str, max_results: int = 40) -> list:
        leads, offset = [], 0
        while len(leads) < max_results:
            soup = self._get(self.URL, params={"what": category, "where": f"{city}, UK", "from": offset})
            if soup is None:
                break
            cards = (soup.select("div.result-container") or
                     soup.select("[class*='result']") or
                     soup.select("div.business-listing"))
            if not cards:
                log.info(f"[thomson] No cards found (offset={offset}) for '{category}'/'{city}' — selectors may be stale")
                break
            raw = [self._parse(c, category, city) for c in cards]
            parsed = [l for l in raw if l]
            no_site = [l for l in parsed if not l.has_real_website()]
            log.info(f"[thomson] '{category}'/'{city}': {len(cards)} cards, {len(parsed)} parsed, {len(no_site)} no-website")
            leads.extend(no_site)
            if len(cards) < 10:
                break
            offset += len(cards)
        log.info(f"[thomson] '{category}' / '{city}' → {len(leads)} leads total")
        return leads[:max_results]

    def _parse(self, card, category, city) -> Optional[BusinessLead]:
        try:
            name_el = (card.select_one("h2.business-name") or
                       card.select_one("[class*='businessName']") or
                       card.select_one("h2, h3"))
            if not name_el:
                return None

            ws_el = card.select_one("a[class*='website']")
            website = ws_el.get("href", "") if ws_el else ""

            phone_el = card.select_one("[class*='phone'], [class*='telephone'], [itemprop='telephone']")
            phone = phone_el.get_text(strip=True) if phone_el else ""

            addr_el = card.select_one("[class*='address'], [itemprop='address']")
            address = addr_el.get_text(", ", strip=True) if addr_el else city

            return self._make_lead(name_el.get_text(strip=True), address, city, phone, website, category)
        except Exception as exc:
            log.debug(f"[thomson] parse error: {exc}")
            return None


# ─────────────────────────────────────────────────────────────
# TRUSTATRADER
# ─────────────────────────────────────────────────────────────

class TrustATraderScraper(BaseScraper):
    name = "trustatrader"
    base_delay = 3.0
    URL = "https://www.trustatrader.com/search"

    def search(self, category: str, city: str, max_results: int = 40) -> list:
        leads, start = [], 0
        while len(leads) < max_results:
            soup = self._get(self.URL, params={"q": category, "location": f"{city}, UK", "start": start})
            if soup is None:
                break
            cards = (soup.select("div.search-result") or
                     soup.select("[class*='trader-card']") or
                     soup.select("article"))
            if not cards:
                log.info(f"[trustatrader] No cards found (start={start}) for '{category}'/'{city}' — selectors may be stale")
                break
            raw = [self._parse(c, category, city) for c in cards]
            parsed = [l for l in raw if l]
            no_site = [l for l in parsed if not l.has_real_website()]
            log.info(f"[trustatrader] '{category}'/'{city}': {len(cards)} cards, {len(parsed)} parsed, {len(no_site)} no-website")
            leads.extend(no_site)
            if len(cards) < 8:
                break
            start += len(cards)
        log.info(f"[trustatrader] '{category}' / '{city}' → {len(leads)} leads total")
        return leads[:max_results]

    def _parse(self, card, category, city) -> Optional[BusinessLead]:
        try:
            name_el = card.select_one("h2, h3, [class*='trader-name'], [class*='business-name']")
            if not name_el:
                return None

            ws_el = card.select_one("a[class*='website']")
            website = ws_el.get("href", "") if ws_el else ""

            phone_el = card.select_one("[class*='phone'], [class*='tel'], [itemprop='telephone']")
            phone = phone_el.get_text(strip=True) if phone_el else ""

            addr_el = card.select_one("[class*='address'], [class*='location']")
            address = addr_el.get_text(", ", strip=True) if addr_el else city

            return self._make_lead(name_el.get_text(strip=True), address, city, phone, website, category)
        except Exception as exc:
            log.debug(f"[trustatrader] parse error: {exc}")
            return None


# ─────────────────────────────────────────────────────────────
# CHECKATRADE
# ─────────────────────────────────────────────────────────────

class CheckatradeScraper(BaseScraper):
    name = "checkatrade"
    base_delay = 3.5
    URL = "https://www.checkatrade.com/search"

    def search(self, category: str, city: str, max_results: int = 40) -> list:
        leads, page = [], 1
        while len(leads) < max_results and page <= 5:
            soup = self._get(self.URL, params={"what": category, "where": city, "pg": page})
            if soup is None:
                break

            # Try to extract JSON from Next.js __NEXT_DATA__
            script = soup.find("script", {"id": "__NEXT_DATA__"})
            if script:
                leads.extend(self._parse_json(script.string, category, city))
                break

            # Fall back to HTML card parsing
            cards = (soup.select("[class*='TradeMemberCard']") or
                     soup.select("[class*='trademember']") or
                     soup.select("[data-testid*='member']") or
                     soup.select("div[class*='Card']"))
            if not cards:
                break
            for card in cards:
                lead = self._parse_card(card, category, city)
                if lead and not lead.has_real_website():
                    leads.append(lead)
            page += 1

        log.info(f"[checkatrade] '{category}' / '{city}' → {len(leads)} leads")
        return leads[:max_results]

    def _parse_json(self, raw: str, category, city) -> list:
        results = []
        try:
            data = json.loads(raw)
            members = (data.get("props", {}).get("pageProps", {}).get("members") or
                       data.get("props", {}).get("pageProps", {}).get("tradespeople") or [])
            for m in members:
                name = m.get("name") or m.get("tradeName", "")
                phone = str(m.get("phone") or m.get("phoneNumber", ""))
                website = str(m.get("website") or m.get("websiteUrl", ""))
                address = str(m.get("address") or m.get("location") or city)
                if name and not website:
                    lead = self._make_lead(name, address, city, phone, "", category)
                    if lead:
                        results.append(lead)
        except Exception as exc:
            log.debug(f"[checkatrade] JSON parse error: {exc}")
        return results

    def _parse_card(self, card, category, city) -> Optional[BusinessLead]:
        try:
            name_el = card.select_one("h2, h3, [class*='Name'], [class*='name']")
            if not name_el:
                return None
            ws_el = card.select_one("a[href*='http']:not([href*='checkatrade'])")
            website = ws_el.get("href", "") if ws_el else ""
            phone_el = card.select_one("[class*='phone'], [class*='Phone']")
            phone = phone_el.get_text(strip=True) if phone_el else ""
            addr_el = card.select_one("[class*='address'], [class*='location']")
            address = addr_el.get_text(", ", strip=True) if addr_el else city
            return self._make_lead(name_el.get_text(strip=True), address, city, phone, website, category)
        except Exception as exc:
            log.debug(f"[checkatrade] card parse error: {exc}")
            return None


# ─────────────────────────────────────────────────────────────
# PLAYWRIGHT SUBPROCESS WORKERS
# ─────────────────────────────────────────────────────────────

def _configure_worker_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [worker] %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )


def _yelp_worker(task: tuple) -> list:
    """Subprocess worker — scrapes Yelp UK via Playwright."""
    category, city, max_results, headless = task
    _configure_worker_logging()
    log_w = logging.getLogger("yelp_worker")

    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout
    except ImportError:
        return []

    url = (f"https://www.yelp.co.uk/search"
           f"?find_desc={urllib.parse.quote_plus(category)}"
           f"&find_loc={urllib.parse.quote_plus(city + ', UK')}")
    leads = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless, args=["--no-sandbox"])
        ctx = browser.new_context(locale="en-GB", timezone_id="Europe/London",
                                  user_agent=random.choice(USER_AGENTS))
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            time.sleep(random.uniform(2, 4))

            # Accept cookie banner if present
            for sel in ['button:has-text("Accept")', 'button:has-text("OK")', 'button[data-testid="accept-all-cookies"]']:
                try:
                    btn = page.locator(sel).first
                    if btn.is_visible(timeout=2000):
                        btn.click(); time.sleep(1); break
                except Exception:
                    pass

            # Collect listing links
            links = page.locator('h3 a[href*="/biz/"], [class*="businessName"] a[href*="/biz/"]').all()
            for anchor in links[:max_results]:
                try:
                    href = anchor.get_attribute("href") or ""
                    biz_url = href if href.startswith("http") else "https://www.yelp.co.uk" + href
                    name = anchor.inner_text(timeout=2000).strip()
                    if not name:
                        continue

                    detail = ctx.new_page()
                    try:
                        detail.goto(biz_url, wait_until="domcontentloaded", timeout=15000)
                        time.sleep(random.uniform(1.5, 3))

                        # Check website — skip if found
                        website_el = detail.locator('a[href*="biz_website"], a[data-testid="biz-website"]').first
                        has_site = False
                        try:
                            if website_el.is_visible(timeout=2000):
                                has_site = True
                        except Exception:
                            pass
                        if has_site:
                            continue

                        phone = ""
                        try:
                            phone_el = detail.locator('p:has-text("+44"), a[href^="tel:"]').first
                            if phone_el.is_visible(timeout=1500):
                                phone = phone_el.inner_text(timeout=1500).strip()
                        except Exception:
                            pass

                        leads.append(asdict(BusinessLead(
                            name=name, address=city, city=city,
                            phone=phone, industry=category,
                            source="yelp", maps_url=biz_url,
                            scraped_at=datetime.now().isoformat(),
                        )))
                    finally:
                        detail.close()
                    time.sleep(random.uniform(2, 4))
                except Exception as exc:
                    log_w.debug(f"Yelp listing error: {exc}")
                    continue
        except Exception as exc:
            log_w.warning(f"Yelp search failed for '{category}'/'{city}': {exc}")
        finally:
            ctx.close()
            browser.close()

    log_w.info(f"[yelp] '{category}' / '{city}' → {len(leads)} leads")
    return leads


def _bark_worker(task: tuple) -> list:
    """Subprocess worker — scrapes Bark.com via Playwright."""
    category, city, max_results, headless = task
    _configure_worker_logging()
    log_w = logging.getLogger("bark_worker")

    def slugify(s: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", s.lower().strip()).strip("-")

    def pluralize(s: str) -> str:
        s = s.strip()
        if s.endswith("y") and not s.endswith(("ay", "ey", "oy", "uy")):
            return s[:-1] + "ies"
        return s if s.endswith("s") else s + "s"

    url = f"https://www.bark.com/en/gb/{slugify(pluralize(category))}/{slugify(city)}/"
    leads = []

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless, args=["--no-sandbox"])
        ctx = browser.new_context(locale="en-GB", timezone_id="Europe/London",
                                  user_agent=random.choice(USER_AGENTS))
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            time.sleep(random.uniform(2, 4))

            for sel in ['button:has-text("Accept")', 'button:has-text("Allow")', '[class*="cookie"] button']:
                try:
                    btn = page.locator(sel).first
                    if btn.is_visible(timeout=2000):
                        btn.click(); time.sleep(1); break
                except Exception:
                    pass

            # Scroll to load more
            for _ in range(3):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1.5)

            cards = page.locator('[class*="proProfileCard"], [class*="sellerCard"], .profile-card').all()
            for card in cards[:max_results]:
                try:
                    name_el = card.locator("h2, h3, [class*='name']").first
                    name = name_el.inner_text(timeout=2000).strip()
                    if not name:
                        continue
                    leads.append(asdict(BusinessLead(
                        name=name, address=city, city=city,
                        industry=category, source="bark",
                        scraped_at=datetime.now().isoformat(),
                    )))
                except Exception:
                    continue
        except Exception as exc:
            log_w.warning(f"Bark failed for '{category}'/'{city}': {exc}")
        finally:
            ctx.close()
            browser.close()

    log_w.info(f"[bark] '{category}' / '{city}' → {len(leads)} leads")
    return leads


def _gmaps_worker(task: tuple) -> list:
    """Subprocess worker — wraps the existing GoogleMapsScraper from scraper.py."""
    keyword, city, max_results, headless = task
    _configure_worker_logging()
    log_w = logging.getLogger("gmaps_worker")

    # Ensure the project root is on the path so scraper.py can be imported
    sys.path.insert(0, str(Path(__file__).parent))

    try:
        from playwright.sync_api import sync_playwright
        from scraper import GoogleMapsScraper
        from dataclasses import asdict as _asdict
    except ImportError as exc:
        log_w.error(f"Could not import scraper.py: {exc}")
        return []

    location = f"{city}, UK"
    leads = []
    with sync_playwright() as pw:
        s = GoogleMapsScraper(pw, headless=headless)
        try:
            businesses = s.extract_businesses(keyword, location, max_results)
            for b in businesses:
                d = _asdict(b)
                if d.get("website"):
                    continue  # already has a website
                leads.append(asdict(BusinessLead(
                    name=d.get("name", ""),
                    address=d.get("address", ""),
                    city=city,
                    phone=d.get("phone", ""),
                    email=d.get("email", ""),
                    industry=d.get("category", "") or keyword,
                    source="google_maps",
                    website=d.get("website", ""),
                    maps_url=d.get("maps_url", ""),
                    scraped_at=datetime.now().isoformat(),
                )))
        except Exception as exc:
            log_w.error(f"GMaps failed for '{keyword}'/'{location}': {exc}")
        finally:
            s.close()

    log_w.info(f"[gmaps] '{keyword}' / '{city}' → {len(leads)} leads")
    return leads


# ─────────────────────────────────────────────────────────────
# MASTER SCRAPER ORCHESTRATOR
# ─────────────────────────────────────────────────────────────

class MasterScraper:
    """
    Runs all enabled scrapers in parallel and merges results into all_leads.csv.
    HTTP scrapers run in threads; Playwright scrapers run in separate processes.
    """

    def __init__(
        self,
        categories: list,
        cities: list,
        sources: list = None,
        max_results: int = 40,
        http_workers: int = 8,
        pw_workers: int = 3,
        headless: bool = True,
    ):
        self.categories   = categories
        self.cities       = cities
        self.sources      = sources or ALL_SOURCES
        self.max_results  = max_results
        self.http_workers = http_workers
        self.pw_workers   = pw_workers
        self.headless     = headless

    # ── helpers ─────────────────────────────────────────────

    def _http_scrapers(self) -> dict:
        mapping = {
            "yell":         YellScraper,
            "thomson_local": ThomsonLocalScraper,
            "trustatrader": TrustATraderScraper,
            "checkatrade":  CheckatradeScraper,
        }
        return {k: cls() for k, cls in mapping.items() if k in self.sources}

    def _pw_tasks(self) -> list:
        """Return (worker_fn, task_tuple) for all Playwright searches."""
        tasks = []
        for cat in self.categories:
            for city in self.cities:
                if "yelp" in self.sources:
                    tasks.append((_yelp_worker, (cat, city, self.max_results, self.headless)))
                if "bark" in self.sources:
                    tasks.append((_bark_worker, (cat, city, self.max_results, self.headless)))
                if "google_maps" in self.sources:
                    tasks.append((_gmaps_worker, (cat, city, self.max_results, self.headless)))
        return tasks

    def _log_progress(self, done: int, total: int, t0: float, source: str, cat: str, city: str):
        elapsed = time.time() - t0
        rate = done / elapsed if elapsed > 0 else 0
        eta = (total - done) / rate / 60 if rate > 0 else 0
        log.info(
            f"  [{done}/{total}] {source} · '{cat}' / '{city}'"
            f"  |  ETA {eta:.1f} min"
        )

    # ── main run ─────────────────────────────────────────────

    def run(self) -> int:
        """Run all scrapers, merge into all_leads.csv. Returns count of new leads added."""
        http_scrapers = self._http_scrapers()
        pw_tasks = self._pw_tasks()

        http_task_list = [
            (scraper, cat, city)
            for scraper in http_scrapers.values()
            for cat in self.categories
            for city in self.cities
        ]
        total = len(http_task_list) + len(pw_tasks)

        log.info("=" * 60)
        log.info(f"MasterScraper starting")
        log.info(f"  Sources:    {self.sources}")
        log.info(f"  Categories: {len(self.categories)}")
        log.info(f"  Cities:     {len(self.cities)}")
        log.info(f"  Searches:   {total}  (HTTP:{len(http_task_list)}  PW:{len(pw_tasks)})")
        log.info("=" * 60)

        existing = load_existing_leads()
        all_new: list = []
        done = 0
        t0 = time.time()

        # ── Phase 1: HTTP scrapers in thread pool ─────────────
        if http_task_list:
            log.info(f"Phase 1/2 — HTTP scrapers ({self.http_workers} threads)…")
            with ThreadPoolExecutor(max_workers=self.http_workers) as pool:
                futures = {
                    pool.submit(scraper.search, cat, city, self.max_results): (scraper.name, cat, city)
                    for scraper, cat, city in http_task_list
                }
                for future in as_completed(futures):
                    src, cat, city = futures[future]
                    try:
                        leads = future.result()
                        all_new.extend(leads)
                    except Exception as exc:
                        log.error(f"[{src}] Failed '{cat}'/'{city}': {exc}")
                    done += 1
                    self._log_progress(done, total, t0, src, cat, city)

        # ── Phase 2: Playwright scrapers in process pool ──────
        if pw_tasks:
            log.info(f"Phase 2/2 — Playwright scrapers ({self.pw_workers} processes)…")
            with ProcessPoolExecutor(max_workers=self.pw_workers) as pool:
                futures = {
                    pool.submit(fn, task): task[:2]
                    for fn, task in pw_tasks
                }
                for future in as_completed(futures):
                    cat, city = futures[future]
                    try:
                        results = future.result()
                        all_new.extend(results)
                    except Exception as exc:
                        log.error(f"PW worker failed '{cat}'/'{city}': {exc}")
                    done += 1
                    self._log_progress(done, total, t0, "playwright", cat, city)

        # ── Merge and save ────────────────────────────────────
        added, existing = merge_leads(all_new, existing)
        save_all_leads(existing)

        elapsed = time.time() - t0
        log.info("=" * 60)
        log.info(f"SCRAPE COMPLETE in {elapsed/60:.1f} min")
        log.info(f"  Raw results:  {len(all_new)}")
        log.info(f"  New leads:    {added}")
        log.info(f"  Total in CSV: {len(existing)}")
        log.info(f"  CSV path:     {ALL_LEADS_CSV}")
        log.info("=" * 60)
        return added


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Multi-source UK business lead scraper. Outputs output/all_leads.csv.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python scraper_master.py                          # 15 default categories, 10 cities
  python scraper_master.py --all-categories --all-cities
  python scraper_master.py --sources yell,checkatrade --categories "plumber,electrician"
  python scraper_master.py --workers 6 --pw-workers 2
  python scraper_master.py --dry-run                # show task count, don't scrape
        """,
    )
    p.add_argument("--categories", type=str, help="Comma-separated categories (overrides defaults)")
    p.add_argument("--cities",     type=str, help="Comma-separated cities (overrides defaults)")
    p.add_argument("--all-categories", action="store_true", help=f"Use all {len(ALL_CATEGORIES)} categories")
    p.add_argument("--all-cities",     action="store_true", help=f"Use top {len(TOP_50_UK_CITIES)} UK cities")
    p.add_argument(
        "--sources", type=str, default=",".join(DEFAULT_SOURCES),
        help=f"Comma-separated sources (default: google_maps). Options: {ALL_SOURCES}",
    )
    p.add_argument("--max-results", type=int, default=40, help="Max results per search per source (default: 40)")
    p.add_argument("--workers",    type=int, default=8,  help="HTTP thread pool workers (default: 8)")
    p.add_argument("--pw-workers", type=int, default=2,  help="Playwright process pool workers (default: 2)")
    p.add_argument("--visible",    action="store_true",  help="Show browser windows (useful for debugging)")
    p.add_argument("--dry-run",    action="store_true",  help="Print task count and exit without scraping")
    return p


def main():
    if not REQUESTS_OK:
        log.error("Missing dependencies. Run: pip install -r requirements.txt")
        sys.exit(1)

    args = build_parser().parse_args()

    categories = (ALL_CATEGORIES if args.all_categories
                  else [c.strip() for c in args.categories.split(",") if c.strip()] if args.categories
                  else DEFAULT_CATEGORIES)

    cities = (TOP_50_UK_CITIES if args.all_cities
              else [c.strip() for c in args.cities.split(",") if c.strip()] if args.cities
              else DEFAULT_CITIES)

    sources = [s.strip() for s in args.sources.split(",") if s.strip()]

    total_tasks = len(categories) * len(cities) * len(sources)
    log.info(f"Tasks: {len(categories)} categories × {len(cities)} cities × {len(sources)} sources = {total_tasks}")

    if args.dry_run:
        log.info("Dry-run — exiting without scraping.")
        return

    scraper = MasterScraper(
        categories=categories,
        cities=cities,
        sources=sources,
        max_results=args.max_results,
        http_workers=args.workers,
        pw_workers=args.pw_workers,
        headless=not args.visible,
    )
    scraper.run()


if __name__ == "__main__":
    main()
