"""
GEM BidPlus Scraper
====================
- Opens the real browser, types the keyword, clicks the search button
- Captures the exact window.filter/window.param the site uses post-search
- Passes that filter to all subsequent requests for accurate results

Requirements:
    pip install requests selenium pandas

Usage:
    python gem_bid_scraper.py --keyword "Railways" --format json --output bids.json \
        --browser edge --driver-path "C:\path\to\msedgedriver.exe"
"""

import argparse
import json
import time
import re
import sys
import os
import shutil
from datetime import datetime, timezone

import requests
import pandas as pd

from selenium import webdriver
from selenium.webdriver.edge.options   import Options as EdgeOptions
from selenium.webdriver.edge.service   import Service as EdgeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Constants
BASE_URL      = "https://bidplus.gem.gov.in"
ALL_BIDS_PAGE = f"{BASE_URL}/all-bids"
DATA_ENDPOINT = f"{BASE_URL}/all-bids-data"

BID_STATUSES = [
    "Not Evaluated", "Technical Evaluation", "Financial Evaluation", "Bid Award"
]

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

EDGE_BINARY_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    os.path.expandvars(r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe"),
    os.path.expandvars(r"%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
]

EDGEDRIVER_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedgedriver.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedgedriver.exe",
    r"C:\Program Files (x86)\Microsoft\EdgeWebDriver\msedgedriver.exe",
    r"C:\Program Files\Microsoft\EdgeWebDriver\msedgedriver.exe",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "msedgedriver.exe"),
]

CHROME_BINARY_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]

CHROMEDRIVER_PATHS = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "chromedriver.exe"),
]

# Helpers
def find_first(paths):
    for p in paths:
        if p and os.path.isfile(p):
            return p
    return None

# Driver factories
def make_edge_driver(headless, driver_path=None):
    binary = find_first(EDGE_BINARY_PATHS) or shutil.which("msedge")
    drv    = driver_path or find_first(EDGEDRIVER_PATHS) or shutil.which("msedgedriver")

    if not binary:
        raise FileNotFoundError("Microsoft Edge binary not found.")
    if not drv:
        raise FileNotFoundError(
            "msedgedriver.exe not found.\n"
            "Download from: https://developer.microsoft.com/en-us/microsoft-edge/tools/webdriver/\n"
            "Then pass: --driver-path C:\\path\\to\\msedgedriver.exe"
        )

    print(f"[+] Edge binary : {binary}")
    print(f"[+] EdgeDriver  : {drv}")

    opts = EdgeOptions()
    opts.binary_location = binary
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument(f"user-agent={UA}")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    return webdriver.Edge(service=EdgeService(drv), options=opts)


def make_chrome_driver(headless, driver_path=None):
    binary = find_first(CHROME_BINARY_PATHS) or shutil.which("google-chrome")
    drv    = driver_path or find_first(CHROMEDRIVER_PATHS) or shutil.which("chromedriver")

    if not binary:
        raise FileNotFoundError("Chrome binary not found.")
    if not drv:
        raise FileNotFoundError("chromedriver.exe not found.")

    print(f"[+] Chrome binary : {binary}")
    print(f"[+] ChromeDriver  : {drv}")

    opts = ChromeOptions()
    opts.binary_location = binary
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument(f"user-agent={UA}")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    return webdriver.Chrome(service=ChromeService(drv), options=opts)

