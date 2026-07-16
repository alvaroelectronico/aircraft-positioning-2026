# Cross-method benchmark — paper #2 (job-level extension)

Side-by-side comparison of the heuristic methods currently developed
for paper #2, all measured on the **standard battery** defined in
[`experiments/BATTERY.md`](../experiments/BATTERY.md): 12 instance
types × 10 seeds × 3 weight profiles = 360 runs, 60 s budget per run,
instances under `data/instances_202605_02/`.

Each cell is the **mean relative gap over the 10 seeds**:

`gap = (MILP_obj − heuristic_obj) / MILP_obj`

Convention: **gap > 0 ⇒ heuristic better than the MILP**.  By
definition the MILP baseline has gap = 0; it is not shown as a column.

The numbers come verbatim from each method's living `.md` Part II
(no recomputation here).  See the **Source data** table below for the
specific battery log behind each column.

---

## Methods compared

| Column | Folder                                  | Algorithm                              | LLM assistant     | Candidate | State  |
| ------ | --------------------------------------- | -------------------------------------- | ----------------- | --------- | ------ |
| **v01**        | `methods/iterated_greedy_vnd_v01/` | Iterated Greedy + VND                  | ChatGPT (GPT-4)   | A         | frozen |
| **v02 IGVND**  | `methods/iterated_greedy_vnd_v02/` | Iterated Greedy + VND                  | Claude (Anthropic) | A        | frozen |
| **brkga_v02**  | `methods/brkga_v02/`               | BRKGA with mixed-chromosome decoder    | Claude (Anthropic) | C        | frozen |

The MILP baseline (`milp_baseline_job`, `milp_baseline_job_wB`,
`milp_baseline_job_wC`) is the reference; gap = 0 by definition.

`methods/autoresearch/jobs/` (an autoresearch loop on
`topology_heuristic_job`) is not included because it runs on its
own `fast_eval` (4 instances) / `validation` (12 instances) sets
with a different scoring system; its numbers live in
[`methods/autoresearch/jobs/ITERATIONS_SUMMARY.md`](autoresearch/jobs/ITERATIONS_SUMMARY.md)
and are not directly comparable to the standard battery rows below.

---

## Source data

| Column | Battery log | Code commit |
| ------ | ----------- | ----------- |
| v01        | [`instances_main_methods_20260614_114558_iterated_greedy_vnd_v01.log`](../outputs/logs/old/instances_main_methods_20260614_114558_iterated_greedy_vnd_v01.log) | `4a80e79` |
| v02 IGVND  | [`instances_main_methods_20260616_210727_iterated_greedy_vnd_v02_02.log`](../outputs/logs/old/instances_main_methods_20260616_210727_iterated_greedy_vnd_v02_02.log) | `7f53652` (v05 stack) |
| brkga_v02  | wMK/wDLY R5–R10: [`…_20260619_070616.log`](../outputs/logs/old/202605_02_main_methods_20260619_070616.log) (v2 Mode-C); wMOV: [`…_20260620_074942.log`](../outputs/logs/old/202605_02_main_methods_20260620_074942.log) (v3 P1-gated); wMK/wDLY R20/R30: [`…_20260621_074725.log`](../outputs/logs/old/202605_02_main_methods_20260621_074725.log) (P2 budget-honest) | `748c0a8` (P2) |

---

## wMK (100 / 1 / 1 — makespan-priority)

| Instance type                  |   v01   | v02 IGVND | brkga_v02 |
| ------------------------------ | ------- | --------- | --------- |
| scn_chain_tight_P5_R10         | −1.22%  | −2.26%    | −18.46%   |
| scn_full_tight_P5_R10          | +1.40%  | +1.32%    | −31.10%   |
| scn_full_tight_P5_R20          | **+41.21%** | **+38.78%** | −2.98% |
| scn_hub_tight_P5_R10           | −2.48%  | −2.13%    | −13.64%   |
| scn_none_tight_P5_R10          | +0.00%  | +0.00%    | +0.00%    |
| scn_triangle_loose_P5_R10      | +0.12%  | −1.54%    | −10.02%   |
| scn_triangle_medium_P5_R10     | +0.35%  | −1.73%    | −8.03%    |
| scn_triangle_tight_P5_R10      | −0.42%  | −0.86%    | −6.76%    |
| scn_triangle_tight_P5_R20      | **+17.20%** | **+16.57%** | **+7.47%** |
| scn_triangle_tight_P5_R30      | **+35.73%** | **+36.05%** | **+20.56%** |
| scn_triangle_tight_P5_R5       | −0.01%  | −0.04%    | −0.08%    |
| scn_two_rows_tight_P5_R10      | −0.15%  | −0.62%    | −5.15%    |

---

## wDLY (1 / 100 / 1 — delay-priority)

