---
name: theory-assisted-v06-candidate-c-brkga
description: theory_assisted attempt v06 implements Candidate C (BRKGA) — chosen over B/D
metadata:
  type: project
---

The current `methods/theory_assisted/` attempt (v06, started 2026-06-17) implements **Candidate C — BRKGA with a mixed-chromosome decoder + warm-start**, chosen over B and D.

**Why C:** Candidate A (IG+VND) is exhausted (v01 ChatGPT + v02 Claude graduated to their own method dirs). B reuses A's exact SeqVND core (least differentiated). D (GRASP+Local Branching) needs the manual MILP's binary `x_{r,p}` variables → would require reading `methods/manual/` (isolation-contract conflict). C is the only distinct algorithmic family and needs only the problem statement + checker.

**Key design choices** (see `methods/theory_assisted/jobs/notes/design.md`):
- Decoder places positions in topological order of the blocking DAG (fronts first) so rear aircraft classify against already-fixed fronts.
- Per-aircraft start chosen by local-cost scan over candidate A/B windows; construction is **Mode A/B only** (Mode C dominated by B and would retroactively extend a frozen front job). Guaranteed Mode-A safe-late candidate ⇒ always feasible.
- Decoder reuses the checker's `_classify_access` so it agrees with the checker by construction.
- Self-implemented lean BRKGA (no external lib), seeded for determinism.

**v1 (commit 29bd5eb, Mode-A/B-only decoder):** battery log `202605_02_main_methods_20260618_064914.log`, 360/360 feasible. Lost to cached MILP on R5–R10 (drove movements to 0 via safe-late but inflated makespan/delay — fatal under wMK/wDLY where movements are cheap); won only on R30 (unconverged MILP).

**v2 (commit 22c65fb, Mode-C via κ fixpoint):** battery log `202605_02_main_methods_20260619_070616.log`, 360/360 feasible. Big win on wMK/wDLY (chain_R10 wMK −45.8%→−18.5%; triangle_tight_R5 wDLY −1322%→−3.2%); **regressed wMOV** (full_R20 −42%→−120%) — NOT from added movements (Δmov≈0) but because the fixpoint decode is ~8× slower and starves the GA on large R (R20 runs overran the 60 s budget).

**v3 / P1 (commit f7fc536, code bab9773): profile-gated Mode-C — DONE.** `solve()` sets `allow_mode_c = weight_movements <= max(weight_makespan, weight_delay)` (explicit config overrides). Enables Mode C for wMK/wDLY, disables it for wMOV and the default profile. wMOV re-battery (log `…_20260620_074942.log`, 120/120 feasible) confirms the regression is gone: full_R20 −120.3%→−39.5%, triangle_R30 +1.6%→+22.9%, back to ≈ v1; wMK/wDLY unchanged (deterministic same path as v2).

**P2 (commit 748c0a8, code 748c0a8): decode-cost on large R — INVESTIGATED, premise was wrong.** Lowering the κ-fixpoint cap 8→3 doubles GA generations but REGRESSES wMK/wDLY on large R (full_R20 wMK 26323→34419): the fixpoint passes are *productive* — the good Mode-C schedules need >3 passes to converge on large dense instances, so a low cap forces premature Mode-A/B fallback. Cap kept at 8. The only kept change: `run_brkga` now enforces the 60 s budget *inside* the decode loop (`score_pop`), fixing the prior 72–81 s overrun (a BATTERY.md violation) at ~zero quality cost (GA finds its best early; 3/4 large-R head-to-head identical). **Lesson: the fixpoint cost is intrinsic, not waste — large-R quality is not improvable by cost-capping.** Part II wMK/wDLY large-R numbers predate the guard (mildly optimistic until re-batteried).

**Top remaining lever: P3 — warm-start** (`warmstart.py` still unimplemented; `run_brkga` already takes a `warmstarts` arg; reverse-encode cached MILP/topology JSONs per design.md §6). A faster *incremental* fixpoint (re-place only aircraft downstream of a changed κ) is the other large-R idea. Cached MILP for paper #2 lives under labels `milp_job_wMK/wDLY/wMOV` (120 instances each). Related: [[theory-assisted-v02-manoeuvre-decoder]].
