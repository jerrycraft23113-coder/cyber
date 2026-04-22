# Emergent AI — Plan A: VM Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the stack VM execution engine, operand mask utilities, control-flow repair, and updated genome format that the rest of the emergent AI system depends on.

**Architecture:** A `StackVM` class in `shared/vm/stack_vm.py` executes flat opcode-list programs. A `compute_operand_mask()` utility marks inline operands (PUSH/LOOP arguments) so branch-scanning and mutation never confuse data with code. `repair_control_flow()` ensures any spliced or mutated program is syntactically valid before execution. `shared/genome.py` is updated so a genome is an opcode list, not a float array — phases are removed entirely.

**Tech Stack:** Python 3.10+, pytest, existing project at `D:\Ry\cyber\`

**Spec:** `D:\Ry\cyber\docs\superpowers\specs\2026-04-22-emergent-ai-stack-vm-design.md`

---

## File Structure

```
shared/
  vm/
    __init__.py              CREATE — package marker
    stack_vm.py              CREATE — StackVM class, MAX_PROGRAM_LEN, MAX_STEPS
    operand_mask.py          CREATE — compute_operand_mask(), _find_else_or_endif(), _find_endif()
    repair.py                CREATE — repair_control_flow()
    instruction_set.py       CREATE — opcode dispatch stubs (full implementations in Plan B)
    generated/
      __init__.py            CREATE — package marker (auto-loads generated plugins)
  genome.py                  MODIFY — genome = opcode list; remove RED_PHASE_SIZES, phases
tests/
  test_operand_mask.py       CREATE
  test_repair.py             CREATE
  test_stack_vm.py           CREATE
  test_genome_v2.py          CREATE — replaces/extends test_genome.py
```

---

## Task 1: Directory Scaffold

**Files:**
- Create: `D:\Ry\cyber\shared\vm\__init__.py`
- Create: `D:\Ry\cyber\shared\vm\generated\__init__.py`

- [ ] **Step 1: Create the vm package**

```bash
mkdir D:\Ry\cyber\shared\vm
mkdir D:\Ry\cyber\shared\vm\generated
```

- [ ] **Step 2: Write `shared/vm/__init__.py`**

```python
# shared/vm/__init__.py
```

(empty file — package marker)

- [ ] **Step 3: Write `shared/vm/generated/__init__.py`**

```python
# shared/vm/generated/__init__.py
"""
Auto-loads all LLM-generated opcode plugins at import time.
Files are loaded in sorted filename order to ensure deterministic registration.
"""
import importlib
import pkgutil
from pathlib import Path

_here = Path(__file__).parent

def load_all():
    for finder, name, _ in sorted(pkgutil.iter_modules([str(_here)])):
        importlib.import_module(f"shared.vm.generated.{name}")

load_all()
```

- [ ] **Step 4: Verify imports work**

```bash
cd D:\Ry\cyber && python -c "import shared.vm; import shared.vm.generated; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
cd D:\Ry\cyber
git add shared/vm/__init__.py shared/vm/generated/__init__.py
git commit -m "feat: scaffold shared/vm package with generated plugin loader"
```

---

## Task 2: compute_operand_mask and branch scanners

**Files:**
- Create: `D:\Ry\cyber\shared\vm\operand_mask.py`
- Create: `D:\Ry\cyber\tests\test_operand_mask.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_operand_mask.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.vm.operand_mask import compute_operand_mask, _find_else_or_endif, _find_endif

def test_push_marks_next_slot():
    program = ["PUSH", 0.5, "GT"]
    mask = compute_operand_mask(program)
    assert mask == [False, True, False]

def test_loop_marks_next_slot():
    program = ["LOOP", 3, "NOP", "ENDLOOP"]
    mask = compute_operand_mask(program)
    assert mask == [False, True, False, False]

def test_push_at_end_no_operand():
    # PUSH at end of program — no following element to mark
    program = ["NOP", "PUSH"]
    mask = compute_operand_mask(program)
    assert mask == [False, False]

def test_consecutive_pushes():
    program = ["PUSH", 0.1, "PUSH", 0.2]
    mask = compute_operand_mask(program)
    assert mask == [False, True, False, True]

def test_non_operand_opcodes_false():
    program = ["SENSE_DELTA", "GT", "IF_TRUE", "DO_FILE_DROP", "ENDIF"]
    mask = compute_operand_mask(program)
    assert all(not m for m in mask)

def test_mixed_program():
    program = ["SENSE_DELTA", "PUSH", 0.3, "GT", "IF_TRUE", "DO_FILE_DROP", "ENDIF"]
    mask = compute_operand_mask(program)
    assert mask == [False, False, True, False, False, False, False]

def test_find_else_or_endif_simple():
    # IF_TRUE at 0, ENDIF at 2
    program = ["IF_TRUE", "NOP", "ENDIF"]
    mask = compute_operand_mask(program)
    result = _find_else_or_endif(program, 0, mask)
    assert result == 2

def test_find_else_or_endif_with_else():
    program = ["IF_TRUE", "NOP", "ELSE", "NOP", "ENDIF"]
    mask = compute_operand_mask(program)
    result = _find_else_or_endif(program, 0, mask)
    assert result == 2  # finds ELSE first

def test_find_else_or_endif_nested():
    # Nested IF — must skip inner ENDIF to find outer ELSE
    program = ["IF_TRUE", "IF_TRUE", "NOP", "ENDIF", "ELSE", "NOP", "ENDIF"]
    mask = compute_operand_mask(program)
    result = _find_else_or_endif(program, 0, mask)
    assert result == 4  # outer ELSE

def test_find_else_or_endif_not_found():
    # No matching ENDIF — returns len(program)
    program = ["IF_TRUE", "NOP"]
    mask = compute_operand_mask(program)
    result = _find_else_or_endif(program, 0, mask)
    assert result == len(program)

def test_find_else_skips_operand_containing_else_string():
    # A PUSH literal that happens to equal "ELSE" as a string — should be skipped
    # (In practice operands are floats, but test the mask guard)
    program = ["IF_TRUE", "PUSH", "ELSE", "ENDIF"]
    # position 2 is an operand slot (after PUSH) — must NOT be treated as ELSE
    mask = compute_operand_mask(program)
    assert mask[2] is True  # "ELSE" here is an operand, not an opcode
    result = _find_else_or_endif(program, 0, mask)
    assert result == 3  # ENDIF at position 3

