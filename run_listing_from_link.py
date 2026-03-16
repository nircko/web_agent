#!/usr/bin/env python3
"""
Standalone script to fetch a single listing by URL, detect Yad2 vs Madlan,
extract fields, and output a pretty log plus one CSV line (Excel-paste ready).

Usage:
  CLI:  python run_listing_from_link.py "https://www.yad2.co.il/item/..."
  CLI:  python run_listing_from_link.py "https://www.madlan.co.il/listings/..."
  Jupyter:  from run_listing_from_link import run_listing; run_listing("https://...")
"""

from __future__ import annotations

import argparse
import csv
import io
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Project root for imports (so we can import the packaged modules)
_project_root = Path(__file__).resolve().parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from playwright.sync_api import sync_playwright

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

# -----------------------------------------------------------------------------
# URL detection and listing ID extraction
# -----------------------------------------------------------------------------

def detect_source(url: str) -> Optional[str]:
    """Return 'yad2', 'madlan', or None if unknown."""
    u = (url or "").strip().lower()
    if "yad2.co.il" in u:
        return "yad2"
    if "madlan.co.il" in u:
        return "madlan"
    return None


def extract_listing_id(url: str, source: str) -> Optional[str]:
    """Extract listing ID from URL for the given source."""
    if source == "yad2":
        m = re.search(r"/(\d+)$", url.split("?")[0])
        if m:
            return m.group(1)
        m = re.search(r"itemId=(\d+)", url)
        if m:
            return m.group(1)
    elif source == "madlan":
        m = re.search(r"/listings/([a-zA-Z0-9_-]+)", url)
        if m:
            return m.group(1)
    return None


def normalize_listing_url(url: str, source: str) -> str:
    """Ensure URL has scheme and is canonical."""
    u = (url or "").strip()
    if not u:
        return u
    if not u.startswith("http"):
        u = "https://" + u
    if source == "yad2" and "yad2.co.il" not in u:
        return u
    if source == "madlan" and "madlan.co.il" not in u:
        return u
    return u


# -----------------------------------------------------------------------------
# Run extraction and format output
# -----------------------------------------------------------------------------

def _record_to_csv_line(record: Any) -> Tuple[str, str]:
    """Turn a ListingRecord into (header_line, data_line) using same format as pipeline CSV (QUOTE_NONNUMERIC)."""
    d = record.model_dump()
    keys = list(d.keys())
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_NONNUMERIC)
    w.writerow(keys)
    w.writerow([d[k] for k in keys])
    out = buf.getvalue().strip()
    lines = out.split("\n")
    return lines[0], lines[1] if len(lines) > 1 else ""


def _safe(v: Any) -> str:
    """Format value for display; None -> '—'."""
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v)


def _parse_last_update_from_extra(extra_features: Optional[str]) -> Optional[str]:
    """Extract last_update date from extra_features (e.g. '... | last_update:2024-01-15')."""
    if not extra_features:
        return None
    m = re.search(r"last_update:\s*([^\s|]+)", extra_features)
    return m.group(1).strip() if m else None


def _format_value(record: Any, key: str, raw: Any) -> str:
    """Format a single field value for pretty-print (with optional highlighting)."""
    if raw is None or raw == "":
        return "[dim]—[/]"
    if isinstance(raw, bool):
        return "[green]Yes[/]" if raw else "[dim]No[/]"
    if key == "price_ils" and isinstance(raw, (int, float)):
        return f"[bold green]{int(raw):,} ₪[/]".replace(",", " ")
    if key == "price_per_sqm" and isinstance(raw, (int, float)):
        return f"[green]{int(raw):,} ₪/m²[/]".replace(",", " ")
    if key in ("seller_phone_raw", "seller_phone_normalized") and raw:
        return f"[bold green]{raw}[/]"
    if key in ("publication_date_iso", "publication_date_raw") and raw:
        return f"[bold yellow]{raw}[/]"
    if key == "_last_update" and raw:
        return f"[bold yellow]{raw}[/]"
    if key == "original_listing_url":
        return f"[link={raw}][dim]{raw}[/][/link]" if raw else "[dim]—[/]"
    if key in ("description_raw", "description_clean", "property_technical_profile_en", "extra_features"):
        s = str(raw)
        return (s[:300] + "…") if len(s) > 300 else s
    if isinstance(raw, float) and raw == int(raw):
        return str(int(raw))
    return str(raw)


