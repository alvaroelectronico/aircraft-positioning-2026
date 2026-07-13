# Improvement journal — `iterated_greedy_vnd_v01`

Attempt-anchored record of **every** effort to improve the heuristic, kept or
dropped. This complements the two other documentation layers:

- **Living spec** (`methods/iterated_greedy_vnd_v01/jobs/iterated_greedy_vnd.md`,
  Part I–IV) — the *current* method + latest battery.
- **Change log** (tail of that `.md`) — one row per *shipped/deferred commit*.
- **This journal** — one entry per *attempt*, opened with a hypothesis **before**
  coding and closed with a verdict, so dead ends leave a durable, linkable trace
  (their `exp/<slug>` branch + battery log) even when they ship no commit.

**Baseline / return point:** tag `igvnd-v01-baseline-20260713`
(290-instance battery `outputs/logs/combined_290_iterated_greedy_vnd_v01_20260628.log`;
solver behaviour = Commit 5 / `4a80e79`). Every attempt is measured against the
current `main` tip, and improvements are judged with the **cached-MILP rule** +
the **~19 delay-unit noise floor** described in [`BATTERY.md`](BATTERY.md).

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

*(Entries 4–6 backfilled from the living-spec Change log; entry 7 onward is
opened here first, before coding.)*

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
