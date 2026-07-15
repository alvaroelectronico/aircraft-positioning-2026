# Duarte, Mladenovic, Sanchez-Oro, Todosijevic 2025 — Variable Neighborhood Descent

**Citation:** Duarte A., Mladenovic N., Sanchez-Oro J., Todosijevic R. (2025) Variable Neighborhood Descent. In: Marti R. et al. (eds.) *Handbook of Heuristics*. Springer Nature Switzerland AG. https://doi.org/10.1007/978-3-032-00385-0_9
**Source:** methods/theory_assisted/inspiration/Variable_Neighborhood_Descent.pdf
**Read on:** 2026-06-11

## Problem solved by this source

This is a reference handbook chapter, not a paper solving a single problem. It provides a self-contained, definitive treatment of Variable Neighborhood Descent (VND) — the deterministic, local-search-only variant of Variable Neighborhood Search (VNS). The chapter covers: (1) a taxonomy of neighborhood structures for continuous, binary, integer, and permutation problems; (2) best-improvement vs. first-improvement local search; (3) three VND variants — Sequential VND (SeqVND, Algorithm 2), Nested VND (NestedVND, Algorithm 3), and Mixed VND (MixedVND, Algorithm 6); (4) static vs. dynamic neighborhood ordering (Basic, Pipe, Cyclic, Union, Random, Adaptive VND); and (5) empirical comparison on TSP and the Allocation Problem (AP).

The chapter does not model a scheduling or assignment problem matching paper #2 directly. Its contribution is the algorithmic framework itself, applicable to any combinatorial problem with well-defined neighborhood structures.

## Technique

**Sequential VND (SeqVND, Algorithm 2).** Given an ordered list of k_max neighborhoods {N_1, ..., N_{k_max}} and a starting solution x, the outer loop runs until no improvement is found across all neighborhoods. Inside, for k = 1 to k_max: apply local search in N_k(x) to get x'; if f(x') < f(x''), accept and reset k via a NeighborhoodChange function. The key design choice is the NeighborhoodChange policy:
- **Basic VND (B-VND)**: on improvement, reset k = 1 (restart from the smallest/cheapest neighborhood). Empirically best average quality at negligible CPU time (Table 1: avg. 1198.24 on TSP, 0.16 s).
- **Pipe VND (P-VND)**: on improvement, stay in the same neighborhood k. Fastest per unit quality (0.12 s).
- **Cyclic VND (C-VND)**: on improvement, advance to k+1 (mod k_max). Slowest of the sequential variants (0.46 s).
- **Union VND (U-VND)**: treat the union of all neighborhoods as a single large neighborhood; slightly best quality (1197.65) but much slower (1.06 s).

**Nested VND (NestedVND, Algorithm 3).** The composite neighborhood is N_nested = N_1 o N_2 o ... o N_{k_max}, meaning N_1 is applied to all solutions in N_2(x), which is applied to all solutions in N_3(x), etc. Cardinality is at most the product of individual neighborhood sizes. Because the composite neighborhood is large, first-improvement is recommended. The practical illustration (Algorithms 4-5) uses a two-level scheme: outer neighborhood N_H (swap a hub) combined with inner greedy allocation (Algorithm 4: GreedyAllocation) followed by inner neighborhood N_A (reallocate a node). This is a matheuristic pattern: the outer VND move generates a coarse candidate; the inner greedy/local-search phase polishes it efficiently.

**Mixed VND (MixedVND, Algorithm 6).** Parameterised by b (the nesting depth). The first b neighborhoods are composed (nested), and for each element of that composite neighborhood a Sequential VND is run over the remaining k_max - b neighborhoods. Setting b = 0 gives pure SeqVND; b = k_max gives pure NestedVND. The boost parameter b trades intensification depth against runtime. Empirically (Table 3, AP instance n=100, p=15): Mix-VND2 achieves 0.00% max deviation and 0.16 s; Seq-VND achieves 0.00% min deviation at 0.06 s. Mix-VND variants essentially eliminate local minima (Fig. 13 shows only 4 local minima vs. hundreds for single-neighborhood search).

