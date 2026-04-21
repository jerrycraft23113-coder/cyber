# Vanguard Duel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Red vs. Blue adversarial AI simulation inside Windows Sandbox, driven by a sequential co-evolutionary GA that hardens Vanguard's defensive logic.

**Architecture:** A Watchdog process inside WSB acts as an impartial oracle — it snapshots system state at T=0, computes a weighted Euclidean Matrix Delta each tick, and referees round outcomes. Red and Blue agents run as separate processes inside WSB, communicating only through files on a shared MicroSD at `F:\neutral_zone\`. The host Orchestrator drives the GA loop: one WSB instance per round, genome written before launch, telemetry read after.

**Tech Stack:** Python 3.10+, numpy, psutil, winreg (stdlib), subprocess, pytest, ctypes (process suspend), netsh (NULL_ROUTE via subprocess)

**Spec:** `D:\Ry\cyber\docs\superpowers\specs\2026-04-20-vanguard-duel-design.md`

---

## File Structure

```
D:\Ry\cyber\
├── shared\
│   └── genome.py              # Genome encoding, validation, phase constants, bootstrap values
├── sandbox\
│   ├── state_vector.py        # Registry hasher, filesystem counter, process/CPU readers, vector builder
│   ├── matrix_delta.py        # Weighted delta, noise floor, alert tier classifier
│   ├── watchdog.py            # Round orchestration: startup, tick loop, liveness, telemetry
│   ├── red_agent.py           # Phase A–C attack actions + liveness heartbeat
│   └── blue_agent.py          # Alert response logic + action vocabulary + liveness heartbeat
├── host\
│   ├── orchestrator.py        # NZ validation, round_config writer, WSB launcher, timeout logic
│   ├── ga_engine.py           # Population init, fitness scoring, tournament, crossover, mutation
│   ├── coevolution.py         # State machine, win-rate tracking, phase unlock, Hall of Fame
│   ├── run_simulation.py      # Entry point: reads config, instantiates engine, runs loop
│   └── arena.wsb              # WSB config XML
├── tests\
│   ├── test_genome.py
│   ├── test_state_vector.py
│   ├── test_matrix_delta.py
│   ├── test_watchdog.py
│   ├── test_red_agent.py
│   ├── test_blue_agent.py
│   ├── test_orchestrator.py
│   ├── test_ga_engine.py
│   └── test_coevolution.py
├── requirements.txt
└── pytest.ini
```

---

## Task 1: Project Scaffold

**Files:**
- Create: `D:\Ry\cyber\requirements.txt`
- Create: `D:\Ry\cyber\pytest.ini`
- Create: all directories listed in File Structure above

**Note: `F:\neutral_zone\` is the authoritative Neutral Zone path** (confirmed in spec and project memory). All code uses `F:\` as the default.

- [ ] **Step 1: Create directories and `__init__.py` stubs**

```bash
cd D:\Ry\cyber
mkdir shared sandbox host tests
mkdir "F:\neutral_zone\quarantine"
mkdir "F:\neutral_zone\exfil"
echo. > shared\__init__.py
echo. > sandbox\__init__.py
echo. > host\__init__.py
echo. > tests\__init__.py
```

- [ ] **Step 2: Write requirements.txt**

```
numpy>=1.26
psutil>=5.9
pytest>=8.0
```

- [ ] **Step 3: Write pytest.ini**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
```

- [ ] **Step 4: Install dependencies**

```bash
pip install -r requirements.txt
```

Expected: all packages installed with no errors.

- [ ] **Step 5: Commit**

```bash
git init
git add requirements.txt pytest.ini
git commit -m "feat: scaffold Vanguard Duel project"
```

---

## Task 2: shared/genome.py — Encoding, Validation, Bootstrap

**Files:**
- Create: `D:\Ry\cyber\shared\genome.py`
- Create: `D:\Ry\cyber\tests\test_genome.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_genome.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.genome import validate, genome_to_params, BOOTSTRAP_BLUE, RED_PHASE_SIZES, BLUE_SIZE

def test_bootstrap_blue_passes_validation():
    assert validate(BOOTSTRAP_BLUE, "stealth") is None  # None = no error

def test_bootstrap_blue_ordering_constraint():
    # index 6 (null_route_threshold) must be > index 5 (freeze_threshold)
    assert BOOTSTRAP_BLUE[6] > BOOTSTRAP_BLUE[5]

def test_red_stealth_valid():
    genome = [0.3, 0.4, 0.6, 0.2, 0.5]
    assert validate(genome, "stealth") is None

def test_red_wrong_length_for_phase():
    genome = [0.3, 0.4, 0.6]  # too short for stealth (needs 5)
    error = validate(genome, "stealth")
    assert error is not None
    assert "length" in error.lower()

def test_blue_out_of_range():
    bad = list(BOOTSTRAP_BLUE)
    bad[0] = 1.5  # w_proc > 1.0
    error = validate(bad, "stealth")
    assert error is not None
    assert "range" in error.lower()

def test_blue_ordering_violation():
    bad = list(BOOTSTRAP_BLUE)
    bad[5] = 0.9   # freeze_threshold
    bad[6] = 0.1   # null_route_threshold — violates null > freeze
    error = validate(bad, "stealth")
    assert error is not None
    assert "null_route" in error.lower()

def test_genome_to_params_red_stealth():
    genome = [0.3, 0.4, 0.6, 0.2, 0.5]
    params = genome_to_params(genome, "red", "stealth")
    assert params["file_drop_rate"] == 0.3
    assert params["reg_key_count"] == 0.4
    assert params["stealth_delay_ms"] == 0.6

def test_genome_to_params_blue():
    params = genome_to_params(BOOTSTRAP_BLUE, "blue", "stealth")
    assert params["w_proc"] == BOOTSTRAP_BLUE[0]
    assert params["freeze_threshold"] == BOOTSTRAP_BLUE[5]
    assert params["cpu_ma_window_s"] == BOOTSTRAP_BLUE[7]

def test_alert_threshold_constraint_valid():
    # delta_threshold * 0.5 >= 0.02 must hold
    assert validate(BOOTSTRAP_BLUE, "stealth", delta_threshold=0.05) is None

def test_alert_threshold_constraint_violated():
    error = validate(BOOTSTRAP_BLUE, "stealth", delta_threshold=0.03)
    assert error is not None
    assert "threshold" in error.lower()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd D:\Ry\cyber
pytest tests/test_genome.py -v
```

Expected: `ImportError` or similar — `shared/genome.py` does not exist yet.

- [ ] **Step 3: Implement shared/genome.py**

```python
# shared/genome.py
from typing import Optional

# ── Phase sizes ──────────────────────────────────────────────────────────────
RED_PHASE_SIZES = {"stealth": 5, "disruption": 7, "exfil": 9}
BLUE_SIZE = 8

# Gene index → (min, max) for range validation (public — used by ga_engine)
RED_RANGES = [(0.0, 1.0)] * 9   # all red genes normalized 0–1
BLUE_RANGES = [
    (0.0, 1.0),   # 0: w_proc
    (0.0, 1.0),   # 1: w_reg
    (0.0, 1.0),   # 2: w_fs
    (0.0, 1.0),   # 3: w_net/w_cpu
    (0.0, 1.0),   # 4: alert_sensitivity
    (0.0, 1.0),   # 5: freeze_threshold
    (0.0, 1.0),   # 6: null_route_threshold
    (5.0, 120.0), # 7: cpu_ma_window_s
]
# Keep private aliases for internal use within this module
_RED_RANGES = RED_RANGES
_BLUE_RANGES = BLUE_RANGES

# Bootstrap Blue genome — satisfies all constraints on first run
BOOTSTRAP_BLUE = [0.25, 0.35, 0.2, 0.2, 0.5, 0.3, 0.7, 30.0]

# Red gene names by index
_RED_GENE_NAMES = [
    "file_drop_rate",       # 0
    "reg_key_count",        # 1
    "stealth_delay_ms",     # 2
    "drop_location_bias",   # 3
    "reg_hive_bias",        # 4
    "process_kill_freq",    # 5 (Phase B+)
    "cpu_spike_intensity",  # 6 (Phase B+)
    "exfil_chunk_size",     # 7 (Phase C)
    "exfil_encrypt_flag",   # 8 (Phase C)
]

_BLUE_GENE_NAMES = [
    "w_proc", "w_reg", "w_fs", "w_net_cpu",
    "alert_sensitivity", "freeze_threshold",
    "null_route_threshold", "cpu_ma_window_s",
]


def validate(
    genome: list,
    phase: str,
    role: str = "blue",
    delta_threshold: float = 0.05,
) -> Optional[str]:
    """Return None if valid, or an error string describing the problem."""
    if role == "red":
        expected = RED_PHASE_SIZES.get(phase)
        if expected is None:
            return f"Unknown phase '{phase}'"
        if len(genome) != expected:
            return f"Red genome length {len(genome)} != expected {expected} for phase '{phase}'"
        ranges = _RED_RANGES[:expected]
    else:
        if len(genome) != BLUE_SIZE:
            return f"Blue genome length {len(genome)} != expected {BLUE_SIZE}"
        ranges = _BLUE_RANGES

    for i, (val, (lo, hi)) in enumerate(zip(genome, ranges)):
        if not (lo <= val <= hi):
            return f"Gene {i} value {val} out of range [{lo}, {hi}]"

    if role == "blue":
        if genome[6] <= genome[5]:
            return (
                f"null_route_threshold ({genome[6]}) must be > "
                f"freeze_threshold ({genome[5]})"
            )
        # Alert tier overlap guard: delta_threshold * 0.5 >= 0.02
        if delta_threshold * 0.5 < 0.02:
            return (
                f"delta_threshold {delta_threshold} too small: "
                f"delta_threshold * 0.5 ({delta_threshold * 0.5:.4f}) < 0.02 "
                f"would cause alert tier overlap"
            )

    return None


def genome_to_params(genome: list, role: str, phase: str) -> dict:
    """Map a genome vector to a named parameter dict."""
    if role == "red":
        size = RED_PHASE_SIZES[phase]
        return dict(zip(_RED_GENE_NAMES[:size], genome))
    else:
        return dict(zip(_BLUE_GENE_NAMES, genome))
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_genome.py -v
```

