# Provenance — `iterated_greedy_vnd_v01`

## Summary

- **Version:** v01.
- **Task:** produce a heuristic for paper #2 (job-level extension)
  through the `theory_assisted` literature-informed process.
- **Human role:** curator of inspiration, decision-maker on design,
  developer driving the iteration loop.
- **LLM assistance:** **ChatGPT** (GPT-4-class model) as coding
  assistant.  Used for code drafts, refactors, design discussion, and
  algorithm tuning suggestions.
- **First working version:** commit `30e1af0` (2026-06-12),
  *"theory_assisted: implement Candidate A (Iterated Greedy + VND)"*.
  Before that the file was a `NotImplementedError` stub.

## Why this record exists

The repository is designed to compare independent attacks on the same
problem.  v01 was built with a particular LLM assistant (ChatGPT) on a
particular set of curated theory.  A second attempt (**v02**) is now
beginning on the **same theory_assisted scaffold** — same problem
statement, same `inspiration/` and `digest/` folders — but with
**Claude** as the LLM assistant instead of ChatGPT.

Documenting this here lets us, later, ask cleanly:

- Did the two assistants converge on similar algorithmic ideas, or
  diverge?
- Did one produce a better solver than the other under the same
  benchmark (`outputs/solutions/results.csv`)?
- Did the development paths differ in iteration count, dead ends,
  time-to-first-working-solver?

v01 is **frozen** as a reference once v02 starts: further edits to
this method's `.py`/`.md` should be limited to bug fixes and
documentation cleanups, not algorithmic changes, so the comparison
remains apples-to-apples.

## Development history (high level)

The detailed commit history is the authoritative record; this is a
high-level recap:

1. **Scaffolding** (commit history pre-`30e1af0`): the
   `theory_assisted` scaffold was created and the human curated
   ~11 PDFs into `methods/theory_assisted/inspiration/`, then ran
   `/digest-paper` on each to produce the 10 digests in
   `methods/theory_assisted/digest/`.
2. **Synthesis** (also pre-`30e1af0`): the human invoked
   `/synthesize-theory` to produce `synthesis.md` proposing 2–4
   candidate approaches.  Candidate A (Iterated Greedy + VND) was
   selected.
3. **First implementation** (`30e1af0`): the human + ChatGPT
   implemented Candidate A — NEH-style construction with a decoder
   that places the rear aircraft before / after / *enclosing* the
   front (Mode A only, zero movements by construction), plus a
   sequential B-VND over reassign / swap-position / reorder
   neighbourhoods, plus an Iterated-Greedy worst-aircraft
   destruction / reconstruction loop.
4. **Iteration sprint** (subsequent commits, ending around mid-June):
   diagnostic logging, ablations, decode cache, construction
   portfolio with regret-2, variance reduction via adaptive
   multi-start, dense nesting (commit 4), risk diagnostics
   (commit 5), DelayRiskRepair (commit 6 — reverted, no benefit).
5. **Graduation** (commit `6a0b1f7`): the method moved out of the
   `theory_assisted` scaffold to its own directory
   `methods/iterated_greedy_vnd/`, and the `theory_assisted` scaffold
   was reset for the next attempt.
6. **Versioning** (this commit): directory renamed to
   `methods/iterated_greedy_vnd_v01/` and this file added, in
   preparation for the v02 (Claude-assisted) attempt.

## What stays in scope for further edits

While v01 is frozen for algorithmic comparison, the following are
acceptable:

- Bug fixes that affect correctness against `problems/jobs/checker.py`.
- Documentation cleanups (`.md` files, comments).
- Path / import maintenance if the surrounding repo structure changes.
- Performance fixes that don't change algorithmic behaviour
  (caching, dtype, allocation patterns).

What is **out of scope**:

- New neighbourhoods, operators, or construction strategies.
- Re-tuning hyperparameters based on new ablations.
- Any algorithmic change motivated by v02's results.
