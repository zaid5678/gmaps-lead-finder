#!/usr/bin/env python3
"""
Checks whether a business website is outdated, broken, or missing mobile support.

Signals checked:
  - Site unreachable / returns error (broken)
  - No SSL (http only)
  - Copyright year 2+ years old in page footer
  - Missing <meta name="viewport"> (not mobile-friendly)
  - Page loads in > 5 seconds (slow)

Usage as a module:
    from website_checker import check_website, is_outdated

Usage as CLI:
    python website_checker.py https://example.com
    python website_checker.py --csv output/all_leads.csv --out output/outdated_leads.csv
"""

import argparse
import csv
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

CURRENT_YEAR    = datetime.now().year
OUTDATED_CUTOFF = CURRENT_YEAR - 2   # copyright year <= this → outdated
REQUEST_TIMEOUT = 8                   # seconds
SLOW_THRESHOLD  = 5.0                 # seconds response time


@dataclass
class WebsiteResult:
    url: str
    reachable: bool = True
    ssl: bool = False
    copyright_year: Optional[int] = None
    has_viewport: bool = True
    response_time: float = 0.0
    status_code: int = 0
    issues: list = field(default_factory=list)
    score: int = 0  # 0 = fine, higher = more outdated

    @property
    def is_outdated(self) -> bool:
        return self.score >= 2

    @property
    def summary(self) -> str:
        if not self.reachable:
            return "broken"
        if not self.issues:
            return "ok"
        return "; ".join(self.issues)


def check_website(url: str) -> WebsiteResult:
    """Check a single URL. Returns a WebsiteResult."""
    if not url or not url.strip():
        return WebsiteResult(url=url, reachable=False, issues=["no url"])

    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    result = WebsiteResult(url=url)
    result.ssl = url.startswith("https://")
    if not result.ssl:
        result.issues.append("no SSL")
        result.score += 1

    try:
        t0 = time.time()
        resp = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (compatible; LeadChecker/1.0)"},
            allow_redirects=True,
        )
        result.response_time = time.time() - t0
        result.status_code   = resp.status_code

        if resp.status_code >= 400:
            result.reachable = False
            result.issues.append(f"HTTP {resp.status_code}")
            result.score += 3
            return result

        html = resp.text

        # Check mobile viewport
        soup = BeautifulSoup(html, "lxml")
        viewport = soup.find("meta", attrs={"name": re.compile(r"viewport", re.I)})
        if not viewport:
            result.has_viewport = False
            result.issues.append("not mobile-friendly")
            result.score += 2

        # Extract copyright year from footer or full page text
        year_matches = re.findall(r"©\s*(\d{4})|[Cc]opyright\s+(\d{4})", html)
        years = []
        for m in year_matches:
            yr = m[0] or m[1]
            if yr:
                try:
                    years.append(int(yr))
                except ValueError:
                    pass
        if years:
            result.copyright_year = max(years)
            if result.copyright_year <= OUTDATED_CUTOFF:
                result.issues.append(f"copyright {result.copyright_year}")
                result.score += 2

        # Slow response
        if result.response_time > SLOW_THRESHOLD:
            result.issues.append(f"slow ({result.response_time:.1f}s)")
            result.score += 1

    except requests.exceptions.SSLError:
        result.reachable = False
        result.issues.append("SSL error")
        result.score += 2
    except requests.exceptions.ConnectionError:
        result.reachable = False
        result.issues.append("connection refused")
        result.score += 3
    except requests.exceptions.Timeout:
        result.reachable = False
        result.issues.append("timed out")
        result.score += 2
    except Exception as exc:
        result.reachable = False
        result.issues.append(f"error: {str(exc)[:60]}")
        result.score += 2

    return result


def is_outdated(url: str) -> tuple[bool, str]:
    """Quick helper — returns (outdated: bool, reason: str)."""
    r = check_website(url)
    return r.is_outdated, r.summary


def check_leads_csv(input_csv: Path, output_csv: Path, min_score: int = 2):
    """
    Read all_leads.csv or roofers_leads.csv, check each row that HAS a website,
    and write outdated/broken ones to output_csv.
    """
    if not input_csv.exists():
        print(f"Input not found: {input_csv}")
        return

    with open(input_csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    has_website = [r for r in rows if r.get("website", "").strip()
                   or r.get("website_url", "").strip()]
    print(f"Checking {len(has_website)} businesses with websites…")

    outdated = []
    for i, row in enumerate(has_website):
        url = (row.get("website") or row.get("website_url") or "").strip()
        print(f"  [{i+1}/{len(has_website)}] {row.get('name','?')} — {url}")
        result = check_website(url)
        if result.score >= min_score:
            row["website_status"]  = result.summary
            row["website_score"]   = str(result.score)
            row["website_checked"] = datetime.now().strftime("%Y-%m-%d")
            outdated.append(row)
            print(f"    ⚠ OUTDATED ({result.score}): {result.summary}")
        else:
            print(f"    ✓ ok")

    if not outdated:
        print("No outdated websites found.")
        return

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(outdated[0].keys())
    for col in ("website_status", "website_score", "website_checked"):
        if col not in fieldnames:
            fieldnames.append(col)

    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(outdated)

    print(f"\n{len(outdated)} outdated sites → {output_csv}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Check if business websites are outdated.")
    p.add_argument("url", nargs="?", help="Single URL to check")
    p.add_argument("--csv", type=Path, help="Leads CSV to check (rows with website column)")
    p.add_argument("--out", type=Path, default=Path("output/outdated_leads.csv"),
                   help="Output CSV for outdated sites (default: output/outdated_leads.csv)")
    p.add_argument("--min-score", type=int, default=2, help="Min score to flag as outdated (default: 2)")
    args = p.parse_args()

    if args.url:
        r = check_website(args.url)
        print(f"\nURL:          {r.url}")
        print(f"Reachable:    {r.reachable}")
        print(f"SSL:          {r.ssl}")
        print(f"Status code:  {r.status_code}")
        print(f"Response:     {r.response_time:.2f}s")
        print(f"Viewport:     {r.has_viewport}")
        print(f"Copyright yr: {r.copyright_year}")
        print(f"Issues:       {', '.join(r.issues) or 'none'}")
        print(f"Score:        {r.score}")
        print(f"Outdated:     {r.is_outdated}")
    elif args.csv:
        check_leads_csv(args.csv, args.out, args.min_score)
    else:
        p.print_help()
        sys.exit(1)
