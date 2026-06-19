# Theory-Assisted BRKGA for the aircraft-positioning jobs extension (paper #2)

BRKGA (Biased Random-Key Genetic Algorithm) with a mixed-chromosome decoder for the
job-level scheduling variant of the aircraft-positioning problem.  Developed in
isolation under `methods/theory_assisted/` as Candidate C of the synthesis menu
produced by the `/synthesize-theory` skill.  The solver is Claude-assisted: the
algorithm was chosen from the curated literature digests in
`methods/theory_assisted/digest/` and designed from `problems/jobs/problem_statement.md`
and `problems/jobs/checker.py` without reading any other method's source.

> **Status (code 22c65fb, latest battery `202605_02_main_methods_20260619_070616.log`).**
> 360/360 runs feasible.  Decoder v2 (Mode-C construction via κ fixpoint) is a
> large improvement over v1 on wMK and wDLY: e.g. `scn_chain_tight_P5_R10` wMK
> goes from −45.8% to −18.5%, and the extreme `scn_triangle_tight_P5_R5` wDLY
> artefact drops from −1322% to −3.2%.  `scn_triangle_tight_P5_R20` becomes
> positive under wMK (+8.0%) and wDLY (+7.2%).  However, wMOV regresses on large
> instances: `scn_full_tight_P5_R20` falls from −42% to −120%, and
> `scn_triangle_tight_P5_R30` drops from +21.4% to +1.6%.  Root cause is NOT
> added movements (Δmov ≈ 0 under wMOV) but decode-cost starvation — fixpoint
> iteration per chromosome is expensive enough that large-R runs overshoot the
> 60 s budget (observed 72–80 s) and the GA completes far fewer generations.
> Priority next step: cap fixpoint cost on large instances (e.g. reduce
> `max_fixpoint_iters` by instance size, or skip Mode-C when wMOV is large).

---

# Part I — The method

## 1. Problem recap and notation

(write the problem in this method's terms, using the notation from
`problems/jobs/problem_statement.md`.  Keep it short — a page max.)

## 2. Design principle

(write the core insight this method is built on.  One paragraph.
For BRKGA: the key insight is separating the combinatorial decisions —
which aircraft goes where, and in what service order — from the timing
decisions, encoding both in a random-key chromosome so the GA can
explore the combinatorial space while the decoder resolves timing
deterministically and optimally for each chromosome.  The decoder
exploits the topological order of the blocking DAG to guarantee that
front aircraft are fixed before rear aircraft are placed, so access
classification is final and never retroactively invalidated.)

## 3. Chromosome encoding

(write the two-part chromosome structure: assignment genes + sequencing genes,
each of length |R|.  Document the mapping from gene value to decision:
assignment key → position index; sequencing key → service order within position.)

## 4. Decoder

(write the decode procedure: topological placement, candidate-start-time
generation, local-cost scan, Mode-A/B/C classification via `_classify_access`,
cumulative-μ enforcement on Mode-B gaps, Mode-C fixpoint, safe-late fallback.
Reference §4.2–4.4 of `notes/design.md`.)

## 5. BRKGA engine

(write the GA loop: population size, elite/mutant fractions, biased crossover
probability ρ, shake-on-stagnation trigger, wall-clock termination.)

## 6. The complete algorithm in pseudocode