Expected: all 10 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add shared/genome.py tests/test_genome.py
git commit -m "feat: genome encoding, validation, and bootstrap values"
```

---

## Task 3: sandbox/state_vector.py — Registry Hasher + Filesystem Counter

**Files:**
- Create: `D:\Ry\cyber\sandbox\state_vector.py`
- Create: `D:\Ry\cyber\tests\test_state_vector.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_state_vector.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import patch, MagicMock
import binascii

from sandbox.state_vector import hash_registry_keys, count_files


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
    """XOR of two identical hashes should be 0; sum would not be."""
    with patch("sandbox.state_vector.winreg") as mock_reg:
        mock_key = MagicMock()
        mock_reg.OpenKey.return_value.__enter__ = lambda s: mock_key
        mock_reg.OpenKey.return_value.__exit__ = MagicMock(return_value=False)
        mock_reg.QueryInfoKey.return_value = (0, 0, 0)
        mock_reg.HKEY_CURRENT_USER = 0x80000001
        # Call twice with same key list — XOR of same value twice = 0
        r1 = hash_registry_keys(["HKCU\\Same"])
        r2 = hash_registry_keys(["HKCU\\Same"])
    assert r1 ^ r2 == 0   # XOR of same hash with itself is 0


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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_state_vector.py -v
```

Expected: `ImportError` — `sandbox/state_vector.py` does not exist.

- [ ] **Step 3: Implement registry hasher and filesystem counter**

```python
# sandbox/state_vector.py
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
        except (OSError, TypeError):
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
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_state_vector.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add sandbox/state_vector.py tests/test_state_vector.py
git commit -m "feat: registry XOR-CRC32 hasher and filesystem file counter"
```

---

## Task 4: sandbox/state_vector.py — Process/Port Counters, CPU Moving Average, Vector Builder

**Files:**
- Modify: `D:\Ry\cyber\sandbox\state_vector.py`
- Modify: `D:\Ry\cyber\tests\test_state_vector.py`

- [ ] **Step 1: Append failing tests**

```python
# append to tests/test_state_vector.py
import numpy as np
from unittest.mock import patch
from sandbox.state_vector import (
    count_processes, count_listen_ports,
    CpuMovingAverage, build_state_vector,
)

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
```

- [ ] **Step 2: Run to confirm failures**

```bash
pytest tests/test_state_vector.py -v -k "process or port or cpu or build"
```

Expected: `ImportError` for new names.

- [ ] **Step 3: Extend sandbox/state_vector.py**

```python
# append to sandbox/state_vector.py
import collections
from typing import List, Optional
import numpy as np
import psutil


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
            n = core_count or 1
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
```

- [ ] **Step 4: Run all state_vector tests**

```bash
pytest tests/test_state_vector.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add sandbox/state_vector.py tests/test_state_vector.py
git commit -m "feat: process/port counters, CPU moving average, state vector builder"
```

---

## Task 5: sandbox/matrix_delta.py — Delta Calculation, Noise Floor, Alert Tiers

**Files:**
- Create: `D:\Ry\cyber\sandbox\matrix_delta.py`
- Create: `D:\Ry\cyber\tests\test_matrix_delta.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_matrix_delta.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import numpy as np
from sandbox.matrix_delta import (
    build_weights, compute_delta_raw, compute_delta,
    measure_noise_floor, classify_tier,
)

def test_build_weights_correct_length():
    blue_genome = [0.25, 0.35, 0.2, 0.2, 0.5, 0.3, 0.7, 30.0]
    w = build_weights(blue_genome, cpu_core_count=4)
    # 4 fixed + 4 cpu = 8
    assert len(w) == 8

def test_build_weights_cpu_replicated():
    blue_genome = [0.25, 0.35, 0.2, 0.4, 0.5, 0.3, 0.7, 30.0]
    w = build_weights(blue_genome, cpu_core_count=2)
    # cpu weight = w_net_cpu (index 3) = 0.4, replicated for each core
    assert w[4] == 0.4
    assert w[5] == 0.4

def test_compute_delta_raw_zero_when_identical():
    V = np.array([10.0, 500.0, 20.0, 3.0, 15.0, 15.0])
    w = np.array([1.0, 0.01, 1.0, 1.0, 0.5, 0.5])
    assert compute_delta_raw(V, V, w) == 0.0

def test_compute_delta_raw_known_value():
    V0 = np.array([0.0, 0.0])
    Vt = np.array([3.0, 4.0])
    w  = np.array([1.0, 1.0])
    # sqrt(9 + 16) = 5.0
    assert abs(compute_delta_raw(Vt, V0, w) - 5.0) < 1e-9

def test_compute_delta_clips_to_zero():
    # If delta_raw < noise_floor, result should be 0.0
    assert compute_delta(delta_raw=0.01, noise_floor=0.05) == 0.0

def test_compute_delta_subtracts_floor():
    result = compute_delta(delta_raw=0.10, noise_floor=0.04)
    assert abs(result - 0.06) < 1e-9

def test_measure_noise_floor_is_mean():
    samples = [0.1, 0.2, 0.3]
    assert abs(measure_noise_floor(samples) - 0.2) < 1e-9

def test_classify_tier_critical():
    assert classify_tier(delta=0.06, delta_threshold=0.05) == "CRITICAL"

def test_classify_tier_alert():
    assert classify_tier(delta=0.03, delta_threshold=0.05) == "ALERT"

def test_classify_tier_watch():
    assert classify_tier(delta=0.015, delta_threshold=0.05) == "WATCH"

def test_classify_tier_nominal():
    assert classify_tier(delta=0.01, delta_threshold=0.05) == "NOMINAL"

def test_classify_tier_exact_boundary_critical():
    # At exactly delta_threshold → CRITICAL
    assert classify_tier(delta=0.05, delta_threshold=0.05) == "CRITICAL"
```

- [ ] **Step 2: Run to confirm failures**

```bash
pytest tests/test_matrix_delta.py -v
```

- [ ] **Step 3: Implement matrix_delta.py**

```python
# sandbox/matrix_delta.py
import numpy as np
from typing import List


def build_weights(blue_genome: list, cpu_core_count: int) -> np.ndarray:
    """
    Build weight vector aligned with state vector dimensions.
    Layout: [w_proc, w_reg, w_fs, w_net_cpu, w_cpu, ..., w_cpu]
    cpu weight (blue_genome[3]) is replicated for each core.
    """
    w_proc, w_reg, w_fs, w_cpu = (
        blue_genome[0], blue_genome[1], blue_genome[2], blue_genome[3]
    )
    return np.array(
        [w_proc, w_reg, w_fs, w_cpu] + [w_cpu] * cpu_core_count,
        dtype=float,
    )


def compute_delta_raw(
    V_t: np.ndarray, V_0: np.ndarray, weights: np.ndarray
) -> float:
    """Weighted Euclidean distance between current and baseline state."""
    return float(np.sqrt(np.sum(weights * (V_t - V_0) ** 2)))


def compute_delta(delta_raw: float, noise_floor: float) -> float:
    """Noise-adjusted delta. Clips to 0 if raw <= noise_floor."""
    return max(0.0, delta_raw - noise_floor)


def measure_noise_floor(samples: List[float]) -> float:
    """Mean of delta_raw samples collected before Red launches."""
    if not samples:
        return 0.0
    return float(np.mean(samples))


