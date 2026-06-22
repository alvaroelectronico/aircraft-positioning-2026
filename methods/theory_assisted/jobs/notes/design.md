# Design notes — Candidate C (BRKGA), second isolated attempt

These are *this attempt's* design decisions, recorded as they are made.  They
are the experimental data point: the divergence between this and the first
Claude-assisted BRKGA attempt (`methods/brkga_v02/`, which is NOT read) is what
the replication experiment measures.

Solver: `jobs/theory_assisted_job.py` (class `TheoryAssistedJobSolver`,
`name = "theory_assisted_job"`).  Logic split under `jobs/brkga/`.

## Decisions confirmed with the user
- **Own BRKGA loop** (no `brkga_mp_ipr` dependency); **no IPR** initially.
- **Internal greedy/NEH warm-start** + random rest of population (no reading
  other methods, not even their cached MILP solutions for now).
- **Deterministic decoder** (same chromosome → same fitness); **no random
  jitter** inside the decode.
- **Mode C deferred**: exhaust Mode A first, then deliberate Mode-B gaps, then a
  very restricted Mode-C policy if needed.

## Key finding that shaped the decoder (verified in checker.py)
`eta` is NOT `epsilon`.  `epsilon = min_separation` (RQ08 same-position
separation).  `eta` (default 1.0) is the **margin** of the access-mode
classification (`checker.py:346-352`, `_classify_access`):
- Mode A: `τ ≤ s_front − eta` or `τ ≥ f_front + eta`
- Mode C: `s_j + eta ≤ τ ≤ f_j − eta`, interruptible only
- else infeasible

So Mode-A vacancy windows are built with an **`eta` margin**, not a float `TOL`.
`access.TOL = 1e-4` matches `checker.TOL` and is used only for boundary float
comparisons.  The decoder's `count_movements` is a faithful line-for-line mirror
of the checker's RQ07 pass so the reported movement count always equals what the
checker infers (smoke test asserts `mismatch == 0`).

## Chromosome (length 2|R|)
- genes `[0, |R|)`: assignment keys → `position = positions[min(int(key·|P|), |P|−1)]`.
- genes `[|R|, 2|R|)`: sequencing keys → aircraft in a position ordered by
  `(seq_key, aircraft_index)` (stable tie-break by instance index).

## Decoder v0 (`build_schedule`, `allow_mode_c=False`)
- Visit positions in **topological order** (front before rear), so a rear
  position's fronts are fixed when it is scheduled.
- For each aircraft in a position (seq order): `lower = max(E_r, last_finish +
  epsilon)`; jobs scheduled **contiguously**, `κ_j = 0`.
- `earliest_start`: with contiguous jobs there are no inter-job gaps ⇒ **the
  only feasible access mode is Mode A**.  The feasible start window is
  `A_p ∩ (A_p − T_r)` where `A_p` is the intersection over every front aircraft
  of `[0, s_front − eta] ∪ [f_front + eta, ∞)` (entry and exit both Mode-A).
  Window algebra in `windows.py`, semantics in `access.py`.
- Consequence (expected, not a failure): v0 waits for full front vacancy →
  movements = 0 but high makespan/delay.  Optimisation comes from BRKGA search
  over assignment+sequence, then later from Mode-B gaps / Mode-C.

## Hito 1 result (decoder only, no BRKGA yet)
`py -3 methods/theory_assisted/jobs/brkga/smoke.py 100` and a 20-chromosome
sweep over all 120 instances: **100% checker-compliant, 0 movement mismatches**.
Decoder cost ≈ 0.04 ms (R5) to ≈ 0.42 ms (R20/R30 with 10 arcs) per decode →
population `10·2|R|` (e.g. 600 at R30) gives ~200+ generations in a 60 s budget,
so the default population size is viable without trimming.

## Hito 2 (done)
Greedy/NEH seed (`warm_start.py`) + own deterministic BRKGA loop (`engine.py`),
`solve()` wired.  BRKGA improves materially over the seed.

## Hito 4 — Mode C (done; Mode B subsumed/deferred)

**Design choices (the experimental divergence point).**

