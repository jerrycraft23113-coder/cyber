import os
import binascii
from typing import List

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
