# iter_0037_greedy_heavy_lns — drop topdest, more greedy repair

Replaced topdest mode with another greedy in the 6-mode rotation:
50% greedy, 33% uniform, 17% full restart.  Idea: help full_R10
basin via greedy repair.

Result: triangle_R20 regressed 741.5 → 810.95.  Removing topdest lost the
basin escape it provided.  Score +0.0402.

**rejected**.
