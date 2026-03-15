"""
Shared listing HTML/JSON extraction for Yad2 and Madlan.

- Numeric parsers used by both pipelines
- Madlan: window.__SSR_HYDRATED_CONTEXT__ (addressSearch.poi)
- Yad2 can import parse_float/parse_int to avoid duplication
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup


def parse_float(text: Optional[str]) -> Optional[float]:
    if not text:
        return None
    try:
        cleaned = re.sub(r"[^\d.]", "", str(text).replace(",", ""))
        return float(cleaned) if cleaned else None
    except Exception:
        return None


def parse_int(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    try:
        cleaned = re.sub(r"\D", "", str(text))
        return int(cleaned) if cleaned else None
    except Exception:
        return None


# --- JSON from inline script (balanced braces) ---


def extract_ssr_hydrated_context(html: str) -> Optional[Dict[str, Any]]:
    """Parse window.__SSR_HYDRATED_CONTEXT__ = {...} from listing HTML."""
    for marker in ("__SSR_HYDRATED_CONTEXT__", "SSR_HYDRATED_CONTEXT"):
        if marker not in html:
            continue
        idx = html.find(marker)
        sub = html[idx : idx + 50000]
        eq = sub.find("=")
        if eq < 0:
            continue
        blob_start = sub.find("{", eq)
        if blob_start < 0:
            continue
        depth = 0
        in_str = False
        esc = False
        for k in range(blob_start, len(sub)):
            ch = sub[k]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(sub[blob_start : k + 1])
                    except json.JSONDecodeError:
                        break
    return None


def deep_find_poi_ssr(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Walk SSR context for addressSearch -> poi (buildingYear, floor, totalFloors, etc.)."""
    out: Dict[str, Any] = {}

    def walk(obj: Any, depth: int = 0) -> None:
        if depth > 25:
            return
        if isinstance(obj, dict):
            if "addressSearch" in obj and isinstance(obj["addressSearch"], dict):
                as_ = obj["addressSearch"]
                poi = as_.get("poi")
                if isinstance(poi, dict):
                    out.update(poi)
            for v in obj.values():
                walk(v, depth + 1)
        elif isinstance(obj, list):
            for x in obj:
                walk(x, depth + 1)

    walk(ctx)
    try:
        as_ = ctx.get("addressSearch") or {}
        if isinstance(as_, dict) and isinstance(as_.get("poi"), dict):
            out.update(as_["poi"])
    except Exception:
        pass
    return out


def extract_assumed_design_range(ctx: Dict[str, Any], html: str) -> Optional[str]:
    """assumedDesignRange in SSR or similar; else scan HTML."""
    if isinstance(ctx, dict):

        def find_key(d: Any, key: str) -> Any:
            if isinstance(d, dict):
                if key in d:
                    return d[key]
                for v in d.values():
                    r = find_key(v, key)
                    if r is not None:
                        return r
            elif isinstance(d, list):
                for x in d:
                    r = find_key(x, key)
                    if r is not None:
                        return r
            return None

        v = find_key(ctx, "assumedDesignRange")
        if v is not None:
            return str(v)
    m = re.search(r"assumedDesignRange[\"']?\s*:\s*[\"']([^\"']+)", html)
    if m:
        return m.group(1)
    return None


def extract_breadcrumb_items(soup: BeautifulSoup) -> List[str]:
    """BreadcrumbList itemListElement -> names for building scale heuristics."""
    names: List[str] = []
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        items = _ld_breadcrumb_items(data)
        names.extend(items)
    for nav in soup.find_all(["nav", "ol", "ul"], class_=re.compile("breadcrumb", re.I)):
        for a in nav.find_all("a"):
            t = (a.get_text() or "").strip()
            if t and len(t) < 80:
                names.append(t)
    return list(dict.fromkeys(names))


def _ld_breadcrumb_items(data: Any) -> List[str]:
    out: List[str] = []
    if isinstance(data, dict):
        if data.get("@type") == "BreadcrumbList" and "itemListElement" in data:
            for it in data.get("itemListElement") or []:
                if isinstance(it, dict):
                    name = it.get("name") or (it.get("item") or {}).get("name")
                    if name:
                        out.append(str(name))
        for v in data.values():
            out.extend(_ld_breadcrumb_items(v))
    elif isinstance(data, list):
        for x in data:
            out.extend(_ld_breadcrumb_items(x))
    return out


