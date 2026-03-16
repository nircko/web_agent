### Packaging: Listing Inspector Web UI (PyInstaller)

This folder contains **developer-only** scripts to build standalone binaries for the Listing Inspector
web UI. End users should never run these directly; they will only receive the built EXE/app.

---

## 1. Windows: build `LaunchListingInspector.exe`

Prerequisites on the build machine:

- Python 3.10+ installed and on PATH.
- `pip install -r requirements.txt`

Build steps (PowerShell, from the project root `web_agent`):

```powershell
cd /path/to/web_agent
.\packaging\build_web_ui_windows.ps1
```

This will:

- Ensure `pyinstaller` is installed.
- Run PyInstaller against `launch_web_ui.py`.
- Produce a single-file EXE:

```text
dist\LaunchListingInspector.exe
```

To ship to a non-technical Windows user, copy:

- `dist\LaunchListingInspector.exe`
- `assets\` (folder)
- `scraper_preferences.json` (if you use it)
- `madlan_preferences.json` (if you use it)

The user experience:

- They double-click `LaunchListingInspector.exe`.
- A window starts the backend on `http://127.0.0.1:8000/`.
- They open that URL in their browser and use the HTML UI (Analyze button included).

No Python, pip, or CLI required on their side.

---

## 2. macOS: build `LaunchListingInspector` binary

Prerequisites on the build machine:

- Python 3.10+ installed (`python3`).
- `pip install -r requirements.txt`

Build steps (Terminal, from the project root `web_agent`):

```bash
cd /path/to/web_agent
chmod +x packaging/build_web_ui_macos.sh
./packaging/build_web_ui_macos.sh
```

This will:

- Ensure `pyinstaller` is installed.
- Run PyInstaller against `launch_web_ui.py`.
- Produce a single-file binary:

```text
dist/LaunchListingInspector
```

To ship to a non-technical macOS user, copy:

- `dist/LaunchListingInspector`
- `assets/` (folder)
- `scraper_preferences.json` (if you use it)
- `madlan_preferences.json` (if you use it)

The user experience:

- They double-click `LaunchListingInspector` in Finder.
- macOS may ask once if they want to trust/open the app (Gatekeeper).
- The backend starts on `http://127.0.0.1:8000/`, and they use the HTML UI in the browser.

---

## 3. Notes

- These bundles only cover the **web UI**. The batch scrapers (`yad2_pipeline.py`, `madlan_pipeline.py`)
  remain CLI tools; if you also want EXE/app wrappers for them, similar PyInstaller specs can be added.
- All Python code and helpers live under:
  - `web_agent/` (shared logic, pipelines support).
  - `web_ui/` (FastAPI app + HTML).
- Root remains clean for:
  - Jupyter notebook (`Yad2_nadlan.ipynb`)
  - Preferences / assets
  - Main CLI scripts
  - Launchers / built EXEs.

