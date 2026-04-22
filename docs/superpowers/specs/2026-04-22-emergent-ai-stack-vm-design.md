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
  llm_codegen.py         ← Claude API codegen loop (runs on host, never in WSB)
  ga_engine.py           ← crossover + mutation updated for opcode lists
  coevolution.py         ← simplified (phase unlock removed)
  run_simulation.py      ← triggers llm_codegen every 10 generations (blocking)
```

---

## Genome Format

The genome is no longer a flat float array. It is a **JSON opcode list**, maximum 64 elements:

```json
["SENSE_DELTA", "PUSH", 0.3, "GT",
 "IF_TRUE",
   "DO_LATERAL_SPAWN", "DO_NET_SCAN",
 "ELSE",
   "DO_FILE_DROP", "DO_REG_WRITE",
 "ENDIF",
 "SENSE_TIER", "PUSH", 2.0, "GTE",
 "IF_TRUE", "DO_PRIVESC", "ENDIF"]
```

**Key rule: DO ops never consume stack values.** They read from `agent` state only. A `PUSH` before a `DO_*` opcode is independent — it leaves a value on the stack which a subsequent comparison might use, but the `DO_*` ignores the stack entirely. This keeps DO handler signatures simple (`def do_X(agent) -> None`) and prevents mutation from accidentally wiring the wrong stack value into an action.

**Constants:**
- `MAX_PROGRAM_LEN = 64` — hard cap, enforced after every crossover/mutation
- `MIN_PROGRAM_LEN = 4` — prevents degenerate empty programs
- `MAX_STEPS = 512` — total instruction steps per VM run; hitting this is a silent HALT

---

## Opcode vs Operand Slots

The program is a flat list mixing opcode strings and literal float/int values. Two opcodes consume the **next element** as an inline operand:

| Opcode | Consumes next element as |
|--------|--------------------------|
| `PUSH` | float literal pushed onto stack |
| `LOOP` | int iteration count (clamped to [1, 8]) |

A **position mask** is computed once before any mutation or branch-scanning:

```python
def compute_operand_mask(program: list) -> list[bool]:
    mask = [False] * len(program)
    for i, op in enumerate(program):
        if op in ("PUSH", "LOOP") and i + 1 < len(program):
            mask[i + 1] = True
    return mask
```

All functions that scan for branch targets (`_find_else_or_endif`, `_find_endloop`) must skip operand slots using this mask. Mutation must never replace an operand slot with an opcode string or vice-versa — it operates only on non-operand positions for structural mutations, and only on operand positions for value adjustments.

---

## Agent Contract

The VM's `run(program, agent)` method requires the agent to expose these attributes, populated by the agent before calling `run()` each tick:

```python
class AgentContext:
    # Set by agent each tick before calling vm.run()
    current_delta: float          # noise-adjusted matrix delta
    current_tier: int             # NOMINAL=0, WATCH=1, ALERT=2, CRITICAL=3
    current_tick: int             # tick counter since round start
    t0_pids: set                  # PIDs present at T=0
    nz: Path                      # neutral zone path
    role: str                     # "red" or "blue"

    # Snapshotted ONCE at the start of each vm.run() call
    # (not re-read mid-program — ensures SENSE consistency within one tick)
    snap_proc_count: int
    snap_outbound_conns: int
    snap_child_depth: int
    snap_sched_tasks: int
    snap_privesc_signals: int
    snap_cpu_avg: float
    snap_new_procs: int           # processes spawned since T=0 (Blue uses this)
    snap_blue_responses: int      # Blue's response counter (Red reads via NZ heartbeat)
