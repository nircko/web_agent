"""
Shared listing HTML/JSON extraction for Yad2 and Madlan.

- Numeric parsers used by both pipelines
- Yad2 can import parse_float/parse_int to avoid duplication
"""

from __future__ import annotations

import re
from typing import Optional


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
