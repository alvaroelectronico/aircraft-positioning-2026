# Provenance — `brkga_v02`

## Summary

- **Version:** v02 (Claude-assisted, Candidate C of the synthesis).
- **Task:** produce a heuristic for paper #2 (job-level extension)
  through the `theory_assisted` literature-informed process, picking
  a **different candidate** from the ones already exhausted by v01
  and the IGVND-Claude attempt (both implemented Candidate A).
- **Human role:** curator of inspiration, decision-maker on design,
  developer driving the iteration loop.
- **LLM assistance:** **Claude** (Anthropic) as coding assistant.
  Used for code drafts, decoder feasibility analysis, BRKGA engine
  implementation, debugging, and ablation discussion.
- **Starting commit on top of the theory_assisted scaffold:**
  `2d37eeb` (*"v06: initial BRKGA implementation"*).  Before that
  the scaffold held a `NotImplementedError` stub plus the same
  `inspiration/` + `digest/` + `synthesis.md` that v01 / v02 had
  consumed.
- **Graduation:** this commit (moves the matured method out of the
  `theory_assisted/` scaffold to its own isolated directory and
  resets the scaffold for the next attempt).

## Why this record exists

The repository compares independent attacks on the same problem.
v01 (ChatGPT) and v02 (Claude) both implemented Candidate A (IG+VND);
this method implements Candidate C (BRKGA with mixed-chromosome
decoder), giving cross-candidate comparison **within the same LLM
assistant (Claude)** alongside the cross-assistant comparison
(v01 vs v02).

Documenting this lets us later ask:

- How does an evolutionary / population-based approach compare to a
  single-solution metaheuristic (IG+VND) on the same benchmark,
  with the same developer and the same LLM?
- Where does the BRKGA decoder shine, where does it struggle?
- Did the development path differ in time-to-first-working-solver,
  failed branches, or operator choices?

brkga_v02 is **frozen** as a reference once it graduates: further
edits to this method's `.py` / `.md` should be limited to bug fixes
and documentation cleanups, not algorithmic changes, so the
comparison remains apples-to-apples.

## Development history (high level)

The detailed commit history is the authoritative record; this is a
high-level recap of the brkga_v02 trajectory.

1. **v06 — initial BRKGA implementation** (commit `2d37eeb`).
   Decoder (`decoder.py`), BRKGA engine (`brkga.py`), solver wrapper
   (`brkga.py`).  Mixed-chromosome encoding (indicator
   keys for assignment + permutation keys for sequencing).  Mode-A
   + Mode-B decoder (zero-movement and inter-job-gap moves);
   no Mode-C in v1.  Registered as `ta_brkga_wMK/wDLY/wMOV` in
   `experiments/run_experiments.py`.  360/360 feasible on the
   battery; loses to MILP on R5–R10, wins only on unconverged-MILP
   R30.
2. **v06 decoder v2 — Mode-C via κ fixpoint** (commit `22c65fb`).
   `DecoderContext` gains `allow_mode_c` and `max_fixpoint_iters`;
   `decode()` runs a fixpoint of `_decode_pass` until `kappa`
   stabilises (fallback to Mode-A/B-only if not converged in 8
   iters).  wMK / wDLY improve substantially (chain_R10 wMK
   −45.8% → −18.5%, triangle_R5 wDLY −1322% → −3.2%).  wMOV
   regresses on large R due to decode-cost starvation
   (full_R20 −42% → −120%).
3. **v06 P1 — profile-gated Mode-C** (commit `bab9773`).  Mode C is
   enabled only when the movement weight does not dominate
   (`weight_movements <= max(weight_makespan, weight_delay)`).
   Eliminates the wMOV regression while keeping the wMK / wDLY
   gains.  Explicit `allow_mode_c` config overrides the gate for
   ablations.
4. **v06 P2 — enforce wall-clock budget inside `score_pop`**
   (commit `748c0a8`).  Fixes the 72–81 s overrun on R20 / R30
   from the fixpoint decode; numbers refreshed by a guarded
   re-battery, all within the 60 s budget.
5. **Graduation** (this commit).  Moves the matured method out of
   the `theory_assisted/` scaffold to `methods/brkga_v02/` and
   resets the scaffold for the next attempt (Candidates B and D
   remain).

For the per-commit detail (sub-versions, what changed, what
improved), see the Change log section of
[`jobs/brkga.md`](jobs/brkga.md).

## What stays in scope for further edits

While brkga_v02 is frozen for algorithmic comparison, the following
are acceptable:

- Bug fixes that affect correctness against `problems/jobs/checker.py`.
- Documentation cleanups (`.md` files, comments).
- Path / import maintenance if the surrounding repo structure changes.
- Performance fixes that don't change algorithmic behaviour
  (caching, dtype, allocation patterns).

What is **out of scope**:

- New decoder modes, GA operators, or hyperparameter retuning.
- Any algorithmic change motivated by a comparison with v01, v02, or
  a future v03's results.