```
BRKGA(instance, time_limit_s, seed):
  ctx  ← DecoderContext(instance, weights)
  pop  ← initialise(pop_size, n_keys=2|R|, warmstarts, rng)
  scored ← sort([(decode(k), k) for k in pop])
  best ← scored[0]
  stagnant ← 0
  while elapsed < time_limit_s:
    elites    ← scored[:n_elite]
    next_pop  ← elites + mutants + biased_crossover(elites, non_elites)
    scored    ← sort([(decode(k), k) for k in next_pop])
    if scored[0] < best: best ← scored[0]; stagnant ← 0
    else:                 stagnant += 1
    if stagnant ≥ shake_after:
      scored ← elites + resample(non_elites); stagnant ← 0
  return decode(best_keys)

decode(keys, ctx):
  assign each aircraft r to position positions[floor(keys[r]*|P|)]
  sort aircraft within each position by ascending keys[|R|+r]
  kappa ← {}
  for iter in 1..max_fixpoint_iters:
    placed, new_kappa ← decode_pass(ctx, at_position, kappa, allow_mode_c=True)
    if new_kappa == kappa: return assemble(placed, ctx)   // fixpoint reached
    kappa ← new_kappa
  // Not converged — fall back to Mode-A/B-only pass
  placed, _ ← decode_pass(ctx, at_position, kappa={}, allow_mode_c=False)
  return assemble(placed, ctx)

decode_pass(ctx, at_position, kappa, allow_mode_c):
  for pos in topological_order(blocking_DAG):
    for r in at_position[pos] (sequencing order):
      proc ← proc_time[r] + delta * sum(kappa[(r,j)] for j in chain[r])
      cands ← candidate_starts(r, fronts_fixed_above, proc, allow_mode_c)
      best_s ← argmin_{s in cands} local_cost(r, s, fronts, kappa)
      commit(r, best_s); update gap_uses; record modeC events
  return placed, modeC_counts
```

## Behaviour observed

(write after the first battery runs.  v2: Mode-C construction substantially
reduces makespan and delay inflation on R5–R10 instances compared to v1.  The
fixpoint cost stresses the wall-clock budget on large instances (R20/R30),
causing wMOV regression despite Δmov remaining near zero.)

---

# Part II — Results and analysis

## Experimental setup

| field             | value |
| ----------------- | ----- |
| Battery           | Standard paper-#2 battery (`experiments/BATTERY.md`): 12 instance types × 10 seeds × 3 weight profiles = 360 runs |
| Methods compared  | `ta_brkga_wMK` / `ta_brkga_wDLY` / `ta_brkga_wMOV` vs cached `milp_job_wMK` / `milp_job_wDLY` / `milp_job_wMOV` |
| Weight profiles   | wMK (100/1/1) / wDLY (1/100/1) / wMOV (1/1/100) |
| Budget            | 60 s wall-clock per run |
| Metric            | relative gap = (MILP_obj − heuristic_obj) / MILP_obj; gap > 0 means heuristic BETTER |
| Log               | [`outputs/logs/202605_02_main_methods_20260619_070616.log`](../../../outputs/logs/202605_02_main_methods_20260619_070616.log) |

## Relative objective gap (mean / min / max over seeds)

### wMK (100/1/1 — makespan-priority)

| Instance type | N | Mean | Min | Max |
| --- | --- | --- | --- | --- |
| scn_chain_tight_P5_R10 | 10 | −18.46% | −36.41% | −8.60% |
| scn_full_tight_P5_R10 | 10 | −31.10% | −43.38% | −7.25% |
| scn_full_tight_P5_R20 | 10 | −2.45% | −47.76% | +31.58% |
| scn_hub_tight_P5_R10 | 10 | −13.64% | −30.85% | −5.18% |
| scn_none_tight_P5_R10 | 10 | +0.00% | +0.00% | +0.00% |
| scn_triangle_loose_P5_R10 | 10 | −10.02% | −17.70% | −4.33% |
| scn_triangle_medium_P5_R10 | 10 | −8.03% | −15.75% | −3.18% |
| scn_triangle_tight_P5_R10 | 10 | −6.76% | −10.10% | −3.84% |
| scn_triangle_tight_P5_R20 | 10 | **+8.00%** | +1.23% | +15.48% |
| scn_triangle_tight_P5_R30 | 10 | **+21.68%** | +11.88% | +28.86% |
| scn_triangle_tight_P5_R5 | 10 | −0.08% | −0.54% | +0.00% |
| scn_two_rows_tight_P5_R10 | 10 | −5.15% | −10.25% | −1.80% |

### wDLY (1/100/1 — delay-priority)

