import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple, Union
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


JsonMapping = Mapping[str, Any]
StrOrInt = Union[str, int]


def load_mappings(json_path: Union[str, Path]) -> JsonMapping:
    """
    Load the Yad2 area/city mapping JSON.

    The repository already ships a canonical mapping file under:
    `assets/yad2_area_IDs.json`.

    This helper normalizes the path argument to a `Path` and returns a
    read-only mapping (dict-like) of all IDs.
    """
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"Yad2 mappings file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected top-level object in {path}, got {type(data)!r}")
    return data


def _resolve_values(
    values: Optional[Iterable[StrOrInt]],
    mapping: Mapping[str, str],
    label: str,
) -> Optional[str]:
    """
    Resolve human-readable names or raw IDs into a comma-separated string
    of numeric IDs using the provided `mapping`.

    Rules:
    - If `values` is None or empty: return None.
    - For each value:
      - If it's an int: use its string form as-is.
      - If it's a str:
        - If it exactly matches a key in `mapping`: use `mapping[value]`.
        - Else if it is purely digits: accept as raw ID.
        - Else: raise a ValueError (unknown {label}).
    """
    if not values:
        return None

    resolved: List[str] = []
    for value in values:
        if isinstance(value, int):
            resolved.append(str(value))
            continue

        s = str(value).strip()
        if not s:
            continue

        if s in mapping:
            resolved.append(mapping[s])
        elif s.isdigit():
            resolved.append(s)
        else:
            raise ValueError(f"Unknown {label}: {s!r}")

    return ",".join(resolved) if resolved else None


# Yad2 allows at most 3 cities in multiCity.
MAX_MULTI_CITIES = 3


def group_areas_and_cities_by_district(
    mappings: JsonMapping,
    areas: Optional[List[str]] = None,
    cities: Optional[List[str]] = None,
    default_district: str = "Center and Sharon",
) -> List[Tuple[str, List[str], List[str]]]:
    """
    Group requested areas and cities by their district so each group yields a valid Yad2 URL.

    - If both `areas` and `cities` are empty: returns [(default_district, [], [])].
    - Otherwise: resolves each area/city to a district via area_to_district / city_to_district.
      Raises ValueError if any area or city is unknown. Returns one tuple per district
      (district, areas_in_that_district, cities_in_that_district). Cities per district
      are capped at MAX_MULTI_CITIES (3).
    """
    area_to_district_map = mappings.get("area_to_district") or {}
    city_to_district_map = mappings.get("city_to_district") or {}
    if not isinstance(area_to_district_map, dict):
        area_to_district_map = {}
    if not isinstance(city_to_district_map, dict):
        city_to_district_map = {}

    areas = [a for a in (areas or []) if str(a).strip()]
    cities = [c for c in (cities or []) if c and str(c).strip()]

    if not areas and not cities:
        return [(default_district, [], [])]

    # Resolve each area/city to district; collect unknown for error message.
    unknown_areas: List[str] = []
    unknown_cities: List[str] = []
    by_district: Dict[str, Tuple[List[str], List[str]]] = {}

    for a in areas:
        key = str(a).strip()
        if key in area_to_district_map:
            d = area_to_district_map[key]
            if d not in by_district:
                by_district[d] = ([], [])
            by_district[d][0].append(key)
        else:
            unknown_areas.append(key)

    for c in cities:
        key = str(c).strip()
        if key in city_to_district_map:
            d = city_to_district_map[key]
            if d not in by_district:
                by_district[d] = ([], [])
            by_district[d][1].append(key)
        else:
            unknown_cities.append(key)

    if unknown_areas or unknown_cities:
        parts = []
        if unknown_areas:
            parts.append(f"unknown areas: {unknown_areas!r}")
        if unknown_cities:
            parts.append(f"unknown cities: {unknown_cities!r}")
        raise ValueError(
            "Areas and cities must match keys in assets/yad2_area_IDs.json (area_to_district / city_to_district). "
            + "; ".join(parts)
        )

    # Cap cities per district at MAX_MULTI_CITIES
    result: List[Tuple[str, List[str], List[str]]] = []
    for district, (area_list, city_list) in by_district.items():
        result.append((district, area_list, city_list[:MAX_MULTI_CITIES]))
    return result