```

`red_agent.py` and `blue_agent.py` populate these fields by reading `heartbeat.json` and calling the state_vector functions before invoking `vm.run()`.

---

## Instruction Set (`shared/vm/instruction_set.py`)

### SENSE — push snapshotted system state onto stack

| Opcode | Pushes | Role |
|--------|--------|------|
| `SENSE_DELTA` | `agent.current_delta` | both |
| `SENSE_TIER` | `agent.current_tier` (0–3) | both |
| `SENSE_PROC_COUNT` | `agent.snap_proc_count` | both |
| `SENSE_PORT_COUNT` | (computed from psutil at snapshot) | both |
| `SENSE_CPU_AVG` | `agent.snap_cpu_avg` | both |
| `SENSE_TICK` | `agent.current_tick` | both |
| `SENSE_SCHED_TASKS` | `agent.snap_sched_tasks` | both |
| `SENSE_OUTBOUND_CONNS` | `agent.snap_outbound_conns` | both |
| `SENSE_CHILD_DEPTH` | `agent.snap_child_depth` | both |
| `SENSE_PRIVESC_SIGNALS` | `agent.snap_privesc_signals` | both |
| `SENSE_BLUE_RESPONSES` | `agent.snap_blue_responses` | Red only |
| `SENSE_NEW_PROCS` | `agent.snap_new_procs` | Blue only |

**Role-gating:** If a Red program contains `SENSE_NEW_PROCS` (Blue-only) or vice-versa, the opcode pushes `0.0` silently. Programs are never rejected for role violations — the GA learns that these ops are useless in the wrong context.

### Stack Ops

`PUSH <float>` — inline operand pushed onto stack
`POP` — discard top (stack underflow → no-op)
`DUP` — duplicate top (underflow → push 0.0)
`ADD`, `SUB`, `MUL` — pop two, push result (underflow → use 0.0)

### Comparison — pop two, push 1.0 (true) or 0.0 (false)

`GT`, `LT`, `GTE`, `LTE`, `EQ`
Stack underflow (fewer than 2 values): pop what's available, treat missing as 0.0.

### Control Flow

| Opcode | Behaviour |
|--------|-----------|
| `IF_TRUE` | pop top; if ≤ 0.5, skip forward to matching `ELSE` or `ENDIF` |
| `ELSE` | skip forward to matching `ENDIF` |
| `ENDIF` | no-op (branch target) |
| `LOOP <n>` | `n` is inline operand (next element), clamped to [1, 8], rounded to int. Push `(return_ip, n)` onto loop stack. |
| `ENDLOOP` | decrement top of loop stack; if remaining > 0, jump to `return_ip + 2`; else pop loop stack |
| `NOP` | no-op |
| `HALT` | stop immediately, regardless of loop/if nesting |

**Nested loops:** The VM maintains a separate loop stack (independent of the value stack) as a list of `(return_ip, remaining_count)` tuples. Up to 4 nested loops are supported; a 5th `LOOP` is treated as `NOP`.

**MAX_STEPS:** When 512 steps are exhausted, the VM halts silently (same as `HALT`). No error, no partial state rollback.

### Red DO ops (v1 carryovers — implementations already in `red_agent.py`)

`DO_FILE_DROP` — drop random file to Desktop or AppData (gated by agent's genome, not stack)
`DO_REG_WRITE` — write values to HKCU or HKLM VanguardTest key
`DO_PROCESS_KILL` — kill a random non-baseline process
`DO_CPU_SPIKE` — spin daemon threads to spike CPU
`DO_EXFIL_CHUNK` — write random bytes to `nz/exfil/`

### Red DO ops (new)

`DO_LATERAL_SPAWN` — see §New Red Actions
`DO_NZ_ARTIFACT` — see §New Red Actions
`DO_PRIVESC` — see §New Red Actions
`DO_NET_SCAN` — see §New Red Actions
`DO_REG_PERSISTENCE` — see §New Red Actions

### Blue DO ops (v1 carryovers — implementations already in `blue_agent.py`)

`DO_FREEZE` — suspend newest non-baseline process
`DO_NULL_ROUTE` — activate/deactivate outbound firewall block
`DO_QUARANTINE` — move suspicious file to `nz/quarantine/`
`DO_RESTORE_REG` — delete Red's registry writes under monitored keys

### Blue DO ops (new)

`DO_MEMORY_SCAN` — see §New Blue Actions
`DO_ANCESTRY_CHECK` — see §New Blue Actions
`DO_FLOW_ANALYSIS` — see §New Blue Actions

### LLM-generated ops

Any `DO_*` or `SENSE_*` handler defined in `shared/vm/generated/*.py` is auto-registered at VM startup. Files are loaded in sorted filename order (`red_gen_001.py` before `red_gen_002.py`). An opcode name collision with an existing builtin causes the generated file to be skipped and an error logged — it does not overwrite builtins.

---

## Stack VM (`shared/vm/stack_vm.py`)

```python
MAX_PROGRAM_LEN = 64
MIN_PROGRAM_LEN = 4
MAX_STEPS = 512

class StackVM:
    def run(self, program: list, agent) -> None:
        mask = compute_operand_mask(program)
        stack: list[float] = []
        loop_stack: list[tuple] = []  # (return_ip, remaining_count)
        ip = 0
        steps = 0

        while ip < len(program) and steps < MAX_STEPS:
            op = program[ip]
            steps += 1

            if mask[ip]:           # operand slot — should never be executed directly
                ip += 1
                continue

            if op == "PUSH":
                ip += 1
                stack.append(float(program[ip]) if ip < len(program) else 0.0)
            elif op == "POP":
                if stack: stack.pop()
            elif op == "DUP":
                stack.append(stack[-1] if stack else 0.0)
            elif op == "ADD":
                b = stack.pop() if stack else 0.0
                a = stack.pop() if stack else 0.0
                stack.append(a + b)
            elif op == "GT":
                b = stack.pop() if stack else 0.0
                a = stack.pop() if stack else 0.0
                stack.append(1.0 if a > b else 0.0)
            # ... (all comparison ops follow same pattern)
            elif op == "IF_TRUE":
                cond = stack.pop() if stack else 0.0
                if cond <= 0.5:
                    ip = _find_else_or_endif(program, ip, mask)
            elif op == "ELSE":
                ip = _find_endif(program, ip, mask)
            elif op == "ENDIF":
                pass  # target only
            elif op == "LOOP":
                ip += 1
                n = max(1, min(8, int(float(program[ip])) if ip < len(program) else 1))
                if len(loop_stack) < 4:
                    loop_stack.append((ip, n))
                # else: treat as NOP (5th nested loop)
            elif op == "ENDLOOP":
                if loop_stack:
                    ret_ip, remaining = loop_stack[-1]
                    if remaining > 1:
                        loop_stack[-1] = (ret_ip, remaining - 1)
                        ip = ret_ip  # jump back to after LOOP's operand
                    else:
                        loop_stack.pop()
            elif op == "HALT":
                break
            elif op == "NOP":
                pass
            elif op.startswith("SENSE_"):
                stack.append(_do_sense(op, agent))
            elif op.startswith("DO_"):
                instruction_set.dispatch(op, agent)
            # unknown opcode → NOP (handles future generated ops gracefully)

            ip += 1
```

**`_find_else_or_endif(program, ip, mask)`** — scans forward from `ip`, counting nesting depth (each `IF_TRUE` increments, each `ENDIF` decrements). Skips operand slots using mask. Returns index of the matching `ELSE` or `ENDIF` at depth 0. Returns `len(program)` if not found (runs off end).

**`_find_endif(program, ip, mask)`** — same logic, stops only at `ENDIF` at depth 0.

---

## `repair_control_flow(program)` — Concrete Algorithm

Called after every crossover and mutation. Must never produce a program longer than `MAX_PROGRAM_LEN`.

```python
def repair_control_flow(program: list) -> list:
    mask = compute_operand_mask(program)

    # Pass 1: strip orphaned ELSE and ENDIF (those with no matching IF_TRUE)
    result = []
    if_depth = 0
    for i, op in enumerate(program):
        if mask[i]:
            result.append(op)  # operand slots always kept
            continue
        if op == "IF_TRUE":
            if_depth += 1
            result.append(op)
        elif op == "ELSE":
            if if_depth > 0:
                result.append(op)
            # orphaned ELSE → drop
        elif op == "ENDIF":
            if if_depth > 0:
                if_depth -= 1
                result.append(op)
            # orphaned ENDIF → drop
        else:
            result.append(op)

    # Pass 2: close any unclosed IF_TRUE blocks (append ENDIF for each)
    for _ in range(if_depth):
        if len(result) < MAX_PROGRAM_LEN:
            result.append("ENDIF")

    # Pass 3: strip orphaned ENDLOOP (those with no matching LOOP)
    final = []
    loop_depth = 0
    i = 0
    while i < len(result):
        op = result[i]
        if op == "LOOP":
            loop_depth += 1
            final.append(op)
            i += 1
            if i < len(result):  # append operand
                final.append(result[i])
        elif op == "ENDLOOP":
            if loop_depth > 0:
                loop_depth -= 1
                final.append(op)
            # orphaned ENDLOOP → drop
        else:
            final.append(op)
        i += 1

    # Pass 4: close unclosed LOOP blocks
    for _ in range(loop_depth):
        if len(final) < MAX_PROGRAM_LEN:
            final.append("ENDLOOP")

    return final[:MAX_PROGRAM_LEN]
```

**LOOP `n = 0` or negative:** `max(1, min(8, int(n)))` — clamps to [1, 8]. Fractional values are floored. `LOOP 0.7` → 0 after int() → clamped to 1.

---

## New Red Actions

### `DO_LATERAL_SPAWN`
```python
def do_lateral_spawn(agent):
    subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    artifact = agent.nz / f"lateral_{random.randint(1000, 9999)}.json"
    artifact.write_text(json.dumps({"type": "c2_beacon", "tick": agent.current_tick}))
```

### `DO_NZ_ARTIFACT`
```python
def do_nz_artifact(agent):
    artifact = agent.nz / f"c2_{random.randint(1000, 9999)}.json"
    artifact.write_text(json.dumps({"type": "staging", "tick": agent.current_tick}))
```

### `DO_PRIVESC`
Three sequential real attempts. Each is silently swallowed on failure. Counter always incremented.
```python
def do_privesc(agent):
    # Attempt 1: fodhelper UAC bypass
    try:
        import winreg
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                               r"Software\Classes\ms-settings\shell\open\command")
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "cmd.exe")
        winreg.SetValueEx(key, "DelegateExecute", 0, winreg.REG_SZ, "")
    except Exception:
        pass

    # Attempt 2: token impersonation via ctypes
    try:
        import ctypes
        ctypes.windll.advapi32.ImpersonateSelf(2)  # SecurityImpersonation
    except Exception:
        pass

    # Attempt 3: HKLM write
    try:
        import winreg
        winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\VanguardPrivEsc")
    except Exception:
        pass

    # Always record the attempt
    log_path = agent.nz / "privesc_log.json"
    try:
        count = json.loads(log_path.read_text()).get("count", 0) if log_path.exists() else 0
    except Exception:
        count = 0
    log_path.write_text(json.dumps({"count": count + 1}))
```

### `DO_NET_SCAN`
```python
def do_net_scan(agent):
    import socket
    targets = [(f"192.168.1.{random.randint(1,254)}", p) for p in (445, 3389)
               for _ in range(5)]
    for ip, port in targets:
        try:
            s = socket.socket()
            s.settimeout(0.05)
            s.connect_ex((ip, port))
            s.close()
        except Exception:
            pass
```

### `DO_REG_PERSISTENCE`
```python
def do_reg_persistence(agent):
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Run",
                            0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "VanguardPersist", 0, winreg.REG_SZ,
                              sys.executable)
    except Exception:
        pass
```

---

## New Blue Actions

### `DO_MEMORY_SCAN`
```python
def do_memory_scan(agent):
    import ctypes
    PAYLOAD_SIGNATURES = [b"red_payload", b"VanguardTest", b"c2_beacon"]
    for proc in psutil.process_iter(["pid", "create_time"]):
        if proc.pid in agent.t0_pids:
            continue
        try:
            handle = ctypes.windll.kernel32.OpenProcess(0x10, False, proc.pid)
            if not handle:
                continue
            buf = ctypes.create_string_buffer(4096)
            read = ctypes.c_size_t(0)
            ctypes.windll.kernel32.ReadProcessMemory(
                handle, ctypes.c_void_p(0x10000), buf, 4096,
                ctypes.byref(read))
            ctypes.windll.kernel32.CloseHandle(handle)
            for sig in PAYLOAD_SIGNATURES:
                if sig in buf.raw:
                    _log_detection(agent.nz, "memory_scan", proc.pid)
                    break
        except Exception:
            pass
```

### `DO_ANCESTRY_CHECK`
```python
def do_ancestry_check(agent):
    SUSPICIOUS_PARENTS = {"cmd.exe", "powershell.exe", "wscript.exe", "cscript.exe"}
    for proc in psutil.process_iter(["pid", "name", "create_time"]):
        if proc.pid in agent.t0_pids:
            continue
        try:
            parent = proc.parent()
            depth = 0
            while parent and depth < 4:
                if parent.name().lower() in SUSPICIOUS_PARENTS:
                    if parent.parent() and parent.parent().pid not in agent.t0_pids:
                        _log_detection(agent.nz, "ancestry", proc.pid)
                        break
                parent = parent.parent()
                depth += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
```

### `DO_FLOW_ANALYSIS`
```python
def do_flow_analysis(agent):
    conn_by_pid: dict = {}
    for c in psutil.net_connections():
        if c.status == "ESTABLISHED" and c.pid and c.raddr:
            if not c.raddr.ip.startswith("127."):
                conn_by_pid[c.pid] = conn_by_pid.get(c.pid, 0) + 1
    for pid, count in conn_by_pid.items():
        if pid not in agent.t0_pids and count >= 3:
            _log_detection(agent.nz, "flow_analysis", pid)
```

`_log_detection(nz, source, pid)` appends to `nz/blue_detections.json` atomically.

---

## Adaptive Noise Floor (`sandbox/matrix_delta.py`)

```python
NOISE_SETTLE_TICKS = 10   # module constant; default settle threshold

class AdaptiveNoiseFloor:
    def __init__(self, window: int = 20):
        self._samples: collections.deque = collections.deque(maxlen=window)
        self._nominal_streak: int = 0
        self._ticks_since_recal: int = 0
        self.floor: float = 0.0

    def seed(self, samples: list[float]) -> None:
        """Called once after initial noise measurement (replaces bare float)."""
        for s in samples:
            self._samples.append(s)
        self.floor = float(np.mean(self._samples)) if self._samples else 0.0

    def update(self, delta_raw: float, tier: str,
               settle_ticks: int = NOISE_SETTLE_TICKS) -> None:
        self._samples.append(delta_raw)
        self._ticks_since_recal += 1
        if tier == "NOMINAL":
            self._nominal_streak += 1
        else:
            self._nominal_streak = 0

        if self._nominal_streak >= settle_ticks:
            self._recalibrate()
        elif self._ticks_since_recal >= 150:
            self._recalibrate()

    def _recalibrate(self) -> None:
        if self._samples:
            self.floor = float(np.mean(self._samples))
        self._nominal_streak = 0
        self._ticks_since_recal = 0
```

`watchdog.py` replaces `self.noise_floor: float` with `self.anf: AdaptiveNoiseFloor`. After `measure_noise()`, calls `anf.seed(noise_samples)`. Each tick calls `anf.update(delta_raw, tier)` and uses `anf.floor` as the noise floor.

---

## State Vector Expansion (`sandbox/state_vector.py`)

Four new measurement functions appended to `build_state_vector()`:

```python
def count_scheduled_tasks() -> int:
    try:
        r = subprocess.run(["schtasks", "/query", "/fo", "csv"],
                           capture_output=True, text=True, timeout=5)
        return max(0, r.stdout.count("\n") - 2)
    except Exception:
        return 0

def count_outbound_connections() -> int:
    return sum(
        1 for c in psutil.net_connections()
        if c.status == "ESTABLISHED" and c.raddr
        and not c.raddr.ip.startswith("127.")
    )

def measure_child_process_depth(t0_pids: set) -> int:
    max_depth = 0
    for proc in psutil.process_iter(["pid"]):
        if proc.pid in t0_pids:
            continue
        depth, p = 0, proc
        try:
            while p and p.pid not in t0_pids and depth < 16:
                p = p.parent()
                depth += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        max_depth = max(max_depth, depth)
    return max_depth

def read_privesc_signals(nz: Path) -> int:
    try:
        return json.loads((nz / "privesc_log.json").read_text()).get("count", 0)
    except (FileNotFoundError, json.JSONDecodeError):
        return 0
```

Updated `build_state_vector()` signature:
```python
def build_state_vector(config: dict, cpu_ma: CpuMovingAverage,
                       t0_pids: set = None, nz: Path = None) -> np.ndarray:
    ...
    return np.array(
        [proc_count, reg_hash, file_count, open_ports]
        + cpu_cores
        + [sched_tasks, outbound_conns, child_depth, privesc_signals],
        dtype=float,
    )
```

---

## GA Engine Updates (`host/ga_engine.py`)

### `random_program(role, min_len=8, max_len=32) -> list`

Generates a structurally valid opcode list. Algorithm:
1. Pick a random length in `[min_len, max_len]`
2. Fill with random opcodes from the role-appropriate set
3. For each `PUSH`, append a random float in [0.0, 1.0] as the next element
4. For each `LOOP`, append a random int in [1, 4] as the next element
5. Call `repair_control_flow()` to balance branches
6. Truncate to `MAX_PROGRAM_LEN`

### `crossover(prog_a, prog_b) -> list`

```python
def crossover(prog_a: list, prog_b: list) -> list:
    mask_a = compute_operand_mask(prog_a)
    # Find valid splice points: non-operand positions only
    valid_a = [i for i in range(1, len(prog_a)) if not mask_a[i]]
    point = random.choice(valid_a) if valid_a else len(prog_a) // 2
    child = prog_a[:point] + prog_b[point:]
    child = repair_control_flow(child)
    return child[:MAX_PROGRAM_LEN]
```

### `mutate(program, win_rate, role) -> list`

Mutation type is chosen by weighted random, where weights depend on `win_rate`:

```python
def _mutation_weights(win_rate: float) -> dict:
    wr = max(0.0, min(1.0, win_rate))
    return {
        "replace":      0.3 + 0.4 * (1.0 - wr),   # more replace when losing
        "adjust_push":  0.30,                        # constant
        "insert":       0.20 * (1.0 - wr),          # more insertion when losing
        "delete":       0.10 + 0.10 * wr,           # more pruning when winning
        "swap":         0.10,                        # constant
    }
```

- **replace**: pick a random non-operand position; replace with a random opcode from role's set. If replacement is `PUSH` or `LOOP`, insert operand immediately after.
- **adjust_push**: find all operand slots (PUSH/LOOP operands); pick one; add `Gaussian(0, 0.1)`, clamp LOOP operands to [1, 8], float operands to [0.0, 10.0].
- **insert**: insert a random opcode at a random non-operand position.
- **delete**: remove a random non-operand, non-structural opcode (not `IF_TRUE`/`ENDIF`/`LOOP`/`ENDLOOP`).
- **swap**: swap two random non-operand positions.

After any mutation: `repair_control_flow()` + truncate to `MAX_PROGRAM_LEN`.

---

## LLM Codegen (`host/llm_codegen.py`)

Runs **synchronously on the host** after every 10 generations (blocking the GA loop). API latency is expected 5–30 seconds — acceptable given generation time is minutes.

### API credentials
Read from environment variable `ANTHROPIC_API_KEY`. If unset, codegen is skipped and a warning is logged. No crash.

### Cost guardrails
- Maximum 1 call per 10 generations (enforced by `run_simulation.py`)
- Prompt is capped at 2000 tokens of telemetry context
- A `CODEGEN_BUDGET_USD` env var (default: 5.0) tracks spend via the API's usage response; if exceeded, future codegen calls are skipped

### Process

1. Read last 20 entries from `ga_history.jsonl`
2. Identify dominant Red pattern (opcode sequence with highest red_fitness correlation)
3. Choose role to generate for: Red if `state == EVOLVE_RED`, Blue otherwise
4. Call Claude API with structured prompt
5. Parse response using the declared format
6. Validate with AST walk (see §Safety)
7. Write to `shared/vm/generated/<role>_gen_<N>.py`
8. Commit: `git add ... && git commit -m "codegen: add <opcode_name>"`

### LLM prompt structure

```
You are generating a new primitive action for a Windows adversarial AI simulation
running inside Windows Sandbox. The agent is a Python process.

Role: {role}
Current generation: {gen}
Top performing opcode sequences this generation: {sequences}
Dominant pattern Red is using: {pattern}

Generate ONE new {role} primitive that would {complement/counter} this pattern.

Rules:
- Function signature: def {snake_case_name}(agent) -> None
- Allowed imports (must be at module top): os, subprocess, json, random, time,
  pathlib, psutil, ctypes, socket, winreg
- No exec(), eval(), compile(), __import__(), importlib
- Must complete within 2 seconds
- agent.nz is the neutral zone Path
- agent.t0_pids is the set of baseline PIDs

Output format (exactly):
# OPCODE: DO_SNAKE_CASE_NAME
# ROLE: {role}
# DESCRIPTION: one sentence
def do_snake_case_name(agent) -> None:
    ...
```

### Safety: AST validation (`host/llm_codegen.py`)

```python
import ast, sys

ALLOWED_IMPORTS = {"os","subprocess","json","random","time",
                   "pathlib","psutil","ctypes","socket","winreg"}
FORBIDDEN_CALLS = {"exec","eval","compile","__import__"}

def validate_generated_code(source: str) -> tuple[bool, str]:
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return False, f"SyntaxError: {e}"

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                     else [node.module])
            for name in names:
                root = (name or "").split(".")[0]
                if root not in ALLOWED_IMPORTS:
                    return False, f"Forbidden import: {name}"
        if isinstance(node, ast.Call):
            func = node.func
            name = (func.id if isinstance(func, ast.Name) else
                    func.attr if isinstance(func, ast.Attribute) else None)
            if name in FORBIDDEN_CALLS:
                return False, f"Forbidden call: {name}"

    return True, "ok"
```

Note: `subprocess` is in the whitelist because `DO_NET_SCAN` and other DO ops legitimately need it. The real containment boundary is Windows Sandbox — WSB ensures the Python process cannot affect the host regardless of what it runs. The import whitelist is defence-in-depth against obviously malformed generated code, not a security perimeter.

### Opcode name validation

```python
import re

def parse_generated_file(source: str) -> tuple[str, str, callable]:
    """Extract opcode name and function from generated source. Returns (opcode, role, fn)."""
    opcode_match = re.search(r"^# OPCODE: (DO_\w+|SENSE_\w+)", source, re.MULTILINE)
    role_match = re.search(r"^# ROLE: (red|blue)", source, re.MULTILINE)
    fn_match = re.search(r"^def (do_\w+|sense_\w+)\(agent\)", source, re.MULTILINE)

    if not (opcode_match and role_match and fn_match):
        raise ValueError("Generated file missing required header or function signature")

    declared = opcode_match.group(1).lower().replace("do_", "").replace("sense_", "")
    defined = fn_match.group(1).replace("do_", "").replace("sense_", "")
    if declared != defined:
        raise ValueError(f"Opcode name mismatch: {declared!r} vs {defined!r}")

    return opcode_match.group(1), role_match.group(1)
```

---

## Co-evolution Simplification (`host/coevolution.py`)

**Removed:** `PHASE_UNLOCK` state, `expand_red_genome()`, all phase transition logic.

**State machine:** `EVOLVE_RED → EVOLVE_BLUE → DONE`

Red exit: win_rate ≥ 60% over last 20 competitive rounds → freeze Red champion, switch to `EVOLVE_BLUE`, clear results.

Blue exit: win_rate ≥ 80% over last 20 competitive rounds AND ≥ 3 distinct programs (pairwise **edit distance** > 5 opcodes, not Euclidean distance) → freeze Blue champion → `DONE`.

Edit distance for programs: count positions where opcodes differ (after zero-padding shorter program).

---

## Testing Strategy

| Test file | Key cases |
|-----------|-----------|
| `test_stack_vm.py` | PUSH/POP/DUP arithmetic; GT/LT branch taken/skipped; LOOP runs exactly N times; nested loops up to 4 deep; 5th nested loop is NOP; MAX_STEPS causes silent halt; stack underflow returns 0.0; unknown opcode → NOP; HALT inside loop exits immediately; role-gated SENSE returns 0.0 for wrong role |
| `test_instruction_set.py` | each DO_* handler callable with mock agent; SENSE_* returns float; generated/ plugins auto-register in filename order; name collision with builtin → skip + log |
| `test_repair_control_flow.py` | orphaned ELSE removed; orphaned ENDIF removed; unclosed IF_TRUE closed; orphaned ENDLOOP removed; unclosed LOOP closed; nested mismatches resolved; output ≤ MAX_PROGRAM_LEN; operand slots preserved |
| `test_ga_engine_v2.py` | random_program structurally valid (passes repair no-op); crossover splices at non-operand positions only; mutate output ≤ MAX_PROGRAM_LEN; mutate preserves PUSH-operand adjacency; mutation weights shift correctly with win_rate; adjust_push clamps LOOP operands to [1,8] |
| `test_state_vector_v2.py` | count_scheduled_tasks returns int ≥ 0; count_outbound_connections returns int ≥ 0; measure_child_process_depth returns int ≥ 0; build_state_vector includes 4 new dims |
| `test_matrix_delta_v2.py` | AdaptiveNoiseFloor.seed() sets initial floor; recalibrates after settle_ticks NOMINAL; resets streak after non-NOMINAL tick; recalibrates after 150 ticks regardless of tier; floor updates to mean of window |
| `test_llm_codegen.py` | validate_generated_code rejects: unknown import, `from os import system`, `exec(...)`, `eval(...)`, `__import__(...)`, dotted import not in whitelist; accepts valid code; parse_generated_file rejects name mismatch; accepts valid file; collision with builtin is skipped |
| `test_compute_operand_mask.py` | PUSH at end produces no operand slot; consecutive PUSHes each mark next slot; LOOP operand correctly marked; mixed program correct |

---

## Migration from v1

1. **Checkpoints incompatible.** `ga_history.jsonl` stores float arrays in v1 and opcode lists in v2. On first v2 run, `coevolution.py` detects the schema mismatch (list vs float at genome index 0) and discards the checkpoint, restarting evolution. Existing champion JSON files are also discarded.

2. **Test files updated in-place.** Files that change: `test_genome.py` (genome is opcode list, no phases), `test_red_agent.py` (agent is thin VM shell), `test_blue_agent.py` (same), `test_ga_engine.py` (new operators), `test_coevolution.py` (no phase unlock). Files that are kept unchanged: `test_watchdog.py` (watchdog structure preserved), `test_orchestrator.py`, `test_run_simulation.py` (new HOF uses edit distance), `test_state_vector.py` (extended, not replaced), `test_matrix_delta.py` (extended, not replaced).

3. `arena.wsb` — unchanged.

4. Neutral zone file shapes — unchanged. `telemetry.json`, `heartbeat.json`, `round_config.json` schemas are preserved. `round_config.json` gains `red_program` and `blue_program` fields (opcode lists) replacing `red_genome` / `blue_genome` float arrays.

---

## Open Questions / Future Work

- **Program length pressure:** Without explicit length penalisation, programs may bloat to 64 opcodes. Consider adding a length term to fitness: `fitness -= 0.5 * (len(program) / MAX_PROGRAM_LEN)`.
- **Cross-round memory:** Programs have no persistent state across ticks (stack resets each tick). A `STORE <slot>` / `LOAD <slot>` opcode pair (8 slots, floats, persisted in agent) could enable mid-round memory.
- **Generated code human review gate:** Currently auto-committed. A GitHub PR workflow where generated files require human approval before being included in the active instruction set would reduce risk.
- **Telemetry replay:** Storing full per-tick state vectors in telemetry would enable exact round replay and better LLM context for codegen.
