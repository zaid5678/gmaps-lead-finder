#!/usr/bin/env python3
"""
Master orchestrator — runs the full lead-generation + email pipeline.

Step 1: Scrape all configured sources → output/all_leads.csv
Step 2: Send initial cold emails to new leads
Step 3: Send Day-3 follow-ups to leads contacted 3+ days ago
Step 4: Send Day-7 final follow-ups to leads contacted 7+ days ago
Step 5: Show live campaign stats

Usage:
    python run_all.py                   # run once, then exit
    python run_all.py --loop            # run every 7 days indefinitely
    python run_all.py --email-only      # skip scraping, send emails only
    python run_all.py --scrape-only     # scrape only, don't email
    python run_all.py --dry-run         # preview everything, no sends
    python run_all.py --stats           # show stats and exit
    python run_all.py --loop --interval 3   # run every 3 days
"""

import argparse
import csv
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

OUTPUT_DIR = Path("output")
ALL_LEADS  = OUTPUT_DIR / "all_leads.csv"
LOG_DIR    = OUTPUT_DIR / "logs"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("run_all")


# ─────────────────────────────────────────────────────────────
# STATS DISPLAY
# ─────────────────────────────────────────────────────────────

def read_stats(path: Path = ALL_LEADS) -> dict:
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return {}

    total       = len(rows)
    with_email  = sum(1 for r in rows if r.get("email", "").strip())
    contacted   = sum(1 for r in rows if r.get("contacted") == "yes")
    fu1         = sum(1 for r in rows if r.get("follow_up_1_sent") == "yes")
    fu2         = sum(1 for r in rows if r.get("follow_up_2_sent") == "yes")
    replied     = sum(1 for r in rows if r.get("replied") == "yes")
    unsub       = sum(1 for r in rows if r.get("unsubscribed"))

    # Pending queue sizes
    from auto_emailer import needs_initial, needs_follow_up_1, needs_follow_up_2
    pending_i  = sum(1 for r in rows if needs_initial(r))
    pending_f1 = sum(1 for r in rows if needs_follow_up_1(r))
    pending_f2 = sum(1 for r in rows if needs_follow_up_2(r))

    # Source breakdown
    sources: dict = {}
    for r in rows:
        s = r.get("source", "unknown")
        sources[s] = sources.get(s, 0) + 1

    return {
        "total": total, "with_email": with_email,
        "contacted": contacted, "fu1": fu1, "fu2": fu2,
        "replied": replied, "unsub": unsub,
        "pending_initial": pending_i,
        "pending_fu1": pending_f1,
        "pending_fu2": pending_f2,
        "sources": sources,
    }


def print_stats(stats: dict, label: str = "CAMPAIGN STATS"):
    if not stats:
        log.info("No leads data yet.")
        return
    s = stats
    response_rate = f"{s['replied']/s['contacted']*100:.1f}%" if s.get('contacted') else "n/a"

    print()
    print(f"{'═'*52}")
    print(f"  {label}")
    print(f"{'═'*52}")
    print(f"  Total leads scraped:    {s.get('total', 0):>6}")
    print(f"  Leads with email:       {s.get('with_email', 0):>6}")
    print()
    print(f"  Initial emails sent:    {s.get('contacted', 0):>6}")
    print(f"  Follow-up 1 sent:       {s.get('fu1', 0):>6}")
    print(f"  Follow-up 2 sent:       {s.get('fu2', 0):>6}")
    print(f"  Replies received:       {s.get('replied', 0):>6}")
    print(f"  Unsubscribed:           {s.get('unsub', 0):>6}")
    print(f"  Response rate:          {response_rate:>6}")
    print()
    print(f"  ── Pending emails ──")
    print(f"  Initial queue:          {s.get('pending_initial', 0):>6}")
    print(f"  Follow-up 1 queue:      {s.get('pending_fu1', 0):>6}")
    print(f"  Follow-up 2 queue:      {s.get('pending_fu2', 0):>6}")
    print()
    sources = s.get("sources", {})
    if sources:
        print(f"  ── Leads by source ──")
        for src, cnt in sorted(sources.items(), key=lambda x: -x[1]):
            print(f"  {src:<24}  {cnt:>6}")
    print(f"{'═'*52}")
    print()


# ─────────────────────────────────────────────────────────────
# PIPELINE STEPS
# ─────────────────────────────────────────────────────────────

