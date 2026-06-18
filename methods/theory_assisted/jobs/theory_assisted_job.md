# Theory-Assisted BRKGA for the aircraft-positioning jobs extension (paper #2)

BRKGA (Biased Random-Key Genetic Algorithm) with a mixed-chromosome decoder for the
job-level scheduling variant of the aircraft-positioning problem.  Developed in
isolation under `methods/theory_assisted/` as Candidate C of the synthesis menu
produced by the `/synthesize-theory` skill.  The solver is Claude-assisted: the
algorithm was chosen from the curated literature digests in
`methods/theory_assisted/digest/` and designed from `problems/jobs/problem_statement.md`
and `problems/jobs/checker.py` without reading any other method's source.

> **Status (code 2d37eeb, first battery 2026-06-18, log `202605_02_main_methods_20260618_064914.log`).**
> 360/360 runs feasible.  The BRKGA broadly loses to the cached MILP on R5–R10
> instances across all three weight profiles: the Mode-A/B-only decoder drives
> movements to zero but inflates makespan and delay significantly.  The one clear
> win is `scn_triangle_tight_P5_R30`, where the 60 s MILP is unconverged and the
> heuristic beats it by +15.8% (wMK), +21.0% (wDLY), +21.4% (wMOV).
> `scn_none` (no blocking) ties at ~0%.  Priority next step: Mode-C construction
> and/or warm-start injection to reduce the makespan/delay inflation on R5–R10.

---

# Part I — The method

## 1. Problem recap and notation

(write the problem in this method's terms, using the notation from
`problems/jobs/problem_statement.md`.  Keep it short — a page max.)

## 2. Design principle

(write the core insight this method is built on.  One paragraph.
For BRKGA: the key insight is separating the combinatorial decisions —
which aircraft goes where, and in what service order — from the timing
decisions, encoding both in a random-key chromosome so the GA can
explore the combinatorial space while the decoder resolves timing
deterministically and optimally for each chromosome.  The decoder
exploits the topological order of the blocking DAG to guarantee that
front aircraft are fixed before rear aircraft are placed, so access
classification is final and never retroactively invalidated.)

## 3. Chromosome encoding

(write the two-part chromosome structure: assignment genes + sequencing genes,
each of length |R|.  Document the mapping from gene value to decision:
assignment key → position index; sequencing key → service order within position.)

## 4. Decoder

(write the decode procedure: topological placement, candidate-start-time
generation, local-cost scan, Mode-A/B/C classification via `_classify_access`,
cumulative-μ enforcement on Mode-B gaps, safe-late fallback.  Reference §4.2–4.4
of `notes/design.md`.)

## 5. BRKGA engine

(write the GA loop: population size, elite/mutant fractions, biased crossover
probability ρ, shake-on-stagnation trigger, wall-clock termination.)

## 6. The complete algorithm in pseudocode

```
BRKGA(instance, time_limit_s, seed):
  ctx  ← DecoderContext(instance, weights)
  pop  ← initialise(pop_size, n_keys=2|R|, warmstarts, rng)
  scored ← sort([(decode(k), k) for k in pop])
  best ← scored[0]
  stagnant ← 0
  while elapsed < time_limit_s:
    elites    ← scored[:n_elite]
    next_pop  ← elites + mutants + biased_crossover(elites, non_elites)
    scored    ← sort([(decode(k), k) for k in next_pop])
    if scored[0] < best: best ← scored[0]; stagnant ← 0
    else:                 stagnant += 1
    if stagnant ≥ shake_after:
      scored ← elites + resample(non_elites); stagnant ← 0
  return decode(best_keys)

decode(keys, ctx):
  assign each aircraft r to position positions[floor(keys[r]*|P|)]
  sort aircraft within each position by ascending keys[|R|+r]
  for pos in topological_order(blocking_DAG):
    for r in at_position[pos] (sequencing order):
      cands ← candidate_starts(r, fronts_fixed_above)
      best_s ← argmin_{s in cands} local_cost(r, s, fronts)  // Mode A or B only
      commit(r, best_s); update gap_uses
  return assemble_solution(placed, ctx)
```

## Behaviour observed

(write after the first battery runs.  Initially: decoder produces feasible
solutions on all tested chromosomes.  Mode-C construction is deliberately
excluded, so all schedules satisfy RQ09 trivially.)

---

# Part II — Results and analysis

## Experimental setup

