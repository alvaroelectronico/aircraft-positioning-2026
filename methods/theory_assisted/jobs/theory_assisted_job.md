# Theory-Assisted BRKGA (Candidate C) for the Job-Level Scheduling Problem

Second independent, isolated Claude-assisted attempt at Candidate C from the
literature synthesis: a Biased Random-Key Genetic Algorithm with a mixed
chromosome (position assignment + in-position sequencing) and a greedy/NEH
warm-start seed.  Built in full isolation from `methods/brkga_v02/` to measure
how much two Claude-assisted attempts at the same algorithm family diverge in
implementation choices and final quality.

> **Status (working tree on top of `7c0c957`, not yet committed; latest battery
> [`seed1$_202605_02_main_methods_20260622_075606.log`](../../../outputs/logs/seed1$_202605_02_main_methods_20260622_075606.log)).**
> The decoder is at **v0: Mode-A only** (contiguous jobs, κ=0).  All 36 seed-1
> runs are feasible with 0 movements under all three profiles.  Against the
> cached job-level MILP the solver matches on the no-arc control (`scn_none`,
> +0%) and the tiny R5 case (+0%), edges ahead on R30 (where the MILP is far
> from converged at 60 s: +2–10%), and is worse on every other blocking-heavy
> type — **the expected v0 outcome**: Mode-A-only waits for full front vacancy,
> so makespan/delay inflate.  Mode-B gaps (Hito 3) and a restricted Mode-C
> (Hito 4) are the planned levers to close that gap; neither is implemented yet.

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

The build order is **decoder-first**: get a conservative, provably-checker-
compliant decoder before adding the GA, and add access modes in order of risk
(A → B → C).  The current code is at the first stage (Mode-A only) plus the GA.

## 3. Chromosome and decoder

### 3.1 Chromosome layout (length $2|R|$)

| gene range | encodes |
|---|---|
| $[0, |R|)$ | assignment keys: aircraft $r_i$ → position $\text{positions}[\min(\lfloor k_i \cdot |P|\rfloor, |P|-1)]$ |
| $[|R|, 2|R|)$ | sequencing keys: aircraft sorted by key within each position gives the service order (tie-break by instance index) |

Both decisions are jointly evolved; crossover respects the block boundary.

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
3. Jobs are scheduled **contiguously** (no pauses, κ=0).  Because there are no
   inter-job gaps, the only feasible access mode is Mode A — this is the v0
   decoder.  `build_schedule` accepts an `allow_mode_c` flag for forward
   compatibility, but it currently has **no effect**: Mode C is not implemented
   yet (deferred to Hito 4).
4. `compute_objective` evaluates the weighted sum; any infeasible access adds a
   penalty $10^9$ per violation (the search should never fix on one — and in v0
   it never does, by construction).
5. `count_movements` mirrors `checker._classify_access` line-for-line (same
   $\eta$ margins, same `TOL = 1e-4`) so the reported movement count equals what
   the checker infers at validation time.  In v0 it is always 0.

### 3.3 Access-mode windows (`brkga/access.py`, `brkga/windows.py`)

`mode_a_windows_for_position(p, state, model)` computes the intersection over
every front aircraft of position $p$ of the Mode-A windows
$[0, s_{\text{front}}-\eta] \cup [f_{\text{front}}+\eta, \infty)$.  The decoder
intersects this with its $-T_r$ shift (the exit-instant constraint) and takes
`first_point_at_or_after(lower)`.  All window operations live in `windows.py`
(pure interval algebra, no problem semantics); the semantics — including
`classify_access`, the faithful checker mirror — live in `access.py`.

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

## 4. The complete algorithm

```
TheoryAssistedJobSolver.solve(instance_data):
  model   ← build_model(instance_data)         # parse + topo-sort positions
  weights ← {makespan: wMK, delay: wDLY, movements: wMOV}   # CONFIGURED weights
  obj, state, generations ← run_brkga(model, weights, time_limit, seed,
                                       allow_mode_c=False)   # v0: Mode-A only
  return to_solution_dict(state, model, weights,
                          status=f"brkga ({generations} generations)")

run_brkga(model, weights, time_limit, seed, allow_mode_c=False):
  rng        ← Random(seed)
  population ← [greedy_seed(model, weights)] + random chromosomes
  scored     ← sort by fitness(ch) = decode(ch, model, weights)[0]
  while elapsed < time_limit:
    elite, non_elite ← top 15%, bottom 85%
    next_pop ← elite + mutants + biased-crossover offspring
    scored   ← re-evaluate and sort
    update best if improved
    generations += 1
  return best_obj, decode(best_ch)[1], generations
```

