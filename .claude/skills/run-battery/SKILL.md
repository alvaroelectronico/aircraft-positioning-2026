---
description: Corre la batería estándar de paper #2 para un método tal como se articuló la experimentación — heurístico-solo, 60 s, 3 perfiles de peso (wMK/wDLY/wMOV), orden seed-first, emparejado contra el MILP cacheado SIN re-ejecutarlo — y devuelve el reporte pareado + un juicio de calidad (gap medio → Δ por componente → cumplimiento → suelo de ruido). Uso `/run-battery <método-o-labels> [scope] [mode]`. Despacha al subagente `battery-runner`. La metodología vive en `experiments/BATTERY.md`.
arguments: target scope_and_mode
context: fork
agent: battery-runner
---

Run the standard paper-#2 battery for the target method and report it, the way
the experimentation is articulated in [`experiments/BATTERY.md`](../../experiments/BATTERY.md).

Target: **$target**
Scope / mode: **$scope_and_mode**

Follow the protocol in your agent system prompt. In short:

1. **Read `experiments/BATTERY.md` first** — it is the single source of truth
   for the benchmark, weight profiles, cached-MILP rule, subset shortcuts and
   judging procedure. Operate it; do not duplicate or contradict it.
2. Resolve the target into its three heuristic labels (`*_wMK / _wDLY / _wMOV`)
   from `experiments/run_experiments.py`. Default scope is the `_seed1$` subset
   (~35 min); `full` is 360 runs (~6 h) — for `full`, emit the command and have
   the caller run it backgrounded rather than blocking.
3. **Run the heuristic only**, 60 s per run, seed-first; **never re-run the
   MILP** — pair against the cached rows in `outputs/solutions/results.csv` via
   `paired_report.py` (or the method's `ta_` wrapper for `ta_igvnd_*` labels).
4. **Judge** in order: mean relative gap `(MILP−heur)/MILP` → per-component Δ
   (cross-read because the relative gap inflates when the MILP value ≈ 0) →
   compliance (0 checker violations). In `ablation` mode, apply the **noise
   floor** test (≈19 delay units on this battery): a delta inside the
   run-to-run spread is *not* an improvement.
5. Return a short summary: commands + scope, git-stamped log path, report path,
   per-profile headline (gap + decisive Δ), compliance count, and — in ablation
   mode — effect-vs-noise and a keep/drop recommendation. Flag any caveat
   (unconverged MILP at scale, small-denominator inflation, stale MILP cache).

Honour the method's isolation contract: read only the target method's tree,
`problems/jobs/**`, `shared/**`, and the `experiments/` battery tooling. Do not
read other methods' source, `literature_review/`, or `papers/`.

Usage examples:

```
/run-battery methods/theory_assisted                       # _seed1$ subset, snapshot
/run-battery methods/theory_assisted  full                 # full 360-run battery (background it)
/run-battery ta_igvnd_wMK,ta_igvnd_wDLY,ta_igvnd_wMOV  seed1
/run-battery methods/theory_assisted  scope: scn_chain_*  mode: ablation
```
