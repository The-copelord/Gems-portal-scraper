# GEM BidPlus Scraper & Downloader

A toolkit to search, scrape, and download bid documents from the [Government e-Marketplace (GEM) BidPlus portal](https://bidplus.gem.gov.in/all-bids).

---

## Files

| File | Purpose |
|---|---|
| `gem_bid_scraper.py` | Search by keyword and scrape all matching bid metadata to CSV or JSON |
| `download_bids.py` | Read the JSON output and download each bid's PDF document |

---
## Requirements

### Python packages
```bash
pip install requests selenium pandas
```

### Browser + WebDriver

The scraper uses a real browser to bypass the site's bot protection. You need:

1. **Microsoft Edge** (pre-installed on Windows 10/11) — recommended  
   **or** Google Chrome

2. **EdgeDriver** matching your exact Edge version  
   - Check your Edge version: open Edge → `edge://settings/help`  
   - Download the matching driver from:  
     https://developer.microsoft.com/en-us/microsoft-edge/tools/webdriver/  
   - Unzip and place `msedgedriver.exe` anywhere convenient (e.g. the project folder)

> **No internet needed for driver setup** — the scraper uses your locally installed driver directly, unlike `webdriver-manager` which tries to download one.

---

## Usage

### Step 1 — Scrape bid metadata

```bash
python gem_bid_scraper.py \
  --keyword "Railways" \
  --format json \
  --output bids.json \
  --browser edge \
  --driver-path "C:\path\to\msedgedriver.exe"
```

This will:
1. Open Edge, type your keyword, click the search button
2. Capture the exact session cookies and search filters
3. Paginate through all result pages using `requests`
4. Save every bid's metadata to `bids.json`

**All scraper options:**

| Flag | Default | Description |
|---|---|---|
| `--keyword` / `-k` | *(required)* | Search keyword e.g. `"Railways"` |
| `--output` / `-o` | `gem_bids.csv` | Output file path |
| `--format` / `-f` | `csv` | Output format: `csv` or `json` |
| `--browser` | `edge` | Browser to use: `edge` or `chrome` |
| `--driver-path` | auto-detect | Path to `msedgedriver.exe` or `chromedriver.exe` |
| `--status` | `ongoing_bids` | Filter: `ongoing_bids`, `bidrastatus`, or `closed_bids` |
| `--max-pages` / `-m` | all pages | Limit number of pages fetched |
| `--delay` | `1.5` | Seconds to wait between page requests |
| `--no-headless` | off | Show the browser window while scraping |

---

### Step 2 — Download bid PDFs

```bash
python download_bids.py \
  --input bids.json \
  --driver-path "C:\path\to\msedgedriver.exe"
```

This will:
1. Read every entry in `bids.json`
2. Create a subfolder inside `bids_pdf/` named `{bid_number} - {items}`
3. Visit each bid URL in the browser, which triggers an automatic PDF download
4. Move the downloaded PDF into the correct subfolder, named `{bid_number}.pdf`

**Output folder structure:**
```
bids_pdf/
  GEM_2026_B_7319567 - Cleaning Sanitation and Disinfection Service/
      GEM_2026_B_7319567.pdf
  GEM_2026_B_7321846 - Monthly Basis Cab and Taxi Hiring Services/
      GEM_2026_B_7321846.pdf
  ...
```

**All downloader options:**

| Flag | Default | Description |
|---|---|---|
| `--input` / `-i` | *(required)* | Path to `bids.json` from the scraper |
| `--out-dir` / `-o` | `bids_pdf` | Root folder for downloaded PDFs |
| `--browser` | `edge` | Browser to use: `edge` or `chrome` |
| `--driver-path` | auto-detect | Path to `msedgedriver.exe` or `chromedriver.exe` |
| `--delay` | `2.0` | Seconds to wait between downloads |
| `--timeout` | `60` | Seconds to wait for each PDF to download |
| `--limit` | all | Only download the first N bids (useful for testing) |

---

### Step 3 (optional) — Fix an existing JSON file

If you have a `bids.json` produced by an older version of the scraper where fields appear as lists (e.g. `"bid_number": ["GEM/2026/B/7319567"]`) or URLs are broken (e.g. `.../showbidDocument/[9078233]`), run:

```bash
python fix_bids_json.py --input bids.json
```

This overwrites the file in-place with cleaned, normalised data. Pass `--output fixed.json` to write to a new file instead.

---

## Typical workflow

```bash
# 1. Scrape all Railway bids to JSON
python gem_bid_scraper.py --keyword "Railways" --format json --output bids.json --driver-path "C:\path\to\msedgedriver.exe"

# 2. Test the downloader on 5 bids first
python download_bids.py --input bids.json --driver-path "C:\path\to\msedgedriver.exe" --limit 5

# 3. Download everything
python download_bids.py --input bids.json --driver-path "C:\path\to\msedgedriver.exe"
```

---

## Notes

- **Resumable downloads** — the downloader skips any bid whose PDF already exists, so it is safe to stop and re-run at any time.
- **PDF fallback** — if the site opens a PDF viewer in the browser instead of triggering a download, the script automatically falls back to Chrome/Edge's built-in print-to-PDF to save the page.
- **Be polite** — the default delays (`1.5s` for scraping, `2.0s` for downloading) are intentional. GEM is a government server; avoid setting delays below `0.5s`.
- **Session expiry** — for very large result sets the browser session cookies may expire mid-run. If you see `403 Forbidden` errors, just re-run the scraper to get a fresh session, then re-run the downloader (it will skip already-downloaded files).
- **Windows path limits** — folder and file names are automatically sanitised to remove characters that Windows does not allow (`< > : " / \ | ? * ;`) and truncated to avoid hitting the 260-character path limit.
