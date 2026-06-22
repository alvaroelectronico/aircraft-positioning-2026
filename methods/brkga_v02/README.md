# `brkga_v02` — method overview

**Version:** v02 (Claude-assisted, Candidate C of the literature
synthesis menu).
**LLM assistance:** Claude (Anthropic).  See
[`PROVENANCE.md`](PROVENANCE.md) for the full record.

Biased Random-Key Genetic Algorithm (BRKGA) with a **mixed-chromosome
decoder**: indicator keys for position assignment, permutation keys
for in-position job sequencing.  Targets paper #2 (job-level
extension).  Profile-gated Mode-C manoeuvres (enabled under `wMK` /
`wDLY`, disabled under `wMOV`).

## Provenance

This method originated from the `theory_assisted` literature-informed
process.  The artefacts of that process now live alongside the solver:

- [`jobs/synthesis.md`](jobs/synthesis.md) — cross-paper synthesis of
  the curated theory that produced this design (Candidate C in that
  document — distinct from v01/v02 which both built Candidate A).
- [`jobs/design.md`](jobs/design.md) — design rationale derived from
  the synthesis (encoding, decoder, GA outer loop).
- [`jobs/brkga.md`](jobs/brkga.md) —
  current behaviour, contract, and configuration knobs of the solver.
  Kept in sync with the `.py` (see the project-level memory note
  `keep-igvnd-md-in-sync`, generalised to "keep the spec .md in sync
  with the .py for every method").

The original `inspiration/` PDFs and `digest/` notes remain under
`methods/theory_assisted/` because they are reusable theory for future
attempts; they are NOT on this method's read path any more (see
[`CLAUDE.md`](CLAUDE.md)).

## Reading list

| Path                                              | Purpose                                        |
| ------------------------------------------------- | ---------------------------------------------- |
| `problems/jobs/problem_statement.md`              | Self-contained spec of paper #2.              |
| `problems/jobs/checker.py`                        | Source of truth for feasibility / metrics.    |
| `shared/application.py`                           | Solver contract.                              |
| `shared/instance_io.py`, `shared/rcl.py`          | Loader + RCL helpers.                         |
| `methods/brkga_v02/jobs/*.md`                     | Method's own docs (design, changelog).        |
| `experiments/BATTERY.md`                          | Standard battery for paper #2.                |

## Reproducing

Through `experiments/run_experiments.py`, with the existing labels
(kept as `ta_brkga_*` for `results.csv` continuity — the prefix is
historical, from when the method lived in the `theory_assisted/` dir):

```
py -3 experiments/run_experiments.py "_seed1$" "ta_brkga_wMK"  data/instances_202605_02
py -3 experiments/run_experiments.py "_seed1$" "ta_brkga_wDLY" data/instances_202605_02
py -3 experiments/run_experiments.py "_seed1$" "ta_brkga_wMOV" data/instances_202605_02
```

Or invoke the solver directly:

```
py -3 methods/brkga_v02/jobs/brkga.py \
    data/instances_202605_02/scn_triangle_tight_P5_R5/scn_triangle_tight_P5_R5_seed1.json
```

## Comparing against other methods

Through `outputs/solutions/results.csv` and
`experiments/paired_report.py` only — never by reading other methods'
source.  See [`CLAUDE.md`](CLAUDE.md) for the run-vs-read distinction
and [`experiments/BATTERY.md`](../../experiments/BATTERY.md) for the
standard battery + cached-MILP rule.
