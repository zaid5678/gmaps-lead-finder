#!/usr/bin/env python3
"""
update_readme.py — Regenerate the leads table in README.md.

Reads output/all_leads.csv and replaces the section between
<!-- LEADS_START --> and <!-- LEADS_END --> in README.md with
an up-to-date markdown table.
"""

import csv
import sys
from pathlib import Path
from datetime import datetime, timezone

CSV_PATH    = Path("output/all_leads.csv")
README_PATH = Path("README.md")
START_TAG   = "<!-- LEADS_START -->"
END_TAG     = "<!-- LEADS_END -->"


def build_table(rows: list[dict]) -> str:
    if not rows:
        return "_No leads scraped yet._\n"

    # Group by industry
    by_industry: dict[str, list] = {}
    for r in rows:
        ind = r.get("industry", "unknown").strip().title()
        by_industry.setdefault(ind, []).append(r)

    clean = [r for r in rows if not r.get("website_found")]
    contacted = sum(1 for r in rows if r.get("contacted") == "yes")

    lines = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append(f"_Last updated: {now} — {len(clean)} confirmed leads (no website) across {len(by_industry)} categories_\n")

    # Summary counts
    lines.append("| Category | Total scraped | Confirmed no website | With phone |")
    lines.append("|----------|:---:|:---:|:---:|")
    for ind, ind_rows in sorted(by_industry.items()):
        no_site  = sum(1 for r in ind_rows if not r.get("website_found"))
        w_phone  = sum(1 for r in ind_rows if r.get("phone","").strip())
        lines.append(f"| {ind} | {len(ind_rows)} | {no_site} | {w_phone} |")
    total_rows = rows
    total_clean = len(clean)
    total_phone = sum(1 for r in rows if r.get("phone","").strip())
    lines.append(f"| **Total** | **{len(total_rows)}** | **{total_clean}** | **{total_phone}** |")
    lines.append("")

    # Full leads table (only confirmed no-website leads)
    lines.append("### All Leads (confirmed no website)")
    lines.append("")
    lines.append("| # | Business | City | Category | Phone | Contacted |")
    lines.append("|---|----------|------|----------|-------|:---------:|")
    for i, r in enumerate(clean, 1):
        name      = r.get("name", "").replace("|", "&#124;")
        city      = r.get("city", "")
        industry  = r.get("industry", "").title()
        phone     = r.get("phone", "") or "—"
        contacted = "✓" if r.get("contacted") == "yes" else ""
        lines.append(f"| {i} | {name} | {city} | {industry} | {phone} | {contacted} |")

    lines.append("")
    lines.append(f"_Emails sent: {contacted} / {total_clean}_")
    return "\n".join(lines) + "\n"


def update_readme(table: str):
    if not README_PATH.exists():
        print(f"README.md not found at {README_PATH}")
        sys.exit(1)

    content = README_PATH.read_text(encoding="utf-8")

    if START_TAG not in content:
        # Append section at the end
        content += f"\n\n## Current Leads\n\n{START_TAG}\n{table}{END_TAG}\n"
    else:
        start = content.index(START_TAG) + len(START_TAG)
        end   = content.index(END_TAG)
        content = content[:start] + "\n" + table + content[end:]

    README_PATH.write_text(content, encoding="utf-8")
    print(f"README.md updated — {table.count(chr(10))} lines written")


if __name__ == "__main__":
    if not CSV_PATH.exists():
        print(f"No leads file at {CSV_PATH} — nothing to update")
        sys.exit(0)

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    table = build_table(rows)
    update_readme(table)
