"""
GEM Bid PDF Downloader
=======================
Reads the JSON output from scraper.py and downloads the bid document
PDF for every entry.

Folder structure created:
    bids_pdf/
        {bid_number} - {items}/
            {bid_number}.pdf
        ...

Usage:
    python download_bids.py --input bids.json
    python download_bids.py --input bids.json --out-dir my_folder --delay 2.0
    python download_bids.py --input bids.json --driver-path "C:\\path\\to\\msedgedriver.exe"
"""

import argparse
import json
import os
import re
import time
import shutil
import sys

from selenium import webdriver
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait

# Constants
EDGE_BINARY_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    os.path.expandvars(r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe"),
    os.path.expandvars(r"%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
]

EDGEDRIVER_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedgedriver.exe",
    r"C:\Program Files\Microsoft\EdgeWebDriver\msedgedriver.exe",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "msedgedriver.exe"),
]

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# Characters not allowed in Windows folder/file names
INVALID_CHARS = r'[<>:"/\\|?*;\x00-\x1f]'
# Helpers
def find_first(paths):
    for p in paths:
        if p and os.path.isfile(p):
            return p
    return None

def unwrap(val, default=""):
    """Solr returns some fields as lists — unwrap to scalar."""
    if isinstance(val, list):
        return val[0] if val else default
    return val if val is not None else default

def fix_bid(bid):
    """
    Normalise a bid dict so all fields are plain scalars (not lists) and
    the bid_url contains the real numeric ID (not '[12345]').
    """
    bid = dict(bid)  # shallow copy — don't mutate original

    for key in ("bid_id", "bid_number", "quantity", "ministry", "department",
                "start_date", "end_date"):
        bid[key] = unwrap(bid.get(key, ""))

    # Fix bid_url: replace /showbidDocument/[9078233] → /showbidDocument/9078233
    url = bid.get("bid_url", "")
    url = re.sub(r"/\[(\d+)\]", r"/", url)
    bid["bid_url"] = url

    return bid

