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

After the setup script has completed successfully, you only need **one command per OS**.

#### Option A: Runner scripts (simple)

**macOS / Linux:**

```bash
cd /path/to/web_agent
chmod +x scripts/run_yad2_macos.sh   # first time only
./scripts/run_yad2_macos.sh
```

**Windows:** Open the `scripts\` folder and double‑click `run_yad2_windows.bat`, or from PowerShell:

```powershell
cd C:\path\to\web_agent
.\scripts\run_yad2_windows.bat
```

The runner uses the `.venv` from setup and writes results to `./output`.

#### Option B: Run `yad2_pipeline.py` directly

From the project root, with the virtual environment activated:

```bash
# Activate venv (macOS/Linux)
source .venv/bin/activate

# Run with defaults (output to ./output, 4 pages, headless)
python yad2_pipeline.py
```

**All CLI options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--output-dir` | `output` | Root folder for CSV, images, debug, logs. |
| `--max-pages` | `4` | Number of search result pages to visit per area. |
| `--captcha-avoidance-min` | `0` | Minutes to sleep between pages to reduce captcha risk. |
| `--headless` | `1` | `1` = no browser window (default); `0` = visible window (for debugging and solving captchas manually). |
| `--areas` | *(none)* | Comma-separated Yad2 area names (e.g. `'Rishon LeZion Area, Netanya Area'`). Overrides areas from preferences. If omitted, uses preferences or the default region. |

**Examples:**

```bash
# Visible browser (e.g. to solve captchas)
python yad2_pipeline.py --headless 0

# Custom output folder and more pages
python yad2_pipeline.py --output-dir my_output --max-pages 6

# Specific areas (overrides scraper_preferences.json)
python yad2_pipeline.py --areas "Netanya Area, Rishon LeZion Area"

# Delay between pages to reduce captcha risk
python yad2_pipeline.py --captcha-avoidance-min 1.5
```

The pipeline reads search and filter settings from **`scraper_preferences.json`** in the project root (see Preferences below). It visits the configured pages per area, scrapes and enriches listings, persists progress after each listing, and writes logs to `output/logs/` and debug artifacts to `output/debug/`.

### 4. Preferences (`scraper_preferences.json`)

The scraper loads preferences from **`scraper_preferences.json`** in the project root. You can also use `config/filter_preferences.json` (nested format); the loader falls back to it if the root file is missing.

**User-friendly format (root file):**

- **default_region** — Used only when **areas** and **cities** are both empty. If you set areas or cities, district is deduced from those lists and this value is ignored.
- **listing_type** — e.g. `"forsale"`.
- **areas** — Optional list of area names (see `assets/yad2_area_IDs.json`). Each must belong to one district.
- **cities** — Optional list of city names. At most 3 per district.
- **price_min**, **price_max** — ILS.
- **max_floor**, **min_square_meters**, **property_condition** — URL filters.
- **publication_max_months** — Drop listings older than this many months.
- **max_building_floors** — Skip listings in buildings with more floors than this.
- **exclude_cities** — City names to exclude after parsing.

CLI `--areas` overrides the areas from this file. Exclude lists can also be set in `config/yad2_config.json` (merged).

### 5. Outputs

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

