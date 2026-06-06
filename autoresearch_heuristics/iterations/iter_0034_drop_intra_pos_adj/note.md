# iter_0034_drop_intra_pos_adj — drop Op 3 (intra-pos adjacent swap)

Thought: idle-gap covers within-position timing.  Wrong: removing Op 3
regressed hub_R10 145.5 → 154.5 and triangle_R20 741.5 → 827.3.  Score
+0.0646.

**rejected** — Op 3 finds intra-position reorderings that idle-gap doesn't.
