# Maia, Rosseti, Martins, Plastino 2025 — Data Mining in Heuristics

**Citation:** Maia M.R.H., Rosseti I., de Lima Martins S., Plastino A. (2025) Data Mining in Heuristics. In: Martí R. et al. (eds.) *Handbook of Heuristics*. Springer Nature Switzerland AG. https://doi.org/10.1007/978-3-032-00385-0_11
**Source:** methods/theory_assisted/inspiration/Data_Mining_in_Heuristics.pdf
**Read on:** 2026-06-11

## Problem solved by this source

This is a survey/handbook chapter, not a paper targeting one specific problem. It describes a family of techniques — DM-MSH, MDM-MSH, and MineReduce (MR-MSH) — for embedding frequent-itemset data mining inside multistart stochastic local search (SLS) metaheuristics. The chapter then validates these techniques on three application problems: the Capacitated VRP (CVRP), the Heterogeneous Fleet VRP (HFVRP), and the Multisource Capacitated Facility Location Problem with Customer Incompatibilities (MS-CFLP-CI). None of these share the structure of paper #2 directly, but the meta-framework is problem-agnostic.

The core assumption shared with paper #2 is that the problem is NP-hard, solutions decompose into identifiable "elements" (arcs, assignments, job-slot pairings), and good solutions tend to share substructures that can be mined and exploited.

## Technique

**DM-MSH (Fig. 1).** Two-phase framework. Phase 1 (*Elite Set Generation*): run `gen_elite_iter` standard MSH iterations; after each, update elite set D with the d best solutions found. After Phase 1, apply frequent-itemset mining (MINE) to D to extract pattern set P (patterns = sets of solution elements appearing in at least s% of elite solutions). Phase 2 (*Hybrid Phase*): for each remaining iteration, select a pattern p from P, run DM_CONSTRUCT_SOL (seeding the construction with p's elements) and DM_LOCAL_SEARCH (restricting the neighbourhood to solutions containing p's elements). Best solution returned.

**MDM-MSH (Fig. 2).** Eliminates the hard phase boundary. The elite set is mined whenever it becomes *stable* (no change for >= δR_MAX consecutive restarts) and re-mined every time it becomes stable again after changing. This adaptive mining schedule is triggered multiple times during a single run, allowing patterns to evolve as better solutions are found. MDM-MSH generally outperforms DM-MSH.

**MineReduce / MR-MSH (Fig. 3).** Adds a *problem-decomposition* layer on top of MDM-MSH. When a pattern p is selected, the original instance π is *reduced* to a smaller instance π' by fixing (removing) the variables corresponding to p's elements, solving π' with the standard SLS, and then *expanding* the result back to a full solution for π (reinserting p's elements). A second local search is then applied to the full solution. This reduce-optimize-expand cycle shrinks the search space for each SLS call, producing faster convergence and better final solutions. MR-MSH won the MESS 2020+1 Metaheuristics Competition (facility location) and ranked 2nd in the 12th DIMACS CVRP Challenge.

**Frequent-itemset mining details (not stated exactly).** Patterns are maximal frequent itemsets extracted with minimum support s% from the elite set. For routing problems, items are (arc, vehicle-type) pairs; for assignment problems, items are (customer, facility, quantity) triples. The exact mining algorithm is not specified (standard Apriori-family assumed).

**Empirical results.** MR-MSH beats plain MS-ILS by ~2.4% APD globally on CFLP-CI and wins on 83%/76% of HFVRP instances vs. MS-ILS/MDM-MS-ILS respectively. Convergence speed (TTT plot, Fig. 9) shows MR-MS-ILS reaches target in 200 s with 97% probability vs. 76% for MDM and 67% for plain ILS.

## What transfers to paper #2

- **Elite-set frequent-pattern mining as a guidance layer (DM-MSH/MDM-MSH)** — Paper #2 is a multistart problem (any GRASP or ILS outer loop can serve as the MSH). After accumulating an elite set of solutions, frequent itemsets can be mined over (aircraft, position) assignment pairs. Patterns with high support (e.g., aircraft r always assigned to position p in top-k solutions) represent structurally stable assignments that the blocking-arc topology rewards. These can seed future constructions and restrict local-search neighbourhoods. Cost: moderate — requires an itemset mining library (e.g., Python `mlxtend`) and encoding solution elements as transactions. Risk: low at the DM-MSH level; works on any set-representable solution.

- **MDM-MSH adaptive re-mining schedule** — Paper #2 instances may vary widely in difficulty and the elite set may improve non-monotonically (especially as the blocking-arc structure creates many local optima). Adaptive re-mining (triggered by elite-set stability rather than a fixed iteration count) is preferable to DM-MSH's hard phase split. Cost: low incremental over DM-MSH (add a stability counter). Risk: low.

