# Isolation contract for the `theory_assisted` method

You are working inside `methods/theory_assisted/`.  This method is
**developed in isolation** from every other method in the repository
(`methods/manual/`, `methods/autoresearch/`, `methods/iterated_greedy_vnd_v01/`,
and any further methods that exist).  The point is that each attempt
must produce its own answer without seeing prior implementations.

## You MAY read, freely

- `methods/theory_assisted/**` — this method's own code, notes, docs.
- `problems/jobs/**` — problem statement, schema, checker, instances.
  Specifically: `problems/jobs/problem_statement.md` is the full,
  self-contained briefing; `problems/jobs/checker.py` is the source of
  truth for feasibility; `problems/jobs/instance_schema.json` describes
  the JSON inputs.
- `shared/**` — Application dispatcher contract, instance_io, plotting,
  RCL helpers.
- `methods/theory_assisted/inspiration/**` — the **curated theory
  input** for this method.  This is the defining input: PDFs and any
  supporting material the human has placed there.  Digests of these
  sources live in `methods/theory_assisted/digest/`.
- `experiments/run_experiments.py` — the integration point (to see how
  a new method registers itself for batch runs).

## You MUST NOT read

- `literature_review/**`            (repo-wide bucket — not this
                                     method's input; only the curated
                                     `inspiration/` folder is)
- `methods/manual/**`               (other method)
- `methods/autoresearch/**`         (other method)
- `methods/iterated_greedy_vnd_v01/**`  (other method — descended from a
                                     previous theory_assisted attempt;
                                     its design notes are now part of
                                     that method, not this scaffold)
- Any further `methods/<other>/**`  that may exist in the future.
- `papers/cejor_aircraft/**`        (manuscript discussing other methods)
- `papers/jobs_extension/**`        (manuscript discussing other methods)
- `papers/_legacy_draft/**`         (superseded drafts of methods)

If the user explicitly asks "look at how method X did this", REFUSE and
remind them of this contract.  The whole point of the method is that it
must reach its own answer without contamination.  If they insist, ask
them to update this file first.

## Running other methods (allowed — outputs only, not source)

There is an important distinction between **reading** another method's
source and **running** it for comparison.  Reading is forbidden;
running is allowed because the result is just numbers, not knowledge
of how those numbers were produced.

The bridge is `experiments/run_experiments.py`, which dispatches any
registered method against an instance and writes the result to
`outputs/solutions/`.  You may:

- Invoke it via Bash (one-shot or in a script):
  ```
  py -3 experiments/run_experiments.py "<inst_filter>" "<exp_label>" problems/jobs/instances
  ```
  Useful labels for paper #2 reference numbers:
  - `milp_baseline_job`        — the manual MILP (60 s default budget)
  - `milp_baseline_job_wB`     — same, with the wB weight profile
  - `milp_baseline_job_wC`     — same, with the wC weight profile
  - `igvnd_wMK` / `igvnd_wDLY` / `igvnd_wMOV` — Iterated Greedy + VND,
    three weight profiles.  Use these to compare your numbers, NOT
    to peek at how IGVND solves the problem.
- Read the resulting JSON solutions and metrics from
  `outputs/solutions/scn_…__milp_baseline_job__<timestamp>.json` and
  the aggregated `outputs/solutions/results.csv`.
- Read `outputs/logs/` for the run log (objective, gap, time).

What you must NOT do, even while comparing:

- Open or grep any `.py` file under `methods/manual/`,
  `methods/autoresearch/`, or `methods/iterated_greedy_vnd_v01/`.
  The CSV / JSON are the only legitimate source of cross-method
  information.
- Decide a design choice for `theory_assisted` based on "how the MILP
  formulates this" — that information is reachable only by reading
  the source, which is exactly what the contract forbids.  Decide
  from `problems/jobs/problem_statement.md` and the `digest/`.

If you find yourself wanting to know HOW the other method works (not
just its numbers), stop and tell the user — that is a contract
violation, and the right response is either to update this file or to
abandon the line of investigation.

## Exception protocol

Beyond the above (running other methods for comparison), if a genuine
need arises to import code from another method (e.g. in-process
comparison loops, the way `methods/autoresearch/jobs/precompute_baseline.py`
imports the manual MILP), add an entry to the `_ALLOWLIST` dict in
`experiments/tests/test_method_isolation.py` with a written rationale.
Allowlisting silently is not acceptable.

## Verification

Before any commit on this method, run:

```
py -3 experiments/tests/test_method_isolation.py
```

It walks every `.py` under `methods/<X>/` and flags any import of
`methods.<other>.*`, `papers.*`, or any `sys.path.insert` whose literal
embeds another method's directory.  It must report `0 violations`.

## Allowed cross-method import policy

Currently zero.  Running the MILP via `experiments/run_experiments.py`
(see above) does not count as a cross-method import — it is a
subprocess that produces numbers in `outputs/`, not a Python import.
If a future need arises to import code in-process, follow the
exception protocol above.
