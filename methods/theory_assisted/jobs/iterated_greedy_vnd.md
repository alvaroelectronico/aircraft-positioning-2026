# Iterated Greedy + VND heuristic for job-level aircraft positioning

This document has four parts. **Part I** explains the heuristic as a method,
the way a paper would, with no reference to the source code; **Part II**
reports the results and their analysis; **Part III** is the improvement
roadmap; **Part IV** explains how the method is realised in code.

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

## 4. Construction — a portfolio of seeds

Each multi-start restart builds its own seed from a different **construction
rule**, so the restarts differ by *construction* (not only by the
perturbation RNG):

- **NEH-style greedy insertion** under an ordering rule: aircraft are taken in
  the rule's order and each is inserted, in turn, at the position minimising
  the partial objective of the aircraft placed so far. The ordering rule is
  one of: `−Tᵣ` (NEH, makespan), `Lᵣ` (EDD, earliest due date), slack
  `Lᵣ−Eᵣ−Tᵣ`, critical ratio `Lᵣ/Tᵣ`, or a rank blend.
- **Regret-2 insertion**: a *dynamic* order — at each step insert the aircraft
  whose 2nd-best position is much worse than its best (largest regret), at its
  best position.

The due-date rules (EDD / slack / critical-ratio) and regret-2 are what steer
**tight-target aircraft into early slots**, the lever the delay-priority
profile needs; NEH remains the strong makespan seed.

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

The whole construct-and-improve procedure is run several times — each restart
with its own construction rule (§4) *and* its own perturbation RNG — and the
best result is kept. The restart count is **adaptive to instance size** (more
restarts on the cheap small instances, fewer on large ones that need their
per-start time). This matters because the search is *time-limited and hence
non-deterministic*: on some instances a single run occasionally settles in a
bad (high-delay) basin, and independent restarts make finding the good basin
reliable.

## 8. How the two regimes are combined

Each restart first searches in the **zero-movement regime** (a fast, always-
feasible floor) and then **polishes in the manoeuvre-aware regime**. The
polished, manoeuvre-spending schedule is adopted only if it is **certified
feasible by the independent compliance checker** *and* strictly better than
the zero-movement floor. Consequently the method can never return an
infeasible schedule and can never do worse than its zero-movement result,
regardless of any approximation inside the manoeuvre-aware decoder.

When the **movement-priority** profile meets a **blocking topology**, one
extra candidate is also built once and folded in by the same best-of /
checker rule: a **dense concentric-nesting schedule**. In a dense component
the zero-movement optimum packs aircraft into a few *concentric-nesting
waves* — a long aircraft wraps shorter ones, all overlapping in one wave's
span — but the earliest-feasible decode cannot produce that (it always
prefers placing *before* over *nested*). So this candidate is written with
**explicit start times**, not via the decode: sort aircraft by stay length,
group into waves of ≤ |P|, make the longest of each wave the outer container
on the deepest position, and *stretch* shorter aircraft with idle so the
stay lengths step down by ≥ 2·η (the nesting condition) even when their work
durations are equal. A tiny beam (two wave partitions) is tried and the best
kept. On the complete-blocking `full` topology this reaches — and beats — the
MILP's reported makespan-at-zero-movements; on other topologies it is simply
ignored by best-of.

## 9. The complete algorithm in pseudocode

Notation: a *state* is `(π, σ)` — an assignment `π : R → P` and a priority
order `σ` over the aircraft. `Eᵣ, Lᵣ, Tᵣ` are aircraft `r`'s earliest start,
target finish and total processing time; `ε, η, μ, δ` are the instance's tow
time, access margin, Mode-B gap unit and Mode-C extension. The cost of a
schedule is `F = Wᴹ·makespan + Wᴰ·Σ delay + Wˢ·movements`.

