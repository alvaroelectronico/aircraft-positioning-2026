# `theory_assisted` — method overview

A solving method whose defining input is the **external scheduling and
OR literature** in `literature_review/`.  The method does not see how
`manual/` or `autoresearch/` solved the same problem — it must produce
its own approach from first principles + published research.

## Reading list (the ONLY background to consume)

| Path                                       | Purpose                                            |
| ------------------------------------------ | -------------------------------------------------- |
| `problems/jobs/problem_statement.md`       | Self-contained spec of paper #2.                  |
| `problems/jobs/checker.py`                 | Source of truth for feasibility / metrics.        |
| `problems/jobs/instance_schema.json`       | JSON instance format.                              |
| `shared/application.py`                    | Solver contract (`configure_solver`, `solve`).    |
| `shared/instance_io.py`, `shared/rcl.py`   | Loader + RCL helpers (no method-specific bias).   |
| `literature_review/papers/*.pdf`           | External literature — the defining input.         |
| `literature_review/report_consensus.txt`   | Curated overview of how the papers relate.        |

## Forbidden (enforced by the isolation test)

- `methods/manual/**`
- `methods/autoresearch/**`
- `papers/**` (publishable manuscripts of OUR work)

See `CLAUDE.md` for the full rationale and the protocol if you need an
exception.

## How to start

1. Read `problems/jobs/problem_statement.md` end-to-end.  This is the
   complete brief — no other internal docs.
2. Skim `literature_review/report_consensus.txt` to map the literature.
   Then digest the 2–4 papers that look most applicable using the
   project skill (it runs the `theory-paper-digest` subagent and writes
   to `methods/theory_assisted/jobs/notes/literature_digest/`):
   ```
   /digest-paper literature_review/papers/qin2019.pdf
   /digest-paper literature_review/papers/festa2008.pdf  GRASP construction
   ```
   Take any cross-paper synthesis or design sketches under
   `methods/theory_assisted/jobs/notes/`.
3. Sketch a design.  Put it in `methods/theory_assisted/jobs/notes/design.md`.
4. Implement in `methods/theory_assisted/jobs/theory_assisted_job.py`.
   Keep the class name `TheoryAssistedJobSolver` and the contract from
   `shared/application.py`.
5. Register a label in `experiments/run_experiments.py` so the batch
   runner can dispatch your method against the benchmark.
6. Run the isolation test:
   ```
   py -3 experiments/tests/test_method_isolation.py
   ```
   Must report `0 violations`.
7. Run a smoke test:
   ```
   py -3 experiments/run_experiments.py "scn_triangle_tight_P5_R5_seed1$" \
       "<your_label>" problems/jobs/instances
   ```

## Comparing against other methods (after implementation)

Do this through `outputs/solutions/results.csv` only — never by reading
other methods' source.  The CSV has one row per (instance, method) run
and is the right place to see the relative quality of approaches.
