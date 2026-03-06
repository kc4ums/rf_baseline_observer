import pandas as pd
import numpy as np
import sys
import os

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


def band_for_freq(hz):
    for name, low, high in HAM_BANDS:
        if low <= hz <= high:
            return name
    return None


def analyze_rf_csv(file_path):
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found.")
        return

    try:
        df = pd.read_csv(file_path, header=None)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return

    # rtl_power CSV columns: date, time, hz_low, hz_high, hz_step, samples, [power...]
    band_data = {name: [] for name, _, _ in HAM_BANDS}

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

    print(f"--- RF NOISE REPORT: {os.path.basename(file_path)} ---")
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
        avg  = np.mean(arr)
        peak = np.max(arr)

        if avg > -60:
            status = "CRITICAL - high noise"
        elif avg > -75:
            status = "WARNING  - elevated"
        else:
            status = "NOMINAL"

        print(f"{name:<8} {avg:>10.2f} {peak:>11.2f} {len(vals):>8}  {status}")

    if not any_data:
        print("No ham band data found. Check that the CSV covers ham band frequencies.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_floor.py <path_to_csv>")
        sys.exit(1)
    analyze_rf_csv(sys.argv[1])
