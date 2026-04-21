import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import patch, MagicMock
from pathlib import Path
from sandbox.blue_agent import BlueAgent, decide_action


def test_decide_action_nominal_does_nothing():
    assert decide_action("NOMINAL", 0.01, genome=[0.25,0.35,0.2,0.2,0.5,0.3,0.7,30.0]) is None


def test_decide_action_alert_suggests_freeze():
    action = decide_action("ALERT", 0.03, genome=[0.25,0.35,0.2,0.2,0.5,0.3,0.7,30.0])
    assert action is not None
    assert action["type"] == "FREEZE"


def test_decide_action_critical_above_null_route_threshold():
    # null_route_threshold = 0.7; delta = 0.9 > 0.7 → NULL_ROUTE
    genome = [0.25, 0.35, 0.2, 0.2, 0.5, 0.3, 0.7, 30.0]
    action = decide_action("CRITICAL", 0.9, genome=genome)
    assert action["type"] == "NULL_ROUTE"


def test_blue_writes_heartbeat(tmp_path):
    (tmp_path / "round_config.json").write_text(json.dumps({
        "phase": "stealth",
        "red_genome": [0.3,0.4,0.6,0.2,0.5],
        "blue_genome": [0.25,0.35,0.2,0.2,0.5,0.3,0.7,30.0],
    }))
    agent = BlueAgent(nz=tmp_path)
    agent.write_heartbeat()
    assert (tmp_path / "blue_heartbeat.json").exists()
