# iter_0013_ls_cap — cap each LNS-internal LS at 2s

## Hypothesis

More LNS iters per 20 s budget by limiting each post-perturbation LS
to 2 s.  Initial LS still uses full remaining time.

## Eval result

Score +0.0691 (identical to iter_0011).  No instance moved.

## Outcome

**rejected** — LS was already converging well within 2 s on these
instances; capping had no effect.

## Lessons

- The current LS portfolio is fast enough that LNS budget is already
  spent mostly on _construct + perturbation, not on LS depth.
  Reducing LS budget per call doesn't buy more LNS iterations.
