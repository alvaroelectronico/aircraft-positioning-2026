# Aircraft hangar positioning — job-level IG+VND heuristic

This repository develops and evaluates **one** solving method for the
**job-level** hangar-positioning problem (paper #2): the **`iterated_greedy_vnd_v01`**
heuristic (Iterated Greedy + Variable Neighbourhood Descent), measured against a
**MILP baseline**. The companion manuscript is `papers/jobs_extension/`.

> **Focus (since 2026-07).** The repo was refocused from a broad
> two-problem / six-method comparison to improving **`iterated_greedy_vnd_v01`**
> alone. The aircraft-level problem (paper #1) and the other method attempts
> (`iterated_greedy_vnd_v02`, `brkga_v02`, `theory_assisted`, `autoresearch`,
> and the old manual job heuristics) are **retired**. They remain in the tree
> for now (inert, pending a later deletion pass) and the full pre-refocus tree
> is preserved on the branch `archive/pre-restructure-20260713`. The **MILP
> baseline** (`methods/manual/jobs/milp_jobs_v2_solver.py`) is **kept** — it is
> the comparison reference the paper uses, not a discarded attempt.

## What is active

```
methods/iterated_greedy_vnd_v01/jobs/
    iterated_greedy_vnd.py        # the heuristic under study (labels igvnd_*)
    iterated_greedy_vnd.md        # living spec: Part I method / II results / III roadmap / IV code + Change log
    design.md, synthesis.md       # design rationale + literature synthesis
methods/manual/jobs/
    milp_jobs_v2_solver.py        # MILP baseline (labels milp_job_*), Gurobi
problems/jobs/                    # problem statement, checker (source of truth), schema, instances
data/instances_202605_02/         # the jobs benchmark (default instance root)
shared/                           # Application dispatcher, instance_io, plotting, rcl
experiments/                      # runner + battery tooling (see below)
papers/jobs_extension/            # the manuscript (tables auto-generated from results.csv)
outputs/                          # solutions/ (per-run JSONs + results.csv), logs/ (battery logs)
```

Retired-but-inert (to be deleted in a later pass; preserved on the archive branch):
`problems/aircraft/`, `methods/manual/aircraft/`, `methods/{autoresearch,iterated_greedy_vnd_v02,brkga_v02,theory_assisted}/`, `papers/cejor_aircraft/`.

## Branch / tag map

| ref | kind | meaning |
| --- | --- | --- |
| `main` | branch | **stable published baseline** = last *kept* improvement + paper |
| `dev` | branch | integration branch for active work |
| `exp/<slug>` | branch | one per improvement attempt (kept **or** dropped; never force-deleted) |
| `igvnd-v01-baseline-20260713` | tag | **the return point** — v01 code + 290-instance battery + paper |
| `igvnd-v01-<milestone>` | tag | each shipped improvement |
| `archive/pre-restructure-20260713` | branch | full pre-refocus tree (all methods + aircraft) |
| `v02-start`, `origin/theory_assisted-v02` | existing | historical markers |

**Return to the baseline at any time:**
```
git switch --detach igvnd-v01-baseline-20260713     # inspect the exact baseline
# or start over from it:
git switch -c try-again igvnd-v01-baseline-20260713
```

## Running a battery

The default instance root is now the jobs benchmark (`data/instances_202605_02`).
The convention (weight profiles, 60 s budget, **cached-MILP rule**, subset
shortcuts, quality judging + noise floor) lives in
[`experiments/BATTERY.md`](experiments/BATTERY.md) — read it first.

Heuristic on one instance, three weight profiles:
```
py -3 experiments/run_experiments.py "scn_triangle_tight_P5_R10_seed1$" \
    "igvnd_wMK,igvnd_wDLY,igvnd_wMOV" data/instances_202605_02
```
**Do not re-run the MILP** — its rows are cached in `outputs/solutions/results.csv`.
Pair a fresh heuristic run against the cached MILP with
`experiments/paired_report.py` / `experiments/gap_summary.py`, and A/B a code
change on a stratified subset with `experiments/ablation_subset.py` (applies the
~19 delay-unit noise floor). The `/run-battery` skill drives all of this.

## Documenting each step (improve or not)

Three layers keep a full trail, not just the latest code:

1. **Living spec** — `methods/iterated_greedy_vnd_v01/jobs/iterated_greedy_vnd.md`
   (Part I–IV): current method + latest battery. Sync after each kept change with
   `/sync-method-doc methods/iterated_greedy_vnd_v01 <hint> [log: <path>]`.
2. **Change log** — tail of that `.md`: one row per shipped/deferred commit.
3. **Improvement journal** — [`methods/iterated_greedy_vnd_v01/IMPROVEMENT_LOG.md`](methods/iterated_greedy_vnd_v01/IMPROVEMENT_LOG.md):
   one entry **per attempt**, recorded *before* coding (hypothesis) and closed
   with a verdict (KEPT / DROPPED / neutral-within-noise), its `exp/<slug>`
   branch or tag, and the battery log — so dead ends are documented too.

Per-attempt workflow: branch `exp/<slug>` off `dev` + add a journal row with the
hypothesis → run battery/ablation paired vs cached MILP → apply the noise-floor
check → fill the verdict. If KEPT: merge `--no-ff` into `main`, tag
`igvnd-v01-<milestone>`, run `/sync-method-doc`. If DROPPED: keep the `exp/`
branch and add a Change-log "attempted & DROPPED" row.

## Isolation test

The runner still guards its imports so removing retired methods won't break it.
Before committing solver/infra changes:
```
py -3 experiments/tests/test_method_isolation.py     # must report 0 violations
```
