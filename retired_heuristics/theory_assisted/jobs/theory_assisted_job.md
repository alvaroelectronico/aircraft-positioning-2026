# Theory-Assisted BRKGA (Candidate C) for the Job-Level Scheduling Problem

Second independent, isolated Claude-assisted attempt at Candidate C from the
literature synthesis: a Biased Random-Key Genetic Algorithm with a mixed
chromosome (position assignment + in-position sequencing) and a greedy/NEH
warm-start seed.  Built in full isolation from `methods/brkga_v02/` to measure
how much two Claude-assisted attempts at the same algorithm family diverge in
implementation choices and final quality.

> **Status (code `4837874`, latest battery seeds 1–3 v2:
> [`…180236`](../../../outputs/logs/old/seed1$_202605_02_main_methods_20260622_180236.log)
> + [`…184024`](../../../outputs/logs/old/seed2$,_seed3$_202605_02_main_methods_20260622_184024.log)).**
> Decoder at **v2: Mode-A + in-fitness Mode-C (profile-gated) + timing genes
> (chromosome 3|R|, cap 0.5·mean_T)**.  Part II reflects the seeds-1–3 v2 battery
> (N=3, 108 runs).  Timing genes roughly halve the Mode-C gap again on the
> dominant `full_tight` outlier and flip several R20/R30 cells to beat the MILP
> (e.g. full_tight_R20 wDLY +24.5%).  The deeply-stuck-aircraft case is gone, so
> multi-front Mode-C is dropped; next levers are checker-free Mode-C feasibility
> (Hito 4b) and the full 10-seed battery (Hito 6).

---

# Part I — The method

## 1. Problem recap and notation

The hangar has positions $P$ linked by a blocking DAG $G=(P,A)$: arc $(p,q)$
means front position $p$ must move out of the way for a rear-position aircraft
at $q$ to enter or leave.  Each aircraft $r \in R$ has a chain of jobs with
known durations and strict precedence, an earliest start $E_r$, and a target
finish $L_r$; two aircraft sharing a position must be served in sequence with
$\epsilon$ separation ($\epsilon = $ `min_separation`).  A rear-position
aircraft may access its slot while a front aircraft is occupied only in three
modes — A (front fully vacant with $\eta$ margin), B (front in an inter-job gap
$\ge \mu$), or C (front mid-interruptible job, $\eta$ margin) — any other access
is infeasible.  Mode-B and Mode-C entries cost 2 movements each; Mode-A is free.
$\eta$ (`eta`, default 1.0) is the access margin and is **distinct** from
$\epsilon$.  The objective is
$w_{MK}\cdot\text{makespan} + w_{DLY}\cdot\sum_r\max(0, f_r-L_r) + w_{MOV}\cdot\text{movements}$.

## 2. Design principle

Separate the *combinatorial* decisions (which position each aircraft uses; in
what order multiple aircraft share a position) from the *timing* decisions
(when each job starts).  BRKGA evolves a real-valued chromosome that encodes
both combinatorial decisions; a deterministic decoder converts any chromosome
to a feasible schedule in topological position order, so the GA operates over a
space that is always feasible and timing is derived analytically.

The build order is **decoder-first**: a conservative, provably-checker-compliant
Mode-A decoder first, then access modes in order of risk (A → C; Mode-B gaps not
needed), then a third chromosome block (timing genes) that gives the GA a timing
degree of freedom the earliest-feasible sweep alone lacked.  The current code
has all three: Mode-A construction, in-fitness Mode C (§3.6), and timing
genes (§3.7).

## 3. Chromosome and decoder

### 3.1 Chromosome layout (length $3|R|$)

| gene range | encodes |
|---|---|
| $[0, |R|)$ | assignment keys: aircraft $r_i$ → position $\text{positions}[\min(\lfloor k_i \cdot |P|\rfloor, |P|-1)]$ |
| $[|R|, 2|R|)$ | sequencing keys: aircraft sorted by key within each position gives the service order (tie-break by instance index) |
| $[2|R|, 3|R|)$ | timing keys: per-aircraft delay preference past the earliest feasible start (§3.7) |

All three blocks are jointly evolved; crossover respects the block boundaries.

### 3.2 Decoder (`brkga/decoder.py`)

1. `decode_chromosome` maps genes to $(π, \text{seq\_order})$ — position
   assignment and per-position aircraft ordering.
2. `build_schedule` visits positions in **topological order** of the blocking
   DAG (every front position before the rear positions it blocks), so the
   Mode-A windows of a rear position can be computed against already-fixed front
   aircraft.  Within a position, each aircraft is given the earliest feasible
   start: `lower = max(E_r, last_finish + ε)`; then the window algebra finds the
   smallest `start ≥ lower` such that both the aircraft's entry (`start`) and
   exit (`start + T_r`) are Mode-A against every front aircraft of that position.
