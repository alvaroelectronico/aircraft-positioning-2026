# Sevaux, Sörensen, Pillay 2025 — Adaptive and Multi-level Metaheuristics

**Citation:** Sevaux M., Sörensen K., Pillay N. (2025) Adaptive and Multi-level Metaheuristics. In: Martí R. et al. (eds.) *Handbook of Heuristics*. Springer Nature Switzerland AG. https://doi.org/10.1007/978-3-032-00385-0_16
**Source:** methods/theory_assisted/inspiration/Adaptive_and_Multi-level_Metaheuristics.pdf
**Read on:** 2026-06-11

## Problem solved by this source

This is a survey/reference chapter, not a paper solving a specific problem. Its subject is the *configuration* problem of metaheuristic algorithms: how to determine and, more importantly, how to dynamically adapt the control flow and parameter values of a metaheuristic during a search run. The chapter does not target one application domain; it provides a structured taxonomy applicable to any combinatorial optimisation problem.

The chapter is directly complementary to the GRASP digest (GRASP.md): where that chapter describes the GRASP algorithm in detail, this chapter explains the mechanisms by which any metaheuristic — including GRASP, tabu search, VNS, ALNS — can self-tune its parameters and operator-selection probabilities during search, removing the burden of offline parameter calibration.

## Technique

**Definitions (Section "Definitions").** The chapter introduces precise vocabulary. A metaheuristic *configuration* = its control flow (order of components) + parameter values. An *adaptive* metaheuristic modifies its configuration during the run. A *multi-level* metaheuristic uses a second metaheuristic algorithm to perform the adaptation (i.e., a hyper-heuristic). These definitions frame everything that follows.

**Simple adaptive mechanisms (pp. 11).** Online parameter tuning examples include: (a) *cycle detection* in tabu search — detect cycling in the objective trajectory and lengthen the tabu tenure in response (ref [36]); (b) *retroactive loops* in simulated annealing — control the temperature schedule to follow a predefined acceptance probability curve (ref [7]).

**Reactive search — Battiti [2] (pp. 11).** Feedback-based parameter tuning driven by search history. Two uses: (i) automated tuning of parameter values based on past events; (ii) automated balance of diversification vs. intensification. Reactive tabu search adjusts tabu tenure: lengthen if search is not improving, shorten if it is. This is the foundational adaptive mechanism referenced by all other methods in the chapter.

**Reactive GRASP — Delorme et al. [13] (pp. 11–12).** For each α_i in a discrete set, maintain a pool P_i of solutions found under that α_i and a weight λ_i. The selection probability p_i = λ_i / Σλ_k. The weight update rule is:

  λ_i = ( mean_{x ∈ P_i}[f(x) − f(x̲)] / (f(x̄) − f(x̲)) )^δ

where x̲ is the best solution found so far, x̄ is the worst, and δ attenuates the update speed. Good α_i values accumulate weight; poor ones are demoted. This is a more precise formulation than the one cited in GRASP.md (which references a different reactive GRASP variant by Prais and Ribeiro [30]).

**Adaptive Large Neighbourhood Search — ALNS (pp. 12–14).** LNS alternates destructive heuristics (partial solution destruction) and constructive heuristics (rebuild). ALNS selects the destroy/repair pair adaptively. Each heuristic i starts with λ_i^c = 1 (or λ_i^d = 1). After each iteration, the selected pair is scored:

  α = 0.5  if new solution is worse than current
  α = 1.5  if new solution is better than current
  α = 2    if new solution is better than global best

The weight update is: λ_{i,new} = γ·λ_i + (1−γ)·α, where γ ∈ (0,1) is a smoothing parameter. The resulting probabilities p_i = λ_i / Σλ_k remain bounded in (0.5/(n·γ+1−γ), 2/(n·γ+1−γ)) so no heuristic is ever excluded. The meta-analysis by Turkeš et al. [40] (Eur J Oper Res 292(2):423–442, 2021) critically notes that on average, the adaptive layer contributes only ~0.14% improvement in solution quality in ALNS. The benefit is most pronounced when the problem instance set has high internal diversity.

**Multi-level metaheuristics / Hyper-heuristics (pp. 14–19).** A hyper-heuristic operates on the space of heuristics rather than the space of solutions. Two main categories: (i) *selection* hyper-heuristics — choose which low-level heuristic to apply at each step; (ii) *generation* hyper-heuristics — evolve new low-level heuristics (primarily via genetic programming). Selection hyper-heuristics can be constructive (choose construction operators) or perturbative (choose neighbourhood operators). Move acceptance can be simple (accept if improving) or complex (simulated annealing acceptance). Applications to timetabling scheduling [32] illustrate that different low-level heuristics are effective at different stages of construction, motivating dynamic selection.

**Configuring a Metaheuristic (pp. 8–10).** The chapter distinguishes offline parameter tuning (before the run, using a representative instance subset, e.g. factorial design [22, 45, 46], response surface methodology [12]) from online adaptive tuning. Best practice: report results under both "standard" and "best" parameter settings (Prins [31]).

## What transfers to paper #2

- **ALNS adaptive weight update (the three-score rule + exponential smoothing)** — Paper #2 requires both a destroy operator (remove an aircraft's position assignment and job schedule) and a repair operator (reassign and reschedule). Multiple destroy/repair strategies are natural: destroy by worst-delay aircraft, by highest-movement aircraft, by randomly chosen aircraft; repair by earliest-start greedy, by blocking-arc-aware greedy, by timing optimisation. The ALNS weight update (α ∈ {0.5, 1.5, 2.0}, λ_{new} = γλ + (1−γ)α) automatically identifies which destroy/repair combination performs well on the particular instance topology (sparse vs. dense blocking graph). Cost: low — the mechanism is ~20 lines of bookkeeping on top of any LNS skeleton. Risk: the Turkeš meta-analysis [40] warns that the benefit is marginal on average; for paper #2 this risk is mitigated because the blocking-arc graph structure creates genuine diversity across instances, which is precisely the scenario where ALNS adaptivity helps most.

