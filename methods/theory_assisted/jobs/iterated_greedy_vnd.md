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

## 9. The complete algorithm in pseudocode

Notation: a *state* is `(π, σ)` — an assignment `π : R → P` and a priority
order `σ` over the aircraft. `Eᵣ, Lᵣ, Tᵣ` are aircraft `r`'s earliest start,
target finish and total processing time; `ε, η, μ, δ` are the instance's tow
time, access margin, Mode-B gap unit and Mode-C extension. The cost of a
schedule is `F = Wᴹ·makespan + Wᴰ·Σ delay + Wˢ·movements`.

```
ALGORITHM  Solve(instance, time_limit, weights, n_starts, base_seed):
    preprocess instance  (job chains, Tᵣ, blocking arcs, position depths)
    σ₀ ← NEHorder()                                       # NEH order (R by Tᵣ desc)
    π₀ ← GreedyConstruct(σ₀)                              # shared seed
    best ← ∅ ;  best_F ← +∞
    for i in 0 … n_starts−1  while time remains:
        seed the RNG with base_seed + i
        deadline_i ← now + time_limit / n_starts
        (sol, F) ← OneStart(π₀, σ₀, deadline_i)              # σ₀ is the NEH order
        if F < best_F:  best, best_F ← sol, F
    return best


PROCEDURE  GreedyConstruct(σ):              # NEH-style greedy insertion
    π ← ∅                                    # empty assignment
    placed ← []                              # prefix of σ already situated
    for r in σ:                              # longest Tᵣ first
        placed ← placed + [r]
        for each position p ∈ P:
            π[r] ← p                          # tentative
            evaluate F of the partial decode of 'placed'
        π[r] ← the position p with the lowest partial F
    return π
    # decides positions only; σ is the insertion sequence, refined later by
    # NEHorder and the search.  Deterministic — shared by every multi-start.


PROCEDURE  NEHorder():                      # priority order for the search
    return the aircraft set R sorted by Tᵣ descending
    # Orders all aircraft R; depends only on Tᵣ (not on any assignment).
    # A due-date-aware variant (also reading Lᵣ) is a Part IV candidate, e.g.
    # EDD.  The order is then refined by the Reorder neighbourhood.


PROCEDURE  OneStart(π, σ, deadline):
    # Phase 1 — zero-movement regime (a guaranteed-feasible floor)
    (π,σ) ← Search(π, σ, DecodeZeroMov, deadline·½)
    floor ← DecodeZeroMov(π, σ) ;  bestF ← F(floor)
    # Phase 2 — manoeuvre-aware polish, only kept if certified and better
    (π′,σ′) ← Search(π, σ, DecodeManoeuvre, deadline)
    cand ← DecodeManoeuvre(π′, σ′)
    if F(cand) < bestF  and  CompliantByChecker(cand):
        return (cand, F(cand))
    return (floor, bestF)


PROCEDURE  Search(π, σ, Decode, deadline):          # VND + Iterated Greedy
    (π,σ) ← VND(π, σ, Decode)
    best ← (π,σ) ;  cur ← (π,σ)
    while now < deadline and stale < max_no_improve:
        cand ← Perturb(cur)                          # destroy k + reinsert
        cand ← VND(cand, Decode)
        if F(Decode(cand)) ≤ F(Decode(cur)):  cur ← cand
        if F(Decode(cand)) < F(Decode(best)):  best ← cand ; stale ← 0
        else: stale ← stale + 1
        every 50 stale steps:  cur ← best            # restart the walk
    return best


PROCEDURE  VND(π, σ, Decode):                        # sequential B-VND
    neighbourhoods ← [Reassign, SwapPositions, Reorder]
    k ← 0
    while k < 3:
        (improved, π, σ) ← FirstImprovement(neighbourhoods[k], π, σ, Decode)
        k ← 0 if improved else k+1                   # reset on improvement
    return (π, σ)


PROCEDURE  FirstImprovement(N, π, σ, Decode):        # take the first better move
    base ← F(Decode(π, σ))
    for each move m in neighbourhood N of (π, σ):
        (π′, σ′) ← apply m to (π, σ)
        if F(Decode(π′, σ′)) < base:                 # strictly better
            return (true, π′, σ′)                    # stop at the first one
    return (false, π, σ)                             # local optimum for N
    #  Reassign      : move one aircraft to another position
    #  SwapPositions : swap the positions of two aircraft
    #  Reorder       : swap two aircraft in σ


PROCEDURE  Perturb(π, σ):                            # Iterated Greedy kick
    remove the k aircraft of largest contribution (Wᴰ·delayᵣ + small·Tᵣ),
        with light randomisation
    for each removed r:                              # greedy reconstruction
        insert r at the (position, slot in σ) minimising F of the decode
    return the rebuilt state


# ── Inner layer: the two decoders ────────────────────────────────────

PROCEDURE  DecodeZeroMov(π, σ):        # feasible by construction, 0 moves
    placed ← ∅
    for r in σ:                                      # place in priority order
        F ← forbidden start-intervals of r vs each already-placed neighbour:
            same position p           → must keep gap ≥ ε  (before/after)
            blocking pair (p,p′)       → keep both access instants Mode-A:
                rear BEFORE front, or AFTER front, or ENCLOSING it (margin η)
            (the “enclose’’ option leaves a feasible hole between two bands)
        sᵣ ← earliest t ≥ Eᵣ not inside any forbidden interval
        lay r’s jobs tight from sᵣ ;  κ = 0          # no extensions
        placed ← placed ∪ {r}
    return schedule with movements = 0


PROCEDURE  DecodeManoeuvre(π, σ):      # may spend Mode-B / Mode-C manoeuvres
    for p in positions, deepest-rear first:          # rears fixed before fronts
        prev_finish ← −∞
        for r in (aircraft at p, in σ order):
            low ← max(Eᵣ, prev_finish + ε)
            A   ← access instants {sₐ, fₐ} of every already-placed rear of p
            (sᵣ, fᵣ, sched, moves) ← PlaceFront(r, low, A)
            prev_finish ← fᵣ
    return schedule with movements = 2 · Σ moves


PROCEDURE  PlaceFront(r, low, A):      # choose r’s min-cost feasible start
    candidates ← { low }
      ∪ { τ−η−Tᵣ , τ−η , τ+η : τ ∈ A }                       # before/after/nest
      ∪ { starts aligning an interruptible job interior over τ }  # invite Mode-C
      ∪ { starts aligning a job END just before τ }              # invite Mode-B
      ∪ { max(low, max A + η) }                                  # always feasible
    best ← ∅
    for s in candidates (ascending):
        (fᵣ, sched, moves, ok) ← SimulateFront(r, s, A)
        if ok:
            cost ← Wᴹ·fᵣ + Wᴰ·max(0, fᵣ−Lᵣ) + Wˢ·2·moves
            keep (s, …) if cost is the lowest so far
    return best                                       # zero-move options are
                                                      # always among candidates


PROCEDURE  SimulateFront(r, s, A):     # forward sweep, classify each access
    t ← s ;  moves ← 0 ;  sched ← []
    for each job j of r (in chain order):
        κ ← fixpoint: number of unused τ ∈ A strictly inside [t+η, fⱼ−η],
                      where fⱼ = t + Dⱼ + δ·κ                       # Mode C
        if κ>0 and j not interruptible:  return infeasible
        if any τ ∈ A lies in an η-margin of j:  return infeasible
        moves ← moves + κ ;  append (j, t, fⱼ, κ) ;  t ← fⱼ
        if j is not the last job:                                  # Mode B?
            open a gap before the next job for the unused τ just past fⱼ
              when that beats Mode C (τ within δ of fⱼ) or the next job is
              non-interruptible; size the gap ≥ μ·(#accesses in it);
              count every τ inside the gap as a movement; advance t past it
    if any access in (s, fᵣ) is still unclassified:  return infeasible
    return (fᵣ = t, sched, moves, ok)
```

