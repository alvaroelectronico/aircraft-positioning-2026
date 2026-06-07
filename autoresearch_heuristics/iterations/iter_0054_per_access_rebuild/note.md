# iter_0055_per_access_rebuild — rebuild resolvers honor checker's per-access Mode-A

## Hypothesis

The previous rebuild rejected any configuration where the rear's SPAN
overlaps the front's SPAN, but the checker's RQ07_v2 is **per-access**:
each rear access instant τ ∈ {tau_in, tau_out} only needs to satisfy
`τ ≤ f_start - eta OR τ ≥ f_finish + eta` individually.  This allows
the **engulfing rear** pattern — rear's stay overlaps front's, with
entry Mode A z- (before front) and exit Mode A z+ (after front) — which
the MILP exploits heavily on chain (R5/P5 [2, 36] engulfs R6/P1 [10, 27]).

iter_0047 tried this with a quick patch and regressed (LS converged
differently).  This time: full rewrite of BOTH resolvers with
**minimum-feasible-tau_in** computation that considers both options.

## What changed

`_resolve_rear_interactions`:
- Collect all overlapping fronts.
- Build candidate `tau_in` set: `{s_r_first} ∪ {f_finish + eta} ∪
  {f_finish + eta - total_duration : feasible z-}` per front.
- For each candidate ≥ `s_r_first`, check per-access feasibility against
  ALL fronts (both `tau_in` and `tau_out`).
- Pick the smallest feasible candidate.  Delay = that − s_r_first.
- Defensive fallback: iterative push-past-front if no candidate works.

`_resolve_front_interactions`:
- Per-access check against front's stay `[F_s, F_f]` with eta margin:
  rear access τ must satisfy `τ ≤ F_s - eta OR τ ≥ F_f + eta`.
- If neither, push front so `F_s = τ + eta` (the maximum τ over all
  problematic rear accesses determines the shift).

LOC delta: ~+70 lines.

## Eval result

| instance                          | obj_var | obj_milp |    gap    | compliant |
| --------------------------------- | ------: | -------: | --------: | :-------: |
| triangle_tight_P5_R5_seed1        |    3.00 |     3.00 |   +0.000  |     Y     |
| chain_tight_P5_R10_seed1          |  184.45 |   163.35 |   +0.129  |     Y     |
| hub_tight_P5_R10_seed1            | **136.75** |   136.40 |  **+0.003** |  Y  |
| triangle_tight_P5_R20_seed1       | **690.05** |   823.00 | **−0.162** |  Y  |

- **score (mean gap)**: **−0.0075**  (iter_0029 had +0.0191 — sign change!)
- All 4 compliant.

## Outcome

**accepted** — first NEGATIVE fast_eval score in the loop.  The heuristic
on average beats MILP across fast_eval.

## Lessons

- The pre-iter_0055 rebuild was leaving substantial value on the table
  by enforcing span-disjointness rather than per-access disjointness.
  Even though both produce compliant solutions, the per-access rebuild
  reaches schedules the span-based rebuild can't represent.
- The "engulfing rear" pattern (rear engulfs front, accesses on
  opposite sides) is exactly the MILP staggering on chain.  Previous
  iter_0047 quick-patch failed because it kept the SEQUENTIAL "push
  past" delay logic but only changed the conflict-test; the minimum-
  tau_in candidate scan is the right structural change.
- hub_R10 from 145.5 → 136.75 means we essentially match MILP on hub
  too — that was the dimension fast_eval needed most.  Net gain
  across fast_eval ≈ 0.025 (huge for a single change).
- chain_R10 picked up a small regression (181.1 → 184.45) because the
  LS converges to a different basin under the new semantics.  Likely
  recoverable with further LNS tuning, but the +51 unit win on
  triangle_R20 and +8.75 on hub_R10 dominate.
