# iter_0016_pair_idle_gap — synchronised idle-gap for aircraft pairs

## Hypothesis

MILP's hub_R10 solution times slot-2 aircraft to start TOGETHER
after the central blocker (R6/P1) clears.  Single-aircraft idle-gap
can't find such moves when each aircraft delayed alone makes
things worse, but the simultaneous pair-delay improves the objective.

## What changed

LS Op 5: for each pair (a, b), try delaying both by the same Δ ∈
{5, 10, 20, 50, 100}.

## Eval result

Score +0.0630 (identical to iter_0014).  Hub_R10 still 145.5.

## Outcome

**rejected** — even paired delays can't find a productive
synchronised slot-2 staggering inside 20 s on hub_R10.  Likely
requires 3+ aircraft delayed together (slot-2 has 4 aircraft on
hub_R10), which the operator can't express.

## Lessons

- Single-aircraft and pair-aircraft delay neighbourhoods are
  exhausted; the residual hub gap needs either a k-aircraft
  simultaneous delay (k=4) or a rebuild that schedules the
  whole position-block atomically.
