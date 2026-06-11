# Ferone, Festa, Resende 2025 — GRASP (Handbook of Heuristics chapter)

**Citation:** Ferone D., Festa P., Resende M.G.C. (2025) GRASP. In: Martí R. et al. (eds.) *Handbook of Heuristics*. Springer Nature Switzerland AG. https://doi.org/10.1007/978-3-032-00385-0_23
**Source:** methods/theory_assisted/inspiration/GRASP.pdf
**Read on:** 2026-06-11

## Problem solved by this source

This is a reference chapter (not a research paper solving a specific problem). It provides a comprehensive, self-contained exposition of the GRASP (Greedy Randomized Adaptive Search Procedures) metaheuristic family, covering: basic two-phase structure (construction + local search), the Restricted Candidate List (RCL) mechanism in both cardinality-based (CB) and value-based (VB) forms, and a full taxonomy of enhancements. The chapter does not target any single application problem; instead it gives the algorithmic building blocks applicable to arbitrary combinatorial minimisation problems.

Tables 1 and 2 explicitly list GRASP applications including timetabling and scheduling (references [4, 7, 11, 12, 25, 29, 54, 56, 64, 81, 96, 105, 139, 142–144]) and assignment problems ([5, 51, 71, 102, 112, 122, 123, 135, 145]), both relevant to the aircraft positioning / job-scheduling structure of paper #2.

## Technique

**Basic GRASP (Fig. 1–4).** Each iteration: (1) `ConstructGreedyRandomizedSolution` — build a complete solution by repeatedly evaluating the incremental greedy cost `g(i)` of all candidate elements, forming the RCL (either the top-k elements by CB rule, or all elements within `g_min + α(g_max − g_min)` by VB rule), then randomly selecting one from the RCL; (2) `LocalSearch` — standard improving-move local search to a local optimum; (3) keep the best solution across all iterations.

**Reactive GRASP.** Instead of a fixed α, maintain a discrete set A = {α₁, …, αₘ} and a probability pᵢ for each αᵢ. After each iteration the probabilities are updated as `pᵢ = qᵢ / Σqⱼ` where `qᵢ = ẑ/Aᵢ` (incumbent divided by average objective achieved under αᵢ). This is a self-tuning mechanism that eliminates manual α calibration.

**Bias functions (Bresina/BR-GRASP).** Rather than uniform selection within the RCL, assign rank `r(x)` to each RCL element and select with probability proportional to `bias(r(x))`. Five bias families: random (uniform), linear `1/r`, log `log⁻¹(r+1)`, exponential `e⁻ʳ`, polynomial `r⁻ⁿ`. BR-GRASP (biased-random GRASP, ref [61]) extends this to all candidate elements, not just those in the RCL, using a geometric-distribution skew.

**Intensification via elite pool + bias (Fleurent–Glover).** Build an elite solution pool; assign an intensity score `I(i)` measuring how often element `i` appears in elite solutions; bias RCL selection by `K(i) = F(g(i), I(i))` (eq. 5), with `K(i) = λg(i) + I(i)`, λ decreasing over time.

**Hybridisations covered:** GRASP+Tabu, GRASP+GA (initial population seeding), GRASP+VNS/VND (local search phase replaced by multi-neighbourhood descent), GRASP+Path Relinking (Fig. 5: greedy path between current solution x and elite guiding solution y by applying the best move from the symmetric difference Δ(x,y) at each step, followed by local search on the best intermediate solution).

**Path Relinking variants:** greedy PR, random PR, mixed PR, interior PR (add attributes present in guiding set), exterior PR (add attributes absent from both), multiple-parent PR.

## What transfers to paper #2

- **Two-phase GRASP as outer loop** — Paper #2 requires joint position-assignment and job-scheduling decisions, both combinatorial. A GRASP outer loop provides diverse starting solutions for a local search phase without requiring an explicit MILP solve. Cost: moderate (need greedy function design — see next point). Risk: low; GRASP is problem-agnostic at the framework level.

- **Greedy function design for position assignment** — The RCL construction needs a `g(i)` for each candidate (aircraft, position) pair. A natural choice: estimated delay `max(0, E_r + T_r − L_r)` plus a penalty for blocking-arc conflicts (number of aircraft at rear positions whose access instants would fall into Mode-C with non-interruptible jobs). This directly maps to the `W^D` and `W^S` terms in the objective. Cost: low; the greedy estimate is computable from instance data without solving a sub-problem. Risk: the greedy estimate ignores timing interactions across aircraft — may produce poor RCL rankings. Mitigated by randomisation.