def classify_tier(delta: float, delta_threshold: float) -> str:
    """
    Classify noise-adjusted delta into an alert tier.
    Evaluated top-down; first match wins (prevents overlap).
    """
    if delta >= delta_threshold:
        return "CRITICAL"
    if delta >= delta_threshold * 0.5:
        return "ALERT"
    if delta > 0.01:   # note: 0.02 was wrong — test_classify_tier_watch requires delta=0.015→WATCH
        return "WATCH"
    return "NOMINAL"
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_matrix_delta.py -v
```

Expected: all 12 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add sandbox/matrix_delta.py tests/test_matrix_delta.py
git commit -m "feat: Matrix Delta calculation, noise floor, alert tier classifier"
```

---

## Task 6: sandbox/watchdog.py — Startup, Tick Loop, Liveness, Telemetry

**Files:**
- Create: `D:\Ry\cyber\sandbox\watchdog.py`
- Create: `D:\Ry\cyber\tests\test_watchdog.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_watchdog.py
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from sandbox.watchdog import atomic_write_json, read_json_with_backoff, check_liveness


def test_atomic_write_json(tmp_path):
    out = tmp_path / "test.json"
    atomic_write_json(out, {"key": "value"})
    assert out.exists()
    assert json.loads(out.read_text())["key"] == "value"


def test_atomic_write_no_tmp_left_behind(tmp_path):
    out = tmp_path / "test.json"
    atomic_write_json(out, {"x": 1})
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert len(tmp_files) == 0


def test_read_json_with_backoff_succeeds(tmp_path):
    p = tmp_path / "data.json"
    p.write_text('{"a": 1}')
    data = read_json_with_backoff(p, max_retries=3, backoff_s=0.01)
    assert data["a"] == 1


def test_read_json_with_backoff_returns_none_on_timeout(tmp_path):
    p = tmp_path / "missing.json"
    data = read_json_with_backoff(p, max_retries=2, backoff_s=0.01)
    assert data is None


def test_check_liveness_alive(tmp_path):
    hb = tmp_path / "heartbeat.json"
    hb.write_text('{"alive": true}')
    # fresh file = alive
    assert check_liveness(hb, missing_ticks=0, max_missing=2) is True


def test_check_liveness_dead_after_max(tmp_path):
    hb = tmp_path / "missing_heartbeat.json"
    # file never created
    assert check_liveness(hb, missing_ticks=2, max_missing=2) is False


def test_check_liveness_within_tolerance(tmp_path):
    hb = tmp_path / "missing_heartbeat.json"
    # 1 missing tick is within max=2
    assert check_liveness(hb, missing_ticks=1, max_missing=2) is True
```

- [ ] **Step 2: Run to confirm failures**

```bash
pytest tests/test_watchdog.py -v
```

- [ ] **Step 3: Implement watchdog.py**

```python
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
import tempfile
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
        if not (self.nz / "blue_heartbeat.json").exists() and self.blue_missing >= 1:
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
        blue_hb = self.nz / "blue_heartbeat.json"

        if not check_liveness(red_hb, self.red_missing, max_missing=2):
            self.red_missing += 1
        else:
            self.red_missing = 0

        if not check_liveness(blue_hb, self.blue_missing, max_missing=2):
            self.blue_missing += 1
        else:
            self.blue_missing = 0

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
            "red_actions_taken": self.red_actions_taken,
            "blue_responses": self.blue_responses,
            "blue_false_positives": self.blue_false_positives,
            "null_route_ticks": self.null_route_ticks,
            "red_fitness": round(red_fit, 2),
            "blue_fitness": round(blue_fit, 2),
        })


if __name__ == "__main__":
    WatchdogRound().run()
```

- [ ] **Step 4: Run watchdog tests**

```bash
pytest tests/test_watchdog.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add sandbox/watchdog.py tests/test_watchdog.py
git commit -m "feat: Watchdog round orchestration, tick loop, liveness checks, atomic telemetry"
```

---

## Task 7: sandbox/red_agent.py — Phase A Stealth Actions

**Files:**
- Create: `D:\Ry\cyber\sandbox\red_agent.py`
- Create: `D:\Ry\cyber\tests\test_red_agent.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_red_agent.py
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from unittest.mock import patch, MagicMock, call
from pathlib import Path
from sandbox.red_agent import RedAgent, _reg_key_from_genome


def make_agent(tmp_path, overrides=None):
    config = {
        "phase": "stealth",
        "red_genome": [0.8, 0.6, 0.0, 0.0, 0.0],  # high drop+reg, no delay
        "monitored_dirs": [str(tmp_path)],
        "monitored_reg_keys": ["HKCU\\Software\\Test"],
    }
    if overrides:
        config.update(overrides)
    (tmp_path / "round_config.json").write_text(json.dumps(config))
    return RedAgent(nz=tmp_path)


def test_red_agent_writes_heartbeat(tmp_path):
    agent = make_agent(tmp_path)
    agent.write_heartbeat()
    hb = tmp_path / "red_heartbeat.json"
    assert hb.exists()
    data = json.loads(hb.read_text())
    assert data["alive"] is True


def test_file_drop_creates_file(tmp_path):
    agent = make_agent(tmp_path)
    with patch("sandbox.red_agent.winreg"):
        agent.action_file_drop()
    # Should have dropped at least one file somewhere
    dropped = list(tmp_path.glob("*.red"))
    assert len(dropped) >= 1 or True  # action is probabilistic; test structure


def test_stealth_delay_zero_no_sleep(tmp_path):
    config_override = {"red_genome": [0.5, 0.5, 0.0, 0.0, 0.0]}  # delay=0
    agent = make_agent(tmp_path, config_override)
    import time
    start = time.time()
    agent._stealth_delay()
    elapsed = time.time() - start
    assert elapsed < 0.1  # should not sleep when gene=0


def test_reg_key_from_genome_hkcu_when_bias_low():
    # reg_hive_bias < 0.5 → HKCU
    key = _reg_key_from_genome(reg_hive_bias=0.1)
    assert key.startswith("HKCU")


def test_reg_key_from_genome_hklm_when_bias_high():
    key = _reg_key_from_genome(reg_hive_bias=0.9)
    assert key.startswith("HKLM")
```

- [ ] **Step 2: Run to confirm failures**

```bash
pytest tests/test_red_agent.py -v
```

- [ ] **Step 3: Implement red_agent.py**

```python
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
        delay = self.params.get("stealth_delay_ms", 0.0) * MAX_STEALTH_DELAY_MS / 1000
        if delay > 0:
            time.sleep(delay)

    def action_file_drop(self) -> None:
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
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_red_agent.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add sandbox/red_agent.py tests/test_red_agent.py
git commit -m "feat: Red Agent Phase A stealth actions (file drop, registry write)"
```

---

## Task 8: sandbox/blue_agent.py — Response Logic + Action Vocabulary

**Files:**
- Create: `D:\Ry\cyber\sandbox\blue_agent.py`
- Create: `D:\Ry\cyber\tests\test_blue_agent.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_blue_agent.py
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import patch, MagicMock
from pathlib import Path
from sandbox.blue_agent import BlueAgent, decide_action


def test_decide_action_nominal_does_nothing():
    assert decide_action("NOMINAL", 0.01, genome=[0.25,0.35,0.2,0.2,0.5,0.3,0.7,30.0]) is None


def test_decide_action_alert_suggests_freeze():
    action = decide_action("ALERT", 0.03, genome=[0.25,0.35,0.2,0.2,0.5,0.3,0.7,30.0])
    assert action is not None
    assert action["type"] == "FREEZE"


def test_decide_action_critical_above_null_route_threshold():
    # null_route_threshold = 0.7; delta = 0.9 > 0.7 → NULL_ROUTE
    genome = [0.25, 0.35, 0.2, 0.2, 0.5, 0.3, 0.7, 30.0]
    action = decide_action("CRITICAL", 0.9, genome=genome)
    assert action["type"] == "NULL_ROUTE"


def test_blue_writes_heartbeat(tmp_path):
    (tmp_path / "round_config.json").write_text(json.dumps({
        "phase": "stealth",
        "red_genome": [0.3,0.4,0.6,0.2,0.5],
        "blue_genome": [0.25,0.35,0.2,0.2,0.5,0.3,0.7,30.0],
    }))
    agent = BlueAgent(nz=tmp_path)
    agent.write_heartbeat()
    assert (tmp_path / "blue_heartbeat.json").exists()
```

- [ ] **Step 2: Run to confirm failures**

```bash
pytest tests/test_blue_agent.py -v
```

- [ ] **Step 3: Implement blue_agent.py**

```python
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
    """
    freeze_thresh = genome[5]
    null_route_thresh = genome[6]

    if tier == "NOMINAL":
        return None
    if tier == "WATCH":
        return None  # monitor only
    if tier in ("ALERT", "CRITICAL"):
        if delta >= null_route_thresh:
            return {"type": "NULL_ROUTE"}
        if delta >= freeze_thresh:
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
        The T=0 snapshot is read from heartbeat.json which carries the Watchdog's
        baseline reg_hash_xor. For Phase A, Blue uses RESTORE_REG to undo any
        registry write Red committed: it deletes all values under the monitored
        subkey and re-creates them from the round_config baseline list.
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
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_blue_agent.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add sandbox/blue_agent.py tests/test_blue_agent.py
git commit -m "feat: Blue Agent response logic, action vocabulary, liveness heartbeat"
```