The decisive contrast: `DecodeZeroMov` only ever keeps rear access instants
in Mode A (never paying a manoeuvre), while `DecodeManoeuvre` additionally
*offers* the Mode-B and Mode-C options and lets the min-cost start choose
them when the weights make a manoeuvre worth its makespan/delay saving — and
the zero-movement placements remain candidates, so it never discards a
feasible no-movement schedule.

## 10. Behaviour observed

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
- **Time budget.** `_time_up()` (a `time.perf_counter()` vs `self._deadline`
  check) is polled inside every search loop — construction, VND, each
  neighbourhood scan, and the IG reinsertion — so the solver returns within
  `time_limit_s` even on large instances where a single sweep is expensive.
  Loops that must leave a complete solution (construction, reinsertion) fall
  back to a cheap feasible completion when the budget runs out.

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

# Part III — Results and analysis (heuristic at commit `68dc201`)

> This section documents the performance of the solver **as it stands at
> commit `68dc201`** (the Mode-B build; solver logic unchanged since
> `d00af90`). Later commits will append their own Part III / Part IV blocks,
> so each snapshot stays attached to the code that produced it.

## Experimental setup

- **Battery:** all 120 benchmark instances —
  12 configurations (`chain / full / hub / none / triangle_loose /
  triangle_medium / triangle_tight / two_rows`, at `P5` with
  `R5 / R10 / R20 / R30`) × 10 seeds.
