# Iterated Greedy + VND for aircraft positioning with job-level scheduling (paper #2)

This is **Candidate A** from the theory-assisted design process: an Iterated
Greedy outer loop (destruction–reconstruction over position assignments) wrapped
around a sequential Variable Neighbourhood Descent local search.  The design is
drawn entirely from the curated literature digest in `inspiration/` / `digest/`
(see the notes in `methods/theory_assisted/jobs/notes/`); no external solver is
used.  The v02 upgrade adds a manoeuvre-aware decoder (Mode-C interruptions with
a kappa fixpoint) so the heuristic can spend movements to compress makespan and
delay, making it competitive on all three weight profiles rather than only the
movement-priority one.

> **Status (working tree, uncommitted; no formal battery yet).**
> v02 is freshly introduced.  The zero-movement baseline (v01 rule) is always
> retained as a fallback so v02 is provably non-regressing against v01.
> Correctness has been validated with `problems/jobs/checker.py` across 8
> topologies × 2 seeds × 3 weight profiles (**0 violations**); an ad-hoc v02
> vs v01 comparison is summarised in the change log.  Part II awaits a formal
> `experiments/run_experiments.py` battery (the method is not yet registered
> there — see Part III, Priority 0).

---

# Part I — The method

## 1. Problem recap and notation

Each aircraft $r$ must be assigned a position $\pi(r)$ and a start time for its
ordered job chain; its finish $f_r$ incurs delay $v^D_r = \max(0, f_r - L_r)$.
Some positions are *rear* positions whose access path crosses a *front*
position (a blocking arc $(p_\text{front}, p_\text{rear})$).  When a rear
aircraft enters or leaves while the front position is occupied, the access is
feasible only as **Mode A** (front vacant, free), **Mode B** (front in an
inter-job gap $\ge \mu$, +2 movements) or **Mode C** (front mid-*interruptible*-
job: pause it, +2 movements, the job grows by $\delta$ and $\kappa$ increments).
Accessing across a non-interruptible job is infeasible.  Same-position aircraft
serialise with an $\varepsilon$ gap.  The objective is
$W^M\,m + W^D\sum_r v^D_r + W^S n$ (makespan, total delay, movement count).
This method targets the three pure profiles $(W^M,W^D,W^S) \in
\{(100,1,1),(1,100,1),(1,1,100)\}$.

## 2. Design principle

**Separate the combinatorial decision from the timing decision** (the
convergent theme of the synthesis): the *outer* layer chooses the assignment
$\pi$ and a global priority order; a deterministic *decoder* turns
(assignment, order) into job start/finish times.  The outer layer is searched
by Iterated Greedy + VND; the decoder owns all feasibility.  v02's added
insight: the decoder may **spend a Mode-C manoeuvre** — let a rear aircraft
access *during* a front interruptible job rather than waiting until it ends —
whenever the weighted objective rewards the earlier finish more than the
2-movement (+$\delta$) cost.  It is never forced to, so under the
movement-priority profile it simply declines and stays at zero movements.

## 3. Outer loop — Iterated Greedy

- **Construction:** NEH order (descending $T_r$) + greedy best-position
  insertion (`_greedy_construct`): each aircraft is placed at the position
  minimising the partial decoded objective.
- **Perturbation** (`_perturb`): remove the $k = \max(1, R/4)$ highest
  delay-contribution aircraft (lightly randomised via a $k{+}2$ pool), then
  greedily reinsert each at its best (position, order-slot).
- **Acceptance:** accept the new local optimum if it does not worsen the
  incumbent walk (accept-if-not-worse); track the global best separately;
  restart the walk from the global best every 50 stalled iterations; early-stop
  after `max_no_improve` stalls.

## 4. Inner loop — Variable Neighbourhood Descent

`_vnd` is a sequential B-VND over three first-improvement neighbourhoods,
resetting to N1 on any improvement:
- **N1 `_n_reassign`** — move one aircraft to a different position;
- **N2 `_n_swap_pos`** — swap the positions of two aircraft;
- **N3 `_n_reorder`** — swap two aircraft in the priority order.

## 5. Decoder — zero-movement and manoeuvre-aware

Two decoders, dispatched by `_decode` which returns the **lower-objective** of
the two for each (assignment, order):
- **`_decode_zero`** (v01 rule): every rear access is forced Mode A by placing
  the rear before / after / *enclosing* the front stay; `movements = 0` by
  construction; always feasible.