| Instance type | N | Mean | Min | Max |
| --- | --- | --- | --- | --- |
| scn_chain_tight_P5_R10 | 10 | −23.52% | −92.51% | +7.66% |
| scn_full_tight_P5_R10 | 10 | −21.35% | −40.26% | −0.52% |
| scn_full_tight_P5_R20 | 10 | **+16.47%** | −12.24% | +36.50% |
| scn_hub_tight_P5_R10 | 10 | −11.05% | −26.68% | −1.20% |
| scn_none_tight_P5_R10 | 10 | −0.00% | −0.00% | +0.00% |
| scn_triangle_loose_P5_R10 | 10 | −711.65% | −1674.23% | −153.35% |
| scn_triangle_medium_P5_R10 | 10 | −11.34% | −37.60% | +15.90% |
| scn_triangle_tight_P5_R10 | 10 | −7.79% | −15.17% | −1.43% |
| scn_triangle_tight_P5_R20 | 10 | **+7.19%** | −10.15% | +23.87% |
| scn_triangle_tight_P5_R30 | 10 | **+16.81%** | −2.84% | +37.16% |
| scn_triangle_tight_P5_R5 | 10 | −3.22% | −12.12% | +0.00% |
| scn_two_rows_tight_P5_R10 | 10 | −4.00% | −10.79% | +4.95% |

### wMOV (1/1/100 — movement-priority)

| Instance type | N | Mean | Min | Max |
| --- | --- | --- | --- | --- |
| scn_chain_tight_P5_R10 | 10 | −34.48% | −72.06% | +12.22% |
| scn_full_tight_P5_R10 | 10 | −59.45% | −95.32% | −20.88% |
| scn_full_tight_P5_R20 | 10 | −120.32% | −181.99% | −93.09% |
| scn_hub_tight_P5_R10 | 10 | −17.96% | −25.73% | −13.33% |
| scn_none_tight_P5_R10 | 10 | −0.06% | −0.62% | +0.00% |
| scn_triangle_loose_P5_R10 | 10 | −67.24% | −109.63% | +0.75% |
| scn_triangle_medium_P5_R10 | 10 | −29.74% | −63.67% | +9.60% |
| scn_triangle_tight_P5_R10 | 10 | −19.29% | −40.36% | +8.19% |
| scn_triangle_tight_P5_R20 | 10 | −8.07% | −28.85% | +10.78% |
| scn_triangle_tight_P5_R30 | 10 | +1.56% | −25.88% | +18.41% |
| scn_triangle_tight_P5_R5 | 10 | −20.00% | −74.29% | +0.00% |
| scn_two_rows_tight_P5_R10 | 10 | −19.24% | −40.71% | +3.09% |

### All profiles aggregated

| Instance type | N | Mean | Min | Max |
| --- | --- | --- | --- | --- |
| scn_chain_tight_P5_R10 | 30 | −25.49% | −92.51% | +12.22% |
| scn_full_tight_P5_R10 | 30 | −37.30% | −95.32% | −0.52% |
| scn_full_tight_P5_R20 | 30 | −35.43% | −181.99% | +36.50% |
| scn_hub_tight_P5_R10 | 30 | −14.22% | −30.85% | −1.20% |
| scn_none_tight_P5_R10 | 30 | −0.02% | −0.62% | +0.00% |
| scn_triangle_loose_P5_R10 | 30 | −262.97% | −1674.23% | +0.75% |
| scn_triangle_medium_P5_R10 | 30 | −16.37% | −63.67% | +15.90% |
| scn_triangle_tight_P5_R10 | 30 | −11.28% | −40.36% | +8.19% |
| scn_triangle_tight_P5_R20 | 30 | **+2.38%** | −28.85% | +23.87% |
| scn_triangle_tight_P5_R30 | 30 | **+13.35%** | −25.88% | +37.16% |
| scn_triangle_tight_P5_R5 | 30 | −7.77% | −74.29% | +0.00% |
| scn_two_rows_tight_P5_R10 | 30 | −9.46% | −40.71% | +4.95% |

## Per-component mean Δ (heuristic − MILP; negative = heuristic better)

### wMK (100/1/1)

