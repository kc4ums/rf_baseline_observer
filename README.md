rf_baseline_observer
Ham Band Interference Monitoring System (RTL-SDR Blog V4 + Python)

This project establishes a high-resolution RF noise floor baseline on Windows 11 to quantify electromagnetic interference (EMI) from a nearby data center across all US amateur radio bands — HF through microwave.

## Project Architecture

- **Sensor:** RTL-SDR Blog V4 (R828D2 chip, 500 kHz – 1.766 GHz; HF via direct sampling)
- **Host:** Windows 11
- **Data Logger:** rtl_power — dual sweep per cycle: HF (1.8M–28M, direct sampling) + VHF/UHF (28M–1.766G)
- **Processor:** check_floor.py — per-band noise floor analysis (Python/Pandas)
- **Scheduler:** run_continuous.ps1 — headless continuous logging loop (PowerShell)
- **TUI:** rf_observer_tui.py — interactive terminal UI with live band table (replaces run_continuous.ps1)
- **TX Toggle:** toggle_rf.ps1 — kill/resume logging when going on air
- **Visualization:** SDR++ — realtime spectrum and waterfall display

### Monitored Ham Bands

| Band   | Frequency Range           | Sweep          |
|--------|---------------------------|----------------|
| 160m   | 1.800 – 2.000 MHz         | HF (direct)    |
| 80m    | 3.500 – 4.000 MHz         | HF (direct)    |
| 60m    | 5.330 – 5.404 MHz         | HF (direct)    |
| 40m    | 7.000 – 7.300 MHz         | HF (direct)    |
| 30m    | 10.100 – 10.150 MHz       | HF (direct)    |
| 20m    | 14.000 – 14.350 MHz       | HF (direct)    |
| 17m    | 18.068 – 18.168 MHz       | HF (direct)    |
| 15m    | 21.000 – 21.450 MHz       | HF (direct)    |
| 12m    | 24.890 – 24.990 MHz       | HF (direct)    |
| 10m    | 28.000 – 29.700 MHz       | VHF/UHF        |
| 6m     | 50.000 – 54.000 MHz       | VHF/UHF        |
| 2m     | 144.000 – 148.000 MHz     | VHF/UHF        |
| 1.25m  | 222.000 – 225.000 MHz     | VHF/UHF        |
| 70cm   | 420.000 – 450.000 MHz     | VHF/UHF        |
| 33cm   | 902.000 – 928.000 MHz     | VHF/UHF        |
| 23cm   | 1240.000 – 1300.000 MHz   | VHF/UHF        |

## Folder Structure

```
C:\
├── Projects\
│   └── rf_baseline_observer\          ← this repo
│       ├── check_floor.py             ← per-band noise floor analyzer
│       ├── rf_observer_tui.py         ← terminal UI for live monitoring
│       ├── run_continuous.ps1         ← main continuous logging loop (use this)
│       ├── start_logging.ps1          ← single-run background logger + Task Scheduler setup
│       ├── toggle_rf.ps1              ← pause/resume logging when transmitting
│       ├── setup.ps1                  ← one-time dependency installer
│       ├── LICENSE
│       └── README.md
│
├── Tools\
│   └── rtl-sdr-blog-v4\              ← RTL-SDR Blog V4 Windows driver package (extracted here)
│       ├── rtl_power.exe             ← sweep tool used by run_continuous.ps1
│       ├── rtl_test.exe              ← device verification tool
│       ├── rtl_fm.exe
│       ├── rtl_sdr.exe
│       └── *.dll                     ← required runtime libraries (must stay with the .exe files)
│
└── Users\
    └── <your username>\
        └── rf_logs\                  ← runtime output (auto-created on first run)
            ├── hf_<timestamp>.csv    ← HF sweep data (1.8M–28M, direct sampling)
            ├── vhf_<timestamp>.csv   ← VHF/UHF sweep data (28M–1.766G)
            └── rf_history.log        ← JSON Lines history (one record per cycle)
```

> **PATH requirement:** Add `C:\Tools\rtl-sdr-blog-v4` to your system PATH so `rtl_power.exe` is accessible from any terminal. The `.dll` files in that folder must stay alongside the executables — do not move the `.exe` files out on their own.

## Installation & Setup

### 1. Install Python

Download and install Python 3.x from https://www.python.org/downloads/

Check "Add Python to PATH" during installation.

### 2. Install RTL-SDR Blog V4 Drivers

The V4 requires the RTL-SDR Blog driver package — **not** the generic osmocom build.

1. Download the RTL-SDR Blog Windows driver package from https://www.rtl-sdr.com/rtl-sdr-blog-v4-dongle-initial-release/
2. Extract and add the folder containing `rtl_power.exe` to your system PATH:
   - Search "Environment Variables" in the Start menu
   - Edit the `Path` variable under System Variables
   - Add the path to the extracted folder (e.g., `C:\Tools\rtl-sdr-blog-v4`)

### 3. Install the WinUSB Driver (Zadig)

