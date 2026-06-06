# iter_0024_blocker_destroy — destroy aircraft at highest-blocking-load position

## Hypothesis

Chain/hub topologies have a single position (P1) that blocks every
other position.  Destroying every aircraft there forces re-thinking
the choke point.

## Eval result

chain_R10 regressed 198.80 → 205.15.  Score +0.0677 (worse than
iter_0023's +0.0580).

## Outcome

**rejected** — the 7-mode rotation dilutes the productive modes too
much.  Blocker destroy is effectively the same as topdest mode for
chain (P1 is both highest-blocking AND most-populated), so adding it
is pure overhead that crowds out random+greedy.
