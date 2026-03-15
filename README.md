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

### 1. Easy installation (recommended)

The simplest way to install everything is to use the provided setup scripts.
They will:

- Install Python 3.12 (when possible).
- Create a `.venv` virtual environment.
- Install all required Python packages.
- Install Playwright browsers.
- Create a `.env` file with your API keys.

**Windows:**

1. In File Explorer, open the `scripts\` folder inside `web_agent`.
2. Double‑click `setup_yad2_scraper_windows.bat`  
   **or** open PowerShell in the project root (`web_agent`) and run:

   ```powershell
   .\scripts\setup_yad2_scraper_windows.bat
   ```

**macOS / Linux:**

1. Open Terminal in the project root (`web_agent`).
2. Make the script executable once:

   ```bash
   chmod +x scripts/setup_yad2_scraper_macos.sh
   ```

3. Run:

   ```bash
   ./scripts/setup_yad2_scraper_macos.sh
   ```

These scripts are **idempotent** – you can re-run them if something goes wrong.

### 2. Environment variables

Create a `.env` file in the project root:

```bash
ORS_API_KEY=your_openrouteservice_api_key
GEOCODING_EMAIL=your_email_for_nominatim_header
```

- **`ORS_API_KEY`**: Free key from OpenRouteService.
- **`GEOCODING_EMAIL`**: Used in Nominatim headers as a contact.

### 3. How to run

After the setup script has completed successfully, use one of the options below. The pipeline prints a **colored summary** of your input filters and search plan (e.g. when the search is split by district) before starting.

#### Option A: Runner scripts (one-click)

**macOS:**

1. Open **Terminal** and go to the project folder:
   ```bash
   cd /path/to/web_agent
   ```
2. First time only, make the script executable:
   ```bash
   chmod +x scripts/run_yad2_macos.sh
   ```
3. Run:
   ```bash
   ./scripts/run_yad2_macos.sh
   ```

**Windows:**

1. Open **File Explorer** and go to the project folder (e.g. `C:\Users\YourName\Documents\web_agent`).
2. Open the `scripts` folder and **double‑click** `run_yad2_windows.bat`  
   **or** open **PowerShell** in the project folder and run:
   ```powershell
   .\scripts\run_yad2_windows.bat
   ```
3. The script will ask for output folder, number of pages, headless/visible browser, and areas. Press Enter to accept defaults.

The runner uses the `.venv` from setup and writes results to `./output` (or the folder you chose).

#### Option B: Run the pipeline directly (Windows / Mac)

From the project root, activate the virtual environment, then run `yad2_pipeline.py`.

**macOS / Linux:**

```bash
cd /path/to/web_agent
source .venv/bin/activate
python yad2_pipeline.py
```

**Windows (PowerShell or Command Prompt):**

```powershell
cd C:\path\to\web_agent
.\.venv\Scripts\Activate.ps1
python yad2_pipeline.py
```

Or in **Command Prompt**:

```cmd
cd C:\path\to\web_agent
.venv\Scripts\activate.bat
python yad2_pipeline.py
```

Examples with options:

```bash
# Visible browser (e.g. to solve captchas)
python yad2_pipeline.py --headless 0

# Custom output folder and more pages
python yad2_pipeline.py --output-dir my_output --max-pages 6

# Specific areas (overrides scraper_preferences.json)
python yad2_pipeline.py --locations "Netanya, Rishon LeZion"
```

On Windows, use double quotes for arguments with spaces:

```powershell
python yad2_pipeline.py --output-dir "C:\Users\YourName\Documents\yad2_output" --locations "Ramat Gan, Netanya"
```

**All CLI options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--output-dir` | `output` | Root folder for CSV, images, debug, logs. |
| `--max-pages` | `4` | Number of search result pages to visit per area. |
| `--captcha-avoidance-min` | `0` | Minutes to sleep between pages to reduce captcha risk. |
| `--headless` | `1` | `1` = no browser window (default); `0` = visible window (for debugging and solving captchas manually). |
| `--locations` | *(none)* | City/area to search (unified for Yad2 and Madlan). English or legacy names, comma-separated (e.g. `'Haifa'`, `'Haifa, Rehovot'`, `'Rishon LeZion Area'`). Resolved via `assets/unified_location_names.json`; unknown tokens are also matched against **`assets/yad2_area_IDs.json`** area names (e.g. `'Haifa Area'` or `'Haifa_Area'`). If omitted, uses areas/cities from preferences. |

The pipeline reads search and filter settings from **`scraper_preferences.json`** in the project root (see Preferences below). It visits the configured pages per area, scrapes and enriches listings, persists progress after each listing, and writes logs to `output/logs/` and debug artifacts to `output/debug/`.

### 4. Summary PowerPoint

The pipeline saves **debug PNG and HTML only for listings that pass all filters** and are written to `listings_full.csv`. You can then generate a summary PowerPoint from an output directory.

**Generate the summary deck:**

```bash
# From project root (Mac/Linux)
source .venv/bin/activate
python scripts/build_summary_pptx.py --output-dir output
```

**Windows (PowerShell):**

```powershell
.\.venv\Scripts\Activate.ps1
python scripts/build_summary_pptx.py --output-dir output
```

Optional: `--out-pptx path/to/summary.pptx` (default: `<output-dir>/summary_listings.pptx`).

**Each slide contains:**

- **Title:** city + address + price  
- **Subtitle:** original listing URL  
- **Right:** debug screenshot (listing page PNG)  
- **Left upper:** listing images + description text  
- **Left bottom:** floor, parking, transportation (drive times), property status  

Requires `listings_full.csv`, and optionally `output/debug/` (PNG per exported listing) and `output/images/<listing_id>/` (downloaded images).