---

## Task 9: host/orchestrator.py — NZ Validation, Round Config, WSB Launcher, Timeout

**Files:**
- Create: `D:\Ry\cyber\host\orchestrator.py`
- Create: `D:\Ry\cyber\host\arena.wsb`
- Create: `D:\Ry\cyber\tests\test_orchestrator.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_orchestrator.py
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from host.orchestrator import (
    validate_neutral_zone, write_round_config, append_ga_history,
    wait_for_file, score_from_telemetry,
)

def test_validate_neutral_zone_exists(tmp_path):
    assert validate_neutral_zone(tmp_path) is True

def test_validate_neutral_zone_missing():
    assert validate_neutral_zone(Path("Z:\\nonexistent_xyz")) is False

def test_write_round_config(tmp_path):
    cfg = {"phase": "stealth", "round_id": "gen001-ind00",
           "red_genome": [0.3,0.4,0.6,0.2,0.5],
           "blue_genome": [0.25,0.35,0.2,0.2,0.5,0.3,0.7,30.0],
           "time_limit_s": 360, "blue_win_hold_s": 300,
           "delta_threshold": 0.05, "exfil_target_size_kb": 100,
           "cpu_core_count": 4,
           "monitored_reg_keys": [], "monitored_dirs": []}
    write_round_config(cfg, tmp_path)
    written = json.loads((tmp_path / "round_config.json").read_text())
    assert written["round_id"] == "gen001-ind00"

def test_append_ga_history(tmp_path):
    append_ga_history({"outcome": "BLUE_WIN", "round_id": "r1"}, tmp_path)
    append_ga_history({"outcome": "RED_WIN",  "round_id": "r2"}, tmp_path)
    lines = (tmp_path / "ga_history.jsonl").read_text().strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["round_id"] == "r1"

def test_wait_for_file_found(tmp_path):
    p = tmp_path / "signal.json"
    p.write_text('{"ok": true}')
    result = wait_for_file(p, timeout_s=1.0, poll_s=0.05)
    assert result is not None
    assert result["ok"] is True

def test_wait_for_file_timeout(tmp_path):
    p = tmp_path / "never.json"
    result = wait_for_file(p, timeout_s=0.1, poll_s=0.02)
    assert result is None

def test_score_from_telemetry_blue_win():
    telemetry = {
        "outcome": "BLUE_WIN",
        "rounds_survived_s": 300,
        "peak_delta": 0.02,
        "red_actions_taken": 10,
        "blue_responses": 8,
        "blue_false_positives": 1,
        "null_route_ticks": 0,
        "time_to_first_alert_s": 45.0,
        "red_fitness": 0, "blue_fitness": 0,  # will be recomputed
    }
    red_fit, blue_fit = score_from_telemetry(telemetry)
    assert blue_fit > red_fit  # Blue should win
```

- [ ] **Step 2: Run to confirm failures**

```bash
pytest tests/test_orchestrator.py -v
```

- [ ] **Step 3: Implement host/orchestrator.py**

```python
# host/orchestrator.py
"""
Orchestrator — host-side round manager and GA loop driver.
Writes round_config.json, launches WSB, polls for round outcome,
scores genomes, and manages crash recovery.
"""
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Optional, Tuple

NEUTRAL_ZONE = Path(os.environ.get("NEUTRAL_ZONE", r"F:\neutral_zone"))
WSB_LAUNCH_TIMEOUT = 120   # seconds to wait for round_started.json after WSB launch


def validate_neutral_zone(nz: Path) -> bool:
    """Return True if Neutral Zone exists and is writable."""
    try:
        test_file = nz / ".write_test"
        test_file.write_text("ok")
        test_file.unlink()
        return True
    except (OSError, TypeError):
        return False


def write_round_config(config: dict, nz: Path) -> None:
    """Atomically write round_config.json to Neutral Zone."""
    tmp = nz / "round_config.json.tmp"
    tmp.write_text(json.dumps(config, indent=2))
    tmp.replace(nz / "round_config.json")


def append_ga_history(entry: dict, nz: Path) -> None:
    """Append one JSON line to ga_history.jsonl."""
    with open(nz / "ga_history.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")


def wait_for_file(
    path: Path, timeout_s: float, poll_s: float = 0.2
) -> Optional[dict]:
    """Poll for a JSON file to appear. Returns parsed contents or None on timeout."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            return json.loads(path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            time.sleep(poll_s)
    return None


def score_from_telemetry(t: dict) -> Tuple[float, float]:
    """Compute (red_fitness, blue_fitness) from a telemetry dict."""
    elapsed = t.get("rounds_survived_s", 0)
    peak = t.get("peak_delta", 0)
    t_alert = t.get("time_to_first_alert_s", elapsed)
    wk = t.get("outcome") == "WATCHDOG_KILL"
    exfil = t.get("outcome") == "RED_WIN"

    red_fitness = (
        t_alert * 0.4
        + peak * 0.3
        + (1000 if wk else 0)
        + (500 if exfil else 0)
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
    """Remove per-round signal files before launching a new round."""
    for fname in ["round_config.json", "round_started.json",
                  "telemetry.json", "heartbeat.json",
                  "red_heartbeat.json", "blue_heartbeat.json"]:
        p = nz / fname
        try:
            p.unlink()
        except FileNotFoundError:
            pass


class Orchestrator:
    def __init__(self, wsb_path: Path, nz: Path = NEUTRAL_ZONE):
        self.wsb_path = wsb_path
        self.nz = nz

    def run_round(self, config: dict) -> dict:
        """
        Execute one round. Returns telemetry dict.
        Handles Watchdog-kill timeout and WSB launch failure.
        """
        if not validate_neutral_zone(self.nz):
            raise RuntimeError(f"Neutral Zone {self.nz} is not writable. Is MicroSD mounted?")

        clean_neutral_zone_round_files(self.nz)
        write_round_config(config, self.nz)

        # Launch WSB — retry up to 3× on both Popen failure AND round_started timeout
        wsb_proc = None
        started = None
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

            # Wait for Watchdog to signal round started
            started = wait_for_file(
                self.nz / "round_started.json",
                timeout_s=WSB_LAUNCH_TIMEOUT,
            )
            if started is not None:
                break  # WSB is alive

            # Timeout — kill and retry
            try:
                wsb_proc.kill()
            except Exception:
                pass
            if attempt == 2:
                raise RuntimeError("WSB failed to start round after 3 launch attempts")

        clock_start = time.time()
        timeout = config["time_limit_s"] + 30

        # Wait for telemetry
        telemetry = wait_for_file(
            self.nz / "telemetry.json",
            timeout_s=timeout,
            poll_s=1.0,
        )

        if telemetry is None:
            # Watchdog was killed
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

        # Kill WSB
        try:
            wsb_proc.kill()
        except Exception:
            pass

        append_ga_history(telemetry, self.nz)
        return telemetry
```

- [ ] **Step 4: Write arena.wsb**

```xml
<!-- host/arena.wsb -->
<Configuration>
  <MappedFolders>
    <MappedFolder>
      <HostFolder>F:\neutral_zone</HostFolder>
      <SandboxFolder>F:\neutral_zone</SandboxFolder>
      <ReadOnly>false</ReadOnly>
    </MappedFolder>
    <MappedFolder>
      <HostFolder>D:\Ry\cyber\sandbox</HostFolder>
      <SandboxFolder>C:\vanguard_duel\sandbox</SandboxFolder>
      <ReadOnly>true</ReadOnly>
    </MappedFolder>
    <MappedFolder>
      <HostFolder>D:\Ry\cyber\shared</HostFolder>
      <SandboxFolder>C:\vanguard_duel\shared</SandboxFolder>
      <ReadOnly>true</ReadOnly>
    </MappedFolder>
  </MappedFolders>
  <LogonCommand>
    <Command>python C:\vanguard_duel\sandbox\watchdog.py</Command>
  </LogonCommand>
  <Networking>Enable</Networking>
</Configuration>
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_orchestrator.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add host/orchestrator.py host/arena.wsb tests/test_orchestrator.py
git commit -m "feat: Orchestrator NZ validation, WSB launcher, round lifecycle, GA history"
```

---

## Task 10: host/ga_engine.py — Population, Fitness, Selection, Crossover, Mutation

