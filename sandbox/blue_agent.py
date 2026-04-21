# sandbox/blue_agent.py
"""
Blue Agent — Vanguard driver / defender running inside WSB.
Reads heartbeat.json each tick, decides on an action, executes it.
"""
import json
import os
import sys
import time
import shutil
import subprocess
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
from sandbox.watchdog import atomic_write_json, read_json_with_backoff

try:
    import psutil
    import ctypes
except ImportError:
    psutil = None
    ctypes = None

NEUTRAL_ZONE = Path(os.environ.get("NEUTRAL_ZONE", r"F:\neutral_zone"))
TICK_INTERVAL = 2.0


def decide_action(tier: str, delta: float, genome: list) -> Optional[dict]:
    """
    Decide which action to take based on alert tier and delta.
    Returns None (no action), or a dict with 'type' and relevant args.

    Tier semantics:
      NOMINAL / WATCH  → no action (monitor only)
      ALERT            → always FREEZE (tier classification already crossed
                         the freeze threshold)
      CRITICAL         → NULL_ROUTE if delta >= null_route_threshold,
                         else FREEZE
    """
    null_route_thresh = genome[6]

    if tier == "NOMINAL":
        return None
    if tier == "WATCH":
        return None  # monitor only
    if tier == "ALERT":
        return {"type": "FREEZE", "target": "newest_suspicious"}
    if tier == "CRITICAL":
        if delta >= null_route_thresh:
            return {"type": "NULL_ROUTE"}
        return {"type": "FREEZE", "target": "newest_suspicious"}
    return None


class BlueAgent:
    def __init__(self, nz: Path = NEUTRAL_ZONE):
        self.nz = nz
        self.config: dict = {}
        self.genome: list = []
        self.null_route_active = False
        self.responses = 0

    def load_config(self) -> bool:
        cfg = read_json_with_backoff(self.nz / "round_config.json")
        if not cfg:
            return False
        self.config = cfg
        self.genome = cfg["blue_genome"]
        return True

    def read_heartbeat(self) -> Optional[dict]:
        return read_json_with_backoff(self.nz / "heartbeat.json", max_retries=3, backoff_s=0.05)

    def action_freeze(self, t0_pids: list) -> None:
        """Freeze the most recently spawned non-baseline process."""
        if psutil is None:
            return
        t0_set = set(t0_pids)
        candidates = [
            p for p in psutil.process_iter(["pid", "create_time"])
            if p.pid not in t0_set
        ]
        if not candidates:
            return
        target = max(candidates, key=lambda p: p.info["create_time"])
        try:
            target.suspend()
            self.responses += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    def action_null_route(self, activate: bool) -> None:
        """Activate or deactivate Windows Firewall outbound block rule."""
        if activate and not self.null_route_active:
            subprocess.run(
                ["netsh", "advfirewall", "firewall", "add", "rule",
                 "name=VanguardNullRoute", "dir=out", "action=block", "protocol=any"],
                capture_output=True,
            )
            self.null_route_active = True
        elif not activate and self.null_route_active:
            subprocess.run(
                ["netsh", "advfirewall", "firewall", "delete", "rule",
                 "name=VanguardNullRoute"],
                capture_output=True,
            )
            self.null_route_active = False

    def action_quarantine(self, path: str) -> None:
        q_dir = self.nz / "quarantine"
        q_dir.mkdir(exist_ok=True)
        try:
            shutil.move(path, str(q_dir))
            self.responses += 1
        except OSError:
            pass

    def action_restore_reg(self, key: str) -> None:
        """
        Restore a monitored registry key to its T=0 value.
        For Phase A, Blue uses RESTORE_REG to undo Red's registry writes:
        deletes all values under the monitored subkey.
        """
        try:
            import winreg
            parts = key.split("\\", 1)
            hive = winreg.HKEY_CURRENT_USER if parts[0] == "HKCU" else winreg.HKEY_LOCAL_MACHINE
            # Delete the entire subkey tree to wipe Red's writes
            winreg.DeleteKey(hive, parts[1])
            self.responses += 1
        except Exception:
            pass  # key didn't exist or access denied — acceptable

    def write_heartbeat(self) -> None:
        atomic_write_json(self.nz / "blue_heartbeat.json", {
            "alive": True,
            "tick_time": time.time(),
            "responses": self.responses,
        })

    def run_tick(self) -> None:
        hb = self.read_heartbeat()
        if not hb:
            self.write_heartbeat()
            return

        tier = hb.get("tier", "NOMINAL")
        delta = hb.get("delta", 0.0)
        t0_pids = hb.get("t0_pids", [])

        action = decide_action(tier, delta, self.genome)

        if action:
            if action["type"] == "FREEZE":
                self.action_freeze(t0_pids)
            elif action["type"] == "NULL_ROUTE":
                self.action_null_route(activate=True)
        else:
            # Deactivate NULL_ROUTE if tier drops
            if self.null_route_active and tier in ("NOMINAL", "WATCH"):
                self.action_null_route(activate=False)

        self.write_heartbeat()

    def run(self) -> None:
        if not self.load_config():
            return
        while True:
            self.run_tick()
            time.sleep(TICK_INTERVAL)


if __name__ == "__main__":
    BlueAgent().run()
