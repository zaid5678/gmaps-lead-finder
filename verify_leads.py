#!/usr/bin/env python3
"""
verify_leads.py — Post-scrape website verification.

For each lead in all_leads.csv that has no website, searches DuckDuckGo for
"{business name} {city}" and checks whether the top results contain a real
business website (not a directory listing). Leads found to have websites are
marked website_found=yes so you can filter them out before emailing.

Usage:
    python verify_leads.py                        # verify all un-checked leads
    python verify_leads.py --recheck              # re-verify everything
    python verify_leads.py --csv output/my.csv    # different file
    python verify_leads.py --dry-run              # show what would be searched
"""

import argparse
import csv
import logging
import random
import re
import time
from pathlib import Path
from urllib.parse import quote_plus, urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    raise SystemExit("Run: pip install requests beautifulsoup4 lxml")

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("verify")

OUTPUT_CSV = Path("output/all_leads.csv")

# Domains that are directories/aggregators — finding one of these is NOT
# evidence the business has its own website.
DIRECTORY_DOMAINS = {
    "yell.com", "checkatrade.com", "trustatrader.com", "bark.com",
    "yelp.co.uk", "yelp.com", "thomsonlocal.com", "ratedpeople.com",
    "mybuilder.com", "houzz.co.uk", "houzz.com", "nextdoor.com",
    "facebook.com", "instagram.com", "twitter.com", "linkedin.com",
    "google.com", "google.co.uk", "maps.google.com",
    "yellowpages.com", "cylex.co.uk", "freeindex.co.uk",
    "tradesperson.co.uk", "rated.co.uk", "checktrade.com",
    "scoot.co.uk", "192.com", "ukbusinessdirectory.com",
    "gumtree.com", "justdial.com", "hotfrog.co.uk",
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]


def _root_domain(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower().lstrip("www.")
        parts = host.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else host
    except Exception:
        return ""


def search_duckduckgo(query: str, session: requests.Session) -> list[str]:
    """Return list of result URLs from a DuckDuckGo HTML search."""
    url = "https://html.duckduckgo.com/html/"
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.7",
        "Referer": "https://duckduckgo.com/",
    }
    try:
        r = session.post(url, data={"q": query, "kl": "uk-en"}, headers=headers, timeout=15)
        if r.status_code != 200:
            log.warning(f"DuckDuckGo returned HTTP {r.status_code}")
            return []
        soup = BeautifulSoup(r.text, "lxml")
        links = []
        for a in soup.select("a.result__url, h2.result__title a, a[href*='uddg=']"):
            href = a.get("href", "")
            # DuckDuckGo wraps links — extract real URL
            if "uddg=" in href:
                m = re.search(r"uddg=([^&]+)", href)
                if m:
                    from urllib.parse import unquote
                    href = unquote(m.group(1))
            if href.startswith("http"):
                links.append(href)
        return links[:8]
    except Exception as exc:
        log.debug(f"DDG search error: {exc}")
        return []


def find_business_website(name: str, city: str, industry: str, session: requests.Session) -> str | None:
    """
    Search DuckDuckGo for the business. Return the website URL if a non-directory
    result is found, otherwise None.
    """
    query = f"{name} {city} {industry}"
    log.debug(f"Searching: {query!r}")
    urls = search_duckduckgo(query, session)

    for url in urls:
        domain = _root_domain(url)
        if domain and domain not in DIRECTORY_DOMAINS:
            # Sanity-check: the domain should look like a real business site
            # (skip generic TLDs that are clearly not this business, e.g. gov.uk, bbc.co.uk)
            if not any(generic in domain for generic in ["gov.uk", "bbc.co.", "wikipedia.", "amazon.", "ebay."]):
                log.debug(f"  Found: {url}")
                return url

    return None


def read_csv(path: Path) -> tuple[list, list]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    return fieldnames, rows


def write_csv(path: Path, fieldnames: list, rows: list):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def main():
    ap = argparse.ArgumentParser(description="Verify whether scraped leads actually have websites.")
    ap.add_argument("--csv",     default=str(OUTPUT_CSV), help="Path to leads CSV")
    ap.add_argument("--recheck", action="store_true",     help="Re-verify leads already checked")
    ap.add_argument("--dry-run", action="store_true",     help="Show what would be searched, don't update CSV")
    ap.add_argument("--delay",   type=float, default=4.0, help="Seconds between searches (default: 4)")
    args = ap.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        raise SystemExit(f"File not found: {csv_path}")

    fieldnames, rows = read_csv(csv_path)

    # Ensure verification columns exist
    for col in ("website_verified", "website_found"):
        if col not in fieldnames:
            fieldnames.append(col)
        for r in rows:
            r.setdefault(col, "")

    # Decide which rows to check
    to_check = [
        r for r in rows
        if not r.get("website")                          # no website from scrape
        and (args.recheck or not r.get("website_verified"))  # not already checked
        and r.get("name", "").strip()
    ]

    log.info(f"Leads to verify: {len(to_check)} / {len(rows)} total")

    if args.dry_run:
        for r in to_check:
            print(f"  Would search: {r['name']!r} in {r.get('city','')}")
        return

    session = requests.Session()
    found = 0
    no_site = 0

    for i, row in enumerate(to_check, 1):
        name     = row.get("name", "").strip()
        city     = row.get("city", "").strip()
        industry = row.get("industry", "").strip()

        log.info(f"[{i}/{len(to_check)}] Checking: {name} ({city})")

        website = find_business_website(name, city, industry, session)

        row["website_verified"] = "yes"
        if website:
            row["website_found"] = website
            log.info(f"  ✗ Has website: {website} — will be marked")
            found += 1
        else:
            row["website_found"] = ""
            log.info(f"  ✓ No website found — good lead")
            no_site += 1

        # Save after every lead so progress isn't lost on interrupt
        write_csv(csv_path, fieldnames, rows)

        if i < len(to_check):
            time.sleep(random.uniform(args.delay, args.delay * 1.5))

    log.info("=" * 50)
    log.info(f"Verified {len(to_check)} leads")
    log.info(f"  Have websites (exclude):  {found}")
    log.info(f"  No website (good leads):  {no_site}")
    log.info(f"  CSV updated: {csv_path}")

    # Print the clean leads
    clean = [r for r in rows if not r.get("website") and not r.get("website_found")]
    print(f"\nClean leads (no website anywhere): {len(clean)}")
    for r in clean:
        print(f"  {r.get('city',''):<15} {r.get('name',''):<40} {r.get('phone','')}")


if __name__ == "__main__":
    main()