- **MineReduce decomposition for the position-assignment subproblem** — When a pattern p = {(r1, p1), (r2, p2), …} is mined, these aircraft-position assignments can be fixed, reducing the instance to a smaller scheduling problem with fewer aircraft competing for fewer positions. The reduced instance is easier to solve (fewer blocking interactions, smaller MILP or local-search space). After solving the reduced instance, the fixed assignments are reinserted to reconstruct a full solution, which is then locally searched. This directly exploits the structure of paper #2: fixing high-confidence position assignments collapses the most expensive part of the search (mode-A/B/C feasibility checking across all aircraft pairs). Cost: medium — requires implementing the reduce/expand operators on the instance JSON; the instance schema supports position assignment so the representation is natural. Risk: medium — if the mined patterns are wrong (over-fitted to a local optimum of the elite set), fixing them can cut off good regions; mitigated by using only high-support patterns and by running a full local search on the expanded solution.

- **Solution representation as transactions of (aircraft, position) pairs** — Each solution in the elite set is encoded as a set of (aircraft_id, position_id) pairs. Frequent itemsets over these transactions directly identify which co-assignments are structurally beneficial. This is a natural encoding for paper #2 (one pair per aircraft, |R| items per transaction). Cost: trivial — the solution dict already contains position assignments. Risk: none for the representation itself.

- **Restricting local-search neighbourhoods to pattern-consistent moves** — In DM_LOCAL_SEARCH, only moves that keep p's elements in the solution are evaluated. For paper #2 this means: during local search, do not reassign aircraft that appear in the current pattern. This dramatically reduces the neighbourhood size and can speed up each local-search iteration. Cost: low (add a "frozen aircraft" set to the move generator). Risk: medium — may cause the local search to miss improving moves that require reassigning a "frozen" aircraft; use with soft-pattern enforcement or time-limited freezing.

- **Pattern-seeded construction (DM_CONSTRUCT_SOL)** — Initialise the construction heuristic by pre-assigning pattern elements and then greedily completing the remaining aircraft. For paper #2, pre-assigning the pattern's aircraft-position pairs and scheduling them first (in order of earliest start E_r) leaves a smaller residual problem for the greedy step. Cost: low (modify the GRASP construction to accept a pre-assignment dict). Risk: low.

## What does NOT transfer

- **Route-segment patterns (arc sequences) from VRP** — The CVRP/HFVRP representation mines (arc, vehicle-type) pairs forming route segments. Paper #2 has no routing structure; aircraft do not visit sequences of locations. The specific representation and the CW-savings-based randomised construction (DM_RCW) are entirely irrelevant.

- **Customer-cluster vertex merging (MineReduce for HFVRP)** — The reduce step for HFVRP merges customer vertices into cluster super-nodes based on route-segment patterns. This graph-contraction idea has no analogue in paper #2's position-assignment structure.

- **Facility-location quantity triples** — The (i, j, q) encoding used for MS-CFLP-CI (customer, facility, quantity) does not map to paper #2, which has no continuous flow variables.

- **Population-level restarts (HGS framework)** — MDM-HGS restarts the population when no improvement occurs for many consecutive iterations. Paper #2 is not population-based (unless a GA is adopted as the outer loop), so the HGS-specific stability criterion is inapplicable.

- **Competition-specific time limits** — The 10√J and J second time-out protocols from the DIMACS/MESS competitions are not relevant to paper #2's benchmark setup.

## Verdict for theory_assisted

**Priority:** Medium

**Rationale:** The DM-MSH/MDM-MSH/MineReduce framework is a well-validated, problem-agnostic layer that can be bolted onto any multistart metaheuristic already planned for paper #2 (e.g., the GRASP described in the GRASP digest). The most immediately valuable idea is MineReduce applied to the aircraft-position assignment subproblem: fixing high-confidence (aircraft, position) pairs from the mined elite set produces a reduced instance with fewer blocking interactions, which is cheaper to optimise and naturally exploits paper #2's blocking-arc topology. The transfer is conceptually clean and the implementation cost is moderate. However, the technique requires a working multistart outer loop and an elite set of reasonable quality before it adds value, so it is a second-layer enhancement rather than a foundation. Priority is Medium rather than High because the application problems in the chapter (VRP, facility location) are structurally remote from paper #2, meaning the specific operators described are not directly reusable — only the meta-framework transfers.

## Cross-references

- [[GRASP]] — The GRASP chapter describes the multistart outer loop (GRASP iterations) that would serve as the MSH component in DM-MSH/MDM-MSH. The elite-pool intensification mechanism described in the GRASP digest (Fleurent–Glover K(i) scoring) is a lightweight alternative to full frequent-itemset mining and should be compared before investing in the mining infrastructure. MineReduce is the stronger technique when instance sizes are large enough that reducing the sub-instance yields meaningful speedup.