1. Plug in your RTL-SDR Blog V4 dongle
2. Download Zadig from https://zadig.akeo.ie/
3. In Zadig: Options > List All Devices
4. Select **Bulk-In, Interface (Interface 0)** — the V4 shows as `RTL2832UHIDIR`
5. Choose **WinUSB** and click **Install Driver**

> **V4 note:** Do not select the wrong interface. If you see two entries for the device, pick `Interface (Interface 0)`.

### 4. Run the Setup Script

Open PowerShell as Administrator and run:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\setup.ps1
```

This installs the required Python packages (`pandas`, `numpy`) and verifies your rtl_power installation. If you plan to use the TUI (`rf_observer_tui.py`), also run `pip install textual` afterward.

## Operation Workflow

### Phase 1: Continuous Logging (Recommended)

Run the continuous logger for long-term baseline collection. Each cycle runs two back-to-back 30-minute sweeps — HF bands using direct sampling mode (`-D 2` required by the V4 for frequencies below 28 MHz), then VHF/UHF with the normal tuner. After both sweeps, it auto-fetches the Kp index from NOAA, analyzes results across all 16 bands, and appends a JSON record to the history log.

```powershell
.\run_continuous.ps1
```

Optional parameters:

```powershell
.\run_continuous.ps1 -OutputDir "D:\rf_data" -FreqHF "1.8M:28M:100K" -FreqVHF "28M:1.766G:100K"
```

Press **Ctrl+C** to stop. Each completed cycle is already saved and logged before the next begins.

### Pausing Logging While Transmitting

The RTL-SDR and your transceiver share the USB bus — you cannot transmit while logging. Stop the logger before keying up:

```powershell
.\toggle_rf.ps1
```

Run `toggle_rf.ps1` again to resume, or simply restart `run_continuous.ps1`. Each resume starts fresh CSVs with new timestamps.

### Phase 2: Manual Analysis

Analyze any collected CSVs at any time. Pass one or both sweep files from a cycle. Use `--json` for machine-readable output.

#### Space Weather Flagging

Geomagnetic activity independently raises the noise floor on HF/VHF bands. Always include the Kp index to distinguish solar interference from local EMI.

```powershell
# Human-readable, auto-fetch Kp from NOAA (requires internet)
python check_floor.py "$env:USERPROFILE\rf_logs\hf_<timestamp>.csv" "$env:USERPROFILE\rf_logs\vhf_<timestamp>.csv" --fetch-kp

# Manually specify Kp
python check_floor.py "$env:USERPROFILE\rf_logs\hf_<timestamp>.csv" "$env:USERPROFILE\rf_logs\vhf_<timestamp>.csv" --kp 1.7

# JSON output with Kp
python check_floor.py "$env:USERPROFILE\rf_logs\hf_<timestamp>.csv" "$env:USERPROFILE\rf_logs\vhf_<timestamp>.csv" --json --fetch-kp

# Single-sweep file (HF only or VHF/UHF only)
python check_floor.py "$env:USERPROFILE\rf_logs\vhf_<timestamp>.csv" --fetch-kp
```

Human-readable example:
```
--- RF NOISE REPORT: hf_20260101_120000.csv, vhf_20260101_123000.csv ---
Space Weather:  Kp=1.7  [UNSETTLED]
Band     Avg (dBm)  Peak (dBm)  Samples  Status
------------------------------------------------------------
160m        -88.40      -74.10      512  NOMINAL
80m         -85.22      -70.60      820  NOMINAL
60m         -84.10      -69.80      102  NOMINAL
40m         -83.55      -68.30      492  NOMINAL
30m         -82.90      -67.50       82  NOMINAL
20m         -81.20      -66.40      574  NOMINAL
17m         -80.75      -65.90      164  NOMINAL
15m         -79.60      -64.20      738  NOMINAL
12m         -78.30      -63.10      164  NOMINAL
10m         -83.12      -71.40     1024  NOMINAL
6m          -81.55      -68.90      412  NOMINAL
2m          -76.20      -62.10      492  WARNING
1.25m       --          --            0  no data
70cm        -79.45      -60.80     1860  NOMINAL
33cm        -65.10      -55.20     1638  WARNING
23cm        -82.77      -70.10     3720  NOMINAL
```

JSON example:
```json
{
  "timestamp": "2026-01-01T12:00:00Z",
  "source_file": ["hf_20260101_120000.csv", "vhf_20260101_123000.csv"],
  "space_weather": {"kp_index": 1.7, "condition": "UNSETTLED"},
  "bands": {
    "160m": {"avg_dbm": -88.40, "peak_dbm": -74.10, "samples": 512, "status": "NOMINAL"},
    "2m":   {"avg_dbm": -76.20, "peak_dbm": -62.10, "samples": 492, "status": "WARNING"}
  }
}
```

#### Kp Condition Scale

| Kp    | Condition    | Effect on HF/VHF           |
|-------|--------------|----------------------------|
| 0–1   | QUIET        | Clean baseline              |
| 2–3   | UNSETTLED    | Minor ionospheric variation |
| 4     | ACTIVE       | Noticeable HF impact        |
| 5     | G1-MINOR     | HF degradation possible     |
| 6     | G2-MODERATE  | HF unreliable               |
| 7     | G3-STRONG    | HF blackouts possible       |
| 8     | G4-SEVERE    | Wide HF blackout            |
| 9     | G5-EXTREME   | Total HF blackout           |

> **Baseline tip:** Use only **Kp ≤ 1 (QUIET)** runs as your reference baseline when comparing pre- vs. post-construction readings.

### Phase 3: Review History Log

Each cycle appends one JSON record to `%USERPROFILE%\rf_logs\rf_history.log` (JSON Lines format — one complete object per line). Tail it live:

```powershell
Get-Content "$env:USERPROFILE\rf_logs\rf_history.log" -Wait
```

## Terminal UI (rf_observer_tui.py)

`rf_observer_tui.py` is a fully interactive terminal application that replaces `run_continuous.ps1` with a live display. It runs the same dual-sweep cycle (HF direct sampling + VHF/UHF) but shows results in real time as each cycle completes.

### Additional Dependency

The TUI requires the `textual` package, which is not installed by `setup.ps1`:

```powershell
pip install textual
```

### Running the TUI

```powershell
python rf_observer_tui.py

