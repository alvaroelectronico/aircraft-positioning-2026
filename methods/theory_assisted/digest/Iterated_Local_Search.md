# Stützle & Ruiz 2025 — Iterated Local Search (Handbook of Heuristics chapter)

**Citation:** Stützle T., Ruiz R. (2025) Iterated Local Search. In: Martí R. et al. (eds.) *Handbook of Heuristics*. Springer Nature Switzerland AG. Chapter 26, pp. 779–803. https://doi.org/10.1007/978-3-032-00385-0_8
**Source:** methods/theory_assisted/inspiration/Iterated_Local_Search.pdf
**Read on:** 2026-06-11

## Problem solved by this source

This is a reference chapter (not a paper solving one specific problem). It provides a self-contained, authoritative exposition of the Iterated Local Search (ILS) metaheuristic: its four-component framework (GenerateInitialSolution / Perturbation / LocalSearch / AcceptanceCriterion), its relationship to VNS, GRASP, tabu search, simulated annealing, and memetic algorithms, and a survey of successful applications in scheduling, routing, and assignment.

The scheduling application section (pp. 797–798) is directly relevant. Problems covered include: single-machine total weighted tardiness (SMTWTP), parallel-machine weighted tardiness, permutation flow-shop makespan and flowtime, blocking flow-shop, job-shop weighted tardiness, and complex hybrid flowline scheduling. Several of these share structural features with paper #2: precedence-chained jobs, makespan + tardiness objectives, position/machine assignment combined with job sequencing.

## Technique

**Core ILS framework (Fig. 1, p. 783).** Four procedures:
1. `GenerateInitialSolution` — any constructive heuristic; quality of initial solution matters most in the early search phase but diminishes for long runs.
2. `Perturbation(s*, history)` — transforms the current local optimum into a new starting point for local search. Must be larger in scope than local search moves to escape the current basin, but not so large as to destroy solution structure (risk of random restart behaviour). Perturbation size is the critical tuning parameter.
3. `LocalSearch(s')` — any improvement method: iterative improvement (best/first improvement), tabu search, simulated annealing, VND, etc. The chapter explicitly notes that the local search can itself be a sophisticated method, including non-improvement methods.
4. `AcceptanceCriterion(s*, s*', history)` — controls exploration/exploitation balance. Choices: strict improvement only (intensification), Metropolis condition `exp{(f(s*) − f(s*'))/T}` (simulated annealing-style, diversification), random-walk (accept all), or history-based restarts.

**Perturbation design principles (p. 784–785).** Random perturbation (uniform selection of components to change) is the simplest but loses quality. Biased perturbations using heuristic information are preferable: remove high-cost components, introduce low-cost components, or use destruction-reconstruction cycles (iterated greedy, [110]). The latter removes k solution components and rebuilds greedily — explicitly described as a special case of ILS perturbation.

**Don't-look bits (p. 785, ref [15,68]).** A speed-up technique: associate a bit with each solution component; skip components whose bit is 0 during local search; set bits to 1 when a component improves the solution; reset bits selectively after a perturbation affects nearby components. Particularly effective for TSP-class problems and directly applicable to any neighbourhood scan.

**Scheduling-specific ILS instantiation (PFSP example, pp. 789–791).** The canonical scheduling ILS by Stützle [116]:
- Initial solution: NEH heuristic (constructive, O(n²m) complexity via Taillard speed-ups [124]).
- Local search: insert neighbourhood (remove job at position i, try all n−1 insertion positions; first-improvement scan; repeat until no improvement). Incremental evaluation using NEH speed-ups.
- Perturbation: mix of contiguous swap moves + interchange moves, with restriction |i−j| ≤ max{n/5, 30} to avoid excessive disruption.
- Acceptance: Metropolis condition with fixed temperature.

**SMTWTP ILS (p. 797, refs [26,50,51]).** Iterated dynasearch by Congram et al. [26] and Grosso et al. [50,51] are state-of-the-art. Den Besten et al. [31] use ILS with VND local search for SMTWTP.

**Acceptance criterion variants (p. 786).** Beyond strict improvement and Metropolis: (a) short random walks with occasional backtracks to best-so-far [26]; (b) periodic restarts from a new initial solution [117,119] — shown to cure stagnation in long ILS runs.

**Relationship to other methods.** ILS is clearly distinguished from GRASP: GRASP creates many independent starting points via randomised greedy construction; ILS creates a biased walk in the space of local optima. Extensions of GRASP that reuse parts of elite solutions (path relinking) move GRASP toward ILS territory. VNS is characterised as a specific ILS instantiation where perturbation strength is varied in a fixed neighbourhood-ordering scheme.

## What transfers to paper #2

- **ILS as the outer search loop** — Paper #2 is NP-hard with a complex feasibility structure (Mode A/B/C access conditions, interruptibility flags, blocking DAG). A single local search will be trapped in local optima shaped by the position assignment. ILS provides a principled escape mechanism: perturb the current best solution (e.g., reassign 2–4 aircraft to different positions) and re-run local search from there. Cost: low if a local search already exists. Risk: low; ILS is problem-agnostic at the framework level.

- **Perturbation by destruction-reconstruction** — The iterated greedy perturbation (remove k aircraft from their position assignments, rebuild greedily by estimated delay + movement penalty) is a natural fit. The k aircraft to remove can be selected by highest contribution to the objective (worst-first removal), which is a biased perturbation that retains good structure. Cost: moderate — need the greedy rebuild sub-procedure, but this overlaps with a GRASP construction phase (see GRASP.md). Risk: low; worst-first removal is a standard, well-understood design.

