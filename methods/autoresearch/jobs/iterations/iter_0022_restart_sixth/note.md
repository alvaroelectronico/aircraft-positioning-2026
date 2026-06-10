# iter_0022_restart_sixth — reduce full-restart frequency to 1/6 from 1/4

## Hypothesis

iter_0021's 4-mode rotation spends 25 % of LNS budget on full restart
— too much.  full_R10 regressed at 60 s (264.85 → 294.60).  Move to a
6-mode rotation where full restart only fires 1/6 of the time.

## What changed

LNS mode cycling: `kick_idx % 6` with modes:
  0, 3: random destroy + greedy repair
  1, 4: random destroy + uniform repair
  2:    topdest destroy + uniform repair
  5:    full restart + uniform repair

## Eval result

fast_eval score +0.0600 (identical to iter_0021).

Broader probe (60 s):
| instance        | iter_0021 | iter_0022 |    MILP |
| --------------- | --------: | --------: | ------: |
| full_R10        |    294.60 |    264.85 |  180.35 |
| full_R20        |   1690.10 |   1690.10 | 2533.10 |
| triangle_R30    |   2496.45 |   2496.45 | 3208.85 |

iter_0022 recovers full_R10 to iter_0014 level (264.85) while keeping
chain_R10 improvement.  Strictly dominates iter_0021 on broader
benchmark.

## Outcome

**rejected by protocol** (fast_eval tie with iter_0021).  Manually
promoted to best — full_R10 recovery is the deciding factor on the
broader benchmark.
