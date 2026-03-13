<# 
 Yad2 Scraper Setup (Windows, PowerShell)

 Core setup script used by the Windows .bat launcher.
#>

param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "=== Yad2 Scraper Setup (Windows) ===" -ForegroundColor Cyan

# 1. Prefer using the Python 3.12 version inside an existing .venv, if present,
#    but only if that .venv is running Python >= 3.8. Older venvs are deleted
#    and recreated with Python 3.12, otherwise playwright cannot be installed.
$venvPython = ".venv\Scripts\python.exe"
$reuseVenv = $false

if (Test-Path $venvPython) {
    $versionOutput = & $venvPython --version 2>$null
    if ($versionOutput -match "Python\s+(\d+)\.(\d+)\.") {
        $major = [int]$matches[1]
        $minor = [int]$matches[2]

        if (($major -gt 3) -or (($major -eq 3) -and ($minor -ge 8))) {
            Write-Host "Existing virtual environment detected. Using its Python version:" -ForegroundColor Yellow
            & $venvPython --version
            $reuseVenv = $true
        } else {
            Write-Host "Existing virtual environment uses unsupported Python version ($versionOutput)." -ForegroundColor Yellow
            Write-Host "Recreating .venv with Python 3.12 so playwright can be installed..." -ForegroundColor Yellow
            Remove-Item -Recurse -Force ".venv"
        }
    } else {
        Write-Host "Could not determine Python version of existing .venv. Recreating it with Python 3.12..." -ForegroundColor Yellow
        Remove-Item -Recurse -Force ".venv"
    }
}

if (-not $reuseVenv) {
    # Ensure Python 3.12 is installed (try to auto-install via winget when possible)
    # We are strict here: Playwright requires Python >= 3.8, and this project is
    # tested with Python 3.12 specifically.

    # Decide which Python executable and args to use for (re)creating the venv
    $pythonExe  = $null
    $pythonArgs = @()

    # 1) Try a direct python3.12 first
    $python312 = Get-Command python3.12 -ErrorAction SilentlyContinue
    if ($python312) {
        $pythonExe  = $python312.Source
        $pythonArgs = @()
    } else {
        # 2) Fallback to the Windows `py` launcher, but pin it to 3.12 explicitly
        $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
        if ($pyLauncher) {
            $pythonExe  = $pyLauncher.Source
            $pythonArgs = @("-3.12")
        }
    }

    if (-not $pythonExe) {
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
            $python312 = Get-Command python3.12 -ErrorAction SilentlyContinue
            if ($python312) {
                $pythonExe  = $python312.Source
                $pythonArgs = @()
            } else {
                $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
                if ($pyLauncher) {
                    $pythonExe  = $pyLauncher.Source
                    $pythonArgs = @("-3.12")
                }
            }
        } else {
            Write-Host "winget is not available on this system." -ForegroundColor Yellow
            Write-Host "Please install Python 3.12 from https://www.python.org/downloads/ and run this script again." -ForegroundColor Red
            exit 1
        }
    }

    if (-not $pythonExe) {
        Write-Host "Python 3.12 is still not available after attempted installation." -ForegroundColor Red
        Write-Host "Please install Python 3.12 manually from https://www.python.org/downloads/ and re-run this script." -ForegroundColor Red
        exit 1
    }

    Write-Host ("Using system Python 3.12 to create virtual environment: {0}" -f $pythonExe) -ForegroundColor Green

    # 2. Create virtual environment with Python 3.12
    if (-not (Test-Path ".venv")) {
        Write-Host "Creating virtual environment in .venv ..." -ForegroundColor Yellow
        & $pythonExe @pythonArgs -m venv .venv
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

$orsKey   = Read-Host "Enter your OpenRouteService API key (ORS_API_KEY), or leave empty to skip routing"
$geoEmail = Read-Host "Enter your email for Nominatim (GEOCODING_EMAIL), used only in headers (recommended)"

if ([string]::IsNullOrWhiteSpace($geoEmail)) {
    $geoEmailToWrite = "example@example.com"
} else {
    $geoEmailToWrite = $geoEmail
}

@"
ORS_API_KEY=$orsKey
GEOCODING_EMAIL=$geoEmailToWrite
"@ | Out-File -FilePath $envFile -Encoding UTF8 -Force

Write-Host ""
Write-Host ("Wrote configuration to {0}:" -f $envFile) -ForegroundColor Green

Write-Host ""
Write-Host "=== Setup complete ===" -ForegroundColor Cyan

