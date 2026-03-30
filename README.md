# Google Maps Lead Scraper 🇬🇧

Find UK businesses on Google Maps that **don't have a website** — sorted by review count so you target the highest-demand opportunities first.

Built for selling web development services to established businesses that are missing an online presence.

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
├── scraper.py          # Main script — everything in one file
├── requirements.txt    # Python dependencies
├── README.md           # This file
└── output/             # CSV files (created on first run)
    ├── leads_*.csv
    └── all_results_*.csv
```

---

## Legal Note

This tool is for personal lead generation research. Be mindful of Google's Terms of Service. Use responsibly, don't hammer their servers, and respect the businesses you contact. Consider using the Google Maps Platform API for production-scale usage.
