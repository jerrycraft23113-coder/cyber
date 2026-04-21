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
    if delta > 0.01:
        return "WATCH"
    return "NOMINAL"
