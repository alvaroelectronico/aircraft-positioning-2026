# Notes — synthesis, design, experiments log

Working area for the current `theory_assisted` attempt.  Files here
are **private to this method** and may quote `inspiration/` PDFs and
`digest/` notes freely.  They must NOT contain code or descriptions
copied from `methods/manual/`, `methods/autoresearch/`,
`methods/iterated_greedy_vnd_v01/`, or `methods/iterated_greedy_vnd_v02/`.

## What's here at the start of a new attempt

- **`synthesis.md`** — literature synthesis (output of
  `/synthesize-theory`) with the 4 candidate algorithmic approaches
  derived from `digest/`.  Carried over from prior attempts because
  the digests are the same.  **Read it first** — your starting choice
  of algorithmic angle should come from this menu (and Candidate A is
  exhausted; see `../CLAUDE.md`).

## What you write here as you iterate

- **`design.md`** — design rationale for your chosen candidate:
  algorithmic outline, data structures, decoder shape, decision points.
  Start it once you've picked an angle from `synthesis.md`.
- **`experiments_log.md`** — human-readable diary of what you tried,
  what worked, what didn't.  Not a `JOURNAL.md`-style autoresearch
  log — a development diary.
- Any other working notes you want (ablation plans, hyperparameter
  tables, profiling outputs, …).

## Re-running the synthesis

If you decide the existing `synthesis.md` is stale (e.g. you added
new PDFs to `inspiration/` and regenerated `digest/`, or you want a
focus-biased view), invoke:

```
/synthesize-theory                 # general re-synthesis
/synthesize-theory  hyper-heuristic    # bias toward one angle
```

The agent rewrites `synthesis.md` with the new digest content,
rolling the previous version into an archived section at the bottom.
