# iter_0058_engulfing_front_resolver — front resolver tries engulfing

Added option: F_s = rear.start + eta (engulfing front) when rear is
long enough to engulf.  Picks smallest feasible F_s.

Result: hub regressed 136.75 → 143.95, triangle_R20 690.05 → 697.05.
The engulfing-front pattern fires but downstream cascade is worse than
push-past-rear for these instances.  Reverted to iter_0054 front
resolver (per-access push only).

**rejected**.
