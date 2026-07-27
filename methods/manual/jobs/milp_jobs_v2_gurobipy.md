# Native-gurobipy MILP for the job-level access problem (paper #2)

The exact MILP baseline for the job-as-scheduling-unit problem
(`problems/jobs/problem_statement.md`): a joint assignment-and-timing
formulation that encodes the three-mode access logic (Mode A vacant
front, Mode B inter-job gap with parameter `mu`, Mode C interruptible
mid-job with parameter `delta`) directly as a per-access-instant
partition of binary indicators.  It is hand-written (not LLM-derived)
and serves as the **cached reference** every heuristic method in this
repo is measured against (`experiments/BATTERY.md`, "the cached-MILP
rule").

> **Status (code `14cc776`, latest battery
> [`outputs/logs/seed8$,_seed9$,_seed10$_202605_02_main_methods_20260724_155333.log`](../../../outputs/logs/seed8$,_seed9$,_seed10$_202605_02_main_methods_20260724_155333.log)).**
> Convergence is fleet-size-gated: every `R5` instance and most `R10`
> instances close to proven optimality inside the 60 s / `MIPGap=0.0`
> budget, but `R20`/`R30` instances essentially never do (0 of 21 and
> 0 of 18 runs optimal, respectively, across all three weight
> profiles) and hit the time limit with large residual MIP gaps —
> see Part II.

---

# Part I — The method

## 1. Problem recap and notation

Fleet `R` of aircraft, each with a fixed job chain `J_r = (j_1, …,
j_{N_r})` under strict precedence; hangar positions `P` with blocking
arcs `(p, p') ∈ A` (front `p` obstructs rear `p'`).  A solution
assigns each aircraft to one position and a start time to every job.
Every access instant (entry `s_r'` or exit `f_r'`) into a rear
position must classify into exactly one of:

- **Mode A** — front vacant at that instant: free.
- **Mode B** — front aircraft between two consecutive jobs, gap ≥
  `mu`: costs 2 movements, no time extension.
- **Mode C** — front aircraft strictly mid-job and that job is
  interruptible: costs 2 movements and extends the job by `delta` per
  use (accumulated in `kappa_j`).

Objective: `min  wM·makespan + wD·Σ delay_r + wS·movements`.  See
`problems/jobs/problem_statement.md` for the full formal statement.

## 2. Design principle

Rather than linearising the Mode A/B/C disjunction as nested big-M
implications on a handful of ordering variables, the model introduces
one binary per (blocking arc, front aircraft, rear aircraft, access
side, candidate window) and forces them to **partition** the
placement-compatibility indicator `y_{r,r',p,p'}` exactly:
`z⁻ + z⁺ + Σ b_B + Σ b_C == y`.  Each partition member then gets its
own pair of big-M timing constraints tying it to the relevant job
start/finish.  This keeps the disjunction linear without an auxiliary
mode-selection layer, at the cost of one binary per (arc × ordered
aircraft pair × side × gap-or-job) — the model's main source of size.

## 3. Formulation

### 3.1 Sets and parameters (code names)

| formulation | code |
| --- | --- |
| aircraft `R`, positions `P`, blocking arcs `A` | `aircraft`, `positions`, `blocking_arcs` |
| job chain `J_r` | `chains[r]` (topologically sorted by [`_sort_job_chain`](milp_jobs_v2_gurobipy.py)) |
| `mu`, `delta`, `eta` | `data["mu"/"delta"/"eta"]`, defaulted from `_DEFAULT_MU/_DELTA/_ETA` if absent from the instance |
| big-M | `data["big_m"]`, derived from a `horizon_ub` upper bound (worst-case sequential schedule + interruption/gap slack) |
| `K_max` (cap on `kappa_j`) | `2·max(1, |R|-1)` |

### 3.2 Variables

| symbol | code | meaning |
| --- | --- | --- |
| `x[r,p]` | assignment binary |
| `s[j]`, `f[j]`, `k[j]` | start, finish, interruption count of job `j` (`k` forced to 0 for non-interruptible jobs) |
| `q[r,r',p]` | same-position sequencing direction indicator |
| `y[r,r',p_f,p_r]` | placement-compatibility (both `r` at front, `r'` at rear of the arc) |
| `z⁻/z⁺[r,r',p_f,p_r,a]` | Mode-A before/after indicators, per access side `a ∈ {in,out}` |
| `b_B[...,gi]` | Mode-B indicator for inter-job gap `gi` of the front chain |
| `b_C[...,jid]` | Mode-C indicator for job `jid` of the front chain (forced 0 if non-interruptible) |
| `n`, `delay[r]`, `mks` | movement count, per-aircraft delay, makespan |

### 3.3 Constraints (by block, see `build_model`)

1. **Assignment** — each aircraft to exactly one position.
2. **Duration/chaining** — `f[j] == s[j] + D_j + delta·k[j]`;
   `s[next] >= f[prev]` along each chain; `s_r >= E_r`.
3. **Same-position sequencing** — `q` activates only when both
   aircraft share `p`; enforces `eps`-separated start/finish via big-M.
4. **Placement compatibility `y`** — linear AND of the two `x`
   indicators for a given arc and ordered pair.
5. **Partition** — `z⁻ + z⁺ + Σ_gi b_B + Σ_j b_C == y`, per access
   side, so exactly one mode is "active" whenever the pair is
   co-located at the arc.
6. **Timing links** — each partition member's big-M window: Mode A
   compares the access instant `tau` against `[s_r, f_r]` of the front
   aircraft's *whole stay* (closed bounds — see the 2026-07-23 audit
   note in the code re: the width-`eta` band); Mode B against the gap
   `[f[j_k], s[j_k+1]]`; Mode C against the job's interior
   `[s[j]+eta, f[j]-eta]` with `k[j]` in the finish-time expression.