**Dynamic ordering variants.** Random VND picks the next neighborhood at random (regardless of improvement). Adaptive VND tracks a merit score per neighborhood (reflecting recent improvement success) and reorders dynamically; the merit can be maintained by adaptive mechanisms or ML.

**Neighborhood taxonomy.** The chapter formalises neighborhoods for binary (drop/add/swap on binary vectors, eq. 6), integer (swap and replace moves, eqs. 9-10), and permutation problems (exchange and insert moves, eqs. 12; illustrated on TSP with 2-opt, Insertion-1, Insertion-2). This taxonomy is directly applicable to the mixed discrete structure of paper #2.

## What transfers to paper #2

- **SeqVND with B-VND reset as the local-search engine** — Paper #2 needs a local search that simultaneously handles position assignment (discrete, finite) and job scheduling (integer start times). SeqVND with B-VND reset is the natural choice: define small cheap neighborhoods first (e.g., single-aircraft job retiming) and expensive ones last (position swap). On improvement, always restart from N_1. The theoretical guarantee is that the output is locally optimal with respect to ALL defined neighborhoods simultaneously — which is precisely what is needed to avoid partial local optima. Cost: moderate (requires k_max neighbourhood definitions and move evaluators). Risk: low; the framework is problem-agnostic.

- **Three concrete neighborhood definitions for paper #2** — The chapter's permutation/integer taxonomy suggests the following direct mappings:
  - N_1: **Retime** — fix all position assignments, shift the start time of one aircraft's entire job chain by delta (integer move, similar to replace/swap on integer variables). Very cheap to evaluate; affects delay and potentially movement count.
  - N_2: **Reassign** — move one aircraft to a different position (binary/integer assignment change). Requires re-checking all blocking-arc access conditions (Mode A/B/C). Medium cost.
  - N_3: **Swap** — exchange positions of two aircraft. Larger neighbourhood (size |R|*(|R|-1)/2); more expensive but can escape symmetrical local optima in the blocking structure.
  Ordering N_1 before N_2 before N_3 matches the B-VND prescription of cheapest-first. Cost: low to moderate per neighbourhood; the three together cover the main degrees of freedom in paper #2. Risk: the Mode A/B/C feasibility check after each Reassign/Swap move is non-trivial; must be implemented carefully.

- **Nested VND pattern (outer coarse / inner fine)** — The hub-allocation illustration (Algorithms 4-5) directly mirrors a natural decomposition for paper #2: outer move = position reassignment (N_H analogue), inner optimisation = job retiming given fixed positions (N_A analogue, solvable greedily by earliest-start scheduling within each position). This decoupling converts the joint problem into a sequence of cheaper sub-problems. Cost: moderate (need a fast retiming subroutine for fixed assignments). Risk: medium — the inner problem is not trivially solved because of the Mode B gap constraint (mu) and Mode C interruption penalty (delta), but a greedy earliest-start sweep is a reasonable approximation.

- **Mixed VND (b=1) as intensification layer** — After the basic SeqVND converges, applying MixedVND with b=1 (compose N_1 and N_2, then run SeqVND over N_3 for each composite-neighbourhood element) dramatically reduces local minima (empirically, from hundreds to single digits in the AP experiment, Table 3). For paper #2 this translates to: for each (aircraft, new_position) candidate (N_2 move), immediately retime all affected aircraft (N_1), and then check if a position swap (N_3) improves further. Cost: high (runtime grows as |N_2| * cost(SeqVND)); suitable only as a post-processing intensifier on promising solutions. Risk: medium — runtime may be prohibitive for large instances; use a time budget cutoff.