1. *Where Mode C lives.*  First tried a **post-pass** local search (improve the
   Mode-A incumbent).  Measured finding: it is **inert** on a BRKGA-optimised
   Mode-A incumbent — the GA already routes delay-critical aircraft to front
   positions (which never wait), so the residual delay is intrinsic and the
   blocked rears that remain have slack (no delay to save).  Conclusion: Mode C
   must be **in the fitness**, so the GA can explore assignments that are
   Mode-A-suboptimal but Mode-C-good.  The post-pass was removed; Mode C is now
   woven into the decoder sweep (`decoder.build_schedule`, `allow_mode_c=True`).

2. *Correctness without re-deriving the checker.*  Front interruptions
   propagate (κ extends a job, shifts the front's later jobs, can affect
   separation and downstream rears).  Rather than reason about propagation
   analytically (the error-prone path the guidelines warn about), each Mode-C
   decode is **validated by the real checker** (`check_solution`, ~1.7× a decode
   — cheap).  If the build is non-compliant the decode **falls back to the
   always-feasible Mode-A build**.  Feasibility never depends on hand-rederived
   logic.

3. *Profile-aware greedy.*  Per rear, Mode C is accepted only when the weighted
   delay/makespan it saves the rear exceeds the weighted movement cost plus the
   extra delay the front extension causes; a separation guard forbids
   interruptions that would collide a front with its successor.

4. *Profile gate (independently derived).*  Mode C trades movements for time.
   When `weight_movements > max(weight_makespan, weight_delay)` (the wMOV
   profile) the trade never pays and the Mode-C build's per-rear overhead only
   steals BRKGA generations — so `solve()` disables Mode C under wMOV and runs
   pure Mode-A.  (Convergent with prior attempts arriving at "profile-gated
   Mode-C" — that convergence is itself replication data; the derivation here is
   from this attempt's own measurements.)

5. *Checker-skip fast path.*  When a Mode-C build applies no interruption
   (movements = 0) it is Mode-A-equivalent and already feasible, so the checker
   call is skipped — keeps non-Mode-C decodes fast.

**Measured (10 s budget, seed 1, A vs A+C):** wDLY +5–26 %, wMK +1–16 %, wMOV
≈ 0 % (gated to Mode-A).  Deliberate Mode-B gap insertion was not needed as a
separate move — incidental Mode-B windows are already handled by the classifier,
and Mode C is the dominant lever; explicit gap insertion remains possible future
work.

## Hito 7 — Timing genes (done)

**Why.**  `diagnose.py` on v1 `full_tight` showed the gap was serialization +
one deeply-stuck rear aircraft (R18 waiting 255 of 314), not a missing manoeuvre.
The decoder had no timing degree of freedom (earliest-feasible sweep fixed every
start), so the GA could not reshape the serialization.

**Design.**  Chromosome `2|R|→3|R|`; block 3 is a per-aircraft delay preference
(`_apply_timing`): start = `first_feasible(windows, earliest + gene·cap)`,
`cap = timing_cap_factor·mean_T`.  Deterministic (gene=0 ⇒ earliest), warm-start
genes = 0, population pinned to `20|R|`, applied to both Mode-A and Mode-C
reference starts.  This is the v2-vs-v1 experimental divergence point.

**Ablation (`ablation_timing.py`, cap=0 ≡ v1 baseline).**  cap=0.5 is the
consistent winner.  Effect on the dominant outlier (N=3): full_tight_R20
wMK −95→−20 %, wDLY −35→**+24.5 %** (beats MILP), wMOV −196→−12 %; triangle_tight_R20
wMK now +8.8 %.  Small cost on easy topologies.

**Consequence.**  `diagnose.py` on v2 `full_tight`: the stuck aircraft is gone
(wait spread, max ≈ 80, more aircraft in front positions).  → **multi-front
Mode-C rescue dropped** (no concentrated case remains).

## Open / next
- Hito 6: full 10-seed battery to replace the seeds-1–3 numbers.
- Hito 4b: checker-free Mode-C feasibility evaluator (validated vs checker) to
  lift the generation count at R20/R30 (now the main residual lever).
- Optional: warm-start from cached MILP/topology; deliberate Mode-B gaps.
