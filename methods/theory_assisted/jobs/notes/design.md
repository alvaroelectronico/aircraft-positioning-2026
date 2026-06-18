# Design — theory_assisted, attempt v06: Candidate C (BRKGA)

**Date:** 2026-06-17
**Chosen candidate:** **C — BRKGA with mixed-chromosome decoder + warm-start.**
**Status:** design agreed; implementation pending (decoder-first).

---

## 1. Why Candidate C

Candidate A (IG+VND) is exhausted — both v01 (ChatGPT) and v02 (Claude)
implemented it. Of the remaining three:

- **B (GRASP+VND+PR)** reuses A's *exact* SeqVND core (N1/N2/N3). The
  synthesis itself calls it "strictly an extension of Candidate A". With A
  done twice, B is the least differentiated contribution.
- **D (GRASP+LB)** has a real isolation-contract conflict: writing the
  Local-Branching constraint requires knowing the MILP's binary
  `x_{r,p}` variables (synthesis Open Question #4), which means reading
  `methods/manual/` (forbidden) or re-deriving the whole MILP.
- **C** is the only genuinely distinct algorithmic family
  (population-based / decoder-centric). It needs only
  `problem_statement.md` + `checker.py`. Its one risky component (the
  decoder) is exactly the piece that is independently testable against
  the checker before any GA loop exists.

## 2. Decisions taken (2026-06-17)

1. **BRKGA engine: self-implemented** (~100–150 lines), no external
   dependency. Full transparency and reproducibility; tight control for
   the custom decoder.
2. **Decoder timing: local-cost scan.** Each rear aircraft's start is
   chosen to minimise local cost `W^M·Δmakespan + W^D·delay + W^S·moves`,
   scanning candidate instants. Exploits the W^S-dominant objective
   instead of leaving quality for the GA to recover (resolves synthesis
   Open Question #1).
3. **Scope: decoder-first.** Build + validate the decoder against
   `checker.py` (0 violations on random chromosomes) before adding the
   BRKGA loop.

## 3. Two design moves that neutralise the #1 risk (decoder correctness)

The synthesis flagged "incorrect Mode-C repair silently corrupts fitness"
as the dominant risk. Two choices remove it:

### 3a. Reuse the checker's own classification
`problems/jobs/checker.py` exposes `_classify_access(tau, r_start,
r_finish, job_intervals, job_by_id, eta)`. Importing it is **legitimate**
— it is problem infrastructure (allowed: `problems/jobs/**`), not another
method. The decoder scores candidate placements with the *same* function
the checker uses → classification matches the checker by construction.
Watch the η-margin subtleties baked into that function:
- Mode A iff `τ ≤ s_r − η` or `τ ≥ f_r + η` (plus the slot-edge bands
  `[s_r−η, s_r]`, `[f_r, f_r+η]`, also treated as A).
- Mode C is the **interior** `[s_j+η, f_j−η]` of an interruptible job.
- Mode B is the inter-job gap `[f_k, s_{k+1}]`.
- Thin bands just inside a job boundary (within η) classify as
  **infeasible** — the decoder must never land an access there.

### 3b. Construct in Mode A and Mode B only (never deliberately Mode C)
Cost ranking under the benchmark weights `(W^M,W^D,W^S)=(0.1,1,10)`:
- Mode A = 0 movements (free).
- Mode B = +2 movements, no job extension.
- Mode C = +2 movements **and** +δ delay (extends the front job).

So Mode C is **dominated by Mode B** whenever a B window exists. Refusing
to target Mode C costs almost nothing and buys two structural guarantees:
- **Fronts stay fixed.** A Mode-C event would increment `κ_j` and stretch
  the front's interrupted job by δ, retroactively shifting a front we
  already froze under the topological order (§4.2). Forbidding C keeps
  the front schedules final.
- **RQ09 is trivially satisfied** (all `κ_j = 0`, every job runs at
  nominal duration).

**Feasibility is always reachable:** push a rear aircraft past the front
aircraft's finish (+η) → front position vacant → both its access instants
are Mode A. So the candidate set per rear aircraft is never empty.

Mode-C construction is logged as a documented **v2 refinement** if the
benchmark later shows it would help.

## 4. The decoder (heart of the method)

### 4.1 Chromosome — length `2|R|` (per synthesis)
- Genes `1..|R|` — **assignment keys**: `π(r) = positions[floor(key_r·|P|)]`.
  Multiple aircraft may share a position (sequential service, allowed).
- Genes `|R|+1..2|R|` — **sequencing keys**: within each position,
  service order = ascending sequencing key.

### 4.2 Decode procedure
1. Assign every aircraft to a position from its assignment key.
2. **Topologically order the positions** by the blocking DAG `G=(P,A)`
   — *front positions first*. (DAG ⇒ a topo order exists.) When we place
   a rear aircraft, all its fronts are already fixed, so its Mode A/B
   classification is final and never retroactively invalidated.
3. For each position in topo order, take its aircraft in sequencing-key
   order and place them sequentially (≥ ε after the previous aircraft's
   finish at that position — RQ08):
   - Build the candidate start-time set for the aircraft (see §4.3).
   - For each candidate start, lay the job chain out compactly (jobs
     back-to-back, respecting precedence and `E_r`), compute entry
     `s_r` and exit `f_r`, and classify **both** access instants against
     **every** front on incident blocking arcs via `_classify_access`.
   - Reject candidates that yield Mode C or infeasible on any arc, or
     that violate the cumulative-μ rule on a Mode-B gap given current
     gap usage.
   - Among survivors, pick the start minimising local cost
     `W^M·Δm + W^D·max(0,f_r−L_r) + W^S·(#movements)`.
   - Commit; update per-front Mode-B `gap_uses` counters.
4. Assemble the solution dict; compute exact metrics + weighted objective
   (this exact objective is the GA fitness, not the greedy local cost).

### 4.3 Candidate start-time set per rear aircraft
Generated from already-fixed fronts so accesses land in safe A/B regions:
- `E_r` and `prev_finish + ε` (earliest feasible).
- For each incident front aircraft `r`: `f_r + η` (Mode-A-after) and, per
  inter-job gap, a point centred in `[f_k, s_{k+1}]` (Mode-B) when the gap
  ≥ μ·(uses+1).
- A safe late fallback (after the latest incident front finishes) that is
  guaranteed Mode A on every arc.
Cap the set (e.g. ≤ ~50 instants) and `log()` if truncated — no silent caps.

### 4.4 Output shape (per checker / Application)
```
{"status", "objective", "metrics": {"makespan","total_delay","movements"},
 "aircraft": [{"id","position","start","finish","delay",
               "jobs":[{"id","start","finish"}, ...]}, ...]}
```

## 5. BRKGA loop (self-implemented)
- Population `|P_pop| = max(100, 10·n)`, `n = 2|R|`.
- Elite fraction 15%, mutant fraction 10%, biased crossover `ρ = 0.7`.
- Generational: keep elites, fill from elite×non-elite biased crossover,
  inject fresh mutants.
- Shake on stagnation (`I_shake ≈ 50` gens no-improve): resample
  non-elites, keep elites.
- Terminate on `time_limit_s` (Application guarantees this key).
- Determinism: seed the RNG from a `seed` config key (script env forbids
  `Math.random`-style nondeterminism; pass an explicit seed).

## 6. Warm-start
Reverse-encode cached baseline solutions (read-only, **numbers only**)
from `outputs/solutions/scn_…__milp_baseline_job__*.json` and topology
heuristic JSONs into chromosomes injected into the initial population:
- assignment key for `r` ← `(index(π(r)) + 0.5)/|P|`.
- sequencing keys ← rank of `s_r` within each position.
Reading these JSONs is allowed (results, not other methods' source).

## 7. Module layout (under `methods/theory_assisted/jobs/`)
- `theory_assisted_job.py` — `TheoryAssistedJobSolver` (Application
  contract); `solve()` wires decoder + BRKGA, honours `time_limit_s`,
  `weight_*`, `seed`.
- `decoder.py` — chromosome → solution dict; imports `_classify_access`
  from `problems/jobs/checker.py`. Independently testable.
- `brkga.py` — generic BRKGA over random keys, decoder injected.
- `warmstart.py` — reverse-encode cached JSONs → chromosomes.

## 8. Validation plan
1. **Decoder smoke test (milestone 1):** decode 10+ random chromosomes
   for `scn_triangle_tight_P5_R5_seed1`; assert `check_solution`
   compliant (0 violations) every time. No GA yet.
2. **BRKGA on one instance:** 60 s on the same instance; compare
   objective to cached `milp_baseline_job` row in `results.csv`.
3. **Standard battery (milestone 2):** all three weight profiles
   `wMK`/`wDLY`/`wMOV`, paired vs cached MILP via
   `experiments/paired_report.py` (see BATTERY.md). Then
   `/sync-method-doc`.

## 8b. v2 — Mode-C construction via fixpoint (2026-06-18)

The first battery (commit 2d37eeb, log `202605_02_main_methods_20260618_064914`)
showed the Mode-A/B-only decoder loses to the cached MILP on R5–R10 across all
three profiles: it drives movements to 0 (Δmov ≤ 0) but inflates makespan/delay
(large +Δ).  Root cause: under **wMK/wDLY** a movement is cheap (weight 1) while
waiting for a Mode-A/B window costs +30 makespan or +150 delay — so refusing
Mode C is the wrong trade there.  §3b's exclusion was right only for the
default/wMOV profile.

**v2 lifts the restriction with a fixpoint that resolves the Mode-C cascade.**
A Mode-C event extends the (already-placed) front job by δ, which would ripple
backward.  Instead of mutating fronts mid-pass, each pass lays out every
aircraft with the front extensions `kappa` **held fixed from the previous
pass**, choosing the best A/B/**C** placement against those frozen fronts, then
recomputes `kappa` from the Mode-C events observed.  When `kappa` stops changing
the schedule is self-consistent (front job durations match their Mode-C counts →
RQ09 holds).  Non-convergence within `max_fixpoint_iters` (=8) → fall back to the
A/B-only pass (`kappa={}`, always consistent).  `allow_mode_c` config flag keeps
v1 reachable for ablation.

The local-cost scan adds a rough downstream estimate `(W^M+W^D)·δ` per Mode-C
event so the greedy is biased against extensions that won't pay off; under wMOV
the +2·W^S movement cost already suppresses Mode C (fixpoint converges in one
pass, ~no overhead).

**8 s probe (v1=A/B vs v2=+C vs cached MILP), seed1:** v2 improves wMK/wDLY
substantially — chain_R10 wDLY 21739→11534 (beats MILP 12491); triangle_R10 wMK
7869→6454, wDLY 14533→11771; full_R10 wMK 11949→9325.  wMOV unchanged (correct).
One case (full_R10 wDLY) where the greedy over-uses Mode C; left for the full
60 s battery + GA to resolve.  A per-decode A/B floor was tried and reverted: it
doubles decode cost and the lost GA generations hurt more than the floor helps.

**Open v2 follow-ups:** (i) sharpen the Mode-C downstream cost estimate to cut
the occasional misfire; (ii) warm-start (`warmstart.py`) still unimplemented;
(iii) re-run the standard battery to measure v2 vs MILP across all 360 runs.

## 9. Open questions / risks carried forward
- **Q1 (resolved by §3b for v1):** Mode-C construction deferred to v2.
- **Q2 — small instances (|R|=5):** population may be larger than the
  useful search space; warm-start + low mutant rate should still help.
  Watch whether BRKGA beats a single greedy decode at all on R=5.
- **Q3 — decoder cost:** candidate-scan × |incident fronts| per aircraft;
  bounded by §4.3 cap. Profile on the largest instance before the battery.
- **Q4 — chain compactness:** v1 lays each chain compactly (no internal
  idle). Allowing internal slack to slide the exit into a cheaper window
  is a v2 lever (interacts with Mode-B μ).
```
