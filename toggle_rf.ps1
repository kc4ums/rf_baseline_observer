# RF Baseline Observer - Toggle pause/resume
# Run this when going on air and again when done transmitting.

$rtlProcess = Get-Process -Name "rtl_power" -ErrorAction SilentlyContinue

if ($rtlProcess) {
    Stop-Process -Name "rtl_power" -Force
    Write-Host "RF logging PAUSED - safe to transmit."
} else {
    Write-Host "RF logging RESUMING..."
    & "$PSScriptRoot\start_logging.ps1"
}
