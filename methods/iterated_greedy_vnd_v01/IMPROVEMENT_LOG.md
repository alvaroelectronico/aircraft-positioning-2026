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
| 7 | profile-aware budget split (v2/v3 phases) | `exp/profile-budget` *(planned)* | *(pending)* | *(open)* | targets wMOV R5/R10 residual delay |
| 8 | profile-composed portfolio + biased-randomised construction | `exp/biased-construction` *(planned)* | *(pending)* | *(open)* | targets inter-start spread (variance) |

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

## Attempt 7 — profile-budget (OPEN)
- **Date:** 2026-07-13 (opened; coding not started)
- **Hypothesis:** the fixed 50/50 v2/v3 phase split wastes budget under
  wMOV, where the v3 polish almost never buys a manoeuvre. A
  profile-dependent split — under an effective wS-dominant objective, shrink or
  skip v3 and reinvest the time in more independent restarts — reduces the
  residual delay on wMOV R5/R10 without regressing wMK/wDLY (where v3 earns its
  half).
- **Ref:** branch `exp/profile-budget` off `dev` *(not yet created)*; baseline =
  tag `igvnd-v01-baseline-20260713` (`fc3ec71`).
- **How measured:** ablation arms {current 50/50, v2-only, v3-only,
  profile-split} on the wMOV R5/R10 stratum + wMK/wDLY controls; paired vs
  cached MILP; judged by **per-component Δdelay** (not relative gap, which
  inflates at small denominators) and by inter-start `obj_spread`.
- **Noise check:** against the Step-0 stratum floor (below), not the wMK
  19-unit figure.
- **Status:** blocked on Step 0.

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
