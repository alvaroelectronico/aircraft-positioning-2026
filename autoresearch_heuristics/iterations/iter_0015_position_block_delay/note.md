# iter_0015_position_block_delay — delay all aircraft at a position simultaneously

## Hypothesis

Delay every aircraft at a position by the same Δ, replicating MILP's
"slot 2 after slot 1" staggering pattern.  Lighter than per-aircraft
because one big move per position, not R individual moves.

## What changed

LS Op 5: for each position with 2+ aircraft, try shifting the LATER
aircraft in the position block by Δ ∈ {5, 20, 50, 100}.

## Eval result

Score +0.0630 (identical to iter_0014).  No movement.

## Outcome

**rejected** — per-aircraft idle-gap (Op 4) already finds whatever
productive delays exist; the position-block constraint is a subset of
what the per-aircraft op can express, so adding it is pure overhead.
