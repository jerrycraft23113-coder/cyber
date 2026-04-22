# Emergent AI — Stack VM + LLM Codegen Design

**Date:** 2026-04-22
**Project:** Vanguard Duel (`D:\Ry\cyber\`)

---

## Goal

Replace hardcoded Red/Blue action lists with **stack-program genomes** evolved by the GA, and add an **LLM codegen loop** that generates brand-new primitive opcodes from telemetry after every 10 generations. Neither attack patterns nor defense patterns are ever hardcoded again — they emerge from selection pressure and LLM-driven primitive generation.

---

## Background

The existing system (`v1`) has:
- Red genome: 9 floats encoding action parameters (file drop rate, reg key count, etc.)
- Blue genome: 8 floats encoding response weights and thresholds
- Phase unlock: stealth → disruption → exfil with genome expansion
- Fixed action vocabulary: hardcoded methods in `red_agent.py` / `blue_agent.py`

**Problems this design solves:**
- Adding a new capability requires editing multiple files and incrementing hardcoded gene counts
- Agents can't adapt strategy mid-round (no conditionals, no sensing)
- No mechanism for genuinely new behaviors to emerge

---

## Architecture Overview

```
shared/
  vm/
    stack_vm.py          ← executes opcode programs
    instruction_set.py   ← all opcodes + DO handlers, auto-loads generated/
    generated/           ← LLM-written primitives committed to repo
      red_gen_001.py
      blue_gen_001.py
      ...
  genome.py              ← updated: genome = opcode list, no phases

sandbox/
  red_agent.py           ← slim shell: load config → vm.run(program) → heartbeat
  blue_agent.py          ← slim shell: load config → vm.run(program) → heartbeat
  state_vector.py        ← +4 new measurement dims
  matrix_delta.py        ← + AdaptiveNoiseFloor class

host/
  llm_codegen.py         ← Claude API codegen loop
  ga_engine.py           ← crossover + mutation updated for opcode lists
  coevolution.py         ← simplified (phase unlock removed)
  run_simulation.py      ← triggers llm_codegen every 10 generations
```

---

## Genome Format

The genome is no longer a flat float array. It is a **JSON opcode list**, maximum 64 elements:

```json
["SENSE_DELTA", "PUSH", 0.3, "GT",
 "IF_TRUE",
   "DO_LATERAL_SPAWN", "DO_NET_SCAN",
 "ELSE",
   "DO_FILE_DROP", "PUSH", 0.8, "DO_REG_WRITE",
 "ENDIF",
 "SENSE_TIER", "PUSH", 2.0, "GTE",
 "IF_TRUE", "DO_PRIVESC", "ENDIF"]
```

- Parameters are **PUSH literals** embedded in the program, not separate gene slots
- Crossover splices at a random index and repairs control flow
- Mutation can change opcodes, adjust PUSH literals, insert, or delete

**Constants:**
- `MAX_PROGRAM_LEN = 64` — hard cap, enforced after every crossover/mutation
- `MIN_PROGRAM_LEN = 4` — prevents degenerate empty programs

---

## Instruction Set (`shared/vm/instruction_set.py`)

### SENSE — push system state onto stack

| Opcode | Pushes |
|--------|--------|
| `SENSE_DELTA` | current noise-adjusted delta (float) |
| `SENSE_TIER` | tier as int: NOMINAL=0, WATCH=1, ALERT=2, CRITICAL=3 |
| `SENSE_PROC_COUNT` | current process count |
| `SENSE_PORT_COUNT` | current listening port count |
| `SENSE_CPU_AVG` | mean CPU% across cores |
| `SENSE_TICK` | current tick number |
| `SENSE_SCHED_TASKS` | scheduled task count |
| `SENSE_OUTBOUND_CONNS` | ESTABLISHED non-loopback connections |
| `SENSE_CHILD_DEPTH` | max process tree depth from t0_pids |
| `SENSE_PRIVESC_SIGNALS` | privilege escalation attempt counter |
| `SENSE_BLUE_RESPONSES` | Blue response count (Red only) |
| `SENSE_NEW_PROCS` | processes spawned since T=0 (Blue only) |

### Stack Ops

`PUSH <float>` — push literal (consumes next element as operand)
`POP` — discard top
`DUP` — duplicate top
`ADD`, `SUB`, `MUL` — binary arithmetic on top two

### Comparison — pop two, push 1.0 (true) or 0.0 (false)

`GT`, `LT`, `GTE`, `LTE`, `EQ`

### Control Flow

| Opcode | Behaviour |
|--------|-----------|
| `IF_TRUE` | pop; if ≤ 0.5, skip to matching `ELSE` or `ENDIF` |
| `ELSE` | skip to matching `ENDIF` |
| `ENDIF` | no-op (branch target) |
| `LOOP <n>` | repeat enclosed block n times (n is next element, capped at 8) |
| `ENDLOOP` | loop boundary |
| `NOP` | no-op (used as padding / mutation filler) |
| `HALT` | stop program immediately |

### Red DO ops (actions)

`DO_FILE_DROP`, `DO_REG_WRITE`, `DO_PROCESS_KILL`, `DO_CPU_SPIKE`,
`DO_EXFIL_CHUNK`, `DO_LATERAL_SPAWN`, `DO_NZ_ARTIFACT`,
`DO_PRIVESC`, `DO_NET_SCAN`, `DO_REG_PERSISTENCE`

### Blue DO ops (actions)

`DO_FREEZE`, `DO_NULL_ROUTE`, `DO_QUARANTINE`, `DO_RESTORE_REG`,
`DO_MEMORY_SCAN`, `DO_ANCESTRY_CHECK`, `DO_FLOW_ANALYSIS`

### LLM-generated ops

Any `DO_*` or `SENSE_*` opcode defined in `shared/vm/generated/*.py` is auto-registered at VM startup. No other file changes required.

---

## Stack VM (`shared/vm/stack_vm.py`)

```python
MAX_PROGRAM_LEN = 64
MAX_STEPS = 512  # prevent infinite loops

class StackVM:
    def run(self, program: list, agent) -> None:
        stack = []
        ip = 0
        steps = 0
        while ip < len(program) and steps < MAX_STEPS:
            op = program[ip]
            if op == "PUSH":
                ip += 1
                stack.append(float(program[ip]))
            elif op == "SENSE_DELTA":
                stack.append(agent.current_delta)
            elif op == "GT":
                b, a = _pop2(stack)
                stack.append(1.0 if a > b else 0.0)
            elif op == "IF_TRUE":
                if not (_pop1(stack) > 0.5):
                    ip = _find_else_or_endif(program, ip)
            elif op == "DO_LATERAL_SPAWN":
                instruction_set.do_lateral_spawn(agent)
            # ... all opcodes handled
            ip += 1
            steps += 1
```

**Safety guarantees:**
- `MAX_STEPS = 512` — no infinite loops possible
- Stack underflow returns 0.0 silently — programs never crash the round
- Unknown opcodes are treated as `NOP` — LLM-generated ops gracefully degrade if missing

---

## New Red Actions

### `DO_LATERAL_SPAWN`
Spawns a child Python process (`subprocess.Popen`) and writes a C2-style artifact to `nz/lateral_<id>.json`. Detectable via `child_depth` state dim and NZ file count.

### `DO_NZ_ARTIFACT`
Writes a staging file to `nz/c2_<id>.json` simulating a C2 callback beacon. Blue can detect via NZ file scanning.

### `DO_PRIVESC`
Three real attempts in sequence, each silently failing on access denial:
1. `fodhelper` UAC bypass: writes to `HKCU\Software\Classes\ms-settings\shell\open\command`
2. Token impersonation: `ctypes.windll.advapi32.DuplicateTokenEx` on a SYSTEM process token
3. HKLM write: attempts `winreg.CreateKey(HKEY_LOCAL_MACHINE, "SOFTWARE\\VanguardPrivEsc")`

Increments `nz/privesc_log.json` counter regardless of success.

### `DO_NET_SCAN`
`socket.connect_ex` on 10 randomly chosen RFC-1918 IPs, ports 445 and 3389. Generates ESTABLISHED connection attempts visible to `SENSE_OUTBOUND_CONNS`.

### `DO_REG_PERSISTENCE`
Writes a value to `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`. Survives process restarts. Detectable via `reg_hash` state dim change.

---

## New Blue Actions

### `DO_MEMORY_SCAN`
Uses `ctypes.windll.kernel32.ReadProcessMemory` on the newest non-baseline process. Searches for known payload byte patterns (`b"red_payload"`, `b"VanguardTest"`). Findings written to `nz/blue_detections.json`.

### `DO_ANCESTRY_CHECK`
Walks `psutil.Process.parent()` chain up to 4 levels for each new process. Flags processes whose ancestry includes `cmd.exe` or `powershell.exe` spawned by a non-system parent. Flags written to `nz/blue_detections.json`.

### `DO_FLOW_ANALYSIS`
For each process spawned since T=0, counts ESTABLISHED outbound connections via `psutil.net_connections()`. Flags any process with ≥ 3 connections as a C2 candidate. Result pushed to `nz/blue_detections.json`.

---

## Adaptive Noise Floor (`sandbox/matrix_delta.py`)

```python
class AdaptiveNoiseFloor:
    def __init__(self, window: int = 20):
        self._samples = collections.deque(maxlen=window)
        self._nominal_streak = 0
        self._ticks_since_recal = 0
        self.floor: float = 0.0

    def update(self, delta_raw: float, tier: str, settle_ticks: int = 10) -> None:
        self._samples.append(delta_raw)
        self._ticks_since_recal += 1
        if tier == "NOMINAL":
            self._nominal_streak += 1
        else:
            self._nominal_streak = 0

        # Signal trigger: NOMINAL for settle_ticks consecutive ticks
        if self._nominal_streak >= settle_ticks:
            self._recalibrate()
        # Time fallback: every 150 ticks
        elif self._ticks_since_recal >= 150:
            self._recalibrate()

    def _recalibrate(self) -> None:
        if self._samples:
            self.floor = float(np.mean(self._samples))
        self._nominal_streak = 0
        self._ticks_since_recal = 0
```

`settle_ticks` is read from the Blue program's runtime context (a constant initially, later a SENSE-able value).

---

## State Vector Expansion (`sandbox/state_vector.py`)

Four new measurement functions:

```python
def count_scheduled_tasks() -> int:
    """Count scheduled tasks via schtasks /query."""
    try:
        r = subprocess.run(["schtasks", "/query", "/fo", "csv"],
                           capture_output=True, text=True, timeout=5)
        return max(0, r.stdout.count("\n") - 2)  # subtract header lines
    except Exception:
        return 0

def count_outbound_connections() -> int:
    """Count ESTABLISHED non-loopback outbound connections."""
    return sum(
        1 for c in psutil.net_connections()
        if c.status == "ESTABLISHED"
        and c.raddr
        and not c.raddr.ip.startswith("127.")
    )

def measure_child_process_depth(t0_pids: set) -> int:
    """Max depth of process ancestry tree rooted outside t0_pids."""
    max_depth = 0
    for proc in psutil.process_iter(["pid", "ppid"]):
        if proc.pid in t0_pids:
            continue
        depth, p = 0, proc
        try:
            while p and p.pid not in t0_pids:
                p = p.parent()
                depth += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        max_depth = max(max_depth, depth)
    return max_depth

def read_privesc_signals(nz: Path) -> int:
    """Read Red's privilege escalation attempt counter from NZ."""
    try:
        return json.loads((nz / "privesc_log.json").read_text()).get("count", 0)
    except (FileNotFoundError, json.JSONDecodeError):
        return 0
```

Updated `build_state_vector()` appends these four after CPU cores.

---

## LLM Codegen (`host/llm_codegen.py`)

Runs on the **host** after every 10 generations. Never runs inside WSB.

### Inputs
- Last generation's `ga_history.jsonl` entries (outcomes, fitness scores, peak deltas)
- Current instruction set (list of registered opcodes)
- Role to generate for (`"red"` or `"blue"`, alternates each call)

### Process
1. Read last 10 rounds of telemetry
2. Identify winning patterns (what opcode sequences correlated with high fitness)
3. Call Claude API: *"Given these Red winning strategies and Blue's current defenses, generate one new Blue detection primitive that would counter the dominant Red pattern."*
4. Parse the response: opcode name + Python function body
5. Validate: function must accept `(agent)` signature, no imports outside whitelist
6. Write to `shared/vm/generated/blue_gen_<N>.py`
7. Commit to git

### Safety whitelist
Generated code may only import: `os`, `subprocess`, `json`, `random`, `time`, `pathlib`, `psutil`, `ctypes`, `socket`, `winreg`. Any other import causes the generated file to be rejected and regenerated.

### Output format expected from LLM
```python
# OPCODE: DO_ARP_SWEEP
# ROLE: red
# DESCRIPTION: Scan local ARP table to enumerate reachable hosts
def do_arp_sweep(agent):
    result = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=5)
    (agent.nz / "arp_scan.txt").write_text(result.stdout)
```

---

## GA Engine Updates (`host/ga_engine.py`)

### `random_program(role, min_len=8, max_len=32)`
Generates a random valid opcode list. Ensures balanced IF/ENDIF pairs and valid PUSH operands.

### `crossover(prog_a, prog_b)`
Single-point splice + `repair_control_flow()` + truncate to `MAX_PROGRAM_LEN`.

### `mutate(program, win_rate)`
Pick one mutation type (weighted by win_rate — lower win_rate = more aggressive mutation):
- **Replace** random opcode with random valid opcode
- **Adjust** random PUSH literal (Gaussian noise)
- **Insert** random opcode at random position
- **Delete** random non-structural opcode
- **Swap** two opcodes

### `repair_control_flow(program)`
Scans for unmatched `IF_TRUE`/`ENDIF`/`ELSE`/`LOOP`/`ENDLOOP`. Removes orphaned control flow opcodes. Ensures program is always syntactically valid.

---

## Co-evolution Simplification (`host/coevolution.py`)

Removed:
- `PHASE_UNLOCK` state
- `expand_red_genome()` method
- Phase-based genome size logic

Remaining state machine: `EVOLVE_RED → EVOLVE_BLUE → DONE`

Red exit condition: win rate ≥ 60% over last 20 competitive rounds → freeze Red champion, switch to `EVOLVE_BLUE`.

Blue exit condition (was "phase unlock"): Blue win rate ≥ 80% over last 20 rounds with ≥ 3 distinct programs (pairwise edit distance > 5 opcodes) → freeze Blue champion → `DONE`.

---

## Testing Strategy

| File | Key tests |
|------|-----------|
| `test_stack_vm.py` | PUSH/POP/DUP, GT/LT, IF_TRUE branch taken/skipped, LOOP executes N times, MAX_STEPS halt, stack underflow safe, unknown opcode = NOP |
| `test_instruction_set.py` | each DO_* handler callable, SENSE_* returns float, generated/ plugins auto-register |
| `test_ga_engine_v2.py` | random_program valid, crossover produces balanced program, mutate stays within MAX_PROGRAM_LEN, repair_control_flow fixes unmatched IFs |
| `test_state_vector_v2.py` | count_scheduled_tasks returns int, count_outbound_connections returns int, measure_child_process_depth returns int |
| `test_matrix_delta_v2.py` | AdaptiveNoiseFloor recalibrates after settle_ticks NOMINAL, recalibrates after 150 ticks, floor updates correctly |
| `test_llm_codegen.py` | import whitelist validation, output format parsing, file written to generated/ |

---

## Migration from v1

1. Existing `ga_history.jsonl` checkpoints are incompatible (float arrays → opcode lists). On first run with v2, checkpoint is discarded and evolution restarts.
2. Existing tests (`test_genome.py`, `test_red_agent.py`, etc.) are updated in-place — the files they test change.
3. `arena.wsb` unchanged.
4. Neutral zone structure unchanged (same file names, same JSON shapes).

---

## Open Questions / Future Work

- **Program length pressure**: without explicit length penalisation, programs may bloat to 64 opcodes. Consider adding a length term to fitness scoring.
- **Generated code review**: currently auto-committed. Could add a human-review gate before generated primitives become available to the GA.
- **Cross-round memory**: programs currently have no persistent state across ticks (only the stack). A `STORE`/`LOAD` opcode pair could enable mid-round memory.
