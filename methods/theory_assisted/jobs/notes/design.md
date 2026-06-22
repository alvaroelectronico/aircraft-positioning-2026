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

## Open / next
- Hito 2: greedy/NEH seed (`warm_start.py`) + own BRKGA loop (`engine.py`),
  wire `solve()`.
- Hito 3: deliberate Mode-B gaps when they reduce delay/makespan.
- Hito 4: Mode-C policy C1 (interruptible, slack `≥ δ`, not last job,
  preserves Mode-B μ, local re-validation).