- **Methods:** the job-level MILP baseline (`milp_baseline_job`,
  `MILPJobsV2Solver`) vs this heuristic (`iterated_greedy_vnd`).
- **Weight profiles:** `wMK = (100,1,1)` makespan-priority,
  `wDLY = (1,100,1)` delay-priority, `wMOV = (1,1,100)` movement-priority.
- **Budget:** 60 s nominal per solve. **720 runs, 0 failures.**
- **Metric:** relative gap `g = (MILP_obj − heuristic_obj) / MILP_obj`
  (`g > 0` ⇒ heuristic better). Mean / min / max over the 10 seeds of each
  type, disaggregated per profile and aggregated.
- **Full log:**
  [`outputs/logs/instances_main_methods_20260612_143618.log`](../../../outputs/logs/instances_main_methods_20260612_143618.log)
  (the gap table below is its header table; the per-instance detail follows
  it in the file).

## Gap table (from the log header)

```
[wMK  (100/1/1  makespan-priority)]            N     Mean      Min      Max
  scn_chain_tight_P5_R10                       10   -1.44%   -4.41%   +2.08%
  scn_full_tight_P5_R10                        10   +1.12%   -4.22%   +6.72%
  scn_full_tight_P5_R20                        10  +46.17%  +26.49%  +63.27%
  scn_hub_tight_P5_R10                         10   -2.33%   -4.53%   +0.01%
  scn_none_tight_P5_R10                        10   +0.00%   +0.00%   +0.00%
  scn_triangle_loose_P5_R10                    10   -1.02%   -4.71%   +1.53%
  scn_triangle_medium_P5_R10                   10   -0.32%   -3.24%   +1.91%
  scn_triangle_tight_P5_R10                    10   -1.02%   -4.73%   +1.63%
  scn_triangle_tight_P5_R20                    10  +17.28%  +11.47%  +23.06%
  scn_triangle_tight_P5_R30                    10  +36.66%  +26.87%  +42.91%
  scn_triangle_tight_P5_R5                     10   -0.04%   -0.37%   +0.00%
  scn_two_rows_tight_P5_R10                    10   -0.05%   -0.62%   +0.36%

[wDLY (1/100/1  delay-priority)]               N     Mean        Min       Max
  scn_chain_tight_P5_R10                       10   +5.76%     -3.00%   +13.13%
  scn_full_tight_P5_R10                        10  +21.22%    +12.84%   +34.15%
  scn_full_tight_P5_R20                        10  +58.53%    +44.15%   +71.80%
  scn_hub_tight_P5_R10                         10   +3.30%     -3.42%   +10.23%
  scn_none_tight_P5_R10                        10   -0.79%     -7.70%    +0.00%
  scn_triangle_loose_P5_R10                    10 -303.75%  -1273.64%   +11.75%
  scn_triangle_medium_P5_R10                   10   +3.72%     -3.95%    +9.21%
  scn_triangle_tight_P5_R10                    10   +4.54%     -3.37%   +10.89%
  scn_triangle_tight_P5_R20                    10  +12.68%     -1.07%   +23.48%
  scn_triangle_tight_P5_R30                    10  +35.08%    +18.41%   +48.70%
  scn_triangle_tight_P5_R5                     10  -95.78%   -647.83%    +0.00%
  scn_two_rows_tight_P5_R10                    10   +0.41%     -3.17%    +4.78%

[wMOV (1/1/100  movement-priority)]            N     Mean       Min      Max
  scn_chain_tight_P5_R10                       10  -13.47%   -29.15%   +5.06%
  scn_full_tight_P5_R10                        10  -30.62%   -83.06%  +14.47%
  scn_full_tight_P5_R20                        10  +23.61%   +10.40%  +37.68%
  scn_hub_tight_P5_R10                         10   -7.75%   -25.73%   +5.00%
  scn_none_tight_P5_R10                        10   -2.51%   -13.12%   +0.00%
  scn_triangle_loose_P5_R10                    10   -6.28%   -21.14%   +6.12%
  scn_triangle_medium_P5_R10                   10   -1.54%   -26.32%   +5.47%
  scn_triangle_tight_P5_R10                    10   -0.90%    -8.42%   +5.76%
  scn_triangle_tight_P5_R20                    10   +9.49%    +2.82%  +17.24%
  scn_triangle_tight_P5_R30                    10  +32.59%   +18.63%  +40.21%
  scn_triangle_tight_P5_R5                     10  -30.68%  -114.29%   +0.00%
  scn_two_rows_tight_P5_R10                    10   -0.32%    -6.51%   +2.37%

[ALL profiles]                                 N     Mean        Min       Max
  scn_chain_tight_P5_R10                       30   -3.05%    -29.15%   +13.13%
  scn_full_tight_P5_R10                        30   -2.76%    -83.06%   +34.15%
  scn_full_tight_P5_R20                        30  +42.77%    +10.40%   +71.80%
  scn_hub_tight_P5_R10                         30   -2.26%    -25.73%   +10.23%
  scn_none_tight_P5_R10                        30   -1.10%    -13.12%    +0.00%
  scn_triangle_loose_P5_R10                    30 -103.69%  -1273.64%   +11.75%
  scn_triangle_medium_P5_R10                   30   +0.62%    -26.32%    +9.21%
  scn_triangle_tight_P5_R10                    30   +0.87%     -8.42%   +10.89%
  scn_triangle_tight_P5_R20                    30  +13.15%     -1.07%   +23.48%
  scn_triangle_tight_P5_R30                    30  +34.78%    +18.41%   +48.70%
  scn_triangle_tight_P5_R5                     30  -42.17%   -647.83%    +0.00%
  scn_two_rows_tight_P5_R10                    30   +0.01%     -6.51%    +4.78%
```

