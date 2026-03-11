# RF Baseline Observer - Continuous Logging (RTL-SDR V4)
# Runs indefinitely: two 30-min sweeps per cycle (HF + VHF/UHF), analyzes with Kp index, logs result.
# HF sweep uses direct sampling (-D 2) required by the V4 for bands below ~28 MHz.
# Press Ctrl+C to stop.

param(
    [string]$OutputDir  = "$env:USERPROFILE\rf_logs",
    [string]$FreqHF     = "1.8M:28M:100K",    # HF bands: 160m through 10m (direct sampling)
    [string]$FreqVHF    = "28M:1.766G:100K",   # VHF/UHF: 10m through 23cm
    [int]   $DeviceIdx  = 0,                   # RTL-SDR device index (0 = first/only dongle)
    [string]$PythonExe  = "python"
)

$logFile    = "$OutputDir\rf_history.log"
$scriptPath = Join-Path $PSScriptRoot "check_floor.py"

# Create output directory if needed
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
    Write-Host "Created output directory: $OutputDir"
}

Write-Host "RF Baseline Observer - Continuous Mode (RTL-SDR V4)"
Write-Host "  HF sweep        : $FreqHF  (direct sampling, -D 2)"
Write-Host "  VHF/UHF sweep   : $FreqVHF"
Write-Host "  Device index    : $DeviceIdx"
Write-Host "  Output dir      : $OutputDir"
Write-Host "  History log     : $logFile"
Write-Host "  Press Ctrl+C to stop."
Write-Host ""

$cycleNum = 0

while ($true) {
    $cycleNum++
    $timestamp  = Get-Date -Format "yyyyMMdd_HHmmss"
    $csvHF      = "$OutputDir\hf_$timestamp.csv"
    $csvVHF     = "$OutputDir\vhf_$timestamp.csv"
    $sweepOk    = $false

    # --- HF sweep (30 min, direct sampling mode) ---
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')]  Cycle $cycleNum - HF sweep ($FreqHF) -> $csvHF"
    try {
        & rtl_power -d $DeviceIdx -D 2 -f $FreqHF -i 30m -e 30m $csvHF
        if (Test-Path $csvHF) { $sweepOk = $true }
    } catch {
        Write-Warning "HF sweep failed: $_"
    }

    # --- VHF/UHF sweep (30 min, normal tuner) ---
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')]  Cycle $cycleNum - VHF/UHF sweep ($FreqVHF) -> $csvVHF"
    try {
        & rtl_power -d $DeviceIdx -f $FreqVHF -i 30m -e 30m $csvVHF
        if (Test-Path $csvVHF) { $sweepOk = $true }
    } catch {
        Write-Warning "VHF/UHF sweep failed: $_"
    }

    if (-not $sweepOk) {
        Write-Warning "Both sweeps failed - retrying next cycle."
        Start-Sleep -Seconds 5
        continue
    }

    # --- Analyze available CSVs and append JSON result to history log ---
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')]  Analyzing and logging result..."
    $csvArgs = @()
    if (Test-Path $csvHF)  { $csvArgs += $csvHF }
    if (Test-Path $csvVHF) { $csvArgs += $csvVHF }

    try {
        $result = & $PythonExe $scriptPath @csvArgs --json --fetch-kp 2>&1
        Add-Content -Path $logFile -Value $result
        Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')]  Logged to $logFile"
    } catch {
        Write-Warning "Analysis failed: $_"
    }

    Write-Host ""
}
