# iter_0047_per_access_mode_a — per-access Mode-A in rear resolver

The rebuild rejected configurations where rear span overlaps front span
even if both accesses (entry/exit) are outside the front stay.  The
checker is per-access, so I relaxed the rebuild to match.

Result: triangle_R20 regressed 741.5 → 817.65; all compliant.  The LS
converges to a different (worse) basin under the new semantics — the
old pessimistic check happened to guide LS toward better basins.

**rejected** — reverted to span-based check.