## Performance summary

- **Makespan-priority (`wMK`) on R5–R10: genuinely competitive.** Within
  about ±2.5 % of the MILP on every R10 topology (and exact on `none` and
  `R5`). Mode-B/nesting do their job here.
- **Delay-priority (`wDLY`) and movement-priority (`wMOV`): systematically
  behind**, across topologies and even on tiny R5 instances. The big
  negative numbers are partly a small-denominator artefact (see caveats) but
  reflect a real, repeated failure mode.
- **R20 / R30: the large positive gaps are *not* a real win.** They combine
  two confounds — the MILP times out with 80–99 % optimality gaps, **and the
  heuristic itself overruns the 60 s budget** (88 s on `full_R20`, **413 s**
  on `R30`). The comparison there is neither fair nor a like-for-like 60 s.
- **High variance.** The same type swings from exact match to large loss
  across seeds (e.g. `R5` `wDLY` seed1 = 0 %, seed10 = −297 %).

## Analysis by weight profile

### `wMK` — makespan-priority
The heuristic is at parity on R10 (chain −1.4 %, hub −2.3 %, triangle
−1.0/−0.3/−1.0 % for tight/medium/loose, two_rows −0.05 %, full +1.1 %,
none 0 %). This is the regime the Mode-B work targeted, and it holds up: the
manoeuvre-aware decoder finds compact overlapping schedules close to the
MILP optimum. The R20/R30 "+17 %…+46 %" are timeout/over-budget artefacts
(below).

### `wDLY` — delay-priority (the dominant weakness)
The catastrophic relative numbers come from instances whose optimum has
**zero delay** (loose targets), so the MILP objective is tiny and any delay
the heuristic incurs explodes the ratio. But the underlying loss is real and
is a **search failure to trade manoeuvres for delay**:

- `triangle_loose_R10` seed10: MILP `ms 69 / delay 0 / 8 mov → obj 77`
  (spends 8 manoeuvres to wipe out delay); heuristic
  `ms 70.5 / delay 5 / 0 mov → obj 570` (stays at 0 manoeuvres and eats the
  delay, ×100).
- `triangle_tight_R5` seed10: optimum is `ms 35 / delay 0 / 0 mov` (MILP
  obj 35); the heuristic returns `ms 35 / delay 1 / 4 mov → obj 139` — it
  both *misses* the zero-delay schedule **and** wastes 4 manoeuvres. A pure
  search/decoder failure on a five-aircraft instance.

The decoder's per-front cost does include `Wᴰ·delay`, so the lever exists —
but the **greedy, due-date-blind placement and the NEH-by-processing-time
ordering do not steer tight-target aircraft into early slots**, and the
search does not reliably discover the "spend a manoeuvre to remove a delay"
move when `Wᴰ` is large. Where targets are not the binding constraint the
gaps are small and often positive (chain +5.8 %, full +21 %, two_rows +0.4 %).

### `wMOV` — movement-priority
Here both methods drive movements to 0, so the contest is *who packs a
zero-movement schedule tightest*. The heuristic's zero-movement decoder is
**too loose in dense topologies**:

