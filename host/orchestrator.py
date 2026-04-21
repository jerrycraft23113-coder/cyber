import json
import os
import subprocess
import time
from pathlib import Path
from typing import Optional, Tuple

NEUTRAL_ZONE = Path(os.environ.get("NEUTRAL_ZONE", r"F:\neutral_zone"))
WSB_LAUNCH_TIMEOUT = 120


def validate_neutral_zone(nz: Path) -> bool:
    try:
        test_file = nz / ".write_test"
        test_file.write_text("ok")
        test_file.unlink()
        return True
    except (OSError, TypeError):
        return False


def write_round_config(config: dict, nz: Path) -> None:
    tmp = nz / "round_config.json.tmp"
    tmp.write_text(json.dumps(config, indent=2))
    tmp.replace(nz / "round_config.json")


def append_ga_history(entry: dict, nz: Path) -> None:
    with open(nz / "ga_history.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")


def wait_for_file(path: Path, timeout_s: float, poll_s: float = 0.2) -> Optional[dict]:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            return json.loads(path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            time.sleep(poll_s)
    return None


def score_from_telemetry(t: dict) -> Tuple[float, float]:
    elapsed = t.get("rounds_survived_s", 0)
    peak = t.get("peak_delta", 0)
    t_alert = t.get("time_to_first_alert_s", elapsed)
    wk = t.get("outcome") == "WATCHDOG_KILL"
    exfil = t.get("outcome") == "RED_WIN"
    red_fitness = (
        t_alert * 0.4 + peak * 0.3
        + (1000 if wk else 0) + (500 if exfil else 0)
        - t.get("blue_responses", 0) * 10
    )
    blue_wins = t.get("outcome") == "BLUE_WIN"
    blue_fitness = (
        elapsed * 0.5
        - t.get("blue_false_positives", 0) * 20
        - t.get("null_route_ticks", 0) * 15
        - peak * 100
        + (1000 if blue_wins else 0)
    )
    return red_fitness, blue_fitness


def clean_neutral_zone_round_files(nz: Path) -> None:
    for fname in ["round_config.json", "round_started.json",
                  "telemetry.json", "heartbeat.json",
                  "red_heartbeat.json", "blue_heartbeat.json"]:
        try:
            (nz / fname).unlink()
        except FileNotFoundError:
            pass


class Orchestrator:
    def __init__(self, wsb_path: Path, nz: Path = NEUTRAL_ZONE):
        self.wsb_path = wsb_path
        self.nz = nz

    def run_round(self, config: dict) -> dict:
        if not validate_neutral_zone(self.nz):
            raise RuntimeError(f"Neutral Zone {self.nz} is not writable.")
        clean_neutral_zone_round_files(self.nz)
        write_round_config(config, self.nz)

        wsb_proc = None
        for attempt in range(3):
            try:
                wsb_proc = subprocess.Popen(
                    ["C:\\Windows\\System32\\WindowsSandbox.exe", str(self.wsb_path)],
                    creationflags=subprocess.DETACHED_PROCESS,
                )
            except OSError as e:
                if attempt == 2:
                    raise RuntimeError(f"WSB failed to launch after 3 attempts: {e}")
                time.sleep(5)
                continue
            started = wait_for_file(self.nz / "round_started.json", timeout_s=WSB_LAUNCH_TIMEOUT)
            if started is not None:
                break
            try:
                wsb_proc.kill()
            except Exception:
                pass
            if attempt == 2:
                raise RuntimeError("WSB failed to start round after 3 launch attempts")

        clock_start = time.time()
        timeout = config["time_limit_s"] + 30
        telemetry = wait_for_file(self.nz / "telemetry.json", timeout_s=timeout, poll_s=1.0)

        if telemetry is None:
            red_fit, _ = score_from_telemetry({
                "outcome": "WATCHDOG_KILL",
                "rounds_survived_s": time.time() - clock_start,
                "peak_delta": 1.0,
            })
            telemetry = {
                "round_id": config["round_id"],
                "outcome": "WATCHDOG_KILL",
                "watchdog_killed": True,
                "phase": config["phase"],
                "red_fitness": red_fit + 1000,
                "blue_fitness": 0.0,
            }

        try:
            wsb_proc.kill()
        except Exception:
            pass

        append_ga_history(telemetry, self.nz)
        return telemetry
