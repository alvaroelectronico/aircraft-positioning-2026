# Reanudar la batería MILP (modelo relajado) — estado y runbook

**Última actualización: 2026-07-24 12:25** (parada manual solicitada por el
usuario a mitad de batería).

## Contexto — por qué se está relanzando el MILP

La auditoría forense del 2026-07-23 (commit `96d2595`) demostró que el
modelo MILP baseline era **más conservador que el problema declarado**: los
estados before/after (z∓) exigían una holgura η completa alrededor de la
estancia del avión frontal, mientras que el problem statement y
`problems/jobs/checker.py` consideran vacante cualquier instante fuera de
`[s_r, f_r]`.  El heurístico explotaba legalmente esa banda (accesos a
±ε=0.5 del frontal) y quedaba por debajo de "óptimos probados" del MILP.

El modelo se corrigió en el commit **`0fb58ea`**
(`methods/manual/jobs/milp_jobs_v2_gurobipy.py`, restricciones `zm`/`zp`:
`τ ≤ s_r` y `τ ≥ f_r`, antes `∓η`).  Smoke tests en ese commit:
`two_rows_loose seed8 wDLY` → obj **61.5 óptimo probado** (modelo viejo:
115.5); `triangle_tight_R5 seed1 wMK` → 3000.0 sin cambios.

Según la regla de `experiments/BATTERY.md`, **la caché MILP quedó
invalidada** y hay que relanzar las 870 ejecuciones
(290 instancias × 3 perfiles).  Las filas nuevas en
`outputs/solutions/results.csv` superseden a las viejas por timestamp
(la agregación siempre toma la fila más reciente por `(instancia, label)`).

## Estado en el momento de la parada

- Batería lanzada el **2026-07-23 19:03**; parada el **2026-07-24 12:23**
  en el run 614/870.
- **613/870 filas grabadas** en `results.csv` (timestamps ≥ `20260723_19`):
  - Seeds **1–7 completos** (87 filas por seed = 29 configs × 3 perfiles).
  - Seed 8 parcial: 4 filas (chain_tight_R10 ×3 + full_tight_R10 wMK).
  - El run en vuelo al parar (`full_tight_P5_R10_seed8  milp_job_wDLY`)
    murió sin escribir fila — inofensivo.
- Sin errores de licencia (renovada el 2026-07-23: LicenseID 2847819,
  expira 2027-07-23, en `C:\Users\alvaro\gurobi.lic`; cualquier proceso
  nuevo la usa automáticamente).
- Incidencia registrada: en la noche del 23→24 el equipo se suspendió y
  dos runs absorbieron la pausa como tiempo propio (ver "Limpieza" abajo).

## Cómo reanudar

**Precondiciones** (2 min):

1. Ninguna otra batería en curso: `tasklist | findstr /i python` vacío.
2. Portátil **enchufado**, tapa abierta, y suspensión con corriente =
   Nunca (ya configurado el 2026-07-24).

**Comando de reanudación** (seeds 8–10 completos; ~261 runs ≈ **3.3 h**):

```
py -3 experiments/run_experiments.py "_seed8$,_seed9$,_seed10$" "milp_job_wMK,milp_job_wDLY,milp_job_wMOV" data/instances_202605_02
```

Redundancia asumida: repite las 4 filas de seed8 ya grabadas (~4 min);
es inofensivo — la fila más reciente gana.

## Limpieza — las 2 ejecuciones extra pendientes

Dos filas de seed3 tienen el **tiempo de pared contaminado** por la
suspensión nocturna del equipo (27 481 s y 4 947 s registrados con límite
de 60 s).  Sus objetivos/incumbentes son válidos y **no afectan a las
tablas del paper** (usan objetivos y gaps, no tiempos), pero para dejar el
ledger limpio hay que re-ejecutarlas (~2 min en condiciones normales):

```
py -3 experiments/run_experiments.py "scn_triangle_medium_P5_R10_seed3$" "milp_job_wDLY,milp_job_wMOV" data/instances_202605_02
```

## Verificación al terminar

```
py -3 - <<EOF
import csv, re
rows = [r for r in csv.reader(open("outputs/solutions/results.csv", newline="", encoding="utf-8"))
        if len(r) >= 10 and r[2].startswith("milp_job_") and r[3] >= "20260723_19"]
pairs = {(r[0], r[2]) for r in rows}
print("pares (instancia,label) con fila nueva:", len(pairs), "/ 870 esperados")
seeds = {}
for inst, lab in pairs:
    s = int(re.search(r"_seed(\d+)$", inst).group(1)); seeds[s] = seeds.get(s, 0) + 1
print("por seed (esperado 87):", dict(sorted(seeds.items())))
EOF
```

- Esperado: 870 pares (87 × 10 seeds).  Posible excepción legítima: los
  seeds R=30 wMK que agoten memoria (OOM) — en la batería vieja fueron 2
  (triangle_loose y two_rows_tight); con el modelo relajado pueden
  repetirse o no.  Un OOM se registra como fallo sin solución y las
  tablas lo marcan explícitamente.

## Pipeline post-batería

1. **Regenerar las tablas del paper** (lee filas MILP más recientes de
   `results.csv` + gaps de los JSON; el lado heurístico sigue clavado al
   log de la batería del 2026-07-14 — no se relanza):

   ```
   py -3 papers/jobs_extension/make_tables.py
   ```

2. **Pasada de prosa post-batería** en `papers/jobs_extension/` —
   re-verificar cada número contra las tablas nuevas (regla: nunca
   inventar cifras) y actualizar:
   - `milp.tex`: las ecuaciones z∓ aún muestran `∓η` — actualizarlas al
     modelo relajado; reescribir el párrafo de "η-clearance conservatism"
     (el modelo ya está alineado con la semántica del problema; la
     conservadurez vieja puede citarse como nota histórica o eliminarse).
   - `computational_results.tex`: párrafo "Delay-priority outliers"
     (esperable: el +11 % de Two rows colapsa hacia ~0 y desaparece la
     explicación por banda η) y párrafo "Movement-priority profile"
     (esperable: desaparecen los casos "beats the certified optimum").
   - `conclusions.tex`: frase "ending below the MILP's reported optimum
     … marginally conservative feasible set" — ya no aplicará.
   - Abstract: re-verificar los claims cuantitativos si los gaps cambian.
3. **Compilar** (`latexmk`/`pdflatex` + bibtex; ojo si `paper.pdf` está
   abierto en un visor — usar `-jobname` alterno para verificar).
4. **Commit y push** (mensajes tipo `paper(jobs_extension): …` /
   `experiments: …` como en el historial).

## Referencias

- Modelo relajado: commit `0fb58ea` · Auditoría: commit `96d2595`.
- Protocolo general de batería: `experiments/BATTERY.md` (nota: su
  sección "Composition" dice 12 configs — está desactualizada; el grid
  real son 29 configs / 290 instancias desde el commit `a932289`).
- Tiempos de referencia: ~46 s/run de media (0.4 s en R=5; ~60–70 s en
  R≥10, presupuesto de 60 s + build).
