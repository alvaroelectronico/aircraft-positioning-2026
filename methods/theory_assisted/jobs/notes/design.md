# Design — Candidate A (Iterated Greedy + VND), v1

**Status:** first heuristic, implemented in
[`iterated_greedy_vnd.py`](../iterated_greedy_vnd.py)
(`IteratedGreedyVNDJobSolver`, label `iterated_greedy_vnd`).
**Picked from:** [synthesis.md](synthesis.md) → Candidate A (IG+VND), the
recommended starting point.

## Two-layer architecture

Per the synthesis convergent theme *separation of position assignment from
job timing*:

1. **Outer** decision = assignment `pi : R → P` + a global priority order.
2. **Inner** decision = a deterministic **decoder** (assignment, order) →
   job start/finish times.

## v1 decoder: zero-movement by construction

The hard part of paper #2 is the κ feedback loop: a Mode-C interruption
extends a front aircraft's job, which shifts its finish, which shifts
same-position successors and the access windows seen by rear aircraft.
To get a correct first heuristic without solving that fixpoint, v1 uses a
**zero-movement decoding rule**:

> For each blocking arc `(front, rear)`, the rear aircraft's entry and
> exit must each be **Mode A** relative to the front stay — i.e. the rear
> is placed **before**, **after**, or **enclosing** the front (margins
> `eta`). Aircraft on the same position are separated by ≥ `epsilon`
> (RQ08). Aircraft on non-conflicting positions run fully in parallel.

Under this rule every rear access instant falls outside the front
aircraft's stay ⇒ the checker classifies it **Mode A** ⇒
`movements = 0`, `kappa = 0`, no timing feedback. The decoder is an
earliest-feasible-start list scheduler (jobs packed tight in chain
order); `_forbidden()` emits the infeasible start-time bands per placed
neighbour, leaving a feasible *hole* for the nesting option. Feasibility
is guaranteed and confirmed by `checker.py` on every run (RQ01–RQ09 PASS).

**Nesting / containment (the key relaxation).** Allowing the rear to
*enclose* the front (rather than only before/after, as the first cut did)
lets blocking-related aircraft overlap in time whenever one is long
enough to wrap the other. This is what breaks the full-serialisation
bottleneck on tight-blocking topologies — still at zero movements. On the
benchmark it pulls the heuristic up to the MILP optimum on R5
(triangle_R5_s1/s2: makespan 30 / 37, delay 0 — matching the MILP exactly)
and to within ~5 % makespan of the MILP on triangle_R10 while using
**0 manoeuvres vs the MILP's 8–10**.

**What this optimises:** `makespan` and `total_delay` only (movements are
always 0), via the choice of assignment and order. The IG+VND loop searches
that space.

## IG + VND loop

- **Construction:** NEH order (longest `T_r` first) + greedy best-position
  insertion (each aircraft placed at the position minimising the partial
  objective).
- **VND (B-VND reset)** over three neighbourhoods, first-improvement:
  N1 reassign one aircraft, N2 swap two aircraft's positions, N3 swap two
  aircraft in the priority order.
- **Perturbation (Iterated Greedy):** remove the `k = max(1, R//4)` highest
  -contribution aircraft (delay-weighted, lightly randomised), greedily
  reinsert each at its best (position, order-slot).
- **Acceptance:** accept-if-not-worse for the walk; track global best
  separately; restart the walk from best every 50 stale iterations.
  Early-stop after `max_no_improve` (default 400) non-improving iterations.

## Remaining gap of v1 (drove v02)

Even with nesting, v1 never *spends* a manoeuvre: it stays at zero movements
by construction. On tight-blocking instances the MILP edges ahead by buying
a few Mode-B/C manoeuvres to compress the schedule. That residual gap is
exactly the trade v1 could not make.

# v02 — manoeuvre-spending decoder (Mode C) + κ fixpoint

**Status:** implemented in [`iterated_greedy_vnd.py`](../iterated_greedy_vnd.py)
(2026-06-15). The two-layer architecture, the IG loop and the three VND
neighbourhoods are **unchanged** — only the decoder and the search schedule
gained capabilities, exactly as v1's "next iteration" note anticipated.

## What changed and why

The benchmark weight profiles this attempt targets are the three *pure*
profiles `(W^M,W^D,W^S) ∈ {(100,1,1), (1,100,1), (1,1,100)}`. Measurement
reframed the motivation away from v1's "compress makespan" story:

