# Aircraft positioning — comparison of solving methods

This repository compares different solving methods for two scheduling
problems on shared aircraft-positioning resources:

- **Paper #1 (aircraft-level):** atomic resource requests `D_r`; objective
  combines makespan, total delay, and topology movements.
- **Paper #2 (job-level extension):** each request decomposes into jobs
  `J(r)` with three modes (A continuous, B partial-overlap, C interruptible)
  and per-mode access semantics.

The point of the layout below is to make it possible to add a new solving
method (hand-coded or LLM-driven) **without seeing how existing methods
solved the problem**.  A new method consumes only the self-contained
problem statement, the schema, the loader, and the checker — never another
method's source or the papers that document the formulation history.

## Layout

```
problems/                # What a method is allowed to know.
  aircraft/              # Paper #1.
    problem_statement.md     # self-contained spec; the ONLY background
    instance_schema.json     # JSON schema for instances
    checker.py               # feasibility / metric checker
    instances/               # scn_*/scn_*_seed{N}.json
  jobs/                  # Paper #2.
    problem_statement.md
    instance_schema.json
    checker.py
    instances/

shared/                  # Cross-method, cross-problem infrastructure.
  application.py             # the Application dispatcher (solver contract)
  instance_io.py             # JSON loader (single canonical, both papers)
  rcl.py                     # GRASP RCL helpers
  plotting.py                # Gantt-chart plotting

methods/                 # ONE subtree per solving approach. ISOLATED.
  manual/                # hand-coded MILPs + heuristics (FAS, TGR, LNS, …)
    aircraft/                # paper #1 manual code + docs/
    jobs/                    # paper #2 manual code + docs/
  autoresearch/          # LLM-iterative loop (snapshot + evaluate harness)
    aircraft/                # (placeholder — no autoresearch yet)
    jobs/                    # paper #2 autoresearch (only one done so far)
  theory_assisted/       # literature-informed, clean-room implementation
    jobs/                    # paper #2 (the only scope so far)

experiments/             # Cross-method orchestration; imports any method.
  run_experiments.py         # batch runner (the bridge across methods)
  tests/                     # incl. test_method_isolation.py

outputs/                 # All solver outputs.
  solutions/                 # per-run JSONs + results.csv
  logs/                      # batch logs
  logs_heuristic/

papers/                  # Publishable manuscripts. Not on any read path.
  cejor_aircraft/            # paper #1 draft
  jobs_extension/            # paper #2 draft
  _legacy_draft/             # superseded earlier drafts (archive)

literature_review/       # Bibliography + external papers (reference only).
```

## Isolation contract

| From                                | May read `problems/<paper>/` | May read `shared/` | May read `methods/<other>/` | May read `papers/` |
| ----------------------------------- | :--: | :--: | :----------------------------------: | :--: |
| `methods/<X>/`                      |  ✅  |  ✅  | ❌ (allowlist: see isolation test)   |  ❌  |
| `experiments/`                      |  ✅  |  ✅  |  ✅                                  |  ❌  |
| `papers/<paper>/` (manuscript build)|  ✅  |  —  |  ❌                                  |  ✅  |

The single documented exception is
`methods/autoresearch/jobs/precompute_baseline.py`, which imports the
manual MILP because the autoresearch loop's score is defined as
`(variant_obj − milp_obj) / max(1, |milp_obj|)`.  The exception is
allowlisted explicitly in `experiments/tests/test_method_isolation.py`.

Run the contract:

```
py -3 experiments/tests/test_method_isolation.py
```

## How to add a new method

1. Create `methods/<your_method>/<paper>/` (where `<paper>` is
   `aircraft` or `jobs`).
2. Read `problems/<paper>/problem_statement.md`.  That is the entire
   permitted briefing.  Do not read `papers/`, `literature_review/`,
   or any other `methods/<X>/`.
3. Implement the solver contract from `shared/application.py`
   (`configure_solver`, `solve(instance) -> {objective, metrics,
   schedule, status}`).
4. Add an entry to `experiments/run_experiments.py` so the batch runner
   can dispatch your method against the benchmark.
5. `py -3 experiments/tests/test_method_isolation.py` must pass.

## Running things

Paper #1, one instance, the manual MILP baseline:

```
py -3 experiments/run_experiments.py "scn_triangle_tight_P5_R5_seed1$" \
    "milp_baseline" problems/aircraft/instances
```

Paper #2, the manual MILP + the autoresearch heuristic on the same
instance:

```
py -3 experiments/run_experiments.py "scn_triangle_tight_P5_R5_seed1$" \
    "milp_baseline_job,topology_ms6_job_ar" problems/jobs/instances
```

Score the autoresearch working copy of `topology_heuristic_job.py`
against its MILP baseline:

```
py -3 methods/autoresearch/jobs/evaluate.py fast_eval
```