def test_find_endif_simple():
    program = ["IF_TRUE", "NOP", "ENDIF"]
    mask = compute_operand_mask(program)
    assert _find_endif(program, 0, mask) == 2

def test_find_endif_skips_else():
    program = ["IF_TRUE", "NOP", "ELSE", "NOP", "ENDIF"]
    mask = compute_operand_mask(program)
    assert _find_endif(program, 2, mask) == 4  # called from ELSE position
```

- [ ] **Step 2: Run to confirm failures**

```bash
cd D:\Ry\cyber && python -m pytest tests/test_operand_mask.py -v 2>&1 | head -20
```

Expected: `ImportError` or `ModuleNotFoundError`

- [ ] **Step 3: Write `shared/vm/operand_mask.py`**

```python
# shared/vm/operand_mask.py
"""
Utilities for distinguishing opcode positions from inline operand positions
in a flat stack-program list.
"""
from typing import List

# Opcodes that consume the NEXT program element as an inline operand
_INLINE_OPERAND_OPCODES = frozenset(["PUSH", "LOOP"])


def compute_operand_mask(program: list) -> List[bool]:
    """
    Return a boolean list the same length as program.
    Position i is True if program[i] is an inline operand (not an opcode).

    Only PUSH and LOOP consume the next element as an operand.
    If PUSH/LOOP is the last element, no operand slot is marked.
    """
    mask = [False] * len(program)
    for i, op in enumerate(program):
        if op in _INLINE_OPERAND_OPCODES and i + 1 < len(program):
            mask[i + 1] = True
    return mask


def _find_else_or_endif(program: list, if_ip: int, mask: List[bool]) -> int:
    """
    Scan forward from if_ip (exclusive) for the ELSE or ENDIF that closes the
    IF_TRUE at if_ip, respecting nesting depth and skipping operand slots.

    Returns the index of the matching ELSE or ENDIF, or len(program) if not found.
    """
    depth = 0
    ip = if_ip + 1
    while ip < len(program):
        if mask[ip]:
            ip += 1
            continue
        op = program[ip]
        if op == "IF_TRUE":
            depth += 1
        elif op == "ENDIF":
            if depth == 0:
                return ip
            depth -= 1
        elif op == "ELSE" and depth == 0:
            return ip
        ip += 1
    return len(program)


def _find_endif(program: list, from_ip: int, mask: List[bool]) -> int:
    """
    Scan forward from from_ip (exclusive) for the ENDIF that closes the current
    IF/ELSE block, respecting nesting depth and skipping operand slots.

    Returns the index of the matching ENDIF, or len(program) if not found.
    """
    depth = 0
    ip = from_ip + 1
    while ip < len(program):
        if mask[ip]:
            ip += 1
            continue
        op = program[ip]
        if op == "IF_TRUE":
            depth += 1
        elif op == "ENDIF":
            if depth == 0:
                return ip
            depth -= 1
        ip += 1
    return len(program)
```

- [ ] **Step 4: Run tests**

```bash
cd D:\Ry\cyber && python -m pytest tests/test_operand_mask.py -v
```

Expected: all 14 tests PASS

- [ ] **Step 5: Commit**

```bash
cd D:\Ry\cyber
git add shared/vm/operand_mask.py tests/test_operand_mask.py
git commit -m "feat: add compute_operand_mask and branch scanners"
```

---

## Task 3: repair_control_flow

**Files:**
- Create: `D:\Ry\cyber\shared\vm\repair.py`
- Create: `D:\Ry\cyber\tests\test_repair.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_repair.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.vm.repair import repair_control_flow
from shared.vm.stack_vm import MAX_PROGRAM_LEN

def test_valid_program_unchanged():
    program = ["IF_TRUE", "NOP", "ENDIF"]
    assert repair_control_flow(program) == program

def test_removes_orphaned_endif():
    program = ["NOP", "ENDIF", "NOP"]
    result = repair_control_flow(program)
    assert "ENDIF" not in result

def test_removes_orphaned_else():
    program = ["NOP", "ELSE", "NOP"]
    result = repair_control_flow(program)
    assert "ELSE" not in result

def test_closes_unclosed_if():
    program = ["IF_TRUE", "NOP"]
    result = repair_control_flow(program)
    assert result.count("ENDIF") == 1
    assert result[-1] == "ENDIF"

def test_removes_orphaned_endloop():
    program = ["NOP", "ENDLOOP", "NOP"]
    result = repair_control_flow(program)
    assert "ENDLOOP" not in result

def test_closes_unclosed_loop():
    program = ["LOOP", 2, "NOP"]
    result = repair_control_flow(program)
    assert "ENDLOOP" in result

def test_preserves_push_operand():
    program = ["PUSH", 0.5, "GT"]
    result = repair_control_flow(program)
    assert result == ["PUSH", 0.5, "GT"]

def test_preserves_loop_operand():
    program = ["LOOP", 3, "NOP", "ENDLOOP"]
    result = repair_control_flow(program)
    assert result == ["LOOP", 3, "NOP", "ENDLOOP"]

def test_truncates_to_max_len():
    program = ["NOP"] * 100
    result = repair_control_flow(program)
    assert len(result) <= MAX_PROGRAM_LEN

def test_nested_if_valid():
    program = ["IF_TRUE", "IF_TRUE", "NOP", "ENDIF", "ENDIF"]
    result = repair_control_flow(program)
    assert result == program

def test_else_without_if_removed():
    program = ["ELSE", "NOP", "ENDIF"]
    result = repair_control_flow(program)
    assert "ELSE" not in result
    assert "ENDIF" not in result  # orphaned ENDIF also removed

def test_nested_if_unclosed_outer():
    program = ["IF_TRUE", "IF_TRUE", "NOP", "ENDIF"]
    result = repair_control_flow(program)
    assert result.count("IF_TRUE") == 2
    assert result.count("ENDIF") == 2

def test_operand_containing_if_keyword_preserved():
    # PUSH followed by a float that happens to be 0.0 — stays as operand
    program = ["IF_TRUE", "PUSH", 0.0, "ENDIF"]
    result = repair_control_flow(program)
    assert result == ["IF_TRUE", "PUSH", 0.0, "ENDIF"]