# Step 1 — Browser session
# Opens the page, types keyword, clicks search, then captures:
#   - cookies  (session authentication)
#   - window.filter  (exact filter object the site built after search)
#   - window.param   (exact param string the site uses)
#   - csrf_token
def get_browser_session(headless=True, browser="edge", driver_path=None, keyword=""):
    print(f"[*] Launching {browser.title()} …")

    if browser == "chrome":
        driver = make_chrome_driver(headless, driver_path=driver_path)
    else:
        driver = make_edge_driver(headless, driver_path=driver_path)

    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )

    try:
        driver.get(ALL_BIDS_PAGE)

        # Wait for the search input to appear
        search_box = WebDriverWait(driver, 25).until(
            EC.presence_of_element_located((By.ID, "searchBid"))
        )

        # Wait for initial page load spinner to clear
        WebDriverWait(driver, 25).until(
            lambda d: "gemloader.gif" not in
            d.find_element(By.ID, "bidCard").get_attribute("innerHTML")
        )
        time.sleep(1)

        # ----- Type keyword and click the search button -----
        if keyword:
            print(f"[*] Typing '{keyword}' into search box …")
            search_box.clear()
            search_box.send_keys(keyword)
            time.sleep(0.5)

            search_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "searchBidRA"))
            )
            search_btn.click()
            print("[*] Search button clicked — waiting for results …")

            # Wait for spinner to appear (search started)
            try:
                WebDriverWait(driver, 6).until(
                    lambda d: "gemloader.gif" in
                    d.find_element(By.ID, "bidCard").get_attribute("innerHTML")
                )
            except Exception:
                pass  # spinner may be too fast to catch

            # Wait for spinner to disappear (results loaded)
            WebDriverWait(driver, 30).until(
                lambda d: "gemloader.gif" not in
                d.find_element(By.ID, "bidCard").get_attribute("innerHTML")
            )
            time.sleep(2)
            print("[*] Search results loaded.")

        # ----- Capture window.filter and window.param set by the site JS -----
        try:
            js_param  = driver.execute_script("return window.param;")
            js_filter = driver.execute_script("return JSON.stringify(window.filter);")
            print(f"[+] window.param  = {js_param}")
            print(f"[+] window.filter = {js_filter}")
        except Exception as e:
            print(f"[!] Could not read window.filter/param ({e}) — will build manually.")
            js_param  = keyword
            js_filter = None

        # ----- Extract CSRF token -----
        csrf_token = ""
        try:
            csrf_token = driver.execute_script(
                "return (typeof csrf_bd_gem_nk !== 'undefined') ? csrf_bd_gem_nk : '';"
            ) or ""
        except Exception:
            pass

        if not csrf_token:
            # Search page source
            src = driver.page_source
            m = re.search(r"csrf_bd_gem_nk\s*[:=,]\s*['\"]([a-f0-9]{32})['\"]", src)
            if m:
                csrf_token = m.group(1)

        if not csrf_token:
            for s in driver.find_elements(By.TAG_NAME, "script"):
                txt = s.get_attribute("innerHTML") or ""
                m = re.search(r"['\"]([a-f0-9]{32})['\"]", txt)
                if m:
                    csrf_token = m.group(1)
                    break

        if csrf_token:
            print(f"[+] CSRF token: {csrf_token}")
        else:
            csrf_token = "5f1695962efbc998aed2f5bed85824b7"
            print(f"[!] CSRF not found — using hardcoded fallback.")

        # ----- Grab cookies -----
        cookies_dict = {c["name"]: c["value"] for c in driver.get_cookies()}
        print(f"[+] Captured {len(cookies_dict)} cookies.")

        headers = {
            "User-Agent":       UA,
            "Referer":          ALL_BIDS_PAGE,
            "Origin":           BASE_URL,
            "X-Requested-With": "XMLHttpRequest",
            "Accept":           "application/json, text/javascript, */*; q=0.01",
            "Content-Type":     "application/x-www-form-urlencoded; charset=UTF-8",
            "Accept-Language":  "en-US,en;q=0.9",
            "Accept-Encoding":  "gzip, deflate, br",
            "Connection":       "keep-alive",
            "Sec-Fetch-Dest":   "empty",
            "Sec-Fetch-Mode":   "cors",
            "Sec-Fetch-Site":   "same-origin",
        }

        return cookies_dict, headers, csrf_token, js_param, js_filter

    finally:
        driver.quit()
        print("[*] Browser closed — continuing with requests.")

