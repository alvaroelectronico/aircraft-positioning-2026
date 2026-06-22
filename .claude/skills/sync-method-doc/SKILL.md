---
description: Sincroniza el `.md` de especificación viva de un método con su código actual, manteniendo la estructura Part I/II/III/IV + Change log. **El `.md` se llama exactamente igual que el `.py` del solver y vive en su misma carpeta**, y siempre refleja el log de batería más reciente. Uso `/sync-method-doc <ruta-método-o-solver> [hint]`. Despacha al subagente `method-doc`. **Invocar siempre tras cada commit con cambio de comportamiento y tras cada batería**, no es opcional.
arguments: target hint
context: fork
agent: method-doc
---

Sync the living `.md` spec of the target method with its current code.

Target: **$target**
Hint:   **$hint**

Follow the workflow in your agent system prompt, respecting the two
hard rules:

1. **Doc filename equals solver `.py` filename.**  Same basename, same
   directory, `.md` extension.  E.g. `methods/brkga_v02/jobs/brkga.py`
   ↔ `methods/brkga_v02/jobs/brkga.md`.  Never elsewhere, never
   renamed independently of the `.py`.
2. **Latest log filename appears in both the Status callout and the
   Part II Experimental setup table** whenever Part II is refreshed,
   so the reader always sees which battery the current numbers come
   from.  Both references cite the same log basename.

Steps:

1. Resolve the target — accept either a method directory
   (e.g. `methods/theory_assisted`) or a specific solver `.py`
   (e.g. `methods/manual/jobs/milp_jobs_v2_solver.py`).
2. Read the current `.md` (at the fixed `<solver_basename>.md`
   location) if it exists, or scaffold from the embedded template
   if not.
3. Update Part IV from the code (always), Part II from a battery log
   if `log: <path>` (or a `.log` path) is present in the hint, and
   append a Change log row if the hint contains a free-form
   description of what changed.  When Part II is refreshed, update
   BOTH the Status callout and the Experimental setup `Log` row.
4. Leave Parts I and III alone unless the user explicitly asks to
   edit them; flag any drift you notice in your return summary.
5. Return a short summary: doc path, sections touched, log
   referenced (if any), drift warnings, approximate line delta.

Honour the per-method isolation contract: read only the target
method's tree, plus `problems/<paper>/`, `shared/`,
`experiments/run_experiments.py`, `experiments/BATTERY.md`, and any
log file referenced in the hint.  Do not read other methods,
`literature_review/`, or `papers/`.

Refuse to write to frozen directories
(`methods/iterated_greedy_vnd_v01/`, `methods/iterated_greedy_vnd_v02/`,
`methods/brkga_v02/`).

Hint examples:

```
/sync-method-doc methods/theory_assisted                  # passive sync (Part IV only)
/sync-method-doc methods/theory_assisted  Commit 1: <what changed>
/sync-method-doc methods/theory_assisted  Commit 1: <what changed>  log: outputs/logs/<battery>.log
/sync-method-doc methods/theory_assisted  log: outputs/logs/<battery>.log   # refresh Part II only
/sync-method-doc methods/manual/jobs/milp_jobs_v2_solver.py  Added tight per-pair big-M cuts
```