```
ALGORITHM  Solve(instance, time_limit, weights, base_seed):
    preprocess instance  (job chains, Tᵣ, blocking arcs, position depths)
    reset the decode cache                               # memoised per solve
    portfolio ← BuildPortfolio()                         # construction rules
    n_starts  ← 8 if R ≤ 10 else 4 if R ≤ 20 else 3      # adaptive: small = cheap
    best ← ∅ ;  best_F ← +∞
    for i in 0 … n_starts−1  while time remains:
        seed the RNG with base_seed + i
        deadline_i ← now + time_limit / n_starts
        (π₀, σ₀) ← portfolio[i mod |portfolio|]()        # this start's seed
        (sol, F) ← OneStart(π₀, σ₀, deadline_i)
        if F < best_F:  best, best_F ← sol, F
    return best
    # Each restart differs by construction rule AND RNG.  The time-limited
    # search is non-deterministic, so more *independent* restarts on the cheap
    # small instances reliably avoid the occasional bad (high-delay) basin.


PROCEDURE  BuildPortfolio():        # construction rules; each returns a seed (π, σ)
    return [
        NEH     :  GreedyConstruct( R sorted by −Tᵣ        )    # makespan
        EDD     :  GreedyConstruct( R sorted by Lᵣ         )    # earliest due date
        SLACK   :  GreedyConstruct( R sorted by Lᵣ−Eᵣ−Tᵣ   )
        regret2 :  Regret2Construct()
        CR      :  GreedyConstruct( R sorted by Lᵣ/Tᵣ      )    # critical ratio
        BLEND   :  GreedyConstruct( R sorted by rank-blend )
    ]
    # The due-date rules (EDD / SLACK / CR) and regret-2 steer tight-target
    # aircraft into early slots — the lever `wDLY` needs.


PROCEDURE  GreedyConstruct(σ):              # NEH-style greedy insertion
    π ← ∅ ;  placed ← []                     # prefix of σ already situated
    for r in σ:                              # in the rule's order
        placed ← placed + [r]
        for each position p ∈ P:
            π[r] ← p                          # tentative
            evaluate F of the partial decode of 'placed'   (cached)
        π[r] ← the position p with the lowest partial F
    return (π, σ)                             # σ is the start's priority order


PROCEDURE  Regret2Construct():      # dynamic insertion order, by regret
    π ← ∅ ;  order ← []
    while aircraft remain unplaced:
        for each unplaced r:
            (best, second) ← the two lowest F of inserting r at each position
            regret[r] ← second − best
        place the r with the largest regret at its best position; append to order
    return (π, order)
    # Prioritises low-slack / high-Wᴰ aircraft that have few good slots.


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

# Part II — Results and analysis (solver at Commits 1–4; run under `cb5656c`)

> Snapshot of the solver **after Commits 1–4** (decode cache + enforced time
> budget; construction portfolio + regret-2; adaptive multi-start; dense
> concentric-nesting builder). Battery run under commit `cb5656c`, seed-first;
> the code state is stamped in the log header. The Change log (Part III) maps
> every commit to its effect; this section is the current results.

## Experimental setup

- **Battery:** all 120 instances — 12 configurations (`chain / full / hub /
  none / triangle_loose / triangle_medium / triangle_tight / two_rows`, at
  `P5`, sizes `R5 / R10 / R20 / R30`) × 10 seeds, run **seed-first** (seed-1
  of every type, then seed-2, …) for an early cross-type read.
- **Methods:** job-level MILP baseline (`milp_baseline_job`) vs this heuristic.
- **Weight profiles:** `wMK = (100,1,1)`, `wDLY = (1,100,1)`, `wMOV = (1,1,100)`.
- **Budget:** 60 s, strictly enforced (R20/R30 are a fair 60-s comparison).
  **720 runs, 0 failures.**
- **Metric:** relative gap `g = (MILP_obj − heuristic_obj) / MILP_obj`
  (`g > 0` ⇒ heuristic better), **plus** per-component Δ (heuristic − MILP)
  for makespan / delay / movements (the undistorted read).
- **Log (this code state):**
  [`outputs/logs/instances_main_methods_20260613_235129.log`](../../../outputs/logs/instances_main_methods_20260613_235129.log)
  — self-stamped `Code state (git): cb5656c`.

## Relative objective gap (mean / min / max over 10 seeds)

```
[wMK  (100/1/1  makespan-priority)]            N     Mean      Min      Max
  scn_chain_tight_P5_R10                       10   -1.21%   -2.95%   -0.01%
  scn_full_tight_P5_R10                        10   +1.40%   -3.18%   +6.35%
  scn_full_tight_P5_R20                        10  +41.33%  +15.64%  +60.94%
  scn_hub_tight_P5_R10                         10   -2.47%   -4.82%   +0.01%
  scn_none_tight_P5_R10                        10   +0.00%   +0.00%   +0.00%
  scn_triangle_loose_P5_R10                    10   +0.07%   -1.76%   +1.66%
  scn_triangle_medium_P5_R10                   10   +0.35%   -0.50%   +1.91%
  scn_triangle_tight_P5_R10                    10   -0.43%   -3.07%   +1.67%
  scn_triangle_tight_P5_R20                    10  +17.18%  +10.68%  +22.20%
  scn_triangle_tight_P5_R30                    10  +35.73%  +24.45%  +40.16%
  scn_triangle_tight_P5_R5                     10   -0.01%   -0.03%   +0.00%
  scn_two_rows_tight_P5_R10                    10   -0.01%   -1.24%   +0.73%

[wDLY (1/100/1  delay-priority)]               N     Mean        Min       Max
  scn_chain_tight_P5_R10                       10   +7.02%     +0.42%   +15.30%
  scn_full_tight_P5_R10                        10  +24.09%    +14.19%   +37.12%
  scn_full_tight_P5_R20                        10  +56.13%    +41.28%   +67.54%
  scn_hub_tight_P5_R10                         10   +3.56%     -3.42%   +10.23%
  scn_none_tight_P5_R10                        10   -0.00%     -0.00%    +0.00%
  scn_triangle_loose_P5_R10                    10  -19.03%   -199.35%   +18.55%
  scn_triangle_medium_P5_R10                   10   +5.48%     +0.76%   +14.62%
  scn_triangle_tight_P5_R10                    10   +6.01%     +1.49%   +10.96%
  scn_triangle_tight_P5_R20                    10  +14.11%     +3.53%   +24.75%
  scn_triangle_tight_P5_R30                    10  +37.06%    +23.47%   +50.02%
  scn_triangle_tight_P5_R5                     10   -0.22%     -2.17%    +0.00%
  scn_two_rows_tight_P5_R10                    10   +1.37%     -0.50%    +4.78%

