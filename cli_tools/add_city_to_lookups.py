"""
Add a new city to all location/city lookup tables under assets/.

Input: city name in English, its district (Yad2 district name), and Yad2 city ID.
Optional: Madlan Hebrew name for the city (for Madlan search and unified lookups).

Updates:
  - assets/yad2_area_IDs.json  (city_to_district, city)
  - assets/unified_location_names.json (locations, aliases; madlan_location if Hebrew given)
  - assets/madlan_config.json (location_slugs if Hebrew given)

All city and location JSON files live under assets/.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Default assets dir: project root / assets (parent of this script = project root when run from repo)
DEFAULT_ASSETS = Path(__file__).resolve().parent.parent / "assets"

# Valid Yad2 district names (keys in yad2_area_IDs district or values in area_to_district)
VALID_DISTRICTS = {
    "Tel Aviv and surroundings",
    "Center and Sharon",
    "Jerusalem and surroundings",
    "Northern Coastal Plain",
    "North and Valleys",
    "South",
}


def add_city_to_lookups(
    city_english: str,
    district: str,
    yad2_city_id: str,
    madlan_hebrew: str | None = None,
    assets_dir: Path | None = None,
) -> None:
    """
    Add a new city to assets/yad2_area_IDs.json, unified_location_names.json, and optionally madlan_config.json.

    Args:
        city_english: City name in English (e.g. "Tirat Carmel").
        district: Yad2 district name (e.g. "Northern Coastal Plain"). Must be one of VALID_DISTRICTS.
        yad2_city_id: Yad2 city ID string (e.g. "2100").
        madlan_hebrew: Optional Hebrew name for Madlan (e.g. "טירת כרמל"). If given, adds to unified locations and madlan_config.
        assets_dir: Path to assets folder. Default: project assets/.
    """
    assets_dir = Path(assets_dir or DEFAULT_ASSETS)
    if not assets_dir.is_dir():
        raise FileNotFoundError(f"Assets directory not found: {assets_dir}")

    district = district.strip()
    if district not in VALID_DISTRICTS:
        raise ValueError(
            f"Invalid district {district!r}. Must be one of: {sorted(VALID_DISTRICTS)}"
        )

    city_english = city_english.strip()
    if not city_english:
        raise ValueError("city_english must be non-empty")

    yad2_city_id = str(yad2_city_id).strip()
    if not yad2_city_id.isdigit():
        raise ValueError(f"yad2_city_id must be numeric, got {yad2_city_id!r}")

    # Normalize for JSON keys (Yad2 city list often uses exact display names)
    city_key = city_english

    # --- 1. yad2_area_IDs.json ---
    yad2_path = assets_dir / "yad2_area_IDs.json"
    if not yad2_path.exists():
        raise FileNotFoundError(f"Missing {yad2_path}")
    with open(yad2_path, "r", encoding="utf-8") as f:
        yad2 = json.load(f)
    city_to_district = yad2.get("city_to_district") or {}
    city_ids = yad2.get("city") or {}
    if city_key in city_to_district and city_to_district[city_key] == district and city_ids.get(city_key) == yad2_city_id:
        pass  # already present
    else:
        city_to_district[city_key] = district
        city_ids[city_key] = yad2_city_id
        yad2["city_to_district"] = city_to_district
        yad2["city"] = city_ids
        with open(yad2_path, "w", encoding="utf-8") as f:
            json.dump(yad2, f, ensure_ascii=False, indent=2)
        print(f"Updated {yad2_path}: city_to_district and city for {city_key!r}")

    # --- 2. unified_location_names.json ---
    unified_path = assets_dir / "unified_location_names.json"
    if not unified_path.exists():
        raise FileNotFoundError(f"Missing {unified_path}")
    with open(unified_path, "r", encoding="utf-8") as f:
        unified = json.load(f)
    locations = unified.get("locations") or {}
    aliases = unified.get("aliases") or {}
    # Use English as canonical key; yad2_city for Yad2, optional madlan_location
    entry = {
        "yad2_area": None,
        "yad2_city": city_key,
        "export_slug": city_key.replace(" ", "_"),
    }
    if madlan_hebrew and madlan_hebrew.strip():
        entry["madlan_location"] = madlan_hebrew.strip()
    else:
        entry["madlan_location"] = None
    if city_key not in locations:
        locations[city_key] = entry
        unified["locations"] = locations
        if city_key not in aliases:
            aliases[city_key] = city_key
        unified["aliases"] = aliases
        with open(unified_path, "w", encoding="utf-8") as f:
            json.dump(unified, f, ensure_ascii=False, indent=2)
        print(f"Updated {unified_path}: locations and aliases for {city_key!r}")
    else:
        # Update existing if we're adding madlan_location
        if madlan_hebrew and madlan_hebrew.strip() and (not locations[city_key].get("madlan_location")):
            locations[city_key]["madlan_location"] = madlan_hebrew.strip()
            with open(unified_path, "w", encoding="utf-8") as f:
                json.dump(unified, f, ensure_ascii=False, indent=2)
            print(f"Updated {unified_path}: added madlan_location for {city_key!r}")

    # --- 3. madlan_config.json (location_slugs) ---
    if madlan_hebrew and madlan_hebrew.strip():
        madlan_path = assets_dir / "madlan_config.json"
        if madlan_path.exists():
            with open(madlan_path, "r", encoding="utf-8") as f:
                madlan = json.load(f)
            slugs = madlan.get("location_slugs") or {}
            hebrew = madlan_hebrew.strip()
            slug_val = hebrew.replace(" ", "-") + "-ישראל"
            if hebrew not in slugs or slugs[hebrew] != slug_val:
                slugs[hebrew] = slug_val
                madlan["location_slugs"] = slugs
                with open(madlan_path, "w", encoding="utf-8") as f:
                    json.dump(madlan, f, ensure_ascii=False, indent=2)
                print(f"Updated {madlan_path}: location_slugs for {hebrew!r}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Add a new city to assets location lookups (yad2_area_IDs, unified_location_names, madlan_config)."
    )
    parser.add_argument("city_english", help="City name in English (e.g. Tirat Carmel)")
    parser.add_argument(
        "district",
        help="Yad2 district name (e.g. Northern Coastal Plain). Use one of: " + ", ".join(sorted(VALID_DISTRICTS)),
    )
    parser.add_argument("yad2_city_id", help="Yad2 city ID (e.g. 2100)")
    parser.add_argument(
        "--madlan-hebrew",
        default=None,
        help="Madlan Hebrew name for the city (e.g. טירת כרמל)",
    )
    parser.add_argument(
        "--assets-dir",
        type=Path,
        default=None,
        help="Path to assets directory (default: project assets/)",
    )
    args = parser.parse_args()
    try:
        add_city_to_lookups(
            city_english=args.city_english,
            district=args.district,
            yad2_city_id=args.yad2_city_id,
            madlan_hebrew=args.madlan_hebrew,
            assets_dir=args.assets_dir,
        )
    except (ValueError, FileNotFoundError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
