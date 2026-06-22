# Theory-Assisted BRKGA (Candidate C) for the Job-Level Scheduling Problem

Second independent, isolated Claude-assisted attempt at Candidate C from the
literature synthesis: a Biased Random-Key Genetic Algorithm with a mixed
chromosome (position assignment + in-position sequencing) and a greedy/NEH
warm-start seed.  Built in full isolation from `methods/brkga_v02/` to measure
how much two Claude-assisted attempts at the same algorithm family diverge in
implementation choices and final quality.

> **Status (code `5b868ff`, latest battery
> [`seed1$_202605_02_main_methods_20260622_124508.log`](../../../outputs/logs/seed1$_202605_02_main_methods_20260622_124508.log)).**
> The decoder is now at **v1: Mode-A + Mode-C (in-sweep, profile-gated)**.
> Mode-C is live for wMK and wDLY profiles (where the time saving outweighs
> the 2-movement cost); wMOV keeps the Mode-A-only path unchanged.  Part II
> now reflects the first Mode-C battery (seed-1, 36 runs).  Mode-C reduces
> the gap on most R10 blocking types but does not close it; the full multi-seed
> battery (Hito 6) is the next measurement step.

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

## 4. The complete algorithm

```
TheoryAssistedJobSolver.solve(instance_data):
  model   ← build_model(instance_data)         # parse + topo-sort positions
  weights ← {makespan: wMK, delay: wDLY, movements: wMOV}   # CONFIGURED weights
  gate    ← wMOV <= max(wMK, wDLY)             # Mode-C profile gate
  allow_mode_c ← config.get("allow_mode_c", gate)
  obj, state, generations ← run_brkga(model, weights, time_limit, seed,
                                       allow_mode_c, instance if allow_mode_c else None)
  return to_solution_dict(state, model, weights,
                          status=f"brkga ({generations} generations, mode {A|A+C})")

run_brkga(model, weights, time_limit, seed, allow_mode_c, instance):
  rng        ← Random(seed)
  population ← [greedy_seed(model, weights)] + random chromosomes
  scored     ← sort by fitness(ch) = decode(ch, model, weights, allow_mode_c, instance)[0]
  while elapsed < time_limit:
    elite, non_elite ← top 15%, bottom 85%
    next_pop ← elite + mutants + biased-crossover offspring
    scored   ← re-evaluate and sort
    update best if improved
    generations += 1
  return best_obj, decode(best_ch, …)[1], generations

decode(ch, model, weights, allow_mode_c, instance):
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
| Battery           | 12 instance types × 1 seed × 3 profiles = 36 runs |
| Methods compared  | `ta2_brkga_wMK` / `ta2_brkga_wDLY` / `ta2_brkga_wMOV` vs cached job-level MILP (`milp_job_*`) |
| Weight profiles   | wMK (100/1/1) · wDLY (1/100/1) · wMOV (1/1/100) |
| Budget            | 60 s wall-clock per run |
| Metric            | relative gap = (MILP_obj − heuristic_obj) / MILP_obj; positive = heuristic better |
| Log               | [`seed1$_202605_02_main_methods_20260622_124508.log`](../../../outputs/logs/seed1$_202605_02_main_methods_20260622_124508.log) |

## Relative objective gap (seed 1 only — N=1 per cell)

Gap = (MILP_obj − heuristic_obj) / MILP_obj.  Positive = heuristic better (lower obj).
wMK and wDLY use the Mode-A + Mode-C (v1) decoder; wMOV uses Mode-A-only.

### wMK (100/1/1 — makespan-priority)

| Instance type              | N | Mean     | Min      | Max      |
|----------------------------|---|----------|----------|----------|
| scn_chain_tight_P5_R10     | 1 | −25.40%  | −25.40%  | −25.40%  |
| scn_full_tight_P5_R10      | 1 | −116.61% | −116.61% | −116.61% |
| scn_full_tight_P5_R20      | 1 | −64.78%  | −64.78%  | −64.78%  |
| scn_hub_tight_P5_R10       | 1 | −20.47%  | −20.47%  | −20.47%  |
| scn_none_tight_P5_R10      | 1 | +0.00%   | +0.00%   | +0.00%   |
| scn_triangle_loose_P5_R10  | 1 | −25.67%  | −25.67%  | −25.67%  |
| scn_triangle_medium_P5_R10 | 1 | −23.05%  | −23.05%  | −23.05%  |
| scn_triangle_tight_P5_R10  | 1 | −18.01%  | −18.01%  | −18.01%  |
| scn_triangle_tight_P5_R20  | 1 | −6.70%   | −6.70%   | −6.70%   |
| scn_triangle_tight_P5_R30  | 1 | +9.04%   | +9.04%   | +9.04%   |
| scn_triangle_tight_P5_R5   | 1 | +0.00%   | +0.00%   | +0.00%   |
| scn_two_rows_tight_P5_R10  | 1 | −5.06%   | −5.06%   | −5.06%   |

### wDLY (1/100/1 — delay-priority)

| Instance type              | N | Mean     | Min      | Max      |
|----------------------------|---|----------|----------|----------|
| scn_chain_tight_P5_R10     | 1 | −38.84%  | −38.84%  | −38.84%  |
| scn_full_tight_P5_R10      | 1 | −125.51% | −125.51% | −125.51% |
| scn_full_tight_P5_R20      | 1 | −21.42%  | −21.42%  | −21.42%  |
| scn_hub_tight_P5_R10       | 1 | −17.96%  | −17.96%  | −17.96%  |
| scn_none_tight_P5_R10      | 1 | +0.00%   | +0.00%   | +0.00%   |
| scn_triangle_loose_P5_R10  | 1 | −330.97% | −330.97% | −330.97% |
| scn_triangle_medium_P5_R10 | 1 | −6.37%   | −6.37%   | −6.37%   |
| scn_triangle_tight_P5_R10  | 1 | −15.71%  | −15.71%  | −15.71%  |
| scn_triangle_tight_P5_R20  | 1 | −15.14%  | −15.14%  | −15.14%  |
| scn_triangle_tight_P5_R30  | 1 | +21.29%  | +21.29%  | +21.29%  |
| scn_triangle_tight_P5_R5   | 1 | +0.00%   | +0.00%   | +0.00%   |
| scn_two_rows_tight_P5_R10  | 1 | −4.06%   | −4.06%   | −4.06%   |

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

| Instance type              | N | Δmakespan | Δdelay   | Δmov   |
|----------------------------|---|-----------|----------|--------|
| scn_chain_tight_P5_R10     | 1 | +15.00    | +80.50   | +0.00  |
| scn_full_tight_P5_R10      | 1 | +77.50    | +244.00  | −22.00 |
| scn_full_tight_P5_R20      | 1 | +172.00   | +818.50  | +18.00 |
| scn_hub_tight_P5_R10       | 1 | +12.50    | +15.50   | −20.00 |
| scn_none_tight_P5_R10      | 1 | +0.00     | +0.00    | +0.00  |
| scn_triangle_loose_P5_R10  | 1 | +15.00    | +27.00   | +4.00  |
| scn_triangle_medium_P5_R10 | 1 | +13.50    | +33.50   | +4.00  |
| scn_triangle_tight_P5_R10  | 1 | +10.50    | +37.50   | +4.00  |
| scn_triangle_tight_P5_R20  | 1 | +10.50    | −21.50   | +10.00 |
| scn_triangle_tight_P5_R30  | 1 | −27.00    | −696.50  | +8.00  |
| scn_triangle_tight_P5_R5   | 1 | +0.00     | +0.00    | +0.00  |
| scn_two_rows_tight_P5_R10  | 1 | +3.00     | +1.50    | +0.00  |

### wDLY

| Instance type              | N | Δmakespan | Δdelay   | Δmov   |
|----------------------------|---|-----------|----------|--------|
| scn_chain_tight_P5_R10     | 1 | +8.00     | +48.50   | −6.00  |
| scn_full_tight_P5_R10      | 1 | +77.50    | +213.50  | +8.00  |
| scn_full_tight_P5_R20      | 1 | +114.50   | +530.00  | +16.00 |
| scn_hub_tight_P5_R10       | 1 | +13.50    | +19.50   | −2.00  |
| scn_none_tight_P5_R10      | 1 | +0.00     | +0.00    | +0.00  |
| scn_triangle_loose_P5_R10  | 1 | +8.50     | +15.50   | +2.00  |
| scn_triangle_medium_P5_R10 | 1 | +0.50     | +4.00    | +2.00  |
| scn_triangle_tight_P5_R10  | 1 | +11.50    | +16.00   | −6.00  |
| scn_triangle_tight_P5_R20  | 1 | +38.50    | +116.50  | −10.00 |
| scn_triangle_tight_P5_R30  | 1 | −69.50    | −800.00  | +8.00  |
| scn_triangle_tight_P5_R5   | 1 | +0.00     | +0.00    | +0.00  |
| scn_two_rows_tight_P5_R10  | 1 | −1.00     | +4.00    | +4.00  |

### wMOV

| Instance type              | N | Δmakespan | Δdelay   | Δmov   |
|----------------------------|---|-----------|----------|--------|
| scn_chain_tight_P5_R10     | 1 | +24.00    | +71.50   | +0.00  |
| scn_full_tight_P5_R10      | 1 | +139.00   | +456.50  | +0.00  |
| scn_full_tight_P5_R20      | 1 | +342.50   | +2828.50 | +0.00  |
| scn_hub_tight_P5_R10       | 1 | +11.50    | +17.50   | +0.00  |
| scn_none_tight_P5_R10      | 1 | +0.00     | +0.00    | +0.00  |
| scn_triangle_loose_P5_R10  | 1 | +15.50    | +37.50   | +0.00  |
| scn_triangle_medium_P5_R10 | 1 | +16.50    | +36.00   | +0.00  |
| scn_triangle_tight_P5_R10  | 1 | +14.50    | +32.00   | +0.00  |
| scn_triangle_tight_P5_R20  | 1 | +38.00    | +318.50  | +0.00  |
| scn_triangle_tight_P5_R30  | 1 | −54.50    | −28.00   | +0.00  |
| scn_triangle_tight_P5_R5   | 1 | +0.00     | +0.00    | +0.00  |
| scn_two_rows_tight_P5_R10  | 1 | +14.50    | +35.00   | +0.00  |

## Performance summary

The v1 decoder (Mode-A + Mode-C, profile-gated) is feasible on all 36 runs.
It matches the MILP exactly on `scn_none` (no blocking arcs) and on
`scn_triangle_tight_P5_R5`, and edges ahead on the largest instances
`scn_triangle_tight_P5_R30` (+9.0% / +21.3% / +2.4%).

**wMK:** Mode-C activates and cuts the makespan/delay deficits roughly in half
versus v0 on most R10 types.  Gaps range from −5% to −117%; `scn_full_tight`
types remain wide because their dense blocking leaves little room for profitable
interruptions.  The Δmov column now shows positive values on some triangle
types (+4 movements per run) — Mode-C did trigger and reduced makespan, but the
MILP still wins on the time components.  On `scn_full_tight_P5_R20` wMK,
Δmov = +18 (heuristic has more movements than MILP), an unusual case where the
in-sweep Mode-C triggered many times but did not fully recover the time deficit.

**wDLY:** Mode-C is most effective here: the gap on `scn_triangle_medium_P5_R10`
closes to −6.4% (was −51%) and `scn_two_rows` narrows to −4.1% (was −34%).
`scn_triangle_loose_P5_R10` retains a large negative figure (−331%) due to
small-denominator inflation (MILP delay ≈ 0); read the Δ table (Δdelay = +15.5)
for the true magnitude.

**wMOV:** Mode-C is gated off for wMOV (weight_movements=100 dominates);
the numbers are identical to v0 — movements remain 0, makespan/delay deficits
persist unchanged.

The gap reduction from Mode-C is real but partial: on `scn_full_tight` the deep
blocking graph means many rear aircraft are constrained by multiple front
positions simultaneously, limiting how many Mode-C interruptions are beneficial
and leaving large makespan/delay residuals.  Hito 6 (full multi-seed battery)
is needed to confirm these N=1 figures have low variance.

## Caveats

1. Battery is seed-1 only (N=1 per cell); variance across seeds is unknown.  A
   multi-seed (10-seed) battery is needed before drawing quality-distribution
   conclusions.
2. The MILP baseline rows are from the cache (`results.csv`); large-R MILP runs
   are likely unconverged (MIPGap > 0), so "MILP better" gaps are conservative
   and "heuristic better" gaps at R20/R30 reflect the MILP's 60 s limit, not
   proven superiority.
3. The `scn_triangle_loose_P5_R10` wDLY gap (−331%) is small-denominator
   inflation (MILP delay ≈ 0); read the per-component Δ tables alongside the
   relative gaps for this type.
4. This battery was run from `e282385+dirty` (Mode-C enabled on HEAD `5b868ff`);
   the `+dirty` flag means the working tree had uncommitted edits at run time.
   The Mode-C logic in `decoder.py` was already finalised at `5b868ff`.

---

# Part III — Improvement roadmap

## Diagnosis

The decoder is correct and fast (100% checker-compliant on 120 instances ×
random chromosomes, 0 movement mismatches), and the BRKGA loop improves
materially over the greedy seed.  Mode C in the fitness (§3.6) roughly halves
the gap to the MILP on blocking-heavy types.  The residual deficit has two
sources: (a) the MILP's joint timing/assignment optimisation that the greedy
contiguous decoder does not match, and (b) fewer BRKGA generations at R20/R30
when Mode C fires often (the per-decode checker call).  The roadmap addresses
both.

## Hito 4 — Mode C in the fitness (DONE, commit `5b868ff`)

Mode C is woven into the decoder sweep (§3.6): per-rear profile-aware greedy,
real-checker validation with Mode-A fallback, a separation guard, and a profile
gate (off under wMOV).  Measured (seed-1): wMK gaps e.g. full_R10 −217→−117 %,
chain_R10 −51→−25 %; wDLY full_R20 −56→−21 %, R30 +9.8→+21.3 %; wMOV unchanged.

## Hito 3 — Deliberate Mode-B gaps (NOT DONE; lower priority)

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

1. Hito 6 — full multi-seed battery to re-baseline the seed-1 numbers.
2. Hito 4b — checker-free Mode-C feasibility to lift R20/R30 generations.
3. Hito 5 — MILP/topology warm-start seeds (if a gap remains).
4. Hito 3 — deliberate Mode-B gaps (lowest priority; Mode C dominates).

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
| `configure_solver(**kw)` | stores all kwargs in `self._config`; honours `time_limit_s`, `weight_makespan`, `weight_delay`, `weight_movements`, `seed`, `allow_mode_c` |
| `solve(instance_data)` | builds the model, determines `allow_mode_c` via the profile gate, runs BRKGA, returns the solution dict |
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
| Chromosome decode (assignment + sequencing) | `brkga/decoder.py` · `decode_chromosome` |
| Earliest Mode-A start sweep | `brkga/decoder.py` · `_earliest_mode_a`, `build_schedule` |
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

- `chromosome_length = 2 * num_aircraft` (property on `Model`); population size
  defaults to `max(100, 10 * chromosome_length)`.
- The greedy/NEH seed is always the first chromosome; `reverse_encode` produces
  keys the decoder maps back to exactly the same assignment and ordering (no
  rounding drift), making the seed perfectly reproducible.
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

---

*Keep this file in sync with `theory_assisted_job.py`: when the code changes
behaviour, invoke `/sync-method-doc methods/theory_assisted` with a brief hint
describing what changed and (if relevant) `log: <battery-log-path>` for
refreshing Part II.  Design rationale and the reading behind the method live in
[`notes/design.md`](notes/design.md) and [`notes/synthesis.md`](notes/synthesis.md).*
