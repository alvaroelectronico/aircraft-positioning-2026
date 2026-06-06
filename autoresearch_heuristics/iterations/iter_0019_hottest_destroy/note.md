# iter_0019_hottest_destroy — LNS mode: destroy two highest-delay positions

## Hypothesis

The hottest-delay positions are where the obj cost concentrates;
destroying them in one shot lets the rebuild rethink that exact spot.

## Eval result

Score +0.0609 (identical to iter_0018).  No instance moved.

## Outcome

**rejected** — topdest mode (iter_0018) already finds the productive
basin escapes that the hottest-delay variant would find.  The two
strategies overlap heavily because high-population positions are
often the high-delay positions on these instances.