3. Jobs are scheduled **contiguously** (no voluntary pauses).  With
   `allow_mode_c=False` (the Mode-A path) every rear waits for full front
   vacancy and κ=0 throughout.  With `allow_mode_c=True` the sweep additionally
   lets a rear start earlier into an interruptible front job's interior
   (Mode C); see §3.6.
4. `compute_objective` evaluates the weighted sum; any infeasible access adds a
   penalty $10^9$ per violation (the search should never fix on one).
5. `count_movements` mirrors `checker._classify_access` line-for-line (same
   $\eta$ margins, same `TOL = 1e-4`) so the reported movement count equals what
   the checker infers at validation time (0 on the Mode-A path).

### 3.3 Access-mode windows (`brkga/access.py`, `brkga/windows.py`)

`mode_a_windows_for_position(p, state, model)` computes the intersection over
every front aircraft of position $p$ of the Mode-A windows
$[0, s_{\text{front}}-\eta] \cup [f_{\text{front}}+\eta, \infty)$.  The decoder
intersects this with its $-T_r$ shift (the exit-instant constraint) and takes
`first_point_at_or_after(lower)`.  All window operations live in `windows.py`
(pure interval algebra, no problem semantics); the semantics — including
`classify_access`, the faithful checker mirror — live in `access.py`.  The
Mode-C path adds `decoder._feasible_bc_windows`, which builds the *Mode-A
regions plus interruptible-job interiors* a rear may use (see §3.6).

### 3.4 Warm-start seed (`brkga/warm_start.py`)

One chromosome of the initial population is a greedy/NEH seed: aircraft are
inserted in descending order of aggregate job time $T_r$ (ties broken by the
tighter slack $L_r - E_r - T_r$); each aircraft is placed in the position that
minimises the current partial objective (append-to-end insertion); the resulting
$(π, \text{seq\_order})$ is reverse-encoded into a key vector that the decoder
reproduces exactly.  The rest of the initial population is random.  No other
method's output is read (not even cached MILP solutions).

### 3.5 BRKGA loop (`brkga/engine.py`)

Pure-Python, self-contained BRKGA (no external library, no IPR).  Parameters:

| param | default |
|---|---|
| population size | `max(100, 10·2·|R|)` |
| elite fraction | 15% |
| mutant fraction | 10% |
| crossover bias (`rho`) | 0.7 (elite gene kept with probability `rho`) |

Each generation: carry elite unchanged → add fresh random mutants → fill the
rest with biased crossover (one elite parent, one non-elite, gene from elite
with probability `rho`).  The budget is checked once per generation; the best
chromosome seen (including the greedy seed at generation 0) is always available
as a fallback, so `solve` returns a feasible solution even for a tiny budget.
The loop is deterministic given `seed`.

### 3.6 Mode C in the fitness (`decoder.build_schedule`, `decode`)

A post-pass Mode-C local search on a Mode-A-optimised incumbent was measured to
be **inert** (the GA already routes delay to non-waiting front positions), so
Mode C is woven into the **decoder sweep** instead, making it part of the
fitness the GA optimises.  Per rear (profile-aware greedy): compute the earliest
start in `_feasible_bc_windows` (Mode-A regions ∪ interruptible-job interiors);
take it over the Mode-A start only when the weighted delay/makespan it saves the
rear exceeds the weighted movement cost (2 per access) **plus** the extra delay
the front extension causes; a separation guard blocks interruptions that would
collide a front with its successor.  Accepted interruptions extend the front job
by δ (κ+1) and shift its later jobs.

Because front extensions propagate, each Mode-C build is **validated by the real
checker** in `decode`; if it is non-compliant the decode **falls back to the
always-feasible Mode-A build**.  A fast path skips the checker when no
interruption was applied (movements = 0 ⇒ Mode-A-equivalent).  `solve` **gates**
Mode C off when `weight_movements > max(weight_makespan, weight_delay)` (wMOV),
where the trade never pays and the build overhead would only steal generations.

### 3.7 Timing genes (chromosome block 3)

The earliest-feasible sweep fully determined timing, so two chromosomes with the
same assignment + order produced the *same* schedule — the GA had no timing
degree of freedom.  Block 3 adds one: for each aircraft, the realised start is
`first_feasible_point(windows, earliest + gene·cap)` with
`cap = timing_cap_factor · mean_T` (factor default **0.5**, ablation-chosen).
The gene only ever pushes a start **later** (and snaps to the next feasible
window), so feasibility is preserved; `gene = 0` reproduces the earliest start
exactly.  It applies symmetrically to the Mode-A start and the Mode-C reference
start, keeping the A-vs-C comparison consistent.  The greedy/NEH warm-start sets
all timing genes to 0 (reproduces the earliest-feasible seed); random
chromosomes carry uniform timing genes.

This is what attacks the serialization in dense topologies: on `full_tight` it
let the GA discover assignments with more aircraft in front (non-waiting)
positions and **dissolved the single deeply-stuck rear aircraft** that v1 left
(diagnosis: one aircraft waiting 255 → wait spread, max ≈ 80).  Population is
pinned to `max(100, 20|R|)` so the longer chromosome does not auto-inflate it.

