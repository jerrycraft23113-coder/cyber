import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import random
from host.ga_engine import (
    random_genome, init_population, tournament_select,
    crossover, adaptive_magnitude, mutate, next_generation,
    POPULATION_SIZE,
)
from shared.genome import RED_PHASE_SIZES, BLUE_SIZE, validate

def test_random_red_genome_valid():
    g = random_genome("red", "stealth")
    assert validate(g, "stealth", role="red") is None

def test_random_blue_genome_valid():
    g = random_genome("blue", "stealth")
    assert validate(g, "stealth", role="blue") is None

def test_init_population_correct_size():
    pop = init_population("red", "stealth")
    assert len(pop) == POPULATION_SIZE

def test_tournament_select_returns_fitter():
    pop = [[float(i)] * 5 for i in range(20)]
    fits = list(range(20))
    wins = sum(1 for _ in range(1000) if tournament_select(pop, fits, k=3) == pop[19])
    assert wins > 100  # ~150 expected; validates selection pressure exists

def test_crossover_child_from_both_parents():
    a = [0.1] * 5
    b = [0.9] * 5
    child = crossover(a, b)
    assert len(child) == 5
    for gene in child:
        assert gene in (0.1, 0.9)

def test_adaptive_magnitude_at_zero():
    assert adaptive_magnitude(0.0) == 0.15

def test_adaptive_magnitude_at_70():
    assert abs(adaptive_magnitude(0.70) - 0.15) < 1e-9

def test_adaptive_magnitude_at_80():
    assert abs(adaptive_magnitude(0.80) - 0.05) < 1e-9

def test_adaptive_magnitude_above_80_clamped():
    assert adaptive_magnitude(0.95) == 0.05

def test_mutate_genes_stay_in_range():
    random.seed(42)
    g = random_genome("blue", "stealth")
    mutated = mutate(g, win_rate=0.0, role="blue", phase="stealth", mutation_rate=1.0)
    assert validate(mutated, "stealth", role="blue") is None

def test_next_generation_size_preserved():
    pop = init_population("red", "stealth")
    fits = [float(i) for i in range(len(pop))]
    new_pop = next_generation(pop, fits, win_rate=0.5, role="red", phase="stealth")
    assert len(new_pop) == POPULATION_SIZE

def test_next_generation_best_genome_preserved():
    pop = init_population("red", "stealth")
    fits = [float(i) for i in range(len(pop))]
    best = pop[fits.index(max(fits))]
    new_pop = next_generation(pop, fits, win_rate=0.5, role="red", phase="stealth")
    assert best in new_pop
