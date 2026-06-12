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

## v3 — manoeuvre-aware decoder (implemented)

The heuristic can now *spend* Mode-C manoeuvres to compress the schedule
when the weights reward it. `solve()` runs two phases:

1. **Phase 1 (v2 decoder)** — the fast zero-movement search above, on the
   first ~50 % of the budget; gives a good assignment + order.
2. **Phase 2 (v3 decoder)** — a VND/IG polish using `_decode_v3`, which
   *allows* rear aircraft to interrupt fronts. Positions are scheduled
   **deep-first** (rears before fronts), so when a front is placed its
   rears' access instants are fixed; `_sim_front` lays the front's jobs
   out tight and runs a per-job **κ fixpoint** (each rear access inside an
   interruptible job interior adds one interruption → `+delta`), counting
   movements. `_place_front` picks the **minimum-cost** start
   (`wM·finish + wD·delay + wS·movements`) from a candidate set that always
   contains the rear-before / after / nested zero-movement options — so v3
   only ever *adds* the manoeuvre option, never removes a feasible one.

**Safety net.** Phase-2 results are validated with the real `checker.py`;
v2 is the guaranteed floor and the v3 solution is taken only if it is
compliant *and* strictly better. So v3 can never regress or emit an
infeasible schedule (if `_sim_front` ever diverges from the checker, the
candidate is simply rejected and v2 stands).

### v3 candidate generation + multi-start

`_place_front` seeds its start-time candidate set with, for every rear
access and every *interruptible* job, the start that slides that job's
interior over the access — so the front can absorb an access as a feasible
Mode-C interruption instead of being pushed past it. `solve()` also wraps
the whole two-phase search in a **multi-start** loop (`n_starts`, default 4;
seeds `base..base+n`), keeping the global best — the per-start variety comes
from the IG perturbation RNG and matters: on triangle_R10 (100/1/1)
different seeds find 60.5 (0 mov) vs 61.5 (2 mov).

## Where we stand vs the MILP

Matches the MILP **exactly on every instance where the MILP proves
optimality** — all R5 profiles and all no-blocking profiles — at 0
manoeuvres. On `triangle_R10`:

| profile | MILP (ms/dly/mov) | IG+VND (ms/dly/mov) | gap |
| ------- | ----------------- | ------------------- | --- |
| wMK (100/1/1) | 59.5 / 101.5 / 8  *(optimal)*       | 60.5 / 110.0 / 0 | +1.7 % |
| wDLY (1/100/1) | 60.5 / 101.5 / 10 *(not proven)*   | 64.5 / 105.0 / 2 | +3.4 % |
| wMOV (1/1/100) | 62.5 / 103.5 / 0  *(not proven)*   | 62.5 / 108.5 / 0 | +3.0 % |

## Remaining gap (drives the next iteration)

The last ~1.7 % on `triangle_R10` makespan-priority is structural: the MILP
reaches 59.5 by buying **Mode-B** manoeuvres (a rear slips through a front's
inter-job *gap*, **no** δ extension), whereas the heuristic only does
Mode-C (δ inflates makespan, so it never beats the 60.5 nested 0-mov
schedule). Closing it needs deliberate inter-job gap insertion sized
`≥ μ·n` — a new timing decision in the decoder — or a front placement that
co-optimises several fronts at once instead of greedily one at a time.
