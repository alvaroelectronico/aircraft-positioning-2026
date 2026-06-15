# `iterated_greedy_vnd_v01` — method overview

**Version:** v01 (first LLM-assisted attempt on paper #2 via the
`theory_assisted` scaffold).
**LLM assistance:** ChatGPT (GPT-4-class model).  See
[`PROVENANCE.md`](PROVENANCE.md) for the full record.

Iterated Greedy outer loop (NEH-style construction + worst-aircraft
destruction/reconstruction) wrapped around a sequential Variable
Neighbourhood Descent local search.  Targets paper #2 (job-level
extension).

## Provenance

This method originated from the `theory_assisted` literature-informed
process.  The artefacts of that process now live alongside the solver:

- [`jobs/synthesis.md`](jobs/synthesis.md) — cross-paper synthesis of
  the curated theory that produced this design (Candidate A in that
  document).
- [`jobs/design.md`](jobs/design.md) — design rationale derived from
  the synthesis.
- [`jobs/iterated_greedy_vnd.md`](jobs/iterated_greedy_vnd.md) —
  current behaviour, contract, and configuration knobs of the solver.
  Kept in sync with the `.py` (see the project-level memory note
  `keep-igvnd-md-in-sync`).

The original `inspiration/` PDFs and `digest/` notes remain under
`methods/theory_assisted/` because they are reusable theory for future
attempts; they are NOT on this method's read path any more (see
[`CLAUDE.md`](CLAUDE.md)).

A parallel **v02** attempt with Claude as the LLM assistant is starting
on the same `theory_assisted` scaffold so the two developer workflows
(human + GPT vs. human + Claude) can be compared head-to-head on
identical theory inputs.  v02 will land in its own method directory
once mature.

## Reading list

| Path                                              | Purpose                                        |
| ------------------------------------------------- | ---------------------------------------------- |
| `problems/jobs/problem_statement.md`              | Self-contained spec of paper #2.              |
| `problems/jobs/checker.py`                        | Source of truth for feasibility / metrics.    |
| `shared/application.py`                           | Solver contract.                              |
| `shared/instance_io.py`, `shared/rcl.py`          | Loader + RCL helpers.                         |
| `methods/iterated_greedy_vnd_v01/jobs/*.md`       | Method's own docs (design, changelog).        |

## Reproducing

Through `experiments/run_experiments.py`, with three weight-profile
labels:

```
py -3 experiments/run_experiments.py "_seed1$" "igvnd_wMK"  problems/jobs/instances
py -3 experiments/run_experiments.py "_seed1$" "igvnd_wDLY" problems/jobs/instances
py -3 experiments/run_experiments.py "_seed1$" "igvnd_wMOV" problems/jobs/instances
```

Labels are kept as `igvnd_*` (without the `v01_` prefix) for backward
compatibility with existing `outputs/solutions/results.csv` rows.
When v02 lands it will register fresh labels (e.g. `igvnd_v02_*` or
whatever the new algorithm is called).

Or invoke the solver directly:

```
py -3 methods/iterated_greedy_vnd_v01/jobs/iterated_greedy_vnd.py \
    problems/jobs/instances/scn_triangle_tight_P5_R5/scn_triangle_tight_P5_R5_seed1.json 10
```

## Comparing against other methods

Through `outputs/solutions/results.csv` only — never by reading other
methods' source.  See [`CLAUDE.md`](CLAUDE.md) for the run-vs-read
distinction.
