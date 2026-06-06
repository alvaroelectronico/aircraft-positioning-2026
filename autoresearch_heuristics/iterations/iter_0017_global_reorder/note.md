# iter_0017_global_reorder — LS op that tries EDD / heaviest / blocking-load orderings

## Hypothesis

Current LS only modifies the global scheduling sequence via intra-position
swaps; the global sequence ordering policy (sort by earliest_start) is
fixed.  An LS op that replaces order wholesale with EDD, heaviest-first,
or rear-most-first might let the resolver see the dependency graph
from a different angle.

## What changed

LS Op 5: try four candidate global orderings (EDD, heaviest, rear-most,
front-most).  Accept first improvement.

## Eval result

Score +0.0630 (identical to iter_0014).

## Outcome

**rejected** — no candidate ordering improved on the basin reached by
intra-pos swaps.  The basin is robust to global reordering once the
position assignment is fixed.
