import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from pathlib import Path
from host.coevolution import CoevolutionEngine, CoevolutionState

def test_bootstrap_starts_in_evolve_blue(tmp_path):
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
    assert engine.competitive_win_rate() == 1.0

def test_phase_unlock_requires_80_percent(tmp_path):
    engine = CoevolutionEngine(nz=tmp_path)
    engine.load_checkpoint()
    for _ in range(15):
        engine.record_outcome("BLUE_WIN", is_hof=False)
    for _ in range(5):
        engine.record_outcome("RED_WIN", is_hof=False)
    assert engine.check_phase_unlock() is False

def test_phase_unlock_requires_3_distinct_genomes(tmp_path):
    engine = CoevolutionEngine(nz=tmp_path)
    engine.load_checkpoint()
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
    assert all(g[5] == 0.0 and g[6] == 0.0 for g in expanded)