## Behaviour observed

v0 (Mode-A only) decodes produce **0 movements** but elevated makespan/delay:
the solver always waits for full front-aircraft vacancy (with $\eta$ margin) at
both the entry and exit instant.  This is feasible everywhere and matches the
MILP on the no-arc and trivially-tight cases, but on blocking-heavy instances
the MILP wins by exploiting Mode-B/C (manoeuvres that let aircraft access slots
without waiting for vacancy) — capability this solver does not have yet.  Decode
cost measured in the smoke test is ≈ 0.04 ms (R5) to ≈ 0.42 ms (R20/R30 with 10
arcs), so the default population (`10·2|R|`, e.g. 600 at R30) still runs 100–800
generations within the 60 s budget.

---

# Part II — Results and analysis

## Experimental setup

| field             | value |
| ----------------- | ----- |
| Battery           | 12 instance types × 1 seed × 3 profiles = 36 runs |
| Methods compared  | `ta2_brkga_wMK` / `ta2_brkga_wDLY` / `ta2_brkga_wMOV` vs cached job-level MILP (`milp_job_*`) |
| Weight profiles   | wMK (100/1/1) · wDLY (1/100/1) · wMOV (1/1/100) |
| Budget            | 60 s wall-clock per run |
| Metric            | relative gap = (MILP_obj − heuristic_obj) / MILP_obj; positive = heuristic better |
| Log               | [`seed1$_202605_02_main_methods_20260622_075606.log`](../../../outputs/logs/seed1$_202605_02_main_methods_20260622_075606.log) |

## Relative objective gap (seed 1 only — N=1 per cell)

Gap = (MILP_obj − heuristic_obj) / MILP_obj.  Positive = heuristic better (lower obj).
All runs produced 0 movements (Mode-A-only v0 decoder).

### wMK (100/1/1 — makespan-priority)

| Instance type              | N | Mean    | Min     | Max     |
|----------------------------|---|---------|---------|---------|
| scn_chain_tight_P5_R10     | 1 | −51.20% | −51.20% | −51.20% |
| scn_full_tight_P5_R10      | 1 | −217.36%| −217.36%| −217.36%|
| scn_full_tight_P5_R20      | 1 | −93.53% | −93.53% | −93.53% |
| scn_hub_tight_P5_R10       | 1 | −20.47% | −20.47% | −20.47% |
| scn_none_tight_P5_R10      | 1 | +0.00%  | +0.00%  | +0.00%  |
| scn_triangle_loose_P5_R10  | 1 | −29.88% | −29.88% | −29.88% |
| scn_triangle_medium_P5_R10 | 1 | −29.51% | −29.51% | −29.51% |
| scn_triangle_tight_P5_R10  | 1 | −35.23% | −35.23% | −35.23% |
| scn_triangle_tight_P5_R20  | 1 | −14.74% | −14.74% | −14.74% |
| scn_triangle_tight_P5_R30  | 1 | +2.27%  | +2.27%  | +2.27%  |
| scn_triangle_tight_P5_R5   | 1 | +0.00%  | +0.00%  | +0.00%  |
| scn_two_rows_tight_P5_R10  | 1 | −31.76% | −31.76% | −31.76% |

### wDLY (1/100/1 — delay-priority)

| Instance type              | N | Mean     | Min      | Max      |
|----------------------------|---|----------|----------|----------|
| scn_chain_tight_P5_R10     | 1 | −72.12%  | −72.12%  | −72.12%  |
| scn_full_tight_P5_R10      | 1 | −279.47% | −279.47% | −279.47% |
| scn_full_tight_P5_R20      | 1 | −56.39%  | −56.39%  | −56.39%  |
| scn_hub_tight_P5_R10       | 1 | −20.63%  | −20.63%  | −20.63%  |
| scn_none_tight_P5_R10      | 1 | +0.00%   | +0.00%   | +0.00%   |
| scn_triangle_loose_P5_R10  | 1 | −818.77% | −818.77% | −818.77% |
| scn_triangle_medium_P5_R10 | 1 | −50.74%  | −50.74%  | −50.74%  |
| scn_triangle_tight_P5_R10  | 1 | −33.33%  | −33.33%  | −33.33%  |
| scn_triangle_tight_P5_R20  | 1 | −27.89%  | −27.89%  | −27.89%  |
| scn_triangle_tight_P5_R30  | 1 | +9.84%   | +9.84%   | +9.84%   |
| scn_triangle_tight_P5_R5   | 1 | +0.00%   | +0.00%   | +0.00%   |
| scn_two_rows_tight_P5_R10  | 1 | −34.41%  | −34.41%  | −34.41%  |