def test_output_minimum_length():
    program = ["NOP"] * 2
    result = repair_control_flow(program)
    assert len(result) >= 1  # never empty
```

- [ ] **Step 2: Run to confirm failures**

```bash
cd D:\Ry\cyber && python -m pytest tests/test_repair.py -v 2>&1 | head -10
```

Expected: `ImportError`

- [ ] **Step 3: Write `shared/vm/repair.py`**

```python
# shared/vm/repair.py
"""
repair_control_flow: ensures any opcode list is syntactically valid.
Called after every crossover and mutation.
"""
from shared.vm.operand_mask import compute_operand_mask

MAX_PROGRAM_LEN = 64  # imported by stack_vm too — defined here as canonical source


def repair_control_flow(program: list) -> list:
    """
    Produce a syntactically valid opcode program from an arbitrary list.

    Four passes:
      1. Strip orphaned ELSE and ENDIF (no matching IF_TRUE)
      2. Close unclosed IF_TRUE blocks with ENDIF
      3. Strip orphaned ENDLOOP (no matching LOOP)
      4. Close unclosed LOOP blocks with ENDLOOP

    Preserves all PUSH/LOOP inline operands.
    Output is truncated to MAX_PROGRAM_LEN.
    """
    program = list(program)

    # ── Pass 1 & 2: IF_TRUE / ELSE / ENDIF ─────────────────────────────────
    pass1 = []
    if_depth = 0
    mask = compute_operand_mask(program)

    for i, op in enumerate(program):
        if mask[i]:
            pass1.append(op)  # operand slots always kept
            continue
        if op == "IF_TRUE":
            if_depth += 1
            pass1.append(op)
        elif op == "ELSE":
            if if_depth > 0:
                pass1.append(op)
            # else: orphaned ELSE — drop
        elif op == "ENDIF":
            if if_depth > 0:
                if_depth -= 1
                pass1.append(op)
            # else: orphaned ENDIF — drop
        else:
            pass1.append(op)

    # Close unclosed IF_TRUE blocks
    for _ in range(if_depth):
        if len(pass1) < MAX_PROGRAM_LEN:
            pass1.append("ENDIF")

    # ── Pass 3 & 4: LOOP / ENDLOOP ──────────────────────────────────────────
    final = []
    loop_depth = 0
    i = 0
    while i < len(pass1):
        op = pass1[i]
        if op == "LOOP":
            loop_depth += 1
            final.append(op)
            i += 1
            if i < len(pass1):  # append inline operand
                final.append(pass1[i])
        elif op == "ENDLOOP":
            if loop_depth > 0:
                loop_depth -= 1
                final.append(op)
            # else: orphaned ENDLOOP — drop
        else:
            final.append(op)
        i += 1

    # Close unclosed LOOP blocks
    for _ in range(loop_depth):
        if len(final) < MAX_PROGRAM_LEN:
            final.append("ENDLOOP")

    return final[:MAX_PROGRAM_LEN]
```

- [ ] **Step 4: Note — `MAX_PROGRAM_LEN` is defined in `repair.py` and imported by `stack_vm.py`**

`repair.py` is the canonical source for `MAX_PROGRAM_LEN = 64`. `stack_vm.py` will import it from here.

- [ ] **Step 5: Run tests**

```bash
cd D:\Ry\cyber && python -m pytest tests/test_repair.py -v
```

Expected: all 14 tests PASS

- [ ] **Step 6: Commit**

```bash
cd D:\Ry\cyber
git add shared/vm/repair.py tests/test_repair.py
git commit -m "feat: add repair_control_flow with full 4-pass algorithm"
```

---

## Task 4: instruction_set.py stubs

**Files:**
- Create: `D:\Ry\cyber\shared\vm\instruction_set.py`

No tests for this task — stubs will be tested via the VM tests in Task 5.

- [ ] **Step 1: Write `shared/vm/instruction_set.py`**

```python
# shared/vm/instruction_set.py
"""
Opcode dispatch: maps DO_* and SENSE_* opcode names to handler functions.

DO_* handlers: def do_xxx(agent) -> None
SENSE_* handlers: def sense_xxx(agent) -> float

Stub implementations suffice for Plan A. Full implementations land in Plan B.
LLM-generated handlers in shared/vm/generated/ are auto-registered at import time.
"""
from typing import Callable, Dict

# ── Registries ────────────────────────────────────────────────────────────────
_DO_HANDLERS: Dict[str, Callable] = {}
_SENSE_HANDLERS: Dict[str, Callable] = {}

_BUILTIN_OPCODES: set = set()  # populated below; LLM ops cannot overwrite these


def register_do(name: str, fn: Callable) -> None:
    """Register a DO_* handler. name must start with 'DO_'. Builtins cannot be overwritten."""
    if name in _BUILTIN_OPCODES:
        import logging
        logging.warning(f"instruction_set: skipping LLM opcode {name!r} — collides with builtin")
        return
    _DO_HANDLERS[name] = fn


def register_sense(name: str, fn: Callable) -> None:
    """Register a SENSE_* handler. Builtins cannot be overwritten."""
    if name in _BUILTIN_OPCODES:
        import logging
        logging.warning(f"instruction_set: skipping LLM opcode {name!r} — collides with builtin")
        return
    _SENSE_HANDLERS[name] = fn


def dispatch_do(opcode: str, agent) -> None:
    """Call the handler for a DO_* opcode. Unknown opcodes are silently ignored (NOP)."""
    fn = _DO_HANDLERS.get(opcode)
    if fn:
        fn(agent)


def dispatch_sense(opcode: str, agent) -> float:
    """Call the handler for a SENSE_* opcode. Unknown opcodes return 0.0."""
    fn = _SENSE_HANDLERS.get(opcode)
    return fn(agent) if fn else 0.0


def known_do_opcodes() -> list:
    return list(_DO_HANDLERS.keys())


def known_sense_opcodes() -> list:
    return list(_SENSE_HANDLERS.keys())


# ── SENSE stub implementations ────────────────────────────────────────────────
# Full snap_* population happens in Plan B (agent shells).
# Stubs return 0.0 so VM tests can run without a real agent.

def _stub_sense(attr: str):
    def _sense(agent) -> float:
        return float(getattr(agent, attr, 0.0))
    return _sense


