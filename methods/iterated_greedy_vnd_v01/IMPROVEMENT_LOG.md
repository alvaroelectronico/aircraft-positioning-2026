# Improvement journal — `iterated_greedy_vnd_v01`

Attempt-anchored record of **every** effort to improve the heuristic, kept or
dropped. This complements the two other documentation layers:

- **Living spec** ([`jobs/iterated_greedy_vnd.md`](jobs/iterated_greedy_vnd.md),
  Part I–IV) — the *current* method + latest battery.
- **Change log** (tail of that `.md`) — one row per *shipped/deferred commit*.
- **This journal** — one entry per *attempt*, opened with a hypothesis **before**
  coding and closed with a verdict, so dead ends leave a durable, linkable trace
  (their `exp/<slug>` branch + battery log) even when they ship no commit.

**Baseline / return point:** tag `igvnd-v01-baseline-20260713`
(290-instance battery `outputs/logs/combined_290_iterated_greedy_vnd_v01_20260628.log`;
solver behaviour = Commit 5 / `4a80e79`). Every attempt is measured against the
current `main` tip, and improvements are judged with the **cached-MILP rule** +
the **~19 delay-unit noise floor** described in
[`experiments/BATTERY.md`](../../experiments/BATTERY.md).

## How to use

1. Before coding: `git switch -c exp/<slug>` off `dev`; add a row to the index
   and an `## Attempt` block below with the **hypothesis** and how you'll measure it.
2. Run `/run-battery` or `ablation_subset.py`, pair vs cached MILP
   (`paired_report.py` / `gap_summary.py`).
3. Close the entry: **verdict** (KEPT / DROPPED / NEUTRAL-within-noise), the
   battery log path, and the net effect. Apply the noise floor — a delta below
   the run-to-run spread is NEUTRAL, not an improvement.
4. If KEPT: merge `--no-ff` into `main`, tag `igvnd-v01-<milestone>`, run
   `/sync-method-doc`. If DROPPED: keep the `exp/` branch and add a Change-log
   "attempted & DROPPED" row.

## Index

| # | attempt | branch / tag | battery/ablation log | verdict | net effect |
| - | ------- | ------------ | -------------------- | ------- | ---------- |
| 4 | dense concentric-nesting builder (wMOV) | `cb5656c` | `…_20260613_235129.log` | **KEPT** | `full_R10 wMOV` −17.1% → **−5.05%** |
| 5 | risk diagnostics (delay/nesting/search) | `dd20bf6` | `combined_290_iterated_greedy_vnd_v01_20260628.log` | **KEPT** | observability only, no behaviour change |
| 6 | DelayRiskRepair (delay-biased re-search) | `95669a2` → reverted `4a80e79` | `ablation_commit6_delayrepair.txt` | **DROPPED** | 0/74 runs accepted; residual is search-variance-bound, within noise |
| 7 | restarts-until-deadline + slim portfolio (NEH+SLACK) + biased-randomised construction | `exp/restart-budget` (`76d43e0`) | `attempt7_restart_budget_20260713.txt` | **KEPT** (pending merge) | wMOV R5/R10 stratum −3.79 % → **+0.00 % = MILP optimum on every cell**; no guard regressed |
| 8 | phase policy: v2/v3 split vs single decoder (4-arm ablation) | `exp/profile-budget` (`6952f14`) | `attempt8_phase_policy_20260714.txt` + `attempt8b_noise_resolution_20260714.txt` | **DROPPED** | two decoders earn their keep: v3-only regresses at R20 (+377/+1933 real); v2-only/split refuted (wMOV +20/+9.5 real) |

*(Entries 4–6 backfilled from the living-spec Change log; entry 7 onward is
opened here first, before coding. The 2026-07 campaign that motivates 7–8 is
documented below, after the template.)*

---

## Attempt template (copy for each new attempt)

