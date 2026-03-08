# RF Baseline Observer - Continuous Logging
# Runs indefinitely: one 1-hour sweep per cycle, analyzes with Kp index, logs result.
# Press Ctrl+C to stop.

param(
    [string]$OutputDir = "$env:USERPROFILE\rf_logs",
    [string]$Freq      = "28M:1.3G:100K",
    [string]$PythonExe = "python"
)

$logFile    = "$OutputDir\rf_history.log"
$scriptPath = Join-Path $PSScriptRoot "check_floor.py"

# Create output directory if needed
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
    Write-Host "Created output directory: $OutputDir"
}

Write-Host "RF Baseline Observer - Continuous Mode"
Write-Host "  Frequency range : $Freq"
Write-Host "  Output dir      : $OutputDir"
Write-Host "  History log     : $logFile"
Write-Host "  Press Ctrl+C to stop."
Write-Host ""

$cycleNum = 0

while ($true) {
    $cycleNum++
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $csvFile   = "$OutputDir\baseline_$timestamp.csv"

    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')]  Cycle $cycleNum - sweeping to $csvFile"

    # Run rtl_power for exactly 1 hour
    try {
        & rtl_power -f $Freq -i 1h -e 1h $csvFile
    } catch {
        Write-Warning "rtl_power failed: $_ - retrying next cycle."
        Start-Sleep -Seconds 5
        continue
    }

    # Analyze the CSV and append JSON result to history log
    if (Test-Path $csvFile) {
        Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')]  Analyzing and logging result..."
        try {
            $result = & $PythonExe $scriptPath $csvFile --json --fetch-kp 2>&1
            Add-Content -Path $logFile -Value $result
            Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')]  Logged to $logFile"
        } catch {
            Write-Warning "Analysis failed: $_"
        }
    } else {
        Write-Warning "CSV not found after sweep - skipping analysis."
    }

    Write-Host ""
}
