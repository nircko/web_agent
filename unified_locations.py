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
_CACHE: Optional[Dict[str, Any]] = None


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

    for part in (location_input or "").split(","):
        canonical = _normalize_token(part, aliases, locations)
        if not canonical or canonical not in locations:
            if part.strip():
                logger.warning("Unknown location %r; add to assets/unified_location_names.json", part.strip())
            continue
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