def step_scrape(args_ns, scraper_args: list):
    """Run scraper_master.py as a module."""
    log.info("─" * 52)
    log.info("STEP 1 — Scraping leads")
    log.info("─" * 52)

    try:
        import scraper_master
        from scraper_master import (
            MasterScraper, DEFAULT_CATEGORIES, DEFAULT_CITIES,
            ALL_CATEGORIES, TOP_50_UK_CITIES, ALL_HTTP_SOURCES, ALL_SOURCES,
        )

        categories = ALL_CATEGORIES if args_ns.all_categories else DEFAULT_CATEGORIES
        cities     = TOP_50_UK_CITIES if args_ns.all_cities else DEFAULT_CITIES
        sources    = [s.strip() for s in args_ns.sources.split(",") if s.strip()]

        if args_ns.dry_run:
            total = len(categories) * len(cities) * len(sources)
            log.info(f"[DRY-RUN] Would scrape {total} searches across {len(sources)} sources.")
            return 0

        sm = MasterScraper(
            categories=categories,
            cities=cities,
            sources=sources,
            max_results=args_ns.max_results,
            http_workers=args_ns.workers,
            pw_workers=args_ns.pw_workers,
            headless=not args_ns.visible,
        )
        return sm.run()

    except Exception as exc:
        import traceback
        log.error(f"Scraper failed: {exc}")
        log.error(traceback.format_exc())
        return 0


def step_email(args_ns):
    """Run auto_emailer.main() for all phases."""
    log.info("─" * 52)
    log.info("STEP 2 — Email campaign")
    log.info("─" * 52)

    if not ALL_LEADS.exists():
        log.warning("No all_leads.csv found — skipping email step. Run scraping first.")
        return

    try:
        import auto_emailer

        gmail_user = args_ns.email.strip()
        app_pw     = args_ns.password.strip()

        if not args_ns.dry_run and not app_pw:
            log.error(
                "GMAIL_APP_PASSWORD is not set.\n"
                "  Add it to .env or pass --password 'xxxx xxxx xxxx xxxx'"
            )
            return

        sender = auto_emailer.GmailSender(gmail_user, app_pw) if not args_ns.dry_run else None

        fieldnames, rows = auto_emailer.read_csv(ALL_LEADS)
        for col in ["contacted", "contacted_date", "follow_up_1_sent", "follow_up_1_date",
                    "follow_up_2_sent", "follow_up_2_date", "replied", "unsubscribed", "send_status", "notes"]:
            if col not in fieldnames:
                fieldnames.append(col)
            for r in rows:
                r.setdefault(col, "")

        phases = [
            auto_emailer.INITIAL_TEMPLATE,
            auto_emailer.FOLLOW_UP_1_TEMPLATE,
            auto_emailer.FOLLOW_UP_2_TEMPLATE,
        ]

        for phase in phases:
            auto_emailer.run_phase(
                rows=rows,
                template=phase,
                sender=sender,
                delay_min=args_ns.delay_min,
                delay_max=args_ns.delay_max,
                dry_run=args_ns.dry_run,
                limit=args_ns.email_limit,
            )

        auto_emailer.write_csv(ALL_LEADS, fieldnames, rows)
        log.info(f"CSV updated: {ALL_LEADS}")

    except Exception as exc:
        log.error(f"Email step failed: {exc}")
        raise


# ─────────────────────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────────────────────

def step_push_github():
    """Rebuild README leads table and push CSV + README to GitHub."""
    log.info("─" * 52)
    log.info("STEP — Pushing to GitHub")
    log.info("─" * 52)
    try:
        from dashboard import load_leads, README_PATH, _LEGAL_MARKER

        leads = load_leads()
        leads.sort(key=lambda r: (r.get("is_priority", "") != "yes", -int(r.get("review_count") or 0)))

        header = (
            "| Business | City | Phone | Reviews | Rating | Contacted | Priority | Maps |\n"
            "|----------|------|-------|---------|--------|-----------|----------|------|\n"
        )
        table_rows = ""
        for r in leads:
            name      = r.get("name", "").replace("|", "\\|").strip()
            city      = r.get("city", "").strip()
            phone     = r.get("phone", "").replace("|", "\\|").strip()
            reviews   = r.get("review_count", "")
            rating    = r.get("rating", "")
            contacted = "Yes" if r.get("contacted") == "yes" else ""
            priority  = "YES" if r.get("is_priority") == "yes" else ""
            maps_url  = r.get("maps_url", "")
            link      = f"[Maps]({maps_url})" if maps_url else ""
            table_rows += f"| {name} | {city} | {phone} | {reviews} | {rating} | {contacted} | {priority} | {link} |\n"

        contacted_count = sum(1 for r in leads if r.get("contacted") == "yes")
        new_section = (
            "## Leads\n\n"
            f"**{len(leads)} total leads — {contacted_count} contacted, {len(leads) - contacted_count} remaining.**\n\n"
            + header + table_rows + "\n"
        )

        content = README_PATH.read_text(encoding="utf-8")
        leads_start = content.find("## Leads\n")
        legal_start = content.find(_LEGAL_MARKER)
        if leads_start != -1 and legal_start != -1:
            content = content[:leads_start] + new_section + "\n---\n\n" + content[legal_start:]
            README_PATH.write_text(content, encoding="utf-8")

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        subprocess.run(["git", "add", "output/roofers_leads.csv", "output/all_leads.csv", "README.md"], check=True)
        result = subprocess.run(["git", "diff", "--cached", "--quiet"])
        if result.returncode != 0:
            subprocess.run(["git", "commit", "-m", f"chore: leads scrape {now}"], check=True)
            subprocess.run(["git", "push", "origin", "main"], check=True)
            log.info(f"Pushed {len(leads)} leads to GitHub")
        else:
            log.info("Nothing new to push")
    except Exception as exc:
        log.warning(f"GitHub push failed (non-fatal): {exc}")


