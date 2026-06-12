# Iterated Greedy + VND heuristic for job-level aircraft positioning

This document has two parts. **Part I** explains the heuristic as a method,
the way a paper would, with no reference to the source code. **Part II**
explains how that method is realised in code.

---

# Part I — The method

## 1. Problem recap and notation

A fleet of aircraft `R` must be serviced in a hangar of parking positions
`P`. The hangar geometry is a set of **blocking arcs**: an arc `(p, p′)`
means a front position `p` obstructs the access path to a rear position
`p′`, so an aircraft parked at `p` physically blocks the entry and exit of
any aircraft at `p′`.

Each aircraft `r` carries an ordered chain of jobs with fixed durations; the
chain must run in order, the aircraft cannot start before its earliest start
`Eᵣ`, and finishing after its target `Lᵣ` incurs a delay
`vᴰᵣ = max(0, fᵣ − Lᵣ)`. Each job is *interruptible* or not. Let `Tᵣ` be the
total processing time of aircraft `r`.

A solution assigns each aircraft to one position `π(r)` and fixes a start
time for every job. Two aircraft at the same position must be serviced one
after the other, separated by at least the tow time `ε`. Whenever a
rear-position aircraft enters or leaves (its two **access instants**, entry
and exit), the state of the front position at that instant determines a
**mode**:

- **Mode A** — the front position is vacant at that instant (the access
  instant lies at least `η` before the front aircraft starts or at least `η`
  after it finishes). No manoeuvre, no cost.
- **Mode B** — the front aircraft is mid-stay but the instant falls in an
  **inter-job gap** of the front aircraft. The front aircraft is towed out
  and back: **+2 movements**, and the gap must be wide enough to absorb the
  manoeuvres routed through it (`gap ≥ μ · n`, with `n` the number of
  accesses using it). No job is extended.
- **Mode C** — the front aircraft is mid-job and that job is
  **interruptible**: the job is paused, the manoeuvre is performed, the job
  resumes — **+2 movements** and the job is lengthened by `δ` (its
  interruption counter `κ` increases by one). If the job is *not*
  interruptible the access is **infeasible**.

The objective minimises a weighted sum of makespan `m`, total delay, and
total movements `n`:

```
min  Wᴹ·m  +  Wᴰ·Σ vᴰᵣ  +  Wˢ·n .
```

## 2. Design principle: separate assignment from timing

The method follows the recurring theme of the scheduling literature it draws
on (NEH / Iterated Greedy, Variable Neighbourhood Descent, Iterated Local
Search): **separate the expensive combinatorial decision from the cheap
timing decision**.

- An **outer** layer fixes the *combinatorial* state: which aircraft goes to
  which position, plus a global priority order over the aircraft.
- An **inner** layer is a deterministic **decoder** that turns that
  combinatorial state into concrete job start/finish times, classifies every
  blocking access, and returns the objective.

All search happens on the small outer state; the decoder is the oracle that
prices it.

## 3. The decoder — turning an assignment + order into a schedule

The decoder is the heart of the method, and it comes in two regimes.

### 3.1 Zero-movement regime

This regime produces schedules that are **feasible by construction with no
manoeuvres at all** (`n = 0`). The idea: for every blocking arc, keep each
rear aircraft's two access instants in Mode A. Relative to a front aircraft,
that leaves exactly three admissible placements of the rear aircraft's stay:

1. entirely **before** the front (rear exit `≤` front start `− η`),
2. entirely **after** the front (rear entry `≥` front finish `+ η`), or
3. **enclosing** the front (rear enters `≥ η` before the front starts and
   leaves `≥ η` after it finishes).

The third placement — **nesting** — is what makes the regime competitive:
when one aircraft is long enough to wrap a shorter one, two
blocking-related aircraft can overlap in time instead of being serialised.
Without nesting the whole blocking component would have to run sequentially.

Aircraft sharing a position are separated by `ε`; aircraft on
non-conflicting positions run fully in parallel. Given the priority order,
each aircraft is placed at the earliest start time that satisfies these
constraints against everything already placed (a forbidden-interval scan
that naturally lands in the "hole" left by the nesting option). Jobs are
packed tight, so `κ = 0` everywhere and no Mode-B/Mode-C feedback on timing
can arise.

This regime is fast, always feasible, and on instances with little or no
blocking it is already optimal.

### 3.2 Manoeuvre-aware regime

