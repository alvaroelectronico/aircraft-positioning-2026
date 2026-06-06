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
