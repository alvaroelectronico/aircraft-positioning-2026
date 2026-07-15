# iter_0039_conflict_targeted_idle_gap — compute Δ from front-finish times

Added Op 5: for each aircraft a, find the latest front-aircraft finish
that could block a, set Δ_a so a starts exactly when that front clears.

Score +0.0191 (same as iter_0029).  The fixed Δ grid in Op 4 already finds
these specific values (eta=1 and finishes round to integers).

**rejected** — no marginal improvement.