When the weights make manoeuvres worth their cost, the schedule can be
compressed further by *spending* them. This regime lets a rear aircraft
overlap a front aircraft and pay for it:

- Positions are processed **deepest-rear first**, so that when a front
  aircraft is scheduled, the access instants of all the rear aircraft it
  blocks are already fixed. The front is then laid out against those fixed
  instants.
- Laying out a front aircraft, each fixed rear access that falls within its
  stay is resolved as either:
  - **Mode C** — it lands inside an interruptible job; the job absorbs it
    and lengthens by `δ`. A short per-job fixed-point is needed because
    lengthening a job can pull further accesses into it.
  - **Mode B** — a **gap** is opened between two jobs so the access passes
    through it with no job extension. A gap is preferred when it is cheaper
    than a Mode-C interruption (the access lies within `δ` of a job end) or
    when the next job is non-interruptible and the access could not be
    absorbed at all. The gap is sized `≥ μ · (number of accesses routed
    through it)`, and every access that ends up inside it is counted.
- The **start time of each front aircraft is chosen to minimise its local
  contribution to the objective**, `Wᴹ·finish + Wᴰ·delay + Wˢ·movements`,
  evaluated over a set of candidate starts that includes the three
  zero-movement placements *and* starts that align a job interior over an
  access (to invite a cheap Mode-C) or a job end just before an access (to
  invite a cheap Mode-B). Because the zero-movement placements are always
  candidates, this regime can only ever *add* the manoeuvre option — it
  never discards a feasible no-movement schedule.

Mode-B is the decisive ingredient for makespan-priority weights: a manoeuvre
through a gap costs `μ` of idle time rather than the `δ` of a job
extension, and it is the only way to move a rear aircraft past a
non-interruptible front job. It lets the heuristic find compact overlapping
schedules that pure nesting cannot.

## 4. Construction

The initial solution uses an **NEH-style greedy insertion**: aircraft are
ordered by decreasing total processing time `Tᵣ` (longest first), and each
is inserted, in turn, at the position that minimises the partial objective
of the aircraft placed so far. This deterministic seed is strong and is
shared by every restart.

## 5. Local search — Variable Neighbourhood Descent

The construction is refined by a sequential VND with the "basic" reset rule
(on any improvement, return to the first neighbourhood). Three
neighbourhoods, explored first-improvement:

1. **Reassign** — move one aircraft to a different position.
2. **Swap positions** — exchange the positions of two aircraft.
3. **Reorder** — swap two aircraft in the global priority order (which
   changes same-position sequencing and placement priority).

## 6. Iterated Greedy outer loop

Around the VND runs an Iterated-Greedy perturbation loop:

- **Destruction** — remove the `k` aircraft that contribute most to the
  objective (delay-weighted, with light randomisation so the loop explores
  rather than repeating the same removals).
- **Reconstruction** — greedily reinsert each removed aircraft at its best
  (position, order-slot).
- **Local search** — re-apply the VND.
- **Acceptance** — keep the new local optimum if it does not worsen the
  current walk; track the global best separately; restart the walk from the
  global best after a streak of non-improving iterations.

## 7. Multi-start

The whole construct-and-improve procedure is run several times from
different random streams (the construction is shared, but the IG
perturbation randomness differs per start), and the best result is kept. The
restart-to-restart variety matters on tight-blocking instances, where
different streams settle in different basins.

## 8. How the two regimes are combined

Each restart first searches in the **zero-movement regime** (a fast, always-
feasible floor) and then **polishes in the manoeuvre-aware regime**. The
polished, manoeuvre-spending schedule is adopted only if it is **certified
feasible by the independent compliance checker** *and* strictly better than
the zero-movement floor. Consequently the method can never return an
infeasible schedule and can never do worse than its zero-movement result,
regardless of any approximation inside the manoeuvre-aware decoder.

## 9. Behaviour observed

- On instances with no blocking, and on the small five-aircraft instances,
  the method reaches the exact optimum on every weight profile, at zero
  manoeuvres.
- On tight-blocking medium instances, the manoeuvre-aware regime spends
  Mode-B/Mode-C manoeuvres to reach — and, where the reference MILP grids
  time to integers while the continuous schedule is admissible, slightly
  beat — the MILP's reported objective on the makespan- and delay-priority
  profiles, in a few tens of seconds.

---

# Part II — How it is implemented

