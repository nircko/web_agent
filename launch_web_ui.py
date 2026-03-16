"""
Cross-platform launcher for the Listing Inspector web UI.

- On Windows and macOS you can usually double-click this file (Python Launcher)
  after Python and the dependencies are installed.
- Under the hood it runs: uvicorn web_ui.api:app on http://127.0.0.1:8000
"""

from __future__ import annotations

import logging

import uvicorn


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    print("Starting Listing Inspector web UI on http://127.0.0.1:8000/ ...")
    uvicorn.run("web_ui.api:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()

