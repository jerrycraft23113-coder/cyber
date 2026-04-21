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


def test_is_heartbeat_fresh_returns_true_for_new_file(tmp_path):
    """A just-written file should be considered fresh."""
    from sandbox.watchdog import _is_heartbeat_fresh
    hb = tmp_path / "hb.json"
    hb.write_text('{"alive": true}')
    assert _is_heartbeat_fresh(hb) is True


def test_is_heartbeat_fresh_returns_false_for_missing_file(tmp_path):
    from sandbox.watchdog import _is_heartbeat_fresh
    hb = tmp_path / "no_hb.json"
    assert _is_heartbeat_fresh(hb) is False
