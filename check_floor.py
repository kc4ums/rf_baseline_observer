import pandas as pd
import numpy as np
import sys
import os
import json
import urllib.request
from datetime import datetime

# US amateur radio bands within RTL-SDR V4 range (Hz)
# HF bands (160m-10m) require direct sampling mode (-D 2) in rtl_power
HAM_BANDS = [
    ("160m",   1_800_000,    2_000_000),
    ("80m",    3_500_000,    4_000_000),
    ("60m",    5_330_500,    5_403_500),
    ("40m",    7_000_000,    7_300_000),
    ("30m",   10_100_000,   10_150_000),
    ("20m",   14_000_000,   14_350_000),
    ("17m",   18_068_000,   18_168_000),
    ("15m",   21_000_000,   21_450_000),
    ("12m",   24_890_000,   24_990_000),
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


def collect_band_data(file_paths):
    """Accept a single path or list of paths; merge all into one band_data dict."""
    if isinstance(file_paths, str):
        file_paths = [file_paths]

    band_data = {name: [] for name, _, _ in HAM_BANDS}

    for file_path in file_paths:
        try:
            df = pd.read_csv(file_path, header=None)
        except Exception as e:
            print(f"Warning: could not read {file_path}: {e}", file=sys.stderr)
            continue

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
    if isinstance(file_path, list):
        label = ", ".join(os.path.basename(f) for f in file_path)
    else:
        label = os.path.basename(file_path)
    print(f"--- RF NOISE REPORT: {label} ---")
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
    if isinstance(file_path, list):
        source = [os.path.basename(f) for f in file_path]
    else:
        source = os.path.basename(file_path)
    record = {
        "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "source_file": source,
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


def analyze_rf_csv(file_paths, as_json=False, kp=None):
    if isinstance(file_paths, str):
        file_paths = [file_paths]

    missing = [f for f in file_paths if not os.path.exists(f)]
    if missing:
        for f in missing:
            print(f"Error: {f} not found.")
        return

    try:
        band_data = collect_band_data(file_paths)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return

    label = file_paths if len(file_paths) > 1 else file_paths[0]
    if as_json:
        print_json(label, band_data, kp=kp)
    else:
        print_human(label, band_data, kp=kp)


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
        print("Usage: python check_floor.py <csv> [<csv2> ...] [--json] [--kp <value>] [--fetch-kp]")
        sys.exit(1)

    analyze_rf_csv(files, as_json=as_json, kp=kp)
