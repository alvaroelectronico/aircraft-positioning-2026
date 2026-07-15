# Fischetti & Fischetti 2025 — Matheuristics by Examples

**Citation:** Fischetti M., Fischetti M. (2025) Matheuristics by Examples. In: Martí R. et al. (eds.) *Handbook of Heuristics*, Chapter 8, pp. 177–209. Springer Nature Switzerland AG. https://doi.org/10.1007/978-3-032-00385-0_14
**Source:** methods/theory_assisted/inspiration/Matheuristics_by_Examples.pdf
**Read on:** 2026-06-11

## Problem solved by this source

This is a tutorial/survey chapter (not a single-problem paper). It introduces the matheuristic paradigm — hybridisation of MIP solvers with metaheuristics — through three worked applications: (1) wind farm layout optimisation (binary assignment of turbines to sites, quadratic interference objective); (2) prepack optimisation (integer bin-packing / inventory allocation, MINLP linearised via binary expansion); (3) distance-constrained capacitated vehicle routing (DCVRP), addressed by the SERR (Selection, Extraction, Recombination, Reallocation) matheuristic.

None of these three applications directly matches paper #2. The chapter's value is in the general-purpose MIP-based heuristic patterns it documents, which are directly portable to any hard MILP: Local Branching, RINS, solution polishing, and proximity search.

## Technique

**General-purpose MIP-based heuristics (pp. 179–182).** All four operate on a generic MIP `min c^T x` subject to `Ax >= b`, `x_j in {0,1}` for j in B, and work via a "black-box" external MIP solver called on a modified or restricted model.

- **Local Branching (LB)** [Fischetti & Lodi 2003]: Given reference solution x-bar, add the *local branching constraint* `Δ(x, x-bar) := Σ_{j∈B: x-bar_j=0} x_j + Σ_{j∈B: x-bar_j=1} (1-x_j) <= k` (eq. 6) as an invalid cut. The resulting sub-MIP restricts search to a Hamming-k neighbourhood of x-bar. Typical k = 10–20. The solver is run with a node/time limit; the best solution found becomes the new reference and k is updated. LB improves LP relaxation grip by driving integrality of many components simultaneously.

- **RINS (Relaxation-Induced Neighborhood Search)** [Danna, Rothberg, Le Pape 2005]: At B&B nodes, compare LP relaxation solution x* with incumbent x-bar; fix all integer-constrained variables that agree in value; solve the reduced MIP. Exploits the convergence of LP relaxation toward the optimum inside B&B.

- **Solution Polishing** [Rothberg]: Evolutionary MIP heuristic. Maintains a population of feasible solutions. Combination step: fix variables whose value coincides in two parent solutions, solve the reduced MIP (RINS-style). Mutation: randomly fix some variables of a seed solution, solve reduced MIP. Selection: random parent + best-objective second parent.

- **Proximity Search** [ref 10]: "Dual" of LB. Instead of fixing the neighbourhood radius k, fix a minimum improvement cutoff: add `c^T x <= c^T x-bar - θ` (eq. 7) as a hard constraint, then minimise `Δ(x, x-bar)` (the Hamming distance to reference) rather than the original objective. Variant "proximity search with incumbent" softens (7) to `c^T x <= c^T x-bar - θ(1-ξ)` and minimises `Δ(x, x-bar) + Mξ` (eq. 8), allowing the solver to start from x-bar without being cut off.

**Application-specific patterns of note:**

- **Algorithm 1 (wind farm, p. 187):** Two-model progressive refinement: (a) simplified MIP without interference constraints is used aggressively to grow the turbine count, then (b) full MIP is applied. This staged relaxation/tightening is the key design pattern.

- **SERR matheuristic (DCVRP, pp. 200–208):** Iterative destroy-and-repair where "destroy" = extract a subset of nodes from routes (RANDOM-ALTERNATE, SCATTERED, or NEIGHBORHOOD selection schemes), and "repair" = solve a set-partitioning MIP (eqs. 46–52) over a pool of candidate sequences to reallocate extracted nodes optimally. The reallocation MIP has binary variable x_{si} = 1 if sequence s is assigned to insertion point i. LP dual pricing guides recombination of extracted node sequences. This is a principled large neighbourhood search (LNS) where the neighbourhood is explored exactly by a MIP sub-solver.

