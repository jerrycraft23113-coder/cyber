# sandbox/watchdog.py
"""
Watchdog — Matrix Masking oracle and round Referee.

Entry point: python watchdog.py  (launched by WSB logon command)
Reads round_config.json from F:\\neutral_zone\\, runs the round,
writes telemetry.json atomically at end.
"""
import json
import os
import sys
import time
import subprocess
from pathlib import Path
from typing import Optional

import numpy as np
import psutil

# Allow running from sandbox\ dir or project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.genome import validate, BOOTSTRAP_BLUE
from sandbox.state_vector import build_state_vector, CpuMovingAverage
from sandbox.matrix_delta import (
    build_weights, compute_delta_raw, compute_delta,
    measure_noise_floor, classify_tier,
)

NEUTRAL_ZONE = Path(os.environ.get("NEUTRAL_ZONE", r"F:\neutral_zone"))
TICK_INTERVAL = 2.0
NOISE_FLOOR_DURATION = 10.0


# ── File I/O helpers ─────────────────────────────────────────────────────────

def atomic_write_json(path: Path, data: dict) -> None:
    """Write data to path atomically via temp-file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


def read_json_with_backoff(
    path: Path, max_retries: int = 10, backoff_s: float = 0.1
) -> Optional[dict]:
    """Read JSON file with retries. Returns None if file absent after all retries."""
    for _ in range(max_retries):
        try:
            return json.loads(path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            time.sleep(backoff_s)
    return None


def check_liveness(
    heartbeat_path: Path, missing_ticks: int, max_missing: int,
    tick_interval: float = TICK_INTERVAL,
) -> bool:
    """
    Return True if process is considered alive.
    Uses mtime freshness — a stale file from a prior tick is treated as absent.
    'missing_ticks' is the caller's counter; incremented externally each tick the
    file is absent or stale.
    """
    try:
        mtime = heartbeat_path.stat().st_mtime
        age = time.time() - mtime
        if age <= tick_interval * 1.5:   # file updated within last 1.5 ticks
            return True
    except FileNotFoundError:
        pass
    return missing_ticks < max_missing


def _is_heartbeat_fresh(path: Path, tick_interval: float = TICK_INTERVAL) -> bool:
    """Return True only if the heartbeat file exists and is within 1.5 tick intervals."""
    try:
        age = time.time() - path.stat().st_mtime
        return age <= tick_interval * 1.5
    except FileNotFoundError:
        return False


# ── Watchdog round ────────────────────────────────────────────────────────────

class WatchdogRound:
    def __init__(self, nz: Path = NEUTRAL_ZONE):
        self.nz = nz
        self.config: dict = {}
        self.V0: Optional[np.ndarray] = None
        self.weights: Optional[np.ndarray] = None
        self.noise_floor: float = 0.0
        self.cpu_ma: Optional[CpuMovingAverage] = None
        self.t0_pids: set = set()

        # Round state
        self.red_missing = 0
        self.blue_missing = 0
        self.blue_below_ticks = 0
        self.null_route_active = False
        self.null_route_ticks = 0
        self.blue_false_positives = 0
        self.blue_responses = 0
        self.red_actions_taken = 0
        self.peak_delta = 0.0
        self.time_to_first_alert_s: Optional[float] = None
        self.start_time: float = 0.0
        self.exfil_complete = False

        # Tracking for BLUE_WIN
        self.delta_exceeded_threshold = False

    def load_config(self) -> Optional[str]:
        cfg = read_json_with_backoff(self.nz / "round_config.json")
        if cfg is None:
            return "CONFIG_ERROR: round_config.json not found"

        err = validate(cfg["blue_genome"], cfg["phase"])
        if err:
            return f"CONFIG_ERROR: blue genome invalid: {err}"
        err = validate(cfg["red_genome"], cfg["phase"], role="red")
        if err:
            return f"CONFIG_ERROR: red genome invalid: {err}"

        # Alert tier overlap guard
        if cfg["delta_threshold"] * 0.5 < 0.02:
            return "CONFIG_ERROR: delta_threshold too small, alert tiers overlap"

        self.config = cfg
        return None

    def measure_noise(self) -> None:
        """Sample delta_raw for NOISE_FLOOR_DURATION seconds before Red launches."""
        ma_window = self.config["blue_genome"][7]
        self.cpu_ma = CpuMovingAverage(window_s=ma_window)
        import psutil as _psutil
        samples = []
        deadline = time.time() + NOISE_FLOOR_DURATION
        while time.time() < deadline:
            cores = _psutil.cpu_percent(percpu=True)
            self.cpu_ma.update(cores)
            time.sleep(0.5)

        # Snapshot T=0 after noise floor
        self.V0 = build_state_vector(self.config, self.cpu_ma)
        self.weights = build_weights(
            self.config["blue_genome"], self.config["cpu_core_count"]
        )
        self.t0_pids = {p.pid for p in _psutil.process_iter()}

        # Measure noise floor: take fresh CPU+state readings at 0.5s intervals
        # so the MA advances and captures real Windows background variance.
        noise_samples = []
        for _ in range(10):
            time.sleep(0.5)
            cores = _psutil.cpu_percent(percpu=True)
            self.cpu_ma.update(cores)
            Vs = build_state_vector(self.config, self.cpu_ma)
            raw = compute_delta_raw(Vs, self.V0, self.weights)
            noise_samples.append(raw)
        self.noise_floor = measure_noise_floor(noise_samples)

    def launch_agents(self) -> None:
        sandbox_dir = Path(__file__).parent
        subprocess.Popen(
            [sys.executable, str(sandbox_dir / "red_agent.py")],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        subprocess.Popen(
            [sys.executable, str(sandbox_dir / "blue_agent.py")],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )

    def tick(self) -> Optional[str]:
        """Run one tick. Returns outcome string if round should end, else None."""
        import psutil as _psutil

        # 1. Update CPU MA
        self.cpu_ma.update(_psutil.cpu_percent(percpu=True))

        # 2. Measure delta
        Vt = build_state_vector(self.config, self.cpu_ma)
        delta_raw = compute_delta_raw(Vt, self.V0, self.weights)
        delta = compute_delta(delta_raw, self.noise_floor)
        tier = classify_tier(delta, self.config["delta_threshold"])

        if delta > self.peak_delta:
            self.peak_delta = delta

        if delta >= self.config["delta_threshold"]:
            self.delta_exceeded_threshold = True

        if tier in ("ALERT", "CRITICAL") and self.time_to_first_alert_s is None:
            self.time_to_first_alert_s = time.time() - self.start_time

        # 3. NULL_ROUTE auto-deactivate on Blue crash
        blue_hb = self.nz / "blue_heartbeat.json"
        if not _is_heartbeat_fresh(blue_hb) and self.blue_missing >= 1:
            self.null_route_active = False

        if self.null_route_active:
            self.null_route_ticks += 1

        # 4. Write heartbeat
        atomic_write_json(self.nz / "heartbeat.json", {
            "delta": delta,
            "tier": tier,
            "null_route_active": self.null_route_active,
            "t0_pids": list(self.t0_pids),
            "tick_time": time.time(),
        })

        # 5. Check liveness (mtime-based — stale file counts as missing)
        red_hb = self.nz / "red_heartbeat.json"

        if _is_heartbeat_fresh(red_hb):
            self.red_missing = 0
        else:
            self.red_missing += 1

        if _is_heartbeat_fresh(blue_hb):
            self.blue_missing = 0
        else:
            self.blue_missing += 1

        if self.red_missing >= 2:
            return "RED_CRASH"
        if self.blue_missing >= 2:
            pass  # round continues; Blue scores 0

        # 6. Check exfil (Phase C)
        exfil_dir = self.nz / "exfil"
        if exfil_dir.exists():
            total_bytes = sum(
                f.stat().st_size for f in exfil_dir.iterdir() if f.is_file()
            )
            target = self.config.get("exfil_target_size_kb", 100) * 1024
            if total_bytes >= target:
                self.exfil_complete = True
                return "RED_WIN"

        # 7. Check BLUE_WIN: delta stayed below threshold for blue_win_hold_s
        if delta < self.config["delta_threshold"]:
            self.blue_below_ticks += 1
        else:
            self.blue_below_ticks = 0

        hold_ticks = self.config["blue_win_hold_s"] / TICK_INTERVAL
        if self.blue_below_ticks >= hold_ticks:
            return "BLUE_WIN"

        return None

    def compute_fitness(self, outcome: str) -> tuple:
        elapsed = time.time() - self.start_time
        t_alert = self.time_to_first_alert_s or elapsed
        wk = outcome == "WATCHDOG_KILL"
        exfil = self.exfil_complete

        red_fitness = (
            t_alert * 0.4
            + self.peak_delta * 0.3
            + (1000 if wk else 0)
            + (500 if exfil else 0)
            - self.blue_responses * 10
        )
        blue_wins = outcome == "BLUE_WIN"
        blue_fitness = (
            elapsed * 0.5
            - self.blue_false_positives * 20
            - self.null_route_ticks * 15
            - self.peak_delta * 100
            + (1000 if blue_wins else 0)
        )
        return red_fitness, blue_fitness

    def run(self) -> None:
        error = self.load_config()
        if error:
            atomic_write_json(self.nz / "telemetry.json", {
                "round_id": self.config.get("round_id", "unknown"),
                "outcome": "CONFIG_ERROR",
                "error": error,
            })
            return

        self.measure_noise()
        atomic_write_json(self.nz / "round_started.json", {
            "round_id": self.config["round_id"],
            "started_at": time.time(),
        })

        self.launch_agents()
        self.start_time = time.time()
        deadline = self.start_time + self.config["time_limit_s"]
        outcome = None

        while time.time() < deadline:
            outcome = self.tick()
            if outcome:
                break
            time.sleep(TICK_INTERVAL)

        if outcome is None:
            outcome = "DRAW" if self.delta_exceeded_threshold else "BLUE_WIN"

        red_fit, blue_fit = self.compute_fitness(outcome)
        elapsed = time.time() - self.start_time

        atomic_write_json(self.nz / "telemetry.json", {
            "round_id": self.config["round_id"],
            "outcome": outcome,
            "watchdog_killed": False,
            "phase": self.config["phase"],
            "rounds_survived_s": round(elapsed, 2),
            "peak_delta": round(self.peak_delta, 6),
            "time_to_first_alert_s": round(self.time_to_first_alert_s, 3) if self.time_to_first_alert_s is not None else None,
            "red_actions_taken": self.red_actions_taken,
            "blue_responses": self.blue_responses,
            "blue_false_positives": self.blue_false_positives,
            "null_route_ticks": self.null_route_ticks,
            "red_fitness": round(red_fit, 2),
            "blue_fitness": round(blue_fit, 2),
        })


if __name__ == "__main__":
    WatchdogRound().run()
