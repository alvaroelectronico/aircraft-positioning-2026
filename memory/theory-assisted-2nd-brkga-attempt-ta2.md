---
name: theory-assisted-2nd-brkga-attempt-ta2
description: theory_assisted is now a FRESH 2nd isolated Candidate-C (BRKGA) attempt, labels ta2_brkga_*, distinct from v06/brkga_v02 history
metadata:
  type: project
---

As of 2026-06-22, `methods/theory_assisted/` is a **clean scaffold for a SECOND
independent Claude-assisted attempt at Candidate C (BRKGA)**, built from scratch
in isolation from `methods/brkga_v02/` (the experimental goal is replication:
how much do two attempts diverge). Solver `jobs/theory_assisted_job.py`
(`TheoryAssistedJobSolver`), logic under `jobs/brkga/`, registered as
`TheoryAssistedBRKGA2` / labels `ta2_brkga_wMK|wDLY|wMOV`.

Current state: decoder **v0 (Mode-A only)**, contiguous jobs, own deterministic
BRKGA loop, greedy/NEH warm-start. 100% checker-compliant; worse than the MILP
on blocking-heavy instances (expected — no Mode B/C yet). Roadmap: Mode-B gaps
→ restricted Mode-C → multi-seed battery.

**Why this matters / how to apply:** the older memories
[[theory-assisted-v06-candidate-c-brkga]] and
[[theory-assisted-v02-manoeuvre-decoder]] describe the PRIOR attempt that
graduated to `methods/brkga_v02/` and `methods/iterated_greedy_vnd_v02/` — they
are NOT this code. `/sync-method-doc` once pulled that stale history into this
method's `.md` (invented profile-gated Mode-C, a κ-fixpoint, commits
748c0a8/f7fc536/0e2608e, a "worse than brkga_v02" comparison) — none exist here.
**Always verify the generated `.md` against the actual `brkga/` code**; this
attempt has no Mode C, no fixpoint, no profile gate, and compares against the
cached MILP, not brkga_v02.
