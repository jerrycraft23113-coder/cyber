import random
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.genome import (
    RED_PHASE_SIZES, BLUE_SIZE, RED_RANGES, BLUE_RANGES,
    validate, BOOTSTRAP_BLUE,
)

POPULATION_SIZE = 20
WIN_RATE_WINDOW = POPULATION_SIZE


def random_genome(role: str, phase: str) -> list:
    if role == "red":
        size = RED_PHASE_SIZES[phase]
        ranges = RED_RANGES[:size]
        g = [lo + random.random() * (hi - lo) for lo, hi in ranges]
    else:
        g = [lo + random.random() * (hi - lo) for lo, hi in BLUE_RANGES]
        while g[6] <= g[5]:
            g[5] = random.random()
            g[6] = g[5] + random.random() * (1.0 - g[5])
    return g


def init_population(role: str, phase: str, seed_with_bootstrap: bool = True) -> List[list]:
    pop = []
    if role == "blue" and seed_with_bootstrap:
        pop.append(list(BOOTSTRAP_BLUE))
    while len(pop) < POPULATION_SIZE:
        pop.append(random_genome(role, phase))
    return pop[:POPULATION_SIZE]


def tournament_select(population: List[list], fitnesses: List[float], k: int = 3) -> list:
    candidates = random.sample(range(len(population)), k)
    best = max(candidates, key=lambda i: fitnesses[i])
    return population[best]


def crossover(genome_a: list, genome_b: list) -> list:
    point = random.randint(1, len(genome_a) - 1)
    return genome_a[:point] + genome_b[point:]


def adaptive_magnitude(win_rate: float) -> float:
    if win_rate >= 0.70:
        t = (win_rate - 0.70) / (0.80 - 0.70)
        magnitude = 0.15 - t * (0.15 - 0.05)
        return max(magnitude, 0.05)
    return 0.15


def mutate(genome: list, win_rate: float, role: str, phase: str, mutation_rate: float = 0.1) -> list:
    magnitude = adaptive_magnitude(win_rate)
    ranges = RED_RANGES[:len(genome)] if role == "red" else BLUE_RANGES
    mutated = list(genome)
    for i in range(len(mutated)):
        if random.random() < mutation_rate:
            lo, hi = ranges[i]
            mutated[i] = max(lo, min(hi, mutated[i] + random.gauss(0, magnitude)))
    if role == "blue" and mutated[6] <= mutated[5]:
        mutated[6] = min(1.0, mutated[5] + 0.05)
    return mutated


def next_generation(population: List[list], fitnesses: List[float], win_rate: float, role: str, phase: str) -> List[list]:
    best_idx = max(range(len(fitnesses)), key=lambda i: fitnesses[i])
    new_pop = [list(population[best_idx])]
    while len(new_pop) < POPULATION_SIZE:
        parent_a = tournament_select(population, fitnesses)
        parent_b = tournament_select(population, fitnesses)
        child = crossover(parent_a, parent_b)
        child = mutate(child, win_rate, role, phase)
        new_pop.append(child)
    return new_pop
