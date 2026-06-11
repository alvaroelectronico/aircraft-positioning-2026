# Ruiz 2025 — Scheduling Heuristics

**Citation:** Ruiz R. (2025) Scheduling Heuristics. In: Martí R. et al. (eds.) *Handbook of Heuristics*. Springer Nature Switzerland AG. Chapter 52. https://doi.org/10.1007/978-3-032-00385-0_44
**Source:** methods/theory_assisted/inspiration/Scheduling_Heuristics.pdf
**Read on:** 2026-06-11

## Problem solved by this source

This is a reference chapter (not a research paper solving a specific problem). It surveys the scheduling field end-to-end: standard notation (α/β/γ), common constraint families (precedence chains, release dates, due dates, non-wait, interruptibility, setup times), and objective functions (C_max, Σ C_j, Σ T_j, Σ w_j T_j). The concrete algorithmic material focuses on two canonical problems: the permutation flow shop with makespan criterion (F/prmu/C_max) for NEH, and the job shop with makespan criterion (J//C_max) for the Shifting Bottleneck Heuristic (SBH). Dispatching rules are illustrated on the parallel machine problem P//C_max.

The chapter's constraint taxonomy (§"Scheduling Constraints") explicitly lists chains of job/task precedences (β = chains), release dates (β = r_j), interruptible tasks (tasks that may be paused mid-execution), and no-wait constraints — all of which appear in paper #2.

## Technique

**Dispatching rules (constructive, O(n log n)).** Three canonical rules are described: SPT (shortest processing time first — optimal for 1||ΣC), LPT (longest processing time first — ≤4/3 optimal for P//C_max, empirically 0.91% gap on 11,261 real instances), and EDD (earliest due date — optimal for 1||T_max and 1||L_max). The composite ATC rule of Vepsalainen and Morton adds weighted urgency: I_j(t) = (w_j / p_j) · exp((max{d_j − p_j − t, 0}) / (K · p̄)) with O(n²) complexity.

**NEH heuristic (constructive insertion, O(n²m) with Taillard acceleration to O(n²m) with smaller constant).** Three-step procedure: (1) sort jobs by descending total processing time P_j = Σ_i p_{ij}; (2) seed with the best of the two partial permutations formed by the top-2 jobs; (3) iterate: at step k, extract job ℓ_{(k)} from the sorted list and insert it into every possible position of the current partial sequence, keeping the position that minimises partial C_max. Achieves 3.33% average deviation on Taillard's 120 benchmark instances; with Taillard's O(nm) per-step acceleration (NEHT), reduces to 2.24% in 0.077 s on average. NEH serves as both a standalone heuristic and a seed generator for metaheuristics.

**Shifting Bottleneck Heuristic (SBH, decomposition).** For the job shop: (1) identify the bottleneck machine (the one whose schedule contributes most to C_max); (2) solve the single-machine subproblem 1/r_j/max L_j for the bottleneck, using release dates derived from already-scheduled machines and due dates derived from downstream machines; (3) fix the bottleneck schedule and repeat for the remaining m−1 machines. The single-machine subproblem 1/r_j/max L_j is itself hard but solved with efficient exact algorithms.

**Iterated Greedy (IG, metaheuristic).** Four-phase loop (pseudocode in Fig. 3): (1) initialise with NEH + insertion local search; (2) Destruction — randomly remove `destruct` jobs from the current permutation π into a removed list π_R; (3) Reconstruction — reinsert each removed job into the best position of the partial sequence using the NEH insertion criterion; (4) Local Search — insertion neighbourhood until local optimality; (5) Acceptance — accept π'' if C_max(π'') < C_max(π), else accept with SA probability exp(−(C_max(π'') − C_max(π)) / Temperature). Two parameters only: `destruct` (number of jobs removed) and `Temperature`. Achieves 0.44% deviation on Taillard benchmarks in under a minute; a parallel island variant achieves 0.22%.

## What transfers to paper #2

- **EDD-based dispatch for job sequencing within a position** — Paper #2 minimises delay W^D · Σ v^D_r. Within a single parking position shared by multiple aircraft, sequencing aircraft by earliest target finish L_r (analogous to due date d_j) provides an O(n log n) feasibility-aware starting order. EDD is optimal for 1||T_max; paper #2's single-position subproblem is structurally a single-machine problem with release dates and due dates. Cost: trivial. Risk: EDD ignores the ε separation and blocking-arc timing interactions; treat as a tie-breaker only.

- **SPT / LPT for position load balancing** — When assigning aircraft to positions, sorting aircraft by descending total processing time T_r = Σ D_j (LPT-style) and assigning to the least-loaded position gives a balanced initial assignment that minimises makespan W^M · m. This is the direct analogue of LPT for P//C_max. Cost: trivial. Risk: ignores blocking-arc geometry; must be combined with a blocking-aware correction pass.

- **NEH insertion criterion as a constructive sub-routine** — The NEH logic (sort by processing load, then greedily insert each item into the best position of a partial solution) is directly adaptable to the aircraft-to-position assignment phase. Specifically: sort aircraft by T_r descending; for each aircraft, trial-insert it into each candidate parking position and evaluate the resulting objective (delay + movement penalty); keep the best insertion. This is more informed than random assignment and runs in O(|R| · |P|) per aircraft. Cost: low (need a fast objective evaluator for a partial assignment). Risk: the objective evaluator for partial assignments must handle the blocking-arc structure, which requires care; a simplified penalty (e.g., count of blocking-arc conflicts) is a practical proxy.

- **NEH as seed for the GRASP/IG outer loop** — The GRASP digest ([[GRASP]]) recommends seeding with high-quality initial solutions. An NEH-style construction (sort by T_r, greedy insertion) produces a deterministic, high-quality seed that is better than random initialisation. Cost: negligible once the insertion evaluator exists. Risk: none.

- **Iterated Greedy destruction-reconstruction loop** — IG's Destruction + Reconstruction cycle is a natural perturbation operator for paper #2's position-assignment component. Destruction: randomly remove `d` aircraft from their assigned positions. Reconstruction: reinsert each removed aircraft into the best available position using the NEH insertion criterion (best-position insertion). The SA-style acceptance criterion (with Temperature) allows uphill moves and prevents premature convergence. This gives a complete, low-parameter metaheuristic requiring only `destruct` and `Temperature` to tune. Cost: moderate (need the insertion evaluator and the local search). Risk: medium — the reconstruction quality depends heavily on how well the partial-solution evaluator captures the blocking-arc timing interactions.

- **Insertion neighbourhood for local search** — The chapter identifies insertion (extract one item, reinsert at the best position) as the dominant local search neighbourhood for scheduling permutations. For paper #2 this maps to: extract one aircraft from its position, trial-reinsert it into every other position, accept the best improving move. This is simpler than swap and more effective in practice (corroborated by IG's use of it as its sole local search). Cost: O(|R| · |P|) per move evaluation. Risk: low.

- **SBH decomposition principle as a position-sequencing sub-solver** — The SBH decomposes the multi-machine job shop into repeated single-machine subproblems. Paper #2 has an analogous decomposition: fix position assignments, then sequence aircraft within each position as a 1/r_j/d_j problem (one machine per position). For each position, solve 1/r_j/C_max or 1/r_j/T_max exactly (polynomial or pseudo-polynomial) and propagate timing to the blocking-arc constraints. Cost: high (need a per-position single-machine solver that respects ε separation and blocking interactions). Risk: medium — the inter-position coupling through blocking arcs means the subproblems are not fully independent; iterating the decomposition (as SBH does) is required for convergence.

- **ATC composite rule for urgency-weighted dispatch** — ATC's index I_j(t) = (w_j/p_j) · exp(slack / (K · p̄)) captures both weight and remaining slack simultaneously. For paper #2, an ATC-style index for aircraft could be I_r(t) = (W^D / T_r) · exp(max{L_r − T_r − t, 0} / (K · T̄)) to prioritise aircraft with short slack and high delay weight during construction. Useful when the objective weight W^D dominates (as in the default profile W^D = 1.0 vs W^M = 0.1). Cost: low (one parameter K requires calibration). Risk: low.

## What does NOT transfer

- **Permutation flow shop structure (NEH's native setting)** — NEH was designed for the F/prmu/C_max problem where all jobs visit all machines in the same fixed order and the only decision is the job sequence. Paper #2's aircraft do not share a fixed visit order across positions; they are assigned to exactly one position. The NEH sequence optimality guarantees therefore do not apply. Only the insertion-criterion mechanism transfers, not the flow shop convergence analysis.

- **Shifting Bottleneck as-is** — SBH assumes every job visits every machine (job shop). Paper #2 assigns each aircraft to exactly one position, so there is no multi-machine routing to decompose. The decomposition idea transfers in spirit (per-position single-machine sub-solver) but the SBH procedure itself does not.

- **Makespan-only focus of NEH and IG** — Both NEH and the original IG target C_max exclusively. Paper #2's default objective weights movements most heavily (W^S = 10), then delay (W^D = 1.0), then makespan (W^M = 0.1). The insertion criterion and acceptance criterion must be adapted to the composite objective, which complicates evaluation compared to the pure C_max setting.

- **No blocking-arc awareness in any rule** — None of the dispatching rules, NEH, SBH, or IG as described account for the Mode-A/B/C access conditions and the interruptibility constraint (I_j). These are paper #2-specific constraints that require custom feasibility checking layered on top of any imported mechanism.

- **Flow-time objective (Σ C)** — Several dispatching results (SPT optimality for 1||ΣC, EDD optimality for 1||T_max) rely on objectives that differ structurally from paper #2's weighted combination. The rules can be used heuristically but not with their optimality certificates.

## Verdict for theory_assisted

**Priority:** High

**Rationale:** This chapter supplies three directly actionable building blocks for paper #2. First, the NEH insertion-criterion mechanism provides a principled constructive heuristic for the aircraft-to-position assignment phase (sort by T_r, greedy best-position insertion), usable both standalone and as a seed for the GRASP loop described in [[GRASP.md]]. Second, the Iterated Greedy pseudocode (Fig. 3) is a complete, low-parameter metaheuristic template — destruction removes `d` aircraft from their positions, reconstruction reinserts them via the NEH criterion, local search applies the insertion neighbourhood, and SA acceptance prevents premature convergence — that can be instantiated for paper #2 with modest engineering effort and only two parameters to tune. Third, the ATC composite dispatching rule provides an urgency-weighted greedy index directly applicable to the construction phase when delay dominates (as in the default weight profile). The chapter does not address blocking-arc constraints or Mode-A/B/C access conditions, so all techniques require a custom feasibility layer. The combination of NEH-style construction + IG outer loop + insertion local search represents a coherent, well-validated design that is simpler than GRASP yet competitive on benchmarks.

## Cross-references

- [[GRASP.md]] — The GRASP chapter (same Handbook) describes the complementary outer-loop framework. NEH-seed + IG destruction-reconstruction can replace or augment the GRASP construction phase. The reactive α mechanism from GRASP.md is an alternative to IG's fixed Temperature parameter.