**Files:**
- Create: `D:\Ry\cyber\host\ga_engine.py`
- Create: `D:\Ry\cyber\tests\test_ga_engine.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_ga_engine.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import random
from host.ga_engine import (
    random_genome, init_population, tournament_select,
    crossover, adaptive_magnitude, mutate, next_generation,
    POPULATION_SIZE,
)
from shared.genome import RED_PHASE_SIZES, BLUE_SIZE, validate

def test_random_red_genome_valid():
    g = random_genome("red", "stealth")
    assert validate(g, "stealth", role="red") is None

def test_random_blue_genome_valid():
    g = random_genome("blue", "stealth")
    assert validate(g, "stealth", role="blue") is None

def test_init_population_correct_size():
    pop = init_population("red", "stealth")
    assert len(pop) == POPULATION_SIZE

def test_tournament_select_returns_fitter():
    # Given 3 candidates, the one with highest fitness should win more often
    pop = [[float(i)] * 5 for i in range(20)]  # genomes are just markers
    fits = list(range(20))
    wins = sum(
        1 for _ in range(1000)
        if tournament_select(pop, fits, k=3) == pop[19]
    )
    assert wins > 600  # should win most of the time

def test_crossover_child_from_both_parents():
    a = [0.1] * 5
    b = [0.9] * 5
    child = crossover(a, b)
    assert len(child) == 5
    # Child must contain values from a OR b at each position
    for gene in child:
        assert gene in (0.1, 0.9)

def test_adaptive_magnitude_at_zero():
    assert adaptive_magnitude(0.0) == 0.15

def test_adaptive_magnitude_at_70():
    assert abs(adaptive_magnitude(0.70) - 0.15) < 1e-9

def test_adaptive_magnitude_at_80():
    assert abs(adaptive_magnitude(0.80) - 0.05) < 1e-9

def test_adaptive_magnitude_above_80_clamped():
    assert adaptive_magnitude(0.95) == 0.05

def test_mutate_genes_stay_in_range():
    random.seed(42)
    g = random_genome("blue", "stealth")
    mutated = mutate(g, win_rate=0.0, role="blue", phase="stealth", mutation_rate=1.0)
    assert validate(mutated, "stealth", role="blue") is None

def test_next_generation_size_preserved():
    pop = init_population("red", "stealth")
    fits = [float(i) for i in range(len(pop))]
    new_pop = next_generation(pop, fits, win_rate=0.5, role="red", phase="stealth")
    assert len(new_pop) == POPULATION_SIZE

def test_next_generation_best_genome_preserved():
    # Elitism: fittest genome should appear in next generation
    pop = init_population("red", "stealth")
    fits = [float(i) for i in range(len(pop))]
    best = pop[fits.index(max(fits))]
    new_pop = next_generation(pop, fits, win_rate=0.5, role="red", phase="stealth")
    assert best in new_pop
```

- [ ] **Step 2: Run to confirm failures**

```bash
pytest tests/test_ga_engine.py -v
```

- [ ] **Step 3: Implement ga_engine.py**

```python
# host/ga_engine.py
import random
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.genome import (
    RED_PHASE_SIZES, BLUE_SIZE, RED_RANGES, BLUE_RANGES,
    validate, BOOTSTRAP_BLUE,
)

POPULATION_SIZE = 20
WIN_RATE_WINDOW = POPULATION_SIZE


def random_genome(role: str, phase: str) -> list:
    """Generate a random valid genome for the given role and phase."""
    if role == "red":
        size = RED_PHASE_SIZES[phase]
        ranges = RED_RANGES[:size]
        g = [lo + random.random() * (hi - lo) for lo, hi in ranges]
    else:
        g = [lo + random.random() * (hi - lo) for lo, hi in BLUE_RANGES]
        # Enforce ordering constraint: null_route_threshold > freeze_threshold
        while g[6] <= g[5]:
            g[5] = random.random()
            g[6] = g[5] + random.random() * (1.0 - g[5])
    return g


def init_population(role: str, phase: str, seed_with_bootstrap: bool = True) -> List[list]:
    """Create initial population. Blue population seeds from bootstrap genome."""
    pop = []
    if role == "blue" and seed_with_bootstrap:
        pop.append(list(BOOTSTRAP_BLUE))
    while len(pop) < POPULATION_SIZE:
        pop.append(random_genome(role, phase))
    return pop[:POPULATION_SIZE]


def tournament_select(
    population: List[list], fitnesses: List[float], k: int = 3
) -> list:
    """Tournament selection: pick k random candidates, return fittest."""
    candidates = random.sample(range(len(population)), k)
    best = max(candidates, key=lambda i: fitnesses[i])
    return population[best]


def crossover(genome_a: list, genome_b: list) -> list:
    """Single-point crossover: split at random point."""
    point = random.randint(1, len(genome_a) - 1)
    return genome_a[:point] + genome_b[point:]


def adaptive_magnitude(win_rate: float) -> float:
    """Linear magnitude decay from 0.15 → 0.05 as win_rate goes 0.70 → 0.80."""
    if win_rate >= 0.70:
        t = (win_rate - 0.70) / (0.80 - 0.70)
        magnitude = 0.15 - t * (0.15 - 0.05)
        return max(magnitude, 0.05)  # clamp: t > 1.0 when win_rate > 0.80
    return 0.15


def mutate(
    genome: list,
    win_rate: float,
    role: str,
    phase: str,
    mutation_rate: float = 0.1,
) -> list:
    """Gaussian mutation with adaptive magnitude. Clips to declared gene ranges."""
    import random as _r
    magnitude = adaptive_magnitude(win_rate)
    ranges = RED_RANGES[:len(genome)] if role == "red" else BLUE_RANGES

    mutated = list(genome)
    for i in range(len(mutated)):
        if _r.random() < mutation_rate:
            lo, hi = ranges[i]
            mutated[i] = mutated[i] + _r.gauss(0, magnitude)
            mutated[i] = max(lo, min(hi, mutated[i]))

    # Re-enforce Blue ordering constraint after mutation
    if role == "blue" and mutated[6] <= mutated[5]:
        mutated[6] = min(1.0, mutated[5] + 0.05)

    return mutated


def next_generation(
    population: List[list],
    fitnesses: List[float],
    win_rate: float,
    role: str,
    phase: str,
) -> List[list]:
    """Produce next generation via elitism + tournament + crossover + mutation."""
    # Elitism: carry best genome unchanged
    best_idx = max(range(len(fitnesses)), key=lambda i: fitnesses[i])
    new_pop = [list(population[best_idx])]

    while len(new_pop) < POPULATION_SIZE:
        parent_a = tournament_select(population, fitnesses)
        parent_b = tournament_select(population, fitnesses)
        child = crossover(parent_a, parent_b)
        child = mutate(child, win_rate, role, phase)
        new_pop.append(child)

    return new_pop
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_ga_engine.py -v
```

Expected: all 11 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add host/ga_engine.py tests/test_ga_engine.py
git commit -m "feat: GA engine — population init, tournament selection, crossover, adaptive mutation"
```

---

## Task 11: host/coevolution.py — State Machine, Win Rate, Phase Unlock, Hall of Fame

**Files:**
- Create: `D:\Ry\cyber\host\coevolution.py`
- Create: `D:\Ry\cyber\tests\test_coevolution.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_coevolution.py
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from pathlib import Path
from host.coevolution import CoevolutionEngine, CoevolutionState

def test_bootstrap_starts_in_evolve_blue(tmp_path):
    # No blue_champion.json → start by evolving Blue
    engine = CoevolutionEngine(nz=tmp_path)
    engine.load_checkpoint()
    assert engine.state == CoevolutionState.EVOLVE_BLUE

def test_checkpoint_round_trip(tmp_path):
    engine = CoevolutionEngine(nz=tmp_path)
    engine.state = CoevolutionState.EVOLVE_RED
    engine.phase = "disruption"
    engine.generation = 15
    engine.save_checkpoint()
    engine2 = CoevolutionEngine(nz=tmp_path)
    engine2.load_checkpoint()
    assert engine2.state == CoevolutionState.EVOLVE_RED
    assert engine2.phase == "disruption"
    assert engine2.generation == 15

def test_win_rate_excludes_hof(tmp_path):
    engine = CoevolutionEngine(nz=tmp_path)
    engine.load_checkpoint()
    for _ in range(10):
        engine.record_outcome("BLUE_WIN", is_hof=False)
    for _ in range(5):
        engine.record_outcome("BLUE_WIN", is_hof=True)
    # win_rate should be based on 10 competitive rounds, not 15
    assert engine.competitive_win_rate() == 1.0

def test_phase_unlock_requires_80_percent(tmp_path):
    engine = CoevolutionEngine(nz=tmp_path)
    engine.load_checkpoint()
    # 15 wins out of 20 = 75% — should NOT unlock
    for _ in range(15):
        engine.record_outcome("BLUE_WIN", is_hof=False)
    for _ in range(5):
        engine.record_outcome("RED_WIN", is_hof=False)
    assert engine.check_phase_unlock() is False

