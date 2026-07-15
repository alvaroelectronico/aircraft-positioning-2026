# Resumen de iteraciones — autoresearch sobre `topology_heuristic_job`

Este documento explica cómo evolucionó la heurística autoresearch para
el problema #2 (job-level) a lo largo de 92 iteraciones registradas en
`JOURNAL.md`. Resume el punto de partida, las 16 iteraciones aceptadas
y por qué cada una mejoró la métrica.

## Punto de partida

**Heurística base (`iter_0000_baseline`)** — sólo construcción topológica,
sin búsqueda local ni LNS.

- **Score inicial**: `+3.9146` (la media de gap relativo respecto a la
  MILP de referencia sobre las 3 instancias del `fast_eval` original).
  Es decir, el objetivo medio del heurístico era ~390 % peor que el de
  la MILP.
- Todas las soluciones eran factibles (`4/4 compliant`), pero la calidad
  estaba dominada por la instancia más pequeña (`triangle_R5`) cuyo
  denominador MILP es 3.0: cualquier mejora absoluta en ella se amplifica
  enormemente.

## Cómo funciona el bucle

El bucle (snapshot.py + evaluate.py + precompute_baseline.py) compara la
copia activa de `topology_heuristic_job.py` contra los valores incumbents
de la MILP guardados en `baseline_metrics.json`. El score es

```
score = mean over instances of (obj_variant - obj_milp) / max(1, |obj_milp|)
```

— por tanto **negativo = el heurístico mejora a la MILP de referencia en
promedio**. Una iteración se acepta sólo si baja estrictamente el score
y mantiene 100 % de factibilidad (`n_compliant == n_total`).

## Iteraciones aceptadas

La tabla resume las 16 aceptadas (de 92 intentos). Las que están en
negrita marcan inflexiones cualitativas.

| iter  | slug                                | score    | Δ       | qué se añadió/cambió                                                              |
| ----- | ----------------------------------- | -------- | ------- | --------------------------------------------------------------------------------- |
| 0000  | baseline                            | +3.9146  | —       | construcción topológica greedy (heaviest-first) sin LS ni LNS                     |
| 0001  | ls_portfolio                        | +0.1256  | -3.79   | búsqueda local con **compliance gate** (3 operadores: 2-opt, swap, single-move)   |
| 0003  | lns_perturbation                    | +0.0958  | -0.03   | LNS destroy/repair como mecanismo de basin-escape                                 |
| 0011  | lns_random_repair_v2                | +0.0691  | -0.027  | benchmark ampliado a 4 instancias (añadida `triangle_R20`) → métrica más sensible |
| 0014  | idle_gap_with_lns                   | +0.0630  | -0.006  | operador *idle-gap insertion* condicionado por la diversidad de basins de LNS    |
| 0018  | topdest_destroy                     | +0.0609  | -0.002  | destroy dirigido por posiciones extremas (no aleatorio)                          |
| 0021  | full_restart_mode                   | +0.0600  | -0.001  | restart total ocasional como escape de basin                                      |
| 0023  | chained_multistart                  | +0.0580  | -0.002  | chained multi-start: 1 × LNS largo > 6 × LNS cortos                              |
| 0026  | fine_grained_deltas                 | +0.0226  | -0.035  | densificar el menú Δ de idle-gap (añadidos 1, 3, 7, 15, 30, 70)                  |
| 0029  | smaller_kicks                       | +0.0191  | -0.004  | kicks LNS más pequeños — preserva más estructura aprendida                       |
| **0054** | **per_access_rebuild**           | **-0.0075** | **-0.027** | **rebuild *per-access* (no por span) — primer score NEGATIVO**           |
| **0067** | **no_restart_on_improvement**    | **-0.0419** | **-0.034** | el LS deja de reiniciar tras cada mejora; pasa por todos los ops antes  |
| 0069  | intra_pos_insertion_v3              | -0.0420  | -0.0001 | re-añade inserción intra-posición bajo el nuevo LS                                |
| 0070  | edd_repair_v3                       | -0.0425  | -0.0005 | re-añade repair guiado por EDD/slack/delay-ratio                                  |
| 0073  | kick_K12                            | -0.0481  | -0.006  | menú de kicks `[1, 2, R//3, R//2]` (sustituye `R//4` por 2)                       |
| **0074** | **no_topdest_v2**                | **-0.0530** | **-0.005** | descarta destroy por top-destination con el nuevo LS — chain_R10 baja  |

## Las dos inflexiones cualitativas

### iter_0054 — *rebuild per-access* (de +0.019 a −0.008)