| field             | value |
| ----------------- | ----- |
| Battery           | Standard paper-#2 battery (`experiments/BATTERY.md`): 12 instance types × 10 seeds × 3 weight profiles = 360 runs |
| Methods compared  | `ta_brkga_wMK` / `ta_brkga_wDLY` / `ta_brkga_wMOV` vs cached `milp_job_wMK` / `milp_job_wDLY` / `milp_job_wMOV` |
| Weight profiles   | wMK (100/1/1) / wDLY (1/100/1) / wMOV (1/1/100) |
| Budget            | 60 s wall-clock per run |
| Metric            | relative gap = (MILP_obj − heuristic_obj) / MILP_obj; gap > 0 means heuristic BETTER |
| Log               | [`outputs/logs/202605_02_main_methods_20260618_064914.log`](../../../outputs/logs/202605_02_main_methods_20260618_064914.log) |

## Relative objective gap (mean / min / max over seeds)

### wMK (100/1/1 — makespan-priority)

| Instance type | N | Mean | Min | Max |
| --- | --- | --- | --- | --- |
| scn_chain_tight_P5_R10 | 10 | −45.83% | −59.58% | −34.71% |
| scn_full_tight_P5_R10 | 10 | −58.73% | −90.74% | −30.54% |
| scn_full_tight_P5_R20 | 10 | −18.18% | −73.64% | +26.98% |
| scn_hub_tight_P5_R10 | 10 | −21.18% | −36.87% | −14.09% |
| scn_none_tight_P5_R10 | 10 | +0.00% | +0.00% | +0.00% |
| scn_triangle_loose_P5_R10 | 10 | −22.24% | −36.69% | −4.33% |
| scn_triangle_medium_P5_R10 | 10 | −20.93% | −36.31% | −1.43% |
| scn_triangle_tight_P5_R10 | 10 | −21.09% | −37.22% | −4.22% |
| scn_triangle_tight_P5_R20 | 10 | −3.83% | −12.08% | +3.69% |
| scn_triangle_tight_P5_R30 | 10 | **+15.81%** | +3.21% | +25.34% |
| scn_triangle_tight_P5_R5 | 10 | −4.61% | −27.61% | +0.00% |
| scn_two_rows_tight_P5_R10 | 10 | −18.27% | −36.40% | −1.34% |

### wDLY (1/100/1 — delay-priority)

| Instance type | N | Mean | Min | Max |
| --- | --- | --- | --- | --- |
| scn_chain_tight_P5_R10 | 10 | −80.50% | −119.20% | −27.73% |
| scn_full_tight_P5_R10 | 10 | −65.36% | −146.38% | −20.23% |
| scn_full_tight_P5_R20 | 10 | +9.89% | −35.06% | +43.29% |
| scn_hub_tight_P5_R10 | 10 | −17.95% | −32.89% | −1.20% |
| scn_none_tight_P5_R10 | 10 | −0.00% | −0.00% | +0.00% |
| scn_triangle_loose_P5_R10 | 10 | −2151.61% | −5769.18% | +13.64% |
| scn_triangle_medium_P5_R10 | 10 | −41.28% | −93.72% | +15.90% |
| scn_triangle_tight_P5_R10 | 10 | −20.09% | −54.57% | +12.93% |
| scn_triangle_tight_P5_R20 | 10 | −8.37% | −29.97% | +16.88% |
| scn_triangle_tight_P5_R30 | 10 | **+20.97%** | −2.02% | +43.52% |
| scn_triangle_tight_P5_R5 | 10 | −1322.89% | −3695.59% | +0.00% |
| scn_two_rows_tight_P5_R10 | 10 | −21.52% | −43.27% | +4.91% |

### wMOV (1/1/100 — movement-priority)

| Instance type | N | Mean | Min | Max |
| --- | --- | --- | --- | --- |
| scn_chain_tight_P5_R10 | 10 | −34.03% | −76.46% | +12.22% |
| scn_full_tight_P5_R10 | 10 | −56.01% | −100.56% | −23.42% |
| scn_full_tight_P5_R20 | 10 | −42.20% | −62.45% | −29.51% |
| scn_hub_tight_P5_R10 | 10 | −17.88% | −25.73% | −13.33% |
| scn_none_tight_P5_R10 | 10 | −0.06% | −0.62% | +0.00% |
| scn_triangle_loose_P5_R10 | 10 | −57.48% | −111.11% | +2.24% |
| scn_triangle_medium_P5_R10 | 10 | −31.32% | −51.44% | +9.60% |
| scn_triangle_tight_P5_R10 | 10 | −22.38% | −44.59% | +2.72% |
| scn_triangle_tight_P5_R20 | 10 | −6.29% | −21.55% | +13.65% |
| scn_triangle_tight_P5_R30 | 10 | **+21.43%** | −1.41% | +36.33% |
| scn_triangle_tight_P5_R5 | 10 | −20.00% | −74.29% | +0.00% |
| scn_two_rows_tight_P5_R10 | 10 | −19.59% | −42.60% | +1.03% |