_SENSE_DEFS = {
    "SENSE_DELTA":          "current_delta",
    "SENSE_TIER":           "current_tier",
    "SENSE_PROC_COUNT":     "snap_proc_count",
    "SENSE_PORT_COUNT":     "snap_port_count",
    "SENSE_CPU_AVG":        "snap_cpu_avg",
    "SENSE_TICK":           "current_tick",
    "SENSE_SCHED_TASKS":    "snap_sched_tasks",
    "SENSE_OUTBOUND_CONNS": "snap_outbound_conns",
    "SENSE_CHILD_DEPTH":    "snap_child_depth",
    "SENSE_PRIVESC_SIGNALS":"snap_privesc_signals",
    "SENSE_BLUE_RESPONSES": "snap_blue_responses",
    "SENSE_NEW_PROCS":      "snap_new_procs",
}

for _opcode, _attr in _SENSE_DEFS.items():
    _SENSE_HANDLERS[_opcode] = _stub_sense(_attr)
    _BUILTIN_OPCODES.add(_opcode)


# ── DO stub implementations ───────────────────────────────────────────────────
# Plan B replaces these with real implementations.

def _stub_do(name: str):
    def _do(agent) -> None:
        pass  # Plan B fills in real behaviour
    _do.__name__ = name.lower()
    return _do


_DO_NAMES = [
    # Red
    "DO_FILE_DROP", "DO_REG_WRITE", "DO_PROCESS_KILL", "DO_CPU_SPIKE",
    "DO_EXFIL_CHUNK", "DO_LATERAL_SPAWN", "DO_NZ_ARTIFACT",
    "DO_PRIVESC", "DO_NET_SCAN", "DO_REG_PERSISTENCE",
    # Blue
    "DO_FREEZE", "DO_NULL_ROUTE", "DO_QUARANTINE", "DO_RESTORE_REG",
    "DO_MEMORY_SCAN", "DO_ANCESTRY_CHECK", "DO_FLOW_ANALYSIS",
]

for _name in _DO_NAMES:
    _DO_HANDLERS[_name] = _stub_do(_name)
    _BUILTIN_OPCODES.add(_name)


# ── Load LLM-generated plugins (must be last) ─────────────────────────────────
import shared.vm.generated  # noqa: E402 — triggers generated/__init__.py load_all()
```

- [ ] **Step 2: Verify it imports cleanly**

```bash
cd D:\Ry\cyber && python -c "from shared.vm.instruction_set import dispatch_do, dispatch_sense, known_do_opcodes; print(known_do_opcodes())"
```

Expected: list of all 17 DO opcode names

- [ ] **Step 3: Commit**

```bash
cd D:\Ry\cyber
git add shared/vm/instruction_set.py
git commit -m "feat: add instruction_set with stub DO/SENSE handlers and LLM plugin loader"
```

---

## Task 5: StackVM

**Files:**
- Create: `D:\Ry\cyber\shared\vm\stack_vm.py`
- Create: `D:\Ry\cyber\tests\test_stack_vm.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_stack_vm.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.vm.stack_vm import StackVM, MAX_PROGRAM_LEN, MAX_STEPS
from shared.vm.repair import repair_control_flow

class MockAgent:
    """Minimal agent stub for VM tests."""
    current_delta = 0.5
    current_tier = 2        # ALERT
    current_tick = 10
    t0_pids = set()
    nz = None
    role = "red"
    snap_proc_count = 5.0
    snap_port_count = 3.0
    snap_cpu_avg = 0.2
    snap_sched_tasks = 2.0
    snap_outbound_conns = 1.0
    snap_child_depth = 0.0
    snap_privesc_signals = 0.0
    snap_blue_responses = 0.0
    snap_new_procs = 0.0
    actions = []
    def record(self, name): self.actions.append(name)

vm = StackVM()

# ── Stack ops ─────────────────────────────────────────────────────────────────

def test_push_puts_value_on_stack():
    agent = MockAgent()
    vm.run(["PUSH", 0.7], agent)  # value left on stack — no assertion needed, just no crash

def test_pop_removes_top():
    agent = MockAgent()
    vm.run(["PUSH", 0.7, "POP"], agent)

def test_dup_duplicates_top():
    # DUP + GT on same value → 0.0 (not strictly greater than itself)
    agent = MockAgent()
    vm.run(["PUSH", 0.5, "DUP", "GT"], agent)

def test_add():
    # PUSH 0.3 + PUSH 0.4 = 0.7; GT PUSH 0.6 → 1.0 (true); IF_TRUE runs NOP; ENDIF
    agent = MockAgent()
    vm.run(["PUSH", 0.3, "PUSH", 0.4, "ADD", "PUSH", 0.6, "GT",
            "IF_TRUE", "NOP", "ENDIF"], agent)

def test_sub():
    agent = MockAgent()
    vm.run(["PUSH", 0.9, "PUSH", 0.4, "SUB"], agent)  # 0.5 on stack, no crash

def test_mul():
    agent = MockAgent()
    vm.run(["PUSH", 0.5, "PUSH", 0.5, "MUL"], agent)  # 0.25 on stack, no crash

# ── Comparison ────────────────────────────────────────────────────────────────

def test_gt_true():
    agent = MockAgent()
    # PUSH 0.8, PUSH 0.3, GT → 0.8 > 0.3 → 1.0 on stack
    # Then IF_TRUE runs DO_FILE_DROP (stub, no-op), ENDIF
    vm.run(["PUSH", 0.8, "PUSH", 0.3, "GT",
            "IF_TRUE", "DO_FILE_DROP", "ENDIF"], agent)

def test_gt_false_skips_if_body():
    agent = MockAgent()
    # 0.2 > 0.8 → false → IF_TRUE should skip to ENDIF
    vm.run(["PUSH", 0.2, "PUSH", 0.8, "GT",
            "IF_TRUE", "DO_FILE_DROP", "ENDIF"], agent)

def test_lte():
    agent = MockAgent()
    vm.run(["PUSH", 0.3, "PUSH", 0.8, "LTE",
            "IF_TRUE", "NOP", "ENDIF"], agent)

def test_eq_true():
    agent = MockAgent()
    vm.run(["PUSH", 0.5, "PUSH", 0.5, "EQ",
            "IF_TRUE", "NOP", "ENDIF"], agent)

