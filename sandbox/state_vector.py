import collections
import os
import binascii
from typing import List, Optional

import numpy as np
import psutil

try:
    import winreg
except ImportError:
    winreg = None  # allow import on non-Windows for testing

_HIVE_MAP = {
    "HKCU": lambda: winreg.HKEY_CURRENT_USER,
    "HKLM": lambda: winreg.HKEY_LOCAL_MACHINE,
}


def _parse_key_path(key_str: str):
    """Split 'HKCU\\Path\\To\\Key' into (hive_handle, subkey_str)."""
    parts = key_str.split("\\", 1)
    hive_name = parts[0]
    subkey = parts[1] if len(parts) > 1 else ""
    hive = _HIVE_MAP[hive_name]()
    return hive, subkey


def hash_registry_keys(key_list: List[str]) -> int:
    """
    Return XOR of CRC32 hashes of all values under each key.
    Missing or inaccessible keys contribute 0 (silent skip).
    """
    result = 0
    for key_str in key_list:
        try:
            hive, subkey = _parse_key_path(key_str)
            with winreg.OpenKey(hive, subkey) as hkey:
                num_values, _, _ = winreg.QueryInfoKey(hkey)
                for i in range(num_values):
                    name, data, _ = winreg.EnumValue(hkey, i)
                    payload = f"{name}={data}".encode("utf-8", errors="replace")
                    crc = binascii.crc32(payload) & 0xFFFFFFFF
                    result ^= crc
        except (OSError, TypeError, KeyError):
            pass
    return result


def count_files(dir_list: List[str]) -> int:
    """Recursively count files across all listed directories. Missing dirs skipped."""
    total = 0
    for d in dir_list:
        try:
            for _, _, files in os.walk(d):
                total += len(files)
        except OSError:
            pass
    return total


def count_processes() -> int:
    return sum(1 for _ in psutil.process_iter())


def count_listen_ports() -> int:
    return sum(
        1 for c in psutil.net_connections()
        if c.status == "LISTEN"
    )


class CpuMovingAverage:
    """Rolling window average of per-core CPU%. Window in seconds."""

    def __init__(self, window_s: float, tick_interval_s: float = 2.0):
        max_samples = max(1, int(window_s / tick_interval_s))
        self._window: collections.deque = collections.deque(maxlen=max_samples)

    def update(self, per_core: List[float]) -> None:
        self._window.append(list(per_core))

    def get(self, core_count: Optional[int] = None) -> List[float]:
        if not self._window:
            n = core_count if core_count is not None else 1
            return [0.0] * n
        # Column-wise mean across all samples in window
        max_cores = max(len(row) for row in self._window)
        n = core_count if core_count is not None else max_cores
        totals = [0.0] * n
        counts = [0] * n
        for row in self._window:
            for i in range(n):
                if i < len(row):
                    totals[i] += row[i]
                    counts[i] += 1
        return [totals[i] / counts[i] if counts[i] > 0 else 0.0 for i in range(n)]


def build_state_vector(config: dict, cpu_ma: CpuMovingAverage) -> np.ndarray:
    """Build the fixed-length state vector V for the current tick."""
    cpu_core_count: int = config["cpu_core_count"]

    proc_count = float(count_processes())
    reg_hash = float(hash_registry_keys(config["monitored_reg_keys"]))
    file_count = float(count_files(config["monitored_dirs"]))
    open_ports = float(count_listen_ports())
    cpu_cores = cpu_ma.get(core_count=cpu_core_count)

    return np.array(
        [proc_count, reg_hash, file_count, open_ports] + cpu_cores,
        dtype=float,
    )
