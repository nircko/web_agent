import asyncio
import csv
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set, Union

import openrouteservice
import pandas as pd
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from playwright.sync_api import sync_playwright, Page, Browser

from yad2_url_builder import (
    load_mappings,
    build_yad2_url_from_json,
    group_areas_and_cities_by_district,
    MAX_MULTI_CITIES,
)


BASE_SEARCH_URL = "https://www.yad2.co.il/realestate/forsale/center-and-sharon"

# Default preferences when no file is found.
DEFAULT_FILTER_PREFERENCES = {
    "district": "Center and Sharon",
    "listing_type": "forsale",
    "areas": [],
    "cities": [],
    "url_filters": {
        "minPrice": 1600000,
        "maxPrice": 3600000,
        "maxFloor": 4,
        "minSquareMeterBuild": 90,
        "propertyCondition": [5, 3],
    },
    "post_filters": {
        "publication_cutoff_months": 3,
        "max_floor_total": 7,
        "cities_to_skip": [],
    },
}


def _normalize_preferences(data: Dict[str, Any]) -> Dict[str, Any]:
    """Map user-friendly keys to internal format. Accepts both flat and nested formats."""
    out = dict(DEFAULT_FILTER_PREFERENCES)
    # User-friendly flat format (root scraper_preferences.json)
    if "default_region" in data and data["default_region"] is not None:
        out["district"] = str(data["default_region"]).strip()
    if "price_min" in data and data["price_min"] is not None:
        out["url_filters"]["minPrice"] = int(data["price_min"])
    if "price_max" in data and data["price_max"] is not None:
        out["url_filters"]["maxPrice"] = int(data["price_max"])
    if "max_floor" in data and data["max_floor"] is not None:
        out["url_filters"]["maxFloor"] = int(data["max_floor"])
    if "min_square_meters" in data and data["min_square_meters"] is not None:
        out["url_filters"]["minSquareMeterBuild"] = int(data["min_square_meters"])
    if "property_condition" in data and data["property_condition"] is not None:
        out["url_filters"]["propertyCondition"] = list(data["property_condition"])
    if "publication_max_months" in data and data["publication_max_months"] is not None:
        out["post_filters"]["publication_cutoff_months"] = int(data["publication_max_months"])
    if "max_building_floors" in data and data["max_building_floors"] is not None:
        out["post_filters"]["max_floor_total"] = int(data["max_building_floors"])
    if "exclude_cities" in data and data["exclude_cities"] is not None:
        out["post_filters"]["cities_to_skip"] = list(data["exclude_cities"])
    # Common keys in both formats
    if "listing_type" in data and data["listing_type"] is not None:
        out["listing_type"] = str(data["listing_type"]).strip()
    if "areas" in data and data["areas"] is not None:
        out["areas"] = [a for a in data["areas"] if str(a).strip()] if isinstance(data["areas"], list) else []
    if "cities" in data and data["cities"] is not None:
        out["cities"] = [c for c in data["cities"] if c and str(c).strip()] if isinstance(data["cities"], list) else []
    if "district" in data and data["district"] is not None:
        out["district"] = str(data["district"]).strip()
    # Nested format (legacy config/filter_preferences.json)
    if "url_filters" in data and isinstance(data["url_filters"], dict):
        out["url_filters"] = {**out["url_filters"], **data["url_filters"]}
    if "post_filters" in data and isinstance(data["post_filters"], dict):
        out["post_filters"] = {**out["post_filters"], **data["post_filters"]}
    return out


def load_filter_preferences(project_root: Optional[Path] = None) -> Dict[str, Any]:
    """Load preferences from project root (scraper_preferences.json) or config/filter_preferences.json.
    Uses user-friendly flat format when present; district in the file is only used when areas and cities
    are both empty—otherwise district is always deduced from the areas/cities lists."""
    root = project_root or Path(__file__).resolve().parent
    for path in [root / "scraper_preferences.json"]:
        if path.exists():
            try:
                raw = path.read_text(encoding="utf-8")
                data = json.loads(raw)
                if not isinstance(data, dict):
                    return dict(DEFAULT_FILTER_PREFERENCES)
                return _normalize_preferences(data)
            except Exception as e:
                logging.warning("Failed to load preferences from %s: %s, using defaults.", path, e)
                return dict(DEFAULT_FILTER_PREFERENCES)
    return dict(DEFAULT_FILTER_PREFERENCES)


class CriticalFieldMissing(Exception):
    """Raised when a critical field cannot be extracted."""


class ListingRecord(BaseModel):
    # Identity & source
    yad2_listing_id: str
    original_listing_url: str
    filtered_search_url: str
    search_page_number: int
    scrape_timestamp_utc: str

    # Seller & publication
    publication_date_raw: Optional[str] = None
    publication_date_iso: Optional[str] = None
    seller_name: Optional[str] = None
    seller_type: Optional[str] = None
    seller_phone_raw: Optional[str] = None
    seller_phone_normalized: Optional[str] = None
    phone_found: bool = False
    phone_extraction_method: Optional[str] = None

    # Core property
    title: Optional[str] = None
    property_type: Optional[str] = None
    transaction_type: Optional[str] = "sale"
    price_ils: Optional[float] = None
    currency: Optional[str] = "ILS"
    rooms: Optional[float] = None
    floor_current: Optional[int] = None
    floor_total: Optional[int] = None
    built_sqm: Optional[float] = None
    lot_sqm: Optional[float] = None
    price_per_sqm: Optional[float] = None
    property_condition_index: Optional[int] = None
    property_condition_label: Optional[str] = None
    description_raw: Optional[str] = None
    description_clean: Optional[str] = None
    entry_date: Optional[str] = None
    balcony_count: Optional[int] = None
    parking_count: Optional[int] = None
    elevator: Optional[bool] = None
    mamad: Optional[bool] = None
    storage: Optional[bool] = None
    extra_features: Optional[str] = None

    # Location
    street_address_raw: Optional[str] = None
    street_name: Optional[str] = None
    house_number: Optional[str] = None
    neighborhood: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = "center-and-sharon"
    full_address_best: Optional[str] = None
    address_confidence: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    geocode_status: Optional[str] = None

    # Routing
    drive_to_tel_aviv_savidor_duration_min: Optional[float] = None
    drive_to_tel_aviv_savidor_distance_km: Optional[float] = None
    drive_to_beer_sheva_center_duration_min: Optional[float] = None
    drive_to_beer_sheva_center_distance_km: Optional[float] = None

    # Images
    image_count_detected: int = 0
    image_count_downloaded: int = 0
    primary_image_url: Optional[str] = None
    image_folder_path: Optional[str] = None
    image_file_names: Optional[str] = None

    # Intelligence / meta
    property_summary: Optional[str] = None
    commute_assessment: Optional[str] = None
    likely_fit_for_tel_aviv_commuter: Optional[bool] = None
    likely_fit_for_beer_sheva_commuter: Optional[bool] = None
    extraction_confidence_score: float = 0.0
    parsing_notes: Optional[str] = None

    # Failure / debug
    missing_reason_code: Optional[str] = None
    extraction_notes: Optional[str] = None