## 4. The complete algorithm

```
TheoryAssistedJobSolver.solve(instance_data):
  model   ← build_model(instance_data)         # parse + topo-sort positions
  weights ← {makespan: wMK, delay: wDLY, movements: wMOV}   # CONFIGURED weights
  gate    ← wMOV <= max(wMK, wDLY)             # Mode-C profile gate
  allow_mode_c ← config.get("allow_mode_c", gate)
  cap      ← config.get("timing_cap_factor", 0.5) · mean_T   # timing-gene cap
  pop_size ← max(100, 20·|R|)                  # pinned across versions
  obj, state, generations ← run_brkga(model, weights, time_limit, seed,
                                       allow_mode_c, instance if allow_mode_c else None,
                                       cap, pop_size)
  return to_solution_dict(state, model, weights,
                          status=f"brkga ({generations} generations, mode {A|A+C})")

run_brkga(model, weights, time_limit, seed, allow_mode_c, instance, cap, pop_size):
  rng        ← Random(seed)
  population ← [greedy_seed(model, weights)] + random chromosomes   # 3|R| keys
  scored     ← sort by fitness(ch) = decode(ch, model, weights, allow_mode_c, instance, cap)[0]
  while elapsed < time_limit:
    elite, non_elite ← top 15%, bottom 85%
    next_pop ← elite + mutants + biased-crossover offspring
    scored   ← re-evaluate and sort
    update best if improved
    generations += 1
  return best_obj, decode(best_ch, …)[1], generations

decode(ch, model, weights, allow_mode_c, instance, cap):
  pi, seq, timing ← decode_chromosome(ch)      # timing drives the start offset
  build Mode-A (fast) if not allow_mode_c → return (obj, state)
  build Mode-A+C (in-sweep); if no interruption → return (obj, state)   # fast path
  validate with real checker; if compliant → movements from checker, return
  else → rebuild Mode-A (guaranteed feasible), return
```

## Behaviour observed

The Mode-A path produces **0 movements** but elevated makespan/delay (it waits
for full front vacancy at both access instants).  Enabling Mode C in the fitness
(wMK/wDLY) lets rears start inside interruptible front jobs, trading +2 movements
per access for earlier starts; the seed-1 battery shows this roughly halves the
gap to the MILP on blocking-heavy types (and widens the R30 lead) while staying
100 % checker-compliant.  Under wMOV the gate keeps the pure Mode-A path.  Decode
cost is ≈ 0.04 ms (R5) to ≈ 0.42 ms (R20/R30) for Mode-A; a Mode-C decode that
fires adds one checker call (~1.7×), so the generation count drops on large R
when Mode C is heavily used (e.g. ~13–30 gens at R20/R30 vs hundreds at R10).

---

# Part II — Results and analysis

## Experimental setup

| field             | value |
| ----------------- | ----- |
| Battery           | 12 instance types × 3 seeds (1–3) × 3 profiles = 108 runs |
| Methods compared  | `ta2_brkga_wMK` / `ta2_brkga_wDLY` / `ta2_brkga_wMOV` (v2: Mode-C + timing genes) vs cached job-level MILP (`milp_job_*`) |
| Weight profiles   | wMK (100/1/1) · wDLY (1/100/1) · wMOV (1/1/100) |
| Budget            | 60 s wall-clock per run |
| Metric            | relative gap = (MILP_obj − heuristic_obj) / MILP_obj; positive = heuristic better |
| Log               | seeds 1–3 across two runs: [`…180236`](../../../outputs/logs/old/seed1$_202605_02_main_methods_20260622_180236.log) (seed 1) + [`…184024`](../../../outputs/logs/old/seed2$,_seed3$_202605_02_main_methods_20260622_184024.log) (seeds 2–3); aggregated from `results.csv` |

## Relative objective gap (seeds 1–3 — N=3 per cell)

Gap = (MILP_obj − heuristic_obj) / MILP_obj.  Positive = heuristic better.  All
profiles use the v2 decoder (Mode-A + in-fitness Mode-C + timing genes,
`cap = 0.5·mean_T`); Mode-C is gated off under wMOV.

### wMK (100/1/1 — makespan-priority)

| Instance type              | N | Mean    | Min     | Max     |
|----------------------------|---|---------|---------|---------|
| scn_chain_tight_P5_R10     | 3 | −23.21% | −29.97% | −17.21% |
| scn_full_tight_P5_R10      | 3 | −63.83% | −77.93% | −42.25% |
| scn_full_tight_P5_R20      | 3 | −19.73% | −58.02% | +0.29%  |
| scn_hub_tight_P5_R10       | 3 | −10.22% | −24.00% | −3.18%  |
| scn_none_tight_P5_R10      | 3 | +0.00%  | +0.00%  | +0.00%  |
| scn_triangle_loose_P5_R10  | 3 | −15.97% | −23.62% | −5.93%  |
| scn_triangle_medium_P5_R10 | 3 | −11.38% | −12.10% | −10.15% |
| scn_triangle_tight_P5_R10  | 3 | −16.13% | −22.20% | −12.31% |
| scn_triangle_tight_P5_R20  | 3 | +8.79%  | +3.83%  | +16.31% |
| scn_triangle_tight_P5_R30  | 3 | +12.86% | +10.14% | +15.06% |
| scn_triangle_tight_P5_R5   | 3 | −0.06%  | −0.16%  | +0.00%  |
| scn_two_rows_tight_P5_R10  | 3 | −8.60%  | −10.07% | −6.74%  |

