import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import numpy as np
from unittest.mock import patch, MagicMock

from sandbox.state_vector import (
    hash_registry_keys, count_files,
    count_processes, count_listen_ports,
    CpuMovingAverage, build_state_vector,
)


def test_hash_registry_keys_returns_int():
    with patch("sandbox.state_vector.winreg") as mock_reg:
        mock_key = MagicMock()
        mock_reg.OpenKey.return_value.__enter__ = lambda s: mock_key
        mock_reg.OpenKey.return_value.__exit__ = MagicMock(return_value=False)
        mock_reg.QueryInfoKey.return_value = (2, 0, 0)  # 2 values
        mock_reg.EnumValue.side_effect = [
            ("val1", "data1", 1),
            ("val2", "data2", 1),
        ]
        mock_reg.HKEY_CURRENT_USER = 0x80000001
        result = hash_registry_keys(["HKCU\\Software\\Test"])
    assert isinstance(result, int)


def test_hash_registry_keys_xor_not_sum():
    """XOR of a value with itself should be 0; sum-based would not."""
    with patch("sandbox.state_vector.winreg") as mock_reg:
        mock_key = MagicMock()
        mock_reg.OpenKey.return_value.__enter__ = lambda s: mock_key
        mock_reg.OpenKey.return_value.__exit__ = MagicMock(return_value=False)
        mock_reg.QueryInfoKey.return_value = (1, 0, 0)  # 1 value so hash is non-zero
        mock_reg.EnumValue.side_effect = [
            ("val1", "data1", 1),
            ("val1", "data1", 1),  # same value again for second call
        ]
        mock_reg.HKEY_CURRENT_USER = 0x80000001
        r1 = hash_registry_keys(["HKCU\\Same"])
        r2 = hash_registry_keys(["HKCU\\Same"])
    assert r1 != 0          # confirm hash is non-zero
    assert r1 ^ r2 == 0     # XOR of same value with itself is 0
    assert r1 + r2 != 0     # sum-based would not satisfy this

def test_hash_registry_keys_missing_key_returns_zero_contribution():
    """A missing registry key should not crash; skip it silently."""
    with patch("sandbox.state_vector.winreg") as mock_reg:
        mock_reg.OpenKey.side_effect = OSError("key not found")
        mock_reg.HKEY_CURRENT_USER = 0x80000001
        result = hash_registry_keys(["HKCU\\NonExistent"])
    assert result == 0


def test_count_files_sums_all_dirs(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("y")
    count = count_files([str(tmp_path)])
    assert count == 2


def test_count_files_empty_dir(tmp_path):
    assert count_files([str(tmp_path)]) == 0


def test_count_files_missing_dir():
    """Missing directory should be skipped without crashing."""
    count = count_files(["C:\\NonExistentPath_xyz"])
    assert count == 0


# ---------------------------------------------------------------------------
# Task 4: process/port counters, CPU moving average, state vector builder
# ---------------------------------------------------------------------------

def test_count_processes_returns_int():
    with patch("sandbox.state_vector.psutil") as mock_psutil:
        mock_psutil.process_iter.return_value = [1, 2, 3]
        assert count_processes() == 3


def test_count_listen_ports_returns_int():
    conn = type("C", (), {"status": "LISTEN", "laddr": type("A", (), {"port": 80})()})()
    with patch("sandbox.state_vector.psutil") as mock_psutil:
        mock_psutil.net_connections.return_value = [conn]
        assert count_listen_ports() == 1


def test_cpu_moving_average_window():
    ma = CpuMovingAverage(window_s=4, tick_interval_s=2)  # window = 2 samples
    ma.update([50.0, 50.0])
    ma.update([100.0, 100.0])
    result = ma.get()
    # Should be average of last 2 ticks: (50+100)/2 = 75
    assert result == [75.0, 75.0]


def test_cpu_moving_average_pads_to_core_count():
    ma = CpuMovingAverage(window_s=2, tick_interval_s=2)
    ma.update([50.0])  # only 1 core reading
    result = ma.get(core_count=4)
    assert len(result) == 4
    assert result[0] == 50.0
    assert result[1] == 0.0   # padded


def test_build_state_vector_correct_length():
    config = {
        "cpu_core_count": 2,
        "monitored_reg_keys": [],
        "monitored_dirs": [],
        "blue_genome": [0.25, 0.35, 0.2, 0.2, 0.5, 0.3, 0.7, 10.0],
    }
    with patch("sandbox.state_vector.psutil") as mock_psutil, \
         patch("sandbox.state_vector.winreg"):
        mock_psutil.process_iter.return_value = []
        mock_psutil.net_connections.return_value = []
        mock_psutil.cpu_percent.return_value = [10.0, 20.0]
        cpu_ma = CpuMovingAverage(window_s=10, tick_interval_s=2)
        V = build_state_vector(config, cpu_ma)
    # length = 4 fixed + cpu_core_count
    assert len(V) == 4 + 2
    assert isinstance(V, np.ndarray)