# Custom output directory or second dongle
python rf_observer_tui.py --output-dir D:\rf_data --device 1
```

### Layout

```
┌─ RF Baseline Observer — RTL-SDR V4 ──────────────────────────────────────┐
│ ┌─ HAM BAND RF NOISE FLOOR ──────────────┐ ┌─ SWEEP STATUS ─────────────┐ │
│ │ Band   Avg(dBm) Peak(dBm) Samples Status│ │ HF Sweep (elapsed: 12:34)  │ │
│ │ 160m   -88.40   -74.10      512 NOMINAL │ │ Cycle: 3                   │ │
│ │ 80m    -85.22   -70.60      820 NOMINAL │ │                            │ │
│ │ ...                                     │ │ SPACE WEATHER              │ │
│ │ 2m     -76.20   -62.10      492 WARNING │ │ Kp: 1.7  [UNSETTLED]       │ │
│ │ 33cm   -65.10   -55.20     1638 WARNING │ │                            │ │
│ └─────────────────────────────────────────┘ │ CONTROLS                   │ │
│                                             │ [ Start ]                  │ │
│                                             │ [ Stop  ]                  │ │
│                                             └────────────────────────────┘ │
│ CYCLE HISTORY                                                               │
│ [12:04:11] Cycle 3 | Kp=1.7 [UNSETTLED] | NOMINAL:14 WARN:2 CRIT:0       │
│ [11:34:08] Cycle 2 | Kp=1.5 [QUIET]     | NOMINAL:16 WARN:0 CRIT:0       │
└─ q Quit  s Start/Stop  c Copy History ───────────────────────────────────┘
```

### Keyboard Shortcuts

| Key | Action                                        |
|-----|-----------------------------------------------|
| `s` | Start / Stop the sweep loop                   |
| `q` | Quit                                          |
| `c` | Copy cycle history to Windows clipboard       |

### Notes

- Writes to the same `rf_history.log` as `run_continuous.ps1` — both tools share the same log file and output directory.
- Status colors: **green** = NOMINAL (avg ≤ −75 dBm), **yellow** = WARNING (> −75 dBm), **red** = CRITICAL (> −60 dBm).
- The sweep phase timer resets at the start of each HF and VHF/UHF sweep.
- Press **Stop** (or `s`) to let the current sweep finish cleanly before the loop exits. Pressing **Stop** mid-sweep sends a terminate signal to rtl_power immediately.

## Realtime Visualization

For a live spectrum and waterfall display, use **SDR++**:

1. Download from https://github.com/AlexandreRouma/SDRPlusPlus/releases
2. Extract and run `sdrpp.exe` — no install required
3. In SDR++: set Source to **RTL-SDR**, click **Play**

> **Note:** SDR++ and rtl_power cannot share the dongle. Run `.\toggle_rf.ps1` to stop background logging before opening SDR++, and run it again to resume when done.

## Troubleshooting

- **SDR not found:** Run `rtl_test.exe -t` in a terminal. If it fails, re-run Zadig and reinstall the WinUSB driver on `Interface 0`.
- **rtl_power not recognized:** Ensure the RTL-SDR Blog V4 bin folder is in your system PATH and restart the terminal.
- **HF bands show no data:** Direct sampling requires the RTL-SDR Blog V4 driver build. Generic osmocom builds do not support `-D 2` correctly. Confirm with `rtl_power -d 0 -D 2 -f 7M:7.3M:1K -i 10s -e 10s test.csv`.
- **Inaccurate readings:** Place the antenna away from PCs and routers to reduce local noise.
- **Task Scheduler errors:** Run PowerShell as Administrator when executing `start_logging.ps1`.
