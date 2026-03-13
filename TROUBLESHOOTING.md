## Troubleshooting - Yad2 Real Estate Scraper

This guide collects common issues you may encounter when running the scraper and how to fix them.

### 1. Browser never appears / Playwright errors

- **Symptom**: You see errors mentioning Playwright, missing browsers, or nothing seems to happen.
- **Fix**:
  - Make sure you ran one of the setup scripts:
    - macOS / Linux: `./scripts/setup_yad2_scraper_macos.sh`
    - Windows: `scripts\setup_yad2_scraper_windows.bat` (double-click in Explorer, or run from PowerShell)
  - Or at minimum, install Playwright browsers:
    ```bash
    python -m playwright install
    ```

### 2. Headless vs visible browser

- **Symptom**: You expect a browser window to open, but no UI is visible.
- **Cause**: By default the scraper runs in **headless** mode (no visible window).
- **Fix**:
  - To run **with** a visible browser window (for debugging or captchas), pass:
    ```bash
    --headless 0
    ```
  - For unattended / automated runs, use:
    ```bash
    --headless 1
    ```

### 3. Captcha / ShieldSquare blocks

- **Symptom**: Instead of listings, the page shows a "ShieldSquare" or captcha screen.
- **Fix**:
  - Run with a visible browser:
    ```bash
    python yad2_pipeline.py ... --headless 0
    ```
  - When the captcha appears, solve it manually in the browser window; the scraper will continue once the real listings or listing page is visible.
  - Reduce pressure on Yad2:
    - Lower the number of pages:
      ```bash
      --max-pages 1
      ```
    - Add a delay between pages:
      ```bash
      --captcha-avoidance-min 1.5
      ```

### 4. Script opens unrelated regions (e.g. `/south/`)

- **Symptom**: Some logged URLs look like:
  - `https://www.yad2.co.il/realestate/item/south/...`
- **Cause**: Yad2 shows recommended properties from other regions on the same page.
- **Behavior**:
  - The scraper now **filters links** on the search page so that only URLs containing:
    - `"/realestate/item/center-and-sharon/"`
    are actually processed and exported.
- **How to verify**:
  - Check `output/logs/scraper.log` for blocks like:
    ```text
    ==================== EXPORTED LISTING ====================
    ...
    ```
  - Only listings printed there are written to `listings_full.csv`.

### 5. Too many old / stale listings

- **Symptom**: Many listings are opened and then skipped because the publication date is older than 3 months.
- **What the scraper does**:
  - **Card-level filter** on the search page:
    - Estimates recency from phrases like `"פורסם לפני X ימים/שבועות/חודשים"`.
    - Skips obviously old cards before opening them.
  - **Detail-page filter**:
    - Parses the exact publication date and drops anything older than 90 days.
- **How to reduce wasted work**:
  - Lower `--max-pages` (per area) so you stay close to the newest results.
  - Restrict `--areas` to only the regions you really care about.

### 6. Virtual environment / Python 3.12 issues

- **Symptom**: Import errors, missing packages, or wrong Python version.
- **Fix**:
  - Recommended:
    - macOS / Linux:
      ```bash
      ./scripts/setup_yad2_scraper_macos.sh
      ./scripts/run_yad2_macos.sh
      ```
    - Windows:
      - Double-click `scripts\setup_yad2_scraper_windows.bat`
      - Then double-click `scripts\run_yad2_windows.bat`
  - Advanced (manual venv use):
    - macOS / Linux:
      ```bash
      source .venv/bin/activate
      python yad2_pipeline.py ...
      ```
    - Windows (PowerShell):
      ```powershell
      .\.venv\Scripts\Activate.ps1
      python yad2_pipeline.py ...
      ```
  - The setup scripts ensure **Python 3.12** is installed and used for the venv.

### 7. No or partial data in `listings_full.csv`

- **Symptom**: CSV has fewer rows than expected, or some important fields are empty.
- **Checks**:
  - Open `output/run_summary.json` and look at:
    - `total_search_pages_visited`
    - `total_unique_listings_found`
    - `total_exported_rows`
    - `total_rows_with_missing_critical_fields`
  - Open `output/logs/scraper.log` and look for:
    - `EXPORTED LISTING` blocks (these are rows written to CSV).
    - Warnings/errors about critical fields or geocoding.
- **Common causes**:
  - Listings filtered out by:
    - 3‑month publication date rule.
    - `cities_to_skip` in `config/yad2_config.json`.
    - `floor_total > 7` rule.
  - Missing critical fields (recorded with `missing_reason_code` in the CSV).

### 8. Setup script problems

- **Symptom**: Setup script fails early (e.g. missing `brew`, `winget`, or no permissions).
- **Fix**:
  - macOS / Linux:
    - If Homebrew is missing and the script asks for it:
      - Install Homebrew: `https://brew.sh/`
      - Or install Python 3.12 directly from `https://www.python.org/downloads/`.
  - Windows:
    - If `winget` is not available:
      - Install Python 3.12 from `https://www.python.org/downloads/`.
  - After Python 3.12 is installed, you can run:
    ```bash
    python3.12 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    python -m playwright install
    ```