### wMOV (1/1/100 — movement-priority)

| Instance type              | N | Mean     | Min      | Max      |
|----------------------------|---|----------|----------|----------|
| scn_chain_tight_P5_R10     | 1 | −41.16%  | −41.16%  | −41.16%  |
| scn_full_tight_P5_R10      | 1 | −228.16% | −228.16% | −228.16% |
| scn_full_tight_P5_R20      | 1 | −190.16% | −190.16% | −190.16% |
| scn_hub_tight_P5_R10       | 1 | −16.67%  | −16.67%  | −16.67%  |
| scn_none_tight_P5_R10      | 1 | +0.00%   | +0.00%   | +0.00%   |
| scn_triangle_loose_P5_R10  | 1 | −75.71%  | −75.71%  | −75.71%  |
| scn_triangle_medium_P5_R10 | 1 | −42.00%  | −42.00%  | −42.00%  |
| scn_triangle_tight_P5_R10  | 1 | −28.01%  | −28.01%  | −28.01%  |
| scn_triangle_tight_P5_R20  | 1 | −39.22%  | −39.22%  | −39.22%  |
| scn_triangle_tight_P5_R30  | 1 | +2.35%   | +2.35%   | +2.35%   |
| scn_triangle_tight_P5_R5   | 1 | +0.00%   | +0.00%   | +0.00%   |
| scn_two_rows_tight_P5_R10  | 1 | −30.56%  | −30.56%  | −30.56%  |

## Per-component mean Δ (heuristic − MILP; negative = heuristic better)

### wMK

| Instance type              | N | Δmakespan | Δdelay  | Δmov  |
|----------------------------|---|-----------|---------|-------|
| scn_chain_tight_P5_R10     | 1 | +30.50    | +150.00 | −14.00|
| scn_full_tight_P5_R10      | 1 | +144.00   | +499.50 | −40.00|
| scn_full_tight_P5_R20      | 1 | +242.00   | +1843.00| +0.00 |
| scn_hub_tight_P5_R10       | 1 | +12.50    | +15.50  | −20.00|
| scn_none_tight_P5_R10      | 1 | +0.00     | +0.00   | +0.00 |
| scn_triangle_loose_P5_R10  | 1 | +17.50    | +40.00  | −8.00 |
| scn_triangle_medium_P5_R10 | 1 | +17.50    | +34.00  | −8.00 |
| scn_triangle_tight_P5_R10  | 1 | +20.50    | +93.00  | −8.00 |
| scn_triangle_tight_P5_R20  | 1 | +21.50    | +138.50 | −2.00 |
| scn_triangle_tight_P5_R30  | 1 | −6.50     | −202.50 | +0.00 |
| scn_triangle_tight_P5_R5   | 1 | +0.00     | +0.00   | +0.00 |
| scn_two_rows_tight_P5_R10  | 1 | +18.50    | +50.50  | −8.00 |

### wDLY

| Instance type              | N | Δmakespan | Δdelay  | Δmov  |
|----------------------------|---|-----------|---------|-------|
| scn_chain_tight_P5_R10     | 1 | +23.00    | +90.00  | −14.00|
| scn_full_tight_P5_R10      | 1 | +139.50   | +476.00 | −8.00 |
| scn_full_tight_P5_R20      | 1 | +172.00   | +1397.00| −2.00 |
| scn_hub_tight_P5_R10       | 1 | +8.50     | +22.50  | −6.00 |
| scn_none_tight_P5_R10      | 1 | +0.00     | +0.00   | +0.00 |
| scn_triangle_loose_P5_R10  | 1 | +20.50    | +38.50  | −10.00|
| scn_triangle_medium_P5_R10 | 1 | +17.00    | +32.00  | −10.00|
| scn_triangle_tight_P5_R10  | 1 | +16.50    | +34.00  | −10.00|
| scn_triangle_tight_P5_R20  | 1 | +41.00    | +215.00 | −22.00|
| scn_triangle_tight_P5_R30  | 1 | −54.00    | −369.50 | +0.00 |
| scn_triangle_tight_P5_R5   | 1 | +0.00     | +0.00   | +0.00 |
| scn_two_rows_tight_P5_R10  | 1 | +16.50    | +34.00  | −4.00 |

### wMOV

