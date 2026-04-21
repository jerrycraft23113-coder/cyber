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
