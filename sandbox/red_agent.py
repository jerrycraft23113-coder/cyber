# sandbox/red_agent.py
"""
Red Agent — adversarial process running inside WSB.
Executes stealth (Phase A), disruption (Phase B), and exfil (Phase C) actions
according to its genome loaded from round_config.json.
"""
import json
import os
import sys
import time
import random
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
from sandbox.watchdog import atomic_write_json, read_json_with_backoff

try:
    import winreg
except ImportError:
    winreg = None

NEUTRAL_ZONE = Path(os.environ.get("NEUTRAL_ZONE", r"F:\neutral_zone"))
MAX_STEALTH_DELAY_MS = 2000
TICK_INTERVAL = 2.0


def _reg_key_from_genome(reg_hive_bias: float) -> str:
    if reg_hive_bias < 0.5:
        return r"HKCU\Software\VanguardTest"
    return r"HKLM\SOFTWARE\VanguardTest"


class RedAgent:
    def __init__(self, nz: Path = NEUTRAL_ZONE):
        self.nz = nz
        self.config: dict = {}
        self.params: dict = {}
        self.actions_taken = 0

    def load_config(self) -> bool:
        cfg = read_json_with_backoff(self.nz / "round_config.json")
        if not cfg:
            return False
        self.config = cfg
        g = cfg["red_genome"]
        self.params = {
            "file_drop_rate":     g[0],
            "reg_key_count":      g[1],
            "stealth_delay_ms":   g[2],
            "drop_location_bias": g[3],
            "reg_hive_bias":      g[4],
        }
        if len(g) > 5:
            self.params["process_kill_freq"]  = g[5]
            self.params["cpu_spike_intensity"] = g[6]
        if len(g) > 7:
            self.params["exfil_chunk_size"]  = g[7]
            self.params["exfil_encrypt_flag"] = g[8]
        return True

    def _stealth_delay(self) -> None:
        self._ensure_config()
        delay = self.params.get("stealth_delay_ms", 0.0) * MAX_STEALTH_DELAY_MS / 1000
        if delay > 0:
            time.sleep(delay)

    def _ensure_config(self) -> None:
        """Lazy-load config if params have not been populated yet."""
        if not self.params:
            self.load_config()

    def action_file_drop(self) -> None:
        self._ensure_config()
        if random.random() > self.params["file_drop_rate"]:
            return
        bias = self.params.get("drop_location_bias", 0.0)
        if bias < 0.5:
            drop_dir = Path(r"C:\Users\WDAGUtilityAccount\Desktop")
        else:
            drop_dir = Path(r"C:\Users\WDAGUtilityAccount\AppData\Roaming")
        try:
            drop_dir.mkdir(parents=True, exist_ok=True)
            fname = drop_dir / f"tmp_{random.randint(10000,99999)}.red"
            fname.write_text("red_payload")
        except OSError:
            pass

    def action_reg_write(self) -> None:
        self._ensure_config()
        count = max(1, int(self.params["reg_key_count"] * 5))
        hive_bias = self.params.get("reg_hive_bias", 0.0)
        key_str = _reg_key_from_genome(hive_bias)
        if winreg is None:
            return
        parts = key_str.split("\\", 1)
        hive = winreg.HKEY_CURRENT_USER if parts[0] == "HKCU" else winreg.HKEY_LOCAL_MACHINE
        subkey = parts[1] if len(parts) > 1 else "VanguardTest"
        try:
            with winreg.CreateKey(hive, subkey) as key:
                for i in range(count):
                    winreg.SetValueEx(key, f"red_val_{i}", 0, winreg.REG_SZ, f"data_{i}")
        except OSError:
            pass

    def write_heartbeat(self) -> None:
        atomic_write_json(self.nz / "red_heartbeat.json", {
            "alive": True,
            "tick_time": time.time(),
            "actions_taken": self.actions_taken,
        })

    def run_tick(self) -> None:
        self._stealth_delay()
        self.action_file_drop()
        self.action_reg_write()
        self.actions_taken += 1
        self.write_heartbeat()

    def run(self) -> None:
        if not self.load_config():
            return
        while True:
            self.run_tick()
            time.sleep(TICK_INTERVAL)


if __name__ == "__main__":
    RedAgent().run()