```markdown
## Attempt <N> — <slug>
- **Date:** <YYYY-MM-DD>
- **Hypothesis:** <what change, why it should help, which profile/config it targets>
- **Ref:** branch `exp/<slug>` (tip <sha>); baseline = tag `igvnd-v01-<prev>` / <sha>
- **How measured:** ablation_subset.py on <stratum> | /run-battery <scope>; paired vs
  cached MILP; <N> seeds
- **Log:** outputs/logs/<file>.log
- **Result vs baseline:** <config/profile> <before> → <after> (<IMPROVED/REGRESSED/NEUTRAL>)
- **Noise check:** delta <x> vs ~19 delay-unit floor (chain_R10 wMK) → <real / within noise>
- **Decision:** KEPT (merged main, tagged `igvnd-v01-<milestone>`, sync-method-doc)
               | DROPPED (exp/ branch retained; Change-log "attempted & DROPPED" row)
```

---

# Campaign 2026-07 — profile-aware search & variance reduction

Opened 2026-07-13 off the `igvnd-v01-baseline-20260713` tag (290-instance battery
`combined_290_iterated_greedy_vnd_v01_20260628.log`). This section records the
diagnosis and the plan; each concrete attempt (7, 8, …) is a `## Attempt` block
below, opened with its hypothesis **before** coding.

## Diagnosis (code review + 290-instance battery, 2026-07-13)

Structural gaps found in the solver, cross-checked against results:

1. **Representation ceiling of the zero-movement decoder.** `_decode` is
   earliest-fit with jobs packed tight, so it cannot *stretch* a stay with
   inter-job idle to enable nesting — schedules the MILP reaches are outside
   the reachable set of any `(π, σ)`. `_dense_nest_solution` patches only the
   complete-graph case with a rigid wave model (positions by fixed depth, all
   wave members nested even when they do not mutually block, whole waves
   serialised); on chain/hub/triangle that model is wrong or over-conservative,
   so the candidate is discarded there and the ceiling persists.
2. **Myopic v3 decoder.** `_place_front` minimises only the local per-aircraft
   cost; rears are fixed (deep-first) and never revisited; candidate starts
   align **one** access τ at a time, so multi-access alignments arise only by
   accident. No feedback pass re-places a rear given the front outcome.
3. **No incremental evaluation.** Every VND move re-decodes from scratch
   (decode is O(R²); a `_n_swap_pos` sweep is O(R⁴)); the cache only helps exact
   revisits. Because the decode places in σ order, changing the aircraft at
   rank k only invalidates the suffix from k — a prefix-incremental decode is
   within reach and would multiply search-per-second. Evidence it bites: R30
   runs always finish `timed_out=True` with 3–12 % inter-start spread (search
   truncated, not converged).
