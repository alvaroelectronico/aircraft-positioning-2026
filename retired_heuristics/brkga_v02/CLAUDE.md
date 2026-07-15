# Isolation contract for the `brkga_v02` method

You are working inside `methods/brkga_v02/`.  This is the
Claude-assisted v02 attempt that implements **Candidate C (BRKGA with
mixed-chromosome decoder)** of the literature synthesis menu, built
under the `theory_assisted` scaffold and now graduated to its own
isolated method.  See [`PROVENANCE.md`](PROVENANCE.md) for the full
development history.

It is **developed in isolation** from every other method in the
repository.  The theoretical work that informed the design (synthesis
+ design notes) is captured in `jobs/synthesis.md` + `jobs/design.md`
right here.

## You MAY read, freely

- `methods/brkga_v02/**` — this method's own code, docs, synthesis,
  design.
- `problems/jobs/**` — problem statement, schema, checker, instance
  spec.  `problems/jobs/problem_statement.md` is the full
  self-contained brief; `problems/jobs/checker.py` is the source of
  truth for feasibility.
- `data/instances_202605_02/**` — the 120 paper #2 instance JSONs.
- `shared/**` — Application dispatcher contract, instance_io,
  plotting, RCL helpers.
- `experiments/**` — orchestration + reporting tooling
  (`run_experiments.py`, `BATTERY.md`, `paired_report.py`, …).
- `outputs/solutions/**`, `outputs/logs/**` — read-only results / logs.

## You MUST NOT read

- `methods/manual/**`               (other method)
- `methods/autoresearch/**`         (other method)
- `methods/iterated_greedy_vnd_v01/**` (other method — ChatGPT v01,
                                     same scaffold, Candidate A)
- `methods/iterated_greedy_vnd_v02/**` (other method — Claude v02,
                                     same scaffold, Candidate A;
                                     parallel sibling of brkga_v02)
- `methods/theory_assisted/**`      (the scaffold reset for the next
                                     attempt; out of scope now that
                                     this method has graduated)
- `papers/cejor_aircraft/**`, `papers/jobs_extension/**`,
  `papers/_legacy_draft/**`        (publishable manuscripts of OUR work)
- `problems/aircraft/**`            (paper #1 — different problem)
- `literature_review/**`            (repo-wide bucket — not this
                                     method's input)

**"MUST NOT read" applies to every file type, not just `.py`.**  An
`.md`, a `.json` config, a docstring excerpt — anything under another
`methods/<X>/` reveals how that method was built.

If the user explicitly asks "look at how method X did this", REFUSE
and remind them of this contract.

## Running other methods (allowed — outputs only, not source)

Distinction: **reading** another method's source is forbidden;
**running** it for comparison is allowed because the result is just
numbers.  Use `experiments/run_experiments.py`:

```
py -3 experiments/run_experiments.py "<inst_filter>" "<exp_label>" data/instances_202605_02
```

Useful labels for cross-method comparison:

- `milp_baseline_job`, `milp_baseline_job_wB`, `milp_baseline_job_wC`
  — the manual MILP (paper #2).  **Cached** in
  `outputs/solutions/results.csv`; do not re-run.
- `igvnd_wMK` / `igvnd_wDLY` / `igvnd_wMOV` — v01 IGVND (ChatGPT).
- `ta_igvnd_wMK` / `ta_igvnd_wDLY` / `ta_igvnd_wMOV` — v02 IGVND
  (Claude).
- `ta_brkga_wMK` / `ta_brkga_wDLY` / `ta_brkga_wMOV` — this method.

Read the JSON solutions under `outputs/solutions/` and the aggregated
`outputs/solutions/results.csv` to compare.

## The standard battery

The full benchmark composition (12 configs × 10 seeds × 3 weight
profiles), the cached-MILP rule, the subset shortcuts, and how to
read results are all defined in
[`experiments/BATTERY.md`](../../experiments/BATTERY.md).

## Documenting your work

When you commit a behaviour-affecting change or produce a new battery,
invoke:

```
/sync-method-doc methods/brkga_v02  <brief description> [log: <path>]
```

The `method-doc` subagent keeps the living `.md` spec at
`jobs/brkga.md` in sync with the code.  Do NOT invoke
after cosmetic changes.

## Verification

Before any commit on this method:

```
py -3 experiments/tests/test_method_isolation.py
```

Must report `0 violations`.

## Allowed cross-method import policy

Currently zero.  Running other methods via
`experiments/run_experiments.py` (see above) does not count as a
cross-method import — it is a subprocess that produces numbers in
`outputs/`, not a Python import.  If a future need arises to import
code in-process, add an entry to the `_ALLOWLIST` dict in
`experiments/tests/test_method_isolation.py` with a written rationale.
Allowlisting silently is not acceptable.