- **`_decode_man`** (v02): a forward list-scheduler places each aircraft at the
  start minimising a weight-aware local cost, allowing **Mode C** access inside
  interruptible front jobs.  Because a Mode-C interruption lengthens the front
  job (shifting its finish and same-position successors), the decoder iterates a
  **$\kappa$ fixpoint**: place → re-classify all accesses → recompute $\kappa$ →
  rebuild durations → re-place, until interruption counts stabilise (cap 8).  On
  convergence the durations equal $D_j + \delta\kappa_j$ and the classification
  reproduces those $\kappa$, so the schedule passes the checker.  Non-convergence
  falls back to the zero-movement decode.

## 6. The complete algorithm in pseudocode

```
construct s0  (NEH order + greedy best-position insertion, zero decoder)
s* := VND(s0)
phase A (fast zero decoder):
  while budget·man_phase_frac not spent and not stalled:
    s' := VND(perturb(s*));  if obj(s') < obj(s*): s* := s'
phase B (manoeuvres on, decoder = min(zero, man)):
  re-evaluate obj(s*) under the richer decoder
  while budget not spent and not stalled:
    s' := VND(perturb(s*));  if obj(s') < obj(s*): s* := s'
return decode(s*)            # min(zero, man); a final polish for large R
```

## Behaviour observed

Manoeuvres are actually spent where the blocking topology is dense (e.g.
`full_tight` with all-pairs arcs uses tens of movements under the makespan and
delay profiles).  On sparse triangle topologies most of the gain instead comes
from the manoeuvre decoder's weight-aware forward pass packing *tighter than the
v01 earliest-fit rule even at zero movements*.  Under the movement-priority
profile the decoder reliably declines manoeuvres (the dispatcher keeps the
zero-movement decode, which is optimal on the dominant term).  The decoder is
~50× slower than the zero rule, which is why the search is phase-split by size.

---

# Part II — Results and analysis

First v02 battery, paired against the cached job-level MILP.  Authored from
`experiments/ta_paired_report.py` (the shared `paired_report.py` /
`gap_summary.py` are hard-wired to v01's `igvnd_*` labels, so a thin wrapper
swaps in the `ta_igvnd_*` labels and reuses the same gap maths).

## Experimental setup

| field             | value |
| ----------------- | ----- |
| Battery           | `_seed1$` subset (12 configs × seed 1 × 3 profiles = 36 runs) |
| Methods compared  | `ta_igvnd_*` (v02) vs cached `milp_job_*` |
| Weight profiles   | wMK (100/1/1) · wDLY (1/100/1) · wMOV (1/1/100) |
| Budget            | 60 s per run |
| Metric            | relative gap `(MILP − heur)/MILP` (>0 ⇒ v02 better) |
| Instances         | `data/instances_202605_02` |
| Log               | `outputs/logs/seed1$_202605_02_main_methods_20260616_064526.log` |
| Report            | `outputs/logs/ta_paired_report_seed1_20260616.txt` |
| Compliance        | **36/36 pass `checker.py`** (0 violations) |

## Relative objective gap vs MILP (seed 1; >0 ⇒ v02 better)

| configuration              | wMK     | wDLY    | wMOV    |
| -------------------------- | ------- | ------- | ------- |
| chain_tight_R10            | −7.4 %  | −7.2 %  | −11.7 % |
| full_tight_R10             | +6.6 %  | +18.2 % | +7.6 %  |
| **full_tight_R20**         | **+43.4 %** | **+56.3 %** | **+44.8 %** |
| hub_tight_R10              | −1.3 %  | −4.5 %  | +0.8 %  |
| none_tight_R10             | 0.0 %   | 0.0 %   | 0.0 %   |
| triangle_loose_R10         | −5.2 %  | −19.9 %†| +2.8 %  |
| triangle_medium_R10        | +0.0 %  | −0.9 %  | +0.8 %  |
| triangle_tight_R10         | +1.7 %  | +4.0 %  | +0.6 %  |
| triangle_tight_R20         | +12.4 % | +9.6 %  | +9.3 %  |
| **triangle_tight_R30**     | **+34.9 %** | **+46.8 %** | **+32.6 %** |
| triangle_tight_R5          | 0.0 %   | 0.0 %   | 0.0 %   |
| two_rows_tight_R10         | −0.0 %  | −0.5 %  | +1.2 %  |

