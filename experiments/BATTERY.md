# Standard battery for paper #2 (job-level extension)

The canonical benchmark used to compare any solving method for paper #2.
**Single source of truth** — methods' `CLAUDE.md` reference this file
rather than embedding their own copy of the convention.

## Composition

- **12 configurations × 10 seeds × 3 weight profiles = 360 runs.**
- Instances at `data/instances_202605_02/<config>/<config>_seed{N}.json`.
- Wall-clock per run: **60 s** (strictly enforced by every solver).

The 12 configurations (each with seeds 1..10):

```
scn_chain_tight_P5_R10        scn_triangle_loose_P5_R10
scn_full_tight_P5_R10         scn_triangle_medium_P5_R10
scn_full_tight_P5_R20         scn_triangle_tight_P5_R5
scn_hub_tight_P5_R10          scn_triangle_tight_P5_R10
scn_none_tight_P5_R10         scn_triangle_tight_P5_R20
scn_two_rows_tight_P5_R10     scn_triangle_tight_P5_R30
```

Topologies: complete blocking (`full`), chain, hub-and-spoke, no
blocking (`none`), parallel rows, three triangle slack-levels
(`loose`, `medium`, `tight`).  Sizes: R = number of aircraft
(5, 10, 20, 30).  P = number of positions (5 everywhere here).

## Weight profiles

The three canonical perturbations of `(Wᴹ, Wᴰ, Wˢ)`:

| label  | (Wᴹ, Wᴰ, Wˢ)    | drives                       |
| ------ | ---------------- | ---------------------------- |
| `wMK`  | (100, 1, 1)      | makespan-priority            |
| `wDLY` | (1, 100, 1)      | delay-priority               |
| `wMOV` | (1, 1, 100)      | movement-priority            |

Method labels in `experiments/run_experiments.py` carry these
suffixes — e.g. `igvnd_wMK / igvnd_wDLY / igvnd_wMOV` for the
v01 IG+VND solver.  The MILP baseline uses
`milp_baseline_job (≈wMK) / _wB (≈wDLY) / _wC (≈wMOV)` for
historical reasons; check the runner for the exact mapping when in
doubt.

## The cached-MILP rule

The MILP baseline is **fixed reference data**.  Do not re-run it on
every iteration — its rows are already in
[`outputs/solutions/results.csv`](../outputs/solutions/results.csv)
from prior batteries.  Re-running burns ~12 min × 3 profiles × 12
configs per seed for no information.

Cached labels:

- `milp_baseline_job`        — the manual MILP under the default profile
- `milp_baseline_job_wB`     — same, delay-priority profile
- `milp_baseline_job_wC`     — same, movement-priority profile

If you change MILP code (cuts, formulation, time budget), the cache
becomes stale and *must* be refreshed.  Otherwise: never re-run.

Helper: [`experiments/paired_report.py`](paired_report.py) consumes
the cached MILP rows + your fresh heuristic rows and emits the
per-instance + summary tables shown in each method's Part II.

## Running a battery

Full battery (360 runs, ~6 h):

```
py -3 experiments/run_experiments.py "" \
    "<label_wMK>,<label_wDLY>,<label_wMOV>" \
    data/instances_202605_02
```

Subset shortcuts during development (use these between full batteries):

| filter                          | size                   | when                                         |
| ------------------------------- | ---------------------- | -------------------------------------------- |
| `_seed1$`                       | 12 × 3 ≈ 35 min        | cross-type read of one weight per type       |
| `_seed1$,_seed2$,_seed3$`       | 36 × 3 ≈ 1.7 h         | early variance estimate                       |
| `scn_<config>_*`                | 10 × 3 ≈ 30 min        | drill into a specific topology               |
| `_seed10$`                      | 12 × 3 ≈ 35 min        | "the other end" sanity check                 |

The runner already sorts seed-first (all seed-1 of every type before
any seed-2) for an early cross-type read — see `_seed_sort_key` in
`run_experiments.py`.

## Reading results

Per-run artefacts (one row per (instance, label) execution):

- `outputs/solutions/scn_…__<label>__<timestamp>.json` — full solution.
- `outputs/solutions/results.csv`                       — aggregated.
- `outputs/logs/instances_main_methods_<timestamp>.log` — batch log.

Cross-method comparison (fresh heuristic vs cached MILP):

```
py -3 experiments/paired_report.py    # see its docstring for args
```

## Judging quality

For each weight profile, look at three things in this order:

1. **Mean relative gap** = `(MILP_obj − heuristic_obj) / MILP_obj` across
   seeds.  Positive = heuristic better.  Single number per
   (configuration, profile), useful for a quick scan.
2. **Per-component Δ** (heuristic − MILP): `Δmakespan`, `Δdelay`,
   `Δmov`.  The relative gap **inflates when MILP's value ≈ 0**
   (small-denominator effect — a delay of 5 vs 0 reads as +∞ % but
   is 5 absolute units).  Always cross-read the absolute Δ to know
   whether a residual matters.
3. **Compliance**: every solution must pass
   [`problems/jobs/checker.py`](../problems/jobs/checker.py)
   (RQ01–RQ09).  Non-compliant solutions are returned as infeasible
   by the runner and never count as wins.

## Caveats

- **MILP unconverged at scale.**  On R20 / R30 the MILP's 60-s
  objective is an incumbent with a large optimality gap (often
  80–99 %).  A heuristic "winning" there means "better feasible
  solution within the same 60 s", not proven superiority.
- **Run-to-run noise.**  Heuristics are time-limited and
  non-deterministic.  The noise floor on this battery is ~19 delay
  units on `chain_R10 wMK`; any reported delta smaller than that is
  noise, not a real change.  When in doubt, run 3 seeds and look at
  the spread.

## Where to update this file

Any change to the battery composition, the cached-MILP rule, or the
weight profiles is a project-wide decision and lands here, **not** in
each method's `CLAUDE.md`.  Methods that adopt the battery just
reference this file.