def run_once(args):
    start = datetime.now()
    log.info("╔" + "═" * 58 + "╗")
    log.info(f"║  Lead Generator + Emailer   {start.strftime('%Y-%m-%d %H:%M')}          ║")
    log.info("╚" + "═" * 58 + "╝")

    if not args.email_only:
        step_scrape(args, [])

    if not args.scrape_only:
        step_email(args)

    stats = read_stats(ALL_LEADS)
    print_stats(stats)

    if not args.dry_run:
        step_push_github()

    elapsed = (datetime.now() - start).total_seconds()
    log.info(f"Run complete in {elapsed/60:.1f} min")
    return stats


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Run the full lead-generation + email pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python run_all.py                         # scrape + email, run once
  python run_all.py --loop                  # run every 7 days forever
  python run_all.py --loop --interval 3     # run every 3 days
  python run_all.py --email-only            # email only (skip scraping)
  python run_all.py --scrape-only           # scrape only (skip email)
  python run_all.py --dry-run               # preview without sending anything
  python run_all.py --stats                 # print stats and exit
  python run_all.py --all-categories --all-cities --workers 10
        """,
    )

    # Mode flags
    mode = p.add_argument_group("mode")
    mode.add_argument("--loop",       action="store_true", help="Run continuously on a schedule")
    mode.add_argument("--interval",   type=int, default=7,  help="Days between runs in loop mode (default: 7)")
    mode.add_argument("--email-only", action="store_true",  help="Skip scraping, send emails only")
    mode.add_argument("--scrape-only",action="store_true",  help="Scrape leads only, skip email")
    mode.add_argument("--dry-run",    action="store_true",  help="Show what would happen without doing it")
    mode.add_argument("--stats",      action="store_true",  help="Print campaign stats and exit")

    # Scraper settings
    scr = p.add_argument_group("scraper")
    scr.add_argument("--sources",       type=str, default="google_maps",
                     help="Comma-separated sources (default: google_maps)")
    scr.add_argument("--all-categories",action="store_true", help="Use all 35 business categories")
    scr.add_argument("--all-cities",    action="store_true", help="Use top 50 UK cities")
    scr.add_argument("--max-results",   type=int, default=40, help="Max results per search (default: 40)")
    scr.add_argument("--workers",       type=int, default=8,  help="HTTP worker threads (default: 8)")
    scr.add_argument("--pw-workers",    type=int, default=2,  help="Playwright worker processes (default: 2)")
    scr.add_argument("--visible",       action="store_true",  help="Show browser windows")

    # Email settings
    eml = p.add_argument_group("email")
    eml.add_argument("--email",    default=os.environ.get("GMAIL_EMAIL", os.environ.get("GMAIL_USER", "zfkhan321@gmail.com")),
                     help="Gmail address to send from")
    eml.add_argument("--password", default=os.environ.get("GMAIL_APP_PASSWORD", ""),
                     help="Gmail app password (16 chars)")
    eml.add_argument("--delay-min", type=float, default=60,  help="Min seconds between emails (default: 60)")
    eml.add_argument("--delay-max", type=float, default=90,  help="Max seconds between emails (default: 90)")
    eml.add_argument("--email-limit", type=int, default=400, help="Max emails per run (default: 400 — ~8hrs at 72s avg)")

    return p


def main():
    args = build_parser().parse_args()

    if args.stats:
        stats = read_stats(ALL_LEADS)
        print_stats(stats, label="CURRENT CAMPAIGN STATS")
        return

    if args.loop:
        run_number = 0
        interval_secs = args.interval * 24 * 3600
        log.info(f"Loop mode — running every {args.interval} day(s). Press Ctrl+C to stop.")
        while True:
            run_number += 1
            log.info(f"\n{'━'*52}")
            log.info(f"  Run #{run_number}  ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
            log.info(f"{'━'*52}")
            try:
                run_once(args)
            except KeyboardInterrupt:
                log.info("Interrupted by user. Exiting loop.")
                break
            except Exception as exc:
                log.error(f"Run failed: {exc}")
                log.info("Will retry on next scheduled run.")

            next_run = datetime.now().timestamp() + interval_secs
            log.info(f"Next run scheduled for: {datetime.fromtimestamp(next_run).strftime('%Y-%m-%d %H:%M')}")
            log.info(f"Sleeping {args.interval} day(s)… (Ctrl+C to stop)")
            try:
                time.sleep(interval_secs)
            except KeyboardInterrupt:
                log.info("Interrupted by user. Exiting.")
                break
    else:
        run_once(args)


if __name__ == "__main__":
    main()