def extract_schema_org_real_estate_features(soup: BeautifulSoup) -> Dict[str, Any]:
    """Parse JSON-LD RealEstateListing: additionalProperty name/value -> features."""
    features: Dict[str, str] = {}
    for script in soup.find_all("script", type="application/ld+json"):
        raw = (script.string or script.get_text() or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        _walk_additional_property(data, features)
    return features


def _walk_additional_property(obj: Any, out: Dict[str, str]) -> None:
    if isinstance(obj, dict):
        if "additionalProperty" in obj:
            for prop in obj.get("additionalProperty") or []:
                if not isinstance(prop, dict):
                    continue
                name = (prop.get("name") or prop.get("@type") or "").strip()
                val = prop.get("value")
                if val is not None:
                    out[name or "unknown"] = str(val).strip()
        for v in obj.values():
            _walk_additional_property(v, out)
    elif isinstance(obj, list):
        for x in obj:
            _walk_additional_property(x, out)


# Hebrew condition -> English (Madlan / Yad2 labels)
CONDITION_HE_TO_EN = {
    "משופצת": "renovated",
    "לשיפוץ": "to renovate",
    "דורש שיפוץ": "needs renovation",
    "שמורה": "well maintained",
    "חדש": "new",
    "חדשה": "new",
    "משופץ": "renovated",
    "במצב טוב": "good condition",
}


def translate_condition_label(hebrew: str) -> str:
    t = (hebrew or "").strip()
    for he, en in CONDITION_HE_TO_EN.items():
        if he in t:
            return en
    return t or "unknown"


# Investment / description keywords (Hebrew -> English tags)
TRANSIT_KEYWORDS = [
    ("רק\"ל", "light_rail"),
    ("רקל", "light_rail"),
    ("מטרו", "metro"),
    ("איילון", "ayalon_highway"),
    ("רכבת", "train"),
]
NUISANCE_KEYWORDS = [
    ("חניה", "parking"),
    ("חניות", "parking"),
    ("רעש", "noise"),
    ("בנייה", "construction"),
]


def extract_investment_context_from_text(text: str) -> Tuple[str, str]:
    """Returns (transit_mentions_en, nuisance_mentions_en) comma-separated tags."""
    if not text:
        return "", ""
    transit = []
    for he, tag in TRANSIT_KEYWORDS:
        if he in text:
            transit.append(tag)
    nuis = []
    for he, tag in NUISANCE_KEYWORDS:
        if he in text:
            nuis.append(tag)
    return ", ".join(sorted(set(transit))), ", ".join(sorted(set(nuis)))


def map_schema_boolean_to_amenities(features: Dict[str, str]) -> Dict[str, bool]:
    """Map Hebrew/English additionalProperty labels to booleans (elevator, mamad, etc.)."""
    elevator = mamad = ac = balcony = solar = bars = False
    full = " ".join(f"{k} {v}" for k, v in features.items()).lower()

    def yes(v: str) -> bool:
        return v in ("yes", "כן", "true", "1") or "כן" in v

    for k, v in features.items():
        kl = k.lower()
        vl = v.lower()
        if "מעלית" in k or "elevator" in kl:
            elevator = yes(vl) or "כן" in v
        if "ממד" in k or "מיק" in k or "safe" in kl or "mamad" in kl:
            mamad = yes(vl) or "כן" in v
        if "מיזוג" in k or "air" in kl:
            ac = yes(vl) or "כן" in v
        if "מרפסת" in k or "balcony" in kl:
            balcony = yes(vl) or "כן" in v
        if "שמש" in k or "סולאר" in k or "solar" in kl:
            solar = yes(vl) or "כן" in v
        if "סורג" in k or "bars" in kl or "גריל" in k:
            bars = yes(vl) or "כן" in v

    if "מעלית" in full:
        elevator = True
    if "ממ\"ד" in full or "ממד" in full:
        mamad = True
    return {
        "elevator": elevator,
        "mamad": mamad,
        "air_conditioning": ac,
        "balcony": balcony,
        "solar_heater": solar,
        "window_bars": bars,
    }


def build_technical_profile_en(
    *,
    year_built: Optional[int],
    total_floors_building: Optional[int],
    apartment_floor: Optional[int],
    price_ils: Optional[float],
    built_sqm: Optional[float],
    rooms: Optional[float],
    condition_en: Optional[str],
    assumed_design_range: Optional[str],
    amenities: Dict[str, bool],
    transit_tags: str,
    nuisance_tags: str,
) -> str:
    """Single English summary block for CSV/debug."""
    lines = []
    lines.append("Construction: year_built=%s, total_floors=%s, apartment_floor=%s, scale=%s" % (
        year_built, total_floors_building, apartment_floor, assumed_design_range or "—"
    ))
    pps = (price_ils / built_sqm) if price_ils and built_sqm and built_sqm > 0 else None
    lines.append(
        "Financials: price=%s, price_per_sqm=%s"
        % (price_ils, round(pps, 1) if pps else "—")
    )
    lines.append(
        "Technical: size_sqm=%s, rooms=%s, condition=%s"
        % (built_sqm, rooms, condition_en or "—")
    )
    on = [k for k, v in amenities.items() if v]
    lines.append("Amenities: %s" % (", ".join(on) or "—"))
    lines.append("Investment: transit=[%s], nuisances=[%s]" % (transit_tags or "—", nuisance_tags or "—"))
    return " | ".join(lines)
