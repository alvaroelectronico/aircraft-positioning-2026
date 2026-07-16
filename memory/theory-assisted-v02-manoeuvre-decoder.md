---
name: theory-assisted-v02-manoeuvre-decoder
description: theory_assisted v02 iteration goal — manoeuvre-spending decoder and the three target weight profiles
metadata:
  type: project
---

The `theory_assisted` method (paper #2 / jobs) is the Claude-assisted v02
attempt, iterating from the same IGVND baseline as the frozen ChatGPT v01
(see [[keep-igvnd-md-in-sync]]).  Worked on 2026-06-15.

**v02 goal (decided by Claude, delegated by the user):** evolve the v01
*zero-movement* decoder into one that **can spend Mode-C manoeuvres** (the
κ-fixpoint the old design.md anticipated as "v3").  Implemented in
`methods/theory_assisted/jobs/iterated_greedy_vnd.py` as `_decode_man`
(forward list-scheduler + κ fixpoint) behind a dispatcher that returns
`min(zero, man)` per (assignment, order), plus a two-phase search (fast
zero-movement phase A, then manoeuvres ON in phase B) so the slow decoder
does not starve the search on large instances.

**Target weight profiles (W^M, W^D, W^S) — the user fixed these three:**
`(100,1,1)` makespan-priority, `(1,100,1)` delay-priority, `(1,1,100)`
movement-priority.  NOT the benchmark default `(0.1,1,10)`.  Key fact:
under default weights even the MILP picks 0 movements, so manoeuvres only
pay on the makespan/delay-priority profiles; under `(1,1,100)` the
zero-movement decode is already optimal on the movement term.

**Why:** the objective on larger instances is dominated by *delay*, and the
v01 decoder could never trade a manoeuvre to overlap aircraft in time.

**How to apply:** keep `_decode` dominant over v01 (never worse on any
(a,o)); validate every change against `problems/jobs/checker.py` (0
violations) across the three profiles before committing; run the isolation
test `py -3 experiments/tests/test_method_isolation.py`.  Do not read
`methods/iterated_greedy_vnd_v01/**` — contract in CLAUDE.md.