### All profiles aggregated

| Instance type | N | Mean | Min | Max |
| --- | --- | --- | --- | --- |
| scn_chain_tight_P5_R10 | 30 | −53.45% | −119.20% | +12.22% |
| scn_full_tight_P5_R10 | 30 | −60.03% | −146.38% | −20.23% |
| scn_full_tight_P5_R20 | 30 | −16.83% | −73.64% | +43.29% |
| scn_hub_tight_P5_R10 | 30 | −19.01% | −36.87% | −1.20% |
| scn_none_tight_P5_R10 | 30 | −0.02% | −0.62% | +0.00% |
| scn_triangle_loose_P5_R10 | 30 | −743.77% | −5769.18% | +13.64% |
| scn_triangle_medium_P5_R10 | 30 | −31.18% | −93.72% | +15.90% |
| scn_triangle_tight_P5_R10 | 30 | −21.19% | −54.57% | +12.93% |
| scn_triangle_tight_P5_R20 | 30 | −6.16% | −29.97% | +16.88% |
| scn_triangle_tight_P5_R30 | 30 | **+19.40%** | −2.02% | +43.52% |
| scn_triangle_tight_P5_R5 | 30 | −449.17% | −3695.59% | +0.00% |
| scn_two_rows_tight_P5_R10 | 30 | −19.80% | −43.27% | +4.91% |

## Per-component mean Δ (heuristic − MILP; negative = heuristic better)

### wMK (100/1/1)

| Instance type | N | Δmakespan | Δdelay | Δmov |
| --- | --- | --- | --- | --- |
| scn_chain_tight_P5_R10 | 10 | +29.30 | +121.90 | −15.60 |
| scn_full_tight_P5_R10 | 10 | +43.35 | +153.95 | −19.00 |
| scn_full_tight_P5_R20 | 10 | +36.00 | −76.65 | −11.40 |
| scn_hub_tight_P5_R10 | 10 | +13.65 | +18.55 | −9.40 |
| scn_none_tight_P5_R10 | 10 | +0.00 | +0.00 | +0.00 |
| scn_triangle_loose_P5_R10 | 10 | +13.80 | +29.70 | −7.00 |
| scn_triangle_medium_P5_R10 | 10 | +13.10 | +37.20 | −7.60 |
| scn_triangle_tight_P5_R10 | 10 | +13.15 | +43.70 | −7.00 |
| scn_triangle_tight_P5_R20 | 10 | +5.20 | +85.70 | −11.20 |
| scn_triangle_tight_P5_R30 | 10 | **−54.85** | **−676.10** | −2.60 |
| scn_triangle_tight_P5_R5 | 10 | +1.50 | +6.30 | +0.00 |
| scn_two_rows_tight_P5_R10 | 10 | +11.30 | +21.10 | −4.20 |

### wDLY (1/100/1)

| Instance type | N | Δmakespan | Δdelay | Δmov |
| --- | --- | --- | --- | --- |
| scn_chain_tight_P5_R10 | 10 | +23.60 | +97.95 | −15.00 |
| scn_full_tight_P5_R10 | 10 | +32.25 | +123.75 | −14.00 |
| scn_full_tight_P5_R20 | 10 | −1.65 | −314.60 | −10.60 |
| scn_hub_tight_P5_R10 | 10 | +8.55 | +20.20 | −8.20 |
| scn_none_tight_P5_R10 | 10 | +0.00 | +0.00 | +0.00 |
| scn_triangle_loose_P5_R10 | 10 | +15.00 | +25.10 | −6.60 |
| scn_triangle_medium_P5_R10 | 10 | +11.20 | +25.20 | −10.40 |
| scn_triangle_tight_P5_R10 | 10 | +8.20 | +22.60 | −10.80 |
| scn_triangle_tight_P5_R20 | 10 | +7.75 | +60.90 | −11.60 |
| scn_triangle_tight_P5_R30 | 10 | **−72.40** | **−770.20** | −6.80 |
| scn_triangle_tight_P5_R5 | 10 | +4.35 | +4.85 | −0.60 |
| scn_two_rows_tight_P5_R10 | 10 | +9.85 | +22.30 | −5.60 |

