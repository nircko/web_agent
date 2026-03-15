"""
Build Madlan (madlan.co.il) search URLs for for-sale listings.

URL shape: https://www.madlan.co.il/for-sale/{location_slugs}?filters={filter_string}&tracking_search_source=filter_apply

Filter string (underscore-separated segments):
  _priceMin-priceMax_roomsMin-roomsMax_condition_sellerType____-maxFloor_minSqm-__0-100000_______search-filter-top-marketplace
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

logger = logging.getLogger(__name__)

MADLAN_BASE = "https://www.madlan.co.il"
MADLAN_FOR_SALE = "/for-sale"


def load_madlan_config(json_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load assets/madlan_config.json (location slugs, condition/seller mappings)."""
    path = json_path or Path(__file__).resolve().parent / "assets" / "madlan_config.json"
    if not path.exists():
        raise FileNotFoundError(f"Madlan config not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def _resolve_location_slugs(
    locations: List[str],
    config: Dict[str, Any],
) -> str:
    """Resolve human-readable location names to Madlan URL slugs."""
    slug_map = config.get("location_slugs") or {}
    if not isinstance(slug_map, dict):
        slug_map = {}
    resolved: List[str] = []
    for loc in (locations or []):
        name = str(loc).strip()
        if not name:
            continue
        if name in slug_map:
            resolved.append(slug_map[name])
        else:
            if "-" in name and " " not in name:
                resolved.append(name)
            else:
                logger.warning("Unknown Madlan location %r; add to assets/madlan_config.json location_slugs", name)
                resolved.append(name.replace(" ", "-") + "-ישראל")
    return ",".join(resolved) if resolved else ""


def build_madlan_for_sale_url(
    location_slugs: str,
    price_min: int = 1900000,
    price_max: int = 2500000,
    rooms_min: int = 4,
    rooms_max: int = 6,
    property_condition: Optional[List[str]] = None,
    seller_type: str = "private",
    max_floor: int = 4,
    min_sqm: int = 90,
    vaad_max: int = 100000,
    page: Optional[int] = None,
    tracking_source: str = "filter_apply",
) -> str:
    """Build a full Madlan for-sale search URL. seller_type: 'private' or 'agency'."""
    if not location_slugs:
        location_slugs = "חיפה-ישראל"
    condition_str = ",".join(property_condition or ["toRenovated", "preserved"])
    filter_parts = [
        f"_{price_min}-{price_max}",
        f"_{rooms_min}-{rooms_max}",
        f"_{condition_str}",
        f"_{seller_type}",
        "____",
        f"-{max_floor}",
        f"_{min_sqm}-",
        "_",
        f"0-{vaad_max}",
        "_______",
        "search-filter-top-marketplace",
    ]
    filter_string = "".join(filter_parts)
    path_slug = quote(location_slugs, safe=",")
    path = f"{MADLAN_FOR_SALE}/{path_slug}"
    params: List[str] = [f"filters={quote(filter_string, safe='')}", f"tracking_search_source={tracking_source}"]
    if page is not None and page > 1:
        params.append(f"page={page}")
    return f"{MADLAN_BASE}{path}?{'&'.join(params)}"


def build_madlan_url_from_preferences(
    config: Dict[str, Any],
    locations: Optional[List[str]] = None,
    price_min: Optional[int] = None,
    price_max: Optional[int] = None,
    rooms_min: Optional[int] = None,
    rooms_max: Optional[int] = None,
    property_condition: Optional[List[str]] = None,
    seller_type: Optional[str] = None,
    max_floor: Optional[int] = None,
    min_sqm: Optional[int] = None,
    page: Optional[int] = None,
    url_filters: Optional[Dict[str, Any]] = None,
) -> str:
    """Build Madlan for-sale URL from a preferences dict. Uses url_filters to override."""
    uf = url_filters or {}
    locations = locations or uf.get("madlan_locations") or uf.get("locations") or ["חיפה"]
    slug_str = _resolve_location_slugs(
        locations if isinstance(locations, list) else [locations],
        config,
    )
    condition_map = config.get("property_condition_values") or {}
    cond_raw = property_condition or uf.get("property_condition")
    if isinstance(cond_raw, list):
        cond_list = [condition_map.get(str(c), str(c)) for c in cond_raw]
    else:
        cond_list = ["toRenovated", "preserved"]
    seller_map = config.get("seller_type_values") or {}
    seller = seller_type or uf.get("seller_type") or "private"
    seller = seller_map.get(seller, seller) if isinstance(seller_map, dict) else seller

    return build_madlan_for_sale_url(
        location_slugs=slug_str,
        price_min=int(price_min or uf.get("price_min") or uf.get("minPrice") or 1900000),
        price_max=int(price_max or uf.get("price_max") or uf.get("maxPrice") or 2500000),
        rooms_min=int(rooms_min or uf.get("rooms_min") or uf.get("minRooms") or 4),
        rooms_max=int(rooms_max or uf.get("rooms_max") or uf.get("maxRooms") or 6),
        property_condition=cond_list,
        seller_type=seller,
        max_floor=int(max_floor or uf.get("max_floor") or uf.get("maxFloor") or 4),
        min_sqm=int(min_sqm or uf.get("min_square_meters") or uf.get("minSquareMeterBuild") or 90),
        page=page,
    )
