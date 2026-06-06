# iter_0033_combined_move_delay — combined position-change + idle-gap LS op

Added Op 5: for each aircraft, try (new position, Δ) jointly with Δ ∈ {5, 10, 20, 50}.

Result: triangle_R20 regressed 741.5 → 747.5, chain 181.1 → 183.0. Score +0.0238.
The combined op's R × P × |Δ| = 200 trials/pass crowds out LNS iterations.

**rejected**.