### wMOV (1/1/100)

| Instance type | N | Δmakespan | Δdelay | Δmov |
| --- | --- | --- | --- | --- |
| scn_chain_tight_P5_R10 | 10 | +19.85 | +59.05 | +0.00 |
| scn_full_tight_P5_R10 | 10 | +38.90 | +114.05 | +0.00 |
| scn_full_tight_P5_R20 | 10 | +103.70 | +579.55 | +0.00 |
| scn_hub_tight_P5_R10 | 10 | +14.00 | +18.60 | +0.00 |
| scn_none_tight_P5_R10 | 10 | +0.10 | +0.00 | +0.00 |
| scn_triangle_loose_P5_R10 | 10 | +15.65 | +25.15 | +0.00 |
| scn_triangle_medium_P5_R10 | 10 | +13.40 | +27.40 | +0.00 |
| scn_triangle_tight_P5_R10 | 10 | +14.35 | +25.30 | +0.00 |
| scn_triangle_tight_P5_R20 | 10 | +4.55 | +49.70 | +0.00 |
| scn_triangle_tight_P5_R30 | 10 | **−76.55** | **−721.30** | +0.00 |
| scn_triangle_tight_P5_R5 | 10 | +1.60 | +5.50 | +0.00 |
| scn_two_rows_tight_P5_R10 | 10 | +9.90 | +23.45 | +0.00 |

## Performance summary

**wMK (makespan-priority).**  The heuristic loses uniformly on R5–R10 instances:
mean gaps range from −4.6% (`scn_triangle_tight_P5_R5`) to −58.7% (`scn_full_tight_P5_R10`),
driven by large positive Δmakespan (+1 to +43 time units) and heavily inflated Δdelay
(+6 to +154 units).  The Mode-A/B-only decoder eliminates all movements (Δmov ≤ 0
everywhere, often exactly −7 to −19) but does so by packing aircraft later in time,
which pushes makespan and delay up relative to the MILP's tighter schedule.
`scn_none_tight_P5_R10` (no blocking constraints) ties perfectly at 0% — the
decoder produces the same solution as the MILP when there is no access-mode
interaction.  The single win is `scn_triangle_tight_P5_R30` (+15.8% mean gap),
where the MILP runs out of time at 60 s and returns an unconverged feasible solution;
the heuristic's Δmakespan = −54.9 and Δdelay = −676.1 there reflect genuine
schedule compression.

**wDLY (delay-priority).**  The pattern is similar but the headline numbers are
more extreme because delay carries weight 100.  Two instance types show
percentage gaps beyond −1000%: `scn_triangle_loose_P5_R10` (−2152%) and
`scn_triangle_tight_P5_R5` (−1323%).  Both are artefacts of small-denominator
inflation — the MILP achieves near-zero delay on these easy instances (see
Caveat 1 below), so a small absolute worsening (Δdelay = +25 or +5 units)
appears catastrophic in percentage terms.  `scn_full_tight_P5_R20` is the only
non-R30 type with a positive mean gap (+9.9%), but the min (−35.1%) shows the
heuristic only wins on some seeds.  `scn_triangle_tight_P5_R30` again leads at
+21.0%, with Δdelay = −770.2 units on average.

**wMOV (movement-priority).**  Under wMOV the decoder's zero-movement output is
its intended behaviour: Δmov = 0.00 for every instance type, meaning the heuristic
always matches the MILP's movement count (or the MILP cannot reduce movements
further because the decoder already found the floor).  However, the lack of
movement penalty does not fully compensate for higher makespan and delay — the
weighted objective is still worse on R5–R10 because the weight-1 makespan and
delay terms accumulate.  `scn_full_tight_P5_R20` shows the largest absolute
inflation (Δmakespan +103.7, Δdelay +579.6) while still losing the weighted race.
`scn_triangle_tight_P5_R30` wins again (+21.4%), with Δmakespan = −76.6 and
Δdelay = −721.3, again reflecting the unconverged MILP.

## Caveats