### wDLY (1/100/1 — delay-priority)

| Instance type              | N | Mean      | Min       | Max      |
|----------------------------|---|-----------|-----------|----------|
| scn_chain_tight_P5_R10     | 3 | −30.96%   | −48.06%   | −20.77%  |
| scn_full_tight_P5_R10      | 3 | −65.60%   | −96.98%   | −21.29%  |
| scn_full_tight_P5_R20      | 3 | **+24.49%** | +7.76%  | +44.71%  |
| scn_hub_tight_P5_R10       | 3 | −14.49%   | −29.20%   | −6.12%   |
| scn_none_tight_P5_R10      | 3 | +0.00%    | +0.00%    | +0.00%   |
| scn_triangle_loose_P5_R10  | 3 | −1929.57% | −3337.28% | −553.94% |
| scn_triangle_medium_P5_R10 | 3 | −22.77%   | −36.02%   | −8.50%   |
| scn_triangle_tight_P5_R10  | 3 | −11.82%   | −19.35%   | −5.22%   |
| scn_triangle_tight_P5_R20  | 3 | +1.66%    | −11.64%   | +14.62%  |
| scn_triangle_tight_P5_R30  | 3 | +14.11%   | −4.12%    | +28.10%  |
| scn_triangle_tight_P5_R5   | 3 | −200.52%  | −601.53%  | −0.00%   |
| scn_two_rows_tight_P5_R10  | 3 | −10.83%   | −17.08%   | −7.22%   |

### wMOV (1/1/100 — movement-priority)

| Instance type              | N | Mean    | Min     | Max     |
|----------------------------|---|---------|---------|---------|
| scn_chain_tight_P5_R10     | 3 | −31.71% | −41.39% | −23.92% |
| scn_full_tight_P5_R10      | 3 | −78.67% | −93.49% | −54.66% |
| scn_full_tight_P5_R20      | 3 | −11.67% | −18.85% | −7.11%  |
| scn_hub_tight_P5_R10       | 3 | −7.18%  | −19.37% | −0.84%  |
| scn_none_tight_P5_R10      | 3 | −0.38%  | −1.14%  | +0.00%  |
| scn_triangle_loose_P5_R10  | 3 | −27.65% | −47.81% | −7.19%  |
| scn_triangle_medium_P5_R10 | 3 | −16.94% | −21.85% | −12.96% |
| scn_triangle_tight_P5_R10  | 3 | −6.91%  | −18.10% | −1.28%  |
| scn_triangle_tight_P5_R20  | 3 | +1.37%  | −1.12%  | +4.97%  |
| scn_triangle_tight_P5_R30  | 3 | +32.53% | +25.97% | +38.42% |
| scn_triangle_tight_P5_R5   | 3 | −2.45%  | −7.36%  | +0.00%  |
| scn_two_rows_tight_P5_R10  | 3 | −10.37% | −19.63% | −5.25%  |

## Per-component mean Δ (heuristic − MILP; negative = heuristic better)

### wMK

| Instance type              | N | Δmakespan | Δdelay   | Δmov   |
|----------------------------|---|-----------|----------|--------|
| scn_chain_tight_P5_R10     | 3 | +14.55    | +81.20   | −4.67  |
| scn_full_tight_P5_R10      | 3 | +45.59    | +272.69  | −4.00  |
| scn_full_tight_P5_R20      | 3 | +37.67    | +280.16  | +24.00 |
| scn_hub_tight_P5_R10       | 3 | +7.09     | +4.43    | −12.67 |
| scn_none_tight_P5_R10      | 3 | +0.00     | +0.00    | +0.00  |
| scn_triangle_loose_P5_R10  | 3 | +9.71     | +31.94   | −8.67  |
| scn_triangle_medium_P5_R10 | 3 | +7.16     | +25.58   | −8.00  |
| scn_triangle_tight_P5_R10  | 3 | +9.93     | +50.19   | −5.33  |
| scn_triangle_tight_P5_R20  | 3 | −14.34    | −41.38   | −2.67  |
| scn_triangle_tight_P5_R30  | 3 | −45.18    | −218.16  | +10.00 |
| scn_triangle_tight_P5_R5   | 3 | +0.00     | +0.34    | +1.33  |
| scn_two_rows_tight_P5_R10  | 3 | +5.25     | +29.65   | −0.67  |

### wDLY

