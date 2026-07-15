# Propuesta inicial de implementación: BRKGA-decoder para aircraft positioning con scheduling a nivel de jobs

Sí. Mi recomendación es empezar por una versión **decoder-first**, muy conservadora y verificable. El BRKGA es casi mecánico una vez que el decoder produce soluciones factibles; en este problema el riesgo está en la clasificación de accesos y en la consistencia de \(\kappa_j\), porque el checker valida precisamente esas condiciones.

La idea metodológica encaja bien con BRKGA: Los cromosomas de claves aleatorias son especialmente útiles cuando la solución real se obtiene mediante un decoder que transforma claves continuas en asignaciones, permutaciones o calendarios; este es exactamente el patrón descrito por Gonçalves y Resende para BRKGA en combinatoria. Además, el enfoque de construir una solución y después mejorarla es coherente con la filosofía GRASP clásica de construcción + mejora local, aunque aquí la construcción la realiza el decoder de forma determinista o semideterminista.

## Propuesta inicial

Yo empezaría con tres hitos, no con todo el método completo:

1. **Hito 1: Decoder factible conservador.**  
   Implementar un decoder que asigna posiciones y secuencias, pero que inicialmente evita interrupciones de tipo C salvo que estés completamente seguro de actualizar bien \(\kappa_j\), los tiempos de jobs y las precedencias posteriores. Esta primera versión debe pasar el checker de forma robusta.

2. **Hito 2: Decoder con modo C controlado.**  
   Añadir interrupciones solo cuando el job frontal es interrumpible y la extensión \(\delta\) puede propagarse sin romper precedencias, separaciones \(\varepsilon\) ni accesos ya fijados.

3. **Hito 3: Integración BRKGA + warm-start.**  
   Inyectar soluciones iniciales y ejecutar evolución. La API Python espera un objeto decoder con método `decode(self, chromosome, rewrite) -> float`, y el cromosoma se trata como una lista de floats en \([0,1]\). Las soluciones warm-start deben codificarse como cromosomas y pasarse con `set_initial_population()` antes de `initialize()`.

Una advertencia importante: No asumiría todavía el componente IPR en Python. En la versión actual visible del repositorio, `path_relink()` aparece declarado, pero lanza `NotImplementedError`. Por tanto, para la primera implementación usaría BRKGA sin IPR y dejaría el path relinking como mejora posterior propia o como cambio a otra implementación si hiciera falta.

---

## Estructura de implementación recomendada

Separaría el código en módulos pequeños. Esto facilitará comparar contra `checker.py`.

```text
solver/
  instance.py          # Lectura y normalización del JSON
  chromosome.py        # Decode / encode de cromosomas
  schedule_state.py    # Estructuras de calendario
  access.py            # Clasificación modo A/B/C
  decoder.py           # Decoder BRKGA
  warm_start.py        # Reverse-encoding de soluciones existentes
  run_decoder_smoke.py # Tests con cromosomas aleatorios
  run_brkga.py         # Bucle BRKGA
```

## Representación interna

Yo usaría una representación explícita, aunque el JSON final sea distinto.

```python
@dataclass
class JobState:
    job_id: str
    aircraft_id: str
    start: float
    finish: float
    duration: float
    interruptible: bool
    kappa: int = 0

@dataclass
class AircraftState:
    aircraft_id: str
    position: str
    start: float
    finish: float
    jobs: list[JobState]

@dataclass
class ScheduleState:
    aircraft: dict[str, AircraftState]
    by_position: dict[str, list[str]]
    movements: int = 0
```

La clave es que `ScheduleState` sea fácil de consultar:

```python
state.aircraft[r].start
state.aircraft[r].finish
state.aircraft[r].jobs[k].start
state.aircraft[r].jobs[k].finish
state.by_position[p]
```

---

## Decodificación del cromosoma

Mantendría tu layout de longitud \(2|R|\), pero con dos detalles importantes.

### 1. Asignación de posición

Evita errores de borde si una clave vale exactamente 1.0:

```python
pos_idx = min(int(key_assignment[r] * num_positions), num_positions - 1)
position = positions[pos_idx]
```

Para que el decoder sea reproducible, ordena siempre aeronaves y posiciones con listas fijas, no con el orden de diccionarios.

### 2. Secuencia dentro de cada posición

Ordena por clave de secuenciación y rompe empates por id:

```python
assigned[p].sort(key=lambda r: (seq_key[r], aircraft_index[r]))
```

---

## Orden de construcción del calendario