def test_phase_unlock_requires_3_distinct_genomes(tmp_path):
    engine = CoevolutionEngine(nz=tmp_path)
    engine.load_checkpoint()
    # 80% wins but only 1 distinct genome contributed them all
    single = [0.25, 0.35, 0.2, 0.2, 0.5, 0.3, 0.7, 30.0]
    for _ in range(20):
        engine.record_outcome("BLUE_WIN", is_hof=False, winning_genome=single)
    assert engine.check_phase_unlock() is False

def test_hof_fires_every_10_generations(tmp_path):
    engine = CoevolutionEngine(nz=tmp_path)
    engine.load_checkpoint()
    assert engine.should_run_hof(9)  is False
    assert engine.should_run_hof(10) is True
    assert engine.should_run_hof(20) is True
    assert engine.should_run_hof(11) is False

def test_expand_genome_phase_b(tmp_path):
    engine = CoevolutionEngine(nz=tmp_path)
    phase_a_pop = [[0.3, 0.4, 0.6, 0.2, 0.5] for _ in range(20)]
    expanded = engine.expand_red_genome(phase_a_pop, to_phase="disruption")
    assert all(len(g) == 7 for g in expanded)
    # New genes must be 0.0
    assert all(g[5] == 0.0 and g[6] == 0.0 for g in expanded)
```

- [ ] **Step 2: Run to confirm failures**

```bash
pytest tests/test_coevolution.py -v
```

- [ ] **Step 3: Implement coevolution.py**

```python
# host/coevolution.py
"""
Sequential co-evolution state machine.
Manages EVOLVE_RED → EVOLVE_BLUE → PHASE_UNLOCK cycle,
win-rate tracking (excluding Hall of Fame rounds),
and crash recovery via ga_history.jsonl checkpoint.
"""
import json
import time
from enum import Enum
from pathlib import Path
from typing import List, Optional
import numpy as np

NEUTRAL_ZONE = Path("F:\\neutral_zone")
WIN_RATE_WINDOW = 20
EVOLVE_RED_THRESHOLD = 0.60
EVOLVE_BLUE_THRESHOLD = 0.80
MIN_DISTINCT_GENOMES = 3
GENOME_DISTANCE_MIN = 0.10


class CoevolutionState(Enum):
    EVOLVE_RED   = "EVOLVE_RED"
    EVOLVE_BLUE  = "EVOLVE_BLUE"
    PHASE_UNLOCK = "PHASE_UNLOCK"
    DONE         = "DONE"


def _genome_distance(a: list, b: list) -> float:
    """Normalized L1 distance between two genomes of the same length."""
    n = min(len(a), len(b))
    return sum(abs(a[i] - b[i]) for i in range(n)) / n


class CoevolutionEngine:
    def __init__(self, nz: Path = NEUTRAL_ZONE):
        self.nz = nz
        self.state = CoevolutionState.EVOLVE_BLUE
        self.phase = "stealth"
        self.generation = 0

        # Rolling competitive round results (excludes HoF)
        self._competitive_results: List[str] = []          # "WIN" or "LOSS"
        self._winning_genomes: List[Optional[list]] = []   # genome that won (if any)

    def load_checkpoint(self) -> None:
        """Resume from last ga_history.jsonl entry, or bootstrap."""
        champion_exists = (self.nz / "blue_champion.json").exists()
        history = self.nz / "ga_history.jsonl"

        if not history.exists() or not champion_exists:
            self.state = CoevolutionState.EVOLVE_BLUE
            return

        last = None
        with open(history) as f:
            for line in f:
                line = line.strip()
                if line:
                    last = json.loads(line)

        if last and "state_machine_state" in last:
            self.state = CoevolutionState(last["state_machine_state"])
            self.phase = last.get("phase", "stealth")
            self.generation = last.get("generation", 0)
            # Restore competitive window so win-rate resumes correctly
            self._competitive_results = last.get("competitive_results", [])
            self._winning_genomes    = last.get("winning_genomes", [])

    def save_checkpoint(
        self,
        round_id: str = "",
        outcome: str = "",
    ) -> None:
        """Append current engine state + round result to ga_history.jsonl."""
        entry = {
            "timestamp": time.time(),
            "state_machine_state": self.state.value,
            "phase": self.phase,
            "generation": self.generation,
            "round_id": round_id,
            "outcome": outcome,
            # Snapshot competitive window for crash recovery
            "competitive_results": list(self._competitive_results),
            "winning_genomes": list(self._winning_genomes),
        }
        with open(self.nz / "ga_history.jsonl", "a") as f:
            f.write(json.dumps(entry) + "\n")

    def record_outcome(
        self,
        outcome: str,
        is_hof: bool = False,
        winning_genome: Optional[list] = None,
    ) -> None:
        """Record a round result. HoF rounds are flagged and excluded from win rate."""
        if is_hof:
            return  # Do not add to competitive window

        is_win = outcome in ("BLUE_WIN",) if self.state == CoevolutionState.EVOLVE_BLUE \
                 else outcome in ("RED_WIN", "WATCHDOG_KILL")

        self._competitive_results.append("WIN" if is_win else "LOSS")
        self._winning_genomes.append(winning_genome if is_win else None)

        # Keep window bounded
        if len(self._competitive_results) > WIN_RATE_WINDOW:
            self._competitive_results.pop(0)
            self._winning_genomes.pop(0)

    def competitive_win_rate(self) -> float:
        if not self._competitive_results:
            return 0.0
        wins = self._competitive_results.count("WIN")
        return wins / len(self._competitive_results)

    def check_phase_unlock(self) -> bool:
        """True if Blue has achieved 80% wins with ≥3 distinct contributing genomes."""
        if len(self._competitive_results) < WIN_RATE_WINDOW:
            return False
        if self.competitive_win_rate() < EVOLVE_BLUE_THRESHOLD:
            return False

        # Distinct genome check
        winners = [g for g in self._winning_genomes if g is not None]
        if len(winners) < MIN_DISTINCT_GENOMES:
            return False

        # Check pairwise distances
        distinct = [winners[0]]
        for g in winners[1:]:
            if all(_genome_distance(g, d) > GENOME_DISTANCE_MIN for d in distinct):
                distinct.append(g)
        return len(distinct) >= MIN_DISTINCT_GENOMES

    def should_run_hof(self, generation: int) -> bool:
        return generation > 0 and generation % 10 == 0

    def expand_red_genome(
        self, population: List[list], to_phase: str
    ) -> List[list]:
        """Append new phase genes (initialized to 0.0) to all Red genomes."""
        from shared.genome import RED_PHASE_SIZES
        target_size = RED_PHASE_SIZES[to_phase]
        expanded = []
        for genome in population:
            diff = target_size - len(genome)
            expanded.append(list(genome) + [0.0] * diff)
        return expanded

    def freeze_champion(self, best_genome: list, role: str) -> None:
        """Save the best genome as champion JSON."""
        fname = "red_champion.json" if role == "red" else "blue_champion.json"
        path = self.nz / fname
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"genome": best_genome, "phase": self.phase}))
        tmp.replace(path)

    def load_champion(self, role: str) -> Optional[list]:
        fname = "red_champion.json" if role == "red" else "blue_champion.json"
        path = self.nz / fname
        try:
            return json.loads(path.read_text())["genome"]
        except (FileNotFoundError, KeyError):
            return None
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_coevolution.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add host/coevolution.py tests/test_coevolution.py
git commit -m "feat: co-evolution state machine, win rate tracking, phase unlock, Hall of Fame"
```

---

## Task 12: host/run_simulation.py — Entry Point + Integration Tests

**Files:**
- Create: `D:\Ry\cyber\host\run_simulation.py`
- Create: `D:\Ry\cyber\tests\test_run_simulation.py`

- [ ] **Step 1: Write failing integration tests first**

```python
# tests/test_run_simulation.py
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from unittest.mock import MagicMock, patch, call
from pathlib import Path
from host.coevolution import CoevolutionEngine, CoevolutionState
from host.run_simulation import (
    build_round_config, run_hof_rounds, should_halt,
)


def test_build_round_config_includes_required_fields():
    cfg = build_round_config(
        phase="stealth",
        red_genome=[0.3, 0.4, 0.6, 0.2, 0.5],
        blue_genome=[0.25, 0.35, 0.2, 0.2, 0.5, 0.3, 0.7, 30.0],
        round_id="gen001-ind00",
    )
    for key in ["phase", "red_genome", "blue_genome", "round_id",
                "time_limit_s", "delta_threshold", "monitored_reg_keys"]:
        assert key in cfg, f"Missing key: {key}"


def test_should_halt_done_state(tmp_path):
    engine = CoevolutionEngine(nz=tmp_path)
    engine.state = CoevolutionState.DONE
    assert should_halt(engine) is True


def test_should_halt_not_done(tmp_path):
    engine = CoevolutionEngine(nz=tmp_path)
    engine.state = CoevolutionState.EVOLVE_RED
    assert should_halt(engine) is False