- **Adaptive VND for neighbourhood ordering** — Because the relative productivity of retiming vs. reassignment vs. swapping will vary across instances (different blocking-arc topologies, different delay profiles), Adaptive VND's merit-tracking mechanism (merit = frequency/magnitude of recent improvements per neighbourhood) avoids the need to hard-code the ordering. Cost: low (a few lines of bookkeeping). Risk: low; degrades gracefully to fixed ordering if merits do not differentiate.

- **First-improvement for large neighbourhoods** — The chapter explicitly recommends first-improvement for large nested/composite neighbourhoods (section "Nested VND"). For paper #2, the swap neighbourhood N_3 has O(|R|^2) candidates; scanning all of them for best improvement is wasteful. First-improvement with random neighbour ordering (as recommended in the Local Search Methods section) provides diversity and speed. Cost: trivial. Risk: solution quality slightly lower than best-improvement, but mitigated by B-VND restart.

- **GRASP + VND hybridisation** — The GRASP digest already identified GRASP+VND as a key hybridisation (from the GRASP chapter). This VND chapter provides the concrete local-search engine that fills the "LocalSearch" slot in GRASP's two-phase loop. The SeqVND(x, k_max, N) call (Algorithm 2) is a drop-in replacement for a single-neighbourhood local search. Cost: negligible additional cost once both GRASP and VND components are implemented. Risk: low.

## What does NOT transfer

- **Continuous neighborhood structures (section "Neighborhoods for Continuous Optimization Problems", eqs. 1-4)** — Paper #2 is fully discrete (integer position indices, integer or rational job start times). The l_p-metric-based ball neighborhoods are irrelevant.

- **Binary neighborhood structures (drop/add/swap on {0,1} vectors)** — Paper #2's position assignment is a categorical variable, not a binary vector. The Hamming-metric formalism does not apply directly; the swap and reassign moves must be defined at the categorical level.

- **TSP-specific neighborhoods (2-opt, Insertion-1, Insertion-2, Figs. 8-10)** — The empirical comparison on TSP is illustrative only. 2-opt requires a tour structure; paper #2 has no tour. These neighborhoods cannot be reused.

- **Uncapacitated p-Hub Median Problem neighborhoods (N_H, N_A)** — The nested VND illustration problem (r-p-HMP, section "Nested VND") involves flow costs and hub location decisions. The specific neighborhoods (swap a hub, reallocate a node to nearest hub) do not transfer to paper #2's blocking-arc geometry.

- **Union VND (U-VND)** — Treating all neighborhoods as a single union is theoretically appealing but 6x slower than B-VND for equivalent quality (Table 1). For paper #2, where feasibility evaluation already requires checking Mode A/B/C conditions, U-VND's runtime cost would be prohibitive.

## Verdict for theory_assisted

**Priority:** High

**Rationale:** VND is the natural local-search backbone for the theory_assisted method. Paper #2's solution space has two separable but interacting components — position assignment (discrete, small cardinality) and job scheduling (integer start times, large cardinality) — which map cleanly onto a two- or three-neighbourhood SeqVND with B-VND reset. The chapter's empirical result that B-VND gives the best quality/time ratio among sequential variants, combined with the Nested VND pattern for decomposing assignment from timing, gives a concrete and low-risk implementation blueprint. The Mixed VND result (essentially zero local minima in the AP experiment) motivates using MixedVND as an optional intensifier when time budget permits. Critically, this chapter is the direct complement to the GRASP digest: GRASP provides diverse starting solutions; VND (specifically SeqVND) provides the local-search engine that converts each starting solution into a high-quality local optimum. Together they form a complete GRASP+VND heuristic architecture.

## Cross-references

- [GRASP.md](GRASP.md) — The GRASP chapter explicitly lists GRASP+VND as a key hybridisation (section "GRASP + VND as local search phase"). This VND chapter provides the concrete Algorithm 2 (SeqVND) that fills that role. The two digests should be read together when designing the outer metaheuristic loop.