1. **Small-denominator inflation.**  The extreme percentage gaps for
   `scn_triangle_loose_P5_R10` (wDLY: −2152%) and `scn_triangle_tight_P5_R5`
   (wDLY: −1323%) arise because the MILP optimum delay ≈ 0 on those instances —
   dividing even a small absolute Δdelay (≈ +25 or +5 units from the Δ tables)
   by a near-zero denominator produces a large negative percentage.  Read the
   Δ tables alongside the gap tables for these rows.
2. **Unconverged MILP baseline at R20/R30.**  The heuristic "wins" on
   `scn_triangle_tight_P5_R30` (and some seeds of R20) because the cached MILP
   solution was not proven optimal within 60 s.  The positive gaps reflect
   "better feasible-in-60s" rather than proven improvement over the true optimum.
3. **Mode-A/B-only restriction.**  The decoder deliberately excludes Mode-C
   construction (movements allowed).  This floors Δmov at 0 across all profiles,
   which is the intended trade-off under wMOV, but it backfires under wMK and
   wDLY where movements have weight 1 and the MILP freely uses them to compress
   makespan and delay.  The gap under wMK and wDLY is fundamentally a
   Δmakespan/Δdelay problem, not a Δmov problem.

---

# Part III — Improvement roadmap

(empty until the human or solving agent writes a roadmap.)

## Diagnosis

(one paragraph: where the method stands today, what the residuals
look like, what is and is not addressable.)

## Priority 0 — Standard battery (three weight profiles)

(status: PLANNED.  Run the full battery to establish baseline numbers.)

## Priority 1 — Warm-start injection

(status: PLANNED.  `design.md §6` specifies reverse-encoding cached MILP
and topology JSONs into chromosomes for the initial population.  `warmstart.py`
not yet implemented.)

## Priority 2 — Mode-C construction (v2 lever)

(status: PLANNED / deferred.  Allowing Mode C as an additional candidate
widens the search space at the cost of front-schedule mutability.  Needs
a topological re-solve step for affected fronts.  Only worthwhile if the
battery shows Mode-B gaps are the bottleneck.)

## Metrics and ablations

(what to log; how to measure each priority item.)

## Recommended implementation order

1. Run standard battery — PLANNED
2. Implement `warmstart.py` — PLANNED
3. Ablate warm-start vs cold-start on wMK/wDLY/wMOV — PLANNED
4. Evaluate Mode-C construction benefit — PLANNED

---

# Part IV — How it is implemented

Source: [`theory_assisted_job.py`](theory_assisted_job.py) — class
`TheoryAssistedJobSolver`, registered under the labels `ta_brkga_wMK`,
`ta_brkga_wDLY`, `ta_brkga_wMOV`.

## Solver contract (`shared/application.py`)

| member | role |
| --- | --- |
| `name` | `"theory_assisted_job"` |
| `configure_solver(**kw)` | Stores all kwargs in `self._config`; honours `time_limit_s`, `weight_makespan`, `weight_delay`, `weight_movements`, `seed`, `pop_size` |
| `solve(instance)` | Constructs `DecoderContext`, calls `run_brkga`, returns best solution dict |
| `get_config()` | Returns a shallow copy of `self._config` |
| `get_log()` | Returns a copy of `self._log` (BRKGA shake + done events) |

### Config knobs

| key | default | meaning |
| --- | --- | --- |
| `time_limit_s` | `30.0` | Wall-clock time limit (Application guarantees to set this) |
| `weight_makespan` | `0.1` | Objective weight W^M |
| `weight_delay` | `1.0` | Objective weight W^D |
| `weight_movements` | `10.0` | Objective weight W^S |
| `seed` | `0` | RNG seed for BRKGA |
| `pop_size` | `max(100, 10 * n_keys)` | Population size; None = use BRKGA default |

## Method ↔ code map

