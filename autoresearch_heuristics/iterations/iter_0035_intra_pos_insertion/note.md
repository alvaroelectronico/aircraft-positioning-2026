# iter_0035_intra_pos_insertion — add intra-pos insertion as Op 5

Added LS Op 5: pop each same-position aircraft and reinsert at every other slot.

Result: triangle_R20 regressed 741.5 → 752.65, score +0.0225 (worse than iter_0029's +0.0191).
Adding ops keeps diluting LNS budget.

**rejected** — iter_0029's 4-op LS is the sweet spot.
