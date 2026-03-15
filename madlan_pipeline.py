"""
Madlan (madlan.co.il) scraper pipeline.

Produces the same output shape as the Yad2 pipeline: listings_full.csv, run_summary.json,
images/{id}/, debug/ (PNG/HTML for exported listings only), fixed_hebrew_file.xlsx.

Supports exclude_cities and exclude_neighborhoods in preferences (extra effort on avoid lists).
"""

import csv
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Browser, Page

# Reuse models and helpers from Yad2 pipeline for compatible output
from yad2_pipeline import (
    ListingRecord,
    RunSummary,
    Geocoder,
    RouteCalculator,
    _fix_hebrew_encoding,
    _export_listings_to_formatted_excel,
    _classify_seller_type_from_text,
    _is_broker_card,
)
from listing_extract_common import (
    parse_float,
    parse_int,
    extract_ssr_hydrated_context,
    deep_find_poi_ssr,
    extract_assumed_design_range,
    extract_schema_org_real_estate_features,
    extract_breadcrumb_items,
    translate_condition_label,
    extract_investment_context_from_text,
    map_schema_boolean_to_amenities,
    build_technical_profile_en,
)
from madlan_url_builder import build_madlan_url_from_preferences, load_madlan_config
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box


def load_madlan_preferences(project_root: Optional[Path] = None) -> Dict[str, Any]:
    """Load Madlan preferences from scraper_preferences.json (madlan key) or madlan_preferences.json."""
    root = Path(project_root or __file__).resolve().parent
    # Try madlan section in scraper_preferences.json first
    prefs_path = root / "scraper_preferences.json"
    if prefs_path.exists():
        try:
            data = json.loads(prefs_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "madlan" in data:
                return dict(data["madlan"])
        except Exception:
            pass
    # Standalone file
    madlan_path = root / "madlan_preferences.json"
    if madlan_path.exists():
        try:
            return json.loads(madlan_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return _default_madlan_preferences()


def _default_madlan_preferences() -> Dict[str, Any]:
    return {
        "locations": ["חיפה"],
        "price_min": 1900000,
        "price_max": 2500000,
        "rooms_min": 4,
        "rooms_max": 6,
        "property_condition": ["toRenovated", "preserved"],
        "private_only_madlan": False,
        "max_floor": 4,
        "min_square_meters": 90,
        "publication_max_months": 3,
        "max_building_floors": 7,
        "exclude_cities": [],
        "exclude_neighborhoods": [],
        "private_only": False,
        "captcha_avoidance_min": 0.0,
        "trust_url_seller_filter": True,
        "use_israel_bbox": False,
        "bbox": [33.29348, 29.48782, 36.86953, 33.33522],
    }


class MadlanScraper:
    def __init__(
        self,
        output_dir: Path,
        geocoder: Geocoder,
        route_calculator: Optional[RouteCalculator],
        max_pages: int = 4,
        headless: bool = True,
        cities_to_skip: Optional[List[str]] = None,
        neighborhoods_to_skip: Optional[List[str]] = None,
        madlan_preferences: Optional[Dict[str, Any]] = None,
        export_slug: Optional[str] = None,
    ):
        self.output_dir = Path(output_dir)
        self.export_slug = (export_slug or "").strip() or None
        self.images_dir = self.output_dir / "images"
        self.debug_dir = self.output_dir / "debug"
        self.logs_dir = self.output_dir / "logs"
        self.output_csv = self.output_dir / "listings_full.csv"
        self.run_summary_path = self.output_dir / "run_summary.json"
        self.geocoder = geocoder
        self.route_calculator = route_calculator
        self.run_summary = RunSummary()
        self.session = requests.Session()

        prefs = madlan_preferences or load_madlan_preferences()
        self._prefs = prefs
        self.max_pages = max(1, int(max_pages))
        self.headless = bool(headless)

        # Exclude lists (extra effort: cities and neighborhoods to avoid)
        self.cities_to_skip: Set[str] = set()
        for c in (prefs.get("exclude_cities") or []) + (cities_to_skip or []):
            if c and str(c).strip():
                self.cities_to_skip.add(str(c).strip())

        self.neighborhoods_to_skip: Set[str] = set()
        for n in (prefs.get("exclude_neighborhoods") or []) + (neighborhoods_to_skip or []):
            if n and str(n).strip():
                self.neighborhoods_to_skip.add(str(n).strip())

        self.publication_cutoff_days = int((prefs.get("publication_max_months") or 3) * 30)
        self.max_floor_total = int(prefs.get("max_building_floors") or 7)
        if "private_only_madlan" in prefs:
            self.private_only_madlan = bool(prefs.get("private_only_madlan"))
        else:
            self.private_only_madlan = (prefs.get("seller_type") or "private") == "private"
        self.private_only = self.private_only_madlan
        self.trust_url_seller_filter = bool(prefs.get("trust_url_seller_filter", True))
        self.captcha_avoidance_min = max(0.0, float(prefs.get("captcha_avoidance_min", 0)))
        self.madlan_config = load_madlan_config()

        self._setup_dirs()
        self._setup_logging()
        self.seen_listing_ids: Set[str] = set()
        self.seen_listing_urls: Set[str] = set()

    def _setup_dirs(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def _setup_logging(self) -> None:
        log_file = self.logs_dir / "scraper.log"
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[
                logging.FileHandler(log_file, encoding="utf-8"),
                logging.StreamHandler(sys.stdout),
            ],
            force=True,
        )

    def build_search_url(self, page: int = 1) -> str:
        return build_madlan_url_from_preferences(
            self.madlan_config,
            locations=self._prefs.get("locations"),
            price_min=self._prefs.get("price_min"),
            price_max=self._prefs.get("price_max"),
            rooms_min=self._prefs.get("rooms_min"),
            rooms_max=self._prefs.get("rooms_max"),
            property_condition=self._prefs.get("property_condition"),
            max_floor=self._prefs.get("max_floor"),
            min_sqm=self._prefs.get("min_square_meters"),
            page=page if page > 1 else None,
            url_filters=self._prefs,
        )

    def _wait_for_captcha_solved(self, page: Page, context: str) -> None:
        """If the page shows ShieldSquare/captcha and we're not headless, wait for user to solve it (same as Yad2)."""
        while True:
            try:
                title = page.title() or ""
            except Exception:
                title = ""
            if "ShieldSquare" not in title and "Captcha" not in title:
                break
            if self.headless:
                logging.warning(
                    "Captcha/ShieldSquare detected on %s but running headless; "
                    "cannot wait for manual solve. Consider --headless 0.",
                    context,
                )
                break
            logging.info("Captcha/ShieldSquare detected on %s. Solve in browser, then press Enter.", context)
            input("Press Enter when the real page is visible to continue... ")
            page.wait_for_timeout(2000)
        return

    def _normalize_phone(self, raw: str) -> str:
        """Same as Yad2: digits only, 972 prefix."""
        digits = re.sub(r"\D+", "", raw or "")
        if digits.startswith("0"):
            digits = digits[1:]
        if digits and not digits.startswith("972"):
            digits = "972" + digits
        return digits

    def _print_run_plan(self) -> None:
        """Pretty-print Madlan filters and exclude lists (same style as Yad2 run plan)."""
        console = Console()
        t = Table(show_header=False, box=box.ROUNDED, border_style="dim")
        t.add_column(style="cyan", width=32)
        t.add_column(style="white")
        t.add_row("Locations", ", ".join(self._prefs.get("locations") or []))
        t.add_row("Price", f"{self._prefs.get('price_min')} – {self._prefs.get('price_max')} ILS")
        t.add_row("Rooms", f"{self._prefs.get('rooms_min')} – {self._prefs.get('rooms_max')}")
        t.add_row("Private only (Madlan)", str(self.private_only_madlan))
        t.add_row("Exclude cities", ", ".join(self.cities_to_skip) or "(none)")
        t.add_row("Exclude neighborhoods", ", ".join(self.neighborhoods_to_skip) or "(none)")
        t.add_row("Publication ≤ months", str(self._prefs.get("publication_max_months", 3)))
        t.add_row("Max building floors", str(self.max_floor_total))
        t.add_row("Private only (detail)", str(self.private_only))
        t.add_row("Trust URL seller filter", str(self.trust_url_seller_filter))
        console.print(Panel(t, title="[bold cyan] Madlan input filters [/]", border_style="cyan"))

    def _persist_run_summary(self) -> None:
        """Same as Yad2: write run_summary.json."""
        self.run_summary_path.write_text(
            json.dumps(self.run_summary.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def scrape(self) -> None:
        self._print_run_plan()
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            try:
                for page_number in range(1, self.max_pages + 1):
                    url = self.build_search_url(page=page_number)
                    self._process_search_page(browser, url, page_number)
                    if self.captcha_avoidance_min > 0 and page_number < self.max_pages:
                        delay_sec = self.captcha_avoidance_min * 60.0
                        logging.info(
                            "Sleeping %.1f min before next search page (captcha avoidance).",
                            self.captcha_avoidance_min,
                        )
                        time.sleep(delay_sec)
                logging.info("Finished processing all Madlan search pages.")
                self._export_fixed_hebrew_xlsx()
            finally:
                browser.close()

    def _extract_listing_id_from_url(self, url: str) -> Optional[str]:
        m = re.search(r"/listings/([a-zA-Z0-9_-]+)", url)
        return m.group(1) if m else None

    def _process_search_page(self, browser: Browser, url: str, page_number: int) -> None:
        logging.info("Processing Madlan search page %s: %s", page_number, url)
        page = browser.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=120000)
            page.wait_for_timeout(5000)
        except Exception as e:
            logging.error("Failed to load search page %s: %s", page_number, e)
            self._save_debug_artifacts(page, f"search_page_{page_number}", f"search_page_load_error: {e}")
            page.close()
            return

        self._wait_for_captcha_solved(page, f"search page {page_number}")
        self.run_summary.total_search_pages_visited += 1
        cards = page.query_selector_all("a[href*='/listings/']")
        self.run_summary.total_result_cards_found += len(cards)
        logging.info("Found %s listing cards on page %s", len(cards), page_number)

        listing_links: List[Tuple[str, str]] = []
        for card in cards:
            href = card.get_attribute("href") or ""
            if not href.startswith("http"):
                href = "https://www.madlan.co.il" + href
            if "/listings/" not in href:
                continue
            # Yad2-style card broker skip is redundant when Madlan URL already has ?_…_private_… in filters
            if self.private_only and not self.trust_url_seller_filter:
                try:
                    card_text = card.inner_text() or ""
                except Exception:
                    card_text = ""
                if _is_broker_card(card_text):
                    logging.debug("Skipping Madlan card (broker, private_only on search page)")
                    continue
            listing_id = self._extract_listing_id_from_url(href)
            if not listing_id:
                listing_id = f"urlhash_{abs(hash(href))}"
            if listing_id in self.seen_listing_ids or href in self.seen_listing_urls:
                continue
            self.seen_listing_ids.add(listing_id)
            self.seen_listing_urls.add(href)
            listing_links.append((listing_id, href))

        self.run_summary.total_unique_listings_found = len(self.seen_listing_ids)
        for listing_id, listing_url in listing_links:
            self._process_listing(browser, page_number, url, listing_id, listing_url)
        page.close()

    def _process_listing(
        self,
        browser: Browser,
        search_page_number: int,
        filtered_search_url: str,
        listing_id: str,
        listing_url: str,
    ) -> None:
        logging.info("Processing listing %s: %s", listing_id, listing_url)
        page = browser.new_page()
        try:
            self.run_summary.total_listings_opened += 1
            page.goto(listing_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
            self._wait_for_captcha_solved(page, f"listing {listing_id}")
            page.wait_for_timeout(2000)
            record = self._extract_from_listing_page(
                page, listing_id, listing_url, filtered_search_url, search_page_number
            )

            cutoff_date = (datetime.now(timezone.utc) - timedelta(days=self.publication_cutoff_days)).date()
            if record.publication_date_iso:
                try:
                    pub_date = datetime.strptime(record.publication_date_iso, "%Y-%m-%d").date()
                    if pub_date < cutoff_date:
                        self.run_summary.total_listings_filtered_by_date += 1
                        return
                except Exception:
                    pass

            if record.city and record.city.strip() in self.cities_to_skip:
                self.run_summary.total_listings_filtered_by_city += 1
                return

            if record.neighborhood and record.neighborhood.strip() in self.neighborhoods_to_skip:
                logging.info("Skipping listing %s: neighborhood %s in exclude list.", listing_id, record.neighborhood)
                self.run_summary.total_listings_filtered_by_neighborhood += 1
                return

            if record.floor_total is not None and record.floor_total > self.max_floor_total:
                self.run_summary.total_listings_filtered_by_floor += 1
                return

            if self.private_only and record.seller_type == "broker":
                logging.info("Skipping listing %s (broker, private_only=True).", listing_id)
                self.run_summary.total_listings_filtered_by_broker += 1
                return

            self._download_images(listing_id, page, record)
            self._validate_critical_fields(record, page)
            self._append_record_to_csv(record)
            self._persist_run_summary()
            self._save_debug_artifacts(page, listing_id, "exported")
        except Exception as e:
            logging.error("Failed to process listing %s: %s", listing_id, e, exc_info=True)
            self.run_summary.total_failed_rows += 1
            self._save_debug_artifacts(page, listing_id, f"exception: {e}")
        finally:
            page.close()

    def _extract_from_listing_page(
        self,
        page: Page,
        listing_id: str,
        original_url: str,
        filtered_search_url: str,
        search_page_number: int,
    ) -> ListingRecord:
        html = page.content()
        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text(" ", strip=True)

        now_iso = datetime.now(timezone.utc).isoformat()
        record = ListingRecord(
            yad2_listing_id=listing_id,
            original_listing_url=original_url,
            filtered_search_url=filtered_search_url,
            search_page_number=search_page_number,
            scrape_timestamp_utc=now_iso,
        )

        # --- SSR + schema.org (Madlan technical profile) ---
        ssr = extract_ssr_hydrated_context(html) or {}
        poi = deep_find_poi_ssr(ssr) if ssr else {}
        if poi.get("buildingYear") is not None:
            try:
                record.year_built = int(float(poi["buildingYear"]))
            except (TypeError, ValueError):
                pass
        if poi.get("floor") is not None and record.floor_current is None:
            try:
                record.floor_current = int(float(poi["floor"]))
            except (TypeError, ValueError):
                pass
        for k in ("totalFloors", "floorsInBuilding", "buildingFloors", "maxFloor"):
            if poi.get(k) is not None:
                try:
                    record.floor_total = int(float(poi[k]))
                    break
                except (TypeError, ValueError):
                    pass
        record.assumed_design_range = extract_assumed_design_range(ssr, html)
        crumbs = extract_breadcrumb_items(soup)
        if crumbs and not record.assumed_design_range:
            record.assumed_design_range = "breadcrumb:" + " > ".join(crumbs[-4:])
        schema_feats = extract_schema_org_real_estate_features(soup)
        amen = map_schema_boolean_to_amenities(schema_feats)
        record.elevator = amen.get("elevator") or record.elevator
        record.mamad = amen.get("mamad") or record.mamad
        record.air_conditioning = amen.get("air_conditioning")
        record.solar_water_heater = amen.get("solar_heater")
        record.window_bars = amen.get("window_bars")
        if amen.get("balcony"):
            record.balcony_count = record.balcony_count or 1

        # Price: ₪2,200,000
        price_el = soup.find(string=re.compile(r"₪\s*[\d,\.]+")) or soup.find(string=re.compile(r"[\d,\.]+\s*מ'"))
        if price_el:
            record.price_ils = parse_float(str(price_el))
        if not record.price_ils and re.search(r"₪\s*([\d,\.]+)", text):
            record.price_ils = parse_float(re.search(r"₪\s*([\d,\.]+)", text).group(1))

        # Rooms, floor, size — SSR first, then regex
        if not record.rooms and poi.get("rooms") is not None:
            try:
                record.rooms = float(poi["rooms"])
            except (TypeError, ValueError):
                pass
        rooms_m = re.search(r"(\d+(?:\.\d+)?)\s*חדרים?", text)
        if rooms_m:
            record.rooms = parse_float(rooms_m.group(1))
        floor_m = re.search(r"קומה\s*(\d+)", text)
        if floor_m and record.floor_current is None:
            record.floor_current = parse_int(floor_m.group(1))
        floor_tot_m = re.search(r"קומות\s*בבניין\s*(\d+)|מתוך\s*(\d+)\s*קומות", text)
        if floor_tot_m:
            record.floor_total = parse_int(floor_tot_m.group(1) or floor_tot_m.group(2))
        size_m = re.search(r"(\d+)\s*מ[\"']?ר", text)
        if size_m:
            record.built_sqm = parse_float(size_m.group(1))
        if poi.get("size") is not None and not record.built_sqm:
            try:
                record.built_sqm = float(poi["size"])
            except (TypeError, ValueError):
                pass

        # Condition from schema / text
        cond_he = None
        for k, v in schema_feats.items():
            if "מצב" in k or "condition" in k.lower():
                cond_he = v
                break
        if not cond_he:
            cm = re.search(r"מצב\s+הנכס[:\s]+([^\|,\n]{2,40})", text)
            if cm:
                cond_he = cm.group(1).strip()
        if cond_he:
            record.property_condition_label = cond_he
            record.property_condition_index = 5 if any(x in cond_he for x in ["משופ", "חדש", "שמור"]) else 3

        # Address: "ויצ"ו 20, כרמליה, חיפה" or title h1
        title_el = soup.find("h1") or soup.find("title")
        if title_el:
            title_text = title_el.get_text(strip=True) if hasattr(title_el, "get_text") else str(title_el)
            parts = [p.strip() for p in re.split(r"[,،]", title_text) if p.strip()]
            if len(parts) >= 3:
                record.street_name = parts[0]
                record.neighborhood = parts[1]
                record.city = parts[2]
                record.full_address_best = title_text
            elif len(parts) == 2:
                record.street_name = parts[0]
                record.city = parts[1]
                record.full_address_best = title_text
            elif len(parts) == 1:
                record.full_address_best = parts[0]
                record.city = parts[0]

        if not record.city and re.search(r",\s*([^,]+)\s*$", text):
            record.city = re.search(r",\s*([^,]+)\s*$", text).group(1).strip()

        # Description: "תיאור הנכס" section
        desc_el = soup.find(string=re.compile(r"תיאור\s*הנכס"))
        if desc_el and hasattr(desc_el, "parent"):
            parent = desc_el.parent
            for _ in range(5):
                if parent is None:
                    break
                next_el = parent.find_next_sibling()
                if next_el:
                    record.description_raw = next_el.get_text(" ", strip=True)[:5000] if hasattr(next_el, "get_text") else str(next_el)[:5000]
                    record.description_clean = record.description_raw
                    break
                parent = getattr(parent, "parent", None)

        if not record.description_clean and soup.find("meta", attrs={"name": "description"}):
            meta = soup.find("meta", attrs={"name": "description"})
            if meta and meta.get("content"):
                record.description_clean = meta["content"][:3000]

        # Seller: search URL already encodes private vs agency in filters; page text refines
        if "_agency_" in (filtered_search_url or "") or "agency" in (filtered_search_url or "").lower():
            record.seller_type = record.seller_type or "broker"
        elif "_private_" in (filtered_search_url or "") or re.search(r"filters=[^&]*_private_", filtered_search_url or ""):
            record.seller_type = "private"
        classified = _classify_seller_type_from_text(text)
        if classified:
            record.seller_type = classified
        elif not record.seller_type:
            record.seller_type = "private"

        # Investment context from description
        desc_for_ctx = (record.description_clean or text)[:8000]
        transit, nuis = extract_investment_context_from_text(desc_for_ctx)
        record.investment_transit_notes = transit or None
        record.investment_nuisance_notes = nuis or None

        record.property_technical_profile_en = build_technical_profile_en(
            year_built=record.year_built,
            total_floors_building=record.floor_total,
            apartment_floor=record.floor_current,
            price_ils=record.price_ils,
            built_sqm=record.built_sqm,
            rooms=record.rooms,
            condition_en=translate_condition_label(record.property_condition_label or "") if record.property_condition_label else None,
            assumed_design_range=record.assumed_design_range,
            amenities={
                "elevator": bool(record.elevator),
                "air_conditioning": bool(record.air_conditioning),
                "mamad_safe_room": bool(record.mamad),
                "balcony": bool(record.balcony_count),
                "solar_heater": bool(record.solar_water_heater),
                "window_bars": bool(record.window_bars),
            },
            transit_tags=transit,
            nuisance_tags=nuis,
        )
        if schema_feats:
            record.extra_features = (record.extra_features or "") + " | schema:" + json.dumps(schema_feats, ensure_ascii=False)[:500]

        # Publication date if present
        pub_m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
        if pub_m:
            record.publication_date_raw = f"{pub_m.group(1)}/{pub_m.group(2)}/{pub_m.group(3)}"
            try:
                record.publication_date_iso = f"{pub_m.group(3)}-{int(pub_m.group(2)):02d}-{int(pub_m.group(1)):02d}"
            except ValueError:
                pass

        # Phone: same as Yad2 (tel: link, then span with 05, then regex on body)
        raw_phone = None
        phone_method = None
        try:
            tel_link = page.query_selector("a[href^='tel:']")
            if tel_link:
                href = tel_link.get_attribute("href") or ""
                if href.startswith("tel:"):
                    raw_phone = href[len("tel:"):].strip()
                    phone_method = "dom_tel_link"
        except Exception:
            pass
        if not raw_phone:
            try:
                phone_span = page.query_selector("span:has-text('05'), div:has-text('05')")
                if phone_span:
                    candidate = phone_span.inner_text()
                    if re.search(r"05\d", candidate):
                        raw_phone = candidate
                        phone_method = "dom_text"
            except Exception:
                pass
        if not raw_phone:
            try:
                page_text = page.inner_text("body") if hasattr(page, "inner_text") else text
                phone_match = re.search(r"05\d[-\s]?\d{7}", page_text)
                if phone_match:
                    raw_phone = phone_match.group(0)
                    phone_method = "regex_body_text"
            except Exception:
                pass
        if raw_phone:
            record.seller_phone_raw = raw_phone
            record.seller_phone_normalized = self._normalize_phone(raw_phone)
            record.phone_found = True
            record.phone_extraction_method = phone_method

        # Geocode
        if record.full_address_best and self.geocoder:
            try:
                coords = self.geocoder.geocode(record.full_address_best)
                if coords:
                    record.latitude, record.longitude = coords
                    if self.route_calculator:
                        self.route_calculator.compute_routes_for_listing(record, self.run_summary)
            except Exception:
                pass

        if record.price_ils and record.built_sqm and record.built_sqm > 0:
            record.price_per_sqm = record.price_ils / record.built_sqm

        return record

    def _validate_critical_fields(self, record: ListingRecord, page: Page) -> None:
        """Same critical set as Yad2 (where applicable)."""
        critical_fields = {
            "yad2_listing_id": record.yad2_listing_id,
            "original_listing_url": record.original_listing_url,
            "price_ils": record.price_ils,
            "rooms": record.rooms,
            "built_sqm": record.built_sqm,
            "floor_current": record.floor_current,
            "description_clean": record.description_clean,
            "seller_name": record.seller_name,
            "seller_phone_normalized": record.seller_phone_normalized,
            "publication_date_iso": record.publication_date_iso or record.publication_date_raw,
            "city": record.city or record.full_address_best,
        }
        missing = [name for name, value in critical_fields.items() if not value]
        if missing:
            reason = "selector_not_found"
            if "city" in missing and getattr(record, "geocode_status", None) == "address_unresolved":
                reason = "address_unresolved"
            elif getattr(record, "geocode_status", None) == "geocode_failed":
                reason = "geocode_failed"
            record.missing_reason_code = reason
            record.extraction_notes = f"Missing critical fields ({reason}): {', '.join(missing)}"
            self.run_summary.total_rows_with_missing_critical_fields += 1

    def _append_record_to_csv(self, record: ListingRecord) -> None:
        """Same as Yad2: log exported listing block, append CSV, update run summary."""
        logging.info(
            "\n"
            "==================== EXPORTED LISTING (Madlan) ====================\n"
            "ID:                %s\n"
            "URL:               %s\n"
            "City:              %r\n"
            "Street:            %r\n"
            "Rooms:             %s\n"
            "Built sqm:         %s\n"
            "Floor (current):   %s\n"
            "Floor (total):     %s\n"
            "Price (ILS):       %s\n"
            "Publication date:  %s\n"
            "================================================================",
            record.yad2_listing_id,
            record.original_listing_url,
            record.city,
            record.street_name,
            record.rooms,
            record.built_sqm,
            record.floor_current,
            record.floor_total,
            record.price_ils,
            record.publication_date_iso or record.publication_date_raw,
        )
        df = pd.DataFrame([record.model_dump()])
        exists = self.output_csv.exists()
        df.to_csv(
            self.output_csv,
            mode="a",
            header=not exists,
            index=False,
            encoding="utf-8",
            quoting=csv.QUOTE_NONNUMERIC,
        )
        self.run_summary.total_exported_rows += 1
        if record.missing_reason_code:
            self.run_summary.total_partial_rows += 1

    def _save_debug_artifacts(self, page: Page, listing_id: str, reason: str) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        html_path = self.debug_dir / f"{listing_id}_{timestamp}.html"
        screenshot_path = self.debug_dir / f"{listing_id}_{timestamp}.png"
        try:
            html_path.write_text(page.content(), encoding="utf-8")
        except Exception:
            pass
        try:
            page.screenshot(path=str(screenshot_path), full_page=True)
        except Exception:
            pass
        logging.info("Saved debug artifacts for %s: %s", listing_id, reason)

    def _download_images(self, listing_id: str, page: Page, record: ListingRecord) -> None:
        imgs = page.query_selector_all("img[src*='madlan'], img[srcset]")
        urls: List[str] = []
        for img in imgs:
            src = img.get_attribute("src")
            srcset = img.get_attribute("srcset")
            if srcset:
                parts = [p.strip().split(" ")[0] for p in srcset.split(",") if p.strip()]
                if parts:
                    urls.append(parts[-1])
            elif src and src not in urls:
                urls.append(src)
        record.image_count_detected = len(urls)
        if not urls:
            return
        listing_img_dir = self.images_dir / listing_id
        listing_img_dir.mkdir(parents=True, exist_ok=True)
        for idx, url in enumerate(urls[:20], start=1):
            try:
                ext = ".jpg"
                filepath = listing_img_dir / f"{idx:03d}{ext}"
                resp = self.session.get(url, timeout=20)
                resp.raise_for_status()
                filepath.write_bytes(resp.content)
                record.image_count_downloaded += 1
                self.run_summary.total_images_downloaded += 1
            except Exception:
                pass
        record.image_folder_path = str(listing_img_dir)

    def _export_fixed_hebrew_xlsx(self) -> None:
        """Same CSV→Excel as Yad2: column order, date/phone/number formats, filename from --locations (export_slug)."""
        if not self.output_csv.exists():
            return
        base = self.export_slug if self.export_slug else "fixed_hebrew_file"
        out_xlsx = self.output_dir / f"{base}.xlsx"
        try:
            _export_listings_to_formatted_excel(self.output_csv, out_xlsx)
        except Exception as e:
            logging.warning("Failed to create Excel %s: %s", out_xlsx, e)


def main() -> None:
    load_dotenv()
    import argparse
    parser = argparse.ArgumentParser(description="Madlan (madlan.co.il) for-sale scraper")
    parser.add_argument("--output-dir", type=str, default="output_madlan", help="Output directory")
    parser.add_argument("--max-pages", type=int, default=4, help="Search pages to scrape")
    parser.add_argument("--headless", type=int, choices=[0, 1], default=1, help="1=headless, 0=visible")
    parser.add_argument("--captcha-avoidance-min", type=float, default=0, help="Minutes to sleep between search pages (same as Yad2)")
    parser.add_argument(
        "--locations",
        type=str,
        default="",
        help=(
            "City/area to search (unified with Yad2). English or Hebrew, comma-separated. "
            "Examples: --locations 'Haifa', --locations 'Haifa, Rehovot', --locations 'חיפה'. "
            "Resolved via assets/unified_location_names.json. Excel output named e.g. Haifa_Area.xlsx."
        ),
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    prefs = load_madlan_preferences()
    export_slug: Optional[str] = None
    locations_list: Optional[List[str]] = None
    if args.locations:
        try:
            from unified_locations import resolve_locations_to_madlan
            locations_list, export_slug = resolve_locations_to_madlan(args.locations)
            if locations_list:
                prefs["locations"] = locations_list
        except Exception as e:
            logging.warning("Unified locations resolution failed: %s; using --locations as literal.", e)
            locations_list = [x.strip() for x in args.locations.split(",") if x.strip()]
            if locations_list:
                prefs["locations"] = locations_list
    if not locations_list and args.locations:
        locations_list = [x.strip() for x in args.locations.split(",") if x.strip()]
    if locations_list:
        prefs["locations"] = locations_list
    if args.captcha_avoidance_min is not None and args.captcha_avoidance_min > 0:
        prefs["captcha_avoidance_min"] = args.captcha_avoidance_min

    email = os.getenv("GEOCODING_EMAIL", "example@example.com")
    geocoder = Geocoder(email=email)
    ors_key = os.getenv("ORS_API_KEY")
    route_calc = RouteCalculator(ors_key) if ors_key else None

    scraper = MadlanScraper(
        output_dir=output_dir,
        geocoder=geocoder,
        route_calculator=route_calc,
        max_pages=args.max_pages,
        headless=bool(args.headless),
        madlan_preferences=prefs,
        export_slug=export_slug,
    )
    scraper.scrape()
    print("Done. CSV:", scraper.output_csv)
    print("Debug dir:", scraper.debug_dir)


if __name__ == "__main__":
    main()