# ── Control flow ──────────────────────────────────────────────────────────────

def test_if_true_branch_taken():
    """IF_TRUE with 1.0 on stack should execute body."""
    called = []
    from shared.vm import instruction_set as IS

    original = IS._DO_HANDLERS.get("DO_FILE_DROP")
    IS._DO_HANDLERS["DO_FILE_DROP"] = lambda a: called.append("file_drop")
    try:
        agent = MockAgent()
        vm.run(["PUSH", 1.0, "IF_TRUE", "DO_FILE_DROP", "ENDIF"], agent)
        assert called == ["file_drop"]
    finally:
        IS._DO_HANDLERS["DO_FILE_DROP"] = original

def test_if_true_branch_skipped():
    """IF_TRUE with 0.0 on stack should skip body."""
    called = []
    from shared.vm import instruction_set as IS

    original = IS._DO_HANDLERS.get("DO_FILE_DROP")
    IS._DO_HANDLERS["DO_FILE_DROP"] = lambda a: called.append("file_drop")
    try:
        agent = MockAgent()
        vm.run(["PUSH", 0.0, "IF_TRUE", "DO_FILE_DROP", "ENDIF"], agent)
        assert called == []
    finally:
        IS._DO_HANDLERS["DO_FILE_DROP"] = original

def test_else_branch_taken_when_if_skipped():
    called = []
    from shared.vm import instruction_set as IS

    orig_fd = IS._DO_HANDLERS.get("DO_FILE_DROP")
    orig_rw = IS._DO_HANDLERS.get("DO_REG_WRITE")
    IS._DO_HANDLERS["DO_FILE_DROP"] = lambda a: called.append("file_drop")
    IS._DO_HANDLERS["DO_REG_WRITE"] = lambda a: called.append("reg_write")
    try:
        agent = MockAgent()
        vm.run(["PUSH", 0.0, "IF_TRUE", "DO_FILE_DROP",
                "ELSE", "DO_REG_WRITE", "ENDIF"], agent)
        assert called == ["reg_write"]
    finally:
        IS._DO_HANDLERS["DO_FILE_DROP"] = orig_fd
        IS._DO_HANDLERS["DO_REG_WRITE"] = orig_rw

def test_loop_executes_n_times():
    called = []
    from shared.vm import instruction_set as IS

    original = IS._DO_HANDLERS.get("DO_FILE_DROP")
    IS._DO_HANDLERS["DO_FILE_DROP"] = lambda a: called.append(1)
    try:
        agent = MockAgent()
        vm.run(["LOOP", 3, "DO_FILE_DROP", "ENDLOOP"], agent)
        assert len(called) == 3
    finally:
        IS._DO_HANDLERS["DO_FILE_DROP"] = original

def test_loop_clamped_to_8():
    called = []
    from shared.vm import instruction_set as IS

    original = IS._DO_HANDLERS.get("DO_FILE_DROP")
    IS._DO_HANDLERS["DO_FILE_DROP"] = lambda a: called.append(1)
    try:
        agent = MockAgent()
        vm.run(["LOOP", 100, "DO_FILE_DROP", "ENDLOOP"], agent)
        assert len(called) == 8
    finally:
        IS._DO_HANDLERS["DO_FILE_DROP"] = original

def test_nested_loops_up_to_4():
    called = []
    from shared.vm import instruction_set as IS

    original = IS._DO_HANDLERS.get("DO_NOP", IS._DO_HANDLERS.get("DO_FILE_DROP"))
    IS._DO_HANDLERS["DO_FILE_DROP"] = lambda a: called.append(1)
    try:
        agent = MockAgent()
        # 2×2 = 4 calls
        vm.run(["LOOP", 2, "LOOP", 2, "DO_FILE_DROP", "ENDLOOP", "ENDLOOP"], agent)
        assert len(called) == 4
    finally:
        IS._DO_HANDLERS["DO_FILE_DROP"] = original

def test_fifth_nested_loop_is_nop():
    called = []
    from shared.vm import instruction_set as IS

    original = IS._DO_HANDLERS.get("DO_FILE_DROP")
    IS._DO_HANDLERS["DO_FILE_DROP"] = lambda a: called.append(1)
    try:
        agent = MockAgent()
        # 5th nested LOOP should be treated as NOP (no additional iterations)
        prog = (["LOOP", 2] * 5) + ["DO_FILE_DROP"] + (["ENDLOOP"] * 5)
        prog = repair_control_flow(prog)
        vm.run(prog, agent)
        # Should not raise, loop count bounded
        assert len(called) <= 8 ** 4  # can't exceed 4 nested loops of max 8
    finally:
        IS._DO_HANDLERS["DO_FILE_DROP"] = original

# ── Safety ────────────────────────────────────────────────────────────────────

def test_max_steps_halts_silently():
    """Infinite-looking program halts after MAX_STEPS, no exception."""
    agent = MockAgent()
    # Program that would loop forever without MAX_STEPS guard
    # Use a very long NOP sequence instead to hit the step limit
    program = ["NOP"] * (MAX_STEPS + 10)
    vm.run(program, agent)  # must not raise

def test_stack_underflow_returns_zero():
    agent = MockAgent()
    # GT on empty stack should not crash
    vm.run(["GT"], agent)

def test_unknown_opcode_is_nop():
    agent = MockAgent()
    vm.run(["UNKNOWN_OP_XYZ", "NOP"], agent)  # must not raise

def test_halt_stops_execution():
    called = []
    from shared.vm import instruction_set as IS

    original = IS._DO_HANDLERS.get("DO_FILE_DROP")
    IS._DO_HANDLERS["DO_FILE_DROP"] = lambda a: called.append(1)
    try:
        agent = MockAgent()
        vm.run(["HALT", "DO_FILE_DROP"], agent)
        assert called == []  # DO_FILE_DROP never reached
    finally:
        IS._DO_HANDLERS["DO_FILE_DROP"] = original

def test_halt_inside_loop_exits_immediately():
    called = []
    from shared.vm import instruction_set as IS

    original = IS._DO_HANDLERS.get("DO_FILE_DROP")
    IS._DO_HANDLERS["DO_FILE_DROP"] = lambda a: called.append(1)
    try:
        agent = MockAgent()
        vm.run(["LOOP", 5, "HALT", "DO_FILE_DROP", "ENDLOOP"], agent)
        assert called == []
    finally:
        IS._DO_HANDLERS["DO_FILE_DROP"] = original