| Instance type              | N | Δmakespan | Δdelay   | Δmov   |
|----------------------------|---|-----------|----------|--------|
| scn_chain_tight_P5_R10     | 3 | +4.35     | +39.36   | −5.33  |
| scn_full_tight_P5_R10      | 3 | +16.28    | +122.47  | +2.00  |
| scn_full_tight_P5_R20      | 3 | −71.70    | −638.85  | +1.33  |
| scn_hub_tight_P5_R10       | 3 | −0.08     | +17.23   | −6.67  |
| scn_none_tight_P5_R10      | 3 | +0.00     | +0.00    | +0.00  |
| scn_triangle_loose_P5_R10  | 3 | +12.78    | +21.90   | −4.67  |
| scn_triangle_medium_P5_R10 | 3 | +12.13    | +14.82   | −4.67  |
| scn_triangle_tight_P5_R10  | 3 | +5.47     | +12.92   | −8.67  |
| scn_triangle_tight_P5_R20  | 3 | −5.87     | −18.91   | −6.00  |
| scn_triangle_tight_P5_R30  | 3 | −59.85    | −524.48  | +6.00  |
| scn_triangle_tight_P5_R5   | 3 | +0.00     | +0.67    | −0.67  |
| scn_two_rows_tight_P5_R10  | 3 | +0.44     | +11.78   | −1.33  |

### wMOV

| Instance type              | N | Δmakespan | Δdelay   | Δmov   |
|----------------------------|---|-----------|----------|--------|
| scn_chain_tight_P5_R10     | 3 | +23.51    | +54.66   | +0.00  |
| scn_full_tight_P5_R10      | 3 | +52.90    | +163.55  | +0.00  |
| scn_full_tight_P5_R20      | 3 | +16.73    | +178.24  | +0.00  |
| scn_hub_tight_P5_R10       | 3 | +3.52     | +10.20   | +0.00  |
| scn_none_tight_P5_R10      | 3 | +0.33     | +0.33    | +0.00  |
| scn_triangle_loose_P5_R10  | 3 | +3.85     | +16.06   | +0.00  |
| scn_triangle_medium_P5_R10 | 3 | +4.51     | +17.92   | +0.00  |
| scn_triangle_tight_P5_R10  | 3 | +1.34     | +10.32   | +0.00  |
| scn_triangle_tight_P5_R20  | 3 | −7.31     | −6.80    | +0.00  |
| scn_triangle_tight_P5_R30  | 3 | −121.86   | −1071.70 | +0.00  |
| scn_triangle_tight_P5_R5   | 3 | +0.00     | +0.78    | +0.00  |
| scn_two_rows_tight_P5_R10  | 3 | +1.67     | +16.09   | +0.00  |

## Performance summary

The v2 decoder (Mode-A + in-fitness Mode-C + timing genes) is feasible on all
108 runs.  Timing genes (cap 0.5·mean_T) approximately halve the v1 gap again on
the dominant blocking outlier and flip several R20/R30 cells to *beat* the MILP:

- **`scn_full_tight_P5_R20`**: wMK −95→**−20%** (max +0.3%), wDLY −35→**+24.5%**
  (beats MILP every seed), wMOV −196→**−12%** — the headline improvement.
- **`scn_full_tight_P5_R10`**: wMK −100→−64%, wDLY −97→−66%, wMOV −217→−79%.
- **`scn_triangle_tight_P5_R20`**: wMK now **+8.8%**, wDLY **+1.7%** (beats MILP);
  R30 widens to +12.9 / +14.1 / +32.5%.
- Easy topologies (`triangle_tight_R10`, `two_rows`) are roughly unchanged — the
  extra timing freedom costs a little convergence there but the loss is small.

The Δ tables localise the residual: on `full_tight` the heuristic still trails
the MILP on delay (positive Δdelay) under wMK/wMOV because dense blocking
serialises many rear aircraft; under wDLY at R20 the heuristic now *leads*
(Δdelay −639).  At R20/R30 the per-decode checker call caps generations
(~13–53), which is the main remaining lever (Hito 4b).

## Caveats

1. Battery is seeds 1–3 (N=3 per cell); a full 10-seed battery (Hito 6) is still
   the formal rebaseline before firm quality-distribution claims.
2. The MILP baseline rows are cached (`results.csv`); large-R MILP runs are
   likely unconverged (MIPGap > 0), so "MILP better" gaps are conservative and
   "heuristic better" gaps at R20/R30 reflect the MILP's 60 s limit, not proven
   superiority.
3. `scn_triangle_loose_P5_R10` wDLY (−1930%) and `scn_triangle_tight_P5_R5` wDLY
   (−201%) are small-denominator inflation (MILP delay ≈ 0) with high variance;
   read the per-component Δ tables (e.g. loose wDLY Δdelay ≈ +22) for the true,
   small, magnitude — not the relative gap.
4. The two seed batteries ran from working trees on top of HEAD `4837874`
   (timing_cap_factor=0.5); the v2 decoder/cap were finalised at `4837874`.