7. **Mode-B cumulative gap rule** — `s[next]-f[prev] >= mu · Σ b_B`
   over all rear neighbours/sides sharing that gap.
8. **`kappa` consistency** — `k[j] == Σ b_C` over all rear
   neighbours/sides using job `j`.
9. **Objective linking** — `n == 2·(Σ b_B + Σ b_C)`,
   `delay[r] >= f_r[r] - L[r]`, `mks >= f_r[r]` for every `r`.

### 3.4 Objective

`min  wM·mks + wD·Σ delay[r] + wS·n` (weights `weight_makespan`,
`weight_delay`, `weight_movements` from `prepare_data`).

## Behaviour observed

(write: qualitative solve behaviour — instance sizes it closes to
optimality within the battery's 60 s budget vs. where it only reaches
a bound — once a battery log is available to ground this.)

---

# Part II — Results and analysis

This battery is a **MILP-only refresh** (no heuristic paired in the
run) re-establishing the cached baseline rows for seeds 8–10 after the
2026-07-23 Mode-A closed-bounds audit fix (see the code comment above
the `zm_*`/`zp_*` constraints and "Key implementation notes" below).
There is therefore no heuristic-vs-MILP relative-gap table to report
here; the tables below characterise the MILP's own convergence
behaviour instead (Gurobi terminal status and residual `MIPGap`).

## Experimental setup

| field             | value |
| ----------------- | ----- |
| Battery           | 29 instance configs (`scn_*_P5_R{5,10,20,30}`, `data/instances_202605_02`) × seeds {8, 9, 10} × 3 weight profiles = 261 runs |
| Methods compared  | MILP baseline only — `milp_job_wMK`, `milp_job_wDLY`, `milp_job_wMOV` (`MILPJobsV2Solver`); no heuristic paired in this run |
| Weight profiles   | wMK (100/1/1, makespan-priority), wDLY (1/100/1, delay-priority), wMOV (1/1/100, movement-priority) |
| Budget            | 60 s wall-clock per run, `MIPGap=0.0`, `NoRelHeurTime=0` |
| Metric            | Gurobi terminal status (`optimal` / `maxTimeLim`) and the reported residual MIP gap (`Gap` column of the summary table) |
| Log               | [`outputs/logs/seed8$,_seed9$,_seed10$_202605_02_main_methods_20260724_155333.log`](../../../outputs/logs/seed8$,_seed9$,_seed10$_202605_02_main_methods_20260724_155333.log) |

## Convergence by weight profile (261 runs, all fleet sizes)

| profile | n | optimal | maxTimeLim | mean residual gap | mean solve time |
| --- | --- | --- | --- | --- | --- |
| wMK  | 87 | 44 | 43 | 32.42% | 35.4 s |
| wDLY | 87 | 27 | 60 | 68.21% | 43.3 s |
| wMOV | 87 | 30 | 57 | 53.44% | 42.6 s |

