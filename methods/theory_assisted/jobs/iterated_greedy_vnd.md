# `iterated_greedy_vnd.py` — what the heuristic does

> Companion doc for [`iterated_greedy_vnd.py`](iterated_greedy_vnd.py)
> (`IteratedGreedyVNDJobSolver`, label `iterated_greedy_vnd`).
> **Keep this file in sync with the code** — when the `.py` changes, update
> the matching section here. Design rationale lives in
> [`notes/design.md`](notes/design.md); the reading that informed it in
> [`notes/synthesis.md`](notes/synthesis.md).

## Purpose

A clean-room heuristic for the paper-#2 (job-level) aircraft-positioning
problem. It implements **Candidate A** of the synthesis: an **Iterated
Greedy** outer loop around a **Variable Neighbourhood Descent** local
search, over a two-layer model:

- **Outer decision** — the position assignment `π : R → P` and a global
  priority `order` over the aircraft.
- **Inner decision** — a deterministic *decoder* turns `(assignment, order)`
  into job start/finish times and a movement count.

The solver returns the solution dict consumed by `problems/jobs/checker.py`
(`status`, `objective`, `metrics.{makespan,total_delay,movements}`,
`aircraft[…].{id,position,start,finish,delay,jobs[…]}`).

## Solver contract (`shared/application.py`)

| method | behaviour |
| --- | --- |
| `name` | `"iterated_greedy_vnd"` |
| `configure_solver(**kw)` | stores config (see knobs below) |
| `solve(instance)` | runs the search, returns the solution dict |
| `get_config()` | returns the stored config |
| `get_log()` | per-run trace (construction, per-start objective, accept/reject) |

`TheoryAssistedJobSolver` is kept as a backwards-compatible alias of the class.

### Config knobs (all optional)

| key | default | meaning |
| --- | --- | --- |
| `time_limit_s` | 60 | wall-clock cap (the only key Application guarantees) |
| `weight_makespan` / `weight_delay` / `weight_movements` | 0.1 / 1 / 10 | objective weights `Wᴹ, Wᴰ, Wˢ` |
| `seed` | 1 | base RNG seed; start *i* uses `seed+i` |
| `n_starts` | 4 | multi-start restarts (best kept) |
| `k_destroy` | `max(1, R//4)` | aircraft removed per IG perturbation |
| `max_no_improve` | 400 | early-stop a search after this many stale IG iterations |
| `use_v3` | `True` | enable the manoeuvre-aware polish (phase 2) |

## How `solve()` works

```
prepare instance  →  greedy NEH construction (shared by all starts)
for each multi-start i (seed = base+i), within time_limit / n_starts:
    phase 1 — search with the zero-movement decoder (v2)        [floor]
    phase 2 — search with the manoeuvre-aware decoder (v3)      [polish]
              accept the v3 result only if the real checker certifies
              it AND it strictly beats the v2 floor
keep the global best across starts
```

Multi-start matters: the per-start variety comes from the IG perturbation
RNG, and different seeds land in different basins.

### Search (`_search`, shared by both phases via `self._decode_fn`)

- **Construction** — NEH order (longest total processing `Tᵣ` first) +
  greedy best-position insertion (`_greedy_construct`).
- **VND** (`_vnd`, sequential B-VND reset), first-improvement over three
  neighbourhoods: `_n_reassign` (move one aircraft to another position),
  `_n_swap_pos` (swap two aircraft's positions), `_n_reorder` (swap two
  aircraft in the priority order).
- **Iterated Greedy** (`_perturb`) — remove the `k_destroy` highest-
  contribution aircraft (delay-weighted, lightly randomised) and greedily
  reinsert each at its best (position, order-slot); accept-if-not-worse,
  track global best, restart the walk from best every 50 stale iterations.

## The decoders

Both decoders place aircraft so that **every blocking-arc access is valid**
and report `makespan`, `total_delay`, `movements`.

### v2 — zero-movement (`_decode`, the floor)

Guarantees `movements = 0` by construction. For each blocking arc
`(front, rear)` the rear aircraft is placed **before**, **after**, or
**enclosing** the front (margin `eta`) — all three leave the rear's entry
and exit in **Mode A** (front vacant). Aircraft on the same position are
separated by `epsilon`; aircraft on non-conflicting positions run fully in
parallel. `_forbidden()` emits, per already-placed neighbour, the infeasible
start-time bands (two bands leave a feasible *hole* = the nesting option);
the scan takes the earliest feasible start. Jobs are packed tight, `κ = 0`.

### v3 — manoeuvre-aware (`_decode_v3`, the polish)

Lets rear aircraft interrupt fronts, **spending manoeuvres to compress** the
schedule when the weights reward it. Positions are scheduled **deep-first**
(rears before fronts) so each front sees its rears' access instants fixed.
For each front, `_place_front` picks the **minimum-cost** start
(`Wᴹ·finish + Wᴰ·delay + Wˢ·movements`) from a candidate set that always
includes the zero-movement before/after/nested options — so v3 only ever
*adds* manoeuvre options, never removes a feasible one. `_sim_front`
forward-simulates one front and classifies each rear access:

- **Mode C** — strictly inside an *interruptible* job interior; the job is
  extended by `delta` (per-job `κ` fixpoint). `+2` movements.
- **Mode B** — routed through a deliberately inserted inter-job **gap**
  (no job extension), sized `≥ μ · (#accesses in the gap)`. A gap is opened
  after a job for the accesses just past its end when that is cheaper than
  Mode C (within `delta` of the end) or when the next job is
  non-interruptible (so the access *must* pass through a gap). `+2`.
- **Mode A** — outside the front's stay; free.
- otherwise (access in an `eta`-margin or a non-interruptible interior) →
  infeasible, the candidate start is rejected.

### Safety net

`v2` is a guaranteed-feasible floor. Every `v3` candidate is validated with
the **real `problems/jobs/checker.py`** (`_is_compliant`) and accepted only
if compliant *and* strictly better. So the solver can never regress below
v2 nor emit an infeasible schedule, even if `_sim_front` ever diverges from
the checker (the candidate is simply rejected).

## Status vs the MILP (small benchmark)

Matches the MILP optimum on every R5 and every no-blocking profile (0
manoeuvres). On `triangle_R10` the Mode-B capability lets it **reach or beat
the MILP's reported objective** on the makespan- and delay-priority
profiles by spending 8–10 Mode-B manoeuvres. Note the MILP discretises time
to an integer grid whereas the checker (the problem's source of truth)
admits the `ε = 0.5` fractional placements the heuristic uses, so a
checker-valid heuristic schedule can legitimately undercut the MILP's
grid-restricted optimum.

## Isolation

The solver imports nothing from other methods. The lazy
`from checker import check_solution` in `_is_compliant` targets
`problems/jobs/` (allowed), not a method, so
`experiments/tests/test_method_isolation.py` reports 0 violations.

## Smoke test

```
py -3 methods/theory_assisted/jobs/iterated_greedy_vnd.py \
    problems/jobs/instances/scn_triangle_tight_P5_R5/scn_triangle_tight_P5_R5_seed1.json 10
```
Prints the per-run log, the objective/metrics, and the full checker report.
