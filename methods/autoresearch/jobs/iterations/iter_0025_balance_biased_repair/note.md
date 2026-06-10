# iter_0025_balance_biased_repair — weight uniform repair toward less-occupied positions

Idea: instead of uniform sampling, weight positions by (max_count + 1 - count_at_p).
Effect: pulls toward balanced distribution.

Result: score +0.0745 vs iter_0023 +0.0580.  Both chain and triangle_R20 regressed.
Balance-biasing over-emphasizes empty positions even when stacking is optimal.

**rejected**.
