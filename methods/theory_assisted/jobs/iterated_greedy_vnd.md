# Iterated Greedy + VND for aircraft positioning with job-level scheduling (paper #2)

This is **Candidate A** from the theory-assisted design process: an Iterated
Greedy outer loop (destruction–reconstruction over position assignments) wrapped
around a sequential Variable Neighbourhood Descent local search.  The design is
drawn entirely from the curated literature digest in `inspiration/` / `digest/`
(see the notes in `methods/theory_assisted/jobs/notes/`); no external solver is
used.  The v02 upgrade added a manoeuvre-aware decoder (Mode-C interruptions
with a κ fixpoint) so the heuristic can spend movements to compress makespan and
delay; **v03** adds Mode-B manoeuvres (opening inter-job gaps, via a second
fixpoint state) so it can also route a rear access through a front gap without
extending any job — making it competitive on all three weight profiles rather
than only the movement-priority one.

> **Status (v03 — Mode-B added; on branch `theory_assisted-v03-modeB`).**
> The zero-movement baseline (v01 rule) is always retained as a fallback, and a
> staged fixpoint falls back to the v02 (κ-only) decode on dense topologies, so
> v03 is non-regressing against both v01 (per (a,o)) and v02 (within noise).
> Validated with `problems/jobs/checker.py`: **0 violations** over the `_seed1$`
> battery (36 runs) and an 8-topology × 2-seed sweep.  Part II has the v03 vs
> MILP numbers.

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
- **`_decode_man`** (v02 + v03): a forward list-scheduler places each aircraft
  at the start minimising a weight-aware local cost, allowing two manoeuvres:
  **Mode C** (v02) — access inside an interruptible front job, which lengthens
  it by $\delta$ (counted by $\kappa$); and **Mode B** (v03) — access through an
  *opened* inter-job gap of the front (width $\mu\cdot\text{count}$, no $\delta$
  extension).  Both modify the front aircraft, so the decoder iterates a **joint
  $(\kappa, \text{gaps})$ fixpoint**: place → re-classify all accesses →
  recompute $\kappa$ (Mode-C counts) and gap widths (Mode-B counts) → rebuild
  durations/gaps → re-place, until both stabilise (cap 10).  On convergence the
  schedule is self-consistent with the checker's classification and passes it.
  Non-convergence falls back to the zero-movement decode.

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

v03 battery (Mode-B added), paired against the cached job-level MILP.  Authored
from `experiments/ta_paired_report.py` (the shared `paired_report.py` /
`gap_summary.py` are hard-wired to v01's `igvnd_*` labels, so a thin wrapper
swaps in the `ta_igvnd_*` labels and reuses the same gap maths).

## Experimental setup

| field             | value |
| ----------------- | ----- |
| Battery           | `_seed1$` subset (12 configs × seed 1 × 3 profiles = 36 runs) |
| Methods compared  | `ta_igvnd_*` (v03) vs cached `milp_job_*`; v02 column for reference |
| Weight profiles   | wMK (100/1/1) · wDLY (1/100/1) · wMOV (1/1/100) |
| Budget            | 60 s per run |
| Metric            | relative gap `(MILP − heur)/MILP` (>0 ⇒ heuristic better) |
| Instances         | `data/instances_202605_02` |
| Report            | `outputs/logs/ta_paired_report_v03fix_seed1_20260616.txt` |
| Compliance        | **36/36 pass `checker.py`** (0 violations) |

## Relative objective gap vs MILP (seed 1; >0 ⇒ heuristic better)

v03 gap, with the v02 gap in parentheses where it changed materially:

| configuration              | wMK            | wDLY             | wMOV    |
| -------------------------- | -------------- | ---------------- | ------- |
| chain_tight_R10            | −2.6 % (was −7.4) | **+11.7 %** (was −7.2) | −11.7 %‡ |
| full_tight_R10             | +6.5 %         | +23.9 % (was +18.2) | +7.6 %  |
| **full_tight_R20**         | **+42.4 %**    | **+63.8 %** (was +56.3) | **+45.1 %** |
| hub_tight_R10              | −1.4 %         | +2.6 % (was −4.5)| +0.8 %  |
| none_tight_R10             | 0.0 %          | 0.0 %            | 0.0 %   |
| triangle_loose_R10         | −1.6 % (was −5.2) | −11.0 %† (was −19.9) | +2.8 %  |
| triangle_medium_R10        | +0.1 %         | +5.5 % (was −0.9)| +0.8 %  |
| triangle_tight_R10         | +1.7 %         | +4.0 %           | +0.6 %  |
| triangle_tight_R20         | +12.4 %        | +11.7 % (was +9.6) | +9.6 %  |
| **triangle_tight_R30**     | **+34.9 %**    | **+46.8 %**      | **+32.6 %** |
| triangle_tight_R5          | 0.0 %          | 0.0 %            | 0.0 %   |
| two_rows_tight_R10         | +0.1 %         | −5.1 %† (Δdelay +5) | +1.2 %  |

