"""
Cross-platform launcher for the Listing Inspector web UI (single listing + batch).

- On Windows and macOS you can usually double-click this file (Python Launcher)
  after Python and the dependencies are installed.
- Under the hood it runs: uvicorn web_ui.api:app on http://127.0.0.1:8000
"""

from __future__ import annotations

import logging
import threading
import time
import webbrowser

import uvicorn


def _open_browser_later(url: str, delay: float = 1.5) -> None:
    """Open the browser after a short delay so the server is likely ready."""

    def _target() -> None:
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception:
            # Ignore any browser errors; server keeps running.
            pass

    threading.Thread(target=_target, daemon=True).start()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    url = "http://127.0.0.1:8000/"
    print(f"Starting Listing Inspector web UI on {url} ...")
    # Open Safari/Chrome a bit later, so Uvicorn has time to start.
    _open_browser_later(url, delay=1.5)
    uvicorn.run("web_ui.api:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()

