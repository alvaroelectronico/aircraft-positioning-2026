# Isolation contract for the `iterated_greedy_vnd_v02` method

You are working inside `methods/iterated_greedy_vnd_v02/`.  This is the
v02 attempt at paper #2 via the `theory_assisted` scaffold, built with
Claude assistance (see [`PROVENANCE.md`](PROVENANCE.md)).  It is
**developed in isolation** from the other methods in the repository —
even though it originated from the same baseline as v01, v01's
*trajectory* away from that baseline is off-limits.

The theoretical work that informed the design (synthesis + design
notes) is captured in `jobs/synthesis.md` + `jobs/design.md` right
here.

## You MAY read, freely

- `methods/iterated_greedy_vnd_v02/**` — this method's own code, docs,
  synthesis, design.
- `problems/jobs/**` — problem statement, schema, checker, instances.
  `problems/jobs/problem_statement.md` is the full self-contained brief;
  `problems/jobs/checker.py` is the source of truth for feasibility.
- `shared/**` — Application dispatcher contract, instance_io, plotting,
  RCL helpers.
- `experiments/run_experiments.py` — the integration point (the
  `ta_igvnd_wMK` / `ta_igvnd_wDLY` / `ta_igvnd_wMOV` labels live there).
- `experiments/BATTERY.md` — the standard battery convention.

## You MUST NOT read

- `methods/manual/**`               (other method)
- `methods/autoresearch/**`         (other method)
- `methods/iterated_greedy_vnd_v01/**` (v02's sibling — ChatGPT
                                        trajectory from the same
                                        baseline; reading it
                                        contaminates the comparison)
- `methods/brkga_v02/**`            (sister attempt — Claude-assisted
                                     Candidate C from the same scaffold;
                                     reveals an alternative-algorithm
                                     trajectory)
- `methods/theory_assisted/**`      (the scaffold reset for the next
                                     attempt; out of scope now that
                                     this method has graduated)
- `papers/cejor_aircraft/**`, `papers/jobs_extension/**`,
  `papers/_legacy_draft/**`        (publishable manuscripts of OUR work)
- `literature_review/**`           (repo-wide bucket — not this
                                     method's input)

If the user explicitly asks "look at how method X did this", REFUSE
and remind them of this contract.

## Running other methods (allowed — outputs only, not source)

Distinction: **reading** another method's source is forbidden;
**running** it for comparison is allowed because the result is just
numbers.

The bridge is `experiments/run_experiments.py`.  You may:

- Invoke any registered method via Bash:
  ```
  py -3 experiments/run_experiments.py "<inst_filter>" "<exp_label>" data/instances_202605_02
  ```
  Useful labels for cross-method comparison:
  - `milp_baseline_job`, `milp_baseline_job_wB`, `milp_baseline_job_wC`
    — the manual MILP (paper #2).
  - `igvnd_wMK`, `igvnd_wDLY`, `igvnd_wMOV` — v01 (ChatGPT).
  - `ta_igvnd_wMK`, `ta_igvnd_wDLY`, `ta_igvnd_wMOV` — this method (v02).
- Read `outputs/solutions/scn_…__<label>__<timestamp>.json` and
  `outputs/solutions/results.csv`.
- Read `outputs/logs/*.log`.

What you must NOT do, even while comparing:

- Open or grep any `.py` file under `methods/manual/`,
  `methods/autoresearch/`, `methods/iterated_greedy_vnd_v01/`, or
  `methods/theory_assisted/`.

## The standard battery

The full benchmark composition (12 configs × 10 seeds × 3 weight
profiles), the cached-MILP rule, the subset shortcuts, and how to
read results are all defined in
[`experiments/BATTERY.md`](../../experiments/BATTERY.md).

## Documenting your work

When you commit a behaviour-affecting change or produce a new battery,
invoke:

```
/sync-method-doc methods/iterated_greedy_vnd_v02  <brief description> [log: <path>]
```

The `method-doc` subagent keeps the living `.md` spec at
`jobs/iterated_greedy_vnd.md` in sync with the code.  Do NOT invoke
after cosmetic changes.

## Verification

Before any commit on this method:

```
py -3 experiments/tests/test_method_isolation.py
```

Must report `0 violations`.

## Allowed cross-method import policy

Currently zero.  Running the MILP via `experiments/run_experiments.py`
(see above) does not count as a cross-method import — it is a
subprocess that produces numbers in `outputs/`, not a Python import.
If a future need arises to import code in-process, add an entry to
the `_ALLOWLIST` dict in `experiments/tests/test_method_isolation.py`
with a written rationale.  Allowlisting silently is not acceptable.