| Method concept (Part I) | Code |
| --- | --- |
| Chromosome, length `2|R|` | `n_keys = 2 * ctx.n_air` in `TheoryAssistedJobSolver.solve` |
| Assignment genes → position | `decoder.decode`: `idx = min(int(assign_keys[i] * ctx.n_pos), ctx.n_pos - 1)` |
| Sequencing genes → service order | `decoder.decode`: `at_position[p].sort(key=lambda r: seq_of[r])` |
| Topological placement order | `DecoderContext._topo_order` (Kahn's algorithm on blocking DAG) |
| Front-aircraft lookup | `DecoderContext.fronts_of` (dict: rear position → list of front positions) |
| Job chain reconstruction | `DecoderContext._build_chains` (follows `job_precedences`, `is_first` flag) |
| Candidate start-time set | `decoder._candidate_starts` (earliest, Mode-A-after, gap-midpoints, safe-late) |
| Safe-late fallback (Mode A guaranteed) | `decoder._safe_late` |
| Local-cost evaluation + Mode classification | `decoder._evaluate` (calls `_classify_access` from `problems/jobs/checker.py`) |
| Cumulative-μ rule on Mode-B gaps | `decoder._evaluate`: `gap_uses` dict, `gap_size + 1e-9 < ctx.mu * total_uses` |
| Compact job-chain layout | `decoder._layout` (no internal idle) |
| Solution assembly + exact metrics | `decoder._assemble` (re-derives movements via `_classify_access` for checker consistency) |
| BRKGA engine | `brkga.run_brkga` |
| Elite / mutant / crossover partition | `brkga.run_brkga`: `n_elite`, `n_mutant`, biased crossover with probability `rho=0.70` |
| Shake on stagnation | `brkga.run_brkga`: `shake_after=50` stagnant generations |
| Warm-start injection | `brkga.run_brkga`: `warmstarts` parameter (not yet wired in solver) |

## Key implementation notes

- `decoder.py` imports `_classify_access` from `problems.jobs.checker` via package
  path (not bare `import checker`) to avoid ambiguity with the `problems/aircraft/`
  checker that also lives on `sys.path` in the batch runner.
- The candidate-start set is capped at `_MAX_CANDIDATES = 60` instants; if the raw
  set exceeds this, an evenly spaced subset is taken (first element always kept,
  last-index coverage preserved by the step formula).
- Mode C is never targeted by construction: `_evaluate` returns `None` for any
  candidate that would produce a Mode-C or infeasible classification, and the
  safe-late fallback guarantees the candidate set is always non-empty (Mode A).
- Movements are re-derived globally in `_assemble` via `_classify_access` rather
  than accumulated during placement, so the reported count is guaranteed consistent
  with the checker.  The local `gap_uses` tracking during placement is used only
  for the cumulative-μ feasibility check — it is not the movement counter.
- `run_brkga` logs shake events and the final generation count/objective to
  `self._log` via the `log` parameter; these are surfaced by `get_log()` and
  persisted by `Application.save_solution` to `data/logs_heuristic/`.
- `pop_size` defaults to `max(100, 10 * n_keys)` inside `brkga.py`; passing
  `pop_size=None` in the config (the default) uses this formula.

## Isolation

The solver imports nothing from other methods.  The lazy import path for
`_classify_access` targets `problems/jobs/` (allowed).
`experiments/tests/test_method_isolation.py` should report 0 violations.

## Smoke test

```
py -3 methods/theory_assisted/jobs/theory_assisted_job.py \
    data/instances_202605_02/scn_triangle_tight_P5_R5/scn_triangle_tight_P5_R5_seed1.json
```

Prints the checker report.  The solver hard-codes `time_limit_s=20` for the smoke
test.  The default instance path is
`data/instances_202605_02/scn_triangle_tight_P5_R5/scn_triangle_tight_P5_R5_seed1.json`.

---

# Change log

Track the method's evolution.  One row per behaviour-affecting commit
(or per shipped milestone), newest at the bottom.

| commit | change | effect on results |
| ------ | ------ | ----------------- |
| 2d37eeb | v06: initial BRKGA implementation — decoder (`decoder.py`), BRKGA engine (`brkga.py`), solver wrapper (`theory_assisted_job.py`); registered as `ta_brkga_wMK/wDLY/wMOV` in `run_experiments.py` | 360/360 feasible; loses to MILP on R5–R10 across all profiles (mean gap −19% to −59% wMK; extreme wDLY artefacts on near-zero-delay instances); wins only on unconverged-MILP R30 (+15.8/+21.0/+21.4% wMK/wDLY/wMOV); Δmov = 0 everywhere under wMOV as designed. |

---

*Keep this file in sync with `theory_assisted_job.py`: when the code
changes behaviour, invoke `/sync-method-doc methods/theory_assisted`
with a brief hint describing what changed and (if relevant)
`log: <battery-log-path>` for refreshing Part II.  Design rationale
and the reading behind the method live in [`notes/design.md`](notes/design.md)
and [`notes/synthesis.md`](notes/synthesis.md).*
