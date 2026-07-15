# iter_0012_lns_four_mode — add worst-removal destroy to iter_0011

## Hypothesis

iter_0011 alternates random-destroy + greedy-repair with random-destroy +
uniform-repair.  Adding worst-removal destroy as a third axis (× greedy
or uniform repair) gives four LNS modes that should each focus on a
different basin shape: random-greedy (exploration), random-uniform
(balance discovery), worst-greedy (Shaw intensification), worst-uniform
(targeted basin escape).  More diversity = more chance of cracking
triangle_R20 further below 814.

## What changed

LNS loop: `mode = kick_idx % 4` selects (destroy_kind, repair_kind).
Re-added the `_destroy_worst` helper from the (rejected) iter_0005.

## Eval result

| instance                          | obj_var | obj_milp |    gap |
| --------------------------------- | ------: | -------: | -----: |
| triangle_R5                       |    3.00 |     3.00 | +0.000 |
| chain_R10                         |  199.40 |   163.35 | +0.221 |
| hub_R10                           |  145.50 |   136.40 | +0.067 |
| triangle_R20                      |  817.70 |   823.00 | −0.006 |

- **score**: **+0.0702** (iter_0011 had +0.0691 — worse).

## Outcome

**rejected** — triangle_R20 regressed from 814.0 (iter_0011) to 817.7
(iter_0012).  Four-mode LNS spreads the 20 s budget too thin per mode;
each mode gets only ~5 s of effective basin exploration, vs 10 s in
iter_0011's two-mode rotation.

## Lessons

- More LNS variety is not always better.  With a fixed wall-clock
  budget, doubling the number of destroy/repair combos halves the
  iterations spent on each combo.  Two-mode (random + uniform with
  greedy repair) gave the best balance for this benchmark.
- Worst-removal destroy doesn't pay off when the random-destroy
  already finds the relevant basins inside 20 s — re-confirms the
  iter_0005 finding under the broadened metric.
- Next direction: instead of multiplying destroy strategies, try
  to make each LNS iteration cheaper (smaller default kick sizes)
  so more iterations fit in the same budget.  Or: tighten the LS
  inner loop to terminate sooner once no improvement is found.