def build_yad2_url_from_json(
    mappings: JsonMapping,
    *,
    district: Optional[str] = None,
    big_area: Optional[str] = None,
    listing_type: str = "forsale",
    areas: Optional[List[StrOrInt]] = None,
    cities: Optional[List[StrOrInt]] = None,
    neighborhoods: Optional[List[StrOrInt]] = None,
    min_price: int = 1600000,
    max_price: int = 3600000,
    max_floor: int = 4,
    min_square_meter_build: int = 90,
    property_condition: Optional[List[int]] = None,
    page: int = 1,
    extra_filters: Optional[Dict[str, Any]] = None,
    url_filters: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Build a Yad2 search URL using the canonical area/city ID mappings JSON.

    The asset file uses "district" for the path segment (e.g. "Center and Sharon" -> "center-and-sharon").
    Both "district" and "big_area" keys in the JSON are accepted; "district" takes precedence.

    - `mappings`: loaded from `assets/yad2_area_IDs.json` via `load_mappings`.
    - `district` or `big_area`: human-readable region name (e.g. "Center and Sharon"). Must match
      a key in mappings["district"] or mappings["big_area"].
    - `listing_type`: Yad2 listing type segment, e.g. "forsale".
    - `areas`: list of human-readable area names or numeric IDs (from the "area" mapping).
    - `cities`: list of human-readable city names or numeric IDs (from the "city" mapping).
      At most 3 cities are used; cities must be names that exist in the mapping.
    - `neighborhoods`: list of neighborhood IDs (str or int).
    - `min_price`, `max_price`, `max_floor`, `min_square_meter_build`: core URL filters.
    - `property_condition`: list of condition indices (defaults to [5, 3]).
    - `page`: search page number.
    - `extra_filters` / `url_filters`: extra query params; lists are joined with commas.
      `url_filters` overrides individual min_price, max_price, etc. when both are provided.

    Raises ValueError if district/big_area or any area/city name is not in the mapping.
    """
    district_map = mappings.get("district") or mappings.get("big_area") or {}
    area_map = mappings.get("area") or {}
    city_map = mappings.get("city") or {}

    if not isinstance(district_map, dict) or not isinstance(area_map, dict) or not isinstance(city_map, dict):
        raise ValueError("Unexpected mappings structure: expected 'district' (or 'big_area'), 'area', and 'city' dicts.")

    region_name = district or big_area or "Center and Sharon"
    if region_name not in district_map:
        raise ValueError(f"Unknown district/big_area: {region_name!r}. Use a key from assets/yad2_area_IDs.json.")

    base = "https://www.yad2.co.il"
    path = f"/realestate/{listing_type}/{district_map[region_name]}"

    # Start from url_filters if provided, then fill/override with explicit params
    query: Dict[str, Any] = {}
    if url_filters:
        for k, v in url_filters.items():
            if v is None:
                continue
            if isinstance(v, (list, tuple, set)):
                query[k] = ",".join(str(x) for x in v)
            else:
                query[k] = v

    query.setdefault("minPrice", int(min_price))
    query.setdefault("maxPrice", int(max_price))
    query.setdefault("maxFloor", int(max_floor))
    query.setdefault("minSquareMeterBuild", int(min_square_meter_build))
    query.setdefault("page", int(page))

    if property_condition is None:
        property_condition = [5, 3]
    query.setdefault("propertyCondition", ",".join(str(int(x)) for x in property_condition))

    area_ids = _resolve_values(areas, area_map, "area")
    # Cities: enforce max 3; names must match the "city" mapping (district-scoped in Yad2).
    cities_list: Optional[List[StrOrInt]] = None
    if cities:
        cities_list = list(cities)[:MAX_MULTI_CITIES]
        if len(cities) > MAX_MULTI_CITIES:
            logger.warning(
                f"Yad2 allows at most {MAX_MULTI_CITIES} cities; using first {MAX_MULTI_CITIES}: {cities_list}"
            )
    city_ids = _resolve_values(cities_list, city_map, "city")

    # Yad2 expects singular "area" / "city" (lowercase) when there is exactly one; "multiArea" / "multiCity" for multiple.
    if area_ids:
        if "," not in area_ids:
            query["area"] = area_ids
        else:
            query["multiArea"] = area_ids
    if city_ids:
        if "," not in city_ids:
            query["city"] = city_ids
        else:
            query["multiCity"] = city_ids
    if neighborhoods:
        query["multiNeighborhood"] = ",".join(str(n) for n in neighborhoods)

    if extra_filters:
        for k, v in extra_filters.items():
            if v is None:
                continue
            if isinstance(v, (list, tuple, set)):
                query[k] = ",".join(str(x) for x in v)
            else:
                query[k] = v

    return f"{base}{path}?{urlencode(query)}"