| Instance type | N | Δmakespan | Δdelay | Δmov |
| --- | --- | --- | --- | --- |
| scn_chain_tight_P5_R10 | 10 | +11.75 | +54.15 | +0.60 |
| scn_full_tight_P5_R10 | 10 | +22.20 | +107.00 | +12.00 |
| scn_full_tight_P5_R20 | 10 | −8.40 | −155.65 | +40.00 |
| scn_hub_tight_P5_R10 | 10 | +8.55 | +23.70 | +7.60 |
| scn_none_tight_P5_R10 | 10 | +0.00 | +0.00 | +0.00 |
| scn_triangle_loose_P5_R10 | 10 | +6.00 | +19.00 | +3.00 |
| scn_triangle_medium_P5_R10 | 10 | +4.95 | +15.35 | +2.80 |
| scn_triangle_tight_P5_R10 | 10 | +4.15 | +14.90 | +4.00 |
| scn_triangle_tight_P5_R20 | 10 | −13.05 | −37.85 | +15.00 |
| scn_triangle_tight_P5_R30 | 10 | **−77.30** | **−657.55** | +33.00 |
| scn_triangle_tight_P5_R5 | 10 | +0.00 | +1.30 | +1.60 |
| scn_two_rows_tight_P5_R10 | 10 | +3.20 | +5.25 | +2.40 |

### wDLY (1/100/1)

| Instance type | N | Δmakespan | Δdelay | Δmov |
| --- | --- | --- | --- | --- |
| scn_chain_tight_P5_R10 | 10 | +7.75 | +27.00 | −1.40 |
| scn_full_tight_P5_R10 | 10 | +6.75 | +39.55 | +14.20 |
| scn_full_tight_P5_R20 | 10 | −41.75 | −442.15 | +39.40 |
| scn_hub_tight_P5_R10 | 10 | +6.10 | +12.25 | +9.00 |
| scn_none_tight_P5_R10 | 10 | +0.00 | +0.00 | +0.00 |
| scn_triangle_loose_P5_R10 | 10 | +4.85 | +8.30 | +6.00 |
| scn_triangle_medium_P5_R10 | 10 | +0.80 | +7.20 | −1.00 |
| scn_triangle_tight_P5_R10 | 10 | +0.15 | +8.80 | −1.00 |
| scn_triangle_tight_P5_R20 | 10 | −11.05 | −63.00 | +12.40 |
| scn_triangle_tight_P5_R30 | 10 | **−57.00** | **−618.30** | +28.20 |
| scn_triangle_tight_P5_R5 | 10 | +0.60 | +0.00 | +0.60 |
| scn_two_rows_tight_P5_R10 | 10 | −1.50 | +4.05 | +0.20 |

### wMOV (1/1/100)

| Instance type | N | Δmakespan | Δdelay | Δmov |
| --- | --- | --- | --- | --- |
| scn_chain_tight_P5_R10 | 10 | +19.75 | +60.75 | +0.00 |
| scn_full_tight_P5_R10 | 10 | +42.00 | +122.50 | +0.00 |
| scn_full_tight_P5_R20 | 10 | +189.60 | +1502.15 | +2.40 |
| scn_hub_tight_P5_R10 | 10 | +13.65 | +19.10 | +0.00 |
| scn_none_tight_P5_R10 | 10 | +0.10 | +0.00 | +0.00 |
| scn_triangle_loose_P5_R10 | 10 | +16.50 | +31.05 | +0.00 |
| scn_triangle_medium_P5_R10 | 10 | +13.90 | +25.10 | +0.00 |
| scn_triangle_tight_P5_R10 | 10 | +11.15 | +23.60 | +0.00 |
| scn_triangle_tight_P5_R20 | 10 | +6.30 | +66.25 | +0.00 |
| scn_triangle_tight_P5_R30 | 10 | **−18.45** | **−83.75** | +0.00 |
| scn_triangle_tight_P5_R5 | 10 | +1.60 | +5.50 | +0.00 |
| scn_two_rows_tight_P5_R10 | 10 | +10.85 | +21.90 | +0.00 |

## Performance summary

