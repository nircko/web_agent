"""
Unified English location names for Yad2 and Madlan.

Resolves input like "Haifa" or "Haifa, Rehovot" to platform-specific values using
assets/unified_location_names.json. Supports aliases (e.g. Hebrew or "Haifa Area").
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path(__file__).resolve().parent / "assets" / "unified_location_names.json"
_YAD2_AREA_IDS_PATH = Path(__file__).resolve().parent / "assets" / "yad2_area_IDs.json"
_CACHE: Optional[Dict[str, Any]] = None
_YAD2_AREA_CACHE: Optional[Dict[str, str]] = None


def _load_yad2_area_ids(path: Optional[Path] = None) -> Dict[str, str]:
    """Load yad2_area_IDs.json and return the 'area' dict (area name -> id). Cached."""
    global _YAD2_AREA_CACHE
    if _YAD2_AREA_CACHE is not None:
        return _YAD2_AREA_CACHE
    p = path or _YAD2_AREA_IDS_PATH
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    _YAD2_AREA_CACHE = data.get("area") or {}
    return _YAD2_AREA_CACHE


def _find_yad2_area_key(token: str, area_dict: Dict[str, str]) -> Optional[str]:
    """Return the area key from yad2_area_IDs that matches token (with _ normalized to space)."""
    key = (token or "").strip().replace("_", " ")
    if not key:
        return None
    if key in area_dict:
        return key
    key_lower = key.lower()
    for k in area_dict.keys():
        if k.lower() == key_lower:
            return k
    return None


def load_unified_locations(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load unified_location_names.json (cached)."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    p = path or _DEFAULT_PATH
    if not p.exists():
        raise FileNotFoundError(f"Unified locations not found: {p}")
    with p.open("r", encoding="utf-8") as f:
        _CACHE = json.load(f)
    return _CACHE


def _normalize_token(token: str, aliases: Dict[str, str], locations: Dict[str, Any]) -> Optional[str]:
    """Return canonical English key for this token, or None if unknown."""
    t = (token or "").strip()
    if not t:
        return None
    # Direct key (case-insensitive)
    for key in locations.keys():
        if key.lower() == t.lower():
            return key
    # Alias
    if t in aliases:
        return aliases[t]
    for alias, canonical in aliases.items():
        if alias.lower() == t.lower():
            return canonical
    return None


def resolve_locations_to_yad2(
    location_input: str,
    path: Optional[Path] = None,
) -> Tuple[List[str], List[str], str]:
    """
    Resolve unified location string (e.g. "Haifa, Rehovot") to Yad2 areas and cities.

    Returns:
        (areas, cities, export_slug)
    """
    data = load_unified_locations(path)
    locations = data.get("locations") or {}
    aliases = data.get("aliases") or {}
    areas: List[str] = []
    cities: List[str] = []
    slugs: List[str] = []

    yad2_areas = _load_yad2_area_ids()

    for part in (location_input or "").split(","):
        canonical = _normalize_token(part, aliases, locations)
        if canonical and canonical in locations:
            entry = locations[canonical]
            yad2_area = entry.get("yad2_area")
            yad2_city = entry.get("yad2_city")
            if yad2_area and yad2_area not in areas:
                areas.append(yad2_area)
            if yad2_city and yad2_city not in cities:
                cities.append(yad2_city)
            slug = entry.get("export_slug") or canonical.replace(" ", "_")
            if slug not in slugs:
                slugs.append(slug)
            continue
        # Fallback: treat token as Yad2 area name (e.g. "Haifa Area" or "Haifa_Area")
        part_stripped = part.strip()
        if part_stripped:
            area_key = _find_yad2_area_key(part_stripped, yad2_areas)
            if area_key:
                if area_key not in areas:
                    areas.append(area_key)
                slug = part_stripped.replace(" ", "_")
                if slug not in slugs:
                    slugs.append(slug)
            else:
                logger.warning("Unknown location %r; add to assets/unified_location_names.json or use a Yad2 area name from assets/yad2_area_IDs.json", part_stripped)

    export_slug = "_".join(slugs) if slugs else "listings"
    return areas, cities, export_slug


def resolve_locations_to_madlan(
    location_input: str,
    path: Optional[Path] = None,
) -> Tuple[List[str], str]:
    """
    Resolve unified location string to Madlan Hebrew locations and export slug.

    Returns:
        (madlan_locations, export_slug)
    """
    data = load_unified_locations(path)
    locations = data.get("locations") or {}
    aliases = data.get("aliases") or {}
    madlan_list: List[str] = []
    slugs: List[str] = []

    for part in (location_input or "").split(","):
        canonical = _normalize_token(part, aliases, locations)
        if not canonical or canonical not in locations:
            # Pass through as-is (might be Hebrew or existing slug)
            raw = part.strip()
            if raw and raw not in madlan_list:
                madlan_list.append(raw)
                slugs.append(raw.replace(" ", "_").replace("-", "_"))
            continue
        entry = locations[canonical]
        he = entry.get("madlan_location")
        if he and he not in madlan_list:
            madlan_list.append(he)
        slug = entry.get("export_slug") or canonical.replace(" ", "_")
        if slug not in slugs:
            slugs.append(slug)

    export_slug = "_".join(slugs) if slugs else "listings"
    return madlan_list, export_slug
