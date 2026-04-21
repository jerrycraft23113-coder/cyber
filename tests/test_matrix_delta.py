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