wDLY is the hardest profile to close (delay weight `100` amplifies the
big-M sequencing/timing constraints' sensitivity), followed by wMOV;
wMK closes about half the time.

## Convergence by fleet size `R` (pooled over the 3 weight profiles)

| R  | n (per profile) | optimal (wMK / wDLY / wMOV) | mean residual gap (wMK / wDLY / wMOV) |
| -- | --- | --- | --- |
| 5  | 18 | 18 / 18 / 18 | 0.00% / 0.00% / 0.00% |
| 10 | 30 | 26 / 9 / 12  | 3.79% / 67.90% / 32.08% |
| 20 | 21 | 0 / 0 / 0    | 62.88% / 99.91% / 92.34% |
| 30 | 18 | 0 / 0 / 0    | 77.01% / 99.97% / 97.12% |

The convergence cliff is sharp and fleet-size-gated, not profile-gated:
`R5` is solved to proven optimality every single time (all three
profiles, all three seeds), `R10` is a mixed bag dominated by the
weight profile (wMK still closes most of the time; wDLY/wMOV mostly
don't), and from `R20` up the model **never** closes inside the 60 s
budget regardless of profile — residual gaps of 60–100% are the norm,
i.e. the reported `maxTimeLim` objective is frequently far from proven
optimal at this scale.

## Performance summary

The exact reformulation is a genuine baseline only up to `R10`; above
that the 60 s/`MIPGap=0.0` budget is far too tight for the model size
(one binary per blocking-arc × ordered-aircraft-pair × side ×
gap-or-job — see "Design principle"), so cached `R20`/`R30` rows for
wDLY/wMOV in particular should be read as loose upper bounds on the
true optimum, not as ground truth. wMK is comparatively easier to
close because a single scalar (`makespan`) dominates the objective and
propagates through fewer of the partition binaries than a per-aircraft
delay or a global movement count does.

## Caveats

1. **`maxTimeLim` rows are not converged optima** at `R20`/`R30` —
   residual gaps of 60–100% mean the cached objective in
   `outputs/solutions/results.csv` for these rows is a valid *upper
   bound* only; any heuristic-vs-MILP relative gap computed against
   them will be optimistic (the heuristic may look worse than it is,
   or a small "win" may just reflect an unconverged baseline, not a
   better solution).
2. **wDLY is systematically the hardest profile** to close (68.21%
   mean residual gap vs. 32.42% for wMK) — do not read a wDLY-heavy
   aggregate figure as representative of the model's tightness on
   other profiles.
3. This log carries no heuristic comparison; the relative-gap and
   per-component-Δ tables from the template are intentionally omitted
   here and should be filled from a future battery log that pairs
   `milp_job_w*` against a heuristic label.

---

# Part III — Improvement roadmap

(empty until the human or solving agent writes a roadmap.)

## Diagnosis

(one paragraph: where the method stands today, what the residuals
look like, what is and is not addressable.)

## Priority 0 — [foundation item: correctness, time budget, …]

(status: PLANNED / DONE / REVERTED + evidence.)

## Priority 1 — [next biggest lever]

…

## Metrics and ablations

(what to log; how to measure each priority item.)

## Recommended implementation order

(numbered list with status next to each item.)

---

# Part IV — How it is implemented

Source: [`milp_jobs_v2_gurobipy.py`](milp_jobs_v2_gurobipy.py) — the
native-gurobipy model backend (functions `prepare_data`, `build_model`,
`get_solution`).  It does not itself implement the
`shared/application.py` solver contract; the sibling
[`milp_jobs_v2_solver.py`](milp_jobs_v2_solver.py) wraps it as class
`MILPJobsV2Solver`, registered in `experiments/run_experiments.py`
under the labels `milp_baseline_job`, `milp_baseline_job_heur`,
`milp_job_wMK`, `milp_job_wDLY`, `milp_job_wMOV`.

## This module's function-level API

| function | role |
| --- | --- |
| `prepare_data(raw_data, min_separation, weight_makespan, weight_delay, weight_movements)` | flattens a JSON instance into the dict consumed by `build_model`; sorts each aircraft's jobs into chain order via [`_sort_job_chain`](milp_jobs_v2_gurobipy.py); computes `horizon_ub`/`big_m`/`k_max`; defaults `mu`/`delta`/`eta` from the instance or `_DEFAULT_MU/_DELTA/_ETA` |
| `build_model(data)` | builds the unsolved `gp.Model`; stashes `m._d` (data dict) and `m._v` (all variable collections) for later extraction |
| `get_solution(m, raw_data)` | reads `m.Status`/`m.SolCount` post-`optimize()`, maps Gurobi status codes via `_GUROBI_STATUS`, and returns the solution dict (`status`, `objective`, `mip_gap`, `metrics.{makespan,movements,total_delay}`, `aircraft[].{position,start,finish,delay,jobs}`) |

### Solver contract, as implemented by the sibling wrapper (`shared/application.py`)

| member | role |
| --- | --- |
| `name` | `"milp_jobs_v2"` |
| `configure_solver(**kw)` | model keys (`min_separation`, `weight_makespan`, `weight_delay`, `weight_movements`, `time_limit_s`) update `_model_params`; anything else is forwarded verbatim to `m.setParam` |
| `solve(instance)` | calls `prepare_data` → `build_model` → sets `TimeLimit`/backend options → `m.optimize()` → `get_solution` |
| `get_config()` | `{**_model_params, **_solver_options}` |
| `get_log()` | not implemented — no per-run log is produced by this method |

### Config knobs (via `MILPJobsV2Solver.configure_solver`)

| key | default | meaning |
| --- | --- | --- |
| `min_separation` | `0.5` | `eps`, minimum same-position separation |
| `weight_makespan` | `0.1` | `wM` |
| `weight_delay` | `1.0` | `wD` |
| `weight_movements` | `10.0` | `wS` |
| `time_limit_s` | `None` | wall-clock limit passed to `m.setParam("TimeLimit", …)` |
| *(anything else)* | — | forwarded verbatim to Gurobi (e.g. `MIPGap`, `NoRelHeurTime`, `Threads`) |

## Method ↔ code map

| Method concept (Part I) | Code |
| --- | --- |
| job chain, chain precedence | `chains[r]`, `_sort_job_chain`, the `chain_{i}_{i+1}` constraints |
| Mode A vacant-front | `z_minus`/`z_plus` + the `zm_*`/`zp_*` big-M constraints |
| Mode B inter-job gap, `mu` rule | `b_B` + `bB_lb_*`/`bB_ub_*` + `bB_gap_*` |
| Mode C interruptible mid-job, `delta`/`kappa` | `b_C` + `bC_lb_*`/`bC_ub_*` + `kappa_{jid}` |
| exhaustive per-access partition | `part_{r}_{rp}_{p_f}_{p_r}_{a}` (`zm+zp+ΣbB+ΣbC == y`) |
| movement count `n` | `movements` constraint (`n == 2·(ΣbB + ΣbC)`) |
| makespan, delay, objective | `mks_{r}`, `delay_{r}`, final `setObjective` |

## Key implementation notes

- Mode-A clearance uses **closed bounds** on the front aircraft's
  whole stay `[s_r, f_r]` rather than a full `eta`-widened band; a
  2026-07-23 audit found the earlier `eta`-clearance formulation
  stricter than the problem statement and cut off feasible schedules
  at ±`eta` around a front stay (see the in-code comment above the
  `zm_*`/`zp_*` constraints, instance `two_rows_loose` seed 8, `wDLY`).
- `k[jid]` is forced to 0 for non-interruptible jobs at the point of
  variable creation (`non_int_{jid}`), and `b_C` variables for such
  jobs are likewise fixed to 0 (`non_int_C_*`) — the interruptibility
  flag is baked into the model rather than checked post-hoc.
- `q[r,rp,p]` is only created for `r < rp` per position but both
  directions (`q[r,rp,p]` and `q[rp,r,p]`) are added so exactly one
  direction (or neither, if not co-located) can be active.
- `big_m` is a single global constant derived from a worst-case
  sequential-schedule bound (`horizon_ub`) plus a `+1.0` slack over
  the largest temporal parameter — not tightened per-constraint.
- `get_solution` returns an empty-shell solution dict (`objective:
  None`, empty `aircraft`) when `m.SolCount == 0`, so callers do not
  need to guard against exceptions on infeasible/no-incumbent runs.

## Isolation

The solver imports nothing from other methods.  `prepare_data` reads
only the raw instance dict; `get_solution` reads only `m._d`/`m._v`
and the raw instance.  The `__main__` smoke test lazily imports the
paper-#2 checker from `problems/jobs/` (allowed) via a
`scripts/output_data` path insert.

## Smoke test

```
py -3 methods/manual/jobs/milp_jobs_v2_gurobipy.py \
    problems/jobs/instances/scn_triangle_tight_P5_R5/scn_triangle_tight_P5_R5_seed1.json
```

Prints `{status, objective, metrics}` after a 60 s / `MIPGap=0.0` solve,
then the full checker report via `check_solution`/`print_check`.  Note:
via the sibling wrapper (`milp_jobs_v2_solver.py`) the same instance
default and checker call are used, invoked as
`py -3 methods/manual/jobs/milp_jobs_v2_solver.py <instance.json>`.

---

# Change log

Track the method's evolution.  One row per behaviour-affecting commit
(or per shipped milestone), newest at the bottom.

| commit | change | effect on results |
| ------ | ------ | ----------------- |
| — | *(no change-log entry: this sync ran without a hint description of what changed — see summary)* | — |

---

*Keep this file in sync with `milp_jobs_v2_gurobipy.py`: when the code
changes behaviour, invoke `/sync-method-doc
methods/manual/jobs/milp_jobs_v2_gurobipy.py` with a brief hint
describing what changed and (if relevant) `log: <battery-log-path>`
for refreshing Part II.  The LaTeX formulation notes in
[`docs/milp_formulation.tex`](docs/milp_formulation.tex) were rewritten
on 2026-07-27 to match the code's actual partition-based model
(z−/z+/b^B/b^C, relaxed closed Mode-A bounds); the polished journal
version lives in `papers/jobs_extension/milp.tex`.*
