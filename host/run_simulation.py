"""
Entry point: runs the full Vanguard Duel sequential co-evolution loop.

Usage:
    python host/run_simulation.py

Reads F:\\neutral_zone\\ for champion state. Writes all results to ga_history.jsonl.
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from host.orchestrator import Orchestrator
from host.ga_engine import init_population, next_generation, POPULATION_SIZE
from host.coevolution import CoevolutionEngine, CoevolutionState
from shared.genome import RED_PHASE_SIZES

NEUTRAL_ZONE = Path(os.environ.get("NEUTRAL_ZONE", r"F:\neutral_zone"))
WSB_PATH = Path(__file__).parent / "arena.wsb"

BASE_CONFIG = {
    "time_limit_s": 360,
    "blue_win_hold_s": 300,
    "delta_threshold": 0.05,
    "exfil_target_size_kb": 100,
    "cpu_core_count": 4,
    "monitored_reg_keys": [
        "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run",
        "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon",
        "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\RunOnce",
        "HKCU\\Environment",
    ],
    "monitored_dirs": [
        "C:\\Users\\WDAGUtilityAccount\\Desktop",
        "C:\\Users\\WDAGUtilityAccount\\AppData\\Roaming",
    ],
}


def build_round_config(
    phase: str, red_genome: list, blue_genome: list, round_id: str
) -> dict:
    """Build a complete round_config dict from genomes and shared BASE_CONFIG."""
    return {
        **BASE_CONFIG,
        "phase": phase,
        "red_genome": red_genome,
        "blue_genome": blue_genome,
        "round_id": round_id,
    }


def should_halt(engine: "CoevolutionEngine") -> bool:
    return engine.state == CoevolutionState.DONE


def run_hof_rounds(
    engine: "CoevolutionEngine",
    orchestrator,
    best_genome: list,
    role: str,
    phase: str,
    generation: int,
) -> None:
    """
    Hall of Fame anchor test: fires every 10 generations.
    Tests best_genome against:
      1. Three random opponents
      2. The historical champion (red_champion.json or blue_champion.json)
    Results are recorded as HoF (excluded from competitive win rate).
    """
    if not engine.should_run_hof(generation):
        return

    from host.ga_engine import random_genome
    opponent_role = "red" if role == "blue" else "blue"

    # 3 random opponents
    for i in range(3):
        opp = random_genome(opponent_role, phase)
        if role == "blue":
            red_g, blue_g = opp, best_genome
        else:
            red_g, blue_g = best_genome, opp
        cfg = build_round_config(phase, red_g, blue_g, f"hof-gen{generation:04d}-rand{i}")
        t = orchestrator.run_round(cfg)
        engine.record_outcome(t.get("outcome", "DRAW"), is_hof=True)

    # Historical champion opponent
    champion = engine.load_champion(opponent_role)
    if champion is not None:
        if role == "blue":
            red_g, blue_g = champion, best_genome
        else:
            red_g, blue_g = best_genome, champion
        cfg = build_round_config(phase, red_g, blue_g, f"hof-gen{generation:04d}-champ")
        t = orchestrator.run_round(cfg)
        engine.record_outcome(t.get("outcome", "DRAW"), is_hof=True)


def run():
    engine = CoevolutionEngine(nz=NEUTRAL_ZONE)
    engine.load_checkpoint()
    orch = Orchestrator(wsb_path=WSB_PATH, nz=NEUTRAL_ZONE)

    # Load or init populations
    red_pop = init_population("red", engine.phase)
    blue_pop = init_population("blue", engine.phase)
    red_fits = [0.0] * POPULATION_SIZE
    blue_fits = [0.0] * POPULATION_SIZE

    # Load frozen champions if available
    frozen_red  = engine.load_champion("red")
    frozen_blue = engine.load_champion("blue")
    if frozen_blue is None:
        from shared.genome import BOOTSTRAP_BLUE
        frozen_blue = list(BOOTSTRAP_BLUE)

    print(f"Starting in state: {engine.state.value}, phase: {engine.phase}")

    for gen in range(engine.generation, 1000):
        engine.generation = gen
        print(f"\n=== Generation {gen} | Phase: {engine.phase} | State: {engine.state.value} ===")

        is_hof = engine.should_run_hof(gen)

        for ind_idx in range(POPULATION_SIZE):
            round_id = f"gen{gen:04d}-ind{ind_idx:02d}"

            if engine.state == CoevolutionState.EVOLVE_RED:
                red_genome  = red_pop[ind_idx]
                blue_genome = frozen_blue
            else:  # EVOLVE_BLUE
                red_genome  = frozen_red or red_pop[ind_idx]
                blue_genome = blue_pop[ind_idx]

            config = build_round_config(engine.phase, red_genome, blue_genome, round_id)
            telemetry = orch.run_round(config)
            outcome = telemetry.get("outcome", "DRAW")

            # Track fitness
            red_fits[ind_idx]  = telemetry.get("red_fitness",  0.0)
            blue_fits[ind_idx] = telemetry.get("blue_fitness", 0.0)

            winning_genome = None
            if engine.state == CoevolutionState.EVOLVE_BLUE and outcome == "BLUE_WIN":
                winning_genome = blue_genome
            elif engine.state == CoevolutionState.EVOLVE_RED and outcome in ("RED_WIN", "WATCHDOG_KILL"):
                winning_genome = red_genome

            engine.record_outcome(outcome, is_hof=is_hof, winning_genome=winning_genome)
            print(f"  [{round_id}] {outcome} | R:{red_fits[ind_idx]:.1f} B:{blue_fits[ind_idx]:.1f}")

        # Hall of Fame anchor test (3 random + 1 historical champion)
        active_role = "red" if engine.state == CoevolutionState.EVOLVE_RED else "blue"
        active_pop  = red_pop if active_role == "red" else blue_pop
        active_fits = red_fits if active_role == "red" else blue_fits
        best_genome = active_pop[active_fits.index(max(active_fits))]
        run_hof_rounds(engine, orch, best_genome, active_role, engine.phase, gen)

        # Evolve the active population
        win_rate = engine.competitive_win_rate()
        if engine.state == CoevolutionState.EVOLVE_RED:
            red_pop = next_generation(red_pop, red_fits, win_rate, "red", engine.phase)
            # Check Red exit condition
            if win_rate >= 0.60 and len(engine._competitive_results) >= 20:
                best_red = red_pop[red_fits.index(max(red_fits))]
                engine.freeze_champion(best_red, "red")
                frozen_red = best_red
                engine.state = CoevolutionState.EVOLVE_BLUE
                engine._competitive_results.clear()
                engine._winning_genomes.clear()
                print(f"  → Red champion frozen. Switching to EVOLVE_BLUE.")
        else:
            blue_pop = next_generation(blue_pop, blue_fits, win_rate, "blue", engine.phase)
            # Check Blue exit condition
            if engine.check_phase_unlock():
                best_blue = blue_pop[blue_fits.index(max(blue_fits))]
                engine.freeze_champion(best_blue, "blue")
                frozen_blue = best_blue

                # Phase unlock
                phase_order = ["stealth", "disruption", "exfil"]
                current_idx = phase_order.index(engine.phase)
                if current_idx < len(phase_order) - 1:
                    next_phase = phase_order[current_idx + 1]
                    print(f"  → Phase unlock: {engine.phase} → {next_phase}")
                    red_pop = engine.expand_red_genome(red_pop, to_phase=next_phase)
                    red_fits = [0.0] * POPULATION_SIZE
                    engine.phase = next_phase
                else:
                    print("  → Simulation complete. Both champions archived.")
                    engine.state = CoevolutionState.DONE
                    engine.save_checkpoint()
                    break

                engine.state = CoevolutionState.EVOLVE_RED
                engine._competitive_results.clear()
                engine._winning_genomes.clear()

        engine.save_checkpoint()

        if engine.state == CoevolutionState.DONE:
            break


if __name__ == "__main__":
    run()
