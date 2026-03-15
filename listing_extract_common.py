"""
Shared listing HTML/JSON extraction for Yad2 and Madlan.

- Numeric parsers used by both pipelines
- Madlan: window.__SSR_HYDRATED_CONTEXT__ (addressSearch.poi)
- Yad2 can import parse_float/parse_int to avoid duplication
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional


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