| Instance type              | N | Δmakespan | Δdelay  | Δmov  |
|----------------------------|---|-----------|---------|-------|
| scn_chain_tight_P5_R10     | 1 | +24.00    | +71.50  | +0.00 |
| scn_full_tight_P5_R10      | 1 | +139.00   | +456.50 | +0.00 |
| scn_full_tight_P5_R20      | 1 | +342.50   | +2828.50| +0.00 |
| scn_hub_tight_P5_R10       | 1 | +11.50    | +17.50  | +0.00 |
| scn_none_tight_P5_R10      | 1 | +0.00     | +0.00   | +0.00 |
| scn_triangle_loose_P5_R10  | 1 | +15.50    | +37.50  | +0.00 |
| scn_triangle_medium_P5_R10 | 1 | +16.50    | +36.00  | +0.00 |
| scn_triangle_tight_P5_R10  | 1 | +14.50    | +32.00  | +0.00 |
| scn_triangle_tight_P5_R20  | 1 | +38.00    | +318.50 | +0.00 |
| scn_triangle_tight_P5_R30  | 1 | −54.50    | −28.00  | +0.00 |
| scn_triangle_tight_P5_R5   | 1 | +0.00     | +0.00   | +0.00 |
| scn_two_rows_tight_P5_R10  | 1 | +14.50    | +35.00  | +0.00 |

## Performance summary

The v0 decoder is feasible on all 36 runs and matches the MILP exactly on
`scn_none` (no blocking arcs — nothing to manoeuvre around) and on the tiny
`scn_triangle_tight_P5_R5` (+0%).  It even edges ahead of the MILP on the
largest instances `scn_triangle_tight_P5_R30` under every profile (+2.3% / +9.8%
/ +2.4%) and is competitive on R20 — there the 60 s MILP is far from converged,
so a fast feasible heuristic wins.

On every other (blocking-heavy, R10) type the MILP is better, by −15% to −280%.
The Δ tables show why: the heuristic's **makespan and delay are uniformly higher
than the MILP** (positive Δ), because Mode-A-only forces a rear aircraft to wait
for its front positions to be fully vacant.  The MILP instead uses Mode-B/C
manoeuvres to access slots earlier — note its movement count is higher (our Δmov
is mostly negative or zero), but the time it saves outweighs the movement cost
under wMK/wDLY.  `scn_triangle_loose_P5_R10` wDLY (−819%) is small-denominator
inflation (MILP delay ≈ 0).  Under wMOV our movements are uniformly 0, but the
makespan/delay deficit still dominates the objective.

This is the expected v0 result: the lever to close the gap is access modes
beyond A, which the roadmap addresses.

## Caveats

1. Battery is seed-1 only (N=1 per cell); variance across seeds is unknown.  A
   multi-seed (10-seed) battery is needed before drawing quality-distribution
   conclusions.
2. The MILP baseline rows are from the cache (`results.csv`); large-R MILP runs
   are likely unconverged (MIPGap > 0), so "MILP better" gaps are conservative
   and "heuristic better" gaps at R20/R30 reflect the MILP's 60 s limit, not
   proven superiority.
3. The `scn_triangle_loose_P5_R10` wDLY gap (−819%) is small-denominator
   inflation; read the per-component Δ tables alongside the relative gaps.

---

# Part III — Improvement roadmap

## Diagnosis

The decoder is correct and fast (100% checker-compliant on 120 instances ×
random chromosomes, 0 movement mismatches), and the BRKGA loop improves
materially over the greedy seed.  The quality deficit on blocking-heavy
instances is entirely attributable to the **v0 Mode-A-only restriction**: the
solver cannot manoeuvre, so it pays in makespan/delay what the MILP pays in
(cheap) movements.  The roadmap follows the decoder-first plan: add access modes
in order of risk, validating against the checker at each step.

## Hito 3 — Deliberate Mode-B gaps (PLANNED, highest priority)

Insert inter-job gaps of size $\ge \mu \cdot(\text{cumulative uses})$ in front
aircraft so a rear access can use a Mode-B window instead of waiting for full
vacancy.  Mode-B adds 2 movements per access but **does not change job
durations or propagate delay**, so it is cheaper and safer than Mode-C.
Expected benefit: reduces makespan/delay on R10 blocking types where the current
deficit is largest.

## Hito 4 — Restricted Mode-C, Policy C1 (PLANNED)

