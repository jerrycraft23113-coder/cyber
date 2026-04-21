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
    role: Optional[str] = None,
    delta_threshold: float = 0.05,
) -> Optional[str]:
    """Return None if valid, or an error string describing the problem.

    If role is not specified, it is inferred from genome length: if the
    length matches the expected red size for the given phase, role is "red";
    otherwise role is "blue".
    """
    if role is None:
        expected_red = RED_PHASE_SIZES.get(phase)
        role = "red" if (expected_red is not None and len(genome) == expected_red) else "blue"

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
