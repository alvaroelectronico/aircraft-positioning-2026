---
description: Sincroniza el `.md` de especificación viva de un método con su código actual, manteniendo la estructura Part I/II/III/IV + Change log. Uso `/sync-method-doc <ruta-método-o-solver> [hint]`. Despacha al subagente `method-doc`. Invocar en hitos (commit que cambia comportamiento, batería nueva, refactor), no automáticamente.
arguments: target hint
context: fork
agent: method-doc
---

Sync the living `.md` spec of the target method with its current code.

Target: **$target**
Hint:   **$hint**

Follow the workflow in your agent system prompt:

1. Resolve the target — accept either a method directory
   (e.g. `methods/theory_assisted`) or a specific solver `.py`
   (e.g. `methods/manual/jobs/milp_jobs_v2_solver.py`).
2. Read the current `.md` if it exists, or scaffold from the embedded
   template if not.
3. Update Part IV from the code (always), Part II from a battery log
   if `log: <path>` (or a `.log` path) is present in the hint, and
   append a Change log row if the hint contains a free-form
   description of what changed.
4. Leave Parts I and III alone unless the user explicitly asks to
   edit them; flag any drift you notice in your return summary.
5. Return a short summary: doc path, sections touched, drift
   warnings, approximate line delta.

Honour the per-method isolation contract: read only the target
method's tree, plus `problems/<paper>/`, `shared/`,
`experiments/run_experiments.py`, and any log file referenced in the
hint.  Do not read other methods, `literature_review/`, or `papers/`.

Refuse to write to frozen directories (`methods/iterated_greedy_vnd_v01/`).

Hint examples:

```
/sync-method-doc methods/theory_assisted
/sync-method-doc methods/theory_assisted  Commit 1: variance reduction (adaptive starts)
/sync-method-doc methods/theory_assisted  Refresh battery log: outputs/logs/battery_v02_001.log
/sync-method-doc methods/manual/jobs/milp_jobs_v2_solver.py  Added tight per-pair big-M cuts
```
