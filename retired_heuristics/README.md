# Retired heuristic attempts

Inert archive of the solving-method attempts that were **discarded** when the
repo refocused (2026-07-13) on improving `methods/iterated_greedy_vnd_v01/`
alone. They are kept for the record — nothing here is imported, run, or
maintained; the experiment runner's guarded loaders resolve them to `None`
and skip their entries automatically.

| folder | what it was | why retired |
| --- | --- | --- |
| `iterated_greedy_vnd_v02/` | Claude-assisted sister attempt of the IG+VND method, from the same scaffold baseline | never surpassed v01; the v01-vs-v02 comparison era ended with the refocus |
| `brkga_v02/` | BRKGA decoder attempt (Candidate C of the theory synthesis) | tied the MILP baseline on smoke tests but never beat v01 |
| `theory_assisted/` | the literature-digestion scaffold (paper digests, synthesis, and its own solver attempts, incl. a 2nd BRKGA try) | its useful output was distilled into v01's `design.md` / `synthesis.md`; the scaffold itself is superseded |
| `autoresearch/` | earliest automated-research attempt (incl. `precompute_baseline.py`) | superseded by everything above |

History and provenance:

- The **full pre-refocus tree** (these methods still in place under
  `methods/`, plus the aircraft-level problem) is preserved on the branch
  `archive/pre-restructure-20260713`.
- The return-point snapshots are the tags `igvnd-v01-baseline-20260713`
  (start of the improvement campaign) and the per-milestone
  `igvnd-v01-<milestone>` tags.
- The active method's improvement history — including *why* each of these
  directions lost — is in
  [`methods/iterated_greedy_vnd_v01/IMPROVEMENT_LOG.md`](../methods/iterated_greedy_vnd_v01/IMPROVEMENT_LOG.md).

Do not resurrect code from here into the active method without opening an
`exp/<slug>` attempt in that journal first.
