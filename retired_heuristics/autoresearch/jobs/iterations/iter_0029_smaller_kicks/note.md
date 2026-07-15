# iter_0029_smaller_kicks — add K=1 single-aircraft kick to LNS

## Hypothesis

Kick sizes were {R//4, R//3, R//2}.  Adding K=1 lets the LNS perturb
the incumbent one aircraft at a time — much cheaper per iteration so
more iters fit per budget, and many improvements only require
relocating a single aircraft (which LS already does, but in a
fresh-RNG context from LNS the rebuild can find different timing).

## What changed

`kick_sizes = [1, R//4, R//3, R//2]`.

## Eval result

| instance       | obj_var | obj_milp |    gap |
| -------------- | ------: | -------: | -----: |
| triangle_R5    |    3.00 |     3.00 | +0.000 |
| chain_R10      |  **181.10** |   163.35 | **+0.109** |
| hub_R10        |  145.50 |   136.40 | +0.067 |
| triangle_R20   |  **741.50** |   823.00 | **-0.099** |

Score +0.0191 (iter_0026 had +0.0226).

## Outcome

**accepted** — chain_R10 drops to 181.1, triangle_R20 to 741.5.  K=1 kicks
fit ~4× more iterations per budget than K=R//4 and clearly find finer
improvements.
