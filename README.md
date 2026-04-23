# UK Lead Finder — Fully Automated Scraper + Email Outreach

Find UK businesses with **no website** across 7 sources simultaneously, then email them automatically with a 3-stage follow-up sequence — all from one command.

Built for selling web development services to local businesses missing an online presence.

---

## Current Leads

<!-- LEADS_START -->
_Last updated: 2026-04-23 17:14 UTC — 29 confirmed leads (no website) across 1 categories_

| Category | Total scraped | Confirmed no website | With phone |
|----------|:---:|:---:|:---:|
| Roofer | 36 | 29 | 34 |
| **Total** | **36** | **29** | **34** |

### All Leads (confirmed no website)

| # | Business | City | Category | Phone | Contacted |
|---|----------|------|----------|-------|:---------:|
| 1 | Mark The Roof in Kings Heath Birmingham UK | Birmingham | Roofer | +44 7976 286141  |  |
| 2 | Roofing Pro ltd | Liverpool | Roofer | +44 7836 699933  |  |
| 3 | James Lucas Roofing Services | Sheffield | Roofer | +44 7764 940522  |  |
| 4 | Leicestershire Roofing Services Ltd | Leicester | Roofer | +44 7572 133999  |  |
| 5 | MPS ROOFING SERVICES | London | Roofer | 07888 844547  |  |
| 6 | Como Roofing UK Ltd | London | Roofer | 07534 288217  |  |
| 7 | Roofing in London Limited | London | Roofer | 07365 773035  |  |
| 8 | Fitz Roofing | London | Roofer | 020 3670 0226  |  |
| 9 | Tr Roofing | London | Roofer | 07572 750482  |  |
| 10 | West Kensington‎ Roofing | London | Roofer | 020 7126 7260  |  |
| 11 | Fulham Roofers | London | Roofer | 020 3519 2878  |  |
| 12 | Kentish Town Roofing | London | Roofer | 020 3519 0673  |  |
| 13 | London Building & Roofing | London | Roofer | 07551 139005  |  |
| 14 | Stj Roofing Lambeth | London | Roofer | 020 3670 4368  |  |
| 15 | Zenith roofing & Building | London | Roofer | 020 8485 8769  |  |
| 16 | TOB ROOFING & GUTTERING | London | Roofer | 07446 143745  |  |
| 17 | i-tec Flat Roofing | London | Roofer | 020 7692 8381  |  |
| 18 | Broadway Roofing Contractors | London | Roofer | 07444 712714  |  |
| 19 | Safeguard Roofing | Manchester | Roofer | 07759 852170  |  |
| 20 | All Seasons Roofing Ltd | Manchester | Roofer | 07879 153463  |  |
| 21 | LT Roofing & Maintenance | Manchester | Roofer | 07565 218854  |  |
| 22 | Lavelle Roofing | Manchester | Roofer | 07729 244037  |  |
| 23 | Roofer Manchester ltd | Manchester | Roofer | 07493 219057  |  |
| 24 | Roof Plus Uk Ltd | Manchester | Roofer | 07393 997535  |  |
| 25 | Evolution Roofing | Manchester | Roofer | — |  |
| 26 | Manchester Industrial Roofing | Manchester | Roofer | 0161 738 1347  |  |
| 27 | Roof Maintainers Ltd | Manchester | Roofer | 07562 877658  |  |
| 28 | K.H. ROOFING CONTRACTORS LTD | Manchester | Roofer | — |  |
| 29 | J. HEMPSTOCK & CO LTD | Manchester | Roofer | 0161 223 2123  |  |

_Emails sent:  / 29_
<!-- LEADS_END -->

---

## Quick Start

```bash
# 1. Clone and set up
bash setup.sh          # installs all dependencies, creates .env

# 2. Add your Gmail app password
nano .env              # set GMAIL_APP_PASSWORD

# 3. Preview everything (no emails sent)
python run_all.py --dry-run

# 4. Run once
python run_all.py

# 5. Run on a 7-day loop forever
python run_all.py --loop
```

> **One command does it all:** scrapes 7 directories → finds businesses without websites → sends personalised cold emails → automatically follows up on Day 3 and Day 7.

---

## How It Works

```
run_all.py
├── Step 1 — scraper_master.py  (7 sources, parallel)
│   ├── Yell.com
│   ├── Thomson Local
│   ├── TrustATrader
│   ├── Checkatrade
│   ├── Yelp UK          (Playwright — optional)
│   ├── Bark.com         (Playwright — optional)
│   └── Google Maps      (Playwright — optional)
│            └── output/all_leads.csv
│
└── Step 2 — auto_emailer.py  (Gmail SMTP)
    ├── Initial email    (first contact)
    ├── Follow-up 1      (Day 3 — if no reply)
    └── Follow-up 2      (Day 7 — last attempt)
```

### Lead filtering
- Only businesses with **no website** (or only food-delivery aggregators like Uber Eats)
- Google Maps results also filtered by minimum review count (≥50 by default)
- All sources deduplicated by MD5(name + address)

### Email sequence
| Step | When | Subject template |
|------|------|-----------------|
| Initial | Immediately | "Quick idea for {name} — get online for £500" |
| Follow-up 1 | Day 3 | "Following up — website for {name}" |
| Follow-up 2 | Day 7 | "Last message — {name} website" |

Emails skipped if lead has already received that template, replied, or unsubscribed.

---

## Setup

### Prerequisites
- **Python 3.10+**
- **Gmail account** with 2-Step Verification enabled

### 1. Install everything

```bash
bash setup.sh
```

This installs all pip packages, downloads Playwright's Chromium browser, creates `output/`, and validates your `.env`.

### 2. Get a Gmail App Password

