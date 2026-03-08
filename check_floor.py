import pandas as pd
import numpy as np
import sys
import os
import json
import urllib.request
from datetime import datetime

# US amateur radio bands within RTL-SDR range (Hz)
HAM_BANDS = [
    ("10m",   28_000_000,   29_700_000),
    ("6m",    50_000_000,   54_000_000),
    ("2m",   144_000_000,  148_000_000),
    ("1.25m",222_000_000,  225_000_000),
    ("70cm", 420_000_000,  450_000_000),
    ("33cm", 902_000_000,  928_000_000),
    ("23cm",1240_000_000, 1300_000_000),
]


NOAA_KP_URL = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"


def fetch_kp():
    """Fetch the latest Kp index from NOAA SWPC. Returns float or None."""
    try:
        with urllib.request.urlopen(NOAA_KP_URL, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        # data[0] is header row; last entry is most recent
        return float(data[-1][1])
    except Exception:
        return None


def kp_condition(kp):
    if kp is None:
        return "UNKNOWN"
    if kp <= 1:
        return "QUIET"
    if kp <= 3:
        return "UNSETTLED"
    if kp <= 4:
        return "ACTIVE"
    if kp <= 5:
        return "G1-MINOR"
    if kp <= 6:
        return "G2-MODERATE"
    if kp <= 7:
        return "G3-STRONG"
    if kp <= 8:
        return "G4-SEVERE"
    return "G5-EXTREME"


def band_for_freq(hz):
    for name, low, high in HAM_BANDS:
        if low <= hz <= high:
            return name
    return None


def status_for(avg):
    if avg > -60:
        return "CRITICAL"
    elif avg > -75:
        return "WARNING"
    return "NOMINAL"


def collect_band_data(file_path):
    df = pd.read_csv(file_path, header=None)
    band_data = {name: [] for name, _, _ in HAM_BANDS}

    # rtl_power CSV columns: date, time, hz_low, hz_high, hz_step, samples, [power...]
    for _, row in df.iterrows():
        try:
            hz_low  = float(row[2])
            hz_step = float(row[4])
            powers  = pd.to_numeric(row[6:], errors="coerce").dropna().values
            for i, pwr in enumerate(powers):
                freq = hz_low + i * hz_step
                band = band_for_freq(freq)
                if band:
                    band_data[band].append(pwr)
        except (ValueError, TypeError):
            continue

    return band_data


def print_human(file_path, band_data, kp=None):
    print(f"--- RF NOISE REPORT: {os.path.basename(file_path)} ---")
    if kp is not None:
        print(f"Space Weather:  Kp={kp:.1f}  [{kp_condition(kp)}]")
    else:
        print("Space Weather:  Kp=N/A  (use --kp or --fetch-kp)")
    print(f"{'Band':<8} {'Avg (dBm)':>10} {'Peak (dBm)':>11} {'Samples':>8}  Status")
    print("-" * 60)

    any_data = False
    for name, _, _ in HAM_BANDS:
        vals = band_data[name]
        if not vals:
            print(f"{name:<8} {'--':>10} {'--':>11} {'0':>8}  no data")
            continue
        any_data = True
        arr  = np.array(vals)
        avg  = float(np.mean(arr))
        peak = float(np.max(arr))
        print(f"{name:<8} {avg:>10.2f} {peak:>11.2f} {len(vals):>8}  {status_for(avg)}")

    if not any_data:
        print("No ham band data found. Check that the CSV covers ham band frequencies.")


def print_json(file_path, band_data, kp=None):
    record = {
        "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "source_file": os.path.basename(file_path),
        "space_weather": {
            "kp_index": kp,
            "condition": kp_condition(kp)
        },
        "bands": {}
    }

    for name, _, _ in HAM_BANDS:
        vals = band_data[name]
        if not vals:
            record["bands"][name] = {"avg_dbm": None, "peak_dbm": None, "samples": 0, "status": "NO_DATA"}
            continue
        arr  = np.array(vals)
        avg  = round(float(np.mean(arr)), 2)
        peak = round(float(np.max(arr)), 2)
        record["bands"][name] = {
            "avg_dbm": avg,
            "peak_dbm": peak,
            "samples": len(vals),
            "status": status_for(avg)
        }

    print(json.dumps(record))


def analyze_rf_csv(file_path, as_json=False, kp=None):
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found.")
        return

    try:
        band_data = collect_band_data(file_path)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return

    if as_json:
        print_json(file_path, band_data, kp=kp)
    else:
        print_human(file_path, band_data, kp=kp)


if __name__ == "__main__":
    args = sys.argv[1:]
    as_json   = "--json"     in args
    fetch_kp_ = "--fetch-kp" in args

    # --kp <value>
    kp = None
    if "--kp" in args:
        idx = args.index("--kp")
        try:
            kp = float(args[idx + 1])
        except (IndexError, ValueError):
            print("Error: --kp requires a numeric value (e.g. --kp 2.3)")
            sys.exit(1)
    elif fetch_kp_:
        kp = fetch_kp()
        if kp is None:
            print("Warning: Could not fetch Kp index from NOAA. Continuing without it.")

    files = [a for a in args if not a.startswith("--") and not (
        args.index(a) > 0 and args[args.index(a) - 1] == "--kp"
    )]

    if not files:
        print("Usage: python check_floor.py <path_to_csv> [--json] [--kp <value>] [--fetch-kp]")
        sys.exit(1)

    analyze_rf_csv(files[0], as_json=as_json, kp=kp)
