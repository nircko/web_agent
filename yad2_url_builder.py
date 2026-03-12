import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Union
from urllib.parse import urlencode


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


def build_yad2_url_from_json(
    mappings: JsonMapping,
    *,
    big_area: str = "Center and Sharon",
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
) -> str:
    """
    Build a Yad2 search URL using the canonical area/city ID mappings JSON.

    Parameters mirror the original helper, but with stricter typing and
    safer validation:

    - `mappings`: loaded from `assets/yad2_area_IDs.json` via `load_mappings`.
    - `big_area`: human-readable region name, e.g. "Center and Sharon".
    - `listing_type`: Yad2 listing type segment, e.g. "forsale".
    - `areas`: list of human-readable area names or numeric IDs.
    - `cities`: list of human-readable city names or numeric IDs.
    - `neighborhoods`: list of neighborhood IDs (str or int).
    - `min_price`, `max_price`, `max_floor`, `min_square_meter_build`: core filters.
    - `property_condition`: list of condition indices (defaults to [5, 3]).
    - `page`: search page number.
    - `extra_filters`: arbitrary extra query params; if a value is a list,
      it's joined with commas.

    The function will raise ValueError if `big_area` or any area/city name
    is not present in the mapping (to fail fast instead of silently
    generating a wrong URL).
    """
    big_area_map = mappings.get("big_area") or {}
    area_map = mappings.get("area") or {}
    city_map = mappings.get("city") or {}

    if not isinstance(big_area_map, dict) or not isinstance(area_map, dict) or not isinstance(city_map, dict):
        raise ValueError("Unexpected mappings structure: expected 'big_area', 'area', and 'city' dicts.")

    base = "https://www.yad2.co.il"

    if big_area not in big_area_map:
        raise ValueError(f"Unknown big_area: {big_area!r}")

    path = f"/realestate/{listing_type}/{big_area_map[big_area]}"

    query: Dict[str, Any] = {
        "minPrice": int(min_price),
        "maxPrice": int(max_price),
        "maxFloor": int(max_floor),
        "minSquareMeterBuild": int(min_square_meter_build),
        "page": int(page),
    }

    if property_condition is None:
        property_condition = [5, 3]
    query["propertyCondition"] = ",".join(str(int(x)) for x in property_condition)

    area_ids = _resolve_values(areas, area_map, "area")
    city_ids = _resolve_values(cities, city_map, "city")

    if area_ids:
        query["multiArea"] = area_ids
    if city_ids:
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

