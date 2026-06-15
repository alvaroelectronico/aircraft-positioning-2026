# `theory_assisted` — method overview

A solving method whose defining input is the **external scheduling and
OR theory** that the human curates into `inspiration/`.  The method
does not see how any other method (`manual/`, `autoresearch/`,
`iterated_greedy_vnd/`, …) solved the same problem, and it does NOT
consume the repo-wide `literature_review/` either — only the curated
`inspiration/` folder.  This is on purpose: each method owns its own
diet of inputs.

This is a **template scaffold**: `digest/` and `inspiration/` carry
reusable theory from prior attempts; everything else is reset to the
starting state so a new attempt can begin from scratch without seeing
any previous method's code.

## Reading list (the ONLY background to consume)

| Path                                              | Purpose                                            |
| ------------------------------------------------- | -------------------------------------------------- |
| `problems/jobs/problem_statement.md`              | Self-contained spec of paper #2.                  |
| `problems/jobs/checker.py`                        | Source of truth for feasibility / metrics.        |
| `problems/jobs/instance_schema.json`              | JSON instance format.                              |
| `shared/application.py`                           | Solver contract (`configure_solver`, `solve`).    |
| `shared/instance_io.py`, `shared/rcl.py`          | Loader + RCL helpers (no method-specific bias).   |
| `methods/theory_assisted/inspiration/`            | Curated theory input (PDFs etc.) — defining input.|
| `methods/theory_assisted/digest/`                 | Structured digests of `inspiration/` sources.     |

## Forbidden (enforced by the isolation test + the per-method CLAUDE.md)

- `literature_review/**` (the repo-wide bucket is NOT this method's
  input; copy a paper into `inspiration/` to bring it in scope)
- `methods/manual/**`
- `methods/autoresearch/**`
- `methods/iterated_greedy_vnd_v01/**` (the previous theory_assisted
  attempt — graduated to its own method, off this read path)
- `papers/**` (publishable manuscripts of OUR work)

See `CLAUDE.md` for the full rationale and the protocol if you need an
exception.

## How to start

1. Read `problems/jobs/problem_statement.md` end-to-end.  This is the
   complete brief — no other internal docs.
2. Curate `methods/theory_assisted/inspiration/` with the PDFs (and
   any other material) you want this method to consume.  Then digest
   each source with the project skill — it forks the
   `theory-paper-digest` subagent and writes to
   `methods/theory_assisted/digest/`:
   ```
   /digest-paper methods/theory_assisted/inspiration/qin2019.pdf
   /digest-paper methods/theory_assisted/inspiration/festa2008.pdf  GRASP construction
   ```
3. Synthesise across digests with the project skill — it forks the
   `theory-synthesize` subagent and writes
   `methods/theory_assisted/jobs/notes/synthesis.md` with convergent
   themes, distinct angles and 2–4 concrete candidate approaches:
   ```
   /synthesize-theory
   /synthesize-theory  GRASP-heavy   # bias the candidates toward one angle
   ```
4. Pick ONE candidate from the synthesis and develop it in
   `methods/theory_assisted/jobs/notes/design.md` (normal Claude
   session, no extra agent — by this point the design.md is concrete
   enough that regular coding workflow takes over).
5. Implement in `methods/theory_assisted/jobs/theory_assisted_job.py`.
   Keep the class name `TheoryAssistedJobSolver` and the contract from
   `shared/application.py`.
6. Register a label in `experiments/run_experiments.py` so the batch
   runner can dispatch your method against the benchmark.
7. Run the isolation test:
   ```
   py -3 experiments/tests/test_method_isolation.py
   ```
   Must report `0 violations`.
8. Run a smoke test:
   ```
   py -3 experiments/run_experiments.py "scn_triangle_tight_P5_R5_seed1$" \
       "<your_label>" problems/jobs/instances
   ```

## Comparing against other methods (after implementation)

Do this through `outputs/solutions/results.csv` only — never by reading
other methods' source.  The CSV has one row per (instance, method) run
and is the right place to see the relative quality of approaches.
