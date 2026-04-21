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