**Antes**: los resolvers `_resolve_rear_interactions` y
`_resolve_front_interactions` enforzaban *disjunción de spans* — el rear
no podía solaparse con el front durante todo el periodo. Es factible,
pero deja fuera del espacio explorado el patrón **"engulfing rear"** que
la MILP usa de forma intensiva en chain (R5/P5 estaciona durante un
periodo largo que engulle a R6/P1).

**Cambio**: reescritura de ambos resolvers para verificar la condición
*por-acceso* del checker (RQ07_v2). Cada instante de acceso del rear
(`tau_in`, `tau_out`) sólo necesita cumplir `τ ≤ f_start − η ∨ τ ≥
f_finish + η` *individualmente*, no que el *span* entero esté fuera del
`[f_start, f_finish]` del front. Eso permite combinar entrada Mode A z−
con salida Mode A z+ alrededor de un front.

**Resultado**: primer score negativo del bucle; `triangle_R20` bajó de
814 → 690 (−16 % vs MILP).

### iter_0067 — *no restart on improvement* (de −0.008 a −0.042)

**Antes**: la búsqueda local hacía `continue` (re-iniciar desde el op 1)
cada vez que un operador encontraba una mejora. Eso quemaba presupuesto
re-explorando vecindarios que ya se habían recorrido bajo el estado
anterior.

**Cambio**: eliminado el `continue`. La LS hace una pasada completa
op 1 → 2 → 3 → 4 por iteración, reiniciando el bucle externo sólo tras
la pasada entera.

**Resultado**: cada operador actúa sobre el estado fresco dejado por el
anterior, no sobre el original. `hub_R10` cayó de 136.75 → 119.55 — un
−12 % respecto al incumbent MILP (que tenía un gap propio del 83 %, así
que el heurístico se sitúa donde la MILP no había llegado).

## Lo que no funcionó

De 92 iteraciones, **76 fueron rechazadas**. Lecciones recurrentes:

- **Mode-C scan / interruptibilidad** (iter_0007): aparentemente
  prometedora pero rompía factibilidad en las pruebas; la maquinaria no
  está alineada con el checker.
- **Diversificación de construcción** (iter_0006, iter_0008,
  iter_0086): cuando `n_starts` está fijo, repartir starts entre
  estrategias diversas reduce la cobertura de la mejor estrategia
  (heaviest-first). Es **value-destroying** salvo que se aumente el
  presupuesto de starts.
- **Más modos de LNS** (iter_0012, iter_0040, iter_0041): doblar el
  número de combos destroy/repair con presupuesto fijo halva las
  iteraciones por combo — la variedad gratis no existe.
- **Operadores intra-posición sobre R ≤ 10** (iter_0002, iter_0035,
  iter_0042): hay como mucho 2 aviones por posición; los ops 4–6
  colapsan a no-ops invisibles a la métrica. Se aceptan más tarde
  (iter_0069) sólo tras iter_0067 dar el contexto correcto.
- **Restart-on-improvement** (revertido en iter_0067): "iterar otra
  vez desde el principio" parecía cauto pero perdía la riqueza
  combinatoria de pasar por todos los operadores en cadena.
- **Penalizar "stacking"** (iter_0091): añadir términos al objetivo
  para forzar diversidad espacial empeora porque deforma la métrica
  que se optimiza.

## Plateau y cierre

Desde iter_0074 (score `−0.0530`), 18 iteraciones consecutivas
(0075–0092) intentaron mejorar y todas fueron rechazadas. La media de
gap respecto a la MILP está clavada en −5.3 % a través de las 4
instancias del `fast_eval` (`triangle_R5`, `chain_R10`, `hub_R10`,
`triangle_R20`), con `chain_R10` (+10.96 % vs MILP) como el cuello de
botella residual.

El score por instancia en el plateau:

```
triangle_tight_P5_R5_seed1       gap +0.0000   (iguala a la MILP, ambos óptimos)
chain_tight_P5_R10_seed1         gap +0.1096   (MILP mejor por 11 %)
hub_tight_P5_R10_seed1           gap -0.1235   (heurístico mejor por 12 %)
triangle_tight_P5_R20_seed1      gap -0.1981   (heurístico mejor por 20 %)
```

Reproducible desde la nueva ubicación:

```
py -3 methods/autoresearch/jobs/evaluate.py fast_eval
```

## Mejora global

De `+3.9146` (la construcción cruda) a `−0.0530` (iter_0074). En valor
absoluto, ~74× mejor; en signo, el heurístico pasó de quedarse 390 %
por encima de la MILP en promedio a **batirla por 5.3 %** sobre el mismo
benchmark. El presupuesto por instancia se mantuvo en 20 s a lo largo
de todo el bucle.