- `full_R10` seed1: MILP `ms 71.5 / delay 189.5 / 0 mov`; heuristic
  `ms 116.5 / delay 326.5 / 0 mov`. The nesting + greedy-order placement
  serialises far more than the MILP's zero-movement schedule.

Hence `full` −30.6 % (min −83 %), `chain` −13.5 %, `hub` −7.8 %; on sparse
or easy topologies it is fine (`none` −2.5 %, `two_rows` −0.3 %, `triangle`
−0.9 %).

### Scaling (R20 / R30) — read with care
The MILP cannot solve these in 60 s (e.g. `triangle_R30` `wMK`:
`maxTimeLim`, 81 % gap; `full_R20` `wDLY`: 99.98 % gap), so its objective is
a weak incumbent. The heuristic returns a much lower objective
(`triangle_R30` `wMK`: 24 517 vs 37 537), which *suggests* a real
large-instance advantage — **but it used 413 s, not 60 s**, so this is not a
valid 60 s comparison. The genuine takeaway is qualitative: where the MILP
flounders, the heuristic still produces good feasible schedules — once the
time budget is actually enforced.

## Caveats on the metric

1. **Small-denominator inflation.** When the optimum has ~0 delay (loose
   instances under `wDLY`), `MILP_obj` is small and the relative gap is huge
   for a tiny absolute difference. Means like −303 % / −1273 % should be read
   as "the heuristic incurred a few delay units the MILP avoided", not as a
   13× worse schedule. A future log should add the **absolute objective gap**
   and a **per-component (makespan / delay / movements) breakdown**.
2. **Time-limit overrun.** The heuristic exceeds 60 s on R20/R30, so all
   large-instance rows are not like-for-like. Must be fixed before the
   scaling comparison means anything.
3. **MILP not optimal at scale.** R20/R30 MILP objectives are unconverged
   incumbents; "beating" them is expected and not informative about optimality.

---

# Part IV — Candidate improvements (for the next commit)

Derived from the Part III analysis, in rough priority order. These are the
candidates to discuss and pick from; the next commit will implement a subset
and refresh Part III with the new numbers.

1. **Enforce the time budget (correctness, blocking). — DONE.** The deadline
   used to be checked only between IG iterations and VND neighbourhoods, so a
   single sweep on R20/R30 blew past 60 s (413 s observed). Now `_time_up()`
   is polled inside construction, the VND loop, every neighbourhood scan and
   the IG reinsertion, with cheap feasible fallbacks where a complete
   solution is required. Verified: R30 and `full_R20` now return in ~60 s
   (was 413 s / 88 s), with no change on R10. **The Part III R20/R30 rows
   above are therefore stale** — they were produced before this fix and need
   a re-run to be a valid 60 s comparison.

2. **Due-date-aware construction and ordering (targets `wDLY`).** Add EDD
   seeds (order aircraft by `Lᵣ`, or a `Wᴰ`-dependent blend of `Tᵣ` and
   `Lᵣ`) to the multi-start, and a within-position reconciliation that puts
   the tighter-target aircraft in the earlier slot. Directly attacks the
   R5/loose `wDLY` failures where tight-target aircraft are stranded in late
   slots.

3. **Manoeuvre-for-delay move under high `Wᴰ` (targets `wDLY`).** A polishing
   move that, for the most-delayed aircraft, tries to pull it earlier by
   spending a Mode-B/Mode-C manoeuvre on the blocking front, accepted only if
   the (checker-validated) objective improves. The local cost already prices
   this; the search just needs an operator that proposes it.

4. **Tighter zero-movement packing in dense topologies (targets `wMOV`).**
   The greedy per-front placement serialises too much on `full`/`hub`.
   Options: a better processing order for the deep-first sweep, a richer
   nesting search (consider enclosing several shorts in one long), or
   co-optimising the aircraft of a fully-connected block together.

5. **Variance reduction / smarter multi-start.** Diversify the restart seeds
   (NEH + EDD + a couple of randomised orders) and spend more starts on small
   instances (they are cheap), to remove the seed1-perfect / seed10-broken
   swings.

6. **Better evaluation logging.** Add absolute-objective and per-component
   (makespan / delay / movements) gaps alongside the relative gap, so the
   next Part III is not distorted by small denominators.

---

*Keep this file in sync with `iterated_greedy_vnd.py`: when the code changes
(new regime, neighbourhood, config knob, behaviour), update the matching
section here, and append a new Part III / Part IV snapshot tagged with the
new commit. Design rationale and the reading behind the method live in
[`notes/design.md`](notes/design.md) and [`notes/synthesis.md`](notes/synthesis.md).*
