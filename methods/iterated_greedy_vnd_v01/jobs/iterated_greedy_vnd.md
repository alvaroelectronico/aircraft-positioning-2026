# Iterated Greedy + VND heuristic for job-level aircraft positioning (ChatGPT)

This document has four parts. **Part I** explains the heuristic as a method,
the way a paper would, with no reference to the source code; **Part II**
reports the results and their analysis; **Part III** is the improvement
roadmap; **Part IV** explains how the method is realised in code.

> **Status (code `c5f8f99`, latest battery
> [`outputs/logs/202605_02_main_methods_20260905_203305.log`](../../../outputs/logs/202605_02_main_methods_20260905_203305.log)).**
> Attempts 7, 9, 10, 11, 12 and now **14 (ils-at-scale)** are KEPT and merged
> to `main` (Attempt 13, a rear-side stretch-alignment probe, was **not**
> opened — net ~0 in 4 probes). Attempt 14 replaces the B-VND's three
> exhaustive exchange sweeps and its reset-to-N1 rule with an **exact-
> filtered local search** (candidates = the pusher tree under `_decode`
> v2 / all aircraft under `_decode_v3`; moves = reassign, relocate to one
> representative slot per distinct-decode class, swap only with
> conflicting positions — derived exact under N1/N2, a small residual leak
> under N3 at R20 only), and gives `R > 10` **two long ILS trajectories**
> (one per Mode-A band) instead of the old 3–4 lottery restarts, retiring
> the dead re-centre rule. Diagnosis: at R≥20 the search barely acted
> (R30 did 3 restarts; the final best came from restart ≥4 in 0 runs) and
> one VND confirm pass cost 420–900 evals — the cheaper exact-filtered
> descent lets far more kicks accumulate in the same 60 s. Same
> "no-Triangle" grid as the Attempt-12 battery of record — `chain` / `hub`
> / `two_rows` / `none`, R5–R30, loose / medium / tight (37 configs × 3
> profiles × 10 seeds = 1110 runs, 0 failures) — paired against the cached
> MILP; a separate fresh two-arm code-vs-code verdict (candidate vs the
> reused Attempt-12 candidate log as baseline) confirms **NET −403,270.5**,
> 23 consistent wins vs 5 small consistent losses (hub R20 `wMK`/`wMOV`,
> `two_rows_loose_R30` `wMOV`, +0.4–1.3 %; the "zero consistent
> regressions" house rule is not strictly met — kept anyway, user decision
> 2026-09-06, `IMPROVEMENT_LOG.md` Attempt 14). This battery still does
> **not** cover the `triangle` / `full` topologies — see Part II Caveats.

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

- **Mode A** — the front position is **vacant at that instant**: the access
  instant lies at or before the front aircraft's start, or at or after its
  finish (closed bounds — touching the stay endpoints `[s_r, f_r]` is
  vacant; no `η` margin is required by the problem). No manoeuvre, no cost.
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
that leaves exactly three admissible placements of the rear aircraft's stay
(with `bandA` the solver's Mode-A clearance margin, see below):

1. entirely **before** the front (rear exit `≤` front start `− bandA`),
2. entirely **after** the front (rear entry `≥` front finish `+ bandA`), or
3. **enclosing** the front (rear enters `≥ bandA` before the front starts
   and leaves `≥ bandA` after it finishes).

Since Attempt 11 (`igvnd-v01-mode-a-band`) the margin `bandA` is a
**variable, not the constant `η`**: the problem's Mode A needs no margin
at all (closed bounds), so the restart loop alternates the geometry —
`bandA = 0` on even restarts (the exact problem semantics, touching
allowed) and `bandA = η` on odd restarts (the conservative geometry,
which empirically anchors a different, sometimes better search basin).
Each restart's schedules are checker-validated either way, so both
geometries are safe; they simply explore different regions.

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

## 4. Construction — two deterministic seeds plus one diversifier

Every restart seeds from an **insertion order**; aircraft are taken in that
order and each is inserted, in turn, at the position minimising the partial
objective of the aircraft placed so far (NEH-style greedy insertion).

- The **first two restarts** use the two deterministic orders that cover the
  objective's two combinatorial levers: `−Tᵣ` (**NEH**, the classic makespan
  rule — bulkiest aircraft placed while the schedule is empty) and slack
  `Lᵣ−Eᵣ−Tᵣ` (**SLACK**, least due-date headroom first — steers tight-target
  aircraft into early slots, the delay lever).
- **Every later restart** applies a single diversification mechanism: a
  **rank-biased geometric shuffle** of whichever deterministic order scored
  better — the next aircraft is drawn from the *remaining* base order with
  `P(rank k) ∝ (1−β)^k` (β = 0.3), so each restart explores a distinct but
  still rule-shaped insertion order. Restarts are unlimited (§7), so the
  search sees hundreds of such orders on small instances.

This slim portfolio (Attempt 7) replaced the earlier six-rule portfolio
(NEH / EDD / SLACK / regret-2 / CR / BLEND): the retired due-date variants
were near-duplicates of SLACK, regret-2 was the costliest constructor, and
one biased sampler dominates them all once restarts are unlimited.

## 5. Local search — exact-filtered first-improvement descent

The construction is refined by a **first-improvement local search restricted
to an exact candidate filter** (Attempt 14; it replaces an earlier
three-neighbourhood sequential VND with a "basic" reset rule, which paid for
an exhaustive exchange sweep on every pass without changing which local
optima it could reach).

- **Candidate filter.** Under the **zero-movement decoder** only the
  aircraft that can actually change the objective are examined: the
  makespan aircraft, every delayed aircraft, and — transitively — every
  aircraft whose forbidden band pushed one of those aircraft's start later
  (the **pusher tree**, already recorded by the decode). An aircraft outside
  this tree bounds nobody in it and carries no delay, so moving it cannot
  improve the objective — this is exact, confirmed by a brute-force check
  that finds 0 improving moves of the old reassign/swap-position
  neighbourhoods outside the tree in 18/18 test cases. Under the
  **manoeuvre-aware decoder** no such filter exists (a move can ripple
  through the deepest-rear-first pass), so every aircraft is a candidate.
- **Moves, per candidate aircraft `r`.** Reassign `r` to a different
  position; relocate `r` in the priority order, trying only **one
  representative slot per distinct-decode class** (a class is delimited by
  the aircraft `r` shares a position with, or — under the zero-movement
  decoder only — is in blocking conflict with; two slots inside the same
  class decode byte-identically, so testing one is exact — this pruning
  also drives Iterated-Greedy reinsertion, §6); swap positions with another
  aircraft.
- **Scan order.** Each pass visits the current candidate set in random
  order and applies the **first improving move found** (reassign, then
  relocate, then swap, for that candidate); the candidate set is then
  recomputed — since an accepted move can change the pusher tree — and the
  next pass begins. The descent stops at a state with no improving move
  left in any of the three moves for any current candidate, or when the
  time budget runs out.

There is no explicit "neighbourhood level" or reset rule to speak of: the
candidate filter already narrows what is checked on every pass, so nothing
needs resetting. The one place the filter is not exact is the relocate move
under the zero-movement decoder — the old *swap two order slots* move (not
present in the current move set) could improve two aircraft at once and
leaked past the tree filter in 3 of 18 brute-force test cases, always at
`R = 20`; this residual is accepted rather than restoring the extra move,
since the net effect across the arms measured to keep this design was
strongly positive (Part II).

## 6. Iterated Greedy outer loop

Around the local search (§5) runs an Iterated-Greedy perturbation loop:

- **Destruction** — half the time, remove the `k` aircraft that contribute
  most to the objective (delay-weighted, with light randomisation); the
  other half, remove `k` aircraft **uniformly at random** (Attempt 10). The
  targeted rule degenerates under the makespan- and movement-priority
  weights (all delays ≈ 0 ⇒ almost always the same longest `k`), anchoring
  the walk in its basin; the random half restores walk diversity.
- **Reconstruction** — greedily reinsert each removed aircraft at its best
  position and, within it, at the best of **one representative order-slot
  per distinct-decode class** (the same exact pruning as §5's relocate
  move, not a blind scan of every slot).
- **Local search** — re-apply §5's exact-filtered descent.
- **Acceptance** — keep the new local optimum if it does not worsen the
  current walk; track the global best separately. There is no periodic
  "restart the walk from the global best" rule: under this
  better-or-equal acceptance the walk's current state can never fall below
  the best plateau it has reached (`cur`'s objective always equals the best
  seen so far), so a re-centring rule would never have anything to do —
  Attempt 14 retires it as dead code once this was noticed.

## 7. Multi-start — restarts until the deadline

The whole construct-and-improve procedure is repeated — each restart with its
own seed order (§4) *and* its own RNG — **until the time budget runs out**,
and the best result is kept. There is no fixed restart count: each restart
terminates on its own stale counter (§6). A per-start time *slice* caps any
single restart so one slow start cannot eat the whole budget: **budget/8 for
`R ≤ 10`**, so cheap small instances still do hundreds of independent
restarts; **budget/2 for `R > 10`** (Attempt 14a), so a large instance gets
exactly **two long trajectories** rather than several short ones.

Those two trajectories are not a diversification device by themselves — they
fall out of §3.1's existing per-restart Mode-A band alternation (even
restarts search band 0, odd restarts band `η`): once the slice is halved,
`R > 10` simply runs one long trajectory of each band instead of 3–4 short
lottery restarts. This replaced the lottery regime because at `R ≥ 20` the
old finer split left each restart too short to *ever* finish a first
descent, and the eventual best essentially never came from a restart beyond
the first few — the diversity that a fine restart split is meant to buy was
never being cashed in; letting the cheaper local search (§5) run long
instead does.

