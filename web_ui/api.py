from __future__ import annotations

"""
FastAPI backend for the Listing Inspector web UI.

The recommended way to start this app is via the launcher scripts:
- macOS: scripts/launch_web_ui_macos.command
- Windows: scripts/launch_web_ui_windows.bat
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from run_listing_from_link import detect_source, run_listing


logger = logging.getLogger("web_ui")

app = FastAPI(title="Listing Inspector UI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    url: str


class AnalyzeResponse(BaseModel):
    success: bool
    error: Optional[str] = None
    source: Optional[str] = None
    listing_id: Optional[str] = None
    record: Optional[Dict[str, Any]] = None
    csv_line: Optional[str] = None
    first_published_date: Optional[str] = None
    last_update_date: Optional[str] = None


def _derive_dates(record: Dict[str, Any]) -> Dict[str, Optional[str]]:
    pub_iso = record.get("publication_date_iso")
    pub_raw = record.get("publication_date_raw")
    first_published = pub_iso or pub_raw

    # Last update: from dedicated fields if present (Madlan SSR helper),
    # then from extra_features "last_update:YYYY-MM-DD"
    last_update = None
    for key in ("last_update_iso", "last_update_raw"):
        if record.get(key):
            last_update = str(record[key])
            break
    if not last_update:
        extra = record.get("extra_features") or ""
        if isinstance(extra, str) and "last_update:" in extra:
            import re

            m = re.search(r"last_update:\s*([^\s|]+)", extra)
            if m:
                last_update = m.group(1).strip()

    return {
        "first_published_date": str(first_published) if first_published else None,
        "last_update_date": str(last_update) if last_update else None,
    }


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    """Serve the single-page UI."""
    html_path = Path(__file__).resolve().parent / "index.html"
    if not html_path.exists():
        return HTMLResponse("<h1>UI file web_ui/index.html is missing.</h1>", status_code=500)
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.post("/api/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    url = (req.url or "").strip()
    if not url:
        return AnalyzeResponse(success=False, error="URL is required")

    source = detect_source(url)
    if not source:
        return AnalyzeResponse(success=False, error="URL must be a Yad2 or Madlan listing (yad2.co.il / madlan.co.il)")

    logger.info("Analyzing URL from source %s: %s", source, url)
    out = run_listing(url, headless=False, csv_only=True)

    if out.get("error"):
        return AnalyzeResponse(
            success=False,
            error=str(out["error"]),
            source=out.get("source"),
            listing_id=out.get("listing_id"),
        )

    record_obj = out.get("record")
    record_dict: Optional[Dict[str, Any]] = None
    if record_obj is not None:
        try:
            record_dict = record_obj.model_dump()
        except Exception:
            # In case it's already a dict
            if isinstance(record_obj, Dict):
                record_dict = record_obj

    dates = _derive_dates(record_dict or {})

    return AnalyzeResponse(
        success=True,
        error=None,
        source=out.get("source"),
        listing_id=out.get("listing_id"),
        record=record_dict,
        csv_line=out.get("csv_line"),
        first_published_date=dates["first_published_date"],
        last_update_date=dates["last_update_date"],
    )