4. **Elementary, biased neighbourhoods.** Only transpositions (reassign-1,
   swap-positions, swap-in-σ). Missing the standard **insertion** move (extract
   an aircraft, reinsert at any σ rank), which dominates swap in flowshop.
   First-improvement always scans in the same id order (deterministic bias; no
   don't-look bits, no scan randomisation).
5. **Profile-blind destruction.** `_perturb` scores `wD·delay + 1e-3·T`; under
   wMK/wMOV (delays ≈ 0) that degenerates to "almost always the same longest
   k+2, shuffled" — never targets the makespan-defining aircraft nor the
   critical-path blocker. `k_destroy` fixed at R/4.
6. **Fixed 50/50 phase budget, profile-blind.** `_one_start` always spends half
   the time on the v3 polish; under wMOV v3 almost never buys a manoeuvre
   (2 events = 400 objective points), so ~half the budget re-searches the same
   landscape with a costlier decoder instead of doing more restarts.

What the results say (evidence, not just structure):

- **The only defeat against a *converged* optimum is wMOV on small R5/R10
  tight, and it is variance, not packing.** On `triangle_tight_R5 wMOV` the bad
  seeds match the MILP makespan **exactly** (32↔32, 43↔43) at 0 movements, and
  leave only residual delay (7 vs 1, 4 vs 0) on ~30–45 objectives — the
  relative gap inflates it. Internal diagnostic confirms: seed9 `obj_spread`
  across the 8 starts is **1.01** (worst start ≈ 2× the best) on a 5-aircraft
  instance. Landscape under (1,1,100) with movements already 0 is near-flat and
  the search wanders — the Commit-6 "search-variance-bound" phenomenon, but here
  in wMOV where there *is* a real loss vs a converged optimum.
- **At scale (R20/R30) we cannot tell how much headroom remains** — the MILP is
  unconverged (80–99 % gap) or OOM, so "+40 %" does not locate us vs optimum.
  This is a *measurement* gap, not an algorithm gap.
- **wMOV residuals on chain/hub R10 (−10.4 %/−4.0 %)** are vs an unconverged
  MILP and the schedules are already nested (`serial_points 1/10`) — not a
  reliable target; do not chase.

## User's four ideas, reviewed critically (2026-07-13)

1. *Single phase based on v3, letting weights modulate movement generation.*
   Correct that v3 ⊇ v2 in coverage and already prices movements by weight. But
   v2 exists for **cost**, not coverage (cheaper decode → more search/s;
   Commit-4 attempt 1 regressed wMK purely by slowing the decode). Reframe as a
   **profile-dependent budget split** (Attempt 7), tested against v2-only /
   v3-only / current as ablation arms — let data decide, don't assume.
2. *Keep all six construction rules? Select by weights?* Rules are already
   half weight-aware (the insertion greedy prices the weighted objective; only
   the insertion *order* is profile-blind). Real asymmetry: 4 due-date rules,
   1 makespan, **0 nesting/movement rule** — the weak profile has no seed of its
   own. Composing the portfolio by profile makes sense, with one caveat: rule
   diversity is also the anti-variance mechanism (Commit-3 lesson), so selecting
   rules must not cut the restart count.
3. *Biased-randomised construction (GRASP-style).* Best fit for the diagnosis:
   if losses are variance-bound, the lever is **unlimited diverse restarts**;
   today starts 7–8 repeat a rule and differ only in the perturbation RNG. A
   rank-biased (geometric) pick over the rule-sorted list (RCL helpers already
   in `shared/`) gives diversity without hurting the mean. Direct synergy with
   idea 1: budget freed from v3 under wMOV feeds these restarts.
4. *Normalise weights × magnitudes.* Right in principle — (1,1,100) with
   movements at 0 is effectively a 1:1 makespan+delay objective, and the current
   gates use raw weights (`wS >= wM and wS >= wD`), which is fragile for unseen
   weight combos. But as a standalone experiment it is **not measurable** (only
   3 fixed profiles in the battery, and normalisation alone moves no numbers).
   Implement it as **gating infrastructure** inside Attempts 7–8: after the
   first decode, estimate effective importance ŵᵢ = wᵢ · typical-term-magnitude
   and drive the phase split / portfolio with it. Caveat: normalise the *policy*
   decisions, **not** the internal search objective (else we optimise something
   other than what we report).

## Roadmap

- **Step 0 (no code, on `dev`):** measure the run-to-run noise floor of the
  target stratum (wMOV R5/R10). The documented ~19-delay-unit floor was measured
  on wMK; the effects we chase here are 1–7 delay units and we must know if they
  are distinguishable. Key sub-question: do small (R5) runs *converge* within
  60 s (deterministic run-to-run → residual is a real search-quality gap, a
  clear Attempt-7 target) or do they wander (noise-bound → the lever is variance
  reduction)?
- **Attempt 7 — `exp/profile-budget`** (idea 1 + finding #6, idea 4 as gating):
  profile-dependent phase-budget split; ablation arms = current / v2-only /
  v3-only / profile-split; non-regression guards on wMK/wDLY.
- **Attempt 8 — `exp/biased-construction`** (ideas 2 + 3): profile-composed
  portfolio + biased-randomised insertion order; opened after 7 (its payoff
  depends on how many restart slots 7 frees).
- **Parked (recorded):** v3-only as the definitive single phase (decided by the
  Attempt-7 arm data); prefix-incremental decode (finding #3 — the scale lever,
  larger effort; worth it once R20/R30 has a better measurement reference).

---

## Attempt 7 — restart-budget (OPEN)
- **Date:** 2026-07-13 (opened after Step 0; design agreed with the user —
  simplicity is an explicit acceptance criterion: the change must REMOVE parts,
  not add them)
- **Hypothesis:** the wMOV R5/R10 residual delay is a real, deterministic gap
  caused by a capped, non-diverse restart set that leaves ~97 % of the 60 s
  budget idle (Step 0). Looping restarts **until the deadline** and diversifying
  them with **rank-biased randomised construction** finds the better basin the
  8 fixed starts miss (`triangle_tight_R5 seed5` 38 → towards MILP 33).
- **Design (agreed):**
  1. *Loop shape:* `while time remains: run one start`. The `n_starts` cap is
     removed (per-start slice kept as today, `time_limit / (8|4|3)`, so R20/R30
     behaviour is unchanged — the slice never binds on R5 where starts end by
     `max_no_improve` in ~0.15 s). Nets out: −1 knob.
  2. *Slim portfolio:* first two starts = deterministic NEH + SLACK. All later
     starts = **one** mechanism: geometric rank-biased sampling of the insertion
     order, base = the better-scoring of the two deterministic seeds. Removes
     EDD / CR / BLEND / regret-2 (the costliest constructor). Nets out: −4 rules,
     +1 sampler.
  3. *Not touched:* v2/v3 phases (Attempt 8), independent restarts (Commit-3
     lesson), dense-nest, VND, IG perturbation.
- **Ref:** branch `exp/restart-budget` off `dev` (`66eaefc`); baseline =
  tag `igvnd-v01-baseline-20260713` (`fc3ec71`).
- **How measured:** both arms run FRESH back-to-back on a quiet machine (Step 0
  found cached igvnd rows stale and results load-sensitive): baseline (dev) vs
  candidate (branch) on the wMOV R5/R10 stratum + wMK/wDLY/R20 guards; paired vs
  cached MILP rows only. Judged by **per-component Δdelay/Δmakespan** and
  inter-start spread.
- **Noise check:** stratum floor = 0 (Step 0) → any ≥ 1 delay-unit gain is real;
  wMK/R10 guard judged against its ~16–19-unit floor.
- **Log:** [`outputs/logs/attempt7_restart_budget_20260713.txt`](../../outputs/logs/attempt7_restart_budget_20260713.txt)
  (both arms fresh, in-process, 60 s, seed=1; MILP from cached results.csv).
- **Result vs baseline (implementation `76d43e0`):**
  - **Target wMOV R5 (11 cells): mean gap vs MILP −3.79 % → +0.00 % — the
    candidate matches the MILP optimum on EVERY cell.** All misses eliminated:
    seed3 33→32, seed5 38→33 (dly 6→1), seed6 47→39 (dly 8→0), two_rows s10
    36→35. Restarts 8 → ~830–915 per run.
  - **Target wMOV R10:** 167.5 → 166.0 **= MILP exactly** (−0.90 % → 0.00 %).
  - **Guards — none regressed:** control `none wMK` identical (5844.5);
    noisy `chain_R10 wMK` −92.5 (improved, within its ~72-unit floor);
    wDLY guards −1.0 / −11.0 (improved); **extra guard** `triangle_tight_R5
    seed10 wDLY` (the historical due-date-seed case, Commit 2) intact at
    35.0 = MILP with the slim portfolio; scale `triangle_tight_R20 wMK`
    +59.0 on 12 960 (+0.45 %, within run-to-run noise at that size — both
    arms still beat the unconverged MILP by ~+16 %).
- **Noise check:** target deltas (−1, −5, −8, −1.5) are on a floor-0 stratum →
  all REAL. The only adverse delta (+59 scale) is 0.45 % on a cell whose
  run-to-run noise band is larger → neutral.
- **Decision: KEPT.** Simplicity ledger: −1 knob (`n_starts` cap → optional
  test-only), −4 construction rules (EDD/CR/BLEND/regret-2), +1 mechanism
  (`_biased_order`, ~15 lines). Net: the solver is smaller than before.
  Merged `--no-ff` into `main` (`cbf64c7`) + tag
  `igvnd-v01-restart-budget-20260713` + spec synced.
- **Full-battery confirmation (2026-07-14,
  log `202605_02_main_methods_20260713_211851.log`, 870 runs / 0 failures,
  code `cbf64c7`):** R5 closed across ALL profiles (wMK/wMOV exact on every
  config 10/10; wDLY 8–10/10, worst −3 %); R10 wMOV residuals vs unconverged
  MILP shrank (chain −10.4→−8.3, hub −4.0→−3.7, full −5.1→−3.4); R20/R30
  unchanged (+5 % to +42 %). Watch-item for Attempt 8: `triangle_loose_R10
  wMOV` −0.02→−4.08 % (3/10 seeds concede 5–16 absolute units on timed-out
  cells); `triangle_loose_R10 wDLY` −33.8 % mean is the known Δdelay ≤ 1.5-unit
  denominator artifact (heuristic wins 5/10 seeds there). Part II of the
  living spec refreshed from this log.

### Step 0 — noise-floor measurement (DONE 2026-07-13)
- **Goal:** run the wMOV R5/R10 stratum twice with identical seeds at the
  production 60 s budget; the per-instance objective spread is the noise floor
  for this stratum. Also record whether R5 runs converge (deterministic) or
  wander.
- **Log:** [`outputs/logs/step0_noise_floor_20260713.txt`](../../outputs/logs/step0_noise_floor_20260713.txt)
  (in-process solver, seed=1, 60 s, K=2 repeats/cell).
- **Results:**

  | cell | prof | run-to-run obj_spread | dly_spread | verdict | inter-start spread | wall |
  | --- | --- | --- | --- | --- | --- | --- |
  | triangle_tight_R5 seed3 | wMOV | 0.0 | 0.0 | converged | 0.864 | 1.2 s |
  | triangle_tight_R5 seed5 | wMOV | 0.0 | 0.0 | converged | 0.421 | 1.5 s |
  | triangle_tight_R5 seed9 | wMOV | 0.0 | 0.0 | converged | 1.012 | 1.3 s |
  | two_rows_tight_R5 seed10 | wMOV | 0.0 | 0.0 | converged | 0.444 | 1.0 s |
  | triangle_tight_R10 seed1 | wMOV | 0.0 | 0.0 | converged (timed out) | 0.033 | 60 s |
  | **chain_tight_R10 seed1** | **wMK** | **72.0** | **16.0** | **wanders** | 0.047 | 60 s |

- **Conclusions:**
  1. **The whole wMOV R5/R10 stratum is deterministic run-to-run (floor = 0)** —
     even the timed-out R10 cell gives identical objectives across runs. So the
     residuals vs MILP here are **REAL search-quality gaps, not noise**, and any
     improvement ≥ 1 delay unit is cleanly measurable.
  2. **The one wandering cell is the wMK/R10 control** (obj_spread 72 ≈ 16 delay
     units run-to-run), which **reproduces the documented ~19-unit floor** and
     confirms that floor is a **wMK-at-R10 phenomenon, not a wMOV-R5 one**. Good:
     the control validates the measurement.
  3. **The small-instance wMOV gap is caused by an idle budget, not by time
     pressure.** R5 runs converge in ~1–1.5 s doing exactly `n_starts=8` starts
     and then **stop with ~58 s (97 %) of the 60 s budget unused** (the `solve`
     loop is `while … and i < n_starts`). `seed5` best-of-8 = 38 (dly 6) while
     MILP = 33 (dly 1) — **makespan already matches (32=32)**, so it is a pure
     +5 delay gap left on the table with the budget almost entirely idle, and
     the 8 starts disagree (inter-start spread 0.4–1.0), i.e. a better basin
     exists but the capped, non-randomised restart set never reaches it.
  4. **Measurement caveat found:** fresh `seed9` = 43 (= MILP) but the cached
     battery row was 47 (−9.3 %). Step 0 is perfectly deterministic here, so the
     cached igvnd row is **stale** (different code state). ⇒ the ablation MUST
     re-run the heuristic fresh and only reuse the cached **MILP** rows — which
     `ablation_subset.py` already does. Do not trust cached igvnd objectives.

## Attempt 8 — profile-budget / phase policy (OPEN)
- **Date:** 2026-07-14 (opened; hypothesis before coding)
- **Hypothesis:** on the cells that exhaust the 60 s budget (R10+ under
  blocking; R5 is unaffected — its restarts end on the stale counter), the
  fixed 50/50 v2/v3 phase split is not the best use of time. Either a single
  decoder (v3-only, since v3 ⊇ v2 in coverage — user's idea 1, the
  simplification) or a profile-dependent split (skip v3 when effective-wS
  dominates, since v3 rarely buys a manoeuvre there) beats the current split
  on the timed-out stratum. The ablation decides **one decoder or two** with
  data.
- **Design:** add a `phase_mode` config knob — `both` (current), `v2`
  (zero-movement only), `v3` (single decoder: no phase-1 search; the raw v2
  decode of each seed remains the feasibility floor for the safety net).
  Run 4 arms {both, v2, v3, profile-split (v2 under wS-dominant, both
  otherwise)} fresh, back-to-back, on the timed-out stratum: the
  `triangle_loose_R10 wMOV` certified-optimum losses (seeds 5/7/10), chain/hub
  R10 wMK+wMOV, triangle_tight_R10 (3 profiles), one R20 scale cell + the
  `none_R10` control. Judged per-component vs cached MILP; simplicity is the
  tie-break: **if v3-only ≥ both, ship one decoder** (−1 phase).
- **Ref:** branch `exp/profile-budget` off `dev` (`1587242`); baseline = tag
  `igvnd-v01-restart-budget-20260713`.
- **Noise check:** wMK/R10 floor ≈ 16–19 delay units (Step 0); wMOV R10
  deterministic (floor 0); R20 judged loosely (band unknown).
- **Logs:**
  [`attempt8_phase_policy_20260714.txt`](../../outputs/logs/attempt8_phase_policy_20260714.txt)
  (4 arms × 14 cells) +
  [`attempt8b_noise_resolution_20260714.txt`](../../outputs/logs/attempt8b_noise_resolution_20260714.txt)
  (both vs v3, K=3, on the noise-ambiguous cells).
- **Result:**
  - `v2-only` and `split` **refuted** on deterministic wMOV cells: real
    regressions +20 (`t_loose_R10 seed6`) and +9.5 (seed9); `v2` also +2023
    on `chain wMK` (no manoeuvre machinery — expected).
  - `v3-only` (the single-decoder simplification): mixed on the target
    stratum — real wins on `t_loose_R10 seed7` (**62.5, beats the MILP's
    integer-gridded optimum 64.5**) and seed10 (−1.5), real loss on seed9
    (+9.5). The 8a scale deltas were noise-ambiguous, so 8b re-ran K=3:
    `tri_tight_R10 wMK` +7.3 (within noise), but **R20 wMK +377 and R20 wDLY
    +1933 are REAL regressions** (v3 is perfectly deterministic at R20 —
    spread 0 across repeats — because its costly decode leaves so little
    search per slice; the cheap v2 phase is what makes scale work).
- **Decision: DROPPED.** The pre-registered rule was "ship one decoder iff
  v3-only ≥ both"; it is not (real R20 regressions). The two-phase design
  earns its keep with data. The `phase_mode` knob stays on the `exp/` branch
  as ablation infrastructure (no behaviour change shipped to `main`).
  Side-finding for a future attempt: on the certified-loss cells the v3-only
  arm shows the *search*, not the decoder, is the binding constraint (seed7
  62.5 exists and `both` misses it) — consistent with the stay-stretching
  gap being the real target.

## Attempt 9 — nest-stretch (OPEN)
- **Date:** 2026-07-14 (opened; hypothesis before coding)
- **Hypothesis:** the certified-optimum losses (`triangle_loose_R10 wMOV`,
  3/10 seeds, 5–16 units) are caused by the dense-nest candidate's rigid
  complete-graph wave model: it nests ALL wave members concentrically and
  serialises whole waves, so on non-complete topologies its candidate is
  wasteful and loses the best-of. **Generalising the same builder to the real
  blocking DAG** — concentric stay-stretching only along actual arcs (deepest
  rear = outermost, stays stepped by 2η along each front→rear chain, verified
  mechanism of the seed7 optimum), unconflicted positions tight and parallel,
  rounds serialised per blocking component — recovers those losses.
  **Simplicity ledger: net 0** (replaces the existing `_dense_nest_solution`
  internals; same gate `wS`-dominant + arcs, same two-partition beam, same
  best-of + checker safety).
- **Ref:** branch `exp/nest-stretch` off `dev` (`8aa06b6`); baseline = tag
  `igvnd-v01-restart-budget-20260713`.
- **How measured:** two arms fresh (dev vs branch), 60 s, seed=1:
  `triangle_loose_R10 wMOV` all 10 seeds (3 losses + 7 ties/wins as guards),
  `triangle_tight_R10 wMOV`, `full_tight_P5_R10 wMOV` (the complete-graph
  case the old builder owned — must not regress), chain/hub wMOV, one R5 wMOV
  spot, R20 wMOV scale guard. Judged per-component vs cached MILP (all
  R10-loose wMOV MILP rows are certified optimal).
- **Noise check:** wMOV stratum deterministic (floor 0, Step 0) → ≥ 1-unit
  deltas are real.
- **Status:** implementing.

### Revised plan after Step 0 (2026-07-13)

Step 0 **reorders** the attempts. The user's headline problem (poor on small
triangulars) is a *real, deterministic* gap whose immediate cause is a **capped,
non-diverse restart set leaving 97 % of the budget idle** — not the v2/v3 phase
split. So the direct fix moves first:

- **Attempt 7 (was 8) — `exp/restart-budget`:** exhaust the idle budget with
  **more, more-diverse restarts** — remove/raise the `n_starts` cap so small
  instances keep restarting until the deadline, and diversify restarts with
  **biased-randomised construction** (rank-geometric pick over the rule-sorted
  list; RCL helpers in `shared/`). Direct target: wMOV R5 residual delay
  (`seed5` 38→33). Cleanly measurable (floor = 0 on this stratum). Guards:
  no wMK/wDLY regression; the wMK/R10 control (16-unit floor) bounds "real".
- **Attempt 8 (was 7) — `exp/profile-budget`:** profile-dependent v2/v3 phase
  split, targeting the **timed-out** R10+ cells where reallocating v3's half
  matters (R5 does not time out, so the split is irrelevant there). Opened after
  7, since 7 changes how the budget is spent.
- **Parked (unchanged):** v3-only single phase; prefix-incremental decode.

The idea-4 normalisation stays as gating infrastructure inside Attempt 7 (decide
"effective wS-dominant" from ŵᵢ·magnitude, to trigger the restart policy).