1. Go to [myaccount.google.com/security](https://myaccount.google.com/security)
2. Enable **2-Step Verification**
3. Search **"App passwords"**
4. App: **Mail** | Device: **Other** | Name: `lead-finder`
5. Copy the 16-character password (e.g. `wsgj nmyg lrlf cnnr`)

### 3. Configure `.env`

```bash
GMAIL_EMAIL=zfkhan321@gmail.com
GMAIL_APP_PASSWORD=wsgj nmyg lrlf cnnr
```

---

## Usage

### Master orchestrator (recommended)

```bash
# Run everything once
python run_all.py

# Run every 7 days in the background
python run_all.py --loop

# Custom interval (every 3 days)
python run_all.py --loop --interval 3

# Use all 35 categories × top 50 UK cities
python run_all.py --all-categories --all-cities

# Include Playwright sources (Yelp, Bark, Google Maps) with 3 browser processes
python run_all.py --sources yell,thomson_local,trustatrader,checkatrade,yelp,bark,google_maps --pw-workers 3

# Scrape only, no email
python run_all.py --scrape-only

# Email only (skip scraping)
python run_all.py --email-only

# Check campaign stats
python run_all.py --stats
```

### Individual tools

```bash
# Multi-source scraper
python scraper_master.py                          # default 15 categories, 10 cities
python scraper_master.py --all-categories --all-cities --workers 10
python scraper_master.py --sources yell,checkatrade --dry-run

# Automated emailer
python auto_emailer.py --dry-run                  # preview all pending emails
python auto_emailer.py                            # send all phases
python auto_emailer.py --phase initial            # initial outreach only
python auto_emailer.py --phase follow_up_1        # Day-3 follow-ups only
python auto_emailer.py --stats-only               # campaign stats only
python auto_emailer.py --limit 30                 # cap at 30 emails

# Original Google Maps scraper (still works standalone)
python scraper.py --keywords "plumber,electrician" --cities "London, UK|Manchester, UK"
```

### Output files

| File | Description |
|------|-------------|
| `output/all_leads.csv` | Unified leads from all sources — append-only, tracked across runs |
| `output/leads_*.csv` | Per-run leads from Google Maps scraper |
| `output/all_results_*.csv` | All raw Google Maps results (unfiltered) |
| `output/logs/email_log.txt` | Full email activity log |
| `output/logs/run_*.log` | Scraper run logs |

### all_leads.csv columns

| Column | Description |
|--------|-------------|
| `fingerprint` | MD5(name+address) — deduplication key |
| `name` | Business name |
| `address` | Full address |
| `city` | City scraped from |
| `phone` | Phone number |
| `email` | Email address (empty for most leads) |
| `industry` | Business category |
| `source` | Which directory (yell, google_maps, etc.) |
| `website` | Empty = confirmed no website |
| `contacted` | `yes` once initial email sent |
| `contacted_date` | ISO timestamp of initial email |
| `follow_up_1_sent` | `yes` once Day-3 email sent |
| `follow_up_2_sent` | `yes` once Day-7 email sent |
| `replied` | Mark `yes` manually when a lead replies |
| `unsubscribed` | Mark `yes` manually on STOP replies |

---

## Rate Limits & Best Practices

### Email sending
- Default: **8–12 seconds** between emails → ~45 emails/hour
- Gmail free tier: stay under **100 emails/day** to avoid flags
- Use `--limit 50` to cap each run safely
- Increase delay with `--delay-min 15 --delay-max 25` if your account is new

### Scraping
- HTTP scrapers (Yell, Thomson Local, etc.): throttled to **2–4 seconds** per request
- Playwright scrapers (Yelp, Bark, Maps): human-like delays built-in
- Recommended: **≤500 Google Maps listings per session** to avoid CAPTCHA
- Parallel browsers (`--pw-workers`): keep at 2–3 max

### Tracking unsubscribes
When someone replies "STOP", open `output/all_leads.csv` and set their `unsubscribed` column to `yes`. The emailer will skip them automatically.

---

## Sources Explained

| Source | Method | Quality | Notes |
|--------|--------|---------|-------|
| Yell.com | HTTP + BS4 | High | UK's largest business directory |
| Thomson Local | HTTP + BS4 | High | Traditional UK directory |
| TrustATrader | HTTP + BS4 | Medium | Trade services only |
| Checkatrade | HTTP + BS4 | Medium | Trade services, may need Playwright |
| Yelp UK | Playwright | Medium | JS-rendered; uses `--pw-workers` |
| Bark.com | Playwright | Medium | Service marketplace; profiles rarely have websites |
| Google Maps | Playwright | High | Best data quality; needs `--sources` flag to include |

> Playwright sources are excluded from the default `--sources` list to keep the first run fast. Add `yelp,bark,google_maps` to `--sources` once you're comfortable with the system.

---

## Project Structure

```
gmaps-lead-finder/
├── run_all.py           # Master orchestrator — run this
├── scraper_master.py    # Multi-source scraper (7 directories)
├── auto_emailer.py      # Automated email sender (3-stage sequence)
├── scraper.py           # Original Google Maps scraper (still used internally)
├── email_sender.py      # Standalone email sender for per-run CSVs
├── email_templates.py   # Detailed email templates
├── config.yaml          # All settings (delays, limits, SMTP)
├── setup.sh             # One-time setup script
├── requirements.txt     # Python dependencies
├── .env                 # Credentials (gitignored)
├── .env.template        # Template for .env
└── output/
    ├── all_leads.csv        # Unified leads (all sources, all runs)
    ├── leads_*.csv          # Per-run Google Maps leads
    ├── all_results_*.csv    # Per-run raw results
    ├── seen_leads.json      # Deduplication registry (scraper.py)
    ├── outreach_sent.json   # Outreach tracking (scraper.py)
    └── logs/
        ├── email_log.txt    # Full email activity log
        └── run_*.log        # Scraper logs
```

---

## Legal & Compliance

**Cold email to businesses (B2B) under UK GDPR:**
- B2B cold email is permitted under the **legitimate interests** basis when:
  - You are contacting businesses (not individuals/consumers)
  - The service is directly relevant to their trade
  - You include your real contact details
  - You honour opt-out requests immediately
- This system always includes an unsubscribe instruction ("Reply STOP")
- Review [ICO direct marketing guidance](https://ico.org.uk/for-organisations/direct-marketing) before running at scale

**Web scraping:**
- All scraped data is publicly available on the respective directories
- The scrapers use human-like delays and respect rate limits
- Do not scrape at volumes that would impair the target sites
- Google Maps scraping is against Google's ToS — use the [Maps Platform API](https://developers.google.com/maps) for production-scale usage

**This tool is for personal lead generation only — not for resale or third-party use.**

---

## What It Does

1. Searches Google Maps for business types (barber, takeaway, nail salon, etc.) across UK cities
2. Scrolls through results to load up to ~100 listings per search
3. Opens each listing and extracts: name, address, phone, rating, reviews, website, Instagram
4. Filters to businesses with **no website** and **≥50 reviews** (configurable)
5. Detects if a business only uses Uber Eats / Just Eat / Deliveroo (no real site)
6. Deduplicates across searches
7. Exports a prioritised CSV of leads

---

## Setup

### 1. Prerequisites

- **Python 3.10+** installed
- **pip** package manager

### 2. Install dependencies

```bash
cd gmaps_lead_scraper
pip install -r requirements.txt
```

### 3. Install Playwright browsers

```bash
playwright install chromium
```

This downloads a Chromium binary (~150 MB) that the scraper controls.

---

## Usage

### Basic run (uses all defaults)

```bash
python scraper.py
```

Defaults: searches for `barber`, `takeaway`, `nail salon` in London, Manchester, Birmingham with a 50-review minimum.

### Custom keywords and cities

```bash
python scraper.py \
  --keywords "plumber,electrician,personal trainer" \
  --cities "London, UK,Leeds, UK,Bristol, UK" \
  --min-reviews 30 \
  --min-rating 4.0 \
  --max-results 80
```

### Debug mode (watch the browser)

```bash
python scraper.py --visible
```

### All CLI options

| Flag | Default | Description |
|------|---------|-------------|
| `--keywords` | `barber,takeaway,nail salon` | Comma-separated business types |
| `--cities` | `London, UK,Manchester, UK,Birmingham, UK` | Comma-separated locations |
| `--min-reviews` | `50` | Minimum Google review count |
| `--min-rating` | `0.0` | Minimum star rating (set to `4.0` for quality filter) |
| `--max-results` | `100` | Max listings to scrape per keyword+city pair |
| `--visible` | off | Show the browser window |

---

## Output

Results are saved in the `output/` folder:

- **`leads_YYYYMMDD_HHMMSS.csv`** — Filtered leads (no website, meets review threshold)
- **`all_results_YYYYMMDD_HHMMSS.csv`** — Every business scraped (for reference)

### CSV columns

| Column | Description |
|--------|-------------|
| `name` | Business name |
| `address` | Full address |
| `phone` | Phone number |
| `rating` | Google star rating (0–5) |
| `review_count` | Number of Google reviews |
| `website` | Empty for leads (that's the point!) |
| `category` | Business category from Google |
| `instagram` | Instagram URL if found |
| `third_party_only` | Lists delivery platforms (Uber Eats, etc.) if detected |
| `search_keyword` | Which keyword found this business |
| `search_location` | Which city search found this business |

---

## How the Filtering Works

A business is included as a lead if **ALL** of these are true:

1. **No website** — the Google Maps listing has no website link, OR the link points to a food delivery aggregator (Uber Eats, Just Eat, Deliveroo, etc.)
2. **Enough reviews** — meets the `--min-reviews` threshold (default 50)
3. **High enough rating** — meets the `--min-rating` threshold (default 0.0 = no filter)

Businesses are then sorted by review count descending — the ones with 500+ reviews and no website are your hottest leads.

---

## Suggested Keyword Ideas

High-value niches for selling websites:

- `barber`, `hair salon`, `nail salon`, `beauty salon`
- `takeaway`, `restaurant`, `cafe`, `bakery`
- `plumber`, `electrician`, `roofer`, `builder`
- `personal trainer`, `gym`, `yoga studio`
- `car mechanic`, `MOT centre`, `car wash`
- `dentist`, `physiotherapist`, `chiropractor`
- `dog groomer`, `pet shop`, `veterinary`
- `tattoo studio`, `piercing shop`
- `locksmith`, `cleaning service`, `handyman`

---

## Anti-Detection Measures

The scraper includes several measures to avoid being blocked:

- Realistic Chrome user-agent string
- Random delays between all actions (1–3 seconds)
- Character-by-character typing in the search box
- Longer random pauses every ~20 listings
- UK locale, timezone, and geolocation set
- Automation detection flags disabled

**Tips to avoid blocks:**

- Don't run more than ~500 listings per session
- Space out runs by at least a few hours
- Use `--visible` mode occasionally to solve any CAPTCHAs manually
- Consider rotating residential proxies for heavy use

---

## Troubleshooting

### "Could not find results panel"
Google Maps layout changes occasionally. Try running with `--visible` to see what's happening. The scraper may need selector updates.

### Cookie consent blocking everything
The scraper auto-accepts cookies, but if it fails, run with `--visible` and accept manually on the first run.

### Very few results
Google Maps typically shows 20–120 results per search. For more leads, add more keyword/city combinations.

### Getting blocked / CAPTCHAs
Reduce `--max-results` to 50, increase delays in the config section at the top of `scraper.py`, or add proxy support.

---

## Project Structure

```
gmaps_lead_scraper/
├── scraper.py           # Main scraper — Google Maps extraction + filtering
├── email_sender.py      # Standalone email automation script
├── email_templates.py   # Cold email templates (initial, follow-up, final)
├── config.yaml          # Settings for email, delays, and scraper
├── requirements.txt     # Python dependencies
├── .env                 # Credentials (gitignored — never commit this)
├── .env.template        # Template for .env
├── README.md            # This file
└── output/              # Generated files (gitignored)
    ├── leads_*.csv          # Filtered leads with email column
    ├── all_results_*.csv    # All scraped businesses
    ├── seen_leads.json      # Deduplication registry
    └── outreach_sent.json   # Outreach tracking registry
```

---

## Email Automation

### How it works

`email_sender.py` reads your leads CSV, sends personalized cold emails via Gmail SMTP,
and tracks who has been contacted directly in the CSV (adds `contacted`, `contacted_date`,
`template_used`, and `send_status` columns).

Three-stage outreach sequence:
| Stage | Template | When to send |
|-------|----------|--------------|
| 1 | `initial` | First contact — introduces the website idea |
| 2 | `follow_up` | ~3 days later — gentle reminder |
| 3 | `final` | ~7 days later — last attempt, low pressure |

### Setup

#### 1. Get a Gmail App Password

Regular Gmail passwords won't work — you need a 16-character **app password**:

1. Go to [myaccount.google.com/security](https://myaccount.google.com/security)
2. Enable **2-Step Verification** if not already on
3. Search for **"App passwords"** in the search bar
4. Select app: **Mail** → device: **Other** → name it `lead-finder`
5. Copy the 16-character password (e.g. `wsgj nmyg lrlf cnnr`)

#### 2. Add credentials to `.env`

```bash
GMAIL_USER=your_email@gmail.com
GMAIL_APP_PASSWORD=wsgj nmyg lrlf cnnr
```

#### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### Usage

```bash
# Preview all emails without sending anything (always safe to run)
python email_sender.py --dry-run

# Preview with full email body visible
python email_sender.py --dry-run --verbose

# Send initial outreach (reads credentials from .env automatically)
python email_sender.py

# Send initial outreach with explicit credentials
python email_sender.py --email you@gmail.com --password "wsgj nmyg lrlf cnnr"

# Send follow-ups (skips leads already sent initial)
python email_sender.py --template follow_up

# Send final follow-ups
python email_sender.py --template final

# Use a specific CSV file
python email_sender.py --csv-file output/leads_20260420_120000.csv --template follow_up

# Slow down to 20s between emails
python email_sender.py --delay 20
```

### Scaling up the scraper

```bash
# Scrape all 25 business categories across default 10 cities
python scraper.py --all-categories

# Scrape default keywords across all 50 UK cities
python scraper.py --all-cities

# Full scale: all categories × all 50 cities (1,250 searches — takes hours)
python scraper.py --all-categories --all-cities

# Use 3 parallel browsers to speed up scraping (uses more memory)
python scraper.py --workers 3 --all-categories

# Combine: roofing across all cities with 2 workers
python scraper.py --all-cities --workers 2
```

> **Parallel workers:** Each worker runs its own Chromium browser. Recommended maximum is 3 workers — more can trigger Google rate limiting or exhaust memory.

### Best practices for cold email

- **Volume:** Send no more than 50–100 emails per day from a single Gmail account
- **Warm-up:** Start with 10–20/day and increase gradually over 1–2 weeks
- **Personalisation:** The templates already include `{business_name}`, `{city}`, and `{industry}` — edit `email_templates.py` to customise further
- **Avoid spam triggers:** Don't use ALL CAPS, excessive punctuation, or spammy phrases like "FREE!!!" or "CLICK NOW"
- **Delays:** The default 5–10s delay between sends is intentional — increase to 15–30s for safer daily limits
- **Unsubscribes:** Respect any reply asking not to be contacted again
- **Focus on leads with emails:** Only businesses that have an email address visible on Google Maps will receive outreach. Most leads will need to be contacted by phone instead.

### Legal disclaimer

Cold email outreach to businesses (B2B) is generally permitted under GDPR when there is a **legitimate interest** — you are a sole trader offering a relevant service to businesses that could plausibly benefit. However:

- Always include your real name and contact details in emails
- Honour opt-out requests immediately
- Do not scrape or email at mass scale without reviewing the ICO guidance on direct marketing
- This tool is for **personal lead generation** — not for resale or automated bulk campaigns
- Review [ico.org.uk/for-organisations/direct-marketing](https://ico.org.uk/for-organisations/direct-marketing) for UK rules

---

## Leads

All leads are appended here automatically after each run.

### Previous leads (leads_20260331_001030.csv) — 31 Mar 2026 00:10 (1 leads)

| Business | Category | City | Phone | Reviews | Rating | Maps |
|----------|----------|------|-------|---------|--------|------|
| Wicked VIP Mobile Barber |  | London, UK | 07572 923289 | 121 | 4.9 |  |


---

### Previous leads (leads_20260331_171314.csv) — 31 Mar 2026 17:13 (1 leads)

| Business | Category | City | Phone | Reviews | Rating | Maps |
|----------|----------|------|-------|---------|--------|------|
| Jersey Street Social Club - Barber Shop Manchester |  | Manchester, UK | 0161 236 5901 | 156 | 4.8 | [Maps](https://www.google.com/maps/place/Jersey+Street+Social+Club+-+Barber+Shop+Manchester/data=!4m7!3m6!1s0x487bb1bb86da246f:0x23bc358cbfa2a30d!8m2!3d53.4835136!4d-2.2292798!16s%2Fg%2F11f08jy871!19sChIJbyTahruxe0gRDaOiv4w1vCM?authuser=0&hl=en&rclk=1) |


---

### Previous leads (leads_20260331_175331.csv) — 31 Mar 2026 17:53 (11 leads)

| Business | Category | City | Phone | Reviews | Rating | Maps |
|----------|----------|------|-------|---------|--------|------|
| Great British Restaurant |  | London, UK | 020 7491 4840 | 708 | 4.7 | [Maps](https://www.google.com/maps/place/Great+British+Restaurant/data=!4m7!3m6!1s0x487604d7eb4e127f:0xfb641c47b4c42419!8m2!3d51.5054451!4d-0.1394859!16s%2Fg%2F11dxkkxg2y!19sChIJfxJO69cEdkgRGSTEtEccZPs?authuser=0&hl=en&rclk=1) |
| Fade Masters Barbers |  | Manchester, UK | 0161 248 9496 | 509 | 4.7 | [Maps](https://www.google.com/maps/place/Fade+Masters+Barbers/data=!4m7!3m6!1s0x487bb23118cf6489:0xf4aa066e32008d78!8m2!3d53.4417506!4d-2.218368!16s%2Fg%2F11fx_0v99m!19sChIJiWTPGDGye0gReI0AMm4GqvQ?authuser=0&hl=en&rclk=1) |
| Sam’s Electrical Services LTD |  | Manchester, UK | 07507 515818 | 281 | 5.0 | [Maps](https://www.google.com/maps/place/Sam%E2%80%99s+Electrical+Services+LTD/data=!4m7!3m6!1s0x487baf096ebc5c69:0xbdb59c071464e47!8m2!3d53.4601712!4d-2.2772431!16s%2Fg%2F11tmn9m5ps!19sChIJaVy8bgmve0gRR05GccBZ2ws?authuser=0&hl=en&rclk=1) |
| Northern Quarter Barber |  | Manchester, UK | 0161 236 0978 | 200 | 4.5 | [Maps](https://www.google.com/maps/place/Northern+Quarter+Barber/data=!4m7!3m6!1s0x487bb1b9465e2219:0xce85af4e1db0af1b!8m2!3d53.4842216!4d-2.2336266!16s%2Fg%2F11bbrgswy3!19sChIJGSJeRrmxe0gRG6-wHU6vhc4?authuser=0&hl=en&rclk=1) |
| Baz Cutz |  | Birmingham, UK | 07763 636379 | 192 | 4.9 | [Maps](https://www.google.com/maps/place/Baz+Cutz/data=!4m7!3m6!1s0x4870bdab4e866087:0x7013be0c1d66b1c3!8m2!3d52.4553156!4d-1.8861739!16s%2Fg%2F11zk1kt5sl!19sChIJh2CGTqu9cEgRw7FmHQy-E3A?authuser=0&hl=en&rclk=1) |
| Jersey Street Social Club - Barber Shop Manchester |  | Manchester, UK | 0161 236 5901 | 156 | 4.8 | [Maps](https://www.google.com/maps/place/Jersey+Street+Social+Club+-+Barber+Shop+Manchester/data=!4m7!3m6!1s0x487bb1bb86da246f:0x23bc358cbfa2a30d!8m2!3d53.4835136!4d-2.2292798!16s%2Fg%2F11f08jy871!19sChIJbyTahruxe0gRDaOiv4w1vCM?authuser=0&hl=en&rclk=1) |
| Wicked VIP Mobile Barber |  | London, UK | 07572 923289 | 121 | 4.9 | [Maps](https://www.google.com/maps/place/Wicked+VIP+Mobile+Barber/data=!4m7!3m6!1s0x48761d3b2381a44b:0xb0341bb738ee88d0!8m2!3d51.5023083!4d-0.153372!16s%2Fg%2F11jtyr8h8s!19sChIJS6SBIzsddkgR0IjuOLcbNLA?authuser=0&hl=en&rclk=1) |
| RN Electrical Services |  | Manchester, UK | 07976 837343 | 119 | 5.0 | [Maps](https://www.google.com/maps/place/RN+Electrical+Services/data=!4m7!3m6!1s0x487bad251eb1ebf5:0x9ebb4bb4eee7b8a9!8m2!3d53.4441164!4d-2.2660752!16s%2Fg%2F11b5pj69qq!19sChIJ9euxHiWte0gRqbjn7rRLu54?authuser=0&hl=en&rclk=1) |
| My Plumbers Didsbury |  | Manchester, UK | 0161 410 2470 | 109 | 4.9 | [Maps](https://www.google.com/maps/place/My+Plumbers+Didsbury/data=!4m7!3m6!1s0x487bb33935408dd9:0xaf9f6ea923b6ec1e!8m2!3d53.4726386!4d-2.2565407!16s%2Fg%2F11hlfyd96v!19sChIJ2Y1ANTmze0gRHuy2I6lun68?authuser=0&hl=en&rclk=1) |
| tantech Electricals Birmingham Westmidland |  | Birmingham, UK | 07386 775618 | 83 | 4.9 | [Maps](https://www.google.com/maps/place/tantech+Electricals+Birmingham+Westmidland/data=!4m7!3m6!1s0x4870bbfec41ec0f5:0xa40b3317f602407d!8m2!3d52.443547!4d-1.8505143!16s%2Fg%2F11kyrwsv1x!19sChIJ9cAexP67cEgRfUAC9hczC6Q?authuser=0&hl=en&rclk=1) |
| City Electrical Services (Midlands) |  | Birmingham, UK | 07875 603686 | 73 | 5.0 | [Maps](https://www.google.com/maps/place/City+Electrical+Services+%28Midlands%29/data=!4m7!3m6!1s0x4870bbe83a90e055:0xbb4eb67093177ec2!8m2!3d52.4508428!4d-1.8823013!16s%2Fg%2F1tjcnwyl!19sChIJVeCQOui7cEgRwn4Xk3C2Trs?authuser=0&hl=en&rclk=1) |


---

---


### minicab, private hire — 03 Apr 2026 01:44 (39 leads)

| Business | Category | City | Phone | Reviews | Rating | Maps |
|----------|----------|------|-------|---------|--------|------|
| St Pauls Cars |  | Birmingham, UK | 0121 236 1919 | 449 | 4.5 | [Maps](https://www.google.com/maps/place/St+Pauls+Cars/data=!4m7!3m6!1s0x4870bced051cbc0f:0x5bf37d1441ebd50b!8m2!3d52.486673!4d-1.908754!16s%2Fg%2F1w97tvb2!19sChIJD7wcBe28cEgRC9XrQRR981s?authuser=0&hl=en&rclk=1) |
| Great Barr Cars |  | Birmingham, UK | 0121 258 7777 | 444 | 4.4 | [Maps](https://www.google.com/maps/place/Great+Barr+Cars/data=!4m7!3m6!1s0x4870a36b8fadd27f:0xb72a48099702bf6!8m2!3d52.5340429!4d-1.8977846!16s%2Fg%2F11x18q0xgc!19sChIJf9Ktj2ujcEgR9itwmYCkcgs?authuser=0&hl=en&rclk=1) |
| Village Taxis |  | Liverpool, UK | 0151 427 7909 | 234 | 2.8 | [Maps](https://www.google.com/maps/place/Village+Taxis/data=!4m7!3m6!1s0x487b200995768095:0x60ecf6c912586376!8m2!3d53.3570503!4d-2.9049097!16s%2Fg%2F1v6l70l3!19sChIJlYB2lQkge0gRdmNYEsn27GA?authuser=0&hl=en&rclk=1) |
| ABC Taxi's |  | Leicester, UK | 0116 255 5111 | 231 | 2.5 | [Maps](https://www.google.com/maps/place/ABC+Taxi%27s/data=!4m7!3m6!1s0x4877641bc19b5809:0xddec19fbc04e8ecc!8m2!3d52.6302278!4d-1.1246449!16s%2Fg%2F1txnnzm3!19sChIJCVibwRtkd0gRzI5OwPsZ7N0?authuser=0&hl=en&rclk=1) |
| Dixons Taxis |  | Newcastle, UK | 0191 273 3339 | 194 | 4.6 | [Maps](https://www.google.com/maps/place/Dixons+Taxis/data=!4m7!3m6!1s0x487e77412d1ec0e5:0xbfa892d43e2ad7b3!8m2!3d54.9690044!4d-1.6482076!16s%2Fg%2F1tdfh7tv!19sChIJ5cAeLUF3fkgRs9cqPtSSqL8?authuser=0&hl=en&rclk=1) |
| Walker Taxis |  | Newcastle, UK | 0191 265 2237 | 154 | 4.0 | [Maps](https://www.google.com/maps/place/Walker+Taxis/data=!4m7!3m6!1s0x487e706f70c4e7e9:0x17fecf8edb4496e5!8m2!3d54.9652604!4d-1.5502964!16s%2Fg%2F1trpqbxk!19sChIJ6efEcG9wfkgR5ZZE247P_hc?authuser=0&hl=en&rclk=1) |
| Beeston Line Private Hire |  | Leeds, UK | 0113 277 7444 | 140 | 3.2 | [Maps](https://www.google.com/maps/place/Beeston+Line+Private+Hire/data=!4m7!3m6!1s0x48795c28d0157c5f:0x2a85554a8624b6b8!8m2!3d53.7791596!4d-1.5445828!16s%2Fg%2F1tp26s_8!19sChIJX3wV0ChceUgRuLYkhkpVhSo?authuser=0&hl=en&rclk=1) |
| Manchester Cars |  | Manchester, UK | 0161 228 3355 | 130 | 2.3 | [Maps](https://www.google.com/maps/place/Manchester+Cars/data=!4m7!3m6!1s0x487bb195526734a5:0xc46bf571ebb90cab!8m2!3d53.477024!4d-2.237938!16s%2Fg%2F1tgf2s34!19sChIJpTRnUpWxe0gRqwy563H1a8Q?authuser=0&hl=en&rclk=1) |
| Royal Cars |  | Leeds, UK | 0113 230 5000 | 125 | 2.5 | [Maps](https://www.google.com/maps/place/Royal+Cars/data=!4m7!3m6!1s0x48795eb3778b6759:0xd35b4c0d3808c0d2!8m2!3d53.8108478!4d-1.5710201!16s%2Fg%2F1tj52356!19sChIJWWeLd7NeeUgR0sAIOA1MW9M?authuser=0&hl=en&rclk=1) |
| Kapital Venue |  | Leicester, UK | 07866 802172 | 90 | 3.7 | [Maps](https://www.google.com/maps/place/Kapital+Venue/data=!4m7!3m6!1s0x4877611cb87edeaf:0xa59f4d2c1459f9af!8m2!3d52.6420406!4d-1.1299416!16s%2Fg%2F1hc13rw2t!19sChIJr95-uBxhd0gRr_lZFCxNn6U?authuser=0&hl=en&rclk=1) |
| Juve Lounge |  | Newcastle, UK | 07376 921926 | 90 | 4.7 | [Maps](https://www.google.com/maps/place/Juve+Lounge/data=!4m7!3m6!1s0x487e77a0dfcfeec9:0x1e009e70ee13b4b1!8m2!3d54.9765206!4d-1.6795577!16s%2Fg%2F11dxhy4c7v!19sChIJye7P36B3fkgRsbQT7nCeAB4?authuser=0&hl=en&rclk=1) |
| County Cars |  | Nottingham, UK | 0115 942 5425 | 87 | 3.8 | [Maps](https://www.google.com/maps/place/County+Cars/data=!4m7!3m6!1s0x48799554110a4ff3:0x6fd72d76b92a1ecf!8m2!3d52.9758192!4d-1.2118917!16s%2Fg%2F1thmkj4b!19sChIJ808KEVSVeUgRzx4quXYt128?authuser=0&hl=en&rclk=1) |
| Ukrainian Cultural Centre |  | Nottingham, UK | 07948 469302 | 81 | 4.6 | [Maps](https://www.google.com/maps/place/Ukrainian+Cultural+Centre/data=!4m7!3m6!1s0x4879c10aafb69a5d:0x2cb8b517615aa8a1!8m2!3d52.9764022!4d-1.1500992!16s%2Fg%2F1tc_w3hw!19sChIJXZq2rwrBeUgRoahaYRe1uCw?authuser=0&hl=en&rclk=1) |
| Leeds Taxi Central |  | Leeds, UK | 07346 198919 | 80 | 3.6 | [Maps](https://www.google.com/maps/place/Leeds+Taxi+Central/data=!4m7!3m6!1s0x48795da3f32fa60b:0x74c122c18f6b7142!8m2!3d53.7959001!4d-1.5455369!16s%2Fg%2F11gxmctk9g!19sChIJC6Yv86NdeUgRQnFrj8EiwXQ?authuser=0&hl=en&rclk=1) |
| Circle Taxis |  | Leicester, UK | 0116 251 5105 | 77 | 3.5 | [Maps](https://www.google.com/maps/place/Circle+Taxis/data=!4m7!3m6!1s0x487760e050e8af41:0xe48b564f01b4510d!8m2!3d52.6352813!4d-1.1389533!16s%2Fg%2F1tfx4dkm!19sChIJQa_oUOBgd0gRDVG0AU9Wi-Q?authuser=0&hl=en&rclk=1) |
| RCL Travel LTD |  | Liverpool, UK | 07508 847404 | 67 | 3.9 | [Maps](https://www.google.com/maps/place/RCL+Travel+LTD/data=!4m7!3m6!1s0x487b212d8f33416f:0xe02e9aff504c1b04!8m2!3d53.4340596!4d-2.9812043!16s%2Fg%2F11cn5n4vd2!19sChIJb0Ezjy0he0gRBBtMUP-aLuA?authuser=0&hl=en&rclk=1) |
| New Star Private Hire Taxis |  | Manchester, UK | 0161 881 1111 | 62 | 4.3 | [Maps](https://www.google.com/maps/place/New+Star+Private+Hire+Taxis/data=!4m7!3m6!1s0x487badf283b80919:0xd176e5b9fb11db13!8m2!3d53.4361155!4d-2.2739175!16s%2Fg%2F12mm855gt!19sChIJGQm4g_Kte0gRE9sR-7nldtE?authuser=0&hl=en&rclk=1) |
| Bristol Taxis Ltd |  | Bristol, UK | 0117 287 0247 | 59 | 2.1 | [Maps](https://www.google.com/maps/place/Bristol+Taxis+Ltd/data=!4m7!3m6!1s0x48718e0bbd4aeaf1:0xbd019f4f48e7fd35!8m2!3d51.4686897!4d-2.5924538!16s%2Fg%2F1w4f7k2n!19sChIJ8epKvQuOcUgRNf3nSE-fAb0?authuser=0&hl=en&rclk=1) |
| Alpha Taxis |  | Liverpool, UK | 0151 728 8888 | 54 | 3.6 | [Maps](https://www.google.com/maps/place/Alpha+Taxis/data=!4m7!3m6!1s0x487b20e882dc06ad:0xc2329bb52c492297!8m2!3d53.3861261!4d-2.9649027!16s%2Fg%2F11lkh0qkys!19sChIJrQbcgugge0gRlyJJLLWbMsI?authuser=0&hl=en&rclk=1) |
| Lost in Seel Street |  | Liverpool, UK | 07555 151129 | 52 | 4.3 | [Maps](https://www.google.com/maps/place/Lost+in+Seel+Street/data=!4m7!3m6!1s0x487b21030895a3af:0x7b7836ac574255a4!8m2!3d53.4016449!4d-2.9783583!16s%2Fg%2F11tdcgy42n!19sChIJr6OVCAMhe0gRpFVCV6w2eHs?authuser=0&hl=en&rclk=1) |
| Yang Fujia |  | Nottingham, UK | 0115 846 6336 | 50 | 4.4 | [Maps](https://www.google.com/maps/place/Yang+Fujia/data=!4m7!3m6!1s0x4879c209c169aed1:0xb771d03345302c8c!8m2!3d52.9521007!4d-1.1851857!16s%2Fg%2F1thp7j7g!19sChIJ0a5pwQnCeUgRjCwwRTPQcbc?authuser=0&hl=en&rclk=1) |
| Marquee Manchester Events |  | Manchester, UK | 07842 446737 | 49 | 4.9 | [Maps](https://www.google.com/maps/place/Marquee+Manchester+Events/data=!4m7!3m6!1s0x487bb1b3798a5a15:0x8670186f19339488!8m2!3d53.4836383!4d-2.2366595!16s%2Fg%2F11t526qn2r!19sChIJFVqKebOxe0gRiJQzGW8YcIY?authuser=0&hl=en&rclk=1) |
| Street Cars Taxis |  | Leeds, UK | 0113 243 3333 | 45 | 3.0 | [Maps](https://www.google.com/maps/place/Street+Cars+Taxis/data=!4m7!3m6!1s0x48795c1af4045ba1:0x314154c1651feea!8m2!3d53.8006037!4d-1.5405076!16s%2Fg%2F1tkc65vd!19sChIJoVsE9BpceUgR6v5RFkwVFAM?authuser=0&hl=en&rclk=1) |
| Highfields Taxis |  | Leicester, UK | 0116 262 4004 | 43 | 2.6 | [Maps](https://www.google.com/maps/place/Highfields+Taxis/data=!4m7!3m6!1s0x4877611919216c29:0xfd5c5c2a8a8e9964!8m2!3d52.6367705!4d-1.1273714!16s%2Fg%2F1vgw83zd!19sChIJKWwhGRlhd0gRZJmOiipcXP0?authuser=0&hl=en&rclk=1) |
| The Venue Event Hire |  | Liverpool, UK | 07596 863424 | 39 | 4.3 | [Maps](https://www.google.com/maps/place/The+Venue+Event+Hire/data=!4m7!3m6!1s0x487b2136e2a3651b:0xa566e4bec3f9d7c!8m2!3d53.4234638!4d-2.9351916!16s%2Fg%2F11qg5s3156!19sChIJG2Wj4jYhe0gRfJ0_7EtuVgo?authuser=0&hl=en&rclk=1) |
| A2B TAXIS SHEFFIELD |  | Sheffield, UK | 0114 400 3535 | 35 | 4.3 | [Maps](https://www.google.com/maps/place/A2B+TAXIS+SHEFFIELD/data=!4m7!3m6!1s0x48799d2610da0979:0xabba3d48c235822e!8m2!3d53.3606564!4d-1.408745!16s%2Fg%2F11nmldcpkk!19sChIJeQnaECadeUgRLoI1wkg9uqs?authuser=0&hl=en&rclk=1) |
| Dad's Cabs |  | Bristol, UK | 0117 935 0053 | 28 | 4.5 | [Maps](https://www.google.com/maps/place/Dad%27s+Cabs/data=!4m7!3m6!1s0x48718e6cd36fb66f:0xcb1963ed188048c4!8m2!3d51.4654847!4d-2.5808856!16s%2Fg%2F11t4f04xn5!19sChIJb7Zv02yOcUgRxEiAGO1jGcs?authuser=0&hl=en&rclk=1) |
| Boat Party London |  | London, UK | 07939 363020 | 27 | 5.0 | [Maps](https://www.google.com/maps/place/Boat+Party+London/data=!4m7!3m6!1s0x48761d4edb9f2521:0xd32683cc0cc92f55!8m2!3d51.5292262!4d-0.0883143!16s%2Fg%2F11p07c8d12!19sChIJISWf204ddkgRVS_JDMyDJtM?authuser=0&hl=en&rclk=1) |
| Outer Space Bristol |  | Bristol, UK |  | 25 | 4.3 | [Maps](https://www.google.com/maps/place/Outer+Space+Bristol/data=!4m7!3m6!1s0x48718d0cf263ef81:0xb25781f1c51f539b!8m2!3d51.44915!4d-2.6024367!16s%2Fg%2F11nnqdl9z9!19sChIJge9j8gyNcUgRm1MfxfGBV7I?authuser=0&hl=en&rclk=1) |
| Mersey Cabs Ltd |  | Liverpool, UK | 07873 681051 | 21 | 3.7 | [Maps](https://www.google.com/maps/place/Mersey+Cabs+Ltd/data=!4m7!3m6!1s0x487b2117b4fd1903:0xbe26ae975e658dc1!8m2!3d53.4104135!4d-2.9700207!16s%2Fg%2F11b6hxx3sp!19sChIJAxn9tBche0gRwY1lXpeuJr4?authuser=0&hl=en&rclk=1) |
| Venue Hire South Leicestershire |  | Leicester, UK | 07837 325557 | 20 | 4.3 | [Maps](https://www.google.com/maps/place/Venue+Hire+South+Leicestershire/data=!4m7!3m6!1s0x4877671d29938cd9:0xeee269db18e9d5af!8m2!3d52.5802091!4d-1.1372165!16s%2Fg%2F1hc371sx4!19sChIJ2YyTKR1nd0gRr9XpGNtp4u4?authuser=0&hl=en&rclk=1) |
| Alpha Travel |  | Liverpool, UK | 0151 260 0000 | 19 | 3.5 | [Maps](https://www.google.com/maps/place/Alpha+Travel/data=!4m7!3m6!1s0x487b210cd33b432d:0xdba6ac2a129a0193!8m2!3d53.4188747!4d-2.9554191!16s%2Fg%2F1tslj7z4!19sChIJLUM70wwhe0gRkwGaEiqspts?authuser=0&hl=en&rclk=1) |
| OctoCabs 8 seater Taxi service |  | Newcastle, UK | 07506 955191 | 16 | 5.0 | [Maps](https://www.google.com/maps/place/OctoCabs+8+seater+Taxi+service/data=!4m7!3m6!1s0x487e71937374a1c9:0x3f5d4871565563d3!8m2!3d55.0090696!4d-1.5779523!16s%2Fg%2F11v63txl01!19sChIJyaF0c5NxfkgR02NVVnFIXT8?authuser=0&hl=en&rclk=1) |
| N.P.G Taxi Hire Ltd |  | Nottingham, UK | 0115 979 4500 | 15 | 4.4 | [Maps](https://www.google.com/maps/place/N.P.G+Taxi+Hire+Ltd/data=!4m7!3m6!1s0x4879ebfa05fdecbf:0xd8812909953737df!8m2!3d53.0125655!4d-1.1882422!16s%2Fg%2F11lz49l_9q!19sChIJv-z9BfrreUgR3zc3lQkpgdg?authuser=0&hl=en&rclk=1) |
| GH Travel |  | Sheffield, UK | 07472 513148 | 12 | 4.7 | [Maps](https://www.google.com/maps/place/GH+Travel/data=!4m7!3m6!1s0x4ae157643386d2ff:0x4dac27ddc12e5a4!8m2!3d53.3913432!4d-1.4604625!16s%2Fg%2F11ynmjmh87!19sChIJ_9KGM2RX4UoRpOUS3H3C2gQ?authuser=0&hl=en&rclk=1) |
| Geordie Cabs |  | Newcastle, UK | 0191 286 3000 | 11 | 4.4 | [Maps](https://www.google.com/maps/place/Geordie+Cabs/data=!4m7!3m6!1s0x487e7708172e2135:0xd615f070ed235503!8m2!3d54.9816758!4d-1.6745043!16s%2Fg%2F1yh9tzc_0!19sChIJNSEuFwh3fkgRA1Uj7XDwFdY?authuser=0&hl=en&rclk=1) |
| Midlands Private Hire Ltd |  | Birmingham, UK | 07496 053888 | 7 | 3.6 | [Maps](https://www.google.com/maps/place/Midlands+Private+Hire+Ltd/data=!4m7!3m6!1s0x4870bb7b22a42de3:0x62dd723fa02061c6!8m2!3d52.4966196!4d-1.8682921!16s%2Fg%2F11h5rpl24m!19sChIJ4y2kInu7cEgRxmEgoD9y3WI?authuser=0&hl=en&rclk=1) |
| Unique Venue Hire |  | Leeds, UK | 07466 492740 | 5 | 3.8 | [Maps](https://www.google.com/maps/place/Unique+Venue+Hire/data=!4m7!3m6!1s0x48795d78f6834c8f:0x5e369100b9d18f7c!8m2!3d53.804774!4d-1.506416!16s%2Fg%2F11shp6tx0h!19sChIJj0yD9nhdeUgRfI_RuQCRNl4?authuser=0&hl=en&rclk=1) |
| The Courtyard Events Space |  | Sheffield, UK |  | 5 | 5.0 | [Maps](https://www.google.com/maps/place/The+Courtyard+Events+Space/data=!4m7!3m6!1s0x4879796ebe318e37:0x6ed8c1aaf1856206!8m2!3d53.3879568!4d-1.4507696!16s%2Fg%2F11sp6dfptm!19sChIJN44xvm55eUgRBmKF8arB2G4?authuser=0&hl=en&rclk=1) |


---


### private doctor, private dentist, private GP, physiotherapist, chiropractor, optician, private clinic, cosmetic clinic, private dermatologist, private psychiatrist — 04 Apr 2026 02:04 (9 leads)

| Business | Category | City | Phone | Reviews | Rating | Maps |
|----------|----------|------|-------|---------|--------|------|
| Ascenti Physio Manchester Spinningfields |  | Manchester, UK | 0330 678 0850 | 113 | 4.8 | [Maps](https://www.google.com/maps/place/Ascenti+Physio+Manchester+Spinningfields/data=!4m7!3m6!1s0x487bb1a259f1e0f1:0x42746b9e24131ad!8m2!3d53.479909!4d-2.251089!16s%2Fg%2F11hz99h456!19sChIJ8eDxWaKxe0gRrTFB4rlGJwQ?authuser=0&hl=en&rclk=1) |
| Reqover Clinic |  | Manchester, UK | 07780 724715 | 68 | 4.9 | [Maps](https://www.google.com/maps/place/Reqover+Clinic/data=!4m7!3m6!1s0x487bb1099165e027:0x89188c89fc0c39a6!8m2!3d53.4683353!4d-2.2173177!16s%2Fg%2F11whml07hw!19sChIJJ-BlkQmxe0gRpjkM_ImMGIk?authuser=0&hl=en&rclk=1) |
| The City and Travel Clinic |  | London, UK | 020 7062 2385 | 54 | 4.0 | [Maps](https://www.google.com/maps/place/The+City+and+Travel+Clinic/data=!4m7!3m6!1s0x48760512a850de7d:0xd7d9fca48f1fe29c!8m2!3d51.5023025!4d-0.1543379!16s%2Fg%2F11qpl6czjy!19sChIJfd5QqBIFdkgRnOIfj6T82dc?authuser=0&hl=en&rclk=1) |
| The Eye Centre |  | Manchester, UK | 0161 478 7473 | 53 | 4.8 | [Maps](https://www.google.com/maps/place/The+Eye+Centre/data=!4m7!3m6!1s0x487bb3d797477505:0xb01df18d4420f6aa!8m2!3d53.4553853!4d-2.1980766!16s%2Fg%2F1pxqdkrz9!19sChIJBXVHl9eze0gRqvYgRI3xHbA?authuser=0&hl=en&rclk=1) |
| The Ancoats Refinery |  | Manchester, UK | 07533 862172 | 37 | 5.0 | [Maps](https://www.google.com/maps/place/The+Ancoats+Refinery/data=!4m7!3m6!1s0x487bb1bb9b48216b:0x7b5e7a623b35d5df!8m2!3d53.4838743!4d-2.2292122!16s%2Fg%2F1td_b70k!19sChIJayFIm7uxe0gR39U1O2J6Xns?authuser=0&hl=en&rclk=1) |
| HCA Healthcare UK - Manchester Central |  | Manchester, UK | 0345 437 0691 | 28 | 3.4 | [Maps](https://www.google.com/maps/place/HCA+Healthcare+UK+-+Manchester+Central/data=!4m7!3m6!1s0x487bb1c152f65549:0xdf162cac3a223e92!8m2!3d53.4830557!4d-2.2451809!16s%2Fg%2F1vr3cnlc!19sChIJSVX2UsGxe0gRkj4iOqwsFt8?authuser=0&hl=en&rclk=1) |
| Manchester Private Hospital |  | Manchester, UK | 0161 507 8822 | 17 | 3.8 | [Maps](https://www.google.com/maps/place/Manchester+Private+Hospital/data=!4m7!3m6!1s0x48761b413343383d:0xd0856b185b30ae12!8m2!3d51.5207652!4d-0.1492013!16s%2Fg%2F11h48rvyj3!19sChIJPThDM0EbdkgREq4wWxhrhdA?authuser=0&hl=en&rclk=1) |
| Private Doctor Clinic |  | London, UK | 020 3474 6300 | 9 | 4.6 | [Maps](https://www.google.com/maps/place/Private+Doctor+Clinic/data=!4m7!3m6!1s0x4876057dabe652a1:0x1ca3b80593d00c93!8m2!3d51.4848553!4d-0.1746473!16s%2Fg%2F11g7yb6cm2!19sChIJoVLmq30FdkgRkwzQkwW4oxw?authuser=0&hl=en&rclk=1) |
| Leskupu Clinic |  | London, UK | 07540 637496 | 8 | 4.5 | [Maps](https://www.google.com/maps/place/Leskupu+Clinic/data=!4m7!3m6!1s0x48760548ed6e31cf:0xbfbd8e2470d1624!8m2!3d51.5081739!4d-0.153161!16s%2Fg%2F11fhxqsxbw!19sChIJzzFu7UgFdkgRJBYNR-LY-ws?authuser=0&hl=en&rclk=1) |


---

## Legal Note

This tool is for personal lead generation research. Be mindful of Google's Terms of Service. Use responsibly, don't hammer their servers, and respect the businesses you contact. Consider using the Google Maps Platform API for production-scale usage.