---

# Part III — Improvement roadmap

## Diagnosis

The decoder is correct and fast (100% checker-compliant), the BRKGA loop
improves materially over the greedy seed, Mode C (§3.6) roughly halves the gap
on blocking-heavy types, and timing genes (§3.7) halve it again on the dominant
`full_tight` outlier.  After timing genes the wait is no longer concentrated in
one stuck aircraft (diagnosis), so the residual deficit is now broad
serialization plus fewer BRKGA generations at R20/R30 (per-decode checker call) —
not a single rescue case.  The roadmap addresses generations and the baseline.

## Hito 4 — Mode C in the fitness (DONE, commit `5b868ff`)

Mode C woven into the decoder sweep (§3.6): per-rear profile-aware greedy,
real-checker validation with Mode-A fallback, a separation guard, and a profile
gate (off under wMOV).

## Hito 7 — Timing genes (DONE, commits `59ab4fe` / `4837874`)

Chromosome 2|R|→3|R| (§3.7); cap `0.5·mean_T` chosen by `ablation_timing.py`.
On `full_tight` it roughly halves the gap again over Mode C (R20 wMK −96→−28 %,
wMOV −184→−9 %, wDLY −27→+3 %) and dissolves the deeply-stuck aircraft, at a
small cost on easy topologies.  This **removes the motivation for a multi-front
Mode-C rescue** (no concentrated stuck-aircraft case remains) — that idea is
dropped from the active queue.

## Hito 4b — Incremental (checker-free) Mode-C feasibility (PLANNED, now top)

The per-decode `check_solution` call caps generations at R20/R30 (≈ 13–53 gens),
which is now the main remaining lever on dense instances.  A complete *analytic*
feasibility evaluator (validated to agree with the checker over a large sample)
would remove that call from the hot loop and lift the generation count.

## Hito 3 — Deliberate Mode-B gaps (NOT DONE; lowest priority)

Inserting inter-job gaps to open Mode-B windows was **not implemented** as a
separate move: Mode C proved the dominant lever and incidental Mode-B windows
are already handled by the classifier.  Mode-B gap insertion (gap $\ge \mu\cdot$
cumulative uses; no job-duration change, no delay propagation) remains a
possible future move where Mode C is gated off (wMOV).

## Hito 4b — Incremental (checker-free) Mode-C feasibility (PLANNED)

The per-decode `check_solution` call caps generations at R20/R30.  A complete
*analytic* feasibility evaluator (validated to agree with the checker over a
large sample) would remove that call from the hot loop and lift the generation
count where Mode C fires often.

## Hito 5 — Warm-start from cached MILP/topology (OPTIONAL, later)

Reverse-encode cached MILP/topology JSON solutions (numbers only — the allowed
cross-method channel) into chromosomes and inject alongside the greedy/NEH seed.
Expected benefit: stronger initial elite → faster convergence on mid-size R.

## Hito 6 — Full multi-seed battery

Run the 360-run battery (120 instances × 3 profiles) to replace the seed-1
N=1 cells with 10-seed means/variance before any quality claims.

## Metrics and ablations

- Full battery after each behaviour change; track mean relative gap vs cached
  MILP, number of infeasible runs, solve-time distribution.
- Ablations: access mode (A / A+B / A+B+C) × profile × R; warm-start seed count
  vs quality; population size vs generations-in-budget at R20/R30.

## Recommended implementation order

1. Hito 6 — full multi-seed battery to re-baseline (now the immediate step).
2. Hito 4b — checker-free Mode-C feasibility to lift R20/R30 generations.
3. Hito 5 — MILP/topology warm-start seeds (if a gap remains).
4. Hito 3 — deliberate Mode-B gaps (lowest priority; Mode C dominates).

Multi-front Mode-C rescue: **dropped** — timing genes dissolved the stuck-aircraft
case that motivated it.

---

# Part IV — How it is implemented

Source: [`theory_assisted_job.py`](theory_assisted_job.py) — class
`TheoryAssistedJobSolver`, registered as `TheoryAssistedBRKGA2` under the labels
`ta2_brkga_wMK` / `ta2_brkga_wDLY` / `ta2_brkga_wMOV` in
`experiments/run_experiments.py`.

## Solver contract (`shared/application.py`)

| member | role |
| --- | --- |
| `name` | `"theory_assisted_job"` |
| `configure_solver(**kw)` | stores all kwargs in `self._config`; honours `time_limit_s`, `weight_makespan`, `weight_delay`, `weight_movements`, `seed`, `allow_mode_c`, `timing_cap_factor` |
| `solve(instance_data)` | builds the model, determines `allow_mode_c` via the profile gate and the timing cap, runs BRKGA (pop 20·\|R\|), returns the solution dict |
| `get_config()` | returns a shallow copy of `self._config` |

### Config knobs

