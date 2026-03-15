"""
Shared listing HTML/JSON extraction for Yad2 and Madlan.

- Numeric parsers used by both pipelines
- Madlan: window.__SSR_HYDRATED_CONTEXT__ (addressSearch.poi)
- Yad2 can import parse_float/parse_int to avoid duplication
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

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