| Instance type                  |   v01    | v02 IGVND  | brkga_v02   |
| ------------------------------ | -------- | ---------- | ----------- |
| scn_chain_tight_P5_R10         | +7.02%   | −0.16%     | −23.52%     |
| scn_full_tight_P5_R10          | **+24.09%** | **+21.54%** | −21.35%  |
| scn_full_tight_P5_R20          | **+56.22%** | **+54.88%** | **+14.97%** |
| scn_hub_tight_P5_R10           | +3.56%   | +4.35%     | −11.05%     |
| scn_none_tight_P5_R10          | −0.00%   | −2.52% ‡   | −0.00%      |
| scn_triangle_loose_P5_R10      | −19.03% †| −160.02% † | −711.65% †  |
| scn_triangle_medium_P5_R10     | +5.48%   | +5.63%     | −11.34%     |
| scn_triangle_tight_P5_R10      | +6.01%   | +4.18%     | −7.79%      |
| scn_triangle_tight_P5_R20      | **+14.30%** | **+9.45%** | **+6.04%**  |
| scn_triangle_tight_P5_R30      | **+37.02%** | **+35.10%** | **+15.69%** |
| scn_triangle_tight_P5_R5       | −0.22%   | −44.50% †  | −3.22%      |
| scn_two_rows_tight_P5_R10      | +1.37%   | +1.11%     | −4.00%      |

---

## wMOV (1 / 1 / 100 — movement-priority)

| Instance type                  |   v01    | v02 IGVND  | brkga_v02  |
| ------------------------------ | -------- | ---------- | ---------- |
| scn_chain_tight_P5_R10         | −10.42%  | −18.51%    | −35.06%    |
| scn_full_tight_P5_R10          | −5.05%   | +3.54%     | −55.65%    |
| scn_full_tight_P5_R20          | **+26.32%** | **+33.95%** | −39.46% |
| scn_hub_tight_P5_R10           | −4.01% ‡ | −6.53% ‡   | −17.88%    |
| scn_none_tight_P5_R10          | +0.00%   | −2.85% ‡   | −0.06%     |
| scn_triangle_loose_P5_R10      | −0.02% ‡ | −7.47% ‡   | −57.48% ‡  |
| scn_triangle_medium_P5_R10     | +1.86%   | +2.99%     | −31.32%    |
| scn_triangle_tight_P5_R10      | +0.56%   | −1.36%     | −20.79%    |
| scn_triangle_tight_P5_R20      | **+11.98%** | **+12.60%** | −1.25%  |
| scn_triangle_tight_P5_R30      | **+35.30%** | **+34.28%** | **+22.93%** |
| scn_triangle_tight_P5_R5       | −3.88% † | −29.54% †  | −20.00% †  |
| scn_two_rows_tight_P5_R10      | +0.41%   | +0.29%     | −19.59%    |

---

## All profiles aggregated (30 runs per row: 10 seeds × 3 profiles)

| Instance type                  |   v01    | v02 IGVND  | brkga_v02   |
| ------------------------------ | -------- | ---------- | ----------- |
| scn_chain_tight_P5_R10         | −1.54%   | −6.98%     | −25.68%     |
| scn_full_tight_P5_R10          | +6.81%   | +8.80%     | −36.04%     |
| scn_full_tight_P5_R20          | **+41.25%** | **+42.54%** | −9.15%   |
| scn_hub_tight_P5_R10           | −0.98%   | −1.43%     | −14.19%     |
| scn_none_tight_P5_R10          | −0.00%   | −1.79%     | −0.02%      |
| scn_triangle_loose_P5_R10      | −6.31% † | −56.34% †  | −259.72% †  |
| scn_triangle_medium_P5_R10     | +2.56%   | +2.29%     | −16.89%     |
| scn_triangle_tight_P5_R10      | +2.05%   | +0.65%     | −11.78%     |
| scn_triangle_tight_P5_R20      | **+14.49%** | **+12.88%** | **+4.09%** |
| scn_triangle_tight_P5_R30      | **+36.02%** | **+35.14%** | **+19.73%** |
| scn_triangle_tight_P5_R5       | −1.37%   | −24.69% †  | −7.77%      |
| scn_two_rows_tight_P5_R10      | +0.54%   | +0.26%     | −9.58%      |

---

## Reading

**By size**

- **R5 (`triangle_tight_R5`)** — the MILP solves to optimality
  everywhere; the three heuristics roughly match it (within a few
  absolute units of objective).  Negative percentages on
  `triangle_R5 wDLY` are small-denominator artefacts (MILP delay
  ≈ 0; see Caveats).