# Sections: (panel_title, border_style, list of (field_key, human_label))
_FIELD_SECTIONS = (
    (
        "Identity & source",
        "cyan",
        [
            ("yad2_listing_id", "Listing ID"),
            ("original_listing_url", "URL"),
            ("search_page_number", "Search page #"),
            ("scrape_timestamp_utc", "Scraped at (UTC)"),
        ],
    ),
    (
        "Property",
        "blue",
        [
            ("title", "Title"),
            ("property_type", "Property type"),
            ("transaction_type", "Transaction"),
            ("price_ils", "Price (ILS)"),
            ("currency", "Currency"),
            ("rooms", "Rooms"),
            ("floor_current", "Floor (current)"),
            ("floor_total", "Floor (total)"),
            ("built_sqm", "Built (m²)"),
            ("lot_sqm", "Lot (m²)"),
            ("price_per_sqm", "Price per m²"),
            ("property_condition_label", "Condition"),
            ("property_condition_index", "Condition index"),
            ("year_built", "Year built"),
            ("assumed_design_range", "Design range"),
            ("balcony_count", "Balconies"),
            ("parking_count", "Parking"),
            ("elevator", "Elevator"),
            ("mamad", "Mamad (safe room)"),
            ("storage", "Storage"),
            ("air_conditioning", "Air conditioning"),
            ("solar_water_heater", "Solar water heater"),
            ("window_bars", "Window bars"),
            ("extra_features", "Extra features"),
        ],
    ),
    (
        "Location",
        "magenta",
        [
            ("full_address_best", "Full address"),
            ("street_name", "Street"),
            ("house_number", "House number"),
            ("neighborhood", "Neighborhood"),
            ("city", "City"),
            ("region", "Region"),
            ("address_confidence", "Address confidence"),
            ("latitude", "Latitude"),
            ("longitude", "Longitude"),
            ("geocode_status", "Geocode status"),
        ],
    ),
    (
        "Seller & publication",
        "yellow",
        [
            ("publication_date_iso", "First published date"),
            ("_last_update", "Last update date"),
            ("entry_date", "Entry date"),
            ("seller_name", "Seller name"),
            ("seller_type", "Seller type"),
            ("seller_phone_normalized", "Phone"),
            ("phone_found", "Phone found"),
            ("phone_extraction_method", "Phone source"),
        ],
    ),
    (
        "Description & notes",
        "dim",
        [
            ("description_clean", "Description"),
            ("investment_transit_notes", "Transit notes"),
            ("investment_nuisance_notes", "Nuisance notes"),
            ("property_technical_profile_en", "Technical profile"),
        ],
    ),
    (
        "Routing",
        "green",
        [
            ("drive_to_tel_aviv_savidor_duration_min", "Drive to TLV Savidor (min)"),
            ("drive_to_tel_aviv_savidor_distance_km", "Drive to TLV Savidor (km)"),
            ("drive_to_beer_sheva_center_duration_min", "Drive to Beer Sheva (min)"),
            ("drive_to_beer_sheva_center_distance_km", "Drive to Beer Sheva (km)"),
        ],
    ),
    (
        "Images & meta",
        "dim",
        [
            ("image_count_detected", "Images detected"),
            ("image_count_downloaded", "Images downloaded"),
            ("primary_image_url", "Primary image URL"),
            ("image_folder_path", "Image folder"),
            ("image_file_names", "Image files"),
            ("property_summary", "Summary"),
            ("commute_assessment", "Commute assessment"),
            ("likely_fit_for_tel_aviv_commuter", "TLV commuter fit"),
            ("likely_fit_for_beer_sheva_commuter", "Beer Sheva commuter fit"),
            ("extraction_confidence_score", "Extraction confidence"),
            ("parsing_notes", "Parsing notes"),
        ],
    ),
    (
        "Debug / failure",
        "red",
        [
            ("missing_reason_code", "Missing reason"),
            ("extraction_notes", "Extraction notes"),
        ],
    ),
)