Source: [`iterated_greedy_vnd.py`](iterated_greedy_vnd.py) — class
`IteratedGreedyVNDJobSolver`, registered under the label
`iterated_greedy_vnd`. `TheoryAssistedJobSolver` is kept as a
backwards-compatible alias.

## Solver contract (`shared/application.py`)

| member | role |
| --- | --- |
| `name` | `"iterated_greedy_vnd"` |
| `configure_solver(**kw)` | store config |
| `solve(instance)` | run the search, return the solution dict |
| `get_config()` | return stored config |
| `get_log()` | per-run trace (construction, per-start objective, accept/reject) |

The returned dict matches `problems/jobs/checker.py`: `status`, `objective`,
`metrics.{makespan,total_delay,movements}`, and `aircraft[…]` with
`id, position, start, finish, delay, jobs[…].{id,start,finish}`.

### Config knobs

| key | default | meaning |
| --- | --- | --- |
| `time_limit_s` | 60 | wall-clock cap |
| `weight_makespan` / `weight_delay` / `weight_movements` | 0.1 / 1 / 10 | `Wᴹ, Wᴰ, Wˢ` |
| `seed` | 1 | base RNG seed; start *i* uses `seed+i` |
| `n_starts` | 4 | multi-start restarts (§I.7) |
| `k_destroy` | `max(1, R//4)` | aircraft removed per IG perturbation (§I.6) |
| `max_no_improve` | 400 | stale-iteration early stop per search |
| `use_v3` | `True` | enable the manoeuvre-aware polish (§I.3.2) |

## Method ↔ code map

| Method concept (Part I) | Code |
| --- | --- |
| Instance preprocessing (chains, `Tᵣ`, blocking arcs, depths, interruptibility) | `_prepare` |
| Two-layer state | `assignment: dict[r→p]` + `order: list[r]` |
| Zero-movement decoder (§3.1) | `_decode`; admissible-placement bands in `_forbidden` |
| Manoeuvre-aware decoder (§3.2) | `_decode_v3`; per-front placement `_place_front`; forward simulation with Mode-B/C `_sim_front` |
| NEH construction (§4) | `_greedy_construct`, `_neh_order` |
| VND neighbourhoods (§5) | `_vnd`, `_n_reassign`, `_n_swap_pos`, `_n_reorder` |
| IG perturbation (§6) | `_perturb` |
| Search driver (decoder-agnostic via `self._decode_fn`) | `_search` |
| Two-regime combination per restart (§8) | `_one_start` (phase 1 = `_decode`, phase 2 = `_decode_v3`) |
| Multi-start (§7) | loop in `solve` |
| Safety net (§8) | `_is_compliant` calls the real `check_solution` |

## Key implementation notes

- `_forbidden` emits, per already-placed neighbour, the infeasible
  start-time bands; for a blocking pair the *two* bands leave a feasible
  hole between them — that hole is the nesting option of §3.1.
- `_sim_front` returns `(finish, sched, mov_events, feasible)`; `mov_events`
  folds Mode-B + Mode-C events and `movements = 2·mov_events`. It rejects a
  start (returns infeasible) on an access in an `η`-margin, a Mode-C on a
  non-interruptible job, or any access it cannot classify.
- The objective inside the decoders is `Wᴹ·makespan + Wᴰ·total_delay +
  Wˢ·movements`; the zero-movement decoder fixes `movements = 0`.

## Safety net and validation

The zero-movement result is a guaranteed feasible floor. Every
manoeuvre-aware candidate is validated against the real paper-#2 checker
(`_is_compliant` → `problems/jobs/checker.py`) and accepted only if
compliant and strictly better. So an imperfect simulation can only fail to
improve — never produce a wrong answer.

## Isolation

The solver imports nothing from other methods. The lazy
`from checker import check_solution` inside `_is_compliant` targets
`problems/jobs/` (allowed), so `experiments/tests/test_method_isolation.py`
reports 0 violations.

## Smoke test

```
py -3 methods/theory_assisted/jobs/iterated_greedy_vnd.py \
    problems/jobs/instances/scn_triangle_tight_P5_R5/scn_triangle_tight_P5_R5_seed1.json 10
```
Prints the per-run log, the objective/metrics, and the full checker report.

---

*Keep this file in sync with `iterated_greedy_vnd.py`: when the code changes
(new regime, neighbourhood, config knob, behaviour), update the matching
section here. Design rationale and the reading behind the method live in
[`notes/design.md`](notes/design.md) and [`notes/synthesis.md`](notes/synthesis.md).*