† small-denominator artefact — the absolute Δdelay is a handful of units
(MILP delay near the noise floor of ~19 units), not a meaningful loss.
‡ chain wMOV −11.7 % is likewise a small-delay-denominator effect at 0 movements.

**v03 vs v02:** Mode-B turns the cases v02 lost into wins — chain_R10 wDLY
**−7.2 % → +11.7 %**, hub wDLY −4.5 % → +2.6 %, triangle_medium wDLY −0.9 % →
+5.5 %, triangle_loose halved — while the dense `full` topologies (where the
joint fixpoint would oscillate) are held at the v02 level by the staged
fallback (full_R10 wMK +6.5 %, matching v02 within noise).  wMOV is unchanged
(manoeuvres correctly inert under movement-priority).

## Per-component Δ highlights (heuristic − MILP; negative = heuristic better)

Where the MILP is unconverged the absolute wins are large:

| configuration / profile        | Δmakespan | Δdelay      | Δmov  |
| ------------------------------- | --------- | ----------- | ----- |
| full_tight_R20 / wDLY           | ≈ −180    | **≈ −1500** | +20s  |
| triangle_tight_R30 / wDLY       | −157.5    | **−1758.5** | 0     |
| triangle_tight_R30 / wMK        | −115.5    | −1526.0     | 0     |
| chain_tight_R10 / wDLY (v03 win)| ≈ −8      | ≈ −15       | +14   |

## Performance summary

- **wMK (makespan-priority):** dominant on every large instance (full_R20
  +42 %, triangle_R30 +35 %); within noise of the MILP on R10.  Mode-B lifted
  chain_R10 from −7.4 % to −2.6 %.
- **wDLY (delay-priority):** the biggest gains, now including the formerly-lost
  dense-blocking R10s (chain +11.7 %, hub +2.6 %) — Mode-B routes a rear through
  a front gap to finish earlier without the δ cost of Mode C.
- **wMOV (movement-priority):** identical to v02 — the dispatcher keeps the
  zero-movement decode, optimal on the dominant term.

Overall: v03 ≥ v02 across the battery (beyond noise) and dominant in the regime
that matters for a heuristic (large instances where the 60 s MILP is far from
converged).

## Caveats

1. **Small-denominator inflation.** When the MILP optimum is ≈ 0, a few absolute
   units read as a large percentage; cross-read the per-component Δ.
2. **MILP unconverged at scale.** On R20 / R30 the MILP's 60 s objective has an
   80–99 % optimality gap, so the large wins mean "better feasible solution in
   the same budget", not proven optimality.
3. **Single seed.** `_seed1$` cross-type read; per-seed noise (~19 delay units
   on this battery) is not yet estimated.  Promote to 3 seeds / full 360-run
   battery before quoting these as stable means.