- **Perturbation size calibration** — The chapter warns against perturbations that are too small (immediately undone by local search) or too large (random restart). For paper #2, a natural unit is the number of aircraft reassigned; the optimal k likely depends on instance size (number of aircraft R and positions P) and should be explored in [1, max(2, R/4)]. Adaptive perturbation strength (reactive search [10] or VNS-style escalation [52]) can be used if stagnation is detected. Cost: low (bookkeeping). Risk: requires empirical calibration on benchmark instances.

- **Acceptance criterion: strict improvement with periodic restart** — The chapter's recommendation (p. 786) for long runs is strict improvement combined with occasional restarts from a new initial solution [117,119]. For paper #2 this translates to: accept s*' only if it strictly improves on s*; after K consecutive non-improving iterations, restart from a GRASP-constructed solution. This avoids stagnation without the temperature-tuning burden of Metropolis. Cost: trivial. Risk: none; well-established.

- **Metropolis acceptance for diversification** — If the instance landscape has many near-equal local optima (likely given the discrete blocking-arc structure), a Metropolis criterion with a fixed low temperature T allows uphill moves proportional to quality degradation. Particularly useful when the objective weight profile (W^S=10, W^D=1.0, W^M=0.1) creates a heavily quantised landscape (movement counts are integers multiplied by 10). Cost: one temperature parameter to tune. Risk: medium — T is instance-size sensitive.

- **Don't-look bits for neighbourhood scan speed-up** — Paper #2 local search will need to evaluate move candidates (aircraft reassignments, job retiming). Don't-look bits associated with each aircraft suppress re-evaluation of aircraft whose neighbourhood has not been affected by the last accepted move. After a perturbation reassigns aircraft r, reset bits only for r and aircraft sharing a position or blocking arc with r. Cost: low (O(R) bit array). Risk: may miss improving moves involving aircraft affected indirectly; safe to reset more aggressively at cost of speed.

- **Insert neighbourhood for job sequencing** — The PFSP insert neighbourhood (remove one job from its slot, try all other positions) maps directly to the job scheduling sub-problem of paper #2: for a fixed position assignment, remove one job's start time and reschedule it at the earliest feasible time consistent with precedence, Mode A/B/C constraints, and inter-aircraft gaps. This is the scheduling analogue of an insert move. Cost: moderate — need a feasibility oracle per candidate position. Risk: medium — the Mode A/B/C feasibility check is non-trivial; an incremental evaluator is needed for efficiency.

- **VND as local search within ILS** — Den Besten et al. [31] show that replacing simple iterative improvement with VND inside ILS improves SMTWTP results. For paper #2, a VND over two neighbourhoods — (N1) single-aircraft position reassignment, (N2) pairwise aircraft position swap — provides stronger local optima before each perturbation step. This directly complements the GRASP+VND idea from GRASP.md. Cost: high (two neighbourhood evaluators). Risk: low once neighbourhoods are coded.

- **Contiguous-swap + bounded-interchange perturbation (PFSP pattern)** — The PFSP perturbation (contiguous swaps + interchange with |i−j| ≤ max{n/5, 30}) suggests a transfer: for paper #2, perturb by (a) swapping positions of two adjacent aircraft in the same blocking chain, and (b) swapping positions of two arbitrary aircraft with a distance bound on the blocking DAG (e.g., at most 2 hops apart). The bounding prevents excessive disruption while ensuring the perturbation is not immediately undone. Cost: low. Risk: the notion of "distance" on the blocking DAG needs to be formalised; straightforward for the triangular / linear hangar topologies in the benchmark instances.

## What does NOT transfer

- **TSP double-bridge move** — Specific to permutation tour structures. Paper #2 has no equivalent cyclic tour; the move is irrelevant.

- **QAP two-exchange neighbourhood** — QAP is a symmetric assignment (n items to n locations, all must be assigned). Paper #2 has R ≤ P (fewer aircraft than positions), earliest starts, time windows, and blocking-arc feasibility; the QAP neighbourhood and its incremental evaluation do not apply.

- **Continuous optimisation ILS variants (Liao–Stützle [76], Kramer [72])** — Paper #2 is discrete; continuous ILS is irrelevant.

- **Flow/job-shop sequence-specific perturbations** — The contiguous-swap perturbation for PFSP operates on a global job permutation across machines. Paper #2 has per-aircraft job chains (not a global permutation) and no machine-routing decision; the PFSP perturbation operator does not port directly.

- **SimILS (Grasas et al. [49])** — Extends ILS for stochastic combinatorial optimisation by embedding simulation inside the evaluation. Paper #2 is deterministic; SimILS overhead is not needed.

## Verdict for theory_assisted

**Priority:** High

**Rationale:** ILS is the natural complement to GRASP (see GRASP.md). GRASP provides diverse, high-quality starting solutions; ILS provides the outer loop that chains local optima together via structured perturbation. For paper #2, the two methods are complementary rather than competing: a GRASP construction phase generates the initial solution, a local search (possibly VND over position-assignment and job-scheduling neighbourhoods) reaches a local optimum, and the ILS perturbation (worst-k-aircraft destruction-reconstruction) restarts the process from a biased neighbourhood of the current local optimum. The scheduling applications section confirms that ILS is state-of-the-art on SMTWTP and flow-shop problems that share structural features (makespan + tardiness objective, job sequencing) with paper #2. The don't-look-bit speed-up and the insert neighbourhood for job scheduling are immediately actionable implementation details. The main design decision — perturbation size k and acceptance criterion — can be resolved empirically on the small benchmark instances already available.

## Cross-references

- [GRASP.md](GRASP.md) — GRASP chapter from same handbook. ILS and GRASP are complementary: GRASP constructs diverse starting solutions; ILS chains local optima. The GRASP+VND local search proposed there slots directly into the ILS LocalSearch component. The destruction-reconstruction perturbation described here overlaps with GRASP's greedy construction phase, enabling code reuse.
