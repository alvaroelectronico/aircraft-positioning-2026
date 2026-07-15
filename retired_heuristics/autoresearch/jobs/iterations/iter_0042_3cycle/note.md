# iter_0042_3cycle — add 3-cycle position rotation LS op

O(R³) trials per pass.  For R=20 that's 8000 rebuilds per LS pass,
starving LNS of budget.  hub_R10 regressed 145.5 → 157.7, triangle_R20
741.5 → 840.65.  Score +0.0716.

**rejected** — too expensive per LS pass to be productive.