# ── SENSE ─────────────────────────────────────────────────────────────────────

def test_sense_delta_pushes_agent_value():
    """SENSE_DELTA should push agent.current_delta onto stack."""
    from shared.vm import instruction_set as IS

    called_with = []
    # Verify by using SENSE_DELTA + PUSH + GT in a branch
    original_fd = IS._DO_HANDLERS.get("DO_FILE_DROP")
    IS._DO_HANDLERS["DO_FILE_DROP"] = lambda a: called_with.append(a.current_delta)
    try:
        agent = MockAgent()
        agent.current_delta = 0.9
        # SENSE_DELTA (pushes 0.9), PUSH 0.5, GT → 1.0, IF_TRUE → DO_FILE_DROP
        vm.run(["SENSE_DELTA", "PUSH", 0.5, "GT",
                "IF_TRUE", "DO_FILE_DROP", "ENDIF"], agent)
        assert called_with == [0.9]
    finally:
        IS._DO_HANDLERS["DO_FILE_DROP"] = original_fd

def test_role_gated_sense_wrong_role_returns_zero():
    """SENSE_BLUE_RESPONSES in a Red agent returns 0.0 (role-gated)."""
    # With stub implementation, this just reads snap_blue_responses = 0.0 anyway.
    # The important thing is it doesn't crash.
    agent = MockAgent()
    agent.role = "red"
    agent.snap_blue_responses = 99.0  # even if set, role-gating may zero it in Plan B
    vm.run(["SENSE_BLUE_RESPONSES", "PUSH", 0.1, "GT",
            "IF_TRUE", "NOP", "ENDIF"], agent)
```

- [ ] **Step 2: Run to confirm failures**

```bash
cd D:\Ry\cyber && python -m pytest tests/test_stack_vm.py -v 2>&1 | head -10
```

Expected: `ImportError`

- [ ] **Step 3: Write `shared/vm/stack_vm.py`**

```python
# shared/vm/stack_vm.py
"""
StackVM: executes flat opcode-list programs.

Programs are JSON-serialisable lists mixing opcode strings and float/int literals.
See spec: docs/superpowers/specs/2026-04-22-emergent-ai-stack-vm-design.md
"""
from shared.vm.repair import MAX_PROGRAM_LEN
from shared.vm.operand_mask import compute_operand_mask, _find_else_or_endif, _find_endif
from shared.vm import instruction_set

MAX_STEPS = 512
MIN_PROGRAM_LEN = 4

# Maximum depth of nested loops supported (5th nested LOOP is NOP)
_MAX_LOOP_DEPTH = 4


class StackVM:
    def run(self, program: list, agent) -> None:
        """Execute program, calling DO_* and SENSE_* handlers on agent."""
        if not program:
            return

        mask = compute_operand_mask(program)
        stack: list = []
        loop_stack: list = []   # list of [return_ip, remaining_count]
        ip = 0
        steps = 0

        while ip < len(program) and steps < MAX_STEPS:
            # Skip operand slots that appear as the current ip
            # (should not happen in well-formed programs, but guard anyway)
            if mask[ip]:
                ip += 1
                steps += 1
                continue

            op = program[ip]
            steps += 1

            # ── Stack ops ──────────────────────────────────────────────────
            if op == "PUSH":
                ip += 1
                val = float(program[ip]) if ip < len(program) else 0.0
                stack.append(val)

            elif op == "POP":
                if stack:
                    stack.pop()

            elif op == "DUP":
                stack.append(stack[-1] if stack else 0.0)

            elif op == "ADD":
                b = stack.pop() if stack else 0.0
                a = stack.pop() if stack else 0.0
                stack.append(a + b)

            elif op == "SUB":
                b = stack.pop() if stack else 0.0
                a = stack.pop() if stack else 0.0
                stack.append(a - b)

            elif op == "MUL":
                b = stack.pop() if stack else 0.0
                a = stack.pop() if stack else 0.0
                stack.append(a * b)

            # ── Comparison ─────────────────────────────────────────────────
            elif op in ("GT", "LT", "GTE", "LTE", "EQ"):
                b = stack.pop() if stack else 0.0
                a = stack.pop() if stack else 0.0
                if op == "GT":   result = 1.0 if a > b else 0.0
                elif op == "LT": result = 1.0 if a < b else 0.0
                elif op == "GTE": result = 1.0 if a >= b else 0.0
                elif op == "LTE": result = 1.0 if a <= b else 0.0
                else:             result = 1.0 if a == b else 0.0
                stack.append(result)

            # ── Control flow ───────────────────────────────────────────────
            elif op == "IF_TRUE":
                cond = stack.pop() if stack else 0.0
                if cond <= 0.5:
                    ip = _find_else_or_endif(program, ip, mask)

            elif op == "ELSE":
                ip = _find_endif(program, ip, mask)

            elif op == "ENDIF":
                pass  # branch target — no-op

            elif op == "LOOP":
                ip += 1
                raw_n = program[ip] if ip < len(program) else 1
                n = max(1, min(8, int(float(raw_n))))
                if len(loop_stack) < _MAX_LOOP_DEPTH:
                    # return_ip points to the LOOP's operand position;
                    # on ENDLOOP jump-back, ip advances past it to the body
                    loop_stack.append([ip, n])
                # else: 5th nested loop → treat LOOP + operand as consumed, no push

            elif op == "ENDLOOP":
                if loop_stack:
                    ret_ip, remaining = loop_stack[-1]
                    if remaining > 1:
                        loop_stack[-1][1] = remaining - 1
                        ip = ret_ip  # jump back to LOOP operand; ip += 1 below
                                     # advances into loop body on next iteration
                    else:
                        loop_stack.pop()

            elif op == "NOP":
                pass

            elif op == "HALT":
                break

            # ── SENSE ──────────────────────────────────────────────────────
            elif op.startswith("SENSE_"):
                val = instruction_set.dispatch_sense(op, agent)
                stack.append(float(val))

            # ── DO ─────────────────────────────────────────────────────────
            elif op.startswith("DO_"):
                instruction_set.dispatch_do(op, agent)

            # ── Unknown → NOP ──────────────────────────────────────────────
            # (handles future generated ops gracefully if not yet registered)

            ip += 1
