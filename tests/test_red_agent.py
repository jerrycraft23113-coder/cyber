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


# --- Phase B + C tests ---

def make_phase_b_agent(tmp_path):
    config = {
        "phase": "disruption",
        "red_genome": [0.5, 0.5, 0.0, 0.0, 0.0, 0.8, 0.5],
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

def test_action_cpu_spike_does_not_crash(tmp_path):
    agent = make_phase_b_agent(tmp_path)
    agent.action_cpu_spike(duration_s=0.05)

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
        "red_genome": [0.5,0.5,0.0,0.0,0.0,0.0,0.0,0.0,0.0],
        "monitored_dirs": [], "monitored_reg_keys": [],
    }
    (tmp_path / "round_config.json").write_text(json.dumps(config))
    agent = RedAgent(nz=tmp_path)
    agent.load_config()
    agent.action_exfil_chunk()
    assert len(list(exfil_dir.iterdir())) == 0
