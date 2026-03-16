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


class PreferencesPayload(BaseModel):
    scraper: Dict[str, Any]
    madlan: Dict[str, Any]


class PreferencesResult(BaseModel):
    success: bool
    error: Optional[str] = None
    data: Optional[PreferencesPayload] = None


class BatchRequest(BaseModel):
    website: str  # "yad2", "madlan", or "both"
    locations: Optional[str] = None
    price_min: Optional[int] = None
    price_max: Optional[int] = None
    rooms_min: Optional[int] = None
    rooms_max: Optional[int] = None
    max_floor: Optional[int] = None
    min_sqm: Optional[int] = None
    max_pages: Optional[int] = 4
    headless: bool = True
    output_dir_yad2: Optional[str] = None
    output_dir_madlan: Optional[str] = None
    # Inline preferences from the UI for this run only (do not touch disk)
    preferences: Optional[PreferencesPayload] = None


class BatchResult(BaseModel):
    success: bool
    error: Optional[str] = None
    log: str
    yad2_output_dir: Optional[str] = None
    madlan_output_dir: Optional[str] = None


def _run_pipeline(command: list[str], cwd: Path, env: Optional[Dict[str, str]] = None) -> tuple[bool, str]:
    """Run a pipeline as a subprocess and return (success, combined_log)."""
    import subprocess
    import os

    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            env={**os.environ, **(env or {})},
        )
        log_parts = []
        if proc.stdout:
            log_parts.append(proc.stdout)
        if proc.stderr:
            log_parts.append("\n[stderr]\n" + proc.stderr)
        log = "".join(log_parts).strip()
        return proc.returncode == 0, log
    except Exception as e:
        return False, f"Failed to run {' '.join(command)}: {e}"


@app.get("/api/preferences", response_model=PreferencesResult)
def get_preferences() -> PreferencesResult:
    """
    Load scraper and Madlan preferences from JSON files.

    - scraper_preferences.json: flat, user-friendly root plus optional "madlan" section.
    - madlan_preferences.json: dedicated Madlan-only file (overrides madlan section when overlapping).
    """
    import json

    root = Path(__file__).resolve().parents[1]
    scraper_path = root / "scraper_preferences.json"
    madlan_path = root / "madlan_preferences.json"

    scraper_raw: Dict[str, Any] = {}
    madlan_from_root: Dict[str, Any] = {}
    if scraper_path.exists():
        try:
            data = json.loads(scraper_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                scraper_raw = dict(data)
                madlan_from_root = dict(scraper_raw.pop("madlan", {}) or {})
        except Exception as e:
            logger.warning("Failed to read %s: %s", scraper_path, e)

    madlan_raw: Dict[str, Any] = dict(madlan_from_root)
    if madlan_path.exists():
        try:
            data = json.loads(madlan_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                madlan_raw.update(data)
        except Exception as e:
            logger.warning("Failed to read %s: %s", madlan_path, e)

    payload = PreferencesPayload(scraper=scraper_raw, madlan=madlan_raw)
    return PreferencesResult(success=True, data=payload)


@app.post("/api/preferences", response_model=PreferencesResult)
def save_preferences(prefs: PreferencesPayload) -> PreferencesResult:
    """
    Persist scraper and Madlan preferences back to JSON files.

    - Writes scraper + embedded madlan section to scraper_preferences.json
    - Writes madlan-only prefs to madlan_preferences.json
    """
    import json

    root = Path(__file__).resolve().parents[1]
    scraper_path = root / "scraper_preferences.json"
    madlan_path = root / "madlan_preferences.json"

    try:
        scraper_data = dict(prefs.scraper)
        scraper_data["madlan"] = dict(prefs.madlan)
        scraper_path.write_text(
            json.dumps(scraper_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        madlan_path.write_text(
            json.dumps(dict(prefs.madlan), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        payload = PreferencesPayload(scraper=scraper_data, madlan=dict(prefs.madlan))
        return PreferencesResult(success=True, data=payload)
    except Exception as e:
        logger.error("Failed to save preferences: %s", e)
        return PreferencesResult(success=False, error=str(e))


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


@app.post("/api/batch/run", response_model=BatchResult)
def run_batch(req: BatchRequest) -> BatchResult:
    """
    Run Yad2 and/or Madlan batch scrapers based on simple form input.

    This endpoint is a thin wrapper around the existing CLI pipelines:
    - python yad2_pipeline.py ...
    - python madlan_pipeline.py ...

    If req.preferences is provided, those values are passed inline via environment
    variables and used only for this run (JSON files on disk are not modified).
    """
    import json as _json

    root = Path(__file__).resolve().parents[1]
    log_chunks: list[str] = []
    yad2_ok = madlan_ok = True
    yad2_out: Optional[str] = None
    madlan_out: Optional[str] = None

    website = (req.website or "").strip().lower()
    if website not in {"yad2", "madlan", "both"}:
        return BatchResult(success=False, error="website must be one of: yad2, madlan, both", log="")

    # Inline preferences JSON (per-run overrides)
    inline_scraper_prefs: Optional[str] = None
    inline_madlan_prefs: Optional[str] = None
    if req.preferences is not None:
        try:
            inline_scraper_prefs = _json.dumps(req.preferences.scraper, ensure_ascii=False)
            inline_madlan_prefs = _json.dumps(req.preferences.madlan, ensure_ascii=False)
        except Exception as e:
            logger.warning("Failed to serialize inline preferences: %s", e)

    # Yad2
    if website in {"yad2", "both"}:
        yad2_args: list[str] = ["python", "yad2_pipeline.py"]
        if req.output_dir_yad2:
            yad2_out = req.output_dir_yad2
            yad2_args += ["--output-dir", req.output_dir_yad2]
        if req.max_pages:
            yad2_args += ["--max-pages", str(req.max_pages)]
        # headless: 1 or 0
        yad2_args += ["--headless", "1" if req.headless else "0"]
        env: Dict[str, str] = {}
        if inline_scraper_prefs:
            env["SCRAPER_PREFERENCES_INLINE"] = inline_scraper_prefs
        ok, log = _run_pipeline(yad2_args, root, env=env)
        yad2_ok = ok
        log_chunks.append("=== Yad2 pipeline ===\n" + log + "\n")

    # Madlan
    if website in {"madlan", "both"}:
        madlan_args: list[str] = ["python", "madlan_pipeline.py"]
        if req.output_dir_madlan:
            madlan_out = req.output_dir_madlan
            madlan_args += ["--output-dir", req.output_dir_madlan]
        if req.max_pages:
            madlan_args += ["--max-pages", str(req.max_pages)]
        madlan_args += ["--headless", "1" if req.headless else "0"]
        env: Dict[str, str] = {}
        if inline_madlan_prefs:
            env["MADLAN_PREFERENCES_INLINE"] = inline_madlan_prefs
        ok, log = _run_pipeline(madlan_args, root, env=env)
        madlan_ok = ok
        log_chunks.append("=== Madlan pipeline ===\n" + log + "\n")

    overall_ok = yad2_ok and madlan_ok
    error_msg = None if overall_ok else "One or more pipelines failed; see log."
    return BatchResult(
        success=overall_ok,
        error=error_msg,
        log="".join(log_chunks).strip(),
        yad2_output_dir=yad2_out,
        madlan_output_dir=madlan_out,
    )