| key | default | meaning |
| --- | --- | --- |
| `time_limit_s` | `60.0` | wall-clock budget for the BRKGA loop |
| `weight_makespan` | `0.1` | objective weight for makespan (battery passes 100 or 1) |
| `weight_delay` | `1.0` | objective weight for total delay (battery passes 100 or 1) |
| `weight_movements` | `10.0` | objective weight for movement count (battery passes 100 or 1) |
| `seed` | `1` | RNG seed for population initialisation and crossover |
| `allow_mode_c` | *(profile gate)* | override the profile gate: `True` forces Mode-C on, `False` forces it off; absent = automatic (see gate below) |
| `timing_cap_factor` | `0.5` | timing-gene cap as a multiple of `mean_T`: a start may be delayed up to `factor·mean_T` past its earliest feasible instant; `0.0` disables timing genes (reproduces v1) |

The fitness inside the GA uses these **configured** weights, not the
`application.py` defaults.

**Profile gate:** `allow_mode_c` defaults to `True` when
`weight_movements ≤ max(weight_makespan, weight_delay)` and `False` otherwise.
Concretely: wMK (100/1/1) → gate=True (Mode-C on); wDLY (1/100/1) →
gate=True (Mode-C on); wMOV (1/1/100) → gate=False (Mode-A only, full
generation budget).  An explicit `allow_mode_c` config value overrides the gate.

## Method ↔ code map