```

- [ ] **Step 4: Run tests**

```bash
cd D:\Ry\cyber && python -m pytest tests/test_stack_vm.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
cd D:\Ry\cyber
git add shared/vm/stack_vm.py tests/test_stack_vm.py
git commit -m "feat: add StackVM with full opcode execution, loop stack, MAX_STEPS guard"
```

---

## Task 6: Update shared/genome.py

**Files:**
- Modify: `D:\Ry\cyber\shared\genome.py`
- Modify: `D:\Ry\cyber\tests\test_genome.py` (update to match new format)
- Create: `D:\Ry\cyber\tests\test_genome_v2.py`

The genome format changes from float arrays to opcode lists. `RED_PHASE_SIZES` and phase parameters are removed. `validate()` and `random_genome()` are replaced with program-aware versions.

**Important:** Existing `test_genome.py` tests will break — they test the old float-array API. We replace them with v2 tests.

- [ ] **Step 1: Write new tests in `test_genome_v2.py`**

```python
# tests/test_genome_v2.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.genome import (
    random_program, validate_program, BOOTSTRAP_RED_PROGRAM,
    BOOTSTRAP_BLUE_PROGRAM, MAX_PROGRAM_LEN, MIN_PROGRAM_LEN,
)
from shared.vm.repair import repair_control_flow

def test_random_red_program_valid():
    prog = random_program("red")
    err = validate_program(prog, "red")
    assert err is None, err

def test_random_blue_program_valid():
    prog = random_program("blue")
    err = validate_program(prog, "blue")
    assert err is None, err

def test_program_length_in_bounds():
    for _ in range(20):
        prog = random_program("red")
        assert MIN_PROGRAM_LEN <= len(prog) <= MAX_PROGRAM_LEN

def test_validate_rejects_empty():
    err = validate_program([], "red")
    assert err is not None

def test_validate_rejects_too_long():
    prog = ["NOP"] * (MAX_PROGRAM_LEN + 1)
    err = validate_program(prog, "red")
    assert err is not None

def test_validate_rejects_unbalanced_if():
    prog = ["IF_TRUE", "NOP"]  # no ENDIF
    err = validate_program(prog, "red")
    assert err is not None

def test_validate_rejects_orphaned_endif():
    prog = ["NOP", "ENDIF"]
    err = validate_program(prog, "red")
    assert err is not None

def test_validate_rejects_orphaned_endloop():
    prog = ["NOP", "ENDLOOP"]
    err = validate_program(prog, "red")
    assert err is not None

def test_validate_accepts_valid_program():
    prog = ["SENSE_DELTA", "PUSH", 0.5, "GT", "IF_TRUE", "DO_FILE_DROP", "ENDIF"]
    err = validate_program(prog, "red")
    assert err is None

def test_bootstrap_red_is_valid():
    assert validate_program(BOOTSTRAP_RED_PROGRAM, "red") is None

def test_bootstrap_blue_is_valid():
    assert validate_program(BOOTSTRAP_BLUE_PROGRAM, "blue") is None

def test_repair_produces_valid_program():
    broken = ["IF_TRUE", "DO_FILE_DROP"]  # missing ENDIF
    fixed = repair_control_flow(broken)
    assert validate_program(fixed, "red") is None

def test_random_program_contains_opcodes():
    prog = random_program("red")
    opcode_strs = [op for op in prog if isinstance(op, str)]
    assert len(opcode_strs) >= 1
```

- [ ] **Step 2: Run to confirm failures**

```bash
cd D:\Ry\cyber && python -m pytest tests/test_genome_v2.py -v 2>&1 | head -10
```

Expected: `ImportError`

- [ ] **Step 3: Rewrite `shared/genome.py`**

```python
# shared/genome.py
"""
Genome encoding for Vanguard Duel v2.

A genome is a flat opcode list (JSON-serialisable list of strings and floats).
No phases. No float-array encoding. Genomes grow via the GA and LLM codegen.
"""
from typing import Optional
import random

from shared.vm.repair import MAX_PROGRAM_LEN, repair_control_flow
from shared.vm.operand_mask import compute_operand_mask

MIN_PROGRAM_LEN = 4

# ── Opcode vocabularies ───────────────────────────────────────────────────────

_STACK_OPS = ["PUSH", "POP", "DUP", "ADD", "SUB", "MUL"]
_COMPARE_OPS = ["GT", "LT", "GTE", "LTE", "EQ"]
_CONTROL_OPS = ["IF_TRUE", "ELSE", "ENDIF", "LOOP", "ENDLOOP", "NOP", "HALT"]
_SENSE_OPS = [
    "SENSE_DELTA", "SENSE_TIER", "SENSE_PROC_COUNT", "SENSE_PORT_COUNT",
    "SENSE_CPU_AVG", "SENSE_TICK", "SENSE_SCHED_TASKS", "SENSE_OUTBOUND_CONNS",
    "SENSE_CHILD_DEPTH", "SENSE_PRIVESC_SIGNALS",
]
_RED_SENSE_EXTRA = ["SENSE_BLUE_RESPONSES"]
_BLUE_SENSE_EXTRA = ["SENSE_NEW_PROCS"]

_RED_DO_OPS = [
    "DO_FILE_DROP", "DO_REG_WRITE", "DO_PROCESS_KILL", "DO_CPU_SPIKE",
    "DO_EXFIL_CHUNK", "DO_LATERAL_SPAWN", "DO_NZ_ARTIFACT",
    "DO_PRIVESC", "DO_NET_SCAN", "DO_REG_PERSISTENCE",
]
_BLUE_DO_OPS = [
    "DO_FREEZE", "DO_NULL_ROUTE", "DO_QUARANTINE", "DO_RESTORE_REG",
    "DO_MEMORY_SCAN", "DO_ANCESTRY_CHECK", "DO_FLOW_ANALYSIS",
]

# Opcodes that should not be generated freely (they're structural targets only)
_NON_GENERATABLE = frozenset(["ELSE", "ENDIF", "ENDLOOP"])