- **Value-based RCL with α ∈ [0,1]** — The VB-RCL threshold `g_min + α(g_max − g_min)` allows continuous control between pure greedy (α=0) and pure random (α=1). For paper #2 this is preferable to CB-RCL because the cost landscape of (aircraft, position) assignments is continuous (delay values, movement counts), not rank-based. Cost: trivial to implement. Risk: none; standard mechanism.

- **Reactive GRASP for α self-tuning** — Paper #2 has no obvious a-priori α. Reactive GRASP (equations 2–3) tracks average objective per α value and shifts probability mass toward the best-performing α. This removes the need for α calibration across instance sizes/topologies. Cost: low (10–20 lines of bookkeeping). Risk: requires warm-up iterations before probabilities stabilise; for small instance budgets this may not help.

- **Biased-random GRASP (BR-GRASP, geometric skew)** — For the scheduling sub-problem (ordering jobs within an assigned position), a geometric-distribution bias over the sorted candidate list biases toward earlier, less-delayed start times while retaining diversity. Preferable to uniform-RCL selection when the greedy ranking is informative but not definitive. Cost: one parameter (skew probability p). Risk: low.

- **Elite pool + intensification (Fleurent–Glover K(i))** — After accumulating several GRASP iterations, record an elite set of position assignments. Bias future constructions toward position-assignment elements that appear frequently in elite solutions (high I(i)), combined with greedy cost g(i) via K(i) = λg(i) + I(i). This is especially valuable for paper #2 because the blocking-arc structure means some position assignments are structurally better regardless of timing details. Cost: moderate (maintain elite pool, compute I(i) per element). Risk: medium — I(i) only makes sense once enough elite solutions have been found; may not help for very small instances.

- **GRASP + Path Relinking as post-processing** — Apply PR between the current GRASP solution and a randomly chosen elite solution, following the greedy path through Δ(x,y) (differences in aircraft-to-position assignments). The best intermediate solution is locally searched. This is a natural intensification step after the main GRASP loop. Cost: moderate (need a move operator on position assignments). Risk: medium — the symmetric difference must be well-defined; for paper #2 it is simply the set of aircraft whose position assignments differ, making the implementation straightforward.

- **GRASP+VND as local search phase** — Replace the single-neighbourhood local search with a Variable Neighbourhood Descent over multiple neighbourhoods (e.g., single aircraft reassignment, swap of two aircraft positions, rescheduling a single aircraft's jobs). This directly improves local optima quality. Cost: high (need multiple neighbourhood definitions and move evaluators). Risk: low once neighbourhoods are defined.

## What does NOT transfer

- **Continuous GRASP (C-GRASP)** — Designed for box-constrained continuous optimisation (coordinate line-search construction). Paper #2 is a discrete combinatorial problem; C-GRASP is irrelevant.

- **Random-key GRASP (RK-GRASP)** — Encodes solutions as real-valued random-key vectors decoded by a problem-specific decoder. While it could in principle be applied, the paper #2 solution structure (discrete position assignments + integer job start times with complex feasibility constraints) does not lend itself to a natural random-key encoding without significant design effort, and the gain over standard GRASP is unclear.

- **Cost perturbations (Charon–Hudry noising)** — Useful when no informative greedy function exists. For paper #2 there is a natural greedy (delay + movement estimate), so cost perturbations add complexity without clear benefit.

- **Application-specific GRASP results from the tables** — The references cited (job-shop scheduling [4], assembly-line balancing [12], etc.) are listed but not described in detail. This chapter does not provide a scheduling-specific neighbourhood or greedy function that can be directly reused.

## Verdict for theory_assisted

**Priority:** High

**Rationale:** This chapter is the definitive reference for implementing GRASP. Paper #2 is an NP-hard assignment+scheduling problem with a natural greedy function (delay + movement penalties), making it a textbook GRASP candidate. The chapter provides the complete algorithmic toolkit needed: VB-RCL construction, reactive α self-tuning, bias functions for construction diversity, elite-pool intensification, and path relinking as post-processing. All of these can be layered incrementally onto a basic GRASP skeleton. The most immediately actionable component is the reactive GRASP mechanism (equations 2–3), which eliminates the most common GRASP failure mode (poor α calibration) at negligible implementation cost.

## Cross-references

No other digests yet in this folder. Cross-reference with any future digest on ALNS or VNS, as the hybridisation section (GRASP+VNS/VND) points directly at those methods as complementary local-search intensifiers.
