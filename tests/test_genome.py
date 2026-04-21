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
