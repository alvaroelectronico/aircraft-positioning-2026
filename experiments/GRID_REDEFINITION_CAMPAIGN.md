# Campaña: redefinición del benchmark (sin Triangle) + veredicto Attempt 11

**Abierta: 2026-07-28.**  Decisión del usuario: Triangle probablemente sale
del paper (artificioso); el grid se extiende en espejo de Two rows para
Chain y Hub; el estado del algoritmo (baseline `main` vs Attempt 11
`exp/mode-a-band`) se decidirá midiendo AMBOS brazos sobre el grid nuevo.

## Grid extendido (generado, commit de esta campaña)

- 22 configs nuevas: {chain, hub} × R{5,10,20,30} × {loose,medium,tight}
  menos las 2 existentes (tight_R10).  220 instancias en
  `data/instances_202605_02/` (driver: `experiments/_gen_chain_hub_grid.py`).
- Benchmark de decisión (sin triangle): none_tight_R10 + chain×12 + hub×12 +
  two_rows×12 = 37 configs / 370 instancias.

## Fases pendientes (secuenciales, nunca concurrentes)

1. **MILP de referencia en las 220 instancias nuevas** (~8.5 h):
   `py -3 experiments/run_experiments.py "scn_chain_loose,scn_chain_medium,scn_chain_tight_P5_R5,scn_chain_tight_P5_R20,scn_chain_tight_P5_R30,scn_hub_loose,scn_hub_medium,scn_hub_tight_P5_R5,scn_hub_tight_P5_R20,scn_hub_tight_P5_R30" "milp_job_wMK,milp_job_wDLY,milp_job_wMOV" data/instances_202605_02`
2. **Brazo baseline** (en `main`): mismas instancias, labels `igvnd_*` (~9 h).
3. **Brazo candidato** (checkout `exp/mode-a-band`): ídem (~9 h).
4. Comparación pareada por celda (guía: script /tmp de la sesión o
   `paired_report.py`), veredicto Attempt 11 en `IMPROVEMENT_LOG.md`
   (KEPT → merge --no-ff + tag + /sync-method-doc; DROPPED → journal).
5. Batería completa de registro con el estado ganador sobre el benchmark
   definitivo → `make_tables.py` → **pasada de paper**: retirar Triangle
   (tablas, benchmark §5.1, prosa; ojo: la intro/benchmark citan Triangle
   como "the layout of the facility that motivated this study" — reescribir
   la motivación), actualizar BATTERY.md (composición) y el living spec.

## Notas
- MILP cacheado: las filas nuevas se añaden a `results.csv`; las de Triangle
  quedan (inofensivas si el paper deja de leerlas).
- Los brazos IGVND requieren el checkout correcto (el runner importa el
  solver del árbol de trabajo) — no cambiar de rama con una batería en curso.
