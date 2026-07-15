# Provenance — `iterated_greedy_vnd_v02`

## Summary

- **Version:** v02.
- **Task:** produce a heuristic for paper #2 (job-level extension)
  through the `theory_assisted` literature-informed process, starting
  from the **same baseline as v01** (commit `30e1af0`).
- **Human role:** curator of inspiration, decision-maker on design,
  developer driving the iteration loop.
- **LLM assistance:** **Claude** (Anthropic) as coding assistant.
  Used for code drafts, refactors, design discussion, debugging, and
  algorithm tuning suggestions.
- **Starting commit:** the v02 baseline was restored from `30e1af0`
  into `methods/theory_assisted/jobs/iterated_greedy_vnd.py` at commit
  `6b7e769` (tag `v02-start`).
- **First behaviour-affecting commit on top of the baseline:**
  `56fab0c` (*"theory_assisted v02: manoeuvre-spending decoder
  (Mode-C + kappa fixpoint)"*) — this was where v02 began diverging
  from v01's `DecodeZeroMov`-only world.
- **Graduation:** this commit (moves the matured method out of the
  `theory_assisted/` scaffold to its own isolated directory and
  resets the scaffold for the next attempt).

## Why this record exists

The repository compares independent attacks on the same problem
through the lens of which LLM assistant the developer worked with.
v01 (ChatGPT) and v02 (Claude) iterated from **the same baseline**
(commit `30e1af0`, the first working IGVND impl, restored at tag
`v02-start`) under the **same scaffold** (`theory_assisted/` with
identical `inspiration/` PDFs and `digest/` notes).

Documenting this here lets us later ask:

- Did the two assistants converge on similar algorithmic ideas, or
  diverge?  Where did v02 go that v01 didn't, and vice-versa?
- Did one produce a better solver under the same benchmark
  (`outputs/solutions/results.csv`)?
- Did the development paths differ in iteration count, dead ends,
  time-to-first-working-solver?

v02 is **frozen** as a reference once it graduates: further edits to
this method's `.py` / `.md` should be limited to bug fixes and
documentation cleanups, not algorithmic changes, so the comparison
remains apples-to-apples.

## Development history (high level)

The detailed commit history is the authoritative record; this is a
high-level recap of the v02 trajectory.  Sub-versions referenced
match the `.py` docstring's internal version numbering.

1. **v02 — manoeuvre-spending decoder** (commit `56fab0c`).  Added
   `_decode_man`: a Mode-C / κ-fixpoint forward simulator that lets a
   rear aircraft cross a front-aircraft interruptible job, paying for
   it with a movement and a κ-increment.  v01's `DecodeZeroMov` floor
   was kept as a safety net under best-of + checker.
2. **v03 — Mode-B inter-job gaps** (commit `bcb71dd`).  Extended the
   decoder to open Mode-B gaps between front jobs, so a rear access
   can pass through a non-interruptible job by towing the front aside.
   Includes a staged fixpoint to converge the κ counters with the
   gap sizes.
3. **v03.1 — interval caching** (commit `366373a`).  Decode-speed
   refactor: cached forbidden intervals across small changes to the
   schedule.  Identical results; faster search throughput.
4. **Strict 60 s deadline** (commit `0ccd333`).  Enforced
   `time_limit_s` deep inside the search loops (construction, VND
   scans, IG reinsertion) so R20 / R30 runs return within budget.
5. **v04 — light-objective decode path** (commit `f0b5e6a`).  Added
   a fast decode mode used inside VND neighbourhood scans (computes
   only the bound needed for accept/reject, not the full solution).
   +28-49% search throughput.
6. **v05 — incremental zero-decode in the VND** (commit `7f53652`).
   Reuses partial decode state across neighbour evaluations.
   +14-17% search iterations per unit time.
7. **Full battery snapshot** (commit `2b9ae94`).  Part II of the
   living doc refreshed against the cached MILP; method declared
   quality-saturated at 60 s budget on this benchmark.
8. **Graduation** (this commit).  Moves the matured method out of the
   `theory_assisted/` scaffold to `methods/iterated_greedy_vnd_v02/`
   and resets the scaffold for the next attempt.

For the per-commit detail (sub-versions, what changed, what
improved), see the Change log section of
[`jobs/iterated_greedy_vnd.md`](jobs/iterated_greedy_vnd.md).

## What stays in scope for further edits

While v02 is frozen for algorithmic comparison, the following are
acceptable:

- Bug fixes that affect correctness against `problems/jobs/checker.py`.
- Documentation cleanups (`.md` files, comments).
- Path / import maintenance if the surrounding repo structure changes.
- Performance fixes that don't change algorithmic behaviour
  (caching, dtype, allocation patterns).

What is **out of scope**:

- New neighbourhoods, operators, or construction strategies.
- Re-tuning hyperparameters based on new ablations.
- Any algorithmic change motivated by a comparison with v01 or with a
  future v03's results.
