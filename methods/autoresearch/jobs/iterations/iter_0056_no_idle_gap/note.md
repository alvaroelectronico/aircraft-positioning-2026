# iter_0056_no_idle_gap — drop idle-gap LS under new per-access rebuild

Guess: rebuild picks optimal tau_in itself, so LS idle-gap is redundant.
Reality: hub regressed 136.75 → 154.8. The LS idle-gap still pushes
aircraft into Δ regions the rebuild candidate scan doesn't reach
(specific override values force different timing patterns).

**rejected**.