- under the default `(0.1,1,10)` profile even the MILP picks **0 movements**
  (R10 seed1: MILP obj 110.55, makespan 60.5, delay 104.5, mov 0), so
  manoeuvres only pay on `(100,1,1)` (makespan) and `(1,100,1)` (delay);
- under `(1,1,100)` (movements) the zero-movement decode is already optimal
  on the dominant term — so a decoder that *may* spend manoeuvres but is
  never forced to dominates all three.

## The manoeuvre-aware decoder (`_decode_man`)

A forward list-scheduler places each aircraft (in `order`) at the start time
minimising a **weight-aware local cost** `wM·finish + wD·delay + wS·2·events`
over a candidate set induced by the placed neighbours. A rear access instant
may now land **Mode C** — strictly inside an *interruptible* front job —
which pauses that job (`κ += 1`, the job grows by `δ`) at a cost of 2
movements, whenever the weighted cost rewards it. Landing inside a
non-interruptible job, or on a packed job boundary, is rejected as
infeasible.

**κ fixpoint.** A Mode-C interruption lengthens the front job, shifting the
front aircraft's finish and its same-position successors, which changes the
access windows other rears see. The decoder therefore iterates: place →
re-classify every access (mirroring `checker.py`) → recompute κ → rebuild
durations → re-place, until the interruption counts stabilise (cap 8). At
convergence the durations used equal `D_j + δ·κ_j` and the classification
reproduces exactly those κ, so the schedule is self-consistent and passes
the checker.

## Two safety guarantees (v02 ≥ v01, always feasible)

1. **`_decode` returns `min(zero, man)`** per (assignment, order): it
   evaluates both the v1 zero-movement decode and `_decode_man` and keeps the
   lower-objective one. v02 is therefore never worse than v1 on any
   (assignment, order). (Bonus: on several instances `_decode_man` wins
   *at zero movements* — its weight-aware forward pass packs tighter than the
   v1 earliest-fit rule.)
2. **Non-convergence falls back** to the zero-movement decode, which is always
   feasible and consistent.

## Adaptive two-phase search (handles the decoder's cost)

`_decode_man` is ~50× slower than the zero decode and *starves* the IG search
on large instances (R20 hit 0 IG iterations once manoeuvres were on). The
search is therefore split: **phase A** uses the fast zero decoder to fix a
strong incumbent, **phase B** turns manoeuvres on to refine it. The split is
adaptive to size (`man_phase_frac`): `R ≤ 12` → manoeuvres from the start;
`13 ≤ R ≤ 22` → 50/50; `R ≥ 23` → full budget to phase A (identical to v1)
plus a single manoeuvre *polish* at the end. The large-instance setting keeps
phase A ≡ v1 and the final polish can only improve, so v02 never regresses.

## Results (v02 vs v01 baseline, 20 s, all COMPLIANT)

| instance         | wMK (100,1,1) | wDLY (1,100,1) | wMOV (1,1,100) |
| ---------------- | ------------- | -------------- | -------------- |
| triangle_R10     | −6.3 %        | −10.9 %        | −5.7 %         |
| triangle_R20     | −1.1 %        | −2.5 %         | −7.1 %         |
| triangle_R30     |  0.0 %        |  0.0 %         | −0.3 %         |
| full_R20         | **−22.3 %**   | −9.5 %         | **−29.9 %**    |

Manoeuvres are actually spent where the topology is dense (full_R20: up to
38–60 movements under the makespan/delay profiles); on sparse triangle
topologies most of the gain comes from the tighter weight-aware packing at
zero movements.

## Remaining gap (drives the next iteration)

- **Mode B not yet created.** The decoder packs each aircraft's jobs tight,
  so there are no inter-job gaps to route a Mode-B access through. Opening a
  gap of `≥ μ` between two front jobs (cost 2 movements, no δ extension) is
  the natural next lever — it lets a rear pass without lengthening any job,
  which the makespan profile should favour.
- **Polish only on the single best (a,o) for large R.** An elite pool of the
  top-K phase-A solutions, each manoeuvre-polished, would likely recover more
  on R ≥ 23 than polishing only the incumbent.
- **Decoder speed.** Incremental re-classification (only arcs incident on the
  moved aircraft change) would let manoeuvres run throughout the search even
  on large instances, removing the need for the size-based phase split.
