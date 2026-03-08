rf_baseline_observer
Ham Band Interference Monitoring System (RTL-SDR + Python)

This project establishes a high-resolution RF noise floor baseline on Windows 11 to quantify electromagnetic interference (EMI) from a nearby data center across US amateur radio bands.

## Project Architecture

- **Sensor:** RTL-SDR (Blog V4 or similar)
- **Host:** Windows 11
- **Data Logger:** rtl_power (sweeps 28 MHz – 1.3 GHz at 100 kHz steps)
- **Processor:** check_floor.py — per-band noise floor analysis (Python/Pandas)
- **Scheduler:** Windows Task Scheduler (hourly JSON reports)
- **TX Toggle:** toggle_rf.ps1 — pause/resume logging when transmitting
- **Visualization:** SDR++ — realtime spectrum and waterfall display

### Monitored Ham Bands

| Band  | Frequency Range        |
|-------|------------------------|
| 10m   | 28.000 – 29.700 MHz    |
| 6m    | 50.000 – 54.000 MHz    |
| 2m    | 144.000 – 148.000 MHz  |
| 1.25m | 222.000 – 225.000 MHz  |
| 70cm  | 420.000 – 450.000 MHz  |
| 33cm  | 902.000 – 928.000 MHz  |
| 23cm  | 1240.000 – 1300.000 MHz |

## Installation & Setup

### 1. Install Python

Download and install Python 3.x from https://www.python.org/downloads/

Make sure to check "Add Python to PATH" during installation.

### 2. Install RTL-SDR Windows Tools

1. Download the RTL-SDR Windows binary package from https://ftp.osmocom.org/binaries/windows/rtl-sdr/
2. Extract it and add the folder containing `rtl_power.exe` to your system PATH:
   - Search "Environment Variables" in the Start menu
   - Edit the `Path` variable under System Variables
   - Add the path to the extracted folder (e.g., `C:\Tools\rtl-sdr`)

### 3. Install the WinUSB Driver (Zadig)

1. Plug in your RTL-SDR dongle
2. Download Zadig from https://zadig.akeo.ie/
3. In Zadig: Options > List All Devices, select your RTL-SDR device
4. Choose **WinUSB** and click **Install Driver**

### 4. Run the Setup Script

Open PowerShell as Administrator and run:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\setup.ps1
```

This installs the required Python packages (`pandas`, `numpy`) and verifies your RTL-SDR installation.

## Operation Workflow

### Phase 1: Continuous Logging (Recommended)

For long-term baseline collection, run the continuous logging script. It loops forever — each cycle runs a 1-hour sweep, auto-fetches the Kp index from NOAA, analyzes the result, and appends a JSON record to the history log. A new timestamped CSV is created each hour.

```powershell
.\run_continuous.ps1
```

Optional parameters:

```powershell
.\run_continuous.ps1 -OutputDir "D:\rf_data" -Freq "28M:1.3G:100K"
```

Press **Ctrl+C** to stop. Each completed hour is already saved and logged before the next cycle begins.

### Pausing Logging While Transmitting

If you need to transmit on your transceiver, press **Ctrl+C** to stop the continuous logger first (frees the USB device), then run it again when done:

```powershell
.\toggle_rf.ps1
```

Or simply stop and restart `run_continuous.ps1`. Each resume starts a new CSV with a fresh timestamp.

### Phase 2: Manual Analysis

Analyze any collected CSV at any time. Use `--json` for machine-readable output or omit it for a human-readable table.

#### Space Weather Flagging

Geomagnetic activity (solar storms, elevated Kp index) raises the noise floor on HF/VHF bands independently of local interference. Always include the Kp index when analyzing a baseline to identify disturbed conditions.

```powershell
# Human-readable, auto-fetch Kp from NOAA (requires internet)
python check_floor.py "$env:USERPROFILE\rf_logs\baseline_<timestamp>.csv" --fetch-kp

# Human-readable, manually specify Kp
python check_floor.py "$env:USERPROFILE\rf_logs\baseline_<timestamp>.csv" --kp 1.7

# JSON with Kp
python check_floor.py "$env:USERPROFILE\rf_logs\baseline_<timestamp>.csv" --json --fetch-kp

# No Kp (legacy, not recommended for baseline work)
python check_floor.py "$env:USERPROFILE\rf_logs\baseline_<timestamp>.csv"
```

Human-readable example:
```
--- RF NOISE REPORT: baseline_20260101_120000.csv ---
Space Weather:  Kp=1.7  [UNSETTLED]
Band     Avg (dBm)  Peak (dBm)  Samples  Status
------------------------------------------------------------
10m         -83.12      -71.40     1024  NOMINAL
6m          -81.55      -68.90      412  NOMINAL
2m          -76.20      -62.10      492  WARNING
70cm        -79.45      -60.80     1860  NOMINAL
33cm        -65.10      -55.20     1638  WARNING
23cm        -82.77      -70.10     3720  NOMINAL
```

JSON example:
```json
{"timestamp": "2026-01-01T12:00:00Z", "source_file": "baseline_20260101_120000.csv", "space_weather": {"kp_index": 1.7, "condition": "UNSETTLED"}, "bands": {"10m": {"avg_dbm": -83.12, "peak_dbm": -71.40, "samples": 1024, "status": "NOMINAL"}, "2m": {"avg_dbm": -76.20, "peak_dbm": -62.10, "samples": 492, "status": "WARNING"}, ...}}
```

#### Kp Condition Scale

| Kp    | Condition    | Effect on HF/VHF          |
|-------|--------------|---------------------------|
| 0–1   | QUIET        | Clean baseline             |
| 2–3   | UNSETTLED    | Minor ionospheric variation |
| 4     | ACTIVE       | Noticeable HF impact       |
| 5     | G1-MINOR     | HF degradation possible    |
| 6     | G2-MODERATE  | HF unreliable              |
| 7     | G3-STRONG    | HF blackouts possible      |
| 8     | G4-SEVERE    | Wide HF blackout           |
| 9     | G5-EXTREME   | Total HF blackout          |

> **Baseline tip:** Use only **Kp ≤ 1 (QUIET)** runs as your reference baseline when comparing pre- vs. post-construction readings.

### Phase 3: Review History Log

The hourly scheduled task appends one JSON record per run to `%USERPROFILE%\rf_logs\rf_history.log` (JSON Lines format — one complete JSON object per line). This structured format is easy to parse and analyze for noise floor trends over time.

```powershell
Get-Content "$env:USERPROFILE\rf_logs\rf_history.log" -Wait
```

## Realtime Visualization

For a live spectrum and waterfall display, use **SDR++**:

1. Download from https://github.com/AlexandreRouma/SDRPlusPlus/releases
2. Extract and run `sdrpp.exe` — no install required
3. In SDR++: set Source to **RTL-SDR**, click **Play**

> **Note:** SDR++ and `rtl_power` cannot use the dongle at the same time. Run `.\toggle_rf.ps1` to pause background logging before opening SDR++, and again to resume when done.

## Troubleshooting

- **SDR not found:** Run `rtl_test.exe -t` in a terminal. If it fails, re-run Zadig and reinstall the WinUSB driver.
- **rtl_power not recognized:** Ensure the RTL-SDR bin folder is in your system PATH and restart the terminal.
- **Inaccurate readings:** Place the antenna away from local electronics (PCs, routers) to reduce local noise and capture external interference accurately.
- **Task Scheduler errors:** Run PowerShell as Administrator when executing `start_logging.ps1`.