# iter_0067_no_restart_on_improvement — let LS fall through after improvements

## Hypothesis

LS currently restarts from op 1 on every improvement (`if improved:
continue`).  This burns time re-checking already-explored moves under
the new state.  Hypothesis: let the LS fall through to the next op
after an improvement (do a single full pass).  Idle-gap and intra-pos
ops get fresh state to work with each pass.

## What changed

`_local_search`: removed the `if improved: continue` after ops 1, 2, 3.
LS now does a full pass through all 4 ops per iteration, restarting
the outer loop only after each FULL pass.

## Eval result

| instance                          | obj_var | obj_milp |      gap | compliant |
| --------------------------------- | ------: | -------: | -------: | :-------: |
| triangle_tight_P5_R5_seed1        |    3.00 |     3.00 |   +0.000 |     Y     |
| chain_tight_P5_R10_seed1          |  184.45 |   163.35 |   +0.129 |     Y     |
| hub_tight_P5_R10_seed1            | **119.55** |   136.40 |  **−0.124** |  Y  |
| triangle_tight_P5_R20_seed1       | **680.55** |   823.00 | **−0.173** |  Y  |

- **score (mean gap)**: **−0.0419**  (iter_0054 had −0.0075)
- All 4 compliant.

## Outcome

**accepted** — `best.txt → iter_0067_no_restart_on_improvement`.

## Lessons

- Restart-on-improvement was actively harmful: each pass through ops
  1→2→3→4 lets EACH op act on the FRESH state from the previous op'"'"'s
  improvement.  Without restart, the LS converges faster on a richer
  trajectory.
- hub_R10 dropped from 136.75 to **119.55** — now 12.4 %% BELOW the
  MILP'"'"'s 60 s incumbent (MILP gap was 83 %%, so MILP itself hadn'"'"'t
  proven 136.40 optimal — our heuristic just found a better feasible
  solution).
- triangle_R20 deepens to −17 %% vs MILP.
- chain_R10 unchanged (basin floor on chain seems robust to this
  change).
