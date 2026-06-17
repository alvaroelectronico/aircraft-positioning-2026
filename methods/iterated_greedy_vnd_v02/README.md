# `iterated_greedy_vnd_v02` — method overview

**Version:** v02 (second LLM-assisted attempt on paper #2 via the
`theory_assisted` scaffold).
**LLM assistance:** Claude (Anthropic).  See
[`PROVENANCE.md`](PROVENANCE.md) for the full record.

Iterated Greedy outer loop (NEH-style construction + worst-aircraft
destruction/reconstruction) wrapped around a sequential Variable
Neighbourhood Descent local search, evolved through several sub-versions
(v02 → v03 Mode-B gaps → v03.1 interval caching → v04 light-objective
decode → v05 incremental zero-decode in the VND).  Targets paper #2
(job-level extension).

## Provenance

This method originated from the `theory_assisted` literature-informed
process, starting from the **same 30e1af0 IGVND baseline** that v01
(ChatGPT-assisted) evolved from.  The artefacts of that process now
live alongside the solver:

- [`jobs/synthesis.md`](jobs/synthesis.md) — cross-paper synthesis of
  the curated theory that produced this design (Candidate A in that
  document — same as v01's starting candidate).
- [`jobs/design.md`](jobs/design.md) — design rationale derived from
  the synthesis, then evolved through the v02–v05 sub-versions.
- [`jobs/iterated_greedy_vnd.md`](jobs/iterated_greedy_vnd.md) —
  current behaviour, contract, and configuration knobs of the solver.
  Kept in sync with the `.py` (see the project-level memory note
  `keep-igvnd-md-in-sync`).

The original `inspiration/` PDFs and `digest/` notes remain under
`methods/theory_assisted/` because they are reusable theory for future
attempts; they are NOT on this method's read path any more (see
[`CLAUDE.md`](CLAUDE.md)).

The **v01 sibling** (`methods/iterated_greedy_vnd_v01/`) is the
ChatGPT-assisted attempt from the same baseline.  Its code is **not on
v02's read path** — the whole point of the experiment is to compare
the two LLM-assisted developer trajectories without contamination.

## Reading list

| Path                                              | Purpose                                        |
| ------------------------------------------------- | ---------------------------------------------- |
| `problems/jobs/problem_statement.md`              | Self-contained spec of paper #2.              |
| `problems/jobs/checker.py`                        | Source of truth for feasibility / metrics.    |
| `shared/application.py`                           | Solver contract.                              |
| `shared/instance_io.py`, `shared/rcl.py`          | Loader + RCL helpers.                         |
| `methods/iterated_greedy_vnd_v02/jobs/*.md`       | Method's own docs (design, changelog).        |
| `experiments/BATTERY.md`                          | Standard battery for paper #2.                |

## Reproducing

Through `experiments/run_experiments.py`, with the existing labels
(kept as `ta_igvnd_*` for `results.csv` continuity — the prefix is
historical, from when the method lived in the `theory_assisted/` dir):

```
py -3 experiments/run_experiments.py "_seed1$" "ta_igvnd_wMK"  data/instances_202605_02
py -3 experiments/run_experiments.py "_seed1$" "ta_igvnd_wDLY" data/instances_202605_02
py -3 experiments/run_experiments.py "_seed1$" "ta_igvnd_wMOV" data/instances_202605_02
```

Or invoke the solver directly:

```
py -3 methods/iterated_greedy_vnd_v02/jobs/iterated_greedy_vnd.py \
    data/instances_202605_02/scn_triangle_tight_P5_R5/scn_triangle_tight_P5_R5_seed1.json 10
```

## Comparing against other methods

Through `outputs/solutions/results.csv` and
`experiments/paired_report.py` only — never by reading other methods'
source.  See [`CLAUDE.md`](CLAUDE.md) for the run-vs-read distinction
and [`experiments/BATTERY.md`](../../experiments/BATTERY.md) for the
standard battery + cached-MILP rule.
