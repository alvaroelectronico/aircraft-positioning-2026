---
name: keep-igvnd-md-in-sync
description: Keep iterated_greedy_vnd.md updated whenever iterated_greedy_vnd.py changes
metadata:
  type: feedback
---

The user wants `iterated_greedy_vnd.md` to always document what the
heuristic does and stay in sync with `iterated_greedy_vnd.py` in the
same `jobs/` directory.  Applies to every method that hosts an
`iterated_greedy_vnd.py` — currently
`methods/iterated_greedy_vnd_v01/jobs/` and
`methods/iterated_greedy_vnd_v02/jobs/` (both frozen for
v01-vs-v02 comparison per their PROVENANCE.md; only bug fixes and
doc cleanups apply now).  If a future method also adopts the
`iterated_greedy_vnd` name, the same rule extends to it.

**Why:** the `.md` is the human-facing spec of the solver; a stale doc is
worse than none.

**How to apply:** whenever you edit `iterated_greedy_vnd.py` (new
decoder phase, neighbourhood, config knob, behaviour change), update the
matching section of the `.md` in the same change before committing.
Prefer invoking `/sync-method-doc methods/<the_method>` to refresh
Part IV (code map) automatically.  Design rationale belongs in the
sibling `design.md`; the `.md` describes current behaviour, contract,
and config.