- **Reactive GRASP weight update (Delorme et al. formula)** — The formula λ_i = (mean[f(x)−f(x̲)] / (f(x̄)−f(x̲)))^δ is a normalised, attenuated version of the Prais-Ribeiro reactive GRASP. It is more stable than the simpler q_i = ẑ/A_i formula referenced in GRASP.md because it uses a relative gap normalised to [0,1]. For paper #2's GRASP construction loop (choosing α for the RCL), the Delorme formula is preferable when the objective scale varies strongly across instance sizes (which it does: makespan, delay, and movements have different magnitudes). Cost: trivial — replace three lines in the reactive GRASP update. Risk: requires the δ parameter to be set; δ=1 is a safe default.

- **Reactive tabu tenure** — If the theory_assisted method uses tabu search as a local search component (e.g. for rescheduling a single aircraft's jobs after a position assignment is fixed), the reactive tabu search rule (lengthen tenure when cycling is detected, shorten when improving) provides a self-tuning alternative to fixed tenure. For paper #2 the cycle-detection signal can be defined as: the same (position-assignment, job-ordering) combination has been visited within the last T iterations. Cost: low. Risk: the tenure update requires a cycle-detection criterion; for a mixed continuous-discrete solution space the criterion needs careful definition.

- **Selection perturbative hyper-heuristic as operator selector** — The framework of selecting among a set of neighbourhood operators at each local search step (with simulated annealing or improving-move acceptance) maps directly onto the multi-neighbourhood structure needed for paper #2: swap two aircraft positions, reassign one aircraft, retiming a single job chain, merge two aircraft schedules. A selection hyper-heuristic avoids committing to a fixed VND ordering. Cost: moderate (need to define the operator set and acceptance criterion). Risk: medium — selection hyper-heuristics can waste evaluations on poor operators; the ALNS weight mechanism above is a simpler, lower-risk version of the same idea.

- **Offline parameter calibration discipline** — The chapter's best practice of reporting results under both "standard" and "best" parameter settings is directly applicable to the theory_assisted method's benchmarking. For paper #2, parameters such as GRASP's α (or the reactive α set), ALNS γ, and neighbourhood weights should be reported with and without tuning so the contribution of each is separable. Cost: none — this is a reporting discipline. Risk: none.

- **Turkeš et al. [40] meta-analysis finding** — The 0.14% average improvement from ALNS adaptivity is a concrete calibration benchmark. If the theory_assisted ALNS implementation shows improvement well above this threshold on paper #2's instances, it is likely driven by genuine instance diversity (the blocking-arc graph). If improvement is below this threshold, the adaptive layer should be simplified to a fixed uniform selection. Cost: none — this is a diagnostic criterion.

## What does NOT transfer

- **Generation hyper-heuristics (genetic programming to evolve operators)** — Creating new neighbourhood operators or construction heuristics via genetic programming is a multi-month research effort and requires a large training set of instances. Paper #2 has a small benchmark set; this approach is not applicable.

- **Multi-level metaheuristics with evolutionary algorithm configuration** — Using a genetic algorithm or grammatical evolution to configure the metaheuristic for paper #2 (as in refs [6, 15, 25, 26]) is overkill for a single well-defined problem class and would require substantial offline training infrastructure. Not applicable.

- **Response surface methodology for parameter tuning** — The RSM approach (fitting a surrogate model to parameter-space performance) is appropriate when there are many interacting numerical parameters and a large evaluation budget. Paper #2's metaheuristic will likely have 2–4 key parameters; manual grid search or reactive self-tuning is sufficient. RSM is not necessary.

- **Continuous-domain adaptive mechanisms** — All mechanisms specific to continuous parameter vectors (coordinate line-search, gradient-based tuning) are irrelevant; paper #2 is a discrete combinatorial problem.

- **AI-driven parameter tuning / meta-learning / NAS** — The "Perspectives" section describes RL-based and deep-learning approaches to parameter configuration. These are future research directions requiring infrastructure well beyond the scope of paper #2's solution method.

## Verdict for theory_assisted

**Priority:** Medium

**Rationale:** This chapter does not introduce a new algorithm for scheduling or assignment problems; it surveys the configuration and adaptation layer that sits on top of any metaheuristic. Its concrete technical contribution to paper #2 is threefold: (1) the ALNS three-score adaptive weight update (α ∈ {0.5, 1.5, 2.0}), which is immediately usable in the LNS/ALNS skeleton of the theory_assisted method at negligible cost; (2) the Delorme et al. reactive GRASP weight formula, which is a direct improvement over the simpler Prais-Ribeiro formula already described in GRASP.md; and (3) the Turkeš meta-analysis finding that the adaptive layer in ALNS typically yields only ~0.14% improvement, which is a useful empirical brake against over-engineering the adaptive mechanism. The chapter is therefore a useful complement to GRASP.md but not a primary source — it adds specific formulas and one important empirical warning rather than a new algorithmic family.

## Cross-references

- [[GRASP]] — The reactive GRASP section (pp. 11–12) directly extends and refines the reactive GRASP mechanism described in GRASP.md. The Delorme formula (this digest) should be preferred over the Prais-Ribeiro formula (GRASP.md) for paper #2's implementation. The ALNS section (pp. 12–14) provides the destroy/repair adaptive framework that complements the GRASP construction discussed in GRASP.md.