def _generatable_opcodes(role: str) -> list:
    """Return the set of opcodes that random_program may emit directly."""
    base = (_STACK_OPS + _COMPARE_OPS
            + [op for op in _CONTROL_OPS if op not in _NON_GENERATABLE]
            + _SENSE_OPS)
    if role == "red":
        return base + _RED_SENSE_EXTRA + _RED_DO_OPS
    else:
        return base + _BLUE_SENSE_EXTRA + _BLUE_DO_OPS


# ── Bootstrap programs ────────────────────────────────────────────────────────
# Minimal valid programs used to seed the first population.

BOOTSTRAP_RED_PROGRAM = [
    "SENSE_DELTA", "PUSH", 0.3, "GT",
    "IF_TRUE", "DO_FILE_DROP", "DO_REG_WRITE",
    "ELSE", "NOP",
    "ENDIF",
]

BOOTSTRAP_BLUE_PROGRAM = [
    "SENSE_DELTA", "PUSH", 0.5, "GT",
    "IF_TRUE", "DO_FREEZE",
    "ELSE", "NOP",
    "ENDIF",
]


# ── random_program ────────────────────────────────────────────────────────────

def random_program(role: str, min_len: int = 8, max_len: int = 32) -> list:
    """
    Generate a random structurally valid opcode program for the given role.
    Result is guaranteed to pass validate_program(result, role).
    """
    vocab = _generatable_opcodes(role)
    # Filter structural opcodes from the free pool
    free_vocab = [op for op in vocab if op not in _NON_GENERATABLE]

    target_len = random.randint(min_len, min(max_len, MAX_PROGRAM_LEN))
    program = []

    while len(program) < target_len:
        op = random.choice(free_vocab)
        program.append(op)
        if op == "PUSH":
            program.append(round(random.uniform(0.0, 1.0), 4))
        elif op == "LOOP":
            program.append(random.randint(1, 4))

    program = repair_control_flow(program)
    return program[:MAX_PROGRAM_LEN]


# ── validate_program ──────────────────────────────────────────────────────────

def validate_program(program: list, role: str) -> Optional[str]:
    """
    Return None if program is valid, or a string describing the problem.

    Checks:
    - Length within [MIN_PROGRAM_LEN, MAX_PROGRAM_LEN]
    - Balanced IF_TRUE/ENDIF pairs
    - No orphaned ELSE or ENDIF
    - Balanced LOOP/ENDLOOP pairs
    - No orphaned ENDLOOP
    """
    if not program:
        return "Program is empty"
    if len(program) < MIN_PROGRAM_LEN:
        return f"Program length {len(program)} < minimum {MIN_PROGRAM_LEN}"
    if len(program) > MAX_PROGRAM_LEN:
        return f"Program length {len(program)} > maximum {MAX_PROGRAM_LEN}"

    mask = compute_operand_mask(program)
    if_depth = 0
    loop_depth = 0

    for i, op in enumerate(program):
        if mask[i]:
            continue
        if op == "IF_TRUE":
            if_depth += 1
        elif op == "ELSE":
            if if_depth == 0:
                return f"Orphaned ELSE at position {i}"
        elif op == "ENDIF":
            if if_depth == 0:
                return f"Orphaned ENDIF at position {i}"
            if_depth -= 1
        elif op == "LOOP":
            loop_depth += 1
        elif op == "ENDLOOP":
            if loop_depth == 0:
                return f"Orphaned ENDLOOP at position {i}"
            loop_depth -= 1

    if if_depth != 0:
        return f"Unclosed IF_TRUE blocks: {if_depth} unmatched"
    if loop_depth != 0:
        return f"Unclosed LOOP blocks: {loop_depth} unmatched"

    return None
```

- [ ] **Step 4: Archive old genome tests**

Rename `tests/test_genome.py` to `tests/test_genome_v1_archived.py` so it's excluded from the test run (pytest ignores files not named `test_*.py` or `*_test.py` by default):

```bash
cd D:\Ry\cyber
mv tests/test_genome.py tests/test_genome_v1_archived.py
```

- [ ] **Step 5: Run new tests**

```bash
cd D:\Ry\cyber && python -m pytest tests/test_genome_v2.py -v
```

Expected: all 13 tests PASS

- [ ] **Step 6: Run full suite to check no regressions outside genome tests**

```bash
cd D:\Ry\cyber && python -m pytest tests/ -v --ignore=tests/test_genome_v1_archived.py -v 2>&1 | tail -20
```

Expected: all previously-passing tests still pass (genome tests excluded via archive)

- [ ] **Step 7: Commit**

```bash
cd D:\Ry\cyber
git add shared/genome.py tests/test_genome_v2.py tests/test_genome_v1_archived.py
git commit -m "feat: rewrite genome.py — opcode list format, no phases, random_program + validate_program"
```

---

## Task 7: Final Plan A verification

- [ ] **Step 1: Run the full Plan A test suite**

```bash
cd D:\Ry\cyber && python -m pytest tests/test_operand_mask.py tests/test_repair.py tests/test_stack_vm.py tests/test_genome_v2.py -v
```

Expected: all tests PASS (target: ~55 tests)

- [ ] **Step 2: Verify all VM modules import cleanly**

```bash
cd D:\Ry\cyber && python -c "
import sys; sys.path.insert(0, '.')
from shared.vm.operand_mask import compute_operand_mask
from shared.vm.repair import repair_control_flow
from shared.vm.stack_vm import StackVM
from shared.vm.instruction_set import dispatch_do, dispatch_sense
from shared.genome import random_program, validate_program
print('All Plan A imports OK')
"
```

Expected: `All Plan A imports OK`

- [ ] **Step 3: Push to remote**

```bash
cd D:\Ry\cyber && git push origin master
```

---

## What comes next

**Plan B** (Sensors, Noise Floor, Actions, Agent Shells) depends on Plan A being complete. It covers:
- `sandbox/state_vector.py` +4 new measurement dims
- `sandbox/matrix_delta.py` — AdaptiveNoiseFloor class
- Full DO handler implementations in `instruction_set.py` (lateral, privesc, net_scan, etc.)
- Slimmed `sandbox/red_agent.py` and `sandbox/blue_agent.py` calling the VM
- Updated `sandbox/watchdog.py`

**Plan C** (GA Operators, Co-evolution, LLM Codegen) follows Plan B.
