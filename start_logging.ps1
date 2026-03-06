# RF Baseline Observer - Start Background Logging (Windows 11)
# Captures a 7-day wideband sweep from 24 MHz to 1.7 GHz
# Logs are written to %USERPROFILE%\rf_logs\

param(
    [string]$OutputDir = "$env:USERPROFILE\rf_logs",
    [string]$Freq = "28M:1.3G:100K",   # covers 10m through 23cm ham bands
    [string]$Interval = "1h",
    [string]$Duration = "7d"
)

# Create output directory
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
    Write-Host "Created output directory: $OutputDir"
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$csvFile = "$OutputDir\baseline_$timestamp.csv"
$logFile = "$OutputDir\rf_history.log"

Write-Host "Starting RTL-SDR sweep..."
Write-Host "  Frequency range : $Freq"
Write-Host "  Integration     : $Interval"
Write-Host "  Duration        : $Duration"
Write-Host "  Output CSV      : $csvFile"
Write-Host ""

# Run rtl_power as a background job
$job = Start-Job -ScriptBlock {
    param($freq, $interval, $duration, $csv)
    & rtl_power -f $freq -i $interval -e $duration $csv
} -ArgumentList $Freq, $Interval, $Duration, $csvFile

Write-Host "Logging started as background job (ID: $($job.Id))."
Write-Host "To check status : Receive-Job -Id $($job.Id)"
Write-Host "To stop logging : Stop-Job -Id $($job.Id)"
Write-Host ""

# Schedule hourly analysis using Windows Task Scheduler
$taskName = "RF_Baseline_Hourly_Report"
$pythonPath = (Get-Command python).Source
$scriptPath = Join-Path $PSScriptRoot "check_floor.py"
$action = New-ScheduledTaskAction -Execute $pythonPath -Argument "`"$scriptPath`" `"$csvFile`" >> `"$logFile`" 2>&1"
$trigger = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Hours 1) -Once -At (Get-Date)

# Remove existing task if present, then register
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -RunLevel Highest -Force | Out-Null

Write-Host "Hourly report task registered: '$taskName'"
Write-Host "Reports will append to: $logFile"