This matters twice over. The search is time-limited and non-deterministic, so
independent restarts make finding the good basin reliable on small instances
(the original motivation, Attempt 7); and on large instances the descent
itself must simply be cheap enough, and run long enough, to make progress —
which is what §5's exact-filtered local search and this two-trajectory split
jointly buy (Attempt 14, Part III).

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
checker rule: a **concentric nest-stretch schedule** over the *actual
blocking DAG* (Attempt 9; originally a complete-graph-only wave builder,
Commit 4). The zero-movement optimum often *stretches* an aircraft's stay
with inter-job idle so it can wrap a blocking partner — a schedule shape the
earliest-feasible decode cannot produce (it always prefers placing *before*
over *nested*, and packs jobs tight). So this candidate is written with
**explicit start times**, not via the decode: aircraft are grouped into
*rounds* of one per position; within a round, **only the positions that
actually block each other** get the concentric treatment — along every
front→rear arc the rear's stay is stretched so it wraps the front's stay by
`bandA` on both sides (deepest rear = outermost shell; since Attempt 11 the
wrap margin follows the restart's Mode-A geometry — 0 or `η`), while unconflicted
positions run tight and in parallel. Rounds are serialised within the
blocking component and simply chained (`+ε`) per position elsewhere. A small
beam of four round partitions (long-first / short-first / earliest-`E` /
round-robin) is tried and the best kept. On the complete graph this reduces
to the original wave builder (and now beats it: `full_R10` 258 → 235, below
the MILP's 261); on sparse topologies it reproduces the stay-stretching
mechanism verified in the certified optima (e.g. `triangle_loose_R10`); where
it does not help it is simply ignored by best-of.

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
    slice ← time_limit / (8 if R ≤ 10 else 2)   # per-start cap (Attempt 14a):
                                                 # R>10 gets 2 long trajectories
                                                 # (one per Mode-A band) instead
                                                 # of 3-4 short lottery restarts
    σ_NEH   ← R sorted by −Tᵣ            # makespan rule
    σ_SLACK ← R sorted by Lᵣ−Eᵣ−Tᵣ       # due-date (least headroom) rule
    best ← ∅ ;  best_F ← +∞ ;  i ← 0
    while time remains:                                  # restarts until deadline
        seed the RNG with base_seed + i
        deadline_i ← min(global deadline, now + slice)
        σ ← σ_NEH        if i = 0                        # two deterministic seeds…
          | σ_SLACK      if i = 1
          | BiasedOrder(better of the two, RNG)  if i ≥ 2    # …then one diversifier
        π ← GreedyConstruct(σ)
        (sol, F) ← OneStart(π, σ, deadline_i)
        if F < best_F:  best, best_F ← sol, F
        i ← i + 1
    return best
    # No fixed restart count: each restart ends on its own stale counter, so
    # small instances do hundreds of diverse restarts (the old fixed 8/4/3 cap
    # left ~97 % of the budget idle there) and large ones keep their slice.


PROCEDURE  BiasedOrder(σ_base, RNG):    # rank-biased geometric shuffle (β = 0.3)
    pool ← copy of σ_base ;  out ← []
    while pool not empty:
        draw rank k with P(k) ∝ (1−β)^k          # mostly ranks 0–3
        move pool[min(k, |pool|−1)] to out
    return out
    # Stays close to the base rule's logic while every restart explores a
    # distinct insertion order — the single diversification mechanism.


PROCEDURE  GreedyConstruct(σ):              # NEH-style greedy insertion
    π ← ∅ ;  placed ← []                     # prefix of σ already situated
    for r in σ:                              # in the rule's order
        placed ← placed + [r]
        for each position p ∈ P:
            π[r] ← p                          # tentative
            evaluate F of the partial decode of 'placed'   (cached)
        π[r] ← the position p with the lowest partial F
    return π                                  # σ is the start's priority order


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


PROCEDURE  Search(π, σ, Decode, deadline):          # local search + Iterated Greedy
    (π,σ) ← LocalSearch(π, σ, Decode)
    best ← (π,σ) ;  cur ← (π,σ) ;  stale ← 0
    while now < deadline and stale < max_no_improve:
        cand ← Perturb(cur, Decode)                  # destroy k + exact-slot reinsert
        cand ← LocalSearch(cand, Decode)
        if F(Decode(cand)) ≤ F(Decode(cur)):  cur ← cand   # better-or-equal walk
        if F(Decode(cand)) < F(Decode(best)):  best ← cand ; stale ← 0
        else: stale ← stale + 1
        # No re-centring rule: under better-or-equal acceptance, cur's
        # objective always equals best's, so "restart the walk from best"
        # would never have anything to do — retired as dead code (Attempt 14).
    return best


PROCEDURE  LocalSearch(π, σ, Decode):    # exact-filtered first-improvement (Attempt 14)
    cur ← F(Decode(π, σ))
    loop:
        C ← Critical(Decode(π, σ), Decode)            # exact candidate filter
        shuffle C at random
        improved ← false
        for r in C:
            (improved, π, σ, cur) ← TryMoves(r, π, σ, cur, Decode)
            if improved:  break                       # first improving move wins
        if not improved:  return (π, σ)                # local optimum for all 3 moves


PROCEDURE  Critical(sol, Decode):        # which aircraft can still improve the objective
    if Decode = DecodeManoeuvre:  return R             # no exact filter available there
    roots ← { r : delayᵣ > 0  or  finishᵣ = makespan(sol) }
    return roots ∪ { every r that pushed a root's start, transitively }  # pusher tree
    # exact under DecodeZeroMov: r outside the tree bounds no root and delays
    # nobody, so no move of r alone can lower F — brute-force-confirmed (§5)


PROCEDURE  TryMoves(r, π, σ, cur, Decode):           # first improving move of r
    for p in P \ {π(r)}:                              # (1) reassign
        if F(Decode(π[r↦p], σ)) < cur:  return (true, π[r↦p], σ, F(Decode(π[r↦p], σ)))
    for slot in OrderSlots(r, σ minus r, π, Decode):   # (2) relocate, 1 slot/class
        σ′ ← σ with r reinserted at slot
        if F(Decode(π, σ′)) < cur:  return (true, π, σ′, F(Decode(π, σ′)))
    for q ≠ r:                                        # (3) swap positions
        π′ ← π with π(r) and π(q) exchanged
        if F(Decode(π′, σ)) < cur:  return (true, π′, σ, F(Decode(π′, σ)))
    return (false, π, σ, cur)                          # r has no improving move


PROCEDURE  OrderSlots(r, σ, π, Decode):    # one representative slot per decode class
    delimiters ← { q ∈ σ : π(q) = π(r) }                                # same position
    if Decode = DecodeZeroMov:
        delimiters ← delimiters ∪ { q ∈ σ : (π(r), π(q)) blocking-conflict }
    return { the slot just before the first delimiter, and just after each
             delimiter } , or { any one slot } if delimiters = ∅
    # exact: two slots inside the same class decode byte-identically (§5) —
    # shared by TryMoves' relocate move and Perturb's reinsertion below


PROCEDURE  Perturb(π, σ, Decode):                    # Iterated Greedy kick
    with probability ½:
        remove k aircraft uniformly at random        # walk diversity
    otherwise:
        remove the k aircraft of largest contribution (Wᴰ·delayᵣ + small·Tᵣ),
            with light randomisation                  # targeted (delay) rule
    for each removed r:                              # greedy reconstruction
        insert r at the (position, slot) minimising F of the decode, trying
            only one representative slot per class (OrderSlots) at each position
    return the rebuilt state


# ── Inner layer: the two decoders ────────────────────────────────────

PROCEDURE  DecodeZeroMov(π, σ):        # feasible by construction, 0 moves
    placed ← ∅
    for r in σ:                                      # place in priority order
        F ← forbidden start-intervals of r vs each already-placed neighbour:
            same position p           → must keep gap ≥ ε  (before/after)
            blocking pair (p,p′)       → keep both access instants Mode-A:
                rear BEFORE front, or AFTER front, or ENCLOSING it
                (margin bandA: 0 on even restarts, η on odd — Attempt 11)
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

# Part II — Results and analysis (solver at Attempts 7+9+10+11+12+14; run under `c5f8f99`)

> Snapshot of the solver after **Attempts 7, 9, 10, 11, 12 and 14** (restarts-
> until-deadline + slim biased portfolio; DAG-generalised nest-stretch
> candidate; 50/50 targeted/random IG destruction; Mode-A band alignment,
> alternated per restart; closed-boundary `_sim_front`/`_place_front`; and now
> an **exact-filtered local search** replacing the B-VND's three exhaustive
> exchange sweeps and its reset-to-N1 rule, plus **two ILS trajectories per
> Mode-A band** replacing the lottery-restart regime at `R > 10`). This is the
> **battery of record** merged with Attempt 14 (`igvnd-v01-ils-at-scale`): the
> same "no-Triangle" grid — `chain` / `hub` / `two_rows` / `none`, R5–R30,
> loose / medium / tight — run seed-first under commit `1269c32` (the
> candidate arm; the merge commits `7c9090f`/`c5f8f99` changed nothing
> behaviourally), 1110 runs / 0 failures, paired against the cached MILP.
> Headline: **R5 is still closed in every profile and byte-identical to
> Attempt 12** (guards exact); R10 is essentially unchanged (`hub` identical,
> `chain`/`two_rows` inside the run-to-run band); R20/R30 tighten further
> against the unconverged MILP, consistent with the dedicated code-vs-code
> verdict against the Attempt-12 battery: **NET −403,270.5** (23 consistent
> wins vs 5 consistent losses, `IMPROVEMENT_LOG.md` Attempt 14) — the 5 small
> consistent regressions (hub R20 `wMK`/`wMOV`, `two_rows_loose_R30` `wMOV`,
> +0.4–1.3 %) are documented in Caveats. This battery still does **not**
> cover the `triangle` / `full` topologies — see Part II Caveats.

## Experimental setup

- **Battery:** the same "no-Triangle" grid — 37 configurations × 10 seeds:
  `chain` / `hub` / `two_rows` × `loose / medium / tight` × R5/R10/R20/R30
  (36 configs) plus the `none_tight` R10 control. Run **seed-first**. This
  is the dedicated verdict grid built for Attempt 11 and re-run unchanged
  for Attempts 12 and 14 (the candidate arm); it does **not** include the
  `triangle` or `full` topologies (see Caveats).
- **Methods:** job-level MILP baseline (`milp_job_*`) vs this heuristic. The
  MILP is fixed and was **not re-run** — its objectives come from the cached
  ledger `outputs/solutions/results.csv`. No missing MILP cells in this
  battery (every type pairs over all 10 seeds).
- **Weight profiles:** `wMK = (100,1,1)`, `wDLY = (1,100,1)`, `wMOV = (1,1,100)`.
- **Budget:** 60 s, strictly enforced. **1110 heuristic runs, 0 failures.**
- **Metric:** relative gap `g = (MILP_obj − heuristic_obj) / MILP_obj`
  (`g > 0` ⇒ heuristic better), **plus** per-component Δ (heuristic − MILP).
- **Log:**
  [`outputs/logs/202605_02_main_methods_20260905_203305.log`](../../../outputs/logs/202605_02_main_methods_20260905_203305.log)
  — self-stamped `Code state (git): 1269c32` (the battery-of-record merge
  commits are `7c9090f`/`c5f8f99`; the merge itself is a no-op on the
  solver). A separate fresh two-arm code-vs-code verdict — candidate
  `1269c32` (this same log) vs a **reused** Attempt-12 candidate log
  ([`outputs/logs/202605_02_main_methods_20260902_214555.log`](../../../outputs/logs/202605_02_main_methods_20260902_214555.log),
  same machine, 3 days earlier, user-approved reuse as the baseline arm) —
  is the code-vs-code verdict recorded in `IMPROVEMENT_LOG.md` Attempt 14; it
  is not reproduced here since this table's comparison axis is
  heuristic-vs-MILP, not code-vs-code.

## Relative objective gap (mean / min / max over 10 seeds)

```
[wMK  (100/1/1  makespan-priority)]            N     Mean      Min      Max
  scn_chain_loose_P5_R10                       10     -4.42%    -6.28%    -1.69%
  scn_chain_loose_P5_R20                       10    +15.53%    -1.99%   +28.81%
  scn_chain_loose_P5_R30                       10    +30.86%   +22.62%   +33.45%
  scn_chain_loose_P5_R5                        10     +0.00%    +0.00%    +0.00%
  scn_chain_medium_P5_R10                      10     -4.12%    -8.03%    -0.05%
  scn_chain_medium_P5_R20                      10    +17.21%   +11.18%   +22.75%
  scn_chain_medium_P5_R30                      10    +32.06%   +27.56%   +34.30%
  scn_chain_medium_P5_R5                       10     +0.00%    +0.00%    +0.00%
  scn_chain_tight_P5_R10                       10     -1.59%    -4.55%    +4.94%
  scn_chain_tight_P5_R20                       10    +13.84%    +3.95%   +25.33%
  scn_chain_tight_P5_R30                       10    +31.48%   +22.58%   +34.89%
  scn_chain_tight_P5_R5                        10     -0.01%    -0.07%    +0.00%
  scn_hub_loose_P5_R10                         10     -2.50%    -8.02%    +0.00%
  scn_hub_loose_P5_R20                         10    +13.38%   +10.14%   +16.49%
  scn_hub_loose_P5_R30                         10    +14.45%   +10.81%   +17.46%
  scn_hub_loose_P5_R5                          10     +0.00%    +0.00%    +0.00%
  scn_hub_medium_P5_R10                        10     -2.55%    -7.98%    +0.00%
  scn_hub_medium_P5_R20                        10    +12.49%    +6.09%   +16.15%
  scn_hub_medium_P5_R30                        10    +15.28%   +10.43%   +18.85%
  scn_hub_medium_P5_R5                         10     +0.00%    +0.00%    +0.00%
  scn_hub_tight_P5_R10                         10     -1.98%    -6.92%    +0.00%
  scn_hub_tight_P5_R20                         10    +13.25%    +6.70%   +15.69%
  scn_hub_tight_P5_R30                         10    +15.16%   +11.62%   +18.19%
  scn_hub_tight_P5_R5                          10     +0.00%    +0.00%    +0.00%
  scn_none_tight_P5_R10                        10     +0.00%    +0.00%    +0.00%
  scn_two_rows_loose_P5_R10                    10     -0.24%    -1.56%    +0.00%
  scn_two_rows_loose_P5_R20                    10    +13.87%    +2.79%   +28.37%
  scn_two_rows_loose_P5_R30                    10    +30.29%   +10.70%   +55.72%
  scn_two_rows_loose_P5_R5                     10     +0.00%    +0.00%    +0.00%
  scn_two_rows_medium_P5_R10                   10     -0.24%    -1.54%    +0.00%
  scn_two_rows_medium_P5_R20                   10    +17.08%    +1.15%   +31.00%
  scn_two_rows_medium_P5_R30                   10    +29.76%    +3.54%   +59.57%
  scn_two_rows_medium_P5_R5                    10     +0.00%    +0.00%    +0.00%
  scn_two_rows_tight_P5_R10                    10     -0.24%    -1.52%    +0.00%
  scn_two_rows_tight_P5_R20                    10    +19.83%    +5.42%   +38.78%
  scn_two_rows_tight_P5_R30                    10    +30.05%    +7.72%   +59.07%
  scn_two_rows_tight_P5_R5                     10     +0.00%    +0.00%    +0.00%

[wDLY (1/100/1  delay-priority)]               N     Mean      Min      Max
  scn_chain_loose_P5_R10                       10   -111.43%  -467.76%    -4.97%
  scn_chain_loose_P5_R20                       10    +32.06%   +15.84%   +50.82%
  scn_chain_loose_P5_R30                       10    +43.18%   +34.44%   +46.39%
  scn_chain_loose_P5_R5                        10     +0.00%    +0.00%    +0.00%
  scn_chain_medium_P5_R10                      10     +0.76%    -9.53%    +9.61%
  scn_chain_medium_P5_R20                      10    +24.99%    +8.78%   +34.38%
  scn_chain_medium_P5_R30                      10    +36.53%   +28.87%   +43.01%
  scn_chain_medium_P5_R5                       10     +0.00%    +0.00%    +0.00%
  scn_chain_tight_P5_R10                       10    +13.94%    +4.96%   +34.99%
  scn_chain_tight_P5_R20                       10    +18.47%    +9.73%   +39.05%
  scn_chain_tight_P5_R30                       10    +34.77%   +28.52%   +41.18%
  scn_chain_tight_P5_R5                        10    -25.25%  -252.50%    +0.00%
  scn_hub_loose_P5_R10                         10   -148.04%  -621.15%    +0.00%
  scn_hub_loose_P5_R20                         10    +22.20%    +7.71%   +32.73%
  scn_hub_loose_P5_R30                         10    +23.26%   +12.04%   +29.48%
  scn_hub_loose_P5_R5                          10     +0.00%    +0.00%    +0.00%
  scn_hub_medium_P5_R10                        10     -1.44%    -8.08%    +2.90%
  scn_hub_medium_P5_R20                        10    +18.56%   +13.29%   +22.94%
  scn_hub_medium_P5_R30                        10    +19.36%   +11.93%   +23.17%
  scn_hub_medium_P5_R5                         10     +0.00%    +0.00%    +0.00%
  scn_hub_tight_P5_R10                         10     +6.46%    -0.80%   +28.06%
  scn_hub_tight_P5_R20                         10    +15.14%    +3.96%   +22.36%
  scn_hub_tight_P5_R30                         10    +18.38%   +13.54%   +22.40%
  scn_hub_tight_P5_R5                          10     -2.87%   -28.74%    +0.00%
  scn_none_tight_P5_R10                        10     +0.00%    +0.00%    +0.00%
  scn_two_rows_loose_P5_R10                    10    -10.58%   -68.61%    +0.00%
  scn_two_rows_loose_P5_R20                    10    +23.02%    +1.62%   +47.32%
  scn_two_rows_loose_P5_R30                    10    +43.51%   +22.96%   +61.53%
  scn_two_rows_loose_P5_R5                     10     +0.00%    +0.00%    +0.00%
  scn_two_rows_medium_P5_R10                   10     +0.23%    +0.00%    +1.87%
  scn_two_rows_medium_P5_R20                   10    +23.47%    +4.91%   +57.21%
  scn_two_rows_medium_P5_R30                   10    +35.99%   +14.77%   +59.74%
  scn_two_rows_medium_P5_R5                    10     +0.00%    +0.00%    +0.00%
  scn_two_rows_tight_P5_R10                    10     +2.01%    +0.00%    +5.82%
  scn_two_rows_tight_P5_R20                    10    +18.75%    +0.89%   +38.33%
  scn_two_rows_tight_P5_R30                    10    +32.37%   +13.26%   +51.96%
  scn_two_rows_tight_P5_R5                     10     +0.00%    +0.00%    +0.00%

[wMOV (1/1/100  movement-priority)]            N     Mean      Min      Max
  scn_chain_loose_P5_R10                       10     -4.40%   -18.01%    +0.00%
  scn_chain_loose_P5_R20                       10    +15.22%    -5.76%   +28.45%
  scn_chain_loose_P5_R30                       10    +37.09%   +34.02%   +41.56%
  scn_chain_loose_P5_R5                        10     +0.00%    +0.00%    +0.00%
  scn_chain_medium_P5_R10                      10     -2.02%   -10.53%    +0.00%
  scn_chain_medium_P5_R20                      10    +19.92%   +11.08%   +36.81%
  scn_chain_medium_P5_R30                      10    +30.10%   +20.03%   +34.75%
  scn_chain_medium_P5_R5                       10     +0.00%    +0.00%    +0.00%
  scn_chain_tight_P5_R10                       10     +1.96%   -11.86%   +15.79%
  scn_chain_tight_P5_R20                       10    +15.96%    -0.39%   +25.59%
  scn_chain_tight_P5_R30                       10    +31.67%   +27.67%   +38.17%
  scn_chain_tight_P5_R5                        10     +0.00%    +0.00%    +0.00%
  scn_hub_loose_P5_R10                         10     +0.00%    +0.00%    +0.00%
  scn_hub_loose_P5_R20                         10    +25.42%   +17.38%   +33.71%
  scn_hub_loose_P5_R30                         10    +22.94%   +11.23%   +29.20%
  scn_hub_loose_P5_R5                          10     +0.00%    +0.00%    +0.00%
  scn_hub_medium_P5_R10                        10     +0.00%    +0.00%    +0.00%
  scn_hub_medium_P5_R20                        10    +20.81%   +14.45%   +27.01%
  scn_hub_medium_P5_R30                        10    +18.12%   +10.34%   +25.12%
  scn_hub_medium_P5_R5                         10     +0.00%    +0.00%    +0.00%
  scn_hub_tight_P5_R10                         10     +2.81%    +0.00%   +21.03%
  scn_hub_tight_P5_R20                         10    +17.46%   +14.09%   +21.61%
  scn_hub_tight_P5_R30                         10    +17.57%   +13.91%   +24.04%
  scn_hub_tight_P5_R5                          10     +0.00%    +0.00%    +0.00%
  scn_none_tight_P5_R10                        10     +0.00%    +0.00%    +0.00%
  scn_two_rows_loose_P5_R10                    10     -0.08%    -0.76%    +0.00%
  scn_two_rows_loose_P5_R20                    10    +19.13%    +4.15%   +40.99%
  scn_two_rows_loose_P5_R30                    10    +33.12%   +12.09%   +49.75%
  scn_two_rows_loose_P5_R5                     10     +0.00%    +0.00%    +0.00%
  scn_two_rows_medium_P5_R10                   10     +0.00%    +0.00%    +0.00%
  scn_two_rows_medium_P5_R20                   10    +18.81%    +4.41%   +46.89%
  scn_two_rows_medium_P5_R30                   10    +36.49%    +8.55%   +66.20%
  scn_two_rows_medium_P5_R5                    10     +0.00%    +0.00%    +0.00%
  scn_two_rows_tight_P5_R10                    10     +0.80%    +0.00%    +4.35%
  scn_two_rows_tight_P5_R20                    10    +17.00%    +4.69%   +34.00%
  scn_two_rows_tight_P5_R30                    10    +34.63%   +15.87%   +59.37%
  scn_two_rows_tight_P5_R5                     10     +0.00%    +0.00%    +0.00%

[ALL profiles]                                 N     Mean      Min      Max
  scn_chain_loose_P5_R10                       30    -40.08%  -467.76%    +0.00%
  scn_chain_loose_P5_R20                       30    +20.94%    -5.76%   +50.82%
  scn_chain_loose_P5_R30                       30    +37.04%   +22.62%   +46.39%
  scn_chain_loose_P5_R5                        30     +0.00%    +0.00%    +0.00%
  scn_chain_medium_P5_R10                      30     -1.79%   -10.53%    +9.61%
  scn_chain_medium_P5_R20                      30    +20.71%    +8.78%   +36.81%
  scn_chain_medium_P5_R30                      30    +32.90%   +20.03%   +43.01%
  scn_chain_medium_P5_R5                       30     +0.00%    +0.00%    +0.00%
  scn_chain_tight_P5_R10                       30     +4.77%   -11.86%   +34.99%
  scn_chain_tight_P5_R20                       30    +16.09%    -0.39%   +39.05%
  scn_chain_tight_P5_R30                       30    +32.64%   +22.58%   +41.18%
  scn_chain_tight_P5_R5                        30     -8.42%  -252.50%    +0.00%
  scn_hub_loose_P5_R10                         30    -50.18%  -621.15%    +0.00%
  scn_hub_loose_P5_R20                         30    +20.33%    +7.71%   +33.71%
  scn_hub_loose_P5_R30                         30    +20.22%   +10.81%   +29.48%
  scn_hub_loose_P5_R5                          30     +0.00%    +0.00%    +0.00%
  scn_hub_medium_P5_R10                        30     -1.33%    -8.08%    +2.90%
  scn_hub_medium_P5_R20                        30    +17.29%    +6.09%   +27.01%
  scn_hub_medium_P5_R30                        30    +17.59%   +10.34%   +25.12%
  scn_hub_medium_P5_R5                         30     +0.00%    +0.00%    +0.00%
  scn_hub_tight_P5_R10                         30     +2.43%    -6.92%   +28.06%
  scn_hub_tight_P5_R20                         30    +15.28%    +3.96%   +22.36%
  scn_hub_tight_P5_R30                         30    +17.04%   +11.62%   +24.04%
  scn_hub_tight_P5_R5                          30     -0.96%   -28.74%    +0.00%
  scn_none_tight_P5_R10                        30     +0.00%    +0.00%    +0.00%
  scn_two_rows_loose_P5_R10                    30     -3.63%   -68.61%    +0.00%
  scn_two_rows_loose_P5_R20                    30    +18.67%    +1.62%   +47.32%
  scn_two_rows_loose_P5_R30                    30    +35.64%   +10.70%   +61.53%
  scn_two_rows_loose_P5_R5                     30     +0.00%    +0.00%    +0.00%
  scn_two_rows_medium_P5_R10                   30     -0.00%    -1.54%    +1.87%
  scn_two_rows_medium_P5_R20                   30    +19.79%    +1.15%   +57.21%
  scn_two_rows_medium_P5_R30                   30    +34.08%    +3.54%   +66.20%
  scn_two_rows_medium_P5_R5                    30     +0.00%    +0.00%    +0.00%
  scn_two_rows_tight_P5_R10                    30     +0.86%    -1.52%    +5.82%
  scn_two_rows_tight_P5_R20                    30    +18.53%    +0.89%   +38.78%
  scn_two_rows_tight_P5_R30                    30    +32.35%    +7.72%   +59.37%
  scn_two_rows_tight_P5_R5                     30     +0.00%    +0.00%    +0.00%
```

## Per-component mean Δ (heuristic − MILP; negative = heuristic better)

```
[wMK]                        Dmakespan      Ddelay      Dmov
  scn_chain_loose_P5_R10         10        +2.80       -2.80      +1.80
  scn_chain_loose_P5_R20         10       -25.30     -189.25     +17.40
  scn_chain_loose_P5_R30         10      -104.55    -1117.65     +66.00
  scn_chain_loose_P5_R5          10        +0.00       +0.00      +0.00
  scn_chain_medium_P5_R10        10        +2.55       +1.20      +3.40
  scn_chain_medium_P5_R20        10       -27.80     -175.90     +16.60
  scn_chain_medium_P5_R30        10      -108.80    -1264.80     +64.00
  scn_chain_medium_P5_R5         10        +0.00       +0.00      +0.00
  scn_chain_tight_P5_R10         10        +1.10      -13.15      +0.60
  scn_chain_tight_P5_R20         10       -22.30     -120.70     +15.00
  scn_chain_tight_P5_R30         10      -108.40    -1274.85     +70.00
  scn_chain_tight_P5_R5          10        +0.00       +0.80      -0.40
  scn_hub_loose_P5_R10           10        +1.65       -3.65      -6.80
  scn_hub_loose_P5_R20           10       -18.90     -105.55     -16.80
  scn_hub_loose_P5_R30           10       -38.30     -330.40     +16.40
  scn_hub_loose_P5_R5            10        +0.00       +0.00      +0.00
  scn_hub_medium_P5_R10          10        +1.65       +0.30      -7.00
  scn_hub_medium_P5_R20          10       -17.65     -114.05     -14.20
  scn_hub_medium_P5_R30          10       -40.40     -435.80     +14.80
  scn_hub_medium_P5_R5           10        +0.00       +0.00      +0.00
  scn_hub_tight_P5_R10           10        +1.35       -2.80      -7.60
  scn_hub_tight_P5_R20           10       -19.30      -96.35     -16.60
  scn_hub_tight_P5_R30           10       -41.05     -376.65     +21.60
  scn_hub_tight_P5_R5            10        +0.00       +0.00      +0.00
  scn_none_tight_P5_R10          10        +0.00       +0.00      +0.00
  scn_two_rows_loose_P5_R10      10        +0.15       -0.10      -0.60
  scn_two_rows_loose_P5_R20      10       -20.20     -141.45      -2.60
  scn_two_rows_loose_P5_R30      10      -101.90    -1097.05      +1.80
  scn_two_rows_loose_P5_R5       10        +0.00       +0.00      +0.00
  scn_two_rows_medium_P5_R10     10        +0.15       -0.10      -0.40
  scn_two_rows_medium_P5_R20     10       -27.05     -154.55      -0.60
  scn_two_rows_medium_P5_R30     10      -106.60     -993.10      -1.00
  scn_two_rows_medium_P5_R5      10        +0.00       +0.00      +0.00
  scn_two_rows_tight_P5_R10      10        +0.15       +0.45      -0.60
  scn_two_rows_tight_P5_R20      10       -31.85     -279.65      -0.60
  scn_two_rows_tight_P5_R30      10      -109.65    -1115.45      +7.40
  scn_two_rows_tight_P5_R5       10        +0.00       +0.00      +0.00

[wDLY]                        Dmakespan      Ddelay      Dmov
  scn_chain_loose_P5_R10         10        +1.90       +1.85      +2.60
  scn_chain_loose_P5_R20         10       -31.50     -201.95     +18.80
  scn_chain_loose_P5_R30         10      -106.35    -1287.75     +60.40
  scn_chain_loose_P5_R5          10        +0.00       +0.00      +0.00
  scn_chain_medium_P5_R10        10        +0.40       -0.60      +1.40
  scn_chain_medium_P5_R20        10       -35.25     -202.45     +18.80
  scn_chain_medium_P5_R30        10      -102.05    -1195.35     +57.20
  scn_chain_medium_P5_R5         10        +0.00       +0.00      +0.00
  scn_chain_tight_P5_R10         10        -6.10      -18.90      -1.20
  scn_chain_tight_P5_R20         10       -32.70     -172.15     +18.00
  scn_chain_tight_P5_R30         10      -103.90    -1255.75     +58.80
  scn_chain_tight_P5_R5          10        +0.10       +0.10      +0.00
  scn_hub_loose_P5_R10           10        -0.55       +1.85      -3.80
  scn_hub_loose_P5_R20           10       -22.60     -105.45     -23.40
  scn_hub_loose_P5_R30           10       -39.85     -453.50      +8.00
  scn_hub_loose_P5_R5            10        +0.00       +0.00      +0.00
  scn_hub_medium_P5_R10          10        -1.90       +0.80      -1.20
  scn_hub_medium_P5_R20          10       -24.75     -123.30     -14.40
  scn_hub_medium_P5_R30          10       -46.30     -451.60     +11.40
  scn_hub_medium_P5_R5           10        +0.00       +0.00      +0.00
  scn_hub_tight_P5_R10           10        -5.35       -8.65      -0.60
  scn_hub_tight_P5_R20           10       -19.15     -124.85      -8.60
  scn_hub_tight_P5_R30           10       -45.30     -481.05      +6.00
  scn_hub_tight_P5_R5            10        +0.00       +0.10      -0.20
  scn_none_tight_P5_R10          10        +0.00       +0.00      +0.00
  scn_two_rows_loose_P5_R10      10        +0.50       +0.15      -1.20
  scn_two_rows_loose_P5_R20      10       -23.10     -104.20      -4.60
  scn_two_rows_loose_P5_R30      10      -116.05    -1162.65      +2.40
  scn_two_rows_loose_P5_R5       10        +0.00       +0.00      +0.00
  scn_two_rows_medium_P5_R10     10        -1.80       -0.10      -0.40
  scn_two_rows_medium_P5_R20     10       -36.55     -178.70      -1.40
  scn_two_rows_medium_P5_R30     10      -113.15    -1123.25      +0.20
  scn_two_rows_medium_P5_R5      10        +0.00       +0.00      +0.00
  scn_two_rows_tight_P5_R10      10        -4.45       -2.05      -1.80
  scn_two_rows_tight_P5_R20      10       -32.95     -162.25      -0.60
  scn_two_rows_tight_P5_R30      10      -121.75    -1089.30      -6.20
  scn_two_rows_tight_P5_R5       10        +0.00       +0.00      +0.00

[wMOV]                        Dmakespan      Ddelay      Dmov
  scn_chain_loose_P5_R10         10        +0.60       +2.95      +0.00
  scn_chain_loose_P5_R20         10       -25.75      -97.60      +0.00
  scn_chain_loose_P5_R30         10      -106.55    -1143.85      +0.00
  scn_chain_loose_P5_R5          10        +0.00       +0.00      +0.00
  scn_chain_medium_P5_R10        10        +0.45       +2.55      +0.00
  scn_chain_medium_P5_R20        10       -41.85     -174.05      +0.00
  scn_chain_medium_P5_R30        10      -113.30     -973.80      +0.00
  scn_chain_medium_P5_R5         10        +0.00       +0.00      +0.00
  scn_chain_tight_P5_R10         10        -1.00       -4.55      +0.00
  scn_chain_tight_P5_R20         10       -35.00     -159.30      +0.00
  scn_chain_tight_P5_R30         10      -107.35    -1176.75      +0.00
  scn_chain_tight_P5_R5          10        +0.00       +0.00      +0.00
  scn_hub_loose_P5_R10           10        -0.10       +0.10      +0.00
  scn_hub_loose_P5_R20           10       -24.55     -145.60      +0.00
  scn_hub_loose_P5_R30           10       -53.55     -461.80      +0.00
  scn_hub_loose_P5_R5            10        +0.00       +0.00      +0.00
  scn_hub_medium_P5_R10          10        +0.00       +0.00      +0.00
  scn_hub_medium_P5_R20          10       -25.00     -152.25      +0.00
  scn_hub_medium_P5_R30          10       -48.10     -429.10      +0.00
  scn_hub_medium_P5_R5           10        +0.00       +0.00      +0.00
  scn_hub_tight_P5_R10           10        -2.75       -3.45      +0.00
  scn_hub_tight_P5_R20           10       -21.85     -149.20      +0.00
  scn_hub_tight_P5_R30           10       -42.75     -460.55      +0.00
  scn_hub_tight_P5_R5            10        +0.00       +0.00      +0.00
  scn_none_tight_P5_R10          10        +0.00       +0.00      +0.00
  scn_two_rows_loose_P5_R10      10        +0.30       -0.25      +0.00
  scn_two_rows_loose_P5_R20      10       -21.45      -95.75      +0.00
  scn_two_rows_loose_P5_R30      10       -88.20     -771.45      +0.00
  scn_two_rows_loose_P5_R5       10        +0.00       +0.00      +0.00
  scn_two_rows_medium_P5_R10     10        +0.10       -0.10      +0.00
  scn_two_rows_medium_P5_R20     10       -27.50     -135.85      +0.00
  scn_two_rows_medium_P5_R30     10      -133.15    -1293.15      +0.00
  scn_two_rows_medium_P5_R5      10        +0.00       +0.00      +0.00
  scn_two_rows_tight_P5_R10      10        -0.70       -0.60      +0.00
  scn_two_rows_tight_P5_R20      10       -24.20     -144.00      +0.00
  scn_two_rows_tight_P5_R30      10      -127.20    -1273.30      +0.00
  scn_two_rows_tight_P5_R5       10        +0.00       +0.00      +0.00
```

## Performance summary

- **R5 — closed, byte-identical to Attempt 12 (guards exact).** Every
  `chain`/`hub`/`two_rows`/`none` R5 instance matches the proven MILP optimum
  on all three profiles (`wMK`/`wMOV` exact 0.00 %; `wDLY` is 0.00 % except
  `chain_tight_R5` (−25.25 %) and `hub_tight_R5` (−2.87 %) — both unchanged
  from the Attempt-12 battery, the small-denominator artifact of an optimum
  delay of 1–3 units, see Caveats). Attempt 14's exact-filtered local search
  and two-trajectory ILS only engage at `R > 10`, so R5 cannot move.
- **`wMK` — R10 essentially unchanged from Attempt 12.** `hub` R10 is
  byte-identical to Attempt 12 (−2.0 % to −2.55 %); `chain` R10 shifts
  slightly inside the run-to-run band (−1.6 % to −4.4 %, vs −2.4 % to −5.1 %
  before); `two_rows` R10 tightens to a uniform −0.24 % (vs −0.23 % to
  −0.39 % before). R20/R30 gaps of +12.5 % to +32.1 % are the
  unconverged-MILP effect (Caveat 2), not a heuristic regression — the
  per-component table shows the heuristic cutting more makespan/delay units
  than the Attempt-12 battery at the same or fewer movements (the exact-
  filtered descent reaches deeper local optima per kick).
- **`wDLY` — at/above the MILP on `chain_medium`/`two_rows_medium`/
  `two_rows_tight` R10; small positive residual on `chain_tight`/`hub_tight`
  R10 (+6.5 % to +13.9 %, essentially unchanged from Attempt 12's +6.6 % to
  +13.8 %).** The large negative numbers on `chain_loose_R10` (−111.4 %),
  `hub_loose_R10` (−148.0 %), `two_rows_loose_R10` (−10.6 %) and
  `chain_tight_R5`/`hub_tight_R5` are all the small-denominator artifact
  (optimum delay ≈ 0–3; read Δdelay, which stays single-digit on every one
  of them). R20/R30 gaps (+15.1 % to +43.5 %) are again the
  unconverged-MILP effect.
- **`wMOV` — still a clean sweep on movements.** `Δmov = 0` on every single
  cell in this battery (both the MILP and the heuristic reach 0-movement
  schedules on `chain`/`hub`/`two_rows`/`none` at every size under the
  movement-priority weight) — Attempt 14 does not touch this invariant. R10
  is at/above the MILP (`chain`/`hub` 0 % to +2.8 %, `two_rows` −0.1 % to
  +0.8 %); R20/R30 win decisively on makespan and delay against the
  unconverged MILP (+15.2 % to +37.1 %).
- **Scale (R20/R30):** the heuristic wins on every type and every profile
  once the MILP stops converging in 60 s — mean gaps +12.5 % to +32.1 % at
  R20 and +14.5 % to +43.5 % at R30, both ranges wider than the Attempt-12
  battery (+13.9–20.5 % / +15.0–36.0 %), consistent with Attempt 14
  targeting exactly this regime.
- **Attempt 14 vs the Attempt-12 battery of record (code-vs-code, not the
  heuristic-vs-MILP table above):** a dedicated fresh two-arm verdict
  (candidate = this log, baseline = the reused Attempt-12 candidate log)
  gives **NET −403,270.5** (`chain` −258,996, `hub` −97,318, `two_rows`
  −46,957, `none` ±0). R5: all 27 cells identical. R10: NET −204, 1
  consistent win, 0 consistent losses. R20: mean −0.88 %, 8 consistent wins
  / 4 consistent losses. R30: mean −1.66 %, 14 consistent wins / 1
  consistent loss. Overall 23 consistent wins vs 5 consistent losses; 50
  cells better / 22 worse / 39 identical. Five cells regress consistently
  (≥7/10 seeds) above the 19-unit R10 noise floor, all small: `hub_loose/
  medium/tight_R20` `wMK` +0.36 / +0.73 / +0.52 %, `hub_tight_R20` `wMOV`
  +0.70 %, `two_rows_loose_R30` `wMOV` +1.29 % — see Caveat 5. Full detail
  in `IMPROVEMENT_LOG.md` Attempt 14.

## Caveats

1. **Small-denominator inflation.** When the optimum objective is small
   (loose/tight R5/R10; `wDLY` with optimum delay ≈ 0–3), the relative gap
   explodes for a tiny absolute difference — see `chain_loose_R10 wDLY`
   (−111.4 %, Δdelay only +1.85), `hub_loose_R10 wDLY` (−148.0 %, Δdelay
   +1.85), `two_rows_loose_R10 wDLY` (−10.6 %, Δdelay +0.15) and
   `chain_tight_R5 wDLY` (−25.25 %, Δdelay +0.10). Read the per-component Δ,
   not the percentage, for these rows.
2. **MILP unconverged at scale.** R20/R30 MILP objectives are 60-s
   incumbents, not proven optima, so heuristic "wins" there mean "better
   feasible solution fast." No MILP cells were missing (OOM) in this
   battery, unlike the earlier 290-instance run.
3. **This battery excludes `triangle` and `full`.** It is the dedicated
   verdict grid built to measure Attempt 11 against the newly-extended
   `chain`/`hub` instance set (`chain`/`hub`/`two_rows`/`none` only, 37
   configs) and re-run unchanged for Attempts 12 and 14. The `triangle`/
   `full` numbers in this doc's history (Attempts 7+9+10, log `…174533`)
   are **not** re-measured under Attempts 11–14's code and should be
   treated as stale until a full battery (all topologies) is run again.
4. **Never compare against cached heuristic rows.** Cached `igvnd` rows go
   stale across code states and machine load; pair fresh heuristic runs
   against the cached **MILP** rows only.
5. **Attempt 14's residual regressions (small, not zero).** The code-vs-code
   verdict against the Attempt-12 battery found five cells that regress
   consistently (≥7/10 seeds) above the 19-unit noise floor: `hub_loose/
   medium/tight_R20 wMK` (+0.36 / +0.73 / +0.52 %, +46 / +96 / +69 objective
   units on ~13,000 — inside the cell's own K=2 run-to-run band of 5.9 % on
   `hub_medium_R20 wMK`), `hub_tight_R20 wMOV` (+0.70 %, +5.6 on 798) and
   `two_rows_loose_R30 wMOV` (+1.29 %, +20 on 1552). An `AB` (2 slices) vs
   `AB-s4` (4 slices) check on the hub-R20-wMK family found no systematic
   difference, so the R20 slice change is not the cause; the pattern is
   within the ~6-cell false-positive rate expected by chance among 111
   comparisons (against 23 winning cells), or a small residual cost of the
   randomised descent on `hub wMK`. The house rule ("zero consistent
   regressions") is not strictly met; kept anyway per the user's 2026-09-06
   decision (`IMPROVEMENT_LOG.md` Attempt 14) because the large MILP-favouring
   gaps shrank without adding machinery.

---

# Part III — Improvement roadmap

**Diagnosis (updated after Commits 1–6 + the full battery).** The base
architecture is well chosen: separating the combinatorial state `(π, σ)` from a
deterministic decoder shrinks the search space and lets the decoder price each
assignment/order with timing, blocking and manoeuvres — aligned with NEH (a
strong makespan constructor), Iterated Greedy (destruction/reconstruction) and
VND/VNS (systematic neighbourhood change). After the planned per-weight
operators were built and **measured**, the picture changed: the method is now
**at or beyond the MILP wherever the MILP is a reliable target**, and the
remaining gaps are *not* missing-operator gaps. Per weight:

- `wMK`: near the MILP on R10 (±2.5 %, exact on `none`/`R5`); Mode-B/nesting do
  their job. Wins at scale (R20/R30) where the MILP times out.
- `wDLY`: at/above the MILP on R10. The residual that motivated Commit 6
  (DelayRiskRepair) turned out to be **search-variance-bound, not
  order-bound** — the repair never beat the multi-start incumbent (0/74), and
  the run-to-run noise (≈19 delay units) is larger than the residual itself
  (≤ 1.5 units on the one clean seed). The portfolio already reaches the good
  delay basin; seeding it explicitly adds nothing.
- `wMOV`: with both methods at 0 manoeuvres, the winner packs tightest. The
  dense-nest (Commit 4) made the heuristic win on `full`/`chain`/`hub`; where
  it still trails, the MILP is **unconverged** (no reliable target) and the
  schedule is already nested (Commit-5 `serial_points ≈ 1/10`).
- R20/R30: the budget is now strictly enforced (Priority 0 done), so these are
  a fair 60-s comparison — and the heuristic wins decisively (the MILP is an
  unconverged 60-s incumbent there).

**Net:** the method is near its practical ceiling on small/medium instances.
The remaining residuals are either noise-level or against an unconverged MILP,
so further per-weight operators chase noise — the disciplined lesson of
Commits 3 and 6 (*measure the noise floor before keeping an operator*). The
items below are kept for the record and ordered by impact/risk. Cumulative
ablations: `A0 = 68dc201 → A1 budget+cache+logging → A2 seeds → A3 regret →
A4 delay-manoeuvre → A5 zero-move repack → A6 ALNS`.

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
| `n_starts` | `None` (= restart until the deadline) | optional HARD CAP on restarts, testing/ablation only (§I.7) |
| `k_destroy` | `max(1, R//4)` | aircraft removed per IG perturbation (§I.6) |
| `max_no_improve` | 400 | stale-iteration early stop per search |
| `use_v3` | `True` | enable the manoeuvre-aware polish (§I.3.2) |

## Method ↔ code map

| Method concept (Part I) | Code |
| --- | --- |
| Instance preprocessing (chains, `Tᵣ`, blocking arcs, depths, interruptibility) | `_prepare` |
| Two-layer state | `assignment: dict[r→p]` + `order: list[r]` |
| Zero-movement decoder (§3.1) | `_decode`; admissible-placement bands in `_forbidden` |
| Manoeuvre-aware decoder (§3.2) | `_decode_v3`; per-front placement `_place_front`; forward simulation with Mode-B/C `_sim_front` (closed-boundary access classification since Attempt 12) |
| Closed-boundary access classification (Attempt 12) | `_sim_front`'s `used` array seeds accesses at the stay start as already-Mode-A; the Mode-B gap-batch windows in `_sim_front` are closed-at-start / open-at-end (`f_j ≤ τ < f_j + window`, was `f_j < τ ≤ f_j + window`); `_place_front`'s zero-movement candidate set adds `τ` itself alongside `τ ± η` |
| Mode-A vacant-front clearance, alternated per restart (Attempt 11) | `self.bandA` — `_forbidden`'s admissible bands and the `_place_front` zero-movement candidates key off `self.bandA` instead of the fixed `self.eta`; the restart loop in `solve` sets `self.bandA = 0.0 if i % 2 == 0 else self.eta` (even restarts search the checker-exact touching-allowed geometry, odd restarts the older conservative-η geometry); `_dense_nest_solution` always pins `self.bandA = 0.0` before building. `_decoder_tag` carries the active band (`v2b` for band 0, `v2` for band η) so the decode cache stays disjoint between the two geometries. |
| Cached decode (memoised eval) | `_eval` (keyed by decoder tag, order, positions-along-order; reset per solve) |
| Concentric nest-stretch builder over the blocking DAG (§8; explicit starts, best-of) | `_dense_nest_solution` (called once in `solve` when `Wˢ`-dominant + arcs; Attempt 9 generalised its internals from complete-graph waves to the real arc structure) |
| Risk diagnostics (Commit 5; observability) | `_diagnostics(best_sol, start_objs)` → `delay_risk` / `nesting_risk` / `search_risk`, attached to the solution + one log line |
| Slim construction portfolio (§4: NEH + SLACK + biased shuffle) | seed orders inline in `solve`; `_greedy_construct(order)`; `_biased_order(base)` |
| Local search (§5 — **Attempt 14: exact-filtered, replaces the old exhaustive VND/`_vnd`**) | `_local_search` (first-improvement loop); candidate filter `_critical` (pusher tree under `_decode`, every aircraft under `_decode_v3`); exact per-class order-slot enumeration `_order_slots`; move application `_try_moves` (reassign / relocate / swap, first-improvement, randomised scan order) |
| IG perturbation (§6) | `_perturb` (now reinserts via the same exact `_order_slots`, not a blind slot scan) |
| Search driver (decoder-agnostic via `self._decode_fn`) | `_search` (descend with `_local_search`, then IG kick + re-descend; acceptance keeps `cur` on the best plateau — **Attempt 14 retires the dead re-centre rule**, no `cur`-reset code remains) |
| Two ILS trajectories per Mode-A band at `R > 10` (Attempt 14a, replaces the old 3–4 lottery restarts) | `solve`'s `slice_div = 8 if R <= 10 else 2` (per-start slice `time_limit_s / slice_div`); `self.bandA = 0.0 if i % 2 == 0 else self.eta` still alternates every restart, so at `R > 10` there are effectively two long half-budget trajectories, one per band |
| Two-regime combination per restart (§8) | `_one_start(a0, o0, …)` (phase 1 = `_decode`, phase 2 = `_decode_v3`) |
| Multi-start until deadline (§7) | `while` loop in `solve` (per-start slice; optional `n_starts` hard cap) |
| Time budget enforced in every loop | `_time_up` (`self._deadline`) |
| Safety net (§8) | `_is_compliant` calls the real `check_solution` |

## Key implementation notes

- `_forbidden` emits, per already-placed neighbour, the infeasible
  start-time bands; for a blocking pair the *two* bands leave a feasible
  hole between them — that hole is the nesting option of §3.1.
- **Mode-A clearance is a variable, not a constant (Attempt 11).** Before
  Attempt 11, `_forbidden` and the zero-movement candidates in
  `_place_front` used the fixed margin `self.eta` to keep a rear aircraft's
  access instants clear of the front's stay. The problem statement's Mode A
  ("no aircraft occupies `p` at `τ`") requires no margin at all — touching is
  vacant — so the fixed-η version searched a strictly smaller space than the
  problem allows. `self.bandA` replaces the fixed `eta` in both call sites;
  the restart loop alternates it (band 0 on even restarts, band `eta` on odd
  ones) because a band-0-only landscape regressed `chain` R10 and `wDLY` at
  scale relative to the older, more conservative geometry — alternating
  keeps both basins reachable across the multi-start portfolio.
  `_dense_nest_solution` always builds at band 0 (the tightest, checker-exact
  wrap).
- `_sim_front` returns `(finish, sched, mov_events, feasible)`; `mov_events`
  folds Mode-B + Mode-C events and `movements = 2·mov_events`. It rejects a
  start (returns infeasible) on an access in an `η`-margin, a Mode-C on a
  non-interruptible job, or any access it cannot classify.
- **Closed-boundary access classification (Attempt 12).** Before Attempt 12,
  `_sim_front` initialised `used = [False] * len(acc)`, so an access falling
  exactly at the front's own stay start `s_start` was not pre-classified —
  it had to survive the first job's `η`-margin/`κ` checks even though the
  checker treats it as unambiguously Mode A. It now seeds
  `used[i] = True` for any `τ` within `1e-9` of `s_start`. The Mode-B
  gap-batch window also moved from open-at-start/closed-at-end
  (`f_j < τ ≤ f_j + window`) to the checker's closed-at-start/open-at-end
  (`f_j ≤ τ < f_j + window`), so an access exactly at a job's end is now
  routed through the gap that *follows* it rather than being mis-attributed
  to the next job's interior. `_place_front`'s candidate set also gained
  `τ` itself (previously only `τ ± η`), symmetric with the pre-existing
  `τ − T` candidate. Net effect on the battery: the small-denominator
  `wDLY` outliers on `chain`/`hub` R10/R5 shrink sharply (Part II).
- The objective inside the decoders is `Wᴹ·makespan + Wᴰ·total_delay +
  Wˢ·movements`; the zero-movement decoder fixes `movements = 0`.
- **Time budget.** `_time_up()` (a `time.perf_counter()` vs `self._deadline`
  check) is polled inside every search loop — construction, local search, each
  candidate's move scan, and the IG reinsertion — so the solver returns within
  `time_limit_s` even on large instances where a single sweep is expensive.
  Loops that must leave a complete solution (construction, reinsertion) fall
  back to a cheap feasible completion when the budget runs out.
- **Exact-filtered local search (Attempt 14b), two exact facts it relies on.**
  (1) Under `_decode` (v2), a move touching only aircraft outside the pusher
  tree rooted at the makespan/delayed aircraft cannot improve the objective —
  `_critical` restricts the candidate scan to that tree, derived exact and
  confirmed by a brute-force check against the old N1/N2 (0 improving moves
  in 18/18 test cases; N3 — swap two order slots at once — leaks 1–2 moves in
  3/18 cases, all at R20, accepted as a small residual). (2) `_order_slots`
  exploits that inserting an aircraft at any of two slots inside the same
  "distinct-decode class" (delimited by same-position/blocking-conflict
  neighbours; only same-position neighbours matter under `_decode_v3`, whose
  order only matters within a position) produces a byte-identical decode, so
  only one representative slot per class needs to be tried — this pruning is
  shared by `_try_moves` and `_perturb`'s reinsertion. Net effect: cheaper
  descents let far more IG kicks fit in the same wall-clock budget, which is
  what actually moves the R20/R30 numbers (Part II), not a change in which
  local optima are reachable.
- **Two ILS trajectories instead of lottery restarts at `R > 10` (Attempt
  14a).** Diagnosis: at `R ≥ 20` a fixed 8-way restart split left each
  restart too short to finish even one VND confirm pass, and the eventual
  best essentially never came from a restart index ≥ 4 — the old regime was
  paying for diversity it could not use. `slice_div` now drops to 2 once
  `R > 10`, so the existing per-restart `bandA` alternation (`i % 2`, Attempt
  11) yields exactly two long half-budget trajectories, one per Mode-A band,
  instead of 3–4 short lottery restarts. The old "re-centre `cur` to the
  global best" rule is retired along with it (dead code: the acceptance rule
  already keeps `cur` on the best plateau at all times, see `_search`).

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
py -3 methods/iterated_greedy_vnd_v01/jobs/iterated_greedy_vnd.py \
    data/instances_202605_02/scn_triangle_tight_P5_R5/scn_triangle_tight_P5_R5_seed1.json 10
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
| `4a80e79` | **Revert Commit 6 + full battery snapshot.** Code = Commit 5 (Commits 1–4 behaviour + diagnostics). Ran the full 120-instance heuristic battery seed-first (log `…114558`, self-stamped `4a80e79`), paired against the cached MILP via the new `experiments/paired_report.py` (per-instance MILP-then-heuristic detail) + `gap_summary.py`. | Part II refreshed to this state. Confirms Commit 5 is behaviour-neutral (numbers reproduce Commits 1–4 within run-to-run noise) and documents the definitive comparison: heuristic at/above MILP across R10, wins at scale (R20/R30 MILP timeouts), residuals are noise-level or vs unconverged MILP. |
| `76d43e0` | **Attempt 7 (restart-budget) — KEPT.** Restart loop runs **until the deadline** (`n_starts` now an optional test-only hard cap; per-start slice unchanged). Portfolio slimmed to **NEH + SLACK + `_biased_order`** (rank-biased geometric shuffle, β = 0.3, of the better base); EDD / CR / BLEND / regret-2 retired. Per-start log line only on improvement. See `IMPROVEMENT_LOG.md` Attempt 7 + campaign 2026-07 (Step-0 noise floor: the wMOV R5/R10 stratum is deterministic run-to-run, and the old fixed cap left ~97 % of the budget idle there). | Two-arm ablation (`attempt7_restart_budget_20260713.txt`): **wMOV R5/R10 stratum −3.79 % → 0.00 % = MILP optimum on every cell** (seed5 38→33, seed6 47→39 at delay 0; R10 167.5→166 = MILP); ~850–900 restarts/run vs 8. No guard regressed (control identical; wDLY guards improved; R20 +0.45 % within noise; historical `R5 seed10 wDLY` = 35 = MILP intact). Solver got smaller: −1 knob, −4 rules, +1 mechanism. Part II battery refresh pending. |
| `6952f14` (branch `exp/profile-budget`) → **not merged** | **Attempt 8 (phase policy) — attempted & DROPPED.** 4-arm ablation {both, v2-only, v3-only, profile-split} on the timed-out R10+/R20 stratum to decide one-decoder-vs-two (user's simplification hypothesis). A `phase_mode` knob was built on the branch; no behaviour change ships to `main`. | `attempt8_phase_policy_20260714.txt` + K=3 noise resolution `attempt8b_…txt`: v2-only/split refuted (real wMOV regressions +20/+9.5; chain wMK +2023); v3-only wins some certified-loss seeds (`t_loose_R10 s7` 62.5, beats the MILP's integer-gridded 64.5) but has **real R20 regressions** (+377 wMK, +1933 wDLY — its costly decode leaves too little search per slice). **Two decoders earn their keep.** Side-finding: on the certified-loss cells the search, not the decoder, is the binding constraint — the stay-stretching gap stays the target. |
| `164519a` (merged `5d6fcbc`, tag `igvnd-v01-nest-stretch-20260714`) | **Attempt 9 (nest-stretch) — KEPT.** `_dense_nest_solution` internals generalised from complete-graph waves to the **real blocking DAG**: concentric stay-stretching only along actual front→rear arcs (deepest rear = outermost; finish pass stretches rears around late-starting fronts), unconflicted positions tight/parallel, rounds serialised per component, 4-partition beam (long/short/E/rr). Same gate, same best-of + checker — net machinery 0. | Two-arm ablation (`attempt9_nest_stretch_20260714.txt`): **−120.5 net over 19 wMOV cells, 0 regressions**. `t_loose_R10 s5` 74.5→**63.0** (MILP optimum 61.5), `s7` −4; `full_R10` 258→**235** and 294→**235** (beats MILP 261/322); `chain_R10` 258→**235** (−10.4 %→≈−1.3 %). Part II battery refresh pending for the wMOV columns. |
| `15082a0` (merged, tag `igvnd-v01-perturb-mix-20260714`) | **Attempt 10 (perturb-mix) — KEPT.** IG destruction is now a 50/50 mix of the targeted delay-weighted rule and **uniform-random removal** (+4 lines, 0 knobs): the targeted rule degenerates under wMK/wMOV (delay ≈ 0 ⇒ same longest k every kick), anchoring the walk. | Two-arm ablation (`attempt10_perturb_mix_20260714.txt`): **−438 net**. `t_loose_R10 s7` 77→**62.5** (below the MILP's integer-gridded 64.5 — the solution the Attempt-8 v3-only arm proved existed), `s10` →**67 = MILP**; the certified-loss family is closed (s5 63.0 vs 61.5 remains). Cons: +1.0 real on `two_rows_medium_R10 s2`; wDLY guard +1 delay unit (noise). Part II battery refresh covers Attempts 9+10 together. |
| `62bae48` (merged `1850f0a`, tag `igvnd-v01-mode-a-band`) | **Attempt 11 (Mode-A band alignment) — KEPT.** `_forbidden` and the `_place_front` zero-movement candidates now key off `self.bandA` instead of the fixed `self.eta`: the checker's Mode A requires no clearance at all (touching is vacant), so the old fixed-η geometry searched a strictly smaller space than the relaxed MILP now reaches. The restart loop **alternates** `bandA` per start (even → band 0 = checker-exact; odd → band `eta` = the pre-Attempt-11 geometry) after a band-0-only variant regressed `chain` R10/`wDLY` at scale; `_dense_nest_solution` always builds at band 0; `_decoder_tag` (`v2b`/`v2`) keeps the decode cache disjoint between the two geometries. | Two-arm verdict on the no-Triangle grid (37 configs × 3 profiles × 10 seeds, logs `…20260728_211746` vs `…20260729_155203`+`…232650`): **NET −566,398** objective units (chain −82,022, hub −219,110, two_rows −265,265, none ±0); wMOV near-sweep on chain/two_rows, hub improves at every size; zero consistent regressions (≥7/10 seeds) above the 19-unit noise floor. Part II battery refresh pending (needs a full-battery run under this code state; the verdict above is the two-arm ablation, not the Part II format). |
| `ed5c1e7` | **Merged to `main` — battery of record for Attempt 11 (closes the previous row's pending-refresh note).** No solver-code change (the merge commits, `d209ef6`/`ed5c1e7`, only close out the campaign log and sync this spec); solver behaviour is Attempt 11 as merged at `62bae48`. | Part II refreshed from the dedicated verdict grid — "no-Triangle" (`chain`/`hub`/`two_rows`/`none`, R5–R30, loose/medium/tight, 37 configs × 3 profiles × 10 seeds), log [`outputs/logs/202605_02_main_methods_20260730_103730.log`](../../../outputs/logs/202605_02_main_methods_20260730_103730.log), **1110/1110 runs, 0 failures**: R5 closed on every profile; R10 at-or-above the MILP on `wMK`/`wMOV` across all three topologies; R20/R30 win decisively against the unconverged 60 s MILP. Does not cover `triangle`/`full` (Caveat 3). |
| (doc only) | **Part I aligned with Attempt 11 (user-authorised, 2026-07-31).** Mode A's definition corrected to the problem's true contract (front position vacant *at the access instant*, closed bounds — no `η` margin); the zero-movement regime, `DecodeZeroMov` pseudocode and the nest-stretch wrap description now name `bandA` (0 on even restarts / `η` on odd) instead of a fixed `η`. | no behaviour change (documentation) |
| `3bc423c` (branch `exp/sim-boundaries`, tag `igvnd-v01-sim-boundaries`) | **Attempt 12 (sim-boundaries) — KEPT.** `_sim_front`/`_place_front` boundary semantics aligned with the checker's closed-interval rules: an access landing exactly at the front's own stay start is now pre-classified as Mode A (previously it fell through to the first job's `η`-margin/`κ` checks); the Mode-B gap-batch window moved from open-at-start/closed-at-end to the checker's closed-at-start/open-at-end (`f_j ≤ τ < f_j+window`), so an access exactly at a job's end routes through the gap that follows it, not the next job's interior; `τ` itself (not just `τ ± η`) is now a zero-movement `_place_front` start candidate. Preliminary ablation (18 instances × 3 profiles, `attempt12_ablation_20260902.log`): 24 wins / 26 ties / 4 losses. | see the `8c880ee` row below for the full-grid verdict |
| `8c880ee` | **Merged to `main` — battery of record for Attempt 12.** No further solver-code change (the merge commit closes out the campaign); solver behaviour is Attempt 12 as shipped at `3bc423c`. A fresh two-arm code-vs-code verdict (candidate `3bc423c`, 1110/1110, vs a freshly re-run pre-Attempt-12 baseline, 1110/1110 across four log segments `attempt12_baseline_20260904_*.log`) closed the campaign: **NET −205,368** (chain −161,737, hub −24,486, two_rows −19,146, none 0), zero consistent regressions above the 19-unit noise floor. | Part II refreshed from the candidate battery, log [`outputs/logs/202605_02_main_methods_20260902_214555.log`](../../../outputs/logs/202605_02_main_methods_20260902_214555.log) (self-stamped `3bc423c`), paired against the cached MILP: R5 still closed on every profile; R10 still at-or-above the MILP on `wMK`/`wMOV`; the small-denominator `wDLY` outliers shrink sharply relative to the Attempt-11 battery (`chain_loose_R10` −280 %→−141 %, `chain_tight_R5` −260 %→−25 %, `hub_loose_R10` −191 %→−138 %, `hub_tight_R5` −146 %→−3 %); R20/R30 still win decisively against the unconverged 60 s MILP. Does not cover `triangle`/`full` (Caveat 3). |
| `02a7e38` / `1269c32` (branch `exp/ils-at-scale`) | **Attempt 14 (ils-at-scale) — KEPT.** Diagnosis: at `R ≥ 20` the search barely acted (R20 did 4 restarts, R30 did 3; the eventual best never came from a restart index ≥ 4; one VND confirm pass cost 420–900 evals, more than a whole slice at R20). **14b:** the old exhaustive VND (`_vnd`/`_n_reassign`/`_n_swap_pos`/`_n_reorder`, three exchange sweeps + reset-to-N1) is replaced by an exact-filtered first-improvement local search (`_local_search`/`_critical`/`_order_slots`/`_try_moves`): candidates restricted to the pusher tree under `_decode` (exact — brute force found 0 improving N1/N2 moves in 18/18 cases; a small N3 leak in 3/18, R20 only, accepted), one representative order-slot per distinct-decode class (exact under both decoders). **14a:** `slice_div` drops from 8 to 2 once `R > 10`, so the existing per-restart `bandA` alternation now yields two long half-budget ILS trajectories instead of 3–4 short lottery restarts; the dead "re-centre `cur` to best" rule is retired (the acceptance rule already keeps `cur` on the best plateau). Simplicity ledger: −3 neighbourhood functions, −1 B-VND reset, −1 re-centre rule + its constant, −1 slice-table entry, −1 redundant eval; +4 smaller exact-filter functions; 0 new knobs. Arms on 12 scale cells (`attempt14_arms_20260905.txt`, seeds 1–2): AB (14a+14b) 6 wins / 1 loss / 5 ~ (the pre-registered ≥9/12 bar was not met; user approved proceeding to the full grid anyway, 2026-09-05). | Preliminary arms only; see the `c5f8f99` row below for the full-grid verdict. |
| `7c9090f` / `c5f8f99` | **Merged to `main` — battery of record for Attempt 14.** No further solver-code change (the merge commits close out the campaign); solver behaviour is Attempt 14 as shipped at `1269c32`. A fresh two-arm code-vs-code verdict (candidate `1269c32`, 1110/1110, vs the **reused** Attempt-12 candidate log as baseline, same machine, 3 days earlier, user-approved reuse) closed the campaign: **NET −403,270.5** (chain −258,996, hub −97,318, two_rows −46,957, none 0); 23 consistent wins vs 5 small consistent losses (hub R20 `wMK`/`wMOV` +0.4–0.7 %, `two_rows_loose_R30` `wMOV` +1.29 %) — the "zero consistent regressions" house rule is not strictly met; **kept anyway** (user decision, 2026-09-06: the large MILP-favouring gaps shrank without adding machinery). | Part II refreshed from the candidate battery, log [`outputs/logs/202605_02_main_methods_20260905_203305.log`](../../../outputs/logs/202605_02_main_methods_20260905_203305.log) (self-stamped `1269c32`), paired against the cached MILP: R5 still closed and byte-identical to Attempt 12 (guards exact); R10 essentially unchanged (`hub` byte-identical, `chain`/`two_rows` inside the noise band); R20/R30 tighten further against the unconverged 60 s MILP (mean gaps now +12.5–32.1 % at R20, +14.5–43.5 % at R30). Does not cover `triangle`/`full` (Caveat 3); five small consistent regressions documented in Caveat 5. |
| `c5f8f99` (doc only) | **Part I aligned with Attempt 14 (user-authorised, 2026-09-06, `IMPROVEMENT_LOG.md` Attempt 14).** §5 rewritten from the retired 3-neighbourhood sequential VND with a reset rule to the exact-filtered first-improvement local search (`_local_search`/`_critical`/`_order_slots`/`_try_moves`: pusher-tree candidate filter under the zero-movement decoder, every aircraft under the manoeuvre decoder; reassign / relocate-to-one-representative-slot-per-class / swap-positions moves); §6 drops the dead "restart the walk from the global best after a streak" acceptance rule (better-or-equal acceptance already keeps `cur` on the best plateau); §7 replaces the stale budget/8·/4·/3-by-size slice description with budget/8 for `R ≤ 10` and budget/2 for `R > 10` (two ILS trajectories, one per Mode-A band); the Iterated-Greedy reconstruction bullet now names the exact one-slot-per-class reinsertion. §9's pseudocode (`Search`/`LocalSearch`/`Critical`/`TryMoves`/`OrderSlots`/`Perturb`) rewritten to match. | no behaviour change (documentation) |
| `04fb071` (branch `exp/v3-seed-alternation`) → **not merged** | **Attempt 15 (v3-seed-alternation) — attempted & DROPPED.** Diagnosis: `hub`/`chain_loose_R10` `wDLY`/`wMK` cells often end in `phase=zero` (the v3 polish, seeded from the zero-movement local optimum, never leaves that basin). Hypothesis probed: alternate the v3 seed with the existing per-restart Mode-A band parity — even restarts polish the zero-movement optimum (as today), odd restarts start the manoeuvre search from the construction seed instead. 0 new knobs/functions (+1 conditional on the existing alternation). | Pre-registered probe (14 cells) looked promising (6 better/8 same/0 worse), but the ablation subset (`outputs/logs/attempt15_ablation_20260907.log`, 18 instances × 3 profiles, paired against the battery of record `…_20260905_203305.log`) came back **NET −48.0 over 54 runs (7 wins / 38 ties / 9 losses)**: the loose-R10 `wDLY` gains it targets (e.g. `chain_loose_R10` s5 130.5→82.0) are offset by new losses on `chain_medium/tight_R10` and `hub_tight_R10`/`hub_loose_R30` — trading which restart polishes which basin, not closing the residual — net indistinguishable from the ~72-unit R10 noise floor. **Dropped 2026-09-07** (`IMPROVEMENT_LOG.md` Attempt 15); branch retained, not merged, no code change on `main`. |

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