def _pretty_print_rich(record: Any, source: str, csv_line: Optional[str] = None) -> None:
    """Pretty-print listing: human-readable formatted summary (every field with its value). No CSV here; use --csv for Excel paste."""
    if not RICH_AVAILABLE:
        _pretty_log_plain(record, source)
        return
    console = Console()
    source_label = "Madlan" if source == "madlan" else "Yad2"
    title = f"[bold cyan]📋 Listing[/] [bold white]{record.yad2_listing_id}[/] [dim]({source_label})[/]"
    console.print(Panel(title, border_style="cyan", box=box.DOUBLE))
    console.print()

    d = record.model_dump()
    label_width = 32

    for section_title, border_style, fields in _FIELD_SECTIONS:
        rows = []
        for key, label in fields:
            if key == "_last_update":
                raw = _parse_last_update_from_extra(d.get("extra_features"))
            else:
                raw = d.get(key)
            val = _format_value(record, key, raw)
            rows.append((label, val))
        if not rows:
            continue
        table = Table(
            show_header=True,
            header_style="bold",
            box=box.ROUNDED,
            border_style=border_style,
            padding=(0, 2),
            expand=False,
        )
        table.add_column("Field", style="cyan", width=label_width, no_wrap=False)
        table.add_column("Value", style="white", overflow="fold")
        for label, val in rows:
            if label in ("First published date", "Last update date"):
                label = f"[bold]{label}[/]"
            table.add_row(label, val)
        console.print(Panel(table, title=f"[bold] {section_title} [/]", border_style=border_style, box=box.ROUNDED))
        console.print()

    console.print("[dim]Tip: use [cyan]--csv[/] to get a single line ready to paste as a new row in Excel.[/]")


def _pretty_log_plain(record: Any, source: str) -> None:
    """Fallback plain log when Rich is not available."""
    log = logging.getLogger(__name__)
    label = "EXPORTED LISTING (Madlan)" if source == "madlan" else "EXPORTED LISTING"
    log.info(
        "\n==================== %s ====================\n"
        "ID: %s | URL: %s\n"
        "City: %r | Street: %r | Rooms: %s | m²: %s | Floor: %s/%s\n"
        "Price: %s | Published: %s | Seller: %s | Phone: %s\n"
        "================================================================",
        label,
        record.yad2_listing_id,
        record.original_listing_url,
        getattr(record, "city", None),
        getattr(record, "street_name", None),
        getattr(record, "rooms", None),
        getattr(record, "built_sqm", None),
        getattr(record, "floor_current", None),
        getattr(record, "floor_total", None),
        getattr(record, "price_ils", None),
        getattr(record, "publication_date_iso", None) or getattr(record, "publication_date_raw", None),
        getattr(record, "seller_name", None),
        getattr(record, "seller_phone_normalized", None) or getattr(record, "seller_phone_raw", None),
    )


