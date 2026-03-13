## Yad2 Real Estate Scraper

This project implements an end‑to‑end data collection pipeline that:

- Scrapes Yad2 real estate **sale** listings in the **Center & Sharon** region.
- Applies the required filters (price, floor, size, condition).
- Visits a configurable number of search result pages (default **4**).
- Opens each listing to extract detailed data.
- Enriches listings with **geocoding** (Nominatim / OpenStreetMap).
- Computes **driving routes** to:
  - Tel Aviv Savidor Center station
  - Beer Sheva Center station
- Downloads all listing images.
- Exports:
  - `output/listings_full.csv`
  - `output/run_summary.json`
  - `output/images/{listing_id}/...`
  - `output/debug/`
  - `output/logs/`

### 1. Create and activate virtual environment

Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
```

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Upgrade pip

```bash
python -m pip install --upgrade pip
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Install Playwright browsers

```bash
python -m playwright install
```

### 5. Environment variables

Create a `.env` file in the project root:

```bash
ORS_API_KEY=your_openrouteservice_api_key
GEOCODING_EMAIL=your_email_for_nominatim_header
```

- **`ORS_API_KEY`**: Free key from OpenRouteService.
- **`GEOCODING_EMAIL`**: Used in Nominatim headers as a contact.

### 6. How to run

After you have run the setup script once (`setup_yad2_scraper_macos.sh` on macOS,
or `setup_yad2_scraper_windows.ps1` on Windows), the typical run flow is:

- **macOS (example using your preferred output folder and areas)**:

  ```bash
  cd /Users/nircko/GIT/web_agent
  source .venv/bin/activate
  python yad2_pipeline.py \
    --output-dir "/Users/nircko/DATA/projects/yad2_results" \
    --max-pages 2 \
    --captcha-avoidance-min 0 \
    --headless 0 \
    --areas "Ramat HaSharon & Herzliya Area,Rishon LeZion Area, Netanya Area"
  ```

- **Windows (PowerShell, analogous example)**:

  ```powershell
  cd C:\path\to\web_agent
  .\.venv\Scripts\Activate.ps1
  python yad2_pipeline.py `
    --output-dir ".\output" `
    --max-pages 2 `
    --captcha-avoidance-min 0 `
    --headless 1 `
    --areas "Rishon LeZion Area, Netanya Area"
  ```

The script will:

- Visit `--max-pages` search result pages **per area** (default 4 pages for each area in `--areas`, or for the whole big area if `--areas` is omitted).
- Scrape and enrich all listings.
- Persist progress after each listing.
- Write logs to `output/logs/`.
- Save debug artifacts for partial failures to `output/debug/`.

You can control browser visibility with:

- `--headless 1` (default): run Chromium **without** a visible window (faster, better for automated runs).
- `--headless 0`: run Chromium **with** a visible window, which is useful for **debugging** and for **manually solving captchas** when they appear.

### 7. Outputs

- **CSV**: `output/listings_full.csv`
- **Run summary**: `output/run_summary.json`
- **Images**: `output/images/{listing_id}/001.jpg`, `002.jpg`, ...
- **Debug**: `output/debug/`
- **Logs**: `output/logs/`

For common problems and fixes, see the dedicated troubleshooting guide:

- `TROUBLESHOOTING.md`

### 9. Building a standalone Windows EXE (advanced)

If you want a single `.exe` file that includes Python and all dependencies for easier distribution on Windows:

- **Prerequisites** (on a Windows machine):
  - Run `setup_yad2_scraper_windows.ps1` at least once (this creates `.venv` with Python 3.12 and installs dependencies).
- **Build steps**:
  - In PowerShell, from the project root:
    ```powershell
    .\.venv\Scripts\Activate.ps1
    .\build_windows_exe.ps1
    ```
  - This will create `dist\yad2_scraper.exe`.
- **To run on another Windows machine**, copy:
  - `dist\yad2_scraper.exe`
  - The `assets` folder (for area/city ID mappings)
  - Optionally `config` and `.env` if you use routing/geocoding.

Playwright still needs its browser binaries available on the target machine. On first run, if you encounter Playwright errors, see `TROUBLESHOOTING.md` for instructions.

