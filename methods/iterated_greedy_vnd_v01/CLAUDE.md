# Isolation contract for the `iterated_greedy_vnd_v01` method

You are working inside `methods/iterated_greedy_vnd_v01/`.  This is the
v01 attempt at paper #2 via the `theory_assisted` scaffold, built with
ChatGPT assistance (see [`PROVENANCE.md`](PROVENANCE.md)).  It is
**frozen for algorithmic comparison** with the in-progress v02
(Claude-assisted) attempt — only bug fixes, doc cleanups, and
non-algorithmic perf tweaks are in scope (see PROVENANCE for the full
freeze policy).

It is **developed in isolation** from the other methods in the
repository, even though it originated from a `theory_assisted` process
— the theoretical work is captured in `jobs/synthesis.md` +
`jobs/design.md` right here.

## You MAY read, freely

- `methods/iterated_greedy_vnd_v01/**` — this method's own code, docs,
  synthesis, design.
- `problems/jobs/**` — problem statement, schema, checker, instances.
  `problems/jobs/problem_statement.md` is the full self-contained brief;
  `problems/jobs/checker.py` is the source of truth for feasibility.
- `shared/**` — Application dispatcher contract, instance_io, plotting,
  RCL helpers.
- `experiments/run_experiments.py` — the integration point (the
  `igvnd_wMK` / `igvnd_wDLY` / `igvnd_wMOV` labels live there).

## You MUST NOT read

- `methods/manual/**`               (other method)
- `methods/autoresearch/**`         (other method)
- `methods/theory_assisted/**`      (the literature-informed process
                                     that birthed this method has
                                     already been distilled into
                                     synthesis.md + design.md in
                                     this tree; the original digest/
                                     and inspiration/ folders are
                                     reusable theory reserved for
                                     FUTURE method attempts)
- `papers/cejor_aircraft/**`, `papers/jobs_extension/**`,
  `papers/_legacy_draft/**`        (publishable manuscripts of OUR work)
- `literature_review/**`           (repo-wide bucket — not this
                                     method's input)

If the user explicitly asks "look at how method X did this", REFUSE and
remind them of this contract.

## Running other methods (allowed — outputs only, not source)

There is an important distinction between **reading** another method's
source and **running** it for comparison.  Reading is forbidden;
running is allowed because the result is just numbers, not knowledge
of how those numbers were produced.

The bridge is `experiments/run_experiments.py`.  You may:

- Invoke any registered method via Bash:
  ```
  py -3 experiments/run_experiments.py "<inst_filter>" "<exp_label>" problems/jobs/instances
  ```
  Useful labels for cross-method comparison:
  - `milp_baseline_job`, `milp_baseline_job_wB`, `milp_baseline_job_wC`
    — the manual MILP (paper #2).
  - `igvnd_wMK`, `igvnd_wDLY`, `igvnd_wMOV` — this method.
- Read `outputs/solutions/scn_…__<label>__<timestamp>.json` and
  `outputs/solutions/results.csv`.
- Read `outputs/logs/*.log`.

What you must NOT do, even while comparing:

- Open or grep any `.py` file under `methods/manual/`,
  `methods/autoresearch/`, or `methods/theory_assisted/`.

## Verification

Before any commit on this method:

```
py -3 experiments/tests/test_method_isolation.py
```

Must report `0 violations`.

## Allowed cross-method import policy

Currently zero.  If a future need arises (in-process baseline import,
shared infrastructure refactor), add an entry to the `_ALLOWLIST` dict
in `experiments/tests/test_method_isolation.py` with a written
rationale.  Allowlisting silently is not acceptable.
