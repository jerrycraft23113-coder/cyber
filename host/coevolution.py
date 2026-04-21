import json
import time
from enum import Enum
from pathlib import Path
from typing import List, Optional
import numpy as np

NEUTRAL_ZONE = Path("F:\\neutral_zone")
WIN_RATE_WINDOW = 20
EVOLVE_RED_THRESHOLD = 0.60
EVOLVE_BLUE_THRESHOLD = 0.80
MIN_DISTINCT_GENOMES = 3
GENOME_DISTANCE_MIN = 0.10


class CoevolutionState(Enum):
    EVOLVE_RED   = "EVOLVE_RED"
    EVOLVE_BLUE  = "EVOLVE_BLUE"
    PHASE_UNLOCK = "PHASE_UNLOCK"
    DONE         = "DONE"


def _genome_distance(a: list, b: list) -> float:
    n = min(len(a), len(b))
    return sum(abs(a[i] - b[i]) for i in range(n)) / n


class CoevolutionEngine:
    def __init__(self, nz: Path = NEUTRAL_ZONE):
        self.nz = nz
        self.state = CoevolutionState.EVOLVE_BLUE
        self.phase = "stealth"
        self.generation = 0
        self._competitive_results: List[str] = []
        self._winning_genomes: List[Optional[list]] = []

    def load_checkpoint(self) -> None:
        history = self.nz / "ga_history.jsonl"
        if not history.exists():
            self.state = CoevolutionState.EVOLVE_BLUE
            return
        last = None
        with open(history) as f:
            for line in f:
                line = line.strip()
                if line:
                    last = json.loads(line)
        if last and "state_machine_state" in last:
            self.state = CoevolutionState(last["state_machine_state"])
            self.phase = last.get("phase", "stealth")
            self.generation = last.get("generation", 0)
            self._competitive_results = last.get("competitive_results", [])
            self._winning_genomes = last.get("winning_genomes", [])
        else:
            # History exists but has no state entry — bootstrap
            self.state = CoevolutionState.EVOLVE_BLUE

    def save_checkpoint(self, round_id: str = "", outcome: str = "") -> None:
        entry = {
            "timestamp": time.time(),
            "state_machine_state": self.state.value,
            "phase": self.phase,
            "generation": self.generation,
            "round_id": round_id,
            "outcome": outcome,
            "competitive_results": list(self._competitive_results),
            "winning_genomes": list(self._winning_genomes),
        }
        with open(self.nz / "ga_history.jsonl", "a") as f:
            f.write(json.dumps(entry) + "\n")

    def record_outcome(self, outcome: str, is_hof: bool = False, winning_genome: Optional[list] = None) -> None:
        if is_hof:
            return
        is_win = outcome in ("BLUE_WIN",) if self.state == CoevolutionState.EVOLVE_BLUE \
                 else outcome in ("RED_WIN", "WATCHDOG_KILL")
        self._competitive_results.append("WIN" if is_win else "LOSS")
        self._winning_genomes.append(winning_genome if is_win else None)
        if len(self._competitive_results) > WIN_RATE_WINDOW:
            self._competitive_results.pop(0)
            self._winning_genomes.pop(0)

    def competitive_win_rate(self) -> float:
        if not self._competitive_results:
            return 0.0
        return self._competitive_results.count("WIN") / len(self._competitive_results)

    def check_phase_unlock(self) -> bool:
        if len(self._competitive_results) < WIN_RATE_WINDOW:
            return False
        if self.competitive_win_rate() < EVOLVE_BLUE_THRESHOLD:
            return False
        winners = [g for g in self._winning_genomes if g is not None]
        if len(winners) < MIN_DISTINCT_GENOMES:
            return False
        distinct = [winners[0]]
        for g in winners[1:]:
            if all(_genome_distance(g, d) > GENOME_DISTANCE_MIN for d in distinct):
                distinct.append(g)
        return len(distinct) >= MIN_DISTINCT_GENOMES

    def should_run_hof(self, generation: int) -> bool:
        return generation > 0 and generation % 10 == 0

    def expand_red_genome(self, population: List[list], to_phase: str) -> List[list]:
        from shared.genome import RED_PHASE_SIZES
        target_size = RED_PHASE_SIZES[to_phase]
        return [list(g) + [0.0] * (target_size - len(g)) for g in population]

    def freeze_champion(self, best_genome: list, role: str) -> None:
        fname = "red_champion.json" if role == "red" else "blue_champion.json"
        path = self.nz / fname
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"genome": best_genome, "phase": self.phase}))
        tmp.replace(path)

    def load_champion(self, role: str) -> Optional[list]:
        fname = "red_champion.json" if role == "red" else "blue_champion.json"
        try:
            return json.loads((self.nz / fname).read_text())["genome"]
        except (FileNotFoundError, KeyError):
            return None