† small-denominator artefact — the absolute Δdelay is only **+1.0** unit
(MILP delay ≈ 0 there), not a meaningful loss (see Caveats).

## Per-component Δ highlights (heuristic − MILP; negative = v02 better)

Where the MILP is unconverged the absolute wins are large:

| configuration / profile        | Δmakespan | Δdelay   | Δmov  |
| ------------------------------- | --------- | -------- | ----- |
| full_tight_R20 / wDLY           | −169.5    | **−1396.0** | +26 |
| triangle_tight_R30 / wDLY       | −157.5    | **−1758.5** | 0   |
| triangle_tight_R30 / wMK        | −115.5    | −1526.0  | 0     |
| full_tight_R20 / wMOV           | −45.5     | −700.7   | 0     |
| chain_tight_R10 / wMK (a loss)  | +4.5      | +13.6    | **−6** |

## Performance summary

- **wMK (makespan-priority):** v02 wins decisively on every large instance
  (full_R20 +43 %, triangle_R20 +12 %, triangle_R30 +35 %) and is within a few
  percent of the MILP on R10; the only real losses are chain_R10 (−7 %, where
  the MILP packs a tighter makespan) and triangle_loose (−5 %).
- **wDLY (delay-priority):** the largest wins (full_R20 +56 %, triangle_R30
  +47 %) — manoeuvres that pull finishes earlier pay directly in delay.  The
  −20 % on triangle_loose is a small-denominator artefact (Δdelay +1.0).
- **wMOV (movement-priority):** v02 reliably keeps movements at the MILP level
  (Δmov = 0 on almost all R10) while still beating it on the large instances
  (full_R20 +45 %, triangle_R30 +33 %) through tighter zero-movement packing.

Overall: v02 is dominant in the regime that matters for a heuristic (large
instances where the 60 s MILP is far from converged) and competitive on the
small instances where the MILP is near-optimal.

## Caveats

1. **Small-denominator inflation.** When the MILP optimum is ≈ 0 (e.g.
   triangle_loose delay), a few absolute units read as a large percentage.
   Always cross-read the per-component Δ — triangle_loose wDLY is −20 % but
   only +1.0 delay unit.
2. **MILP unconverged at scale.** On R20 / R30 the MILP's 60 s objective is an
   incumbent with an 80–99 % optimality gap, so v02's large wins there mean
   "better feasible solution in the same budget", not proven optimality.
3. **Single seed.** This is the `_seed1$` cross-type read; per-seed noise is not
   yet estimated.  Promote to `_seed1$,_seed2$,_seed3$` (or the full 360-run
   battery) before quoting these as stable means.
4. **Manoeuvre decoder ~50× slower** than the zero-movement rule; the
   size-adaptive phase split (Part IV) handles it but search depth differs by
   instance size.

---

# Part III — Improvement roadmap

## Diagnosis