| Method concept (Part I) | Code |
| --- | --- |
| Model (positions, arcs, chains, T, ε/μ/δ/η) | `brkga/instance.py` · `build_model` → `Model` dataclass |
| Topological position ordering | `brkga/instance.py` · `_topo_positions` (Kahn's algorithm) |
| Per-aircraft job chain | `brkga/instance.py` · `_build_chain` |
| Chromosome decode (assignment + sequencing + timing) | `brkga/decoder.py` · `decode_chromosome` (3 blocks) |
| Earliest Mode-A start sweep | `brkga/decoder.py` · `_earliest_mode_a`, `_mode_a_feasible`, `build_schedule` |
| Timing-gene placement (delay past earliest, snap to feasible) | `brkga/decoder.py` · `_apply_timing` |
| Mode-A access window computation | `brkga/access.py` · `mode_a_windows_for_position` |
| Mode-C feasible windows (Mode-A ∪ interruptible-job interiors) | `brkga/decoder.py` · `_feasible_bc_windows` |
| Mode-C greedy decision (benefit vs cost, separation guard) | `brkga/decoder.py` · `_try_mode_c` |
| Front-job interruption application (κ+1, δ extension, shift) | `brkga/decoder.py` · `_apply_interrupt` |
| Mode-C schedule construction (two-path, with fallback) | `brkga/decoder.py` · `build_schedule` (when `allow_mode_c=True`) |
| Checker-validated decode entry point | `brkga/decoder.py` · `decode` |
| Access-mode classification (mirror of checker) | `brkga/access.py` · `classify_access` |
| Movement count (mirror of checker RQ07) | `brkga/access.py` · `count_movements` |
| Interval algebra | `brkga/windows.py` · `intersect_windows`, `shift_windows`, `clip_nonnegative`, `first_point_at_or_after` |
| Schedule state | `brkga/state.py` · `ScheduleState`, `AircraftState`, `JobState` |
| Greedy/NEH warm-start seed | `brkga/warm_start.py` · `greedy_seed` → `greedy_assignment` + `reverse_encode` |
| BRKGA loop | `brkga/engine.py` · `run_brkga` |
| Objective and solution dict | `brkga/decoder.py` · `compute_objective`, `to_solution_dict` |
| Profile gate (`allow_mode_c` auto-selection) | `theory_assisted_job.py` · `solve()` (lines 81–83) |

## Key implementation notes

- `chromosome_length = 3 * num_aircraft` (property on `Model`): assignment +
  sequencing + timing blocks.  `solve()` pins population to `max(100, 20·|R|)`
  (the 2|R|-era count) so the longer chromosome does not auto-inflate it.
- The greedy/NEH seed is always the first chromosome; `reverse_encode` produces
  keys the decoder maps back to exactly the same assignment and ordering, with
  timing genes set to 0 (earliest start) — so the seed is reproduced exactly and
  `timing_cap_factor=0` reproduces the v1 schedule.
- **Timing genes (`_apply_timing`):** block 3 delays a start to
  `first_feasible(windows, earliest + gene·cap)`, `cap = factor·mean_T`; it only
  pushes later and snaps to a feasible window, so feasibility holds; applied to
  both the Mode-A start and the Mode-C reference start.
- `run_brkga` checks `time.perf_counter()` once per generation (before
  evaluating the new population), so the solver may overshoot the budget by at
  most one generation's decode batch.
- `count_movements` mirrors `checker._classify_access` at the tolerance level
  (`TOL = 1e-4`, the checker's value).  In the Mode-C path the count is
  overwritten by `rq07["movements_count"]` from the real checker report, so it
  is always checker-authoritative.
- The decoder is **deterministic** (no random jitter inside the decode), a hard
  requirement for the GA to compare individuals consistently.
- **Mode-C decoder (`build_schedule` with `allow_mode_c=True`):** for each rear
  aircraft at a position that has front constraints, `_try_mode_c` is called
  after computing the Mode-A start `s_a`.  It computes a potentially earlier
  start `s_c` against the union of Mode-A windows and interruptible-job interiors
  (`_feasible_bc_windows`), checks a profile-aware benefit/cost condition
  (`benefit = wDLY*(delay_A−delay_C) + wMK*(s_A−s_C)` vs
  `cost = wMOV*2*n_events + wDLY*extra_front_delay`), enforces a separation
  guard (no front pushed into its successor), and applies `_apply_interrupt`
  (κ+1, δ extension, shift of later jobs) in place.  The result is validated by
  the real checker (`checker.check_solution`); if any RQ07 violation or other
  infeasibility is found the decoder falls back to the always-feasible Mode-A
  build for that chromosome.  Chromosomes whose Mode-C build yields 0 movements
  skip the checker call entirely (Mode-A-equivalent path; saves time on wMOV).
- **Mode-C `decode` entry point:** `brkga/decoder.py::decode` is the single
  function called by the engine.  It dispatches to `build_schedule` with the
  appropriate `allow_mode_c` flag and `instance` dict (needed for the checker
  call); the engine passes `instance=None` when Mode-C is disabled so no checker
  import occurs in that path.
- Isolation: the `brkga/` sub-package is added to `sys.path` relative to
  `_HERE = Path(__file__).resolve().parent` (the `jobs/` directory) at the front
  of `sys.path`, so its package name does not collide with any internal modules
  loaded for `methods/brkga_v02/` in the same runner process (verified: both
  solver classes load distinctly).

## Isolation

The solver imports nothing from other methods; the only non-method imports are
the compliance checker (`problems/jobs/checker.py`) and `shared/instance_io.py`,
both allowed.  `experiments/tests/test_method_isolation.py` reports 0 violations.

## Smoke test

```
py -3 methods/theory_assisted/jobs/brkga/smoke.py 100        # decoder vs checker, 120 instances
py -3 methods/theory_assisted/jobs/theory_assisted_job.py    # full solver on one instance
```

The decoder smoke test reports, per instance: checker pass count, movement
mismatch count, best-random objective/makespan/delay/movements, and
`runtime_decoder_avg_ms`.

---

# Change log

Track the method's evolution.  One row per behaviour-affecting commit (or per
shipped milestone), newest at the bottom.

| commit | change | effect on results |
| ------ | ------ | ----------------- |
| (working tree, uncommitted; on top of `7c0c957`) | Candidate C BRKGA, second isolated attempt: mixed-chromosome decoder v0 (Mode-A only, contiguous jobs, faithful checker mirror), greedy/NEH warm-start, own deterministic BRKGA loop; registered as `ta2_brkga_*` | First subset battery (seed-1 × 3 profiles): 36/36 feasible, 0 movements; matches MILP on `scn_none`/R5, edges ahead at R30, worse on blocking-heavy R10 (expected for Mode-A-only) — see Part II |
| `5b868ff` | Mode: decoder upgraded from v0 (Mode-A only) to v1 (Mode-A + Mode-C in-sweep).  `_feasible_bc_windows`, `_try_mode_c`, `_apply_interrupt` added to `brkga/decoder.py`; `decode` entry point now runs the real checker and falls back to Mode-A on violation; profile gate in `solve()` enables Mode-C for wMK/wDLY and keeps Mode-A-only for wMOV | Seed-1 battery: gap to MILP roughly halved on blocking types (wMK full_R10 −217→−117 %, chain_R10 −51→−25 %; wDLY full_R20 −56→−21 %, R30 +9.8→+21.3 %); wMOV unchanged; 100 % compliant |
| `59ab4fe` / `4837874` | v2: timing genes — chromosome 2\|R\|→3\|R\| (block 3 = per-aircraft delay preference, `_apply_timing`); cap `timing_cap_factor·mean_T`, default 0.5 chosen by `ablation_timing.py`; population pinned to 20\|R\|.  `decode_chromosome` returns timing; `engine`/`solve` thread cap | Seeds 1–3 v2 battery (N=3): gap halved again on the dominant outlier and several R20/R30 cells now beat the MILP (full_tight_R20 wMK −95→−20 %, wDLY −35→**+24.5 %**, wMOV −196→−12 %; triangle_tight_R20 wMK +8.8 %); diagnosis: stuck-aircraft case dissolved; 100 % compliant |

---

*Keep this file in sync with `theory_assisted_job.py`: when the code changes
behaviour, invoke `/sync-method-doc methods/theory_assisted` with a brief hint
describing what changed and (if relevant) `log: <battery-log-path>` for
refreshing Part II.  Design rationale and the reading behind the method live in
[`notes/design.md`](notes/design.md) and [`notes/synthesis.md`](notes/synthesis.md).*