- **R10 (eight types)** — the MILP is converged or near-converged.
  v01 and v02 IGVND are competitive (mostly within ±5 % of the MILP);
  brkga_v02 trails by 5–35 % consistently.  Under wDLY, IGVND wins
  modestly on dense topologies (`full_R10` +21–24 %); under wMOV all
  three match the MILP at zero movements on most rows.
- **R20 / R30 (three types)** — the MILP is **unconverged** (80–99 %
  optimality gap at the 60 s budget).  v01 and v02 IGVND win
  decisively (+15 to +56 %).  brkga_v02 wins on `triangle_R30` across
  all three profiles (+16 to +23 %) and on `triangle_R20 wDLY`
  (+6 %) and `full_R20 wDLY` (+15 %), but trails on `full_R20 wMK`
  and `wMOV`.

**By LLM assistant (same task, same scaffold)**

- v01 (ChatGPT) and v02 IGVND (Claude) implemented the *same*
  candidate (A = IG+VND).  The numbers are within run-to-run noise of
  each other on every row except `triangle_R5 wDLY`/`wMOV`,
  `triangle_loose_R10 wDLY`, and `chain_R10 wDLY` — all
  small-denominator rows.  Conclusion: under the IG+VND blueprint,
  ChatGPT and Claude converge to essentially the same quality.
- brkga_v02 (Claude, Candidate C) is **dominated** by the IG+VND
  methods on R5–R10 across all three profiles, and on R20 wMK/wMOV.
  It only matches IGVND on R30 (where the MILP is most unconverged).
  Under the same 60 s budget, the BRKGA population approach finds
  fewer high-quality moves than the IG+VND single-trajectory
  approach.  The replication attempt under `methods/theory_assisted/`
  will say whether this is a property of the algorithm family or of
  the specific Claude implementation.

**By weight profile**

- **wMK** — IGVND ties the MILP on small instances and dominates on
  large; brkga_v02 trails everywhere except R30.
- **wDLY** — same shape as wMK with a slightly stronger advantage on
  `full_R10` (IGVND +21–24 %).  Watch the small-denominator † rows.
- **wMOV** — IGVND keeps movements ≈ 0 like the MILP and wins on
  large instances; brkga_v02 paid the decoder fixpoint cost on
  earlier versions but v3-P1-gated still trails on most rows except
  R30 (where unconverged-MILP gaps dominate).

---

## Caveats

1. **Small-denominator inflation** (marked †, ‡).  On slack (`loose`),
   tiny (`R5`), no-blocking (`none`) instances, or 0-movement
   profiles, the MILP optimum value is near 0 on the dominant term —
   a few absolute units of difference read as huge percentages.
   `triangle_loose_R10 wDLY` shows −160 % for v02 IGVND but the
   absolute Δdelay is only ≈ +1.1 units.  Always cross-read the
   per-component Δ tables in each method's Part II.
2. **MILP unconverged at scale.**  At R20 / R30 the MILP's 60 s
   incumbent has an 80–99 % optimality gap.  Heuristic "wins" there
   mean "better feasible solution within the same budget", not
   proven superiority over the true optimum.
3. **Run-to-run noise.**  All three heuristics are time-limited and
   non-deterministic at the 60 s cut.  Noise floor on this battery
   ~19 delay units; deltas smaller than that (and ±-flips in
   min/max columns) are noise, not signal.
4. **brkga_v02 logs split.**  brkga_v02 's three log files reflect
   the v2 (initial Mode-C) → v3 (P1 profile-gated Mode-C) → P2
   (budget-honest re-battery on large R) trajectory; the numbers
   above are the most recent values per (profile, size) per
   `brkga_v02/jobs/brkga.md` Part II.
5. **v01 log was renamed.**  `iterated_greedy_vnd_v01/jobs/iterated_greedy_vnd.md`
   still cites `…_20260614_114558.log` (no suffix); the actual file
   in `outputs/logs/` is `…_20260614_114558_iterated_greedy_vnd_v01.log`.
   Updating v01's doc would be a doc-cleanup edit; left alone here
   to keep this file the only one touched in this commit.

---

## Where the cells come from

| File                                                                 | Used in column |
| -------------------------------------------------------------------- | -------------- |
| [`iterated_greedy_vnd_v01/jobs/iterated_greedy_vnd.md`](iterated_greedy_vnd_v01/jobs/iterated_greedy_vnd.md) Part II | v01            |
| [`iterated_greedy_vnd_v02/jobs/iterated_greedy_vnd.md`](iterated_greedy_vnd_v02/jobs/iterated_greedy_vnd.md) Part II | v02 IGVND      |
| [`brkga_v02/jobs/brkga.md`](brkga_v02/jobs/brkga.md) Part II         | brkga_v02      |

When any of those Part II sections is refreshed (via
`/sync-method-doc … log: <new>`), the corresponding column above
may go stale.  Re-generate this file at the same milestone (or
add a row to the Source data table if a new method is added).