def safe_name(text, max_len=80):
    """Strip characters illegal in Windows paths and truncate."""
    text = str(text)
    text = re.sub(INVALID_CHARS, "_", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = text[:max_len].rstrip(". ")   # Windows forbids trailing dots/spaces
    return text

def folder_name_for(bid):
    """
    Build a folder name like:
        GEM-2026-B-7319567 - Cleaning Sanitation and Disinfection Service
    """
    bid_no = safe_name(unwrap(bid.get("bid_number", "UNKNOWN")), 60)
    items  = safe_name(unwrap(bid.get("items",      "unknown")),  80)
    return f"{bid_no} - {items}"

def wait_for_download(download_dir, timeout=60):
    """
    Block until a new fully-downloaded file appears in download_dir.
    Returns the path of the downloaded file, or None on timeout.
    Ignores .crdownload / .tmp partial files.
    """
    end = time.time() + timeout
    seen_before = set(os.listdir(download_dir))

    while time.time() < end:
        current = set(os.listdir(download_dir))
        new_files = current - seen_before
        complete  = [
            f for f in new_files
            if not f.endswith((".crdownload", ".tmp", ".partial"))
        ]
        if complete:
            return os.path.join(download_dir, complete[0])
        time.sleep(0.8)

    return None

# Browser factory  (download-enabled)
def make_driver(browser, driver_path, download_dir):
    """
    Create a Selenium driver with automatic PDF download enabled
    (no print dialog, saves directly to download_dir).
    """
    abs_dl = os.path.abspath(download_dir)
    os.makedirs(abs_dl, exist_ok=True)

    if browser == "chrome":
        binary = find_first([
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]) or shutil.which("google-chrome")
        drv = driver_path or shutil.which("chromedriver")

        opts = ChromeOptions()
        opts.binary_location = binary
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument(f"user-agent={UA}")
        opts.add_experimental_option("prefs", {
            "download.default_directory":         abs_dl,
            "download.prompt_for_download":       False,
            "download.directory_upgrade":         True,
            "plugins.always_open_pdf_externally": True,   # key: don't open PDF in browser
            "safebrowsing.enabled":               True,
        })
        return webdriver.Chrome(service=ChromeService(drv), options=opts)
    else:  # edge
        binary = find_first(EDGE_BINARY_PATHS) or shutil.which("msedge")
        drv    = driver_path or find_first(EDGEDRIVER_PATHS) or shutil.which("msedgedriver")

        if not binary:
            raise FileNotFoundError("Microsoft Edge binary not found.")
        if not drv:
            raise FileNotFoundError(
                "msedgedriver.exe not found.\n"
                "Pass --driver-path C:\\path\\to\\msedgedriver.exe"
            )

        opts = EdgeOptions()
        opts.binary_location = binary
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument(f"user-agent={UA}")
        # Tell Edge to download PDFs directly instead of opening them
        opts.add_experimental_option("prefs", {
            "download.default_directory":         abs_dl,
            "download.prompt_for_download":       False,
            "download.directory_upgrade":         True,
            "plugins.always_open_pdf_externally": True,
            "safebrowsing.enabled":               True,
        })
        return webdriver.Edge(service=EdgeService(drv), options=opts)
    
# Core downloader
def download_all(bids, out_dir, browser, driver_path, delay, timeout):
    """
    For each bid:
      1. Create  out_dir / {bid_number} - {items} /
      2. Open the bid_url in the browser (triggers auto-download)
      3. Wait for the PDF to land in a temp download dir
      4. Move it into the bid's subfolder, named {bid_number}.pdf
    """
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    # Use a single temp download staging area
    staging = os.path.join(out_dir, "_staging_")
    os.makedirs(staging, exist_ok=True)
    print(f"\n[*] Output root  : {out_dir}")
    print(f"[*] Bids to fetch: {len(bids)}\n")
    driver = make_driver(browser, driver_path, staging)
    ok, skipped, failed = 0, 0, 0
    try:
        for i, bid in enumerate(bids, 1):
            bid      = fix_bid(bid)
            bid_no   = bid.get("bid_number", f"bid_{i}")
            bid_url  = bid.get("bid_url", "")
            items    = bid.get("items", "unknown")

            if not bid_url:
                print(f"[{i}/{len(bids)}] SKIP — no URL for {bid_no}")
                skipped += 1
                continue
            # Build destination folder and final file path
            folder   = os.path.join(out_dir, folder_name_for(bid))
            dest_pdf = os.path.join(folder, f"{safe_name(bid_no)}.pdf")

            # Skip if already downloaded
            if os.path.isfile(dest_pdf):
                print(f"[{i}/{len(bids)}] SKIP (exists) — {bid_no}")
                skipped += 1
                continue
            os.makedirs(folder, exist_ok=True)
            print(f"[{i}/{len(bids)}] Downloading — {bid_no}")
            print(f"         URL    : {bid_url}")
            print(f"         Folder : {folder}")
            # Snapshot of staging before download
            before = set(os.listdir(staging))
            try:
                driver.get(bid_url)
            except Exception as e:
                print(f"         ERROR navigating: {e}")
                failed += 1
                continue
            # Wait for a new complete file to appear in staging
            downloaded = None
            end = time.time() + timeout
            while time.time() < end:
                current = set(os.listdir(staging))
                new = current - before
                complete = [
                    f for f in new
                    if not f.endswith((".crdownload", ".tmp", ".partial"))
                ]
                if complete:
                    downloaded = os.path.join(staging, complete[0])
                    break
                time.sleep(0.8)
            if downloaded and os.path.isfile(downloaded):
                shutil.move(downloaded, dest_pdf)
                size_kb = os.path.getsize(dest_pdf) / 1024
                print(f"         SAVED  : {dest_pdf}  ({size_kb:.1f} KB)")
                ok += 1
            else:
                print(f"         TIMEOUT — no file downloaded within {timeout}s")
                # The page may have opened a viewer instead of downloading;
                # try saving via print-to-PDF as a fallback
                try:
                    pdf_data = driver.execute_cdp_cmd(
                        "Page.printToPDF",
                        {"printBackground": True, "preferCSSPageSize": True}
                    )
                    import base64
                    with open(dest_pdf, "wb") as f:
                        f.write(base64.b64decode(pdf_data["data"]))
                    size_kb = os.path.getsize(dest_pdf) / 1024
                    print(f"         SAVED (CDP print-to-PDF): {dest_pdf}  ({size_kb:.1f} KB)")
                    ok += 1
                except Exception as e2:
                    print(f"         CDP fallback also failed: {e2}")
                    failed += 1

            time.sleep(delay)
    finally:
        driver.quit()
        # Clean up empty staging dir
        try:
            if not os.listdir(staging):
                os.rmdir(staging)
        except Exception:
            pass
    print(f"\n{'='*55}")
    print(f"  Done — {ok} saved, {skipped} skipped, {failed} failed")
    print(f"{'='*55}\n")

# CLI
def main():
    parser = argparse.ArgumentParser(
        description="Download GEM bid PDFs from scraper JSON output."
    )
    parser.add_argument("--input",       "-i", required=True,
                        help="Path to bids.json produced by gem_bid_scraper.py")
    parser.add_argument("--out-dir",     "-o", default="bids_pdf",
                        help="Root output folder (default: bids_pdf next to this script)")
    parser.add_argument("--browser",     choices=["edge", "chrome"], default="edge")
    parser.add_argument("--driver-path", default=None,
                        help="Path to msedgedriver.exe or chromedriver.exe")
    parser.add_argument("--delay",       type=float, default=2.0,
                        help="Seconds to wait between downloads (default: 2.0)")
    parser.add_argument("--timeout",     type=int,   default=60,
                        help="Seconds to wait for each download (default: 60)")
    parser.add_argument("--limit",       type=int,   default=None,
                        help="Only download the first N bids (useful for testing)")
    args = parser.parse_args()
    # Load bids JSON
    if not os.path.isfile(args.input):
        print(f"[!] Input file not found: {args.input}")
        sys.exit(1)
    with open(args.input, encoding="utf-8") as f:
        bids = json.load(f)
    print(f"[+] Loaded {len(bids)} bids from {args.input}")
    if args.limit:
        bids = bids[:args.limit]
        print(f"[+] Limited to first {args.limit} bids")
    # Place bids_pdf next to the script by default
    out_dir = args.out_dir
    if not os.path.isabs(out_dir):
        out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), out_dir)
    download_all(
        bids        = bids,
        out_dir     = out_dir,
        browser     = args.browser,
        driver_path = args.driver_path,
        delay       = args.delay,
        timeout     = args.timeout,
    )
if __name__ == "__main__":
    main()