v02 closes most of v1's "cannot spend a manoeuvre" gap and, by the `min(zero,
man)` dispatcher, is provably non-regressing against v01 per (assignment,
order).  An ad-hoc comparison (20 s, three profiles) shows v02 ≤ v01 on every
instance tested, with large gains on dense topologies (`full_R20`: −22 % wMK,
−30 % wMOV) and meaningful gains on small triangles (`R10`: −6 % to −11 %).
The remaining weaknesses are (a) **large instances** (R ≥ 23), where the slow
decoder forces the phase-split to keep manoeuvres to a final polish only, so the
gain shrinks to ≈0; and (b) **Mode B is unreachable** because the decoder packs
jobs tight — a whole class of cheap (no-$\delta$) manoeuvres is unavailable.

## Priority 0 — Register the method for a formal battery

(status: DONE — registered in `run_experiments.py` as `ta_igvnd_wMK/wDLY/wMOV`;
the `_seed1$` battery (36 runs) is in `results.csv` and summarised in Part II.
**Next:** promote to `_seed1$,_seed2$,_seed3$` then the full 360-run battery to
get stable per-seed means before quoting these numbers as final.)

## Priority 1 — Mode-B manoeuvres (open inter-job gaps)

(status: PLANNED — v02 packs jobs tight so no gaps exist; Mode-B
events are therefore always infeasible in the current decoder.  Opening
gaps for Mode-B is the natural next step.)

## Metrics and ablations

(what to log; how to measure each priority item.)

## Recommended implementation order

1. Run battery (v02 vs v01 vs milp_job_w*) — PLANNED
2. Mode-B gap-opening decoder — PLANNED
3. Adaptive k_destroy based on instance size — PLANNED

---

# Part IV — How it is implemented

Source: [`iterated_greedy_vnd.py`](iterated_greedy_vnd.py) — class
`IteratedGreedyVNDJobSolver`, registered under the labels `igvnd_wMK`,
`igvnd_wDLY`, and `igvnd_wMOV` (three weight-profile experiments share
the same class; the alias `TheoryAssistedJobSolver` provides backward
compatibility).

## Solver contract (`shared/application.py`)

| member | role |
| --- | --- |
| `name` | `"iterated_greedy_vnd"` |
| `configure_solver(**kw)` | Stores all tunable parameters in `self._config`; called before `solve`. |
| `solve(instance)` | Runs the full IG+VND loop; returns a solution dict with keys `status`, `objective`, `metrics`, and `aircraft`. |
| `get_config()` | Returns a shallow copy of `self._config`. |
| `get_log()` | Returns a copy of `self._log` — one string per notable event (construction, phase switch, new best, final summary). |

### Config knobs

| key | default | meaning |
| --- | --- | --- |
| `time_limit_s` | `60` | Wall-clock budget in seconds. |
| `weight_makespan` | `0.1` | $W^M$ — weight on makespan in the objective. |
| `weight_delay` | `1.0` | $W^D$ — weight on total delay. |
| `weight_movements` | `10.0` | $W^S$ — weight on movement count. |
| `seed` | `1` | RNG seed for `random.Random`; controls perturbation randomness. |
| `k_destroy` | `max(1, R // 4)` | Aircraft removed per IG perturbation step. |
| `max_no_improve` | `400` | Early-stop stall counter: halt after this many consecutive non-improving IG iterations. |
| `allow_manoeuvres` | `True` | Master switch for the Mode-C manoeuvre decoder.  When `False`, the solver behaves as the pure v01 zero-movement heuristic. |
| `man_phase_frac` | adaptive (see below) | Fraction of the time budget spent in the zero-movement phase before manoeuvres are enabled.  Auto-set: `0.0` for R ≤ 12, `0.5` for R ≤ 22, `1.0` for R > 22 (polish only).  Overridable. |

## Method ↔ code map

| Method concept (Part I) | Code |
| --- | --- |
| Instance preprocessing (hangar graph, job chains, T_r) | `_prepare(inst)` |
| NEH-style greedy construction | `_greedy_construct(order)` |
| NEH priority ordering (descending T_r) | `_neh_order(assignment)` |
| Variable Neighbourhood Descent (B-VND, 3 neighbourhoods) | `_vnd(assignment, order)` |
| N1 — move one aircraft to a different position | `_n_reassign(assignment, order, cur)` |
| N2 — swap positions of two aircraft | `_n_swap_pos(assignment, order, cur)` |
| N3 — swap two aircraft in priority order | `_n_reorder(assignment, order, cur)` |
| IG perturbation (destruction + greedy reconstruction) | `_perturb(assignment, order, k)` |
| Decoder dispatcher (best of zero-movement and manoeuvre-aware) | `_decode(assignment, order)` |
| Zero-movement decoder (v01 rule, movements = 0) | `_decode_zero(assignment, order)` |
| Forbidden-interval generator for zero-movement decode | `_forbidden(p, dur, p2, s2, f2)` |
| Manoeuvre-aware decoder with kappa fixpoint | `_decode_man(assignment, order)` |
| Forward list-scheduler (one pass, given fixed kappa) | `_forward_pass(assignment, order, kappa)` |
| Candidate start-time selector (local cost minimisation) | `_choose_start(r, assignment, dur, placed, kappa)` |
| Feasibility check + events count for a candidate start | `_eval_start(r, assignment, t, dur, placed, kappa)` |
| Kappa fixpoint classifier (full schedule re-classification) | `_classify_schedule(assignment, placed, kappa)` |
| Access-mode classifier (A / B / C / X) for one instant | `_classify(tau, s, f, jobs)` |
| Job interval builder (packed tight from a start, with kappa extensions) | `_job_intervals(r, start, kappa)` |
| Weighted duration of an aircraft (with kappa extensions) | `_duration(r, kappa)` |
| Solution dict assembler + objective computation | `_finalise(placed, assignment, kappa, movements)` |
| Adaptive two-phase budget split (phase A: zero-movement, phase B: manoeuvre-on) | `man_phase_frac` logic in `solve()` |

## Key implementation notes

- **Two-phase budget split.** The manoeuvre-aware decoder is approximately
  50× slower per evaluation than the zero-movement rule.  `solve()` spends the
  first `man_phase_frac * time_limit` seconds using only the fast decoder
  (phase A) to build a strong incumbent cheaply, then switches to the richer
  decoder for the remainder (phase B).  For R > 22, `man_phase_frac = 1.0` so
  only a single "polish" manoeuvre decode is applied to the best solution at
  the end — this guarantees v02 is never worse than v01 regardless of instance
  size.

- **Kappa fixpoint cap.** `_decode_man` runs at most 8 fixpoint iterations
  (`for _ in range(8)`).  If kappa has not stabilised by then, the manoeuvre
  decode is discarded and the zero-movement decode is used.

- **Safety tolerance duality.** Two constants co-exist: `TOL = 1e-4` (matches
  `checker.py`) used in mode classification so the decoder's decisions agree
  with the checker; `SAFE = 1e-2` used when *generating* candidate placements
  to land comfortably away from the eta boundary.

- **Mode B is currently always infeasible.** `_decode_zero` packs jobs
  tight (zero inter-job gaps), so any access landing in an inter-job gap
  (`kind == "B"`) will fail the cumulative-mu check in
  `_classify_schedule`.  The `gap_uses` accounting is kept for future
  Mode-B support.

- **Perturbation pool size.** `_perturb` picks the top `k + 2` aircraft
  by delay-weighted contribution, shuffles them, and removes the first `k`.
  The `+2` oversize prevents the same aircraft always being destroyed and
  adds mild randomness without full random selection.

- **Restart on stall.** Every 50 non-improving IG iterations the current
  walk is reset to the global best (`no_improve % 50 == 0`), preventing
  indefinite drift into poor basins.

- **Backward-compatible alias.** `TheoryAssistedJobSolver = IteratedGreedyVNDJobSolver`
  at module level; any experiment that registered the old name continues to
  work without changes.

## Isolation

The solver imports only Python stdlib (`random`, `time`) and the
`__main__` block imports `instance_io` from `shared/` and `checker` from
`problems/jobs/` — both allowed paths.  It imports nothing from other
methods.

## Smoke test

```
py -3 methods/theory_assisted/jobs/iterated_greedy_vnd.py \
    problems/jobs/instances/scn_triangle_tight_P5_R5/scn_triangle_tight_P5_R5_seed1.json 10
```

Prints the per-run log, the objective/metrics, and the full checker report.
Optional extra positional arguments: `<time_limit_s> <wM> <wD> <wS>` (defaults
`10 0.1 1.0 10.0`).

---

# Change log

Track the method's evolution.  One row per behaviour-affecting commit
(or per shipped milestone), newest at the bottom.

| commit | change | effect on results |
| ------ | ------ | ----------------- |
| (working tree, uncommitted) | v02: manoeuvre-aware decoder (Mode-C kappa fixpoint) + `min(zero,man)` dispatcher + adaptive two-phase budget split; `allow_manoeuvres` knob; pure zero-movement baseline retained as fallback guaranteeing non-regression against v01.  Registered in `run_experiments.py` as `ta_igvnd_*`; helper `experiments/ta_paired_report.py` added | `_seed1$` battery (36 runs, 60 s, **36/36 COMPLIANT**) vs cached MILP: dominant on large unconverged instances (full_R20 +43/+56/+45 %, triangle_R30 +35/+47/+33 % wMK/wDLY/wMOV), within a few % on R10, ties on none/R5.  Internally v02 ≥ v01 on every (a,o) by the `min(zero,man)` dispatcher |

---

*Keep this file in sync with `iterated_greedy_vnd.py`: when the code
changes behaviour, invoke `/sync-method-doc methods/theory_assisted`
with a brief hint describing what changed and (if relevant)
`log: <battery-log-path>` for refreshing Part II.  Design rationale
and the reading behind the method live in [`notes/design.md`](notes/design.md)
and [`notes/synthesis.md`](notes/synthesis.md) where applicable.*
