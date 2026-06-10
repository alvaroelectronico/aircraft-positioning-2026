# iter_0020_alns_adaptive — adaptive mode selection by past success

## Hypothesis

Round-robin mode selection wastes budget on modes that don't work for
this instance.  ALNS-style adaptive weights (w**2 roulette, w bumped on
success) should focus effort on productive modes.

## Eval result

Score +0.0615 (slightly worse than iter_0018's +0.0609).  triangle_R20
regressed 786.85 → 788.85.

## Outcome

**rejected** — with only 3 modes and few improvements per instance,
the adaptive weights overfit on early success and stop exploring.
The round-robin schedule is more robust at this scale.
