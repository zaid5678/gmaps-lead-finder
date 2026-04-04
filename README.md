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