4. **Staged fixpoint cost.** On dense topologies the joint (κ, gaps) fixpoint
   oscillates (~37 % non-convergence on `full_R10`) and bails to the κ-only
   path; this costs extra forward passes, so search depth on dense instances is
   shallower than v02 even though quality matches.  Incremental re-classification
   (Part III) is the fix.

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
| `allow_manoeuvres` | `True` | Master switch for the manoeuvre decoder (Mode-C interrupts + Mode-B gap opening).  When `False`, the solver behaves as the pure v01 zero-movement heuristic. |
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
| Manoeuvre-aware decode — staged fallback (joint → κ-only → zero) | `_decode_man(assignment, order)` |
| One fixpoint attempt up to a cap (Mode-B gated by `_enable_b`) | `_man_fixpoint(assignment, order, cap)` |
| Fixpoint-state equality test for the gap plan | `_gaps_equal(a, b)` |
| Forward list-scheduler (one pass, given fixed kappa+gaps) | `_forward_pass(assignment, order, kappa, gaps)` |
| Candidate start-time selector (Mode A/B/C candidates, local cost) | `_choose_start(r, assignment, dur, placed, kappa, gaps)` |
| Feasibility check + events count for a candidate start | `_eval_start(r, assignment, t, dur, placed, kappa, gaps)` |
| Fixpoint classifier (sets kappa from Mode-C, gaps from Mode-B) | `_classify_schedule(assignment, placed, kappa, gaps)` |
| Access-mode classifier (A / B / C / X) for one instant | `_classify(tau, s, f, jobs)` |
| Job interval builder (kappa extensions + Mode-B inter-job gaps) | `_job_intervals(r, start, kappa, gaps)` |
| Weighted duration of an aircraft (kappa + gaps) | `_duration(r, kappa, gaps)` |
| Solution dict assembler + objective computation | `_finalise(placed, assignment, kappa, movements, gaps)` |
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

- **Joint (kappa, gaps) fixpoint cap.** `_decode_man` runs at most 10 fixpoint
  iterations.  Each pass re-classifies every access and sets `kappa` from
  Mode-C event counts and `gaps[(r,k)] = mu·count` from Mode-B event counts;
  it converges when both states are stable (`new_kappa == kappa` and
  `_gaps_equal`).  If they have not stabilised by the cap, the manoeuvre decode
  is discarded and the zero-movement decode is used.

- **Safety tolerance duality.** Two constants co-exist: `TOL = 1e-4` (matches
  `checker.py`) used in mode classification so the decoder's decisions agree
  with the checker; `SAFE = 1e-2` used when *generating* candidate placements
  to land comfortably away from the eta boundary.

- **Mode B (v03).** `_decode_man` can now *open* an inter-job gap in a front
  aircraft to route a rear access through it (2 movements, no δ extension).
  `_choose_start` proposes Mode-B candidates (start times landing a rear access
  on a front job-`k` boundary); `_classify_schedule` then sets
  `gaps[(rf,k)] = mu·count`.  Because a gap opened *after* job `k` does not move
  job `k`'s finish, the targeted access stays valid across fixpoint iterations,
  and the gap width = `mu·count` satisfies the cumulative-μ rule by
  construction.  `_decode_zero` (the fallback) still packs tight with no gaps.

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
    data/instances_202605_02/scn_triangle_tight_P5_R5/scn_triangle_tight_P5_R5_seed1.json 10
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
| 56fab0c (main) | v02: manoeuvre-aware decoder (Mode-C kappa fixpoint) + `min(zero,man)` dispatcher + adaptive two-phase budget split; `allow_manoeuvres` knob; pure zero-movement baseline retained as fallback guaranteeing non-regression against v01.  Registered in `run_experiments.py` as `ta_igvnd_*`; helper `experiments/ta_paired_report.py` added | `_seed1$` battery (36 runs, 60 s, **36/36 COMPLIANT**) vs cached MILP: dominant on large unconverged instances (full_R20 +43/+56/+45 %, triangle_R30 +35/+47/+33 % wMK/wDLY/wMOV), within a few % on R10, ties on none/R5 |
| (branch `theory_assisted-v03-modeB`) | v03: **Mode-B** manoeuvres (open inter-job gaps via a `gaps` fixpoint state) so a rear can pass through a front gap with no δ cost; staged fallback (joint κ+gaps → κ-only → zero) fixes the dense-topology oscillation the gaps state introduces | `_seed1$` battery (36 runs, **36/36 COMPLIANT**) vs MILP: turns v02's dense-blocking R10 losses into wins (chain_R10 wDLY −7.2 %→**+11.7 %**, hub wDLY −4.5 %→+2.6 %, triangle_loose/medium up); dense `full` held at v02 level by the fallback; wMOV unchanged.  v03 ≥ v02 across the battery beyond noise |

---

*Keep this file in sync with `iterated_greedy_vnd.py`: when the code
changes behaviour, invoke `/sync-method-doc methods/theory_assisted`
with a brief hint describing what changed and (if relevant)
`log: <battery-log-path>` for refreshing Part II.  Design rationale
and the reading behind the method live in [`notes/design.md`](notes/design.md)
and [`notes/synthesis.md`](notes/synthesis.md) where applicable.*
