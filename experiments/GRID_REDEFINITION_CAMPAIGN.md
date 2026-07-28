# Campaña: redefinición del benchmark (sin Triangle) + veredicto Attempt 11

**Abierta: 2026-07-28.  Diseñada para ejecutarse en OTRA máquina.**

Contexto: Triangle probablemente sale del paper (artificioso).  El grid se ha
extendido en espejo de Two rows para Chain y Hub (220 instancias nuevas, ya
generadas y commiteadas).  El estado del algoritmo — baseline (`main`) vs
Attempt 11 (`exp/mode-a-band`, geometría Mode-A alternada) — se decidirá
midiendo AMBOS brazos sobre el grid nuevo.  Datos del Attempt 11 hasta ahora:
`methods/iterated_greedy_vnd_v01/IMPROVEMENT_LOG.md`, entrada 11 (ON HOLD).

## Prerrequisitos en la máquina de ejecución

1. `git clone` / `git pull` — se necesita `main` ≥ `002a55a` (instancias
   nuevas incluidas) y la rama `exp/mode-a-band` (está en origin).
2. Python 3.11+ (solo stdlib para IGVND).  Para la fase 1 (MILP):
   `gurobipy` con **licencia activa en esa máquina** (`gurobi_cl --license`).
3. Energía: suspensión con corriente = **Nunca**, equipo enchufado, tapa
   abierta si es portátil (una suspensión a mitad de run infla su wall-time;
   ya ocurrió el 2026-07-23).
4. **Nunca dos baterías a la vez** en la misma máquina.
5. Las fases 2 y 3 (los dos brazos IGVND) deben correr **en la misma máquina**
   — se comparan entre sí; con máquinas distintas la comparación no vale.

## Fase 1 — MILP de referencia en las 220 instancias nuevas (~8.5 h)

```
py -3 experiments/run_experiments.py "scn_chain_loose,scn_chain_medium,scn_chain_tight_P5_R5,scn_chain_tight_P5_R20,scn_chain_tight_P5_R30,scn_hub_loose,scn_hub_medium,scn_hub_tight_P5_R5,scn_hub_tight_P5_R20,scn_hub_tight_P5_R30" "milp_job_wMK,milp_job_wDLY,milp_job_wMOV" data/instances_202605_02
```

660 runs (los R5 cierran en <1 s; el resto agota ~60 s + build).  Los R30
pueden agotar memoria en algún seed — queda registrado como fallo y es
esperado/aceptable.

Al terminar, commit + push (los resultados viajan por git):

```
git add outputs/solutions outputs/logs && git commit -m "campaign phase 1: MILP reference on the 22 new chain/hub configs" && git push
```

> Nota de homogeneidad: las configs viejas (tight_R10 de chain/hub, none,
> two_rows×12) ya tienen filas MILP del modelo relajado (batería 2026-07-23/24,
> otra máquina).  Para el VEREDICTO de brazos es irrelevante (contexto), pero
> si se quiere homogeneidad total del MILP para las tablas finales del paper,
> re-correr también esas 15 configs en esta máquina (~7.5 h extra):
> filtro `"scn_none,scn_chain_tight_P5_R10,scn_hub_tight_P5_R10,scn_two_rows"`.

## Fase 2 — brazo BASELINE (rama `main`) (~14 h)

```
git switch main
py -3 experiments/run_experiments.py "scn_none,scn_chain,scn_hub,scn_two_rows" "igvnd_wMK,igvnd_wDLY,igvnd_wMOV" data/instances_202605_02
```

1110 runs (37 configs × 10 seeds × 3 perfiles; el runner importa el solver
del árbol de trabajo — **no cambiar de rama mientras corre**).  Apuntar el
nombre del log que produce (`outputs/logs/..._<timestamp>.log`).
Commit + push como en la fase 1.

## Fase 3 — brazo CANDIDATO (rama `exp/mode-a-band`) (~14 h)

```
git switch exp/mode-a-band
py -3 experiments/run_experiments.py "scn_none,scn_chain,scn_hub,scn_two_rows" "igvnd_wMK,igvnd_wDLY,igvnd_wMOV" data/instances_202605_02
git switch main
```

Mismas 1110 ejecuciones.  Apuntar el log.  Commit + push (el commit de
resultados puede hacerse desde main; los outputs no dependen de la rama).

## Fase 4 — veredicto

```
py -3 experiments/attempt11_grid_verdict.py \
    --baseline-log  outputs/logs/<log_fase_2>.log \
    --candidate-log outputs/logs/<log_fase_3>.log
```

Imprime la tabla pareada por celda, NET global y por topología, y las
regresiones consistentes sobre el suelo de ruido (~19 unidades).  Criterio:
**KEPT** si el NET es favorable sin regresiones consistentes (≥7/10 seeds)
por encima del ruido; en la duda, se decide con el usuario.

Cierre según veredicto (ver `IMPROVEMENT_LOG.md` §How to use):
- KEPT → `git merge --no-ff exp/mode-a-band` en main + tag
  `igvnd-v01-mode-a-band` + `/sync-method-doc`.
- DROPPED → rama retenida + fila "attempted & DROPPED" en el Change log.

## Fase 5 — batería de registro + tablas + paper (con Claude en sesión)

1. Batería completa de registro con el estado ganador sobre el benchmark
   definitivo (sin triangle) → ese log pasa a ser el log de registro.
2. Actualizar `papers/jobs_extension/make_tables.py`: apuntar `BATTERY_LOG`
   al log nuevo y **excluir triangle** de las configs.
3. `py -3 papers/jobs_extension/make_tables.py` → tablas nuevas.
4. Pasada de paper: retirar Triangle (benchmark §, tablas, prosa; reescribir
   la motivación — hoy la intro/benchmark citan Triangle como "the layout of
   the facility that motivated this study"); re-verificar TODA cifra de la
   prosa contra las tablas nuevas (regla: nunca inventar).
5. Actualizar `experiments/BATTERY.md` (composición del benchmark) y el
   living spec (`/sync-method-doc`).

## Estado

- [x] Grid generado y commiteado (`002a55a`): 220 instancias chain/hub.
- [x] Script de veredicto: `experiments/attempt11_grid_verdict.py`.
- [ ] Fase 1 (MILP nuevas)          — máquina B
- [ ] Fase 2 (brazo baseline)       — máquina B
- [ ] Fase 3 (brazo candidato)      — máquina B
- [ ] Fase 4 (veredicto)            — cualquier máquina, tras push de 2+3
- [ ] Fase 5 (registro + paper)     — con Claude en sesión
