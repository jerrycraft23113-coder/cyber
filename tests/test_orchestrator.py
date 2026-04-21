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
        "red_fitness": 0, "blue_fitness": 0,
    }
    red_fit, blue_fit = score_from_telemetry(telemetry)
    assert blue_fit > red_fit