[wMOV (1/1/100  movement-priority)]            N     Mean       Min      Max
  scn_chain_tight_P5_R10                       10  -10.42%   -26.26%   +5.06%
  scn_full_tight_P5_R10                        10   -5.05%   -34.71%   +9.63%   <- dense-nest (was -17.1%)
  scn_full_tight_P5_R20                        10  +26.32%    +7.34%  +40.46%
  scn_hub_tight_P5_R10                         10   -4.01%   -25.73%   +5.00%
  scn_none_tight_P5_R10                        10   +0.00%    +0.00%   +0.00%
  scn_triangle_loose_P5_R10                    10   -0.02%    -9.70%   +6.12%
  scn_triangle_medium_P5_R10                   10   +1.86%    -2.19%   +8.33%
  scn_triangle_tight_P5_R10                    10   +0.56%    -5.83%   +5.76%
  scn_triangle_tight_P5_R20                    10  +11.98%    +3.62%  +19.09%
  scn_triangle_tight_P5_R30                    10  +35.37%   +21.04%  +42.31%
  scn_triangle_tight_P5_R5                     10   -3.88%   -20.51%   +0.00%
  scn_two_rows_tight_P5_R10                    10   +0.41%    -3.55%   +4.12%

[ALL profiles]                                 N     Mean        Min       Max
  scn_chain_tight_P5_R10                       30   -1.54%   -26.26%   +15.30%
  scn_full_tight_P5_R10                        30   +6.81%   -34.71%   +37.12%
  scn_full_tight_P5_R20                        30  +41.26%    +7.34%   +67.54%
  scn_hub_tight_P5_R10                         30   -0.98%   -25.73%   +10.23%
  scn_none_tight_P5_R10                        30   -0.00%    -0.00%    +0.00%
  scn_triangle_loose_P5_R10                    30   -6.32%  -199.35%   +18.55%
  scn_triangle_medium_P5_R10                   30   +2.56%    -2.19%   +14.62%
  scn_triangle_tight_P5_R10                    30   +2.04%    -5.83%   +10.96%
  scn_triangle_tight_P5_R20                    30   +14.43%   +3.53%   +24.75%
  scn_triangle_tight_P5_R30                    30   +36.05%  +21.04%   +50.02%
  scn_triangle_tight_P5_R5                     30   -1.37%   -20.51%    +0.00%
  scn_two_rows_tight_P5_R10                    30   +0.59%    -3.55%    +4.78%
```

## Per-component mean Δ (heuristic − MILP; negative = heuristic better)

```
[wMK]                          Δmakespan      Δdelay      Δmov
  chain_R10                       +0.80       -0.35       -0.60
  full_R10                        -1.15       -0.85       +3.20
  full_R20                      -123.95    -1072.85      +77.80
  hub_R10                         +1.70       -6.25       -2.60
  none_R10                        +0.00       +0.00       +0.00
  triangle_loose_R10              -0.05       +2.80       -1.40
  triangle_medium_R10             -0.15       -2.15       -3.20
  triangle_tight_R10              +0.35       -2.05       -2.60
  triangle_tight_R20             -26.35     -158.30       -8.60
  triangle_tight_R30            -121.80    -1531.60       +8.20
  triangle_tight_R5               +0.00       +0.20       +0.00
  two_rows_R10                    +0.05       -3.70       -0.60

[wDLY]                         Δmakespan      Δdelay      Δmov
  chain_R10                       -1.25       -8.65       -1.20
  full_R10                       -14.20      -48.90      +10.40
  full_R20                      -162.75    -1337.00      +41.20
  hub_R10                         -3.70       -4.40       -1.40
  none_R10                        +0.00       +0.00       +0.00
  triangle_loose_R10              +0.40       +0.00       +1.60
  triangle_medium_R10             -1.30       -3.25       -1.80
  triangle_tight_R10              -4.20       -6.65       -3.60
  triangle_tight_R20             -19.30     -117.40       -1.00
  triangle_tight_R30            -120.25    -1271.80       +5.40
  triangle_tight_R5               +0.10       +0.00       +0.00
  two_rows_R10                    -2.20       -1.40       -0.40

[wMOV]                         Δmakespan      Δdelay      Δmov
  chain_R10                      +13.15      +10.70       +0.00
  full_R10                        +8.70       +2.60       +0.00   <- was +23.95 (dense-nest)
  full_R20                      -49.90     -394.80       +0.00
  hub_R10                         +4.30       +3.05       +0.00
  none_R10                        +0.00       +0.00       +0.00
  triangle_loose_R10              +0.10       -0.15       +0.00
  triangle_medium_R10             +0.00       -2.45       +0.00
  triangle_tight_R10              -0.10       -0.95       +0.00
  triangle_tight_R20             -17.70      -97.75       +0.00
  triangle_tight_R30            -126.35    -1163.60       +0.00
  triangle_tight_R5               +0.00       +1.40       +0.00
  two_rows_R10                    +0.10       -0.80       +0.00
