# iter_0064_pair_idle_gap_v2 — pair idle-gap under per-access rebuild

Re-tried pair idle-gap from iter_0016, now with per-access rebuild.
Hub regressed 136.75 → 154.8.  Even with the better rebuild, pair op
consumes LS budget that hub needs.

**rejected** — reverted via snapshot.py.
