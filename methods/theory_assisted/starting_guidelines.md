# Starting guidelines — current attempt under `theory_assisted/`

Read this file **right after [`CLAUDE.md`](CLAUDE.md)** at the start
of a new session.  It is the user's specific instructions for the
attempt currently in progress under this scaffold — the schema /
skeleton you must follow, the workflow expected, and the
non-negotiable rules that come from `CLAUDE.md`.

This file is **per-attempt**: when the current method graduates out
of `theory_assisted/`, this file travels with it (as design
provenance), and the scaffold gets a fresh `starting_guidelines.md`
for the next attempt.

---

## What this attempt is

- **Candidate:** C — BRKGA with mixed-chromosome decoder + warm-start
  (see `jobs/notes/synthesis.md` lines 158–214, the "Candidate C"
  section, for the original synthesis).
- **Purpose:** *replication* of `methods/brkga_v02/` (Claude-assisted
  Candidate C, first attempt).  Same scaffold, same digests, same
  LLM (Claude), strict isolation from the first attempt.  The
  experimental question is: **how much do two attempts at the same
  algorithm, by the same LLM, on the same theory base, diverge in
  implementation choices and final quality?**
- **You are NOT building Candidate A, B, or D.**  If the BRKGA shape
  feels wrong after reading the synthesis section, *tell the user*
  before pivoting.  Silent switches void the replication experiment.

---

## Esquema general

Use exactly this structure for the first working version.  Do not
deviate without asking the user first.

### Layout de archivos en `methods/theory_assisted/jobs/`

<TODO: indica los archivos que quieres y qué hace cada uno.
Ejemplo:
- `brkga_solver.py`  ← entry point, clase `BRKGAJobSolver`, `name="brkga2_job"`
- `decoder.py`       ← chromosome → solution dict (decoder + Mode-A/B/C classification)
- `ga.py`            ← BRKGA loop (population, crossover, mutants, shake)
- (cualquier otro auxiliar)
>

### Cromosoma

<TODO: forma del cromosoma.
Ejemplo:
- Longitud n = 2|R|
- Genes 1..|R|: position-assignment keys (k_r → floor(k_r·|P|))
- Genes |R|+1..2|R|: priority keys (aircraft sharing a position se ordenan ascending)
- (o lo que quieras: hot-one indicator, separate aircraft-priority, etc.)
>

### Decoder

<TODO: pasos exactos del decoder, en orden.
Ejemplo:
1. Assign each aircraft to its position from the indicator keys.
2. For each position, sort by priority key.
3. Schedule via earliest-feasible-start sweep:
   - respect E_r, ε intra-position gaps
   - classify each access as Mode-A/B/C
   - <qué hace ante Mode-C con job no interrumpible>
   - <qué hace ante Mode-B (gap insertion)>
4. Compute objective W^M·m + W^D·Σdelay + W^S·movements.
5. Return solution dict matching problems/jobs/checker.py.
>

### Bucle BRKGA

<TODO: parámetros del GA.
Ejemplo:
- Population size: <…>
- Elite fraction: <…>
- Mutant fraction: <…>
- Bias ρ: <…>
- Shake / IPR: <activado o no, cada cuántas gens>
- Honra `time_limit_s` del config — el bucle debe terminar dentro del budget.
>

### Profile-gating

<TODO: cuándo Mode-C está activo y cuándo no.
Ejemplo:
- Mode-C ENABLED si w_movements <= max(w_makespan, w_delay); else DISABLED.
- Razón: bajo wMOV el coste de movimiento domina y Mode-C nunca paga.
- Override explícito via config[`allow_mode_c`].
>

### Warm-start

<TODO: de dónde sacas el warm-start, o "ninguno por ahora".
Nota: si quieres warm-start de la MILP del método manual, eso requiere
una entrada en _ALLOWLIST de experiments/tests/test_method_isolation.py
con justificación escrita (no es cross-method import silencioso).
>

### Lo que NO quiero en la primera versión

<TODO: restricciones explícitas.
Ejemplos típicos:
- Sin numpy / sin scipy — solo stdlib.
- Sin path relinking todavía.
- Sin warm-start.
- Sin tests aparte del __main__ smoke test del solver.
- Tamaño máximo de población = X (evita arrancar con 400).
>

---

## Flujo de trabajo (fijo)

1. **Lee primero** `CLAUDE.md` (contrato de aislamiento + propósito
   experimental) y luego este archivo.
2. **Lee SÓLO la sección Candidate C** de `jobs/notes/synthesis.md`
   (líneas 158–214).  No leas otras secciones — evita prejuicios sobre
   A/B/D que no estás construyendo.
3. **Antes de escribir código**, devuelve en una respuesta corta
   (3–5 bullets) tu interpretación del esquema:
   - qué módulos vas a crear
   - qué entradas/salidas tiene el decoder
   - qué hiperparámetros vas a usar
   - qué dejas fuera del MVP
   Espera mi visto bueno antes de tirar línea de código.
4. **Implementa en commits granulares**.  Patrón sugerido:
   - Commit 0: decoder skeleton — pasa `check_solution` en 10 cromosomas aleatorios.
   - Commit 1: bucle BRKGA + primer end-to-end con time budget.
   - Commit 2: profile-gating de Mode-C.
   - Commit 3: registro en `experiments/run_experiments.py` con labels nuevas
     (ej. `brkga2_wMK / wDLY / wMOV` o `ta2_brkga_*`).
5. **Tras el primer commit con `solve()` end-to-end funcionando**,
   invoca:
   ```
   /sync-method-doc methods/theory_assisted  v03 inicial Candidate C (replicación)
   ```
   Eso crea el `.md` viviente (mismo basename que tu `.py`) con la
   estructura Part I–IV + Change log.  Yo después relleno Part I y
   Part III en sesión normal; tú sólo te encargas de Part IV (auto-
   derivada) y Part II (cuando haya batería).
6. **Tras cada batería** (de cualquier subset, no sólo la batería
   completa):
   ```
   /sync-method-doc methods/theory_assisted  <desc>  log: outputs/logs/<file>.log
   ```
   Refresca Part II + actualiza Status callout y Log row.

---

## Reglas no negociables (resumen del CLAUDE.md)

- **Forbidden** (no abras NINGÚN archivo bajo estas rutas, ni `.py`
  ni `.md` ni `.json` ni nada):
  - `methods/manual/`
  - `methods/autoresearch/`
  - `methods/iterated_greedy_vnd_v01/`
  - `methods/iterated_greedy_vnd_v02/`
  - `methods/brkga_v02/`  ← el primer intento del mismo Candidate C; **éste especialmente**
  - `papers/`, `problems/aircraft/`, `literature_review/`
- **El `.md` viviente se llama exactamente igual que el `.py` del solver** (mismo basename, mismo directorio, sólo cambia la extensión).
- **El log de batería más reciente aparece en DOS sitios del `.md`**:
  Status callout en el encabezado, y la fila Log de Part II.
- **Sin cambio silencioso de candidato**: si quieres pivotar a B o D,
  pregúntale al usuario y actualizad este archivo primero.
- **Comparar con otros métodos**: sólo vía `outputs/solutions/results.csv`
  y `experiments/paired_report.py`.  Nunca leyendo el código de otro
  método.

Si te encuentras a punto de violar una de estas, **para y pregúntame**.