**v1→v2 comparison overview.**  The Mode-C fixpoint decoder (v2) is a decisive
improvement on wMK and wDLY but introduces a regression on wMOV for large
instances.  The regression is not caused by additional movements (Δmov ≈ 0 under
wMOV, as intended by the decoder's Mode-A/B floor) but by decode-cost starvation:
the fixpoint loop per chromosome is expensive enough that full_R20 and
triangle_R30 runs routinely overshoot the 60 s budget by 12–20 s (observed
72–81 s in the log), leaving the GA far fewer generations than v1.

**wMK (makespan-priority).**  v2 roughly halves the loss on R10 instances
compared to v1: `scn_chain_tight_P5_R10` improves from −45.8% to −18.5%,
`scn_full_tight_P5_R10` from −58.7% to −31.1%, `scn_hub_tight_P5_R10` from
−21.2% to −13.6%, and the triangle variants from roughly −21% to −6% to −10%.
Δmakespan and Δdelay are still positive (heuristic worse) on R10, but
substantially reduced: e.g. Δmakespan for `scn_chain` drops from +29.3 to
+11.75, Δdelay from +121.9 to +54.2.  Crucially, `scn_triangle_tight_P5_R20`
flips to a positive mean gap (+8.0%), and `scn_triangle_tight_P5_R30` improves
to +21.7% (from +15.8% in v1).  The wMK Δmov column is now sometimes slightly
positive (e.g. +0.6 for chain, +12.0 for full_R10), reflecting Mode-C events
that the v1 decoder would never produce.

**wDLY (delay-priority).**  The improvement is equally clear.  The extreme
`scn_triangle_tight_P5_R5` artefact shrinks from −1322% to −3.2%: the v2
decoder produces schedules with near-zero delay on these small, loosely
constrained instances, matching the MILP more closely.  `scn_triangle_loose_P5_R10`
remains severely negative (−712%) due to small-denominator inflation — the
absolute Δdelay of +8.3 units is small but the MILP optimum delay is nearly
zero on that type (see Caveat 1).  `scn_full_tight_P5_R20` is now a solid
win (+16.5% mean, Δdelay = −442.2), and `scn_triangle_tight_P5_R20` also
turns positive (+7.2%).

**wMOV (movement-priority).**  The decode-cost regression dominates here.
`scn_full_tight_P5_R20` falls from −42.2% (v1) to −120.3% (v2): Δmov
remains +2.4 (essentially zero) while Δmakespan balloons to +189.6 and
Δdelay to +1502.2 — the GA simply does not explore enough of the chromosome
space in the available time.  `scn_triangle_tight_P5_R30` similarly drops
from +21.4% to +1.6%, though it remains narrowly positive thanks to the
unconverged MILP.  R5 and R10 instances are largely unaffected because their
decode cost is proportionally lower; results there are broadly neutral to v1.

## Caveats

1. **Small-denominator inflation.**  The extreme percentage gaps for
   `scn_triangle_loose_P5_R10` (wDLY: −712%) persist in v2 because the MILP
   optimum delay is near-zero on those instances — a small absolute Δdelay
   (≈ +8 units from the Δ table) yields a large negative percentage.  Read the
   Δ tables alongside the gap tables for this row.
2. **Unconverged MILP baseline at R20/R30.**  Positive gaps on
   `scn_triangle_tight_P5_R30` (and some seeds of R20) reflect "better
   feasible-in-60s" rather than proven improvement over the true optimum.
3. **wMOV regression is decode-cost, not movement-quality.**  Under wMOV the
   decoder's Δmov is still ≈ 0 for R10 and most R20 rows — Mode-C movements
   in the v2 decoder are suppressed naturally because they are penalised by
   the local-cost function.  The objective inflation on large R is driven
   entirely by the GA having insufficient generations due to the fixpoint cost
   exceeding the 60 s budget.  Fixing this requires cost control (fewer
   fixpoint iterations, or bypassing Mode-C when the weight profile makes it
   unattractive), not a change to the movement logic.

---

# Part III — Improvement roadmap

## Diagnosis

After two batteries the method's shape is clear.  Against the cached MILP the
BRKGA loses on small/medium instances (R5–R10) and wins on the largest
(R20/R30) where the 60 s MILP is unconverged.  Two batteries isolated the
levers:
- **v1 (Mode-A/B-only)** drove movements to zero via the safe-late candidate,
  but that inflated makespan and delay — fatal under wMK/wDLY where movements
  are cheap (weight 1).
- **v2 (Mode-C via κ fixpoint)** fixed exactly that: letting a rear interrupt a
  cheap interruptible front (Mode C, +2 movements, +δ) instead of waiting cut
  makespan/delay sharply on wMK/wDLY (chain_R10 wMK −45.8%→−18.5%;
  triangle_tight_R5 wDLY −1322%→−3.2%).  But it **regressed wMOV** — not by
  adding movements (Δmov≈0; the scan suppresses Mode C when W^S=100) but
  because the fixpoint decode is ~8× slower, starving the GA on large R
  (full_R20 runs overran the 60 s budget at 72–73 s).

The residual is therefore two-sided: a **decode-cost problem** on large R, and
a **profile-dependence** — Mode C helps when movements are cheap and is pure
overhead when they are not.

## Priority 0 — Standard battery (three weight profiles)

status: **DONE** (v1 log `…_20260618_064914.log`; v2 log
`…_20260619_070616.log`).  Both batteries: 360/360 feasible.

## Priority 1 — Profile-gated Mode-C (v3 lever, highest impact)

status: PLANNED.  Disable Mode C (`allow_mode_c=False`) when the movement
weight dominates (wMOV), since it can only add cost there.  This recovers v1's
behaviour *and* v1's faster decode on wMOV, removing the regression at no risk
to wMK/wDLY.  Concretely: set `allow_mode_c = weight_movements <
k·max(weight_makespan, weight_delay)` in `solve()` (calibrate `k`).

## Priority 2 — Tame the fixpoint decode cost on large R

status: PLANNED.  On R20/R30 the κ fixpoint (up to 8 passes × pop-size decodes)
blows the 60 s budget, so the GA barely evolves.  Options: cap
`max_fixpoint_iters` to 2–3; check the wall-clock budget *inside* the decode
and bail to the Mode-A/B-only pass when time is short; or shrink `pop_size`
for large `n`.  Goal: enough generations on R20/R30 to actually search.

## Priority 3 — Warm-start injection

status: PLANNED.  `design.md §6` specifies reverse-encoding cached MILP and
topology JSONs into chromosomes for the initial population.  `warmstart.py`
not yet implemented; `run_brkga` already accepts a `warmstarts` parameter.

## Metrics and ablations

- Re-run the battery after P1 and confirm wMOV returns to ≥ v1 while wMK/wDLY
  hold their v2 gains.
- Log generations-completed per run to confirm P2 restores GA evolution on R20/R30.
- Ablate warm-start vs cold-start per profile after P3.

## Recommended implementation order

1. Standard battery (v1 + v2) — **DONE**
2. Profile-gated Mode-C — PLANNED (P1)
3. Fixpoint cost control on large R — PLANNED (P2)
4. Warm-start injection + ablation — PLANNED (P3)

---

# Part IV — How it is implemented

Source: [`theory_assisted_job.py`](theory_assisted_job.py) — class
`TheoryAssistedJobSolver`, registered under the labels `ta_brkga_wMK`,
`ta_brkga_wDLY`, `ta_brkga_wMOV`.

## Solver contract (`shared/application.py`)

| member | role |
| --- | --- |
| `name` | `"theory_assisted_job"` |
| `configure_solver(**kw)` | Stores all kwargs in `self._config`; honours `time_limit_s`, `weight_makespan`, `weight_delay`, `weight_movements`, `seed`, `pop_size`, `allow_mode_c` |
| `solve(instance)` | Constructs `DecoderContext` (with `allow_mode_c` from config), calls `run_brkga`, returns best solution dict |
| `get_config()` | Returns a shallow copy of `self._config` |
| `get_log()` | Returns a copy of `self._log` (BRKGA shake + done events) |

### Config knobs

| key | default | meaning |
| --- | --- | --- |
| `time_limit_s` | `30.0` | Wall-clock time limit (Application guarantees to set this) |
| `weight_makespan` | `0.1` | Objective weight W^M |
| `weight_delay` | `1.0` | Objective weight W^D |
| `weight_movements` | `10.0` | Objective weight W^S |
| `seed` | `0` | RNG seed for BRKGA |
| `pop_size` | `max(100, 10 * n_keys)` | Population size; None = use BRKGA default |
| `allow_mode_c` | `True` | Enable Mode-C construction via κ fixpoint; set False for Mode-A/B-only (v1 behaviour) |

## Method ↔ code map

| Method concept (Part I) | Code |
| --- | --- |
| Chromosome, length `2|R|` | `n_keys = 2 * ctx.n_air` in `TheoryAssistedJobSolver.solve` |
| Assignment genes → position | `decoder.decode`: `idx = min(int(assign_keys[i] * ctx.n_pos), ctx.n_pos - 1)` |
| Sequencing genes → service order | `decoder.decode`: `at_position[p].sort(key=lambda r: seq_of[r])` |
| Topological placement order | `DecoderContext._topo_order` (Kahn's algorithm on blocking DAG) |
| Front-aircraft lookup | `DecoderContext.fronts_of` (dict: rear position → list of front positions) |
| Job chain reconstruction | `DecoderContext._build_chains` (follows `job_precedences`, `is_first` flag) |
| Effective processing time (incl. Mode-C extensions) | `decoder._proc_eff(r, ctx, kappa)`: `proc_time[r] + delta * sum(kappa[(r,j)])` |
| Mode-C fixpoint | `decoder.decode`: iterates `_decode_pass` up to `max_fixpoint_iters=8`; stops when `new_kappa == kappa`; falls back to Mode-A/B-only pass if not converged |
| One forward placement pass | `decoder._decode_pass(ctx, at_position, kappa, allow_mode_c)`: places all aircraft in topological order with `kappa` held fixed; returns `(placed, modeC_counts)` |
| Candidate start-time set | `decoder._candidate_starts(earliest, proc, front_air, ctx, allow_mode_c)`: Mode-A after/before, Mode-B gap midpoints, Mode-C job interiors (if `allow_mode_c`), safe-late fallback; capped at `_MAX_CANDIDATES = 80` |
| Mode-C candidate instants | `decoder._candidate_starts`: for each interruptible front job, adds `mid` and `mid − proc` to the candidate set |
| Safe-late fallback (Mode A guaranteed) | `decoder._safe_late(earliest, front_air, ctx)` |
| Local-cost evaluation + Mode classification | `decoder._evaluate(s0, proc, front_air, ctx, gap_uses, allow_mode_c)`: calls `_classify_access` from `problems/jobs/checker.py`; returns `None` for infeasible/Mode-C-when-disabled; accumulates Mode-C penalty in `_place_aircraft` |
| Mode-C local-cost penalty | `decoder._place_aircraft`: `modec_pen = len(ev["modeC"]) * (w_mk + w_dly) * delta` added to candidate cost |
| Cumulative-μ rule on Mode-B gaps | `decoder._evaluate`: `gap_uses` dict, `gap_size + 1e-9 < ctx.mu * total_uses` → `None` |
| Compact job-chain layout (with κ extensions) | `decoder._layout(r, s0, ctx, kappa)`: lays jobs compactly from `s0`, each job's duration extended by `delta * kappa[(r, jid)]` |
| Solution assembly + exact metrics | `decoder._assemble(placed, ctx)`: re-derives movements globally via `_classify_access`; consistent with checker RQ07_v2 and (at fixpoint) RQ09 |
| BRKGA engine | `brkga.run_brkga` |
| Elite / mutant / crossover partition | `brkga.run_brkga`: `n_elite`, `n_mutant`, biased crossover with probability `rho=0.70` |
| Shake on stagnation | `brkga.run_brkga`: `shake_after=50` stagnant generations |
| Warm-start injection | `brkga.run_brkga`: `warmstarts` parameter (not yet wired in solver) |

## Key implementation notes

- `decoder.py` imports `_classify_access` from `problems.jobs.checker` via package
  path (not bare `import checker`) to avoid ambiguity with the `problems/aircraft/`
  checker that also lives on `sys.path` in the batch runner.
- The candidate-start set is capped at `_MAX_CANDIDATES = 80` instants (raised
  from 60 in v1 to accommodate the additional Mode-C interior candidates); if the
  raw set exceeds this, an evenly spaced subset is taken (first element always
  kept, last-index coverage preserved by the step formula).
- The Mode-C fixpoint is deliberately NOT preceded by a separate Mode-A/B floor
  pass per chromosome.  A comment in `decoder.decode` explains the trade-off: the
  floor roughly doubles decode cost, and in a fixed time budget the lost GA
  generations hurt more than the per-chromosome floor helps (measured on an 8 s
  probe).  The GA's population already covers low-Mode-C chromosomes.
- `_proc_eff` extends a front aircraft's effective processing time by
  `delta * kappa[(r, jid)]` for each Mode-C interruption of job `jid`.  This is
  used in `_decode_pass` so that the forward pass respects the extended durations
  baked in from the previous iteration — the mechanism by which the fixpoint
  achieves self-consistency.
- Movements are re-derived globally in `_assemble` via `_classify_access` rather
  than accumulated during placement, so the reported count is guaranteed consistent
  with the checker.  The local `gap_uses` tracking during placement is used only
  for the cumulative-μ feasibility check.
- `run_brkga` logs shake events and the final generation count/objective to
  `self._log` via the `log` parameter; these are surfaced by `get_log()` and
  persisted by `Application.save_solution` to `data/logs_heuristic/`.
- `pop_size` defaults to `max(100, 10 * n_keys)` inside `brkga.py`; passing
  `pop_size=None` in the config (the default) uses this formula.
- The `allow_mode_c=False` path in `decode` bypasses the fixpoint loop entirely
  and runs a single `_decode_pass` with `kappa={}`, reproducing v1 behaviour
  exactly.

## Isolation

The solver imports nothing from other methods.  The lazy import path for
`_classify_access` targets `problems/jobs/` (allowed).
`experiments/tests/test_method_isolation.py` should report 0 violations.

## Smoke test

```
py -3 methods/theory_assisted/jobs/theory_assisted_job.py \
    data/instances_202605_02/scn_triangle_tight_P5_R5/scn_triangle_tight_P5_R5_seed1.json
```

Prints the checker report.  The solver hard-codes `time_limit_s=20` for the smoke
test.  The default instance path is
`data/instances_202605_02/scn_triangle_tight_P5_R5/scn_triangle_tight_P5_R5_seed1.json`.

---

# Change log

Track the method's evolution.  One row per behaviour-affecting commit
(or per shipped milestone), newest at the bottom.

| commit | change | effect on results |
| ------ | ------ | ----------------- |
| 2d37eeb | v06: initial BRKGA implementation — decoder (`decoder.py`), BRKGA engine (`brkga.py`), solver wrapper (`theory_assisted_job.py`); registered as `ta_brkga_wMK/wDLY/wMOV` in `run_experiments.py` | 360/360 feasible; loses to MILP on R5–R10 across all profiles (mean gap −19% to −59% wMK; extreme wDLY artefacts on near-zero-delay instances); wins only on unconverged-MILP R30 (+15.8/+21.0/+21.4% wMK/wDLY/wMOV); Δmov = 0 everywhere under wMOV as designed. |
| 22c65fb | v06 decoder v2 — Mode-C construction via κ fixpoint: `DecoderContext` gains `allow_mode_c` and `max_fixpoint_iters`; `decode()` runs fixpoint of `_decode_pass` until `kappa` stabilises (fallback to Mode-A/B-only if not converged in 8 iters); new helpers `_proc_eff`, `_decode_pass`; Mode-C branches in `_evaluate`, `_candidate_starts`, `_layout`; `_MAX_CANDIDATES` raised to 80 | wMK/wDLY improve substantially: chain_R10 wMK −45.8%→−18.5%, triangle_R5 wDLY −1322%→−3.2%, triangle_R20 wMK+wDLY both turn positive (+8.0%, +7.2%). wMOV regresses on large R due to decode-cost starvation (full_R20 −42%→−120%, triangle_R30 +21%→+1.6%); Δmov ≈ 0 confirms regression is GA-generations loss, not movement quality; full_R20 runs overshoot 60 s budget (72–81 s observed). |

---

*Keep this file in sync with `theory_assisted_job.py`: when the code
changes behaviour, invoke `/sync-method-doc methods/theory_assisted`
with a brief hint describing what changed and (if relevant)
`log: <battery-log-path>` for refreshing Part II.  Design rationale
and the reading behind the method live in [`notes/design.md`](notes/design.md)
and [`notes/synthesis.md`](notes/synthesis.md).*
