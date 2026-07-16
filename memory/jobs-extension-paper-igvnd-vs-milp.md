---
name: jobs-extension-paper-igvnd-vs-milp
description: papers/jobs_extension features IGVND v01 vs the MILP; solving_approaches.tex (GRASP/FAS) is intentionally orphaned
metadata:
  type: project
---

`papers/jobs_extension/paper.tex` is the job-level extension manuscript. As of
2026-06-15 it is built around **two methods only**: the exact MILP (`milp.tex`)
and the **IGVND v01 heuristic** (`heuristic.tex`), compared in
`computational_results.tex`.

**Why:** the user asked to elaborate the paper with what was developed in
[[keep-igvnd-md-in-sync]] (`methods/iterated_greedy_vnd_v01`) and to use the
MILP as the comparison baseline. So "the two methods" = {MILP, IGVND}.

**How to apply:**
- `solving_approaches.tex` (Topology-aware GRASP / FAS / Safe Pipeline — the
  *manual* method, not IGVND) is **intentionally NOT `\input`** by paper.tex.
  It is left on disk, orphaned. Don't treat its absence from the build as a bug.
- Result tables are generated, not hand-written: `make_tables.py` reads
  `outputs/solutions/results.csv` (labels `igvnd_{wMK,wDLY,wMOV}` vs
  `milp_job_{wMK,wDLY,wMOV}`) and emits `tables/res_{gap_profile,components,milp_conv}.tex`.
  Re-run it after any battery refresh, then `build_paper.py`.
- Gap convention: `g = (MILP - IGVND)/MILP`, so `g>0` ⇒ IGVND better. Numbers
  match the method's Part II battery (commit `4a80e79`).
