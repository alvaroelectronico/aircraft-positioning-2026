---
name: keep-igvnd-md-in-sync
description: Keep iterated_greedy_vnd.md updated whenever iterated_greedy_vnd.py changes
metadata:
  type: feedback
---

The user wants `methods/iterated_greedy_vnd_v01/jobs/iterated_greedy_vnd.md`
to always document what the heuristic does and stay in sync with
`iterated_greedy_vnd.py`.  Note: v01 is **frozen for algorithmic
comparison** with the upcoming v02 (Claude-assisted) attempt — see
`methods/iterated_greedy_vnd_v01/PROVENANCE.md`.  Only bug fixes and
doc cleanups apply now; do not let the `.md` drift from a `.py` change
that should not have happened in the first place.

**Why:** the `.md` is the human-facing spec of the solver; a stale doc is
worse than none.

**How to apply:** whenever you edit `iterated_greedy_vnd.py` (new
decoder phase, neighbourhood, config knob, behaviour change), update the
matching section of the `.md` in the same change before committing.
Design rationale belongs in [[design]] /
`methods/iterated_greedy_vnd_v01/jobs/design.md`; the `.md` describes
current behaviour, contract, and config.