- **Partial variable fixing heuristic (prepack, pp. 194–196):** Alternately fix subsets of variables (x-variables or y-variables) to their current solution value, leaving the complementary set free; solve the resulting sub-MIP. The REOPT(S', y^H) function applies this to a subset S' of stores. Sub-problem sequence ordered by `most_dissimilar` (maximally different demand vectors first) or `most_similar` (similar demand vectors first) to manage difficulty.

## What transfers to paper #2

- **Local Branching as a refinement operator** — Paper #2 has a natural MILP formulation with binary position-assignment variables (aircraft r to position p) and integer/continuous start-time variables. Given any feasible solution x-bar produced by a constructive heuristic (e.g., from the GRASP digest), Local Branching adds eq. (6) restricted to the binary position-assignment variables, with k = 5–10 (small fleet sizes). The MIP solver then searches for a better assignment within Hamming distance k while re-optimising all start times freely. Cost: low — requires only the MILP model plus one extra linear constraint. Risk: low; LB is robust and the LB constraint is trivial to implement.

- **Proximity Search as a polishing step** — After any feasible solution is found (constructive or LB iteration), proximity search replaces the objective with the Hamming-distance-to-incumbent minimisation `Δ(x, x-bar)` and adds the cutoff `c^T x <= c^T x-bar - θ`. For paper #2, the objective involves makespan, delay, and movement count — all of which are non-trivial to improve simultaneously. Proximity search forces the solver to find a solution that is both better by at least θ and close to the current one, which is a strong driver for intensification. The "with-incumbent" soft variant (eq. 8) is preferable to avoid cutting off x-bar. Cost: low (two constraint modifications + objective swap). Risk: low; θ must be tuned — start with θ = 1 movement or 1 unit of delay.

- **Two-model staged refinement (Algorithm 1 pattern)** — Paper #2's access-mode constraints (Modes A/B/C) and their movement-count penalties are the "hard" part of the model. A staged approach: (i) solve a simplified sub-MIP that ignores Mode-B/C constraints and the movement objective term W^S·n, to get an initial feasible position assignment and job schedule; (ii) then activate the full model and apply LB or proximity search to refine. This mirrors Algorithm 1's two-model strategy and is likely to produce good incumbents quickly. Cost: moderate (need two versions of the MILP: one without movement constraints). Risk: medium — the simplified model may produce assignments where Mode-A access is impossible, requiring position-assignment changes in phase (ii).

- **SERR-style destroy-and-repair for job scheduling sub-problem** — For a fixed position assignment, paper #2's scheduling sub-problem (determining job start times, access modes, and κ_j counts) can be treated as a destroy-and-repair LNS. "Destroy" = unfix start times of a subset of aircraft (e.g., those at blocked rear positions); "repair" = re-solve the scheduling sub-MIP for those aircraft with the remaining aircraft fixed. The repair sub-MIP is a set of interval-scheduling constraints and is significantly smaller than the full problem. This maps directly to the SERR pattern (extract a subset of "nodes," reallocate via MIP). Cost: high (requires a decomposed scheduling sub-MIP and a selection scheme). Risk: medium — the interaction between position assignment and access modes means fixing position assignments while unfixing start times may not capture all improvement directions.

- **Alternating variable-fixing (prepack pattern) for joint assignment+scheduling** — Alternate between: (a) fix all position assignments π(r), solve the scheduling sub-MIP for all job start times and access modes freely; (b) fix all job start times, solve the assignment sub-MIP for positions freely. This is the direct analogue of the prepack heuristic's alternating x/y fixing (pp. 194–196). Cost: moderate (requires two clean sub-MIP formulations). Risk: medium — the coupling between assignment and scheduling in paper #2 is tight (access modes depend on both), so alternating fixing may cycle or stall. Mitigate by perturbing position assignments between cycles.

- **RINS as a solver-internal hint** — If a commercial solver (Gurobi, CPLEX) is used for the full MILP, enabling RINS-style heuristics internally (already available in both solvers as tuning options) is essentially free and can improve incumbent quality during B&B. No custom implementation needed. Cost: zero (parameter flag). Risk: none.

- **Primal integral metric (eq. 43–45)** — The chapter introduces the primal gap function p(t) and primal integral P(t_max) as a metric for anytime heuristic quality. For paper #2 benchmarking, reporting P(t_max) alongside final solution quality gives a more informative comparison across methods. Cost: trivial (post-processing of solution logs). Risk: none.

## What does NOT transfer

- **Wind farm layout model (eqs. 9–24)** — Quadratic interference objective between co-located binary site variables has no analogue in paper #2. The linearisation trick (Glover's recipe, eqs. 17–24) is specific to pairwise quadratic terms and not needed.

- **Prepack MINLP model (eqs. 25–45)** — Bilinear product of integer variables (x_bs * y_bi) with binary expansion linearisation is problem-specific. Paper #2 has no such product structure.

- **SERR reallocation MIP (eqs. 46–52)** — The set-partitioning model for DCVRP node reallocation is route-sequence-specific. Paper #2 has no equivalent route-sequence structure; the analogue would be an assignment sub-MIP, which is simpler and does not need the full SERR apparatus.

- **ASSIGN/SD neighbourhood for TSP (pp. 200–202)** — Extraction of even-position nodes from a Hamiltonian tour and min-sum reallocation is TSP/VRP-specific. Paper #2 has no tour structure.

- **Store sequencing strategies (most_dissimilar / most_similar, pp. 195–196)** — Ordering sub-problems by demand-vector dissimilarity is specific to the bin-packing context. Not applicable.

## Verdict for theory_assisted

**Priority:** High

**Rationale:** The four general-purpose MIP-based heuristics (Local Branching, RINS, polishing, proximity search) are directly applicable to paper #2's MILP as drop-in refinement operators that require only the existing model plus minor constraint modifications. Local Branching over the position-assignment binary variables provides a principled large-neighbourhood search with controllable radius k, and is the single most actionable idea: add eq. (6) to any feasible solution from the GRASP constructive phase (see [[GRASP]] digest) and let the solver re-optimise. Proximity search (eq. 8, soft variant) is the best polishing step once a good incumbent exists. The staged two-model approach (simplified model first, full model second) is also immediately actionable and likely to accelerate time-to-first-good-incumbent. The application examples are not directly reusable but serve as concrete design illustrations.

## Cross-references

- [[GRASP]] (`methods/theory_assisted/digest/GRASP.md`): Local Branching is the natural refinement phase after GRASP construction. The GRASP digest identifies reactive α and elite-pool construction; this digest provides the MIP-based local search to complement it. Together they form a complete matheuristic: GRASP construction → Local Branching / proximity search refinement.