Como los arcos van de posición frontal a posición trasera, conviene programar las posiciones en **orden topológico** del grafo \(G=(P,A)\). Si \((p,p') \in A\), entonces \(p\) debe estar programada antes que \(p'\).

Esto permite que, cuando programes una aeronave en una posición trasera, los calendarios de sus posiciones frontales ya existan.

```python
topological_positions = topo_sort_positions(front_to_rear_arcs)
for p in topological_positions:
    for r in sequence_by_position[p]:
        schedule_aircraft_earliest_feasible(r, p, state)
```

Este orden no resuelve por sí solo el modo C completo, porque una interrupción en una posición frontal puede modificar tiempos ya programados. Por eso recomiendo que la primera versión sea conservadora.

---

## Decoder v0: Factible y conservador

La primera versión debe programar cada aeronave con jobs contiguos, sin gaps voluntarios y con \(\kappa_j = 0\). Para una aeronave \(r\) en posición \(p\):

\[
s_r \ge \max(E_r,\ f_{\text{última en }p}+\varepsilon)
\]

\[
f_r = s_r + T_r
\]

Después se exige que tanto \(s_r\) como \(f_r\) sean accesos factibles para todos los arcos \((q,p)\) que bloquean \(p\).

### Clasificación conservadora

Para cada acceso \(\tau\) de una aeronave en posición \(p\), y para cada posición frontal \(q\) con \((q,p) \in A\):

1. **Modo A:** No hay aeronave en \(q\) ocupando \(\tau\).
2. **Modo B:** \(\tau\) cae en un gap inter-job ya existente de una aeronave en \(q\) y el gap mide al menos \(\mu\).
3. **Modo C:** En v0, no lo usaría todavía.
4. **Inviable:** Si no es A ni B.

Si el acceso es inviable, empujas \(s_r\) hacia delante hasta el siguiente instante en el que tanto entrada como salida sean factibles.

Esta versión tenderá a esperar a que las posiciones frontales estén libres. Será peor en makespan y retraso, pero debería ser muy robusta. Para empezar, eso es deseable.

---

## Forma limpia de calcular el earliest feasible start

En vez de probar tiempos uno a uno, construiría conjuntos de ventanas factibles.

Para una posición trasera \(p\), define:

\[
\mathcal{A}_p = \{\tau : \tau \text{ es un instante de acceso factible para } p\}
\]

Si \(p\) no tiene posiciones frontales, entonces:

\[
\mathcal{A}_p = [0,\infty)
\]

Si tiene una o varias posiciones frontales, \(\mathcal{A}_p\) es la intersección de las ventanas factibles respecto a cada frontal.

Para programar una aeronave \(r\) con duración agregada \(T_r\), necesitas:

\[
s_r \in \mathcal{A}_p
\]

Y:

\[
s_r + T_r \in \mathcal{A}_p
\]

Por tanto:

\[
s_r \in \mathcal{A}_p \cap (\mathcal{A}_p - T_r)
\]

Y además:

\[
s_r \ge \max(E_r,\ f_{\text{última en }p}+\varepsilon)
\]

Esta es la función central del decoder:

```python
def earliest_start_for_aircraft(r, p, lower_bound, state):
    access_windows = feasible_access_windows(p, state)
    shifted_exit_windows = shift_windows(access_windows, -T[r])
    feasible_start_windows = intersect_windows(access_windows, shifted_exit_windows)
    return first_point_at_or_after(feasible_start_windows, lower_bound)
```

Esta función es más estable que un bucle de reparación ad hoc.

---

## Cómo construir ventanas factibles de acceso

Para cada posición frontal \(q\), genera ventanas en las que un acceso a una posición trasera sería factible.

### Ventanas de modo A

Son los intervalos en los que \(q\) está vacante. Si en \(q\) tienes aeronaves ordenadas:

```text
r1: [s1, f1]
r2: [s2, f2]
r3: [s3, f3]
```

entonces las ventanas vacantes son aproximadamente:

```text
[0, s1)
(f1, s2)
(f2, s3)
(f3, +inf)
```

Usaría un `TOL = 1e-6` para evitar caer justo en los extremos, porque el enunciado define ocupación frontal con intervalo cerrado \(s_r \le \tau \le f_r\).

### Ventanas de modo B

Dentro de una aeronave frontal, para cada par de jobs consecutivos:

```python
gap_start = job_k.finish
gap_end = job_k_plus_1.start
if gap_end - gap_start >= mu:
    add_window(gap_start, gap_end, mode="B")
```

En v0, como programaremos jobs contiguos, casi no habrá modo B. Aun así, implementaría esta clasificación desde el principio para que el código ya tenga la estructura correcta.

### Modo C

No lo añadiría en la primera pasada. Dejaría la función preparada:

```python
if allow_mode_c:
    # TODO v1
```

---

## Por qué no metería modo C desde el primer día

El modo C no es solo “sumar un movimiento y `kappa_j += 1`”. Si interrumpes un job frontal \(j\), su finish pasa a ser:

\[
f_j = s_j + D_j + \delta \kappa_j
\]

Entonces pueden cambiar:

1. **La precedencia con el siguiente job:** Si el siguiente job empezaba justo al terminar el anterior, ahora viola la cadena.
2. **El finish de la aeronave frontal:** Puede aumentar.
3. **La separación con la siguiente aeronave en la misma posición:** Puede violar \(\varepsilon\).
4. **Los accesos de esa propia aeronave si su posición también es trasera:** Su salida cambia y quizá deja de ser factible.
5. **Los accesos de aeronaves traseras ya programadas detrás de ella:** Pueden cambiar de modo o volverse inviables.

Por tanto, el modo C necesita propagación temporal. Meterlo sin propagación probablemente dará soluciones que parecen buenas pero fallan el checker.

---

## Decoder v1: Modo C seguro

Cuando v0 pase el checker, añadiría modo C solo bajo una de estas dos políticas.

### Política C1: Modo C con slack local

Permitir interrupción si el job frontal es interrumpible y existe slack suficiente después del job para absorber \(\delta\) sin mover nada más.

Para un job \(j_k\):

```python
available_slack = next_start_after_job - job_k.finish
if interruptible and available_slack >= delta:
    allow_mode_c
```

Si el job es el último de la aeronave, el `next_start_after_job` debería ser el inicio mínimo permitido de la siguiente aeronave en la misma posición menos \(\varepsilon\), si existe.

**Ventaja:** Es fácil y seguro.

**Desventaja:** Usará pocos modos C.

### Política C2: Modo C con propagación de sufijo

Permitir interrupción y después desplazar:

1. Los jobs posteriores de la misma aeronave frontal.
2. El finish de esa aeronave.
3. Las aeronaves posteriores en la misma posición frontal.
4. Cualquier acceso afectado aguas abajo.

Esta política es más potente, pero yo la dejaría para más adelante.

---

## Funciones que programaría primero

### 1. `decode_chromosome`

```python
def decode_chromosome(chromosome, instance):
    nR = len(instance.aircraft)
    assignment_keys = chromosome[:nR]
    sequence_keys = chromosome[nR:]

    pi = decode_positions(assignment_keys, instance.positions)
    seq = decode_sequences(sequence_keys, pi)

    return pi, seq
```

### 2. `build_schedule_v0`

```python
def build_schedule_v0(pi, seq, instance):
    state = empty_schedule_state(instance)

    for p in instance.topological_positions:
        last_finish = None

        for r in seq[p]:
            lower = instance.E[r]
            if last_finish is not None:
                lower = max(lower, last_finish + instance.epsilon)

            start = earliest_start_for_aircraft(
                r=r,
                p=p,
                lower_bound=lower,
                state=state,
                instance=instance,
            )

            add_aircraft_with_contiguous_jobs(
                r=r,
                p=p,
                start=start,
                state=state,
                instance=instance,
            )

            last_finish = state.aircraft[r].finish

    classify_all_accesses_and_count_movements(state, instance)
    return state
```

### 3. `classify_access`

Debe devolver clasificación por arco, no solo por aeronave. Si \(p\) tiene dos posiciones frontales, un mismo acceso puede generar movimientos por ambas.

```python
def classify_access(tau, rear_position, state, instance):
    events = []

    for front_position in instance.fronts_of[rear_position]:
        event = classify_against_one_front(
            tau=tau,
            front_position=front_position,
            state=state,
            instance=instance,
        )
        events.append(event)

    return events
```

Cada evento debería tener algo así:

```python
@dataclass
class AccessEvent:
    front_position: str
    rear_position: str
    tau: float
    mode: str  # "A", "B", "C"
    front_aircraft: str | None = None
    front_job: str | None = None
    movements: int = 0
```

### 4. `compute_objective`

```python
def compute_objective(state, instance):
    makespan = max(a.finish for a in state.aircraft.values())
    total_delay = sum(
        max(0.0, state.aircraft[r].finish - instance.L[r])
        for r in instance.aircraft_ids
    )
    movements = state.movements

    return (
        instance.WM * makespan
        + instance.WD * total_delay
        + instance.WS * movements
    )
```

---

## Reverse-encoding para warm-start

Para una solución existente:

### 1. Genes de asignación

Si la aeronave \(r\) está en la posición con índice \(k\):

```python
assignment_gene[r] = (k + 0.5) / num_positions
```

Esto evita caer justo en los bordes entre posiciones.

### 2. Genes de secuenciación

Para cada posición, ordena las aeronaves por su start real:

```python
ordered = sorted(aircraft_in_p, key=lambda r: solution.start[r])
```

Y asigna claves crecientes:

```python
sequence_gene[r] = (rank + 0.5) / len(ordered)
```

Para aeronaves aisladas en una posición, puedes usar 0.5.

---

## Integración BRKGA mínima

Cuando el decoder v0 pase el smoke test, el wrapper BRKGA debería ser casi directo:

```python
class HangarDecoder:
    def __init__(self, instance):
        self.instance = instance
        self.best_solution = None
        self.best_fitness = float("inf")

    def decode(self, chromosome, rewrite):
        pi, seq = decode_chromosome(chromosome, self.instance)
        state = build_schedule_v0(pi, seq, self.instance)
        solution = to_solution_dict(state, self.instance)
        fitness = compute_objective(state, self.instance)

        if fitness < self.best_fitness:
            self.best_fitness = fitness
            self.best_solution = solution

        return fitness
```

La documentación de BRKGA-MP-IPR indica que el algoritmo necesita ese decoder, después se inicializa con `initialize()`, se evoluciona con `evolve()` y se recupera el mejor fitness o cromosoma con `get_best_fitness()` y `get_best_chromosome()`.

---

## Tests iniciales que te pediría correr

Antes de BRKGA, haría estos tests:

1. **Test de asignación:** Generar 100 cromosomas aleatorios y comprobar que cada aeronave queda en exactamente una posición.

2. **Test de secuencia:** Verificar que en cada posición no hay solapes y que entre aeronaves consecutivas se cumple \(\varepsilon\).

3. **Test de precedencias:** Verificar que, para cada aeronave, los jobs son contiguos en v0 y cumplen:

   \[
   s_{j_{k+1}} \ge f_{j_k}
   \]

4. **Test de accesos:** Para cada aeronave en posición trasera, clasificar entrada y salida contra todos sus frontales. Ningún evento debe ser inviable.

5. **Test checker:** Ejecutar `checker.py` sobre 10, luego 100 cromosomas aleatorios.

6. **Test objetivo:** Comparar el objetivo calculado por tu solver con el objetivo calculado o inferido por el checker, si el checker lo reporta.

---

## Primer smoke test recomendado

No empezaría con `scn_triangle_tight` directamente si es muy restrictiva. Haría esta secuencia:

1. **Instancia pequeña sin arcos:** Debe comportarse como scheduling por posiciones.
2. **Instancia con un arco simple:** Una posición frontal y una trasera.
3. **Instancia triangular:** Ya con varios bloqueos.
4. **`scn_triangle_tight`:** Solo cuando los tres casos anteriores pasen el checker.

El objetivo del primer día no debería ser ganar al MILP. Debería ser producir soluciones factibles de forma sistemática.

---

## Decisión técnica clave para la primera iteración

Mi directriz concreta sería esta:

**Implementa primero `build_schedule_v0` sin modo C y con ventanas de acceso A/B.**

Es la versión que maximiza la probabilidad de pasar el checker. Cuando me pases resultados, lo más útil sería que incluyas para cada instancia:

```text
instance_name
num_aircraft
num_positions
num_arcs
checker_pass: yes/no
objective
makespan
total_delay
movements
runtime_decoder_avg_ms
best_random_of_100_objective
errores del checker, si los hay
```

Con eso podremos decidir si el siguiente paso debe ser mejorar el decoder, añadir modo C, añadir gaps inter-job, o integrar ya el BRKGA.

---

## Referencias académicas

- Gonçalves, J. F., & Resende, M. G. C. (2011). *Biased random-key genetic algorithms for combinatorial optimization*. **Journal of Heuristics**, 17, 487–525.
- Feo, T. A., & Resende, M. G. C. (1995). *Greedy randomized adaptive search procedures*. **Journal of Global Optimization**, 6, 109–133.
