# RF Baseline Observer - Windows 11 Setup
# Run this script as Administrator in PowerShell

Write-Host "=== RF Baseline Observer Setup ===" -ForegroundColor Cyan

# Check Python
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Python not found. Install from https://www.python.org/downloads/" -ForegroundColor Red
    exit 1
}

# Install Python dependencies
Write-Host "Installing Python dependencies..." -ForegroundColor Yellow
python -m pip install pandas numpy

# Check for rtl_power.exe
$rtlPower = Get-Command rtl_power -ErrorAction SilentlyContinue
if (-not $rtlPower) {
    Write-Host ""
    Write-Host "WARNING: rtl_power not found in PATH." -ForegroundColor Yellow
    Write-Host "Download the RTL-SDR Windows tools from: https://ftp.osmocom.org/binaries/windows/rtl-sdr/" -ForegroundColor Yellow
    Write-Host "Then add the folder containing rtl_power.exe to your system PATH." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "You also need to install the WinUSB driver for your RTL-SDR using Zadig:" -ForegroundColor Yellow
    Write-Host "  1. Plug in your RTL-SDR dongle" -ForegroundColor Yellow
    Write-Host "  2. Download Zadig from https://zadig.akeo.ie/" -ForegroundColor Yellow
    Write-Host "  3. Select your RTL-SDR device and install the WinUSB driver" -ForegroundColor Yellow
} else {
    Write-Host "rtl_power found: $($rtlPower.Source)" -ForegroundColor Green
}

Write-Host ""
Write-Host "Setup complete. See README.md for next steps." -ForegroundColor Green
