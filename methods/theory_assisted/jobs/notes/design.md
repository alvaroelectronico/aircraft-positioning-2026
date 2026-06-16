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

# v03 — Mode-B manoeuvres (open inter-job gaps)

**Status:** implemented in [`iterated_greedy_vnd.py`](../iterated_greedy_vnd.py).
v02's gap analysis named Mode B as the next lever; v03 adds it as a **second
fixpoint state** alongside κ.

## Why Mode B

v02's battery (vs the cached MILP) trailed only on a few small dense R10
instances — notably `chain_R10` (−7 % wMK) — where the MILP compresses the
makespan by routing rear accesses through **inter-job gaps** of the front
aircraft. v02 could not do this: its decoder packs each aircraft's jobs tight,
so no gap exists, and any access landing on a packed boundary is rejected.
Mode B is the cheap manoeuvre (2 movements, **no δ extension** — unlike Mode C)
that the makespan/delay profiles reward.

## The gaps fixpoint

A new state `gaps[(aircraft, k)] = width` records the gap opened after job `k`
of an aircraft; `_job_intervals` inserts it, so the aircraft's finish grows by
the total opened width. The decoder now iterates a **joint (κ, gaps) fixpoint**:

> place (forward pass, weight-aware `_choose_start` now also proposes
> *Mode-B candidates* — start times that land a rear access on a front
> inter-job boundary) → re-classify every access → set `κ` from Mode-C counts
> **and** `gaps[(rf,k)] = μ · (#accesses through that gap)` from Mode-B counts
> → rebuild durations/gaps → re-place, until **both** κ and gaps stabilise.

A structural property helps: opening a gap *after* job `k` does not move job
`k`'s finish, so a rear access targeted at that boundary stays valid across
iterations, and the cumulative-μ rule holds by construction (gap = μ·count).

**Staged fallback (the convergence fix).** Adding the gaps state makes the
joint fixpoint *oscillate on dense topologies*: instrumenting `full_R10` showed
**37 % of manoeuvre decodes hit the iteration cap without converging**, falling
back to the (on dense topologies, very poor) zero-movement decode — which
regressed those cases. The greedy per-pass `_choose_start` re-decision, now with
more modes to flip between, is the oscillation driver, and κ must equal the
classified Mode-C count *exactly* for the checker (so we cannot just damp it).
The fix is a **staged decode** (`_decode_man` → `_man_fixpoint`): try the joint
(κ, gaps) fixpoint with a short cap (5); if it does not converge, retry with
**Mode-B disabled** (`_enable_b = False` → the v02 κ-only fixpoint, cap 8, which
is stable on dense instances); only then fall back to zero. So dense topologies
recover exactly the v02 result while sparse ones keep the Mode-B gains. The v02
safety guarantees still hold — `_decode` returns `min(zero, man)`.

## Results (v03 vs v02, 20 s spot-checks, all COMPLIANT)

Mode B improves exactly the cases v02 left on the table, and is inert where
manoeuvres do not pay:

| instance / profile      | v02 obj  | v03 obj  | change |
| ----------------------- | -------- | -------- | ------ |
| chain_R10 / wMK         | 6681.6   | 6383.5   | −4.5 % |
| chain_R10 / wDLY        | 13394.0  | 11083.5  | −17.3 %|
| chain_R10 / wMOV        | 259.1    | 259.1    | —      |

(Full `_seed1` battery vs MILP recorded in the living `.md` Part II.)

## Remaining gap (drives the next iteration)

- **Polish only on the single best (a,o) for large R.** An elite pool of the
  top-K phase-A solutions, each manoeuvre-polished, would likely recover more
  on R ≥ 23 than polishing only the incumbent.
- **Decoder speed (v05 — incremental zero decode).** The zero-movement forward
  pass is *causal* — each aircraft's placement depends only on those before it
  in `order` — so a VND move that changes the aircraft at order-index `k` only
  needs `order[k:]` re-placed, reusing the cached prefix `order[:k]`
  (`_zero_place(start=k)` / `_zero_obj_inc`).  The three neighbourhoods use this
  in phase A (zero decode); phase B (manoeuvre decode) is not incrementalised.
  **Exact** — the incremental objective equals the full zero decode (verified:
  1701 random N1/N2/N3 probes, 0 mismatches).  Measured **+14–17 % more search
  iterations** on R30 (phase-A-only) and R20.  Because the search is
  time-limited and stochastic, the *extra* iterations shift the RNG/phase-B
  trajectory, so the end objective is v04 ± noise per seed (equal at equal
  iteration count); the net effect over seeds needs a battery to quantify.
- **Decoder speed (v04 — light-objective path).** The search calls the decoder
  only for its objective, but `_finalise` was building the full per-aircraft /
  per-job solution dict on every call.  v04 adds a `full=False` path (used via
  `_obj`) that computes makespan/delay/objective straight from the stored
  `placed[r]` finishes and skips the dict; the full dict is built only for the
  final solution `solve` returns.  Measured **+28–49 % more search iterations**
  (triangle_R30 wMK 43→64, triangle_R20 wDLY 301→424, full_R20 wDLY 190→243)
  with the objective computation unchanged — a pure speedup that helps the
  time-limited large instances (still improving at 60 s).
- **Decoder speed (v03.1 — interval caching).** Profiling the decode
  showed `_job_intervals` dominating (1.3 M calls, ~3.7 s of a 6 s run): every
  candidate in `_choose_start`/`_eval_start` rebuilt the *placed neighbours'*
  intervals, which do not change while later aircraft are placed. Caching them
  once per forward pass (`placed_jobs`), shifting r's own offsets (`base_r`)
  instead of rebuilding, and a fast path for the no-κ/no-gaps case cut decode
  cost **~1.4–2× (denser topology → bigger win)** with **byte-identical
  results** (verified: deterministic construct+VND objectives unchanged). The
  *remaining* step is true **incremental move evaluation** — only re-classify
  the arcs incident on the aircraft a VND move touched (don't-look bits /
  `getAssignDelta`), which would let manoeuvres run throughout the search on
  large instances and remove the need for the size-based phase split.
- **Joint fixpoint convergence.** κ and gaps co-evolve; the staged fallback
  bounds the cost (joint cap 5 → κ-only cap 8 → zero). Worth instrumenting how
  often the fallback fires across the battery.