```

## Performance summary

- **`wMK` (makespan):** competitive on R5–R10 — within ~±2.5 % of the MILP on
  every topology (exact on `none` / `R5`). On R20/R30 the heuristic far
  outperforms the MILP (+17 % / +36 %), a **fair 60-s comparison** (the MILP
  is unconverged there).
- **`wDLY` (delay): solid.** `R5 wDLY` ≈ optimum (−0.22 %); competitive or
  winning on every type. The only outlier is `triangle_loose_R10` (−19 % mean,
  −199 % on the single hardest seed) where the MILP spends manoeuvres to reach
  delay 0; the per-component `Δdelay` is ≈0 there, confirming the relative gap
  is small-denominator inflation, not a large absolute loss.
- **`wMOV` (movements): the dense-nest (Commit 4) closed most of the gap on
  the complete-blocking `full` topology** — `full_R10` −17.1 % → **−5.05 %**
  (`Δmakespan` +24 → **+8.7** at 0 manoeuvres), and `full_R20` improved too.
  `chain`/`hub` are *not* complete blocking graphs, so the nest does not
  trigger there and they are unchanged (`chain` −10 %, `hub` −4 %): those are
  the remaining dense-`wMOV` residual, for a generalised (non-complete)
  nesting decode or the local micro-MILP (Part III, options).

## Caveats

1. **Small-denominator inflation.** When the optimum delay ≈ 0 (`wDLY` on
   loose/easy instances), the relative gap explodes for a tiny absolute
   difference (the −199 % outlier; its `Δdelay` ≈ 0). Read the per-component Δ.
2. **MILP unconverged at scale.** R20/R30 MILP objectives are 60-s incumbents
   (80–99 % optimality gap), so the heuristic "winning" there means "better
   feasible solution fast", not proven optimality.


---

# Part III — Improvement roadmap

**Diagnosis.** The base architecture is well chosen: separating the
combinatorial state `(π, σ)` from a deterministic decoder shrinks the search
space and lets the decoder price each assignment/order with timing, blocking
and manoeuvres — aligned with NEH (a strong makespan constructor), Iterated
Greedy (destruction/reconstruction) and VND/VNS (systematic neighbourhood
change). The bottleneck now is **not "more metaheuristic"** but **missing
operators that attack the specific per-weight failures** of Part II:

- `wMK`: already near the MILP on R10 — Mode-B/nesting do their job.
- `wDLY`: the search does not propose enough states with tight-target
  aircraft scheduled early, nor the "spend a manoeuvre to remove a delay"
  trade.
- `wMOV`: with both methods at 0 manoeuvres, the winner is whoever packs a
  zero-movement schedule tightest — and the decoder is too greedy on dense
  topologies.
- R20/R30: not interpretable until the budget is strictly enforced.

The items are ordered by impact/risk; each names the failure it targets.
Cumulative ablations: `A0 = 68dc201 → A1 budget+cache+logging → A2 seeds →
A3 regret → A4 delay-manoeuvre → A5 zero-move repack → A6 ALNS`.

## Priority 0 — anytime correctness (foundation)

1. **Enforce the time budget. — DONE** (commit after `68dc201`). `_time_up()`
   is now polled inside construction, the VND loop, every neighbourhood scan
   and the IG reinsertion, with cheap feasible fallbacks where a complete
   solution is required. R30 and `full_R20` now return in ~60 s (was 413 s /
   88 s), R10 unchanged. **Consequence: the Part II R20/R30 rows are stale**
   (measured pre-fix) and need a re-run to be a valid 60 s comparison.
2. **Always-valid incumbent.** Each phase must be abortable and return the
   best *checker-certified* schedule so far; if `DecodeManoeuvre` runs out of
   time it returns `+∞` / the last validated complete schedule, never a
   partial one. Record `timed_out` and `phase_returned ∈ {zero, manoeuvre,
   fallback}`.
3. **Decode cache.** VND re-evaluates near-identical states after undone
   swaps, walk restarts and close reconstructions. Add an LRU cache keyed by
   `(decoder_id, positions-by-fixed-aircraft-id, priority-order, weights_id)`.
4. **Per-component logging** (see Metrics) so we can tell whether a change
   actually helps. *Acceptance for P0:* 0 overruns > 1 % of the limit; every
   run carries `timed_out`; R20/R30 reported separately for strict-60 s vs
   no-hard-limit.

## Priority 1 — due-date-aware construction (targets `wDLY`) — DONE

Implemented in Commit 2 (`_build_portfolio` + `_regret2_construct`): each
multi-start restart builds its seed from a different rule (NEH / EDD / SLACK
/ regret-2 / CR / BLEND). `PlaceFront` already prices `Wᴰ·delay`; the gap was
that the search rarely *proposed* states with tight-target aircraft early.
The due-date seeds fix that — `R5 wDLY` seed10 went 139 → 35 (= MILP
optimum), `triangle_loose_R10 wDLY` ~570 → 323, with no `wMK` regression.

```
σ_NEH   = sort by −Tᵣ          σ_EDD   = sort by Lᵣ
σ_SLACK = sort by Lᵣ−Eᵣ−Tᵣ     σ_CR    = sort by (Lᵣ−now)/Tᵣ
σ_BLEND = α·rank(−Tᵣ) + β·rank(Lᵣ) + γ·rank(slack)
σ_RAND_EDD = EDD with controlled noise
```

EDD/ATC are the classical due-date / weighted-tardiness constructive rules;
here they are *seeds* (positions, blocking, job chains and manoeuvres still
matter), not the answer. Replace "insert the next fixed aircraft" with
**regret-2 insertion** (commit the aircraft whose 2nd-best insertion is much
worse than its best) — this helps exactly the low-slack / high-`Wᴰ` aircraft.

## Priority 2 — "buy punctuality with manoeuvres" (targets `wDLY`)

`triangle_loose_R10` seed10 is the canonical miss: the MILP spends 8
manoeuvres for delay 0; the heuristic keeps 0 manoeuvres and eats delay 5
(×100). Add a neighbourhood, tried first when `Wᴰ` dominates:

```
N_delay_manoeuvre: for a top-delayed r, try target starts {Eᵣ, Lᵣ−Tᵣ, …};
  move r earlier in σ / reassign r or its blocker / force a Mode-B gap or a
  Mode-C on the blocker; DecodeManoeuvre; accept iff checker-valid & better.
