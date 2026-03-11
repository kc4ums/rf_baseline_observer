"""
rf_observer_tui.py — RF Baseline Observer Textual TUI
Replaces run_continuous.ps1 with a live terminal UI.

Usage:
    python rf_observer_tui.py
    python rf_observer_tui.py --output-dir D:\rf_data --device 1
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Button, DataTable, Footer, Header, Label, RichLog, Static
from textual.containers import Horizontal, Vertical

from check_floor import (
    HAM_BANDS,
    collect_band_data,
    fetch_kp,
    kp_condition,
    status_for,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
FREQ_HF = "1.8M:28M:100K"
FREQ_VHF = "28M:1.766G:100K"
SWEEP_DURATION = "30m"

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class BandRow:
    name: str
    avg_dbm: Optional[float]
    peak_dbm: Optional[float]
    samples: int
    status: str  # NOMINAL | WARNING | CRITICAL | NO_DATA


@dataclass
class CycleResult:
    cycle_num: int
    timestamp: str
    kp: Optional[float]
    condition: str
    bands: list[BandRow]
    json_record: dict


# ---------------------------------------------------------------------------
# Custom Textual Messages (thread-safe signals)
# ---------------------------------------------------------------------------

class SweepPhaseChanged(Message):
    def __init__(self, phase: str) -> None:
        super().__init__()
        self.phase = phase


class SweepCycleComplete(Message):
    def __init__(self, result: CycleResult) -> None:
        super().__init__()
        self.result = result


class SweepError(Message):
    def __init__(self, msg: str) -> None:
        super().__init__()
        self.msg = msg


class SweepDebug(Message):
    def __init__(self, msg: str) -> None:
        super().__init__()
        self.msg = msg


# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------

class RFObserverApp(App):
    """RF Baseline Observer — Textual TUI."""

    TITLE = "RF Baseline Observer — RTL-SDR V4"
    SUB_TITLE = "HAM Band Noise Floor Monitor"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("s", "toggle_sweep", "Start/Stop"),
        Binding("c", "copy_history", "Copy History"),
    ]

    CSS = """
    Screen {
        background: $surface;
    }

    #main-row {
        height: 1fr;
    }

    #left-panel {
        width: 3fr;
        border: solid $primary;
        padding: 0 1;
    }

    #left-panel-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    #right-panel {
        width: 1fr;
        border: solid $primary;
        padding: 0 1;
    }

    #phase-label {
        color: $warning;
        text-style: bold;
    }

    #cycle-label {
        color: $text-muted;
    }

    #space-weather-title {
        text-style: bold;
        color: $accent;
        margin-top: 1;
    }

    #kp-label {
        color: $text;
    }

    #controls-title {
        text-style: bold;
        color: $accent;
        margin-top: 1;
    }

    #btn-start {
        margin-top: 1;
        width: 100%;
    }

    #btn-stop {
        margin-top: 1;
        width: 100%;
    }

    #history-title {
        text-style: bold;
        color: $accent;
        padding-left: 1;
    }

    #history-log {
        height: 8;
        border: solid $primary;
        padding: 0 1;
    }

    DataTable {
        height: 1fr;
    }
    """

    # Reactive state
    phase: reactive[str] = reactive("Idle")
    cycle_num: reactive[int] = reactive(0)
    elapsed_seconds: reactive[int] = reactive(0)
    running: reactive[bool] = reactive(False)
    kp_display: reactive[str] = reactive("--")

    def __init__(self, output_dir: Path, device_idx: int = 0) -> None:
        super().__init__()
        self.output_dir = output_dir
        self.device_idx = device_idx
        self._stop_event = threading.Event()
        self._elapsed_timer = None
        self._phase_start: Optional[datetime] = None
        self._history_plain: list[str] = []  # plain-text mirror for clipboard

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()

        with Horizontal(id="main-row"):
            with Vertical(id="left-panel"):
                yield Label("HAM BAND RF NOISE FLOOR", id="left-panel-title")
                yield DataTable(id="band-table")

            with Vertical(id="right-panel"):
                yield Label("SWEEP STATUS", id="right-panel-title")
                yield Label("Idle", id="phase-label")
                yield Label("Cycle: 0", id="cycle-label")
                yield Label("SPACE WEATHER", id="space-weather-title")
                yield Label("Kp: --  [--]", id="kp-label")
                yield Label("CONTROLS", id="controls-title")
                yield Button("Start", id="btn-start", variant="success")
                yield Button("Stop", id="btn-stop", variant="error", disabled=True)

        yield Label("CYCLE HISTORY", id="history-title")
        yield RichLog(id="history-log", highlight=True, markup=True)
        yield Footer()

    def on_mount(self) -> None:
        """Set up the DataTable with all 16 band rows."""
        table = self.query_one("#band-table", DataTable)
        table.add_columns("Band", "Avg(dBm)", "Peak(dBm)", "Samples", "Status")
        table.cursor_type = "none"
        for name, _, _ in HAM_BANDS:
            table.add_row(
                name, "--", "--", "0", "[dim]NO DATA[/dim]",
                key=name
            )

    # ------------------------------------------------------------------
    # Reactive watchers
    # ------------------------------------------------------------------

    def watch_phase(self, new_phase: str) -> None:
        label = self.query_one("#phase-label", Label)
        elapsed = self._elapsed_str()
        label.update(f"{new_phase} (elapsed: {elapsed})" if new_phase != "Idle" else "Idle")

    def watch_cycle_num(self, new_val: int) -> None:
        self.query_one("#cycle-label", Label).update(f"Cycle: {new_val}")

    def watch_running(self, new_val: bool) -> None:
        self.query_one("#btn-start", Button).disabled = new_val
        self.query_one("#btn-stop", Button).disabled = not new_val

    def watch_kp_display(self, new_val: str) -> None:
        self.query_one("#kp-label", Label).update(new_val)

    def watch_elapsed_seconds(self, _: int) -> None:
        label = self.query_one("#phase-label", Label)
        label.update(f"{self.phase} (elapsed: {self._elapsed_str()})")

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-start":
            self.action_toggle_sweep()
        elif event.button.id == "btn-stop":
            self.action_toggle_sweep()

    def action_toggle_sweep(self) -> None:
        if not self.running:
            self._stop_event.clear()
            self.running = True
            self._run_sweep_loop()
        else:
            self._stop_event.set()
            self.running = False

    # ------------------------------------------------------------------
    # Message handlers (called on the UI thread)
    # ------------------------------------------------------------------

    def on_sweep_phase_changed(self, message: SweepPhaseChanged) -> None:
        self.phase = message.phase
        if message.phase not in ("Idle", "Analyzing"):
            self._start_elapsed_timer()
        else:
            self._stop_elapsed_timer()
            self.elapsed_seconds = 0

    def on_sweep_cycle_complete(self, message: SweepCycleComplete) -> None:
        result = message.result
        self.cycle_num = result.cycle_num
        kp_str = f"{result.kp:.1f}" if result.kp is not None else "N/A"
        self.kp_display = f"Kp: {kp_str}  [{result.condition}]"
        self._update_band_table(result.bands)
        self._append_history(result)
        self._write_log(json.dumps(result.json_record))

    def on_sweep_error(self, message: SweepError) -> None:
        log = self.query_one("#history-log", RichLog)
        log.write(f"[red][ERROR] {message.msg}[/red]")

    def on_sweep_debug(self, message: SweepDebug) -> None:
        log = self.query_one("#history-log", RichLog)
        log.write(f"[dim cyan][DBG] {message.msg}[/dim cyan]")

    # ------------------------------------------------------------------
    # Band table update
    # ------------------------------------------------------------------

    def _update_band_table(self, bands: list[BandRow]) -> None:
        table = self.query_one("#band-table", DataTable)
        for row in bands:
            if row.avg_dbm is None:
                avg_str = "--"
                peak_str = "--"
                samples_str = "0"
                status_markup = "[dim]NO DATA[/dim]"
            else:
                avg_str = f"{row.avg_dbm:.2f}"
                peak_str = f"{row.peak_dbm:.2f}"
                samples_str = str(row.samples)
                if row.status == "NOMINAL":
                    status_markup = f"[green]{row.status}[/green]"
                elif row.status == "WARNING":
                    status_markup = f"[yellow]{row.status}[/yellow]"
                else:  # CRITICAL
                    status_markup = f"[red]{row.status}[/red]"

            # Update each column cell by row key
            col_keys = ["Band", "Avg(dBm)", "Peak(dBm)", "Samples", "Status"]
            values = [row.name, avg_str, peak_str, samples_str, status_markup]
            for col_key, val in zip(col_keys, values):
                try:
                    table.update_cell(row_key=row.name, column_key=col_key, value=val)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Elapsed timer
    # ------------------------------------------------------------------

    def _elapsed_str(self) -> str:
        secs = self.elapsed_seconds
        minutes, seconds = divmod(secs, 60)
        return f"{minutes:02d}:{seconds:02d}"

    def _start_elapsed_timer(self) -> None:
        self._stop_elapsed_timer()
        self.elapsed_seconds = 0
        self._elapsed_timer = self.set_interval(1.0, self._tick_elapsed)

    def _stop_elapsed_timer(self) -> None:
        if self._elapsed_timer is not None:
            self._elapsed_timer.stop()
            self._elapsed_timer = None

    def _tick_elapsed(self) -> None:
        self.elapsed_seconds += 1

    # ------------------------------------------------------------------
    # History log
    # ------------------------------------------------------------------

    def _append_history(self, result: CycleResult) -> None:
        log = self.query_one("#history-log", RichLog)
        nominal = sum(1 for b in result.bands if b.status == "NOMINAL")
        warn = sum(1 for b in result.bands if b.status == "WARNING")
        crit = sum(1 for b in result.bands if b.status == "CRITICAL")
        kp_str = f"{result.kp:.1f}" if result.kp is not None else "N/A"
        plain = (
            f"[{result.timestamp}] Cycle {result.cycle_num} | "
            f"Kp={kp_str} [{result.condition}] | "
            f"NOMINAL:{nominal} WARN:{warn} CRIT:{crit}"
        )
        self._history_plain.append(plain)
        line = (
            f"[dim][{result.timestamp}][/dim] "
            f"Cycle {result.cycle_num} | "
            f"Kp={kp_str} [{result.condition}] | "
            f"[green]NOMINAL:{nominal}[/green] "
            f"[yellow]WARN:{warn}[/yellow] "
            f"[red]CRIT:{crit}[/red]"
        )
        log.write(line)

    # ------------------------------------------------------------------
    # Log file writer
    # ------------------------------------------------------------------

    def _write_log(self, json_str: str) -> None:
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            log_path = self.output_dir / "rf_history.log"
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json_str + "\n")
        except Exception as e:
            self.post_message(SweepError(f"Could not write log: {e}"))

    # ------------------------------------------------------------------
    # Sweep worker (runs in background thread)
    # ------------------------------------------------------------------

    @work(thread=True)
    def _run_sweep_loop(self) -> None:
        cycle = 0
        self.output_dir.mkdir(parents=True, exist_ok=True)

        while not self._stop_event.is_set():
            cycle += 1
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")

            hf_csv = str(self.output_dir / f"hf_{ts}.csv")
            vhf_csv = str(self.output_dir / f"vhf_{ts}.csv")

            # --- HF Sweep ---
            self.post_message(SweepPhaseChanged("HF Sweep"))
            hf_ok = self._run_rtl_power(
                freq=FREQ_HF,
                output_csv=hf_csv,
                direct_sampling=True,
            )
            if self._stop_event.is_set():
                break

            # --- VHF/UHF Sweep ---
            self.post_message(SweepPhaseChanged("VHF/UHF Sweep"))
            vhf_ok = self._run_rtl_power(
                freq=FREQ_VHF,
                output_csv=vhf_csv,
                direct_sampling=False,
            )
            if self._stop_event.is_set():
                break

            # --- Analysis ---
            self.post_message(SweepPhaseChanged("Analyzing"))
            self.post_message(SweepDebug(f"hf_ok={hf_ok} vhf_ok={vhf_ok}"))
            try:
                csv_files = []
                if hf_ok and Path(hf_csv).exists():
                    csv_files.append(hf_csv)
                if vhf_ok and Path(vhf_csv).exists():
                    csv_files.append(vhf_csv)

                self.post_message(SweepDebug(f"Analyzing {len(csv_files)} CSV(s): {[Path(f).name for f in csv_files]}"))

                if not csv_files:
                    self.post_message(SweepError(f"Cycle {cycle}: no CSV data produced"))
                    continue

                band_data = collect_band_data(csv_files)
                kp = fetch_kp()
                condition = kp_condition(kp)
                now_utc = datetime.now(timezone.utc).strftime("%H:%M:%S")

                band_rows: list[BandRow] = []
                json_bands: dict = {}

                for name, _, _ in HAM_BANDS:
                    vals = band_data.get(name, [])
                    if not vals:
                        band_rows.append(BandRow(name, None, None, 0, "NO_DATA"))
                        json_bands[name] = {
                            "avg_dbm": None, "peak_dbm": None,
                            "samples": 0, "status": "NO_DATA"
                        }
                    else:
                        arr = np.array(vals)
                        avg = round(float(np.mean(arr)), 2)
                        peak = round(float(np.max(arr)), 2)
                        status = status_for(avg)
                        band_rows.append(BandRow(name, avg, peak, len(vals), status))
                        json_bands[name] = {
                            "avg_dbm": avg, "peak_dbm": peak,
                            "samples": len(vals), "status": status
                        }

                json_record = {
                    "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "cycle": cycle,
                    "source_files": [Path(f).name for f in csv_files],
                    "space_weather": {
                        "kp_index": kp,
                        "condition": condition,
                    },
                    "bands": json_bands,
                }

                result = CycleResult(
                    cycle_num=cycle,
                    timestamp=now_utc,
                    kp=kp,
                    condition=condition,
                    bands=band_rows,
                    json_record=json_record,
                )
                self.post_message(SweepCycleComplete(result))

            except Exception as e:
                self.post_message(SweepError(f"Cycle {cycle} analysis failed: {e}"))

        self.post_message(SweepPhaseChanged("Idle"))
        self.app.call_from_thread(setattr, self, "running", False)

    def _run_rtl_power(
        self, freq: str, output_csv: str, direct_sampling: bool
    ) -> bool:
        """Run rtl_power as a subprocess; poll every second for stop signal.

        Returns True if process exited successfully, False otherwise.
        """
        cmd = ["rtl_power"]
        cmd += ["-d", str(self.device_idx)]
        if direct_sampling:
            cmd += ["-D", "2"]
        cmd += ["-f", freq, "-i", SWEEP_DURATION, "-e", SWEEP_DURATION, output_csv]

        self.post_message(SweepDebug(f"CMD: {' '.join(cmd)}"))

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # merge stderr into stdout for capture
            )
        except FileNotFoundError:
            self.post_message(SweepError("rtl_power not found — is it on PATH?"))
            return False
        except Exception as e:
            self.post_message(SweepError(f"Could not start rtl_power: {e}"))
            return False

        self.post_message(SweepDebug(f"PID: {proc.pid}"))

        while True:
            if self._stop_event.wait(timeout=1.0):
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                return False
            ret = proc.poll()
            if ret is not None:
                break

        # Read all output for diagnostics
        try:
            output_text = proc.stdout.read().decode(errors="replace").strip()
        except Exception:
            output_text = ""

        self.post_message(SweepDebug(f"Exit code: {ret}"))
        if output_text:
            for line in output_text.splitlines()[-10:]:  # last 10 lines
                self.post_message(SweepDebug(f"  > {line}"))

        csv_path = Path(output_csv)
        if csv_path.exists():
            size = csv_path.stat().st_size
            self.post_message(SweepDebug(f"CSV: {csv_path.name} ({size} bytes)"))
            if size > 0:
                return True
            self.post_message(SweepError(f"rtl_power created empty CSV (exit {ret})"))
            return False

        self.post_message(SweepError(f"rtl_power produced no CSV file (exit {ret})"))
        return False

    # ------------------------------------------------------------------
    # Clipboard
    # ------------------------------------------------------------------

    def action_copy_history(self) -> None:
        if not self._history_plain:
            self.notify("No history to copy yet.", severity="warning")
            return
        text = "\n".join(self._history_plain)
        try:
            proc = subprocess.Popen(
                ["clip"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            proc.communicate(input=text.encode("utf-16-le"))
            self.notify(f"Copied {len(self._history_plain)} cycle(s) to clipboard.")
        except Exception as e:
            self.notify(f"Clipboard failed: {e}", severity="error")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_unmount(self) -> None:
        self._stop_event.set()
        self._stop_elapsed_timer()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    default_output = os.path.expandvars(r"%USERPROFILE%\rf_logs")

    parser = argparse.ArgumentParser(
        description="RF Baseline Observer — Textual TUI"
    )
    parser.add_argument(
        "--output-dir",
        default=default_output,
        help=f"Directory for CSV and log files (default: {default_output})",
    )
    parser.add_argument(
        "--device",
        type=int,
        default=0,
        help="RTL-SDR device index (default: 0)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    RFObserverApp(output_dir=output_dir, device_idx=args.device).run()


if __name__ == "__main__":
    main()