### 5. Preferences (`scraper_preferences.json`)

The scraper loads preferences from **`scraper_preferences.json`** in the project root. You can also use `config/filter_preferences.json` (nested format); the loader falls back to it if the root file is missing.

**User-friendly format (root file):**

- **default_region** — Used only when **areas** and **cities** are both empty. If you set areas or cities, district is deduced from those lists and this value is ignored.
- **listing_type** — e.g. `"forsale"`.
- **areas** — Optional list of area names (see `assets/yad2_area_IDs.json`). Each must belong to one district.
- **cities** — Optional list of city names. At most 3 per district.
- **price_min**, **price_max** — ILS.
- **max_floor**, **min_square_meters**, **property_condition** — URL filters.
- **last_publication_month** — Drop listings older than this many months (e.g. 1 = only last month).
- **max_building_floors** — Skip listings in buildings with more floors than this.
- **exclude_cities** — City names to exclude after parsing.
- **exclude_neighborhoods** — Neighborhood names to exclude (used by Madlan pipeline; can be added to Yad2 post-filters later).
- **private_only** — If `true`, only private (non‑agency) listings are exported. The scraper skips cards that show "תיווך"/"מתווך" on the search page and skips persisting any listing whose seller type is broker after opening the page. Set to `true` if you were seeing only real estate agencies (״תיווך״/״מתווך״) and want פרטי (private) publishers only.

**Why were all results from agencies?** By default the scraper does not filter by seller type; Yad2 often shows agency listings first. Enable **private_only** in `scraper_preferences.json` to export only private (non‑broker) listings.

CLI `--locations` overrides the areas/cities from this file. Exclude lists can also be set in `config/yad2_config.json` (merged).

#### Madlan (madlan.co.il) scraper

A separate pipeline scrapes **Madlan** with the same output shape (CSV, images, debug, fixed Hebrew XLSX). It uses the **`madlan`** section in `scraper_preferences.json` or a standalone **`madlan_preferences.json`**.

**Run Madlan:**

```bash
python madlan_pipeline.py --output-dir output_madlan --max-pages 4 --headless 1
```

**Madlan preferences** (under `madlan` or in `madlan_preferences.json`):

- **locations** — List of location names (e.g. `["חיפה"]` or `["חיפה", "רחובות"]`). Mapped to URL slugs via `assets/madlan_config.json`.
- **price_min**, **price_max**, **rooms_min**, **rooms_max**, **max_floor**, **min_square_meters** — Same meaning as URL filters (price 1.9M–2.5M, 4–6 rooms, etc.).
- **property_condition** — e.g. `["toRenovated", "preserved"]` (משופצת, שמורה).
- **private_only_madlan** (boolean) — Same idea as Yad2’s **private_only**: `true` = only private sellers (URL filter `_private_`), `false` = both private and agency (no seller filter). Backward compatible with legacy **seller_type** (`"private"` / `"agency"`).
- **trust_url_seller_filter** (default `true`) — If true, the search page does not skip cards by broker heuristics; the URL filter already restricts private vs agency.
- **use_israel_bbox** + **bbox** — Set `use_israel_bbox: true` and optionally `bbox: [west, south, east, north]` for map-style country search: `/for-sale/ישראל?bbox=...&filters=...` (same filters; see [example](https://www.madlan.co.il/for-sale/%D7%99%D7%A9%D7%A8%D7%90%D7%9C?bbox=33.29348%2C29.48782%2C36.86953%2C33.33522&filters=...)).
- **exclude_cities** — Cities to skip (extra effort on avoid lists).
- **exclude_neighborhoods** — Neighborhoods to skip (e.g. `["כרמליה", "הדר"]`).

The Madlan URL filter string is built from these (see [Madlan search URL](https://www.madlan.co.il/for-sale/חיפה-ישראל?filters=...)). You can add cities/areas in the path (e.g. `חיפה-ישראל,אזור-דרום-ישראל,רחובות-ישראל`). Listing pages enrich **`property_technical_profile_en`** (and related CSV columns) from `window.__SSR_HYDRATED_CONTEXT__` (e.g. `addressSearch.poi`: year/floor), schema.org `additionalProperty`, breadcrumbs / `assumedDesignRange`, and description keywords (transit / nuisances). Shared parsing lives in `listing_extract_common.py`; Yad2 reuses `parse_float` / `parse_int` from the same module. The summary PowerPoint and `fixed_hebrew_file.xlsx` work the same on `output_madlan/` as on `output/`.

### 6. Outputs

- **CSV**: `output/listings_full.csv`
- **Run summary**: `output/run_summary.json`
- **Images**: `output/images/{listing_id}/001.jpg`, `002.jpg`, ...
- **Debug**: `output/debug/` — PNG and HTML only for **exported** (post-filter) listings, for use with the summary PowerPoint.
- **Logs**: `output/logs/`

For common problems and fixes, see the dedicated troubleshooting guide:

- `TROUBLESHOOTING.md`

### 7. Building a standalone Windows EXE (advanced)

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

**Ready-for-Windows bundle:** The `ready_for_windows/` folder is a self-contained bundle you can copy to another Windows machine. After building the EXE (steps above), copy `dist\yad2_scraper.exe`, the `assets\` folder, optionally `config\` and `.env`, and the `.playwright\` folder (from project root after `python -m playwright install chromium`) into `ready_for_windows/`. Then zip or copy that folder. On the target PC, the user double-clicks `run_scraper.bat` and answers prompts (output path, pages, headless, areas). Results go to the chosen output folder (e.g. `ready_for_windows\output\`). For problems, see `TROUBLESHOOTING.md`.