```

Gate it with a benefit/cost bound *before* calling the checker (delay +
makespan saving vs manoeuvre + front-time cost) so it fires under `wDLY` but
not `wMOV`. Also add due-date-critical `PlaceFront` candidates `s = Lᵣ−Tᵣ`,
`Lᵣ−Tᵣ−δ·q`, `Lᵣ−Tᵣ−μ·q`: the objective's slope changes at `Lᵣ`.

## Priority 3 — dense zero-movement repacking (targets `wMOV`) — DONE

**Resolution (Commit 4, `_dense_nest_solution`).** The fix that worked is a
dedicated **dense concentric-nesting builder** that writes **explicit start
times** (not via the earliest-feasible decode) and — crucially — **stretches**
shorter aircraft with inter-job idle so their *stay lengths* step down by
≥ 2·η even when work durations tie (the MILP does the same: it stretched
`R10` to a 34-long stay though its work is 30). It groups aircraft into waves
of ≤ |P| (longest = outer container on the deepest position), tries two wave
partitions (chunk + round-robin, a tiny beam), and is folded in by best-of +
checker, gated to `Wˢ`-dominant with a blocking topology. Result on
`full_R10` seed1 `wMOV`: **352.5 → 258** (ms 114.5 → 71), **beating the MILP's
261**; also adopted on `full_R20`. Safely ignored where it does not help (no
regression). The two earlier failed attempts are kept below as the rationale
for why this specific design (explicit starts + stretching) was needed.

When `Wˢ` dominates the problem becomes "best schedule with `n = 0`", and
`DecodeZeroMov` packs loosely on `full`/`hub`/`chain`.

**Autopsy (`full_R10` seed1, both 0 mov).** `full` is a *complete* blocking
graph, so all aircraft mutually conflict. The MILP (ms 71.5) packs them into
**two concentric-nesting waves of 5**: durations staggered (34/32/30/28/26
and 31/29/27/23/17) so each wave's span ≈ its longest member, two waves
serialised. The heuristic (ms 114.5) fills 3 into wave 1, 5 into wave 2, then
**serialises the 2-aircraft tail** → +52 makespan.

**Two attempts, both failed (reverted):**
1. *Left-shift compaction* (re-place each aircraft, latest-first, at its
   earliest feasible start vs all others). Could not restructure the nesting
   (left-shifting one aircraft can't open a nested slot that requires moving
   several), so `full_R10` stayed 114.5 — and the 4 extra O(R²) passes per
   decode **slowed the search enough to regress `wMK` 5961 → 6082**.
2. *Concentric-nesting construction seed* (group by duration into nesting
   waves; safe portfolio seed, best-kept). Still ms ~116 — the seed had the
   right structure but the decode did not preserve it.

**Root cause (fundamental).** The zero-movement decode is *earliest-feasible*,
which always prefers placing an aircraft **before** (earliest) rather than
**nested** (later, inside a container) — so it serialises. Concentric nesting
needs the decode to *choose* a later nested start; neither a post-pass nor a
seed can impose that on an earliest-feasible decode.

**Proper fix (a larger, separate effort).** A *dedicated nesting decode* for
dense components: pick the before/after/enclose disjunction per pair (a
difference-constraint system, longest-path/Bellman-Ford; cycle ⇒ infeasible)
and explore disjunctions with a small beam. The risk is the per-decode cost
(it must not slow the whole search — cf. attempt 1); likely run it only as a
*specialised seed/decode* when `Wˢ / max(Wᴹ,Wᴰ)` is high and density is high,
kept under the best-of safety net. **Deferred** rather than shipped as a
fragile incremental change.

## Priority 4 — weight-profile-dependent VND

Replace the fixed `[Reassign, SwapPositions, Reorder]` with a profile-aware
ordering — semantic operators first, generic ones last: delay operators
(PromoteDelayed, SwapDelayedWithBlocker, ReinsertDelayedAtBestSlot) when `Wᴰ`
dominates; zero-move repack / nesting-flip when `Wˢ` dominates;
critical-path-reassign / Mode-B-compression when `Wᴹ` dominates.

## Priority 5 — ALNS-lite destroy/repair

Costs here are *relational* (an aircraft is bad via its blocker / slot / due
date), so single-contribution destruction is limited. Move IG to a small
ALNS: destroy ∈ {delay, blocker+its fronts, dense-component, costly-movement,
random}; repair ∈ {NEH, EDD/slack, regret-2, manoeuvre-aware, zero-move}.
Adopt only after the operators above exist (premature otherwise).

## Priority 6 — heuristic risk repair for unseen instances (replaces micro-MILP)

**The micro-MILP/CP idea is dropped as a core step.** It could repair known
*benchmark* outliers, but it relies on an external notion of failure: on a new
instance we do not know whether the incumbent is an outlier (there is no MILP
to compare against), so an "is-outlier → run micro-MILP" trigger is not
operational outside the lab. It would also turn the method into a hybrid
matheuristic, diluting the contribution (good quality from *specialised
decoding + structured multi-start + heuristic repairs, no internal exact
solver*). It may still serve as a separate offline baseline, but not here.

Instead the next stage replaces *"detect outlier (external)"* by
**self-diagnosed internal risk → specialised heuristic candidate → checker →
best-of**. The solver measures symptoms it can see without an optimum —
`delay_risk` (positive delay under `Wᴰ`, tight-slack delayed aircraft, active
blockers in front of them), `nesting_risk` (movements 0 but a serialised tail
/ high block density / few waves), `search_risk` (high objective spread across
starts, stale count) — and fires a matching repair only when its trigger is
present. Every repair is a **separate candidate generator** (like the
dense-nest, *not* a VND neighbourhood — cf. the Commit-3 lesson) folded in by
best-of + checker, so it can only help. The repairs:

- **DelayRiskRepair** (`Wᴰ`-dominant, positive delay): `PromoteDelayed`,
  `ReinsertDelayedAtBestSlot`, `SwapDelayedWithBlocker`, `BuyPunctuality`
  (try starts near `Eᵣ`, `Lᵣ−Tᵣ`, `Lᵣ−Tᵣ−δ`, …; force a Mode-B/Mode-C on the
  blocker), gated by a benefit/cost bound before the checker call.
- **ComponentNestingRepair** (`Wˢ`-dominant, 0 mov, dense/serialised):
  generalise the dense-nest to non-complete blocking graphs —
  `ChainWaveRepair`, `HubWaveRepair`, `DenseSubcliqueRepair`,
  `TailAbsorptionRepair` (absorb a serialised tail into an earlier wave).
- **Feature-triggered ALNS** (high search-risk): destroy/repair chosen by the
  active risk, run a few times, never inside a decode.

**Safety principle (unchanged):** all candidates pass the checker; one is
adopted only if it strictly improves the incumbent; the zero-movement floor is
never lost. This is portable — it uses internal features, not an
externally-derived outlier label.

## Metrics & ablations

Log per run: `obj_milp/heur`, `abs_gap`, `rel_gap`, per-component
`Δmakespan / Δdelay / Δmov`, `wall_time`, `timed_out`, `phase_returned`,
`checker_ok`, `n_decodes`, `cache_hit_rate`. Judge by **per-profile success,
not just mean gap**: for `wDLY`, #instances with `delay_heur > delay_milp`
and mean `Δdelay` (and the `optimum-delay = 0` cases); for `wMOV`, gap
*conditioned on `mov = 0`*; for scaling, quality at strict-60 s vs unlimited,
reported separately. The relative gap alone is distorted by small
denominators (see Part II caveats), hence the absolute/per-component fields.

## Recommended implementation order

1. **Commit 1 — DONE** — time budget + always-valid incumbent + decode cache
   + per-component logging.
2. **Commit 2 — DONE** — seed portfolio (EDD/slack/CR/blend) + regret-2.
3. **Commit 3 — DONE, pivoted** — the planned delay-specific neighbourhoods
   were implemented and **dropped** (basin-dependent, unstable). What the data
   actually pointed to was **variance reduction**: the time-limited search is
   non-deterministic and occasionally lands in a bad basin, so an *adaptive
   multi-start count* (more restarts on the cheap small instances) reliably
   finds the good basin — this is what shipped, and it fixed the catastrophic
   `triangle_loose wDLY` seeds (886 → ≈MILP).
4. **Commit 4 — DONE** — dense `wMOV` nesting. Two incremental attempts
   failed (left-shift compaction regressed `wMK` via per-decode slowdown; a
   construction seed wasn't preserved by the earliest-feasible decode). What
   shipped is `_dense_nest_solution`: an **explicit-start** concentric-nesting
   builder with aircraft **stretching** (so stay lengths step down by ≥ 2·η
   even with equal work), a two-partition beam, gated to `Wˢ`-dominant +
   blocking, under best-of + checker. `full_R10 wMOV` 352.5 → **258** (beats
   MILP 261).
5. **Commit 5 — risk diagnostics** (observability, no behaviour change):
   record `delay_risk / nesting_risk / search_risk` per solution so the next
   steps fire on *internal symptoms*, not on an external outlier label. Read
   them on the ablation subset to size the real headroom before building.
6. **Commit 6 — DelayRiskRepair — ATTEMPTED & DROPPED.** Built as designed (a
   best-of'd delay-biased re-search) and measured on the ablation subset: it
   **never improved the incumbent (0/74 runs)** and left the one clean target
   (`triangle_loose_R10` seed10 wDLY) at delay 1.5. The decisive evidence was
   the `search_risk` diagnostic: that seed has an objective **spread of 1.73**
   across the 8 starts (best 230.5, worst 628.5), and the run-to-run search
   noise (≈19 delay units on `chain_R10` wMK, where the repair is gated out
   and cannot act) is **larger than any effect the repair could have**. The
   residual is *search-variance-bound, not order-bound* — the multi-start
   portfolio already reaches an equally good delay-biased basin, so seeding it
   there explicitly adds nothing. Reverted (Commit 3 lesson, again).
7. **Commit 7 — variance reduction on high-`search_risk` instances** (this is
   what the diagnostics actually point to, and what worked last time — the
   adaptive-multi-start of the original Commit 3). The lever is *reducing the
   spread*, not adding a delay operator: e.g. more independent restarts (or an
   elite/restart-from-best ILS) on instances the `search_risk` spread flags as
   luck-dependent. Expected payoff is small (the residuals are ≤ 3 delay units
   on a couple of R10 seeds) and the risk is real (a slower loop cuts restarts
   — exactly how Commit 3's first cut regressed), so **measure on the subset
   before keeping**, and weigh against simply documenting the current strong
   state.
8. **Commit 8 — ComponentNestingRepair** for `chain`/`hub` remains *only* a
   candidate, and a weak one: the `chain_R10 wMOV` residual is large in
   absolute terms (Δms +13.5, Δdelay +9.0) **but the diagnostic shows it is
   already nested** (`serial_points = 1/10`, not serialised), and the MILP
   target there is *unconverged* (45–85 % gap) so there is no reliable target
   to chase. Judge only by absolute makespan/delay reduction at `Δmov = 0`,
   and do not expect much.

**Where this leaves us.** The ablation subset shows the heuristic is at or
beyond the MILP on almost every R10 type (± 2 % or better), wins clearly at
scale (R20/R30, where the MILP times out), and the only genuine residuals are
noise-level (≤ 3 delay units on a few R10 seeds) or against an unconverged
MILP. The method is near its practical ceiling on small/medium instances;
further operators chase noise. The honest next step is to **document the
current state with a full battery** and treat variance reduction as a separate,
carefully-measured experiment rather than an assumed win.

We do **not** proceed with the local micro-MILP/CP as a core step (Priority 6):
it relies on an external notion of failure that does not exist on a new
instance. The route is heuristic-only — self-diagnosed risk → specialised
candidate → checker → best-of — keeping the method's identity (IG+VND with
specialised decoders and repairs, no internal exact solver).

Lesson carried forward: a *targeted operator* is not automatically helpful —
build it as an **external best-of'd candidate** (like the dense-nest), never
as an in-VND neighbourhood (Commit-3 changed the basin and slowed the loop),
and **measure on the ablation subset before keeping it**. Commit 6 reconfirmed
this and added a sharper rule: **measure the noise floor first.** The
time-limited search is non-deterministic, so two runs of the *same* code
differ; on this subset that run-to-run swing reached ≈19 delay units. Any
operator whose effect is smaller than that swing cannot be shown to help and
should not be kept. Commit 5's `search_risk` diagnostic exists precisely to
make that floor visible (its `obj_spread` is the per-instance noise estimate).

---

# Part IV — How it is implemented

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
| `n_starts` | adaptive: 8 / 4 / 3 for R≤10 / ≤20 / else | multi-start restarts (§I.7); overridable |
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
| Cached decode (memoised eval) | `_eval` (keyed by decoder tag, order, positions-along-order; reset per solve) |
| Dense concentric-nesting builder (§8; explicit starts, best-of) | `_dense_nest_solution` (called once in `solve` when `Wˢ`-dominant + arcs) |
| Risk diagnostics (Commit 5; observability) | `_diagnostics(best_sol, start_objs)` → `delay_risk` / `nesting_risk` / `search_risk`, attached to the solution + one log line |
| Construction portfolio (§4) | `_build_portfolio`; `_greedy_construct(order)`; `_regret2_construct` |
| VND neighbourhoods (§5) | `_vnd`, `_n_reassign`, `_n_swap_pos`, `_n_reorder` |
| IG perturbation (§6) | `_perturb` |
| Search driver (decoder-agnostic via `self._decode_fn`) | `_search` |
| Two-regime combination per restart (§8) | `_one_start(a0, o0, …)` (phase 1 = `_decode`, phase 2 = `_decode_v3`) |
| Multi-start, adaptive count (§7) | loop in `solve` over `_build_portfolio()` |
| Time budget enforced in every loop | `_time_up` (`self._deadline`) |
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

# Change log

Track the heuristic's evolution here so each Part II snapshot stays tied to
the code that produced it. Behaviour-affecting commits (newest last):

| commit | change | effect on results |
| --- | --- | --- |
| `d00af90` | Mode-B manoeuvre-aware decoder (`DecodeManoeuvre`, §3.2) | reaches/beats MILP on tight-blocking `wMK`/`wDLY` |
| `68dc201` | gap-summary logging prepended to the run log | **Part II battery ran at this commit** |
| `1f36bd7` | enforce the wall-clock budget inside every search loop (P0 #1) | R30/`full_R20` 413 s/88 s → ~60 s; R20/R30 Part II rows now stale |
| `f4e10f0` | Commit 1 (P0): decode cache (`_eval`, 90–100 % hit), always-valid incumbent with `phase`/`timed_out` fields, per-component (Δmakespan/Δdelay/Δmov) gap logging, and `experiments/ablation_subset.py` (heuristic-only subset reusing the cached MILP) | same objectives, far more search per second; faster ablation loop |
| `ab33af4` | Commit 2 (P1): construction portfolio per multi-start (`_build_portfolio`: NEH / EDD / SLACK / regret-2 / CR / BLEND) + regret-2 insertion (`_regret2_construct`), targeting `wDLY` | due-date seeds steer tight-target aircraft early; `R5 wDLY` seed10 139 → **35 = MILP optimum**, `triangle_loose_R10 wDLY` ~570 → 323; no `wMK` regression |
| `dd12d3e` | Commit 3 (variance reduction): adaptive multi-start count (`n_starts` default 8 / 4 / 3 for R≤10 / ≤20 / else). **The planned delay-specific neighbourhoods were tried and dropped** — basin-dependent and unstable. | search is non-deterministic; more independent restarts make the good basin reliable. `triangle_loose_R10 wDLY` seed7 886 → **67.5 ≈ MILP 64.5**, seed5 487 → 78.5; `wMK` 5961 and R20/R30 unaffected |
| `0620092` | doc sync — Parts I/II + module docstring updated to the current two-decoder / portfolio / adaptive-multi-start / cache state | no behaviour change |
| (no commit) | **Commit 4 attempted & deferred** — dense `wMOV` repacker. Both a left-shift compaction (regressed `wMK` via per-decode slowdown) and a concentric-nesting construction seed (decode didn't preserve nesting) failed; the earliest-feasible decode fundamentally cannot nest. See Part III Priority 3 — needs a dedicated nesting decode (larger effort). Code reverted to `0620092`. | no change shipped |
| `21ad222` | experiment runner only (not the solver): run **seed-first** (early cross-type read) and **stamp the git commit in every log header** so each `.log` self-identifies its code state. | enabled the definitive full-battery snapshot in Part II above (log `…122208`); solver unchanged (still Commits 1–3) |
| `cb5656c` | **Commit 4 (dense nesting) — shipped.** `_dense_nest_solution`: explicit-start concentric-nesting schedule with aircraft *stretching*, two-partition beam, best-of + checker, gated to `Wˢ`-dominant + blocking topology (Part III Priority 3). | `full_R10 wMOV` 352.5 → **258** (beats MILP 261); also helps `full_R20`; ignored elsewhere (no regression). Part II refreshed to this state (battery log `…235129`): `full_R10 wMOV` mean −17.1 % → **−5.05 %**. |
| `dd20bf6` | **Commit 5 (risk diagnostics) — shipped.** `_diagnostics(best_sol, start_objs)` attaches `delay_risk` / `nesting_risk` / `search_risk` to the solution + a one-line log summary (Part III Priority 6, risk-triggered route). | no behaviour change (same search, same objectives); enables Commits 6–7 to fire on internal symptoms. First read: `chain_R10 wMOV` reports `min_slack_delayed=2.0` (removable lateness even at `mov=0`) and `serial_points=1/10` (already nested). |
| `95669a2` → reverted | **Commit 6 (DelayRiskRepair) — attempted & DROPPED.** A best-of'd re-search from a delay-biased seed (delayed aircraft pulled to the front in EDD order) on leftover budget. | **Measured on the ablation subset (baseline `…103224`, repaired `…delayrepair`): never improved the incumbent (0/74 runs accepted).** The one clean target `triangle_loose_R10` seed10 wDLY stayed at delay 1.5; the run-to-run search noise (≈19 delay units on `chain_R10` wMK, where the repair is gated out and *cannot* act) dwarfed any apparent wMOV/wDLY gain (0.5–0.75 units, within noise). The `search_risk` diagnostic (spread 1.73 on that seed) had already flagged the residual as **search-variance-bound, not order-bound** — the multi-start portfolio already reaches an equally good delay-biased basin. Reverted; only a `NOTE` comment + this row remain. Lesson = Commit 3 again: measure before keeping. |

**Evaluation shortcut.** The MILP baseline is fixed, so re-running it is
wasteful. To judge a heuristic change, run `ablation_subset.py` (heuristic
only on a stratified subset) and pair against the MILP rows already in
`outputs/solutions/results.csv`; only refresh the full Part II battery once
a milestone (a group of Part III items) lands.

---

*Keep this file in sync with `iterated_greedy_vnd.py`: when the code changes
(new regime, neighbourhood, config knob, behaviour), update the matching
section here, and append a new Part II (results) / Part III (roadmap) snapshot tagged with the
new commit. Design rationale and the reading behind the method live in
[`notes/design.md`](notes/design.md) and [`notes/synthesis.md`](notes/synthesis.md).*