@dataclass
class RunSummary:
    total_search_pages_visited: int = 0
    total_result_cards_found: int = 0
    total_unique_listings_found: int = 0
    total_listings_opened: int = 0
    total_listings_filtered_by_date: int = 0
    total_listings_filtered_by_floor: int = 0
    total_listings_filtered_by_city: int = 0
    total_exported_rows: int = 0
    total_partial_rows: int = 0
    total_failed_rows: int = 0
    total_images_downloaded: int = 0
    geocode_success_count: int = 0
    geocode_failure_count: int = 0
    route_success_count: int = 0
    route_failure_count: int = 0
    total_rows_with_missing_critical_fields: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class Geocoder:
    def __init__(self, email: str, session: Optional[requests.Session] = None):
        self.email = email
        self.session = session or requests.Session()
        self.last_request_ts = 0.0

    def _respect_rate_limit(self, min_interval: float = 1.0) -> None:
        now = time.time()
        delta = now - self.last_request_ts
        if delta < min_interval:
            time.sleep(min_interval - delta)
        self.last_request_ts = time.time()

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def geocode(self, query: str) -> Optional[Tuple[float, float]]:
        if not query:
            return None
        self._respect_rate_limit()
        headers = {
            "User-Agent": f"yad2-scraper/1.0 ({self.email})",
            "Accept-Language": "en",
        }
        params = {
            "q": query,
            "format": "json",
            "limit": 1,
            "addressdetails": 1,
        }
        resp = self.session.get(
            "https://nominatim.openstreetmap.org/search",
            headers=headers,
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return None
        lat = float(data[0]["lat"])
        lon = float(data[0]["lon"])
        return lat, lon


class RouteCalculator:
    # Hard-coded coordinates for stations (lat, lon)
    TEL_AVIV_SAVIDOR = (32.084040, 34.799780)
    BEER_SHEVA_CENTER = (31.252972, 34.791463)

    def __init__(self, api_key: str):
        self.client = openrouteservice.Client(key=api_key)

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _route(self, origin: Tuple[float, float], dest: Tuple[float, float]) -> Optional[Tuple[float, float]]:
        # openrouteservice expects [lon, lat]
        coords = (
            (origin[1], origin[0]),
            (dest[1], dest[0]),
        )
        result = self.client.directions(
            coords,
            profile="driving-car",
            format="json",
        )
        routes = result.get("routes") or []
        if not routes:
            return None
        summary = routes[0].get("summary", {})
        distance_km = summary.get("distance", 0) / 1000.0
        duration_min = summary.get("duration", 0) / 60.0
        return duration_min, distance_km

    def compute_routes_for_listing(self, record: ListingRecord, run_summary: RunSummary) -> None:
        if not record.latitude or not record.longitude:
            return
        origin = (record.latitude, record.longitude)

        try:
            ta = self._route(origin, self.TEL_AVIV_SAVIDOR)
            if ta:
                record.drive_to_tel_aviv_savidor_duration_min = ta[0]
                record.drive_to_tel_aviv_savidor_distance_km = ta[1]
        except Exception:
            run_summary.route_failure_count += 1
        else:
            if record.drive_to_tel_aviv_savidor_duration_min is not None:
                run_summary.route_success_count += 1

        try:
            bs = self._route(origin, self.BEER_SHEVA_CENTER)
            if bs:
                record.drive_to_beer_sheva_center_duration_min = bs[0]
                record.drive_to_beer_sheva_center_distance_km = bs[1]
        except Exception:
            run_summary.route_failure_count += 1
        else:
            if record.drive_to_beer_sheva_center_duration_min is not None:
                run_summary.route_success_count += 1


class Yad2Scraper:
    def __init__(
        self,
        output_dir: Path,
        geocoder: Geocoder,
        route_calculator: Optional[RouteCalculator],
        max_pages: int = 4,
        captcha_avoidance_min: float = 0.0,
        headless: bool = True,
        cities_to_skip: Optional[List[str]] = None,
        areas: Optional[List[str]] = None,
    ):
        self.output_dir = output_dir
        self.images_dir = output_dir / "images"
        self.debug_dir = output_dir / "debug"
        self.logs_dir = output_dir / "logs"
        self.output_csv = output_dir / "listings_full.csv"
        self.run_summary_path = output_dir / "run_summary.json"
        self.geocoder = geocoder
        self.route_calculator = route_calculator
        self.run_summary = RunSummary()
        self.session = requests.Session()

        # Configuration knobs
        # - max_pages: how many search result pages to visit per area (default 4)
        # - captcha_avoidance_min: optional delay (in minutes) between pages to reduce captcha risk
        # - headless: run browser without UI when True (default) or with visible window when False
        # - cities_to_skip: list of city names to hard-skip after parsing (e.g. cities outside the desired zone)
        # - areas: list of human-readable Yad2 "area" names to iterate over, as defined in assets/yad2_area_IDs.json
        self.max_pages = max(1, int(max_pages))
        self.captcha_avoidance_min = max(0.0, float(captcha_avoidance_min))
        self.headless = bool(headless)
        normalized_cities: Set[str] = set()
        if cities_to_skip:
            for c in cities_to_skip:
                if c is None:
                    continue
                name = str(c).strip()
                if name:
                    normalized_cities.add(name)
        self.cities_to_skip: Set[str] = normalized_cities

        # Areas to iterate over for search pages. If empty, we search only by big_area
        # (i.e., the original behavior without per-area filtering).
        self.areas: List[str] = [a for a in (areas or []) if str(a).strip()]

        # Load canonical Yad2 mappings for big_area / area / city IDs once per scraper.
        mappings_path = Path("assets") / "yad2_area_IDs.json"
        self.yad2_mappings = load_mappings(mappings_path)

        # Derive the slug for the configured big area once (used to filter out
        # unrelated listing links like recommendations from other regions).
        self.big_area_name: str = "Center and Sharon"
        big_area_map = self.yad2_mappings.get("big_area", {}) or {}
        self.big_area_slug: str = big_area_map.get(self.big_area_name, "center-and-sharon")

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

    def build_filtered_url(
        self,
        page_number: int,
        district: str,
        group_areas: List[str],
        group_cities: List[str],
        area_name: Optional[str] = None,
    ) -> str:
        """
        Build a Yad2 search URL for one district group: path uses district,
        multiArea from area_name or group_areas, multiCity from group_cities (max 3).
        """
        areas_param: Optional[List[str]] = None
        if area_name:
            areas_param = [area_name]
        elif group_areas:
            areas_param = group_areas

        return build_yad2_url_from_json(
            self.yad2_mappings,
            district=district,
            listing_type=self.listing_type,
            areas=areas_param,
            cities=group_cities if group_cities else None,
            neighborhoods=None,
            page=page_number,
            url_filters=self.url_filters,
        )

    def scrape(self) -> None:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            try:
                for district, group_areas, group_cities in self.search_groups:
                    # Set district slug for link filtering (region_fragment in _process_search_page)
                    self.big_area_slug = self._district_slug_map.get(district, "center-and-sharon")
                    self.big_area_name = district

                    target_areas: List[Optional[str]] = group_areas if group_areas else [None]
                    for area_name in target_areas:
                        area_label = area_name if area_name is not None else "district_only"
                        logging.info(
                            "Starting search for district=%s area=%s cities=%s",
                            district,
                            area_label,
                            group_cities or "all",
                        )

                        for page_number in range(1, self.max_pages + 1):
                            search_url = self.build_filtered_url(
                                page_number, district, group_areas, group_cities, area_name=area_name
                            )
                            self._process_search_page(browser, search_url, page_number)
                            if self.captcha_avoidance_min > 0 and page_number < self.max_pages:
                                delay_sec = self.captcha_avoidance_min * 60.0
                                logging.info(
                                    "Sleeping for %s minute(s) (%d seconds) before next search page to avoid captcha.",
                                    self.captcha_avoidance_min,
                                    int(delay_sec),
                                )
                                time.sleep(delay_sec)

                logging.info("Finished processing all search pages for all district groups.")
            finally:
                browser.close()

    def _extract_listing_id_from_url(self, url: str) -> Optional[str]:
        # Try to extract numeric ID from path or query.
        m = re.search(r"/(\d+)$", url.split("?")[0])
        if m:
            return m.group(1)
        m = re.search(r"itemId=(\d+)", url)
        if m:
            return m.group(1)
        return None

    def _wait_for_captcha_solved(self, page: Page, context: str) -> None:
        """If the page shows ShieldSquare/captcha and we're not headless, wait for user to solve it."""
        while True:
            try:
                title = page.title() or ""
            except Exception:
                title = ""
            if "ShieldSquare" not in title and "Captcha" not in title:
                break
            if self.headless:
                logging.warning(
                    f"Captcha/ShieldSquare detected on {context} but running headless; "
                    "cannot wait for manual solve. Consider running with --headless 0."
                )
                break
            logging.info(f"Captcha/ShieldSquare detected on {context}.")
            logging.info("Solve the captcha in the browser window, then press Enter here to continue.")
            input("Press Enter when the real page is visible to continue... ")
            page.wait_for_timeout(2000)  # give the page a moment to update after solve
        return

    def _process_search_page(self, browser: Browser, url: str, page_number: int) -> None:
        logging.info(f"Processing search page {page_number}: {url}")
        page = browser.new_page()
        try:
            # Yad2 pages often keep background network activity (ads, analytics, captcha),
            # so waiting for "networkidle" tends to timeout. Instead, wait for DOM content
            # and then give it a short fixed delay to stabilize.
            page.goto(url, wait_until="domcontentloaded", timeout=120000)
            page.wait_for_timeout(5000)  # 5s grace period for listings / widgets to render
        except Exception as e:
            logging.error(f"Timeout or error loading search page {page_number}: {e}")
            self._save_debug_artifacts(page, f"search_page_{page_number}", f"search_page_load_error: {e}")
            page.close()
            return

        self._wait_for_captcha_solved(page, f"search page {page_number}")

        self.run_summary.total_search_pages_visited += 1

        # Attempt to select listing cards heuristically.
        cards = page.query_selector_all("a[href*='/item/'], a[href*='realestate/item']")
        self.run_summary.total_result_cards_found += len(cards)
        logging.info(f"Found {len(cards)} potential listing cards on page {page_number}")

        listing_links: List[Tuple[str, str]] = []  # (id, url)
        region_fragment = f"/realestate/item/{self.big_area_slug}/"

        # Very lightweight pre-filter on publication recency at the card level to
        # avoid opening obviously stale listings (older than ~3 months) when the
        # search UI shows relative strings like "פורסם לפני X ימים".
        def _estimate_days_ago(text: str) -> Optional[int]:
            m_rel = re.search(
                r"פורסם\s+לפני\s+(\d+)\s*(יום|ימים|שבוע|שבועות|חודש|חודשים|שנה|שנים)",
                text,
            )
            if not m_rel:
                return None
            try:
                count = int(m_rel.group(1))
            except ValueError:
                return None
            unit = m_rel.group(2)
            if unit.startswith("יום"):
                return count
            if unit.startswith("שבוע"):
                return count * 7
            if unit.startswith("חודש"):
                return count * 30
            if unit.startswith("שנה"):
                return count * 365
            return None

        cutoff_days = self.publication_cutoff_days

        for card in cards:
            href = card.get_attribute("href") or ""
            if not href.startswith("http"):
                href = "https://www.yad2.co.il" + href
            # Filter out links that do not belong to the configured region, e.g.
            # recommendations like /realestate/item/south/... that appear on the page
            # but are outside the Center & Sharon scope.
            if region_fragment not in href:
                continue

            # Try to estimate recency from the card text (if available) and skip
            # obviously old listings before opening them.
            try:
                card_text = card.inner_text() or ""
            except Exception:
                card_text = ""
            days_ago = _estimate_days_ago(card_text)
            if days_ago is not None and days_ago > cutoff_days:
                logging.info(
                    f"Skipping listing card on search page {page_number} as too old: "
                    f"~{days_ago} days ago (> {cutoff_days})"
                )
                continue

            listing_id = self._extract_listing_id_from_url(href)
            if not listing_id:
                # Fallback: hash the URL.
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

    def _normalize_phone(self, raw: str) -> str:
        digits = re.sub(r"\D+", "", raw or "")
        if digits.startswith("0"):
            digits = digits[1:]
        if digits and not digits.startswith("972"):
            digits = "972" + digits
        return digits

    def _clean_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", (text or "")).strip()

    def _parse_float(self, text: Optional[str]) -> Optional[float]:
        if not text:
            return None
        try:
            cleaned = re.sub(r"[^\d\.]", "", text.replace(",", ""))
            return float(cleaned) if cleaned else None
        except Exception:
            return None

    def _parse_int(self, text: Optional[str]) -> Optional[int]:
        if not text:
            return None
        try:
            cleaned = re.sub(r"[^\d]", "", text)
            return int(cleaned) if cleaned else None
        except Exception:
            return None

    def _extract_publication_date(self, soup: BeautifulSoup, full_text: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Try multiple strategies to extract the publication date:

        1. Look for <time> tags with datetime-like attributes.
        2. Look for phrases like 'פורסם ב dd/mm/yy' or 'פורסם בתאריך dd.mm.yyyy'.
        3. Fall back to any dd/mm/yy or dd.mm.yyyy pattern if it appears near 'פורסם' text.
        """
        # 1) <time> tags
        try:
            for t in soup.find_all("time"):
                cand = t.get("datetime") or t.get("data-date") or ""
                cand = (cand or "").strip()
                if not cand:
                    continue
                # Normalize ISO-like strings
                raw = cand
                # Try to extract just the date part if it's full ISO
                if "T" in cand:
                    cand = cand.split("T", 1)[0]
                # Basic sanity: yyyy-mm-dd or dd/mm/yyyy, etc.
                normalized = cand.replace(".", "/")
                for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
                    try:
                        dt = datetime.strptime(normalized, fmt)
                        return raw, dt.date().isoformat()
                    except Exception:
                        continue
        except Exception:
            # If anything goes wrong here, just fall back to regex logic
            pass

        # 2) Explicit "פורסם ב" style patterns
        # Normalize separators for easier parsing
        text = full_text or ""
        date_match = re.search(r"פורסם\s*ב\s*(\d{1,2}[./]\d{1,2}[./]\d{2,4})", text)
        raw_date = None
        if not date_match:
            date_match = re.search(r"פורסם\s*בתאריך\s*(\d{1,2}[./]\d{1,2}[./]\d{2,4})", text)
        if date_match:
            raw_date = date_match.group(1)
        else:
            # 3) Last resort: any dd/mm/yy or dd.mm.yyyy that is close to the word "פורסם"
            generic = list(re.finditer(r"\d{1,2}[./]\d{1,2}[./]\d{2,4}", text))
            if generic:
                chosen = None
                for m in generic:
                    start = max(m.start() - 20, 0)
                    window = text[start:m.end() + 5]
                    if "פורסם" in window:
                        chosen = m.group(0)
                        break
                if not chosen:
                    chosen = generic[0].group(0)
                raw_date = chosen

        if not raw_date:
            return None, None

        normalized = raw_date.replace(".", "/")
        for fmt in ("%d/%m/%Y", "%d/%m/%y"):
            try:
                dt = datetime.strptime(normalized, fmt)
                return raw_date, dt.date().isoformat()
            except Exception:
                continue

        return raw_date, None

    def _extract_address_from_next_data(
        self, soup: BeautifulSoup
    ) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[float], Optional[float]]:
        """
        Extract address components from the Next.js __NEXT_DATA__ JSON if present.

        Returns:
            street_name, neighborhood, city, latitude, longitude
        """
        data_script = soup.find("script", id="__NEXT_DATA__", type="application/json")
        if not data_script:
            return None, None, None, None, None

        try:
            payload = json.loads(data_script.string or data_script.get_text() or "")
        except Exception:
            return None, None, None, None, None

        try:
            addr = (
                payload.get("props", {})
                .get("pageProps", {})
                .get("dehydratedState", {})
                .get("queries", [])[0]
                .get("state", {})
                .get("data", {})
                .get("address", {})
            )
        except Exception:
            addr = {}

        if not isinstance(addr, dict):
            return None, None, None, None, None

        street_name = None
        neighborhood = None
        city = None
        lat = None
        lon = None

        street_obj = addr.get("street") or {}
        if isinstance(street_obj, dict):
            street_name = (street_obj.get("text") or "").strip() or None

        city_obj = addr.get("city") or {}
        if isinstance(city_obj, dict):
            city = (city_obj.get("text") or "").strip() or None

        neighborhood_obj = addr.get("neighborhood") or {}
        # At the moment only id is present; keep placeholder for future mapping
        if isinstance(neighborhood_obj, dict) and neighborhood_obj.get("text"):
            neighborhood = (neighborhood_obj.get("text") or "").strip() or None

        coords = addr.get("coords") or {}
        if isinstance(coords, dict):
            try:
                lat = float(coords.get("lat")) if coords.get("lat") is not None else None
                lon = float(coords.get("lon")) if coords.get("lon") is not None else None
            except (TypeError, ValueError):
                lat, lon = None, None

        return street_name, neighborhood, city, lat, lon

    def _determine_address_confidence(self, street: Optional[str], house_number: Optional[str], city: Optional[str], neighborhood: Optional[str]) -> Tuple[str, Optional[str]]:
        if street and house_number and city:
            full = f"{street} {house_number}, {city}, Israel"
            return "exact", full
        if street and city:
            full = f"{street}, {city}, Israel"
            return "inferred_from_page", full
        if neighborhood and city:
            full = f"{neighborhood}, {city}, Israel"
            return "neighborhood_level", full
        if city:
            full = f"{city}, Israel"
            return "city_only", full
        return "unresolved", None

    def _generate_summary_and_commute(self, record: ListingRecord) -> None:
        parts = []
        if record.property_type or record.rooms or record.built_sqm:
            core = []
            if record.rooms:
                core.append(f"{record.rooms:g}-room")
            if record.property_type:
                core.append(record.property_type)
            if record.built_sqm:
                core.append(f"{int(record.built_sqm)} sqm")
            parts.append(" ".join(core))
        if record.city:
            parts.append(f"in {record.city}")
        if record.floor_current is not None:
            parts.append(f"on floor {record.floor_current}")
        if record.price_ils:
            parts.append(f"priced at {int(record.price_ils):,} ILS".replace(",", " "))

        commute_bits = []
        if record.drive_to_tel_aviv_savidor_duration_min is not None:
            commute_bits.append(
                f"{record.drive_to_tel_aviv_savidor_duration_min:.0f} min drive to Tel Aviv Savidor"
            )
        if record.drive_to_beer_sheva_center_duration_min is not None:
            commute_bits.append(
                f"{record.drive_to_beer_sheva_center_duration_min:.0f} min drive to Beer Sheva Center"
            )
        if commute_bits:
            parts.append("; ".join(commute_bits))
        record.property_summary = ". ".join(parts) if parts else None

        commute_assessment_parts = []
        if record.drive_to_tel_aviv_savidor_duration_min is not None:
            if record.drive_to_tel_aviv_savidor_duration_min <= 45:
                commute_assessment_parts.append("Good for Tel Aviv commuters")
            elif record.drive_to_tel_aviv_savidor_duration_min <= 75:
                commute_assessment_parts.append("Acceptable Tel Aviv commute")
            else:
                commute_assessment_parts.append("Long Tel Aviv commute")
        if record.drive_to_beer_sheva_center_duration_min is not None:
            if record.drive_to_beer_sheva_center_duration_min <= 60:
                commute_assessment_parts.append("Reasonable Beer Sheva commute")
            elif record.drive_to_beer_sheva_center_duration_min <= 90:
                commute_assessment_parts.append("Borderline Beer Sheva commute")
            else:
                commute_assessment_parts.append("Long Beer Sheva commute")

        record.likely_fit_for_tel_aviv_commuter = (
            record.drive_to_tel_aviv_savidor_duration_min is not None
            and record.drive_to_tel_aviv_savidor_duration_min <= 60
        )
        record.likely_fit_for_beer_sheva_commuter = (
            record.drive_to_beer_sheva_center_duration_min is not None
            and record.drive_to_beer_sheva_center_duration_min <= 75
        )

        record.commute_assessment = "; ".join(commute_assessment_parts) if commute_assessment_parts else None

    def _save_debug_artifacts(self, page: Page, listing_id: str, reason: str) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        html_path = self.debug_dir / f"{listing_id}_{timestamp}.html"
        screenshot_path = self.debug_dir / f"{listing_id}_{timestamp}.png"

        try:
            html_content = page.content()
            html_path.write_text(html_content, encoding="utf-8")
        except Exception as e:
            logging.warning(f"Failed to save HTML debug for {listing_id}: {e}")

        try:
            page.screenshot(path=str(screenshot_path), full_page=True)
        except Exception as e:
            logging.warning(f"Failed to save screenshot debug for {listing_id}: {e}")

        logging.info(f"Saved debug artifacts for {listing_id} due to: {reason}")

    def _download_images(self, listing_id: str, page: Page, record: ListingRecord) -> None:
        image_elements = page.query_selector_all("img[src*='yad2'], img[src*='cloudinary'], img[srcset]")
        image_urls: List[str] = []
        for img in image_elements:
            srcset = img.get_attribute("srcset")
            src = img.get_attribute("src")
            candidate = None
            if srcset:
                # Take the highest resolution from srcset
                parts = [p.strip() for p in srcset.split(",")]
                if parts:
                    candidate = parts[-1].split(" ")[0]
            if not candidate and src:
                candidate = src
            if candidate and candidate not in image_urls:
                image_urls.append(candidate)

        record.image_count_detected = len(image_urls)
        if not image_urls:
            return

        listing_img_dir = self.images_dir / listing_id
        listing_img_dir.mkdir(parents=True, exist_ok=True)
        file_names: List[str] = []

        for idx, url in enumerate(image_urls, start=1):
            ext = ".jpg"
            m = re.search(r"\.(jpe?g|png|webp)(\?|$)", url, re.IGNORECASE)
            if m:
                ext = "." + m.group(1).lower()
            filename = f"{idx:03d}{ext}"
            filepath = listing_img_dir / filename
            try:
                resp = self.session.get(url, timeout=20)
                resp.raise_for_status()
                filepath.write_bytes(resp.content)
                file_names.append(filename)
                record.image_count_downloaded += 1
                self.run_summary.total_images_downloaded += 1
                if idx == 1:
                    record.primary_image_url = url
            except Exception as e:
                logging.warning(f"Failed to download image {url} for {listing_id}: {e}")

        record.image_folder_path = str(listing_img_dir)
        record.image_file_names = ",".join(file_names) if file_names else None

    def _extract_from_listing_html(
        self,
        html: str,
        listing_id: str,
        original_url: str,
        filtered_search_url: str,
        search_page_number: int,
    ) -> ListingRecord:
        soup = BeautifulSoup(html, "lxml")

        now_iso = datetime.now(timezone.utc).isoformat()

        record = ListingRecord(
            yad2_listing_id=listing_id,
            original_listing_url=original_url,
            filtered_search_url=filtered_search_url,
            search_page_number=search_page_number,
            scrape_timestamp_utc=now_iso,
        )

        # Title
        title_el = soup.find("h1") or soup.find("h2")
        if title_el:
            record.title = self._clean_text(title_el.get_text())

        # Basic numeric fields heuristics
        price_el = soup.find(string=re.compile(r"\d[\d,\.]*\s*₪")) or soup.find("span", string=re.compile(r"₪"))
        if price_el:
            record.price_ils = self._parse_float(str(price_el))

        # Try to detect property metadata table / list
        text = soup.get_text(" ", strip=True)

        # Rooms
        m = re.search(r"(\d+(?:\.\d+)?)\s*חדר", text)
        if m:
            record.rooms = float(m.group(1))

        # Floor (current and total, if available, e.g. "קומה 3 מתוך 7")
        m = re.search(r"קומה\s*(\d+)(?:\s*מתוך\s*(\d+))?", text)
        if m:
            record.floor_current = int(m.group(1))
            if m.group(2):
                try:
                    record.floor_total = int(m.group(2))
                except ValueError:
                    record.floor_total = None

        # Built sqm
        m = re.search(r"(\d+)\s*מ\"ר\s*בנוי", text)
        if m:
            record.built_sqm = float(m.group(1))

        # Description
        desc_el = soup.find("div", {"data-testid": "description"}) or soup.find("p", {"class": re.compile("description")})
        if desc_el:
            record.description_raw = desc_el.get_text(" ", strip=True)
            record.description_clean = self._clean_text(record.description_raw)
        else:
            # Fallback: longest paragraph
            paragraphs = sorted(
                (self._clean_text(p.get_text(" ", strip=True)) for p in soup.find_all("p")),
                key=len,
                reverse=True,
            )
            if paragraphs:
                record.description_raw = paragraphs[0]
                record.description_clean = paragraphs[0]

        # Property condition (label + simple index heuristic)
        # Look for a "מצב הנכס" style label followed by a short value
        condition_match = re.search(r"מצב\s+הנכס[:\s]+([^\|,\n]{2,25})", text)
        if condition_match:
            cond_label = self._clean_text(condition_match.group(1))
            if cond_label:
                record.property_condition_label = cond_label
                # Very rough mapping to the spec's 3 and 5 indices
                lowered = cond_label.lower()
                if any(k in lowered for k in ["חדש", "משופץ", "כמו חדש"]):
                    record.property_condition_index = 5
                elif any(k in lowered for k in ["במצב טוב", "דורש שיפוץ", "זקוק לשיפוץ"]):
                    record.property_condition_index = 3

        # Seller block (best-effort name; more enrichment happens in the page-aware wrapper)
        seller_block = None
        # Common Yad2 patterns: "מפרסם", "משרד תיווך", etc.
        for label in ["מפרסם", "פרטים על המפרסם", "משרד תיווך", "משרד"]:
            seller_block = soup.find(string=re.compile(label))
            if seller_block:
                break
        if seller_block:
            # Try to grab a short line near the label as seller name
            parent_text = self._clean_text(seller_block.parent.get_text(" ", strip=True)) if hasattr(
                seller_block, "parent"
            ) else self._clean_text(str(seller_block))
            # Very heuristic: split by ":" or line breaks and take the last reasonable token
            parts = re.split(r"[:|]", parent_text)
            candidate = parts[-1].strip() if parts else parent_text
            if candidate and 2 <= len(candidate) <= 60:
                record.seller_name = candidate

            # Seller type heuristic
            lowered = parent_text.lower()
            if "תיווך" in parent_text or "מתווך" in parent_text or "משרד" in parent_text:
                record.seller_type = "broker"
            elif "קבלן" in parent_text:
                record.seller_type = "contractor"
            else:
                # Leave as None here; we may still infer later
                pass

        # Basic feature flags from page text (best-effort, language-specific)
        # These rely on common Hebrew phrases appearing anywhere in the rendered text.
        # Elevator
        if "מעלית" in text:
            record.elevator = True
        # Mamad (safe room)
        if "ממ\"ד" in text or "ממד" in text:
            record.mamad = True
        # Storage
        if "מחסן" in text:
            record.storage = True

        # Parking and balcony counts (simple numeric heuristics)
        m_parking = re.search(r"(?:(?:חניה|חניות)[:\s]+)(\d+)", text)
        if m_parking:
            record.parking_count = self._parse_int(m_parking.group(1))

        m_balcony = re.search(r"(?:(?:מרפסת|מרפסות)[:\s]+)(\d+)", text)
        if m_balcony:
            record.balcony_count = self._parse_int(m_balcony.group(1))

        # Extra features text: collect a few key real-estate buzzwords if present
        feature_phrases = []
        for phrase in ["מרפסת שמש", "קרוב ל", "נוף", "שקט", "מושקע", "משופץ", "שמורה"]:
            if phrase in text:
                feature_phrases.append(phrase)
        if feature_phrases:
            record.extra_features = ", ".join(sorted(set(feature_phrases)))

        # Publication date heuristic (improved)
        raw_date, iso_date = self._extract_publication_date(soup, text)
        if raw_date:
            record.publication_date_raw = raw_date
        if iso_date:
            record.publication_date_iso = iso_date

        # Location: prefer structured Next.js JSON, then fall back to heuristics
        street_name, neighborhood, city, json_lat, json_lon = self._extract_address_from_next_data(soup)

        # Heuristic fallbacks from breadcrumbs / header / title if needed
        if not city:
            breadcrumb = soup.find("nav") or soup.find("ul", {"class": re.compile("breadcrumb")})
            if breadcrumb:
                crumb_text = breadcrumb.get_text(" ", strip=True)
                m = re.search(r"ב([א-ת\s]+)", crumb_text)
                if m:
                    city = self._clean_text(m.group(1))
        if not city and record.title:
            m = re.search(r"ב([א-ת\s]+)$", record.title)
            if m:
                city = self._clean_text(m.group(1))

        # Additional heuristic: pattern like "דירה, הפרחים, מודיעין מכבים רעות"
        if not city or not street_name:
            m = re.search(
                r"(דירה|בית|פנטהאוס|דופלקס|דירת גן)[ ,]+([^,\n]+),\s*([^,\n]+)",
                text,
            )
            if m:
                candidate_street = self._clean_text(m.group(2))
                candidate_city = self._clean_text(m.group(3))
                if candidate_city:
                    city = city or candidate_city
                if candidate_street:
                    street_name = street_name or candidate_street

        # Heuristic neighborhood / project name appearing before "נכס ..."
        if not neighborhood:
            m_neigh = re.search(r'([א-ת"׳״\s]{2,25})\s+נכס', text)
            if m_neigh:
                candidate_neigh = self._clean_text(m_neigh.group(1))
                if candidate_neigh and 1 < len(candidate_neigh) <= 25:
                    neighborhood = candidate_neigh

        record.city = city
        record.neighborhood = neighborhood
        record.street_name = street_name
        record.house_number = None

        addr_conf, full_addr = self._determine_address_confidence(
            record.street_name,
            record.house_number,
            record.city,
            record.neighborhood,
        )
        record.address_confidence = addr_conf
        record.full_address_best = full_addr

        # Geocoding
        if json_lat is not None and json_lon is not None:
            # Use coordinates provided by Yad2 listing JSON
            record.latitude = json_lat
            record.longitude = json_lon
            record.geocode_status = "from_source"
        else:
            if record.full_address_best:
                try:
                    coords = self.geocoder.geocode(record.full_address_best)
                    if coords:
                        record.latitude, record.longitude = coords
                        record.geocode_status = "success"
                    else:
                        record.geocode_status = "geocode_failed"
                except Exception as e:
                    logging.warning(f"Geocoding failed for {listing_id}: {e}")
                    record.geocode_status = "geocode_failed"
            else:
                record.geocode_status = "address_unresolved"

        if record.geocode_status == "success":
            self.run_summary.geocode_success_count += 1
        else:
            self.run_summary.geocode_failure_count += 1

        # Routes
        if self.route_calculator and record.latitude and record.longitude:
            self.route_calculator.compute_routes_for_listing(record, self.run_summary)

        # Derived metrics
        if record.price_ils and record.built_sqm and record.built_sqm > 0:
            record.price_per_sqm = record.price_ils / record.built_sqm

        self._generate_summary_and_commute(record)

        # Heuristic extraction confidence
        filled_core = sum(
            1
            for f in [
                record.price_ils,
                record.rooms,
                record.built_sqm,
                record.floor_current,
                record.description_clean,
                record.city,
            ]
            if f is not None
        )
        record.extraction_confidence_score = filled_core / 6.0

        return record

    def _extract_from_listing_page(self, page: Page, listing_id: str, original_url: str, filtered_search_url: str, search_page_number: int) -> ListingRecord:
        content_html = page.content()
        record = self._extract_from_listing_html(
            html=content_html,
            listing_id=listing_id,
            original_url=original_url,
            filtered_search_url=filtered_search_url,
            search_page_number=search_page_number,
        )

        # Try to click "show phone" if present to improve phone extraction
        try:
            phone_button = page.query_selector("button:has-text('טלפון'), button:has-text('הצג'), button:has-text('הצג טל')")
            if phone_button:
                phone_button.click()
                time.sleep(2)
        except Exception:
            phone_button = None

        # Phone from DOM (tel: links or dedicated phone span)
        raw_phone = None
        phone_method = None
        try:
            tel_link = page.query_selector("a[href^='tel:']")
            if tel_link:
                href = tel_link.get_attribute("href") or ""
                if href.startswith("tel:"):
                    raw_phone = href[len("tel:") :]
                    phone_method = "dom_tel_link"
        except Exception:
            tel_link = None

        if not raw_phone:
            try:
                # Fallback: any visible element that looks like a phone
                phone_span = page.query_selector("span:has-text('05'), div:has-text('05')")
                if phone_span:
                    candidate = phone_span.inner_text()
                    if re.search(r"05\d", candidate):
                        raw_phone = candidate
                        phone_method = "dom_text"
            except Exception:
                phone_span = None

        # Final fallback: regex over full body text
        if not raw_phone:
            try:
                page_text = page.inner_text("body")
            except Exception:
                page_text = ""
            phone_match = re.search(r"05\d[-\s]?\d{7}", page_text)
            if phone_match:
                raw_phone = phone_match.group(0)
                phone_method = "regex_body_text"

        if raw_phone:
            record.seller_phone_raw = raw_phone
            record.seller_phone_normalized = self._normalize_phone(raw_phone)
            record.phone_found = True
            record.phone_extraction_method = phone_method

        return record

    def _validate_critical_fields(self, record: ListingRecord, page: Page) -> None:
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
            # Choose a more specific reason code when possible
            reason = "selector_not_found"
            if "city" in missing and record.geocode_status == "address_unresolved":
                reason = "address_unresolved"
            elif record.geocode_status == "geocode_failed":
                reason = "geocode_failed"

            record.missing_reason_code = reason
            record.extraction_notes = f"Missing critical fields ({reason}): {', '.join(missing)}"
            self._save_debug_artifacts(page, record.yad2_listing_id, record.extraction_notes)
            self.run_summary.total_rows_with_missing_critical_fields += 1

    def _append_record_to_csv(self, record: ListingRecord) -> None:
        # Pretty-print a summary of the listing that successfully passed all
        # filters and is about to be persisted to the main CSV.
        logging.info(
            "\n"
            "==================== EXPORTED LISTING ====================\n"
            f"ID:                {record.yad2_listing_id}\n"
            f"URL:               {record.original_listing_url}\n"
            f"City:              {record.city!r}\n"
            f"Street:            {record.street_name!r}\n"
            f"Rooms:             {record.rooms}\n"
            f"Built sqm:         {record.built_sqm}\n"
            f"Floor (current):   {record.floor_current}\n"
            f"Floor (total):     {record.floor_total}\n"
            f"Price (ILS):       {record.price_ils}\n"
            f"Publication date:  {record.publication_date_iso or record.publication_date_raw}\n"
            f"Address conf.:     {record.address_confidence}\n"
            f"Geocode status:    {record.geocode_status}\n"
            f"Missing reason:    {record.missing_reason_code}\n"
            "==========================================================="
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

    def _persist_run_summary(self) -> None:
        self.run_summary_path.write_text(
            json.dumps(self.run_summary.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _process_listing(
        self,
        browser: Browser,
        search_page_number: int,
        filtered_search_url: str,
        listing_id: str,
        listing_url: str,
    ) -> None:
        logging.info(f"Processing listing {listing_id}: {listing_url}")
        page = browser.new_page()
        try:
            self.run_summary.total_listings_opened += 1
            # Use domcontentloaded so captcha pages don't hang on networkidle; we then wait for user to solve captcha if needed
            page.goto(listing_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)  # brief stabilization for listing content
            self._wait_for_captcha_solved(page, f"listing {listing_id}")
            page.wait_for_timeout(2000)  # allow page to settle after captcha solve
            record = self._extract_from_listing_page(
                page,
                listing_id=listing_id,
                original_url=listing_url,
                filtered_search_url=filtered_search_url,
                search_page_number=search_page_number,
            )

            # Enforce publication date freshness filter (-3 months)
            cutoff_date = (datetime.now(timezone.utc) - timedelta(days=90)).date()
            if record.publication_date_iso:
                try:
                    pub_date = datetime.strptime(record.publication_date_iso, "%Y-%m-%d").date()
                    if pub_date < cutoff_date:
                        logging.info(
                            f"Listing {listing_id} publication date {pub_date} "
                            f"FAILED 3-month filter (cutoff {cutoff_date}), skipping listing."
                        )
                        self.run_summary.total_listings_filtered_by_date += 1
                        # Do not download images or persist debug artifacts for filtered-out-by-date listings.
                        return
                    else:
                        logging.info(
                            f"Listing {listing_id} publication date {pub_date} "
                            f"PASSED 3-month filter (cutoff {cutoff_date})."
                        )
                except Exception as e:
                    logging.warning(
                        f"Failed to interpret publication_date_iso '{record.publication_date_iso}' "
                        f"for listing {listing_id}: {e}"
                    )

            # Enforce city skip filter: drop listings whose parsed city is explicitly not relevant.
            if record.city and record.city in self.cities_to_skip:
                logging.info(
                    f"Listing {listing_id} city '{record.city}' is in cities_to_skip, "
                    "skipping listing without downloading images or debug artifacts."
                )
                self.run_summary.total_listings_filtered_by_city += 1
                return

            # Enforce maximum total floors filter: if the building has more than 7
            # floors in total, skip this listing (user preference).
            if record.floor_total is not None and record.floor_total > 7:
                logging.info(
                    f"Listing {listing_id} has floor_total={record.floor_total} (> 7), "
                    "skipping listing without downloading images or debug artifacts."
                )
                self.run_summary.total_listings_filtered_by_floor += 1
                return

            # Download images (best-effort, not critical).
            # Only reached for listings that passed all filters (date, city, etc.).
            self._download_images(listing_id, page, record)

            # Validate critical fields and save debug evidence if needed
            self._validate_critical_fields(record, page)

            # Persist record to CSV and summary JSON after each listing
            self._append_record_to_csv(record)
            self._persist_run_summary()
        except Exception as e:
            logging.error(f"Failed to process listing {listing_id}: {e}", exc_info=True)
            self.run_summary.total_failed_rows += 1
            self._save_debug_artifacts(page, listing_id, f"exception: {e}")
        finally:
            page.close()


def main() -> None:
    load_dotenv()

    import argparse

    parser = argparse.ArgumentParser(description="Yad2 Center & Sharon real estate scraper")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="output",
        help="Root folder for all outputs (can be absolute or relative, default: ./output)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=4,
        help="Number of search result pages to visit per area (default: 4)",
    )
    parser.add_argument(
        "--captcha-avoidance-min",
        type=float,
        default=0.0,
        help="Minutes to sleep between pages to reduce CAPTCHA risk (0 = no delay, default: 0)",
    )
    parser.add_argument(
        "--headless",
        type=int,
        choices=[0, 1],
        default=1,
        help=(
            "Control browser UI visibility: 1 (default) runs Chromium in headless mode "
            "(no visible window), 0 runs with a visible browser window (useful for debugging "
            "and manually solving captchas)."
        ),
    )
    parser.add_argument(
        "--areas",
        type=str,
        default="",
        help=(
            "Comma-separated list of Yad2 'area' names (as in assets/yad2_area_IDs.json, "
            "under the 'area' key) to iterate over. Example: "
            "--areas 'Rishon LeZion Area, Netanya Area'. If omitted, the scraper will "
            "search only by big_area (Center and Sharon) without a multiArea filter."
        ),
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)

    # Interpret headless flag: 1 => True (no UI, default), 0 => False (visible window).
    headless_bool = bool(args.headless)

    # Parse areas from comma-separated CLI argument into a list of area names.
    areas_list: List[str] = []
    if args.areas:
        for part in args.areas.split(","):
            name = part.strip()
            if name:
                areas_list.append(name)

    geocoding_email = os.getenv("GEOCODING_EMAIL", "example@example.com")
    geocoder = Geocoder(email=geocoding_email)

    ors_api_key = os.getenv("ORS_API_KEY")
    route_calculator = None
    if ors_api_key:
        route_calculator = RouteCalculator(api_key=ors_api_key)
    else:
        logging.warning("ORS_API_KEY not set, routing will be skipped.")

    # Load cities_to_skip from dedicated config file, if present.
    # Expected path: config/yad2_config.json with structure:
    # {
    #   "cities_to_skip": ["חיפה", "ירושלים"]
    # }
    config_path = Path("config") / "yad2_config.json"
    cities_to_skip_list: List[str] = []
    if config_path.exists():
        try:
            raw_config = json.loads(config_path.read_text(encoding="utf-8"))
            raw_cities = raw_config.get("cities_to_skip", []) or []
            for c in raw_cities:
                if c is None:
                    continue
                name = str(c).strip()
                if name:
                    cities_to_skip_list.append(name)
        except Exception as e:
            logging.warning(f"Failed to load cities_to_skip from {config_path}: {e}")

    scraper = Yad2Scraper(
        output_dir=output_dir,
        geocoder=geocoder,
        route_calculator=route_calculator,
        max_pages=args.max_pages,
        captcha_avoidance_min=args.captcha_avoidance_min,
        headless=headless_bool,
        cities_to_skip=cities_to_skip_list,
        areas=areas_list,
    )
    scraper.scrape()

    print(f"CSV path: {scraper.output_csv}")
    print(f"Images dir: {scraper.images_dir}")
    print(f"Debug dir: {scraper.debug_dir}")
    print(f"Run summary: {scraper.run_summary_path}")


if __name__ == "__main__":
    main()