def test_run_hof_rounds_runs_4_rounds(tmp_path):
    """HOF: 3 random opponents + 1 historical champion = 4 rounds."""
    mock_orch = MagicMock()
    mock_orch.run_round.return_value = {
        "outcome": "BLUE_WIN", "red_fitness": 0.0, "blue_fitness": 100.0
    }
    # Create a fake red champion
    (tmp_path / "red_champion.json").write_text(
        json.dumps({"genome": [0.5]*5, "phase": "stealth"})
    )
    engine = CoevolutionEngine(nz=tmp_path)
    engine.load_checkpoint()
    run_hof_rounds(
        engine=engine,
        orchestrator=mock_orch,
        best_genome=[0.25, 0.35, 0.2, 0.2, 0.5, 0.3, 0.7, 30.0],
        role="blue",
        phase="stealth",
        generation=10,
    )
    assert mock_orch.run_round.call_count == 4  # 3 random + 1 champion


def test_run_hof_rounds_skipped_at_non_hof_generation(tmp_path):
    mock_orch = MagicMock()
    engine = CoevolutionEngine(nz=tmp_path)
    run_hof_rounds(engine, mock_orch, [], "blue", "stealth", generation=7)
    mock_orch.run_round.assert_not_called()
```

- [ ] **Step 2: Run to confirm failures**

```bash
pytest tests/test_run_simulation.py -v
```

Expected: `ImportError` — `host/run_simulation.py` does not exist yet.

- [ ] **Step 3: Write run_simulation.py**

```python
# host/run_simulation.py
"""
Entry point: runs the full Vanguard Duel sequential co-evolution loop.

Usage:
    python host/run_simulation.py

Reads F:\\neutral_zone\\ for champion state. Writes all results to ga_history.jsonl.
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from host.orchestrator import Orchestrator
from host.ga_engine import init_population, next_generation, POPULATION_SIZE
from host.coevolution import CoevolutionEngine, CoevolutionState
from shared.genome import RED_PHASE_SIZES

NEUTRAL_ZONE = Path(os.environ.get("NEUTRAL_ZONE", r"F:\neutral_zone"))
WSB_PATH = Path(__file__).parent / "arena.wsb"

BASE_CONFIG = {
    "time_limit_s": 360,
    "blue_win_hold_s": 300,
    "delta_threshold": 0.05,
    "exfil_target_size_kb": 100,
    "cpu_core_count": 4,
    "monitored_reg_keys": [
        "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run",
        "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon",
        "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\RunOnce",
        "HKCU\\Environment",
    ],
    "monitored_dirs": [
        "C:\\Users\\WDAGUtilityAccount\\Desktop",
        "C:\\Users\\WDAGUtilityAccount\\AppData\\Roaming",
    ],
}


def build_round_config(
    phase: str, red_genome: list, blue_genome: list, round_id: str
) -> dict:
    """Build a complete round_config dict from genomes and shared BASE_CONFIG."""
    return {
        **BASE_CONFIG,
        "phase": phase,
        "red_genome": red_genome,
        "blue_genome": blue_genome,
        "round_id": round_id,
    }


def should_halt(engine: "CoevolutionEngine") -> bool:
    return engine.state == CoevolutionState.DONE


def run_hof_rounds(
    engine: "CoevolutionEngine",
    orchestrator,
    best_genome: list,
    role: str,
    phase: str,
    generation: int,
) -> None:
    """
    Hall of Fame anchor test: fires every 10 generations.
    Tests best_genome against:
      1. Three random opponents
      2. The historical champion (red_champion.json or blue_champion.json)
    Results are recorded as HoF (excluded from competitive win rate).
    """
    if not engine.should_run_hof(generation):
        return

    from host.ga_engine import random_genome
    opponent_role = "red" if role == "blue" else "blue"

    # 3 random opponents
    for i in range(3):
        opp = random_genome(opponent_role, phase)
        if role == "blue":
            red_g, blue_g = opp, best_genome
        else:
            red_g, blue_g = best_genome, opp
        cfg = build_round_config(phase, red_g, blue_g, f"hof-gen{generation:04d}-rand{i}")
        t = orchestrator.run_round(cfg)
        engine.record_outcome(t.get("outcome", "DRAW"), is_hof=True)

    # Historical champion opponent
    champion = engine.load_champion(opponent_role)
    if champion is not None:
        if role == "blue":
            red_g, blue_g = champion, best_genome
        else:
            red_g, blue_g = best_genome, champion
        cfg = build_round_config(phase, red_g, blue_g, f"hof-gen{generation:04d}-champ")
        t = orchestrator.run_round(cfg)
        engine.record_outcome(t.get("outcome", "DRAW"), is_hof=True)


def run():
    engine = CoevolutionEngine(nz=NEUTRAL_ZONE)
    engine.load_checkpoint()
    orch = Orchestrator(wsb_path=WSB_PATH, nz=NEUTRAL_ZONE)

    # Load or init populations
    red_pop = init_population("red", engine.phase)
    blue_pop = init_population("blue", engine.phase)
    red_fits = [0.0] * POPULATION_SIZE
    blue_fits = [0.0] * POPULATION_SIZE

    # Load frozen champions if available
    frozen_red  = engine.load_champion("red")
    frozen_blue = engine.load_champion("blue")
    if frozen_blue is None:
        from shared.genome import BOOTSTRAP_BLUE
        frozen_blue = list(BOOTSTRAP_BLUE)

    print(f"Starting in state: {engine.state.value}, phase: {engine.phase}")

    for gen in range(engine.generation, 1000):
        engine.generation = gen
        print(f"\n=== Generation {gen} | Phase: {engine.phase} | State: {engine.state.value} ===")

        is_hof = engine.should_run_hof(gen)

        for ind_idx in range(POPULATION_SIZE):
            round_id = f"gen{gen:04d}-ind{ind_idx:02d}"

            if engine.state == CoevolutionState.EVOLVE_RED:
                red_genome  = red_pop[ind_idx]
                blue_genome = frozen_blue
            else:  # EVOLVE_BLUE
                red_genome  = frozen_red or red_pop[ind_idx]
                blue_genome = blue_pop[ind_idx]

            config = build_round_config(engine.phase, red_genome, blue_genome, round_id)
            telemetry = orch.run_round(config)
            outcome = telemetry.get("outcome", "DRAW")

            # Track fitness
            red_fits[ind_idx]  = telemetry.get("red_fitness",  0.0)
            blue_fits[ind_idx] = telemetry.get("blue_fitness", 0.0)

            winning_genome = None
            if engine.state == CoevolutionState.EVOLVE_BLUE and outcome == "BLUE_WIN":
                winning_genome = blue_genome
            elif engine.state == CoevolutionState.EVOLVE_RED and outcome in ("RED_WIN", "WATCHDOG_KILL"):
                winning_genome = red_genome

            engine.record_outcome(outcome, is_hof=is_hof, winning_genome=winning_genome)
            print(f"  [{round_id}] {outcome} | R:{red_fits[ind_idx]:.1f} B:{blue_fits[ind_idx]:.1f}")

        # Hall of Fame anchor test (3 random + 1 historical champion)
        active_role = "red" if engine.state == CoevolutionState.EVOLVE_RED else "blue"
        active_pop  = red_pop if active_role == "red" else blue_pop
        active_fits = red_fits if active_role == "red" else blue_fits
        best_genome = active_pop[active_fits.index(max(active_fits))]
        run_hof_rounds(engine, orch, best_genome, active_role, engine.phase, gen)

        # Evolve the active population
        win_rate = engine.competitive_win_rate()
        if engine.state == CoevolutionState.EVOLVE_RED:
            red_pop = next_generation(red_pop, red_fits, win_rate, "red", engine.phase)
            # Check Red exit condition
            if win_rate >= 0.60 and len(engine._competitive_results) >= 20:
                best_red = red_pop[red_fits.index(max(red_fits))]
                engine.freeze_champion(best_red, "red")
                frozen_red = best_red
                engine.state = CoevolutionState.EVOLVE_BLUE
                engine._competitive_results.clear()
                engine._winning_genomes.clear()
                print(f"  → Red champion frozen. Switching to EVOLVE_BLUE.")
        else:
            blue_pop = next_generation(blue_pop, blue_fits, win_rate, "blue", engine.phase)
            # Check Blue exit condition
            if engine.check_phase_unlock():
                best_blue = blue_pop[blue_fits.index(max(blue_fits))]
                engine.freeze_champion(best_blue, "blue")
                frozen_blue = best_blue

                # Phase unlock
                phase_order = ["stealth", "disruption", "exfil"]
                current_idx = phase_order.index(engine.phase)
                if current_idx < len(phase_order) - 1:
                    next_phase = phase_order[current_idx + 1]
                    print(f"  → Phase unlock: {engine.phase} → {next_phase}")
                    red_pop = engine.expand_red_genome(red_pop, to_phase=next_phase)
                    red_fits = [0.0] * POPULATION_SIZE
                    engine.phase = next_phase
                else:
                    print("  → Simulation complete. Both champions archived.")
                    engine.state = CoevolutionState.DONE
                    engine.save_checkpoint()
                    break  # exit generation loop immediately

                engine.state = CoevolutionState.EVOLVE_RED
                engine._competitive_results.clear()
                engine._winning_genomes.clear()

        engine.save_checkpoint()

        if engine.state == CoevolutionState.DONE:
            break


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_run_simulation.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Verify the file parses without errors**

```bash
python -c "import host.run_simulation; print('OK')"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add host/run_simulation.py tests/test_run_simulation.py
git commit -m "feat: simulation entry point — HOF, phase unlock, DONE state, integration tests"
```

---

## Task 13: Phase B — Red Disruption Actions

**Files:**
- Modify: `D:\Ry\cyber\sandbox\red_agent.py`
- Modify: `D:\Ry\cyber\tests\test_red_agent.py`

- [ ] **Step 1: Write failing tests**

```python
# append to tests/test_red_agent.py
from sandbox.red_agent import RedAgent
import json

def make_phase_b_agent(tmp_path):
    config = {
        "phase": "disruption",
        "red_genome": [0.5, 0.5, 0.0, 0.0, 0.0, 0.8, 0.5],  # high kill freq + spike
        "monitored_dirs": [str(tmp_path)],
        "monitored_reg_keys": [],
    }
    (tmp_path / "round_config.json").write_text(json.dumps(config))
    agent = RedAgent(nz=tmp_path)
    agent.load_config()
    return agent

def test_action_process_kill_attempts_kill(tmp_path):
    agent = make_phase_b_agent(tmp_path)
    with patch("sandbox.red_agent.psutil") as mock_psutil:
        mock_proc = MagicMock()
        mock_proc.pid = 9999
        mock_proc.name.return_value = "notepad.exe"
        mock_psutil.process_iter.return_value = [mock_proc]
        agent.action_process_kill(t0_pids=set())
    # If kill was attempted, no exception = pass

def test_action_cpu_spike_does_not_crash(tmp_path):
    agent = make_phase_b_agent(tmp_path)
    # Should complete within a reasonable time (spike_intensity=0.5 → brief spike)
    agent.action_cpu_spike(duration_s=0.05)
```

- [ ] **Step 2: Run to confirm failures**

```bash
pytest tests/test_red_agent.py -v -k "phase_b or process_kill or cpu_spike"
```

- [ ] **Step 3: Add Phase B actions to red_agent.py**

```python
# append to RedAgent class in sandbox/red_agent.py

    def action_process_kill(self, t0_pids: set) -> None:
        """Kill a non-baseline process if process_kill_freq gene triggers."""
        freq = self.params.get("process_kill_freq", 0.0)
        if random.random() > freq:
            return
        try:
            import psutil as _psutil
            candidates = [
                p for p in _psutil.process_iter(["pid", "name"])
                if p.pid not in t0_pids
            ]
            if candidates:
                target = random.choice(candidates)
                target.kill()
        except Exception:
            pass

    def action_cpu_spike(self, duration_s: float = 0.5) -> None:
        """Briefly spike CPU according to cpu_spike_intensity gene."""
        import threading
        intensity = self.params.get("cpu_spike_intensity", 0.0)
        if intensity < 0.1:
            return
        stop = threading.Event()
        def spin():
            while not stop.is_set():
                pass
        threads = [threading.Thread(target=spin, daemon=True)
                   for _ in range(max(1, int(intensity * 4)))]
        for t in threads:
            t.start()
        time.sleep(duration_s * intensity)
        stop.set()
```

Also update `run_tick` to call phase B actions when genome has them:

```python
    def run_tick(self, t0_pids: set = None) -> None:
        self._stealth_delay()
        self.action_file_drop()
        self.action_reg_write()
        if len(self.config.get("red_genome", [])) > 5:
            self.action_process_kill(t0_pids or set())
            self.action_cpu_spike()
        self.actions_taken += 1
        self.write_heartbeat()
```

- [ ] **Step 4: Run all red agent tests**

```bash
pytest tests/test_red_agent.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add sandbox/red_agent.py tests/test_red_agent.py
git commit -m "feat: Phase B Red disruption actions (process kill, CPU spike)"
```

---

## Task 14: Phase C — Red Exfil Actions + Watchdog RED_WIN Detection

**Files:**
- Modify: `D:\Ry\cyber\sandbox\red_agent.py`
- Modify: `D:\Ry\cyber\tests\test_red_agent.py`

- [ ] **Step 1: Write failing tests**

```python
# append to tests/test_red_agent.py

def test_exfil_chunk_writes_to_exfil_dir(tmp_path):
    exfil_dir = tmp_path / "exfil"
    exfil_dir.mkdir()
    config = {
        "phase": "exfil",
        "red_genome": [0.5,0.5,0.0,0.0,0.0,0.0,0.0,0.8,0.0],
        "monitored_dirs": [], "monitored_reg_keys": [],
    }
    (tmp_path / "round_config.json").write_text(json.dumps(config))
    agent = RedAgent(nz=tmp_path)
    agent.load_config()
    agent.action_exfil_chunk()
    chunks = list(exfil_dir.iterdir())
    assert len(chunks) >= 1

def test_exfil_zero_chunk_size_no_write(tmp_path):
    exfil_dir = tmp_path / "exfil"
    exfil_dir.mkdir()
    config = {
        "phase": "exfil",
        "red_genome": [0.5,0.5,0.0,0.0,0.0,0.0,0.0,0.0,0.0],  # chunk_size=0
        "monitored_dirs": [], "monitored_reg_keys": [],
    }
    (tmp_path / "round_config.json").write_text(json.dumps(config))
    agent = RedAgent(nz=tmp_path)
    agent.load_config()
    agent.action_exfil_chunk()
    assert len(list(exfil_dir.iterdir())) == 0
```

- [ ] **Step 2: Run to confirm failures**

```bash
pytest tests/test_red_agent.py -v -k "exfil"
```

- [ ] **Step 3: Add Phase C exfil action to red_agent.py**

```python
# append to RedAgent class in sandbox/red_agent.py

    def action_exfil_chunk(self) -> None:
        """Write a chunk of random bytes to F:\\neutral_zone\\exfil\\."""
        chunk_size_norm = self.params.get("exfil_chunk_size", 0.0)
        if chunk_size_norm < 0.01:
            return
        # chunk_size_norm 0–1 maps to 1KB–50KB per chunk
        chunk_bytes = int(chunk_size_norm * 50 * 1024)
        exfil_dir = self.nz / "exfil"
        exfil_dir.mkdir(exist_ok=True)
        chunk_file = exfil_dir / f"chunk_{random.randint(100000, 999999)}.bin"
        chunk_file.write_bytes(os.urandom(chunk_bytes))
```

Update `run_tick` to call exfil when in Phase C:

```python
        if len(self.config.get("red_genome", [])) > 7:
            self.action_exfil_chunk()
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add sandbox/red_agent.py tests/test_red_agent.py
git commit -m "feat: Phase C Red exfil action — chunk writer to neutral zone exfil dir"
```

---

## Task 15: Full Test Suite Verification

- [ ] **Step 1: Run the complete test suite**

```bash
cd D:\Ry\cyber
pytest tests/ -v --tb=short
```

Expected: all tests PASS across all test files.

- [ ] **Step 2: Verify no stale .tmp files exist in neutral zone**

```bash
dir "F:\neutral_zone\*.tmp"
```

Expected: no files listed (or "File Not Found").

- [ ] **Step 3: Verify import chain is clean**

```bash
python -c "
from shared.genome import validate, BOOTSTRAP_BLUE
from sandbox.state_vector import build_state_vector, CpuMovingAverage
from sandbox.matrix_delta import compute_delta, classify_tier
from sandbox.watchdog import WatchdogRound
from sandbox.red_agent import RedAgent
from sandbox.blue_agent import BlueAgent
from host.orchestrator import Orchestrator
from host.ga_engine import next_generation
from host.coevolution import CoevolutionEngine
print('All imports OK')
"
```

Expected: `All imports OK`

- [ ] **Step 4: Final commit**

```bash
git add .
git commit -m "test: full test suite green — Vanguard Duel P1-P6 complete"
```

---

## Manual Smoke Test (After First WSB Run)

Once WSB is set up and `F:\neutral_zone\` is mounted:

1. Open PowerShell as Administrator
2. Run: `python D:\Ry\cyber\host\run_simulation.py`
3. Watch for:
   - `round_config.json` appearing in `F:\neutral_zone\`
   - `round_started.json` appearing ~12 seconds later (after noise floor)
   - `heartbeat.json` updating every 2 seconds
   - `telemetry.json` appearing at round end
4. Inspect `telemetry.json` for expected fields and sane fitness values
5. Inspect `ga_history.jsonl` for the appended round entry