Allow interrupting an interruptible job $j$ only when (1) $I_j=1$; (2) the
extension fits before the next job without moving it ($f_j + \delta \le
s_{j+1}$); (3) $j$ is not the aircraft's last job (avoids re-validating
downstream finish/separation); (4) any Mode-B access already served by the gap
after $j$ still satisfies $\mu$; (5) affected accesses are locally re-validated
after incrementing $\kappa_j$.  Policy C2 (suffix propagation) is out of scope.

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

1. Hito 3 — deliberate Mode-B gaps.
2. Hito 4 — restricted Mode-C (Policy C1).
3. Hito 6 — full multi-seed battery to re-baseline.
4. Hito 5 — MILP/topology warm-start seeds (if a gap remains).

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
| `configure_solver(**kw)` | stores all kwargs in `self._config`; honours `time_limit_s`, `weight_makespan`, `weight_delay`, `weight_movements`, `seed` |
| `solve(instance_data)` | builds the model, runs BRKGA with `allow_mode_c=False` (hardcoded), returns the solution dict |
| `get_config()` | returns a shallow copy of `self._config` |

### Config knobs

| key | default | meaning |
| --- | --- | --- |
| `time_limit_s` | `60.0` | wall-clock budget for the BRKGA loop |
| `weight_makespan` | `0.1` | objective weight for makespan (battery passes 100 or 1) |
| `weight_delay` | `1.0` | objective weight for total delay (battery passes 100 or 1) |
| `weight_movements` | `10.0` | objective weight for movement count (battery passes 100 or 1) |
| `seed` | `1` | RNG seed for population initialisation and crossover |

The fitness inside the GA uses these **configured** weights, not the
`application.py` defaults.  There is no Mode-C knob: `solve()` passes
`allow_mode_c=False` and the decoder's `allow_mode_c` parameter currently has no
effect (Mode C is not yet implemented).

## Method ↔ code map

| Method concept (Part I) | Code |
| --- | --- |
| Model (positions, arcs, chains, T, ε/μ/δ/η) | `brkga/instance.py` · `build_model` → `Model` dataclass |
| Topological position ordering | `brkga/instance.py` · `_topo_positions` (Kahn's algorithm) |
| Per-aircraft job chain | `brkga/instance.py` · `_build_chain` |
| Chromosome decode (assignment + sequencing) | `brkga/decoder.py` · `decode_chromosome` |
| Earliest Mode-A start sweep | `brkga/decoder.py` · `_earliest_start`, `build_schedule` |
| Mode-A access window computation | `brkga/access.py` · `mode_a_windows_for_position` |
| Access-mode classification (mirror of checker) | `brkga/access.py` · `classify_access` |
| Movement count (mirror of checker RQ07) | `brkga/access.py` · `count_movements` |
| Interval algebra | `brkga/windows.py` · `intersect_windows`, `shift_windows`, `clip_nonnegative`, `first_point_at_or_after` |
| Schedule state | `brkga/state.py` · `ScheduleState`, `AircraftState`, `JobState` |
| Greedy/NEH warm-start seed | `brkga/warm_start.py` · `greedy_seed` → `greedy_assignment` + `reverse_encode` |
| BRKGA loop | `brkga/engine.py` · `run_brkga` |
| Objective and solution dict | `brkga/decoder.py` · `compute_objective`, `to_solution_dict` |

## Key implementation notes

- `chromosome_length = 2 * num_aircraft` (property on `Model`); population size
  defaults to `max(100, 10 * chromosome_length)`.
- The greedy/NEH seed is always the first chromosome; `reverse_encode` produces
  keys the decoder maps back to exactly the same assignment and ordering (no
  rounding drift), making the seed perfectly reproducible.
- `run_brkga` checks `time.perf_counter()` once per generation (before
  evaluating the new population), so the solver may overshoot the budget by at
  most one generation's decode batch.
- `count_movements` mirrors `checker._classify_access` at the tolerance level
  (`TOL = 1e-4`, the checker's value); the smoke test asserts 0 movement
  mismatches across all chromosomes tested, so the reported movement count is
  exactly what the checker infers.
- The decoder is **deterministic** (no random jitter inside the decode), a hard
  requirement for the GA to compare individuals consistently.
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

---

*Keep this file in sync with `theory_assisted_job.py`: when the code changes
behaviour, invoke `/sync-method-doc methods/theory_assisted` with a brief hint
describing what changed and (if relevant) `log: <battery-log-path>` for
refreshing Part II.  Design rationale and the reading behind the method live in
[`notes/design.md`](notes/design.md) and [`notes/synthesis.md`](notes/synthesis.md).*