# Step 2 — Requests paginator
# Uses the exact filter/param captured from the browser
def fetch_page(session, keyword, csrf_token, page=1, bid_status_type="ongoing_bids",
               js_filter=None, js_param=None):

    # Use the browser's exact filter if available
    if js_filter:
        try:
            filter_obj = json.loads(js_filter) if isinstance(js_filter, str) else js_filter
        except Exception:
            filter_obj = None
    else:
        filter_obj = None

    # Fall back to a manually built filter
    if not filter_obj:
        filter_obj = {
            "searchBid":     keyword,
            "bidStatusType": bid_status_type,
            "byType":        "all",
            "sort":          "Bid-End-Date-Latest",
            "ministry":      "",
            "state":         "",
            "department":    "",
        }

    param = js_param if js_param else keyword

    form_data = {
        "payload":        json.dumps({"param": param, "filter": filter_obj, "page": page}),
        "csrf_bd_gem_nk": csrf_token,
    }

    try:
        resp = session.post(DATA_ENDPOINT, data=form_data, timeout=25)
        if resp.status_code == 403:
            print(f"\n[!] 403 Forbidden on page {page} — session expired.")
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"\n[!] Error on page {page}: {e}")
        return None

# Step 3 — Parse bid documents
def parse_utc_date(raw):
    if raw is None:
        return ""
    try:
        if isinstance(raw, (int, float)):
            dt = datetime.fromtimestamp(raw / 1000, tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return dt.strftime("%d-%m-%Y %I:%M %p UTC")
    except Exception:
        return str(raw)

def unwrap(val, default=""):
    """Solr sometimes returns single-value fields as a list. Unwrap them."""
    if isinstance(val, list):
        return val[0] if val else default
    return val if val is not None else default

def extract_bids(docs):
    results = []
    for doc in docs:
        b_id          = unwrap(doc.get("b_id", ""))
        bid_type_code = unwrap(doc.get("b_bid_type", 0)) or 0
        eval_type     = unwrap(doc.get("b_eval_type", 0)) or 0
        raw_status    = unwrap(doc.get("b_buyer_status", 0)) or 0
        status_idx    = min(int(raw_status), len(BID_STATUSES) - 1)

        if bid_type_code == 5:
            type_lbl, doc_lbl = "RA (Direct)", "showdirectradocumentPdf"
        elif bid_type_code == 2:
            type_lbl = "RA"
            doc_lbl  = "list-ra-schedules" if eval_type > 0 else "showradocumentPdf"
        else:
            type_lbl, doc_lbl = "BID", "showbidDocument"

        tag = ""
        if unwrap(doc.get("is_rc_bid", 0)) == 1:
            tag = "Rate Contract"
        elif unwrap(doc.get("ba_is_global_tendering", 0)) == 1:
            tag = "Global Tender"

        cats = doc.get("b_category_name", [])
        results.append({
            "bid_id":       b_id,
            "bid_number":   unwrap(doc.get("b_bid_number", "")),
            "type":         type_lbl,
            "tag":          tag,
            "items":        ", ".join(cats) if isinstance(cats, list) else str(cats),
            "quantity":     unwrap(doc.get("b_total_quantity", "")),
            "ministry":     unwrap(doc.get("ba_official_details_minName", "")) or "",
            "department":   unwrap(doc.get("ba_official_details_deptName", "")) or "",
            "start_date":   parse_utc_date(unwrap(doc.get("final_start_date_sort"))),
            "end_date":     parse_utc_date(unwrap(doc.get("final_end_date_sort"))),
            "buyer_status": BID_STATUSES[status_idx],
            "bid_url":      f"{BASE_URL}/{doc_lbl}/{b_id}",
        })
    return results

# Orchestrator
def scrape(keyword, max_pages=None, bid_status_type="ongoing_bids",
           delay=1.5, headless=True, browser="edge", driver_path=None):

    cookies_dict, headers, csrf_token, js_param, js_filter = get_browser_session(
        headless=headless, browser=browser, driver_path=driver_path, keyword=keyword
    )

    session = requests.Session()
    session.headers.update(headers)
    for name, value in cookies_dict.items():
        session.cookies.set(name, value)

    print(f"\n[*] Starting paginated fetch for: '{keyword}'")
    all_bids, total_pages, page = [], None, 1

    while True:
        if max_pages and page > max_pages:
            print(f"[*] Reached max_pages limit ({max_pages}).")
            break

        label = f"page {page}" + (f"/{total_pages}" if total_pages else "")
        print(f"[*] Fetching {label} …", end=" ", flush=True)

        data = fetch_page(session, keyword, csrf_token, page, bid_status_type,
                          js_filter=js_filter, js_param=js_param)
        if data is None:
            break

        if data.get("code") != 200:
            print(f"\n[!] API code {data.get('code')}: {data.get('message', '')}")
            break

        body      = data.get("response", {}).get("response", {})
        docs      = body.get("docs", [])
        num_found = body.get("numFound", 0)

        if total_pages is None:
            total_pages = max(1, -(-num_found // 10))
            print(f"\n[+] {num_found} records → {total_pages} pages total")

        if not docs:
            print("no docs — done.")
            break

        bids = extract_bids(docs)
        all_bids.extend(bids)
        print(f"got {len(bids)} bids (total: {len(all_bids)})")

        if page >= total_pages:
            break
        page += 1
        time.sleep(delay)

    return all_bids

# Output
def save_csv(bids, path):
    pd.DataFrame(bids).to_csv(path, index=False, encoding="utf-8-sig")
    print(f"[+] Saved {len(bids)} bids → {path}")

def save_json(bids, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(bids, f, indent=2, ensure_ascii=False)
    print(f"[+] Saved {len(bids)} bids → {path}")

def print_summary(bids):
    if not bids:
        print("No bids found.")
        return
    print(f"\n{'='*62}")
    print(f"  {len(bids)} BIDS FOUND")
    print(f"{'='*62}")
    for b in bids[:5]:
        print(f"\n  Bid No : {b['bid_number']}")
        print(f"  Type   : {b['type']}  {b['tag']}")
        print(f"  Items  : {b['items'][:72]}")
        print(f"  Dept   : {b['department']}")
        print(f"  Ends   : {b['end_date']}")
        print(f"  URL    : {b['bid_url']}")
    if len(bids) > 5:
        print(f"\n  … and {len(bids)-5} more.")
    print(f"{'='*62}\n")

# CLI
def main():
    parser = argparse.ArgumentParser(
        description="Scrape GEM BidPlus — types keyword, clicks search, fetches all pages."
    )
    parser.add_argument("--keyword",     "-k", required=True)
    parser.add_argument("--output",      "-o", default="gem_bids.csv")
    parser.add_argument("--format",      "-f", choices=["csv", "json"], default="csv")
    parser.add_argument("--max-pages",   "-m", type=int, default=None)
    parser.add_argument("--status",      choices=["ongoing_bids", "bidrastatus", "closed_bids"],
                        default="ongoing_bids")
    parser.add_argument("--delay",       type=float, default=1.5)
    parser.add_argument("--browser",     choices=["edge", "chrome"], default="edge")
    parser.add_argument("--driver-path", default=None,
                        help="Path to msedgedriver.exe or chromedriver.exe")
    parser.add_argument("--no-headless", action="store_true",
                        help="Show the browser window")

    args = parser.parse_args()

    bids = scrape(
        keyword         = args.keyword,
        max_pages       = args.max_pages,
        bid_status_type = args.status,
        delay           = args.delay,
        headless        = not args.no_headless,
        browser         = args.browser,
        driver_path     = args.driver_path,
    )
    print_summary(bids)
    if not bids:
        sys.exit(1)

    if args.format == "json":
        save_json(bids, args.output)
    else:
        save_csv(bids, args.output)
if __name__ == "__main__":
    main()