# iter_0021_full_restart_mode — add full restart as a 4th LNS mode

## Hypothesis

LNS modes 0-2 all keep a partial assignment from the incumbent.  Adding
a 4th mode that destroys EVERY aircraft and reassigns uniform-random is
essentially a multi-start restart from scratch — useful to escape the
basin lock-in that smaller perturbations cannot break.

## What changed

LNS mode 3: destroy all aircraft, uniform-random repair.

## Eval result

| instance       | obj_var | obj_milp |    gap |
| -------------- | ------: | -------: | -----: |
| triangle_R5    |    3.00 |     3.00 | +0.000 |
| chain_R10      |  **198.80** |   163.35 | **+0.217** |
| hub_R10        |  145.50 |   136.40 | +0.067 |
| triangle_R20   |  786.85 |   823.00 | -0.044 |

Score +0.0600 (iter_0018 had +0.0609 — 1.5% better).

## Outcome

**accepted** — first sub-199.4 result on chain_R10 across 21 iterations.
The full-restart kicks land on a basin where some chain ordering shaves
the last 0.6 obj units.  Improvement is small but it cracks the
basin-lock pattern.

## Lessons

- Full restart (destroy all, random reassign) is qualitatively different
  from K-aircraft destroy: it abandons the partial-assignment carry that
  all other modes depend on.  Useful as a periodic basin-escape.
- chain_R10 floor is 198.8, not 199.4.  The 199.4 we saw across iters
  0001-0020 was the basin reached by all incremental-perturbation
  modes; full restart accesses a slightly lower one.