def run_listing(
    url: str,
    *,
    headless: bool = False,
    captcha_wait_seconds: int = 60,
    csv_only: bool = False,
) -> Dict[str, Any]:
    """
    Fetch a single listing by URL, detect Yad2 vs Madlan, extract and return result.

    When csv_only=False (default): pretty-prints the listing with Rich (color panels/tables).
    When csv_only=True: no pretty print; caller should print result["csv_line"] for Excel paste.

    Returns dict with keys: source, listing_id, record, csv_header, csv_line, error.
    In Jupyter: result = run_listing("https://..."); print(result["csv_line"])  # if you want only CSV
    """
    result = {
        "source": None,
        "listing_id": None,
        "record": None,
        "csv_header": None,
        "csv_line": None,
        "error": None,
    }
    url = (url or "").strip()
    if not url:
        result["error"] = "No URL provided"
        return result

    source = detect_source(url)
    if not source:
        result["error"] = "Unknown source: URL must be yad2.co.il or madlan.co.il"
        return result

    url = normalize_listing_url(url, source)
    listing_id = extract_listing_id(url, source)
    if not listing_id:
        listing_id = f"urlhash_{abs(hash(url))}"

    result["source"] = source
    result["listing_id"] = listing_id

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        try:
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)

            # Optional: wait for captcha (same pattern as pipelines)
            try:
                title = page.title() or ""
                for _ in range(120):
                    if "ShieldSquare" not in title and "Captcha" not in title:
                        break
                    if "madlan" in url.lower() and "ההפרעה" in (page.content() or ""):
                        break
                    page.wait_for_timeout(1000)
                    title = page.title() or ""
                # If still captcha and not headless, one prompt
                if not headless and ("ShieldSquare" in title or "Captcha" in title):
                    logging.getLogger(__name__).info(
                        "Captcha may be visible. You have %s seconds to solve it. Press Enter when done.",
                        captcha_wait_seconds,
                    )
                    page.wait_for_timeout(min(captcha_wait_seconds, 30) * 1000)
            except Exception:
                pass

            page.wait_for_timeout(2000)
            filtered_search_url = url
            search_page_number = 1
            now_iso = datetime.now(timezone.utc).isoformat()

            if source == "yad2":
                from yad2_pipeline import Yad2Scraper, Geocoder, ListingRecord
                from dotenv import load_dotenv
                import os
                load_dotenv()
                email = os.environ.get("NOMINATIM_EMAIL") or os.environ.get("EMAIL") or "listing-preview@local"
                geocoder = Geocoder(email=email)
                output_dir = _project_root / "output_single_listing"
                output_dir.mkdir(parents=True, exist_ok=True)
                scraper = Yad2Scraper(
                    output_dir=output_dir,
                    geocoder=geocoder,
                    route_calculator=None,
                    max_pages=1,
                    headless=headless,
                )
                record = scraper._extract_from_listing_page(
                    page,
                    listing_id=listing_id,
                    original_url=url,
                    filtered_search_url=filtered_search_url,
                    search_page_number=search_page_number,
                )
            else:
                from madlan_pipeline import MadlanScraper, ListingRecord
                from yad2_pipeline import Geocoder
                from dotenv import load_dotenv
                import os
                load_dotenv()
                email = os.environ.get("NOMINATIM_EMAIL") or os.environ.get("EMAIL") or "listing-preview@local"
                geocoder = Geocoder(email=email)
                output_dir = _project_root / "output_single_listing"
                output_dir.mkdir(parents=True, exist_ok=True)
                scraper = MadlanScraper(
                    output_dir=output_dir,
                    geocoder=geocoder,
                    route_calculator=None,
                    max_pages=1,
                    headless=headless,
                )
                record = scraper._extract_from_listing_page(
                    page,
                    listing_id=listing_id,
                    original_url=url,
                    filtered_search_url=filtered_search_url,
                    search_page_number=search_page_number,
                )

            result["record"] = record
            csv_header, csv_line = _record_to_csv_line(record)
            result["csv_header"] = csv_header
            result["csv_line"] = csv_line
            if not csv_only:
                _pretty_print_rich(record, source, csv_line=csv_line)
            return result

        except Exception as e:
            result["error"] = str(e)
            logging.getLogger(__name__).exception("Extraction failed")
            return result
        finally:
            browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch one Yad2 or Madlan listing by URL. Pretty-print with colors, or output only CSV with --csv."
    )
    parser.add_argument("url", help="Listing URL (yad2.co.il or madlan.co.il)")
    parser.add_argument("--headless", action="store_true", help="Run browser headless (captcha cannot be solved)")
    parser.add_argument("--captcha-wait", type=int, default=60, help="Seconds to wait for captcha solve (default 60)")
    parser.add_argument("--csv", "--csv-only", dest="csv_only", action="store_true",
                        help="Print only the CSV data line (for piping / Excel paste); no pretty-print")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )

    out = run_listing(
        args.url,
        headless=args.headless,
        captcha_wait_seconds=args.captcha_wait,
        csv_only=args.csv_only,
    )

    if out.get("error"):
        print(out["error"], file=sys.stderr)
        sys.exit(1)

    if args.csv_only:
        print(out["csv_line"])


if __name__ == "__main__":
    main()
