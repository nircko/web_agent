<# 
 Yad2 Scraper Setup (Windows, PowerShell)

 This script is intended for non‑technical users. It will:
   1. Check that Python 3 is installed.
   2. Create a virtual environment in .venv.
   3. Install all required Python packages.
   4. Install Playwright browsers.
   5. Create a .env file with your API keys.

 Usage:
   - Right‑click this file and choose "Run with PowerShell"
     OR open PowerShell in the project folder and run:
       ./setup_yad2_scraper_windows.ps1
#>

param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "=== Yad2 Scraper Setup (Windows) ===" -ForegroundColor Cyan

# 1. Prefer using the Python 3.12 version inside an existing .venv, if present.
$venvPython = ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    Write-Host "Existing virtual environment detected. Using its Python version:" -ForegroundColor Yellow
    & $venvPython --version
} else {
    # Ensure Python 3.12 is installed (try to auto-install via winget when possible)
    $python = Get-Command python3.12 -ErrorAction SilentlyContinue
    if (-not $python) {
        $python = Get-Command py -ErrorAction SilentlyContinue
    }

    if (-not $python) {
        Write-Host "Python 3.12 was not found on your PATH." -ForegroundColor Yellow

        $winget = Get-Command winget -ErrorAction SilentlyContinue
        if ($winget) {
            Write-Host "winget detected. Attempting to install Python 3.12 via winget ..." -ForegroundColor Yellow
            try {
                winget install -e --id Python.Python.3.12 -h 0
            } catch {
                Write-Host "winget failed to install Python 3.12." -ForegroundColor Red
                Write-Host "Please install Python 3.12 from https://www.python.org/downloads/ and run this script again." -ForegroundColor Red
                exit 1
            }

            # Re-detect python 3.12 after installation
            $python = Get-Command python3.12 -ErrorAction SilentlyContinue
            if (-not $python) {
                $python = Get-Command py -ErrorAction SilentlyContinue
            }
        } else {
            Write-Host "winget is not available on this system." -ForegroundColor Yellow
            Write-Host "Please install Python 3.12 from https://www.python.org/downloads/ and run this script again." -ForegroundColor Red
            exit 1
        }
    }

    if (-not $python) {
        Write-Host "Python 3.12 is still not available after attempted installation." -ForegroundColor Red
        Write-Host "Please install Python 3.12 manually from https://www.python.org/downloads/ and re-run this script." -ForegroundColor Red
        exit 1
    }

    Write-Host ("Using system Python 3.12 to create virtual environment: {0}" -f $python.Source) -ForegroundColor Green

    # 2. Create virtual environment with Python 3.12
    if (-not (Test-Path ".venv")) {
        Write-Host "Creating virtual environment in .venv ..." -ForegroundColor Yellow
        & $python.Source -m venv .venv
    } else {
        Write-Host "Virtual environment .venv already exists, reusing it." -ForegroundColor Yellow
    }

    $venvPython = ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        Write-Host "Could not find $venvPython. Something went wrong creating the virtual environment." -ForegroundColor Red
        exit 1
    }
}

# 3. Upgrade pip inside the virtual environment

Write-Host "Upgrading pip in the virtual environment ..." -ForegroundColor Yellow
& $venvPython -m pip install --upgrade pip

# 4. Install Python dependencies
if (-not (Test-Path "requirements.txt")) {
    Write-Host "requirements.txt not found in the current folder." -ForegroundColor Red
    Write-Host "Make sure you run this script from the project root (where requirements.txt is)." -ForegroundColor Red
    exit 1
}

Write-Host "Installing Python packages from requirements.txt ..." -ForegroundColor Yellow
& $venvPython -m pip install -r requirements.txt

# 5. Install Playwright browsers
Write-Host "Installing Playwright browsers (Chromium, etc.) ..." -ForegroundColor Yellow
& $venvPython -m playwright install

# 6. Create or update .env with required keys
$envFile = ".env"
Write-Host ""
Write-Host "Now we will configure API keys used for geocoding and routing." -ForegroundColor Cyan

$orsKey = Read-Host "Enter your OpenRouteService API key (ORS_API_KEY), or leave empty to skip routing"
$geoEmail = Read-Host "Enter your email for Nominatim (GEOCODING_EMAIL), used only in headers (recommended)"

@"
ORS_API_KEY=$orsKey
GEOCODING_EMAIL=$([string]::IsNullOrWhiteSpace($geoEmail) ? "example@example.com" : $geoEmail)
"@ | Out-File -FilePath $envFile -Encoding UTF8 -Force

Write-Host ""
Write-Host "Wrote configuration to $envFile:" -ForegroundColor Green
Get-Content $envFile

Write-Host ""
Write-Host "=== Setup complete ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "To run the scraper next time:" -ForegroundColor Yellow
Write-Host "  1) Open PowerShell in this folder." -ForegroundColor Yellow
Write-Host "  2) Activate the virtual environment:" -ForegroundColor Yellow
Write-Host "       .\.venv\Scripts\Activate.ps1" -ForegroundColor Yellow
Write-Host "  3) Run, for example:" -ForegroundColor Yellow
Write-Host "       python yad2_pipeline.py \"-output-dir\" \"./output\" \"-max-pages\" 2 \"-captcha-avoidance-min\" 0 \"-headless\" 1 \"-areas\" \"Rishon LeZion Area, Netanya Area\"" -ForegroundColor Yellow
Write-Host ""
Write-Host "If you run into issues (captcha, headless mode, Python errors, etc.), see TROUBLESHOOTING.md in this folder." -ForegroundColor Cyan

