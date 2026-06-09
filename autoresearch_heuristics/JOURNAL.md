# JOURNAL — autoresearch loop on `topology_heuristic_job`

Rolling log of every iteration of the loop.  One entry per attempted variant, **including rejected ones** (we want to know what didn't work, not just what did).

Format per entry:

```
## iter_NNNN_<slug>  (accepted | rejected)
*YYYY-MM-DD HH:MM*  score X.XX  (best Y.YY)

<one paragraph: hypothesis, what changed, why it (didn't) work, lesson>
```

Entries are appended by `snapshot.py save`, never edited by hand.

## iter_0000_baseline  (accepted)
*2026-06-05 12:28*  score +3.9146  (best +inf)

- Construction-only heuristic leaves >390% mean gap to the MILP on `fast_eval`
  even with all three instances compliant — there is a lot of room for LS.
- The `fast_eval` score is dominated by the smallest instance because its
  MILP-incumbent denominator is tiny (3.0); a single LS pass that removes

## iter_0001_ls_portfolio  (accepted)
*2026-06-05 12:50*  score +0.1256  (best +3.9146)

- The compliance gate is **essential**: without it the 2-opt swap found
  large objective drops on chain_R10 (obj 294.8 → 147.0) and triangle_R5
  (obj 35.0 → 3.0) but both produced infeasible solutions.  The Mode-A
  rebuild's `_resolve_*` helpers do not enforce every checker constraint;

## iter_0002_ls_intra_pos_extra  (rejected)
*2026-06-05 17:23*  score +0.1256  (best +0.1256)

- The current `fast_eval` set is too small to reward intra-position
  reordering: on R≤10 with at most 2 aircraft per position, ops 4–6
  collapse to no-ops or are dominated by ops 1–3.  The operators are
  valuable but their value is invisible to the iteration metric.

## iter_0003_lns_perturbation  (accepted)
*2026-06-05 17:26*  score +0.0958  (best +0.1256)

- LNS is a genuine basin-escape mechanism for `hub_R10`: it found a
  better incumbent after the initial LS converged (12.2 obj units, all
  from delay reduction).
- `chain_R10` remains stubborn — neither the LS portfolio nor 20 s of

## iter_0004_lns_plus_extra_ops  (rejected)
*2026-06-05 17:29*  score +0.0958  (best +0.0958)

- The 6-operator LS portfolio + random-destroy LNS has now plateaued
  on `fast_eval` at the same incumbent the basic 3-op LS reached for
  chain_R10.  Further single-aircraft / pair / intra-position moves
  cannot break 199.40, no matter how many basins LNS visits.

## iter_0005_lns_worst_removal  (rejected)
*2026-06-05 17:38*  score +0.0958  (best +0.0958)

- Chain_R10 is now confirmed to be the binding constraint on `fast_eval`
  progress: five distinct LS/LNS configurations all hit obj 199.40
  exactly.  This is almost certainly the Mode-A local optimum that any
  position-search heuristic can reach without Mode-B / Mode-C.

## iter_0006_multi_strategy_construction  (rejected)
*2026-06-05 17:43*  score +0.1031  (best +0.0958)

- Heaviest-first really is the right greedy order for these benchmarks;
  the diversification idea (more strategies → broader exploration) is
  wrong here.  The "diverse" strategies (lightest, EDD, earliest, slack,
  random) consume 5/6 of the multi-start budget on inferior basins that

## iter_0007_mode_c_scan  (rejected)
*2026-06-05 18:15*  score +0.0958  (best +0.0958)

- A standalone probe (force a Mode-C event between an arbitrary
  blocking (R,F) pair with an interruptible front job) confirms the
  wiring works: the rebuild applies the extension (movs=2) and
  produces a longer schedule.  But the resulting solution is **infeasible**

## iter_0008_balance_plus_3cycle  (rejected)
*2026-06-06 08:51*  score +0.1064  (best +0.0958)

- **Diversification via construction scoring is value-destroying when
  the harness fixes n_starts.**  Splitting 6 starts into 3 + 3 halves
  the effective coverage of each strategy.  If one strategy hits a
  rare-but-decisive basin only with certain seeds, halving its seed

## iter_0009_idle_gap_insertion  (rejected)
*2026-06-06 08:55*  score +0.0958  (best +0.0958)

- MILP's chain_R10 solution has no idle gaps: the two "slots" of
  5 aircraft each start back-to-back (slot 2 begins right after
  slot 1 finishes its longest member).  So idle-gap insertion is
  the wrong lever for this benchmark — the residual gap is **pure

## iter_0010_lns_random_repair  (rejected)
*2026-06-06 09:05*  score +0.0958  (best +0.0958)

- Random repair IS an objective improvement on R ≥ 20, especially
  triangle_R20 where it crosses below the MILP incumbent.  The
  iteration metric (`fast_eval = {triangle_R5, chain_R10, hub_R10}`)
  is structurally blind to this regime.

## iter_0011_lns_random_repair_v2  (accepted)
*2026-06-06 13:14*  score +0.0691  (best +0.0722)

- The broadened benchmark is now sensitive to LNS-side improvements
  that the 3-small-instance set was blind to.  Past iterations that
  were rejected only because of this blind spot (`iter_0002`
  intra-pos ops, `iter_0005` worst-removal) should be revisited

## iter_0012_lns_four_mode  (rejected)
*2026-06-06 13:17*  score +0.0702  (best +0.0691)

- More LNS variety is not always better.  With a fixed wall-clock
  budget, doubling the number of destroy/repair combos halves the
  iterations spent on each combo.  Two-mode (random + uniform with
  greedy repair) gave the best balance for this benchmark.

## iter_0013_ls_cap  (rejected)
*2026-06-06 13:20*  score +0.0691  (best +0.0691)

- The current LS portfolio is fast enough that LNS budget is already
  spent mostly on _construct + perturbation, not on LS depth.
  Reducing LS budget per call doesn't buy more LNS iterations.

## iter_0014_idle_gap_with_lns  (accepted)
*2026-06-06 13:23*  score +0.0630  (best +0.0691)

- The idle-gap operator NEEDS LNS-induced basin diversity to fire.
  In iter_0009 (no LNS perturbation) every Δ tested was rejected
  because the construction's initial basin had no slack for
  productive delays.  After iter_0011's random-repair LNS produces

## iter_0015_position_block_delay  (rejected)
*2026-06-06 13:27*  score +0.0630  (best +0.0630)

(no Lessons section in note.md)

## iter_0016_pair_idle_gap  (rejected)
*2026-06-06 13:30*  score +0.0630  (best +0.0630)

- Single-aircraft and pair-aircraft delay neighbourhoods are
  exhausted; the residual hub gap needs either a k-aircraft
  simultaneous delay (k=4) or a rebuild that schedules the
  whole position-block atomically.

## iter_0017_global_reorder  (rejected)
*2026-06-06 17:04*  score +0.0630  (best +0.0630)

(no Lessons section in note.md)

## iter_0018_topdest_destroy  (accepted)
*2026-06-06 17:06*  score +0.0609  (best +0.0630)

- Position-targeted destroy is more productive than random destroy on
  instances where the incumbent stacks aircraft at extreme positions.
  Forces an instant rebalance that random destroy would have to find
  by chance.

## iter_0019_hottest_destroy  (rejected)
*2026-06-06 17:08*  score +0.0609  (best +0.0609)

(no Lessons section in note.md)

## iter_0020_alns_adaptive  (rejected)
*2026-06-06 17:11*  score +0.0615  (best +0.0609)

(no Lessons section in note.md)

## iter_0021_full_restart_mode  (accepted)
*2026-06-06 17:13*  score +0.0600  (best +0.0609)

- Full restart (destroy all, random reassign) is qualitatively different
  from K-aircraft destroy: it abandons the partial-assignment carry that
  all other modes depend on.  Useful as a periodic basin-escape.
- chain_R10 floor is 198.8, not 199.4.  The 199.4 we saw across iters

## iter_0022_restart_sixth  (rejected)
*2026-06-06 17:26*  score +0.0600  (best +0.0600)

(no Lessons section in note.md)

## iter_0023_chained_multistart  (accepted)
*2026-06-06 17:30*  score +0.0580  (best +0.0600)

- Chained multi-start is the right pattern here: the LNS finds
  improvements asymptotically, so 6 × (short LNS) loses to 1 × (long
  LNS) with multi-seed diversification.  The construction step is
  cheap; running it n_starts times was wasted budget.

## iter_0024_blocker_destroy  (rejected)
*2026-06-06 17:32*  score +0.0677  (best +0.0580)

(no Lessons section in note.md)

## iter_0025_balance_biased_repair  (rejected)
*2026-06-06 17:34*  score +0.0745  (best +0.0580)

(no Lessons section in note.md)

## iter_0026_fine_grained_deltas  (accepted)
*2026-06-06 17:36*  score +0.0226  (best +0.0580)

- The Δ menu density matters more than its range.  Adding 1, 3, 7,
  15, 30, 70 between the existing values lets the idle-gap operator
  find exact alignment points the coarse grid misses.
- chain_R10 floor is NOT 198.8 — it's lower.  The previous "floor"

## iter_0027_denser_deltas  (rejected)
*2026-06-06 17:38*  score +0.0246  (best +0.0226)

(no Lessons section in note.md)

## iter_0028_pair_idle_gap_fine  (rejected)
*2026-06-06 17:56*  score +0.0468  (best +0.0226)

(no Lessons section in note.md)

## iter_0029_smaller_kicks  (accepted)
*2026-06-06 17:58*  score +0.0191  (best +0.0226)

(no Lessons section in note.md)

## iter_0030_added_K2  (rejected)
*2026-06-06 18:00*  score +0.0359  (best +0.0191)

(no Lessons section in note.md)

## iter_0031_double_K1  (rejected)
*2026-06-06 18:02*  score +0.0226  (best +0.0191)

(no Lessons section in note.md)

## iter_0032_delay_ordered_idle_gap  (rejected)
*2026-06-06 18:04*  score +0.0191  (best +0.0191)

(no Lessons section in note.md)

## iter_0033_combined_move_delay  (rejected)
*2026-06-06 18:07*  score +0.0238  (best +0.0191)

(no Lessons section in note.md)

## iter_0034_drop_intra_pos_adj  (rejected)
*2026-06-06 18:11*  score +0.0646  (best +0.0191)

(no Lessons section in note.md)

## iter_0035_intra_pos_insertion  (rejected)
*2026-06-06 18:13*  score +0.0225  (best +0.0191)

(no Lessons section in note.md)

## iter_0036_duration_scaled_deltas  (rejected)
*2026-06-06 18:16*  score +0.0435  (best +0.0191)

(no Lessons section in note.md)

## iter_0037_greedy_heavy_lns  (rejected)
*2026-06-06 18:32*  score +0.0402  (best +0.0191)

(no Lessons section in note.md)

## iter_0038_reverse_position_order  (rejected)
*2026-06-06 18:34*  score +0.0191  (best +0.0191)

(no Lessons section in note.md)

## iter_0039_conflict_targeted_idle_gap  (rejected)
*2026-06-06 18:36*  score +0.0191  (best +0.0191)

(no Lessons section in note.md)

## iter_0040_eight_mode  (rejected)
*2026-06-06 18:39*  score +0.0526  (best +0.0191)

(no Lessons section in note.md)

## iter_0041_five_mode  (rejected)
*2026-06-06 18:41*  score +0.0220  (best +0.0191)

(no Lessons section in note.md)

## iter_0042_3cycle  (rejected)
*2026-06-06 18:47*  score +0.0716  (best +0.0191)

(no Lessons section in note.md)

## iter_0043_double_internal_multistart  (rejected)
*2026-06-06 18:49*  score +0.0282  (best +0.0191)

(no Lessons section in note.md)

## iter_0044_bigger_max_kick  (rejected)
*2026-06-06 18:51*  score +0.0191  (best +0.0191)

(no Lessons section in note.md)

## iter_0045_block_swap  (rejected)
*2026-06-07 07:29*  score +0.0191  (best +0.0191)

(no Lessons section in note.md)

## iter_0046_per_access_mode_a  (rejected)
*2026-06-07 07:34*  score +0.0422  (best +0.0191)

(no Lessons section in note.md)

## iter_0047_alpha_halved  (rejected)
*2026-06-07 07:37*  score +0.0593  (best +0.0191)

(no Lessons section in note.md)

## iter_0048_max_needed_delay  (rejected)
*2026-06-07 07:39*  score +0.0191  (best +0.0191)

(no Lessons section in note.md)

## iter_0049_alpha_05  (rejected)
*2026-06-07 07:41*  score +0.0441  (best +0.0191)

(no Lessons section in note.md)

## iter_0050_shaw_relatedness  (rejected)
*2026-06-07 07:43*  score +0.0264  (best +0.0191)

(no Lessons section in note.md)

## iter_0051_persisted_overrides  (rejected)
*2026-06-07 07:47*  score +0.0191  (best +0.0191)

(no Lessons section in note.md)

## iter_0052_global_order_swap  (rejected)
*2026-06-07 07:49*  score +0.0544  (best +0.0191)

(no Lessons section in note.md)

## iter_0053_combined_random_topdest  (rejected)
*2026-06-07 07:51*  score +0.0191  (best +0.0191)

(no Lessons section in note.md)

## iter_0054_per_access_rebuild  (accepted)
*2026-06-07 08:13*  score -0.0075  (best +0.0191)

- The pre-iter_0055 rebuild was leaving substantial value on the table
  by enforcing span-disjointness rather than per-access disjointness.
  Even though both produce compliant solutions, the per-access rebuild
  reaches schedules the span-based rebuild can't represent.

## iter_0055_denser_deltas_v2  (rejected)
*2026-06-07 08:16*  score +0.0057  (best -0.0075)

(no Lessons section in note.md)

## iter_0056_no_idle_gap  (rejected)
*2026-06-07 08:18*  score +0.0256  (best -0.0075)

(no Lessons section in note.md)

## iter_0057_bigger_kicks_v2  (rejected)
*2026-06-07 08:21*  score +0.0458  (best -0.0075)

(no Lessons section in note.md)

## iter_0058_engulfing_front_resolver  (rejected)
*2026-06-07 08:24*  score +0.0079  (best -0.0075)

(no Lessons section in note.md)

## iter_0059_no_topdest  (rejected)
*2026-06-07 08:26*  score +0.0332  (best -0.0075)

(no Lessons section in note.md)

## iter_0060_sparser_deltas  (rejected)
*2026-06-07 08:30*  score +0.0057  (best -0.0075)

(no Lessons section in note.md)

## iter_0061_enumerate_single_move  (rejected)
*2026-06-07 08:34*  score +0.0256  (best -0.0075)

(no Lessons section in note.md)

## iter_0062_alpha_cycling  (rejected)
*2026-06-07 22:27*  score -0.0048  (best -0.0075)

(no Lessons section in note.md)

## iter_0063_enriched_kicks  (rejected)
*2026-06-07 22:29*  score -0.0066  (best -0.0075)

(no Lessons section in note.md)

## iter_0064_pair_idle_gap_v2  (rejected)
*2026-06-07 22:31*  score +0.0256  (best -0.0075)

(no Lessons section in note.md)

## iter_0065_exhaust_k2_repair  (rejected)
*2026-06-07 22:33*  score +0.0265  (best -0.0075)

(no Lessons section in note.md)

## iter_0066_exhaust_replaces_restart  (rejected)
*2026-06-07 22:36*  score -0.0075  (best -0.0075)

(no Lessons section in note.md)

## iter_0067_no_restart_on_improvement  (accepted)
*2026-06-07 22:39*  score -0.0419  (best -0.0075)

- Restart-on-improvement was actively harmful: each pass through ops
  1→2→3→4 lets EACH op act on the FRESH state from the previous op'"'"'s
  improvement.  Without restart, the LS converges faster on a richer
  trajectory.

## iter_0068_3cycle_v3  (rejected)
*2026-06-07 22:41*  score -0.0299  (best -0.0419)

(no Lessons section in note.md)

## iter_0069_intra_pos_insertion_v3  (accepted)
*2026-06-07 22:43*  score -0.0420  (best -0.0419)

(no Lessons section in note.md)

## iter_0070_edd_repair_v3  (accepted)
*2026-06-07 22:45*  score -0.0425  (best -0.0420)

(no Lessons section in note.md)

## iter_0071_nonadj_intra_pos_swap  (rejected)
*2026-06-07 22:47*  score -0.0425  (best -0.0425)

(no Lessons section in note.md)

## iter_0072_denser_deltas_v3  (rejected)
*2026-06-07 22:49*  score -0.0425  (best -0.0425)

(no Lessons section in note.md)

## iter_0073_kick_K12  (accepted)
*2026-06-07 22:50*  score -0.0481  (best -0.0425)

(no Lessons section in note.md)

## iter_0074_no_topdest_v2  (accepted)
*2026-06-07 22:52*  score -0.0530  (best -0.0481)

(no Lessons section in note.md)

## iter_0075_add_K3  (rejected)
*2026-06-07 22:54*  score -0.0489  (best -0.0530)

(no Lessons section in note.md)

## iter_0076_no_full_restart  (rejected)
*2026-06-07 22:56*  score -0.0473  (best -0.0530)

(no Lessons section in note.md)

## iter_0077_drop_adj_swap_v2  (rejected)
*2026-06-07 22:58*  score -0.0417  (best -0.0530)

(no Lessons section in note.md)

## iter_0078_restart_op1_only  (rejected)
*2026-06-07 23:01*  score +0.0163  (best -0.0530)

(no Lessons section in note.md)

## iter_0079_more_K1  (rejected)
*2026-06-07 23:02*  score -0.0318  (best -0.0530)

(no Lessons section in note.md)

## iter_0080_coarser_deltas  (rejected)
*2026-06-07 23:06*  score -0.0481  (best -0.0530)

(no Lessons section in note.md)

## iter_0081_op1_with_delay  (rejected)
*2026-06-07 23:23*  score -0.0400  (best -0.0530)

(no Lessons section in note.md)

## iter_0082_restart_after_op4  (rejected)
*2026-06-07 23:25*  score -0.0356  (best -0.0530)

(no Lessons section in note.md)

## iter_0083_best_improvement_op1  (rejected)
*2026-06-07 23:28*  score -0.0385  (best -0.0530)

(no Lessons section in note.md)

## iter_0084_adaptive_kick  (rejected)
*2026-06-08 07:39*  score -0.0473  (best -0.0530)

(no Lessons section in note.md)

## iter_0085_cyclic_shift_order  (rejected)
*2026-06-08 07:41*  score -0.0500  (best -0.0530)

(no Lessons section in note.md)

## iter_0086_edd_construction  (rejected)
*2026-06-08 07:43*  score -0.0469  (best -0.0530)

(no Lessons section in note.md)

## iter_0087_op4_multi_improvement  (rejected)
*2026-06-08 07:46*  score -0.0133  (best -0.0530)

(no Lessons section in note.md)

## iter_0088_balance_biased_repair_v2  (rejected)
*2026-06-08 07:48*  score -0.0459  (best -0.0530)

(no Lessons section in note.md)

## iter_0089_k1_enumerate_mode  (rejected)
*2026-06-08 07:50*  score -0.0481  (best -0.0530)

(no Lessons section in note.md)

## iter_0090_focused_worst_op  (rejected)
*2026-06-08 07:53*  score -0.0452  (best -0.0530)

(no Lessons section in note.md)

## iter_0091_stack_penalty  (rejected)
*2026-06-09 07:14*  score -0.0477  (best -0.0530)

(no Lessons section in note.md)
