# Epitropakis & Burke 2025 — Hyper-heuristics

**Citation:** Epitropakis M.G., Burke E.K. (2025) Hyper-heuristics. In: Martí R. et al. (eds.) *Handbook of Heuristics*. Springer Nature Switzerland AG. https://doi.org/10.1007/978-3-032-00385-0_24
**Source:** methods/theory_assisted/inspiration/Hyper-heuristics.pdf
**Read on:** 2026-06-11

## Problem solved by this source

This is a reference chapter, not a single-problem paper. It provides a comprehensive literature review of hyper-heuristics (post-2013), followed by a fully worked tutorial case study. The review covers: selection vs. generation hyper-heuristics, online vs. offline learning, multi-objective extensions, dynamic environments, machine-learning-based action selection, and scheduling/timetabling applications.

The case study develops **HHILS** (Hyper-Heuristic Iterated Local Search), a selection hyper-heuristic layered on top of Iterated Local Search. The low-level heuristics are perturbation operators; the high-level controller learns which operator to apply next based on observed reward. HHILS is evaluated across six HyFlex benchmark domains: bin packing, flow-shop, personnel scheduling, SAT, TSP, and VRP — none of which directly match paper #2, but the multi-resource scheduling domain (personnel scheduling) shares some structural features (jobs, resources, time windows, precedences).

## Technique

**HHILS framework (Algorithm 1).** The outer loop is Iterated Local Search. Each ILS iteration: (1) `ActionSelection(str)` — pick a low-level perturbation heuristic from set S using one of five action selection models; (2) `ApplyAction` — perturb the current solution; (3) `ApplyLocalSearch` — greedy local search until no improvement among the active subset of local search heuristics (Algorithm 2: active list L shrinks as non-improving LS methods are dropped, resets when all are exhausted); (4) `AcceptanceCriterion` — Metropolis-style acceptance with fixed temperature T = 2.0, probability `p = exp((f(s_cur) - f(s_tmp)) / (T * mu_i))` where `mu_i` is the mean improvement of improving iterations; (5) `CreditAssignment` — score the applied action using a sliding-window average of improvement rate: `r_i = (1 + improvement_i) / t_i`, averaged over the last w rewards (eq. 1).

**Five action selection models compared:**
- **HHILS** (baseline): uniform random selection, ignores all feedback.
- **HHILS-SA**: proportional selection (roulette wheel) on current reward scores.
- **HHILS-PM**: Probability Matching — maintains selection probabilities updated by exponential smoothing `q(t+1) = q(t) + gamma * (r(t) - q(t))` (gamma = 0.1), then renormalises to probabilities with floor p_min = 0.05 (eqs. 2–3).
- **HHILS-AP**: Adaptive Pursuit — winner-takes-all variant of PM; the best action's probability is pushed toward p_max = 1 - (alpha-1)*p_min at rate beta = 0.8, all others pushed toward p_min (eqs. 4–5).
- **HHILS-MAB**: Upper Confidence Bound (UCB) multi-armed bandit — selects action i* = argmax_i { q_i(t) + C * sqrt(2 log(sum n_k(t)) / n_i(t)) } with C = 0.8 (eqs. 6–8). Balances exploitation of best-performing operator with forced exploration of infrequently tried ones.

**Empirical finding:** HHILS-AP (Adaptive Pursuit) is the strongest overall, winning on BP, FS, TSP. HHILS-SA is second, winning on FS, PS, VRP. Both outperform uniform selection (HHILS baseline) consistently.

## What transfers to paper #2

- **HHILS as an outer loop for the theory_assisted method** — Paper #2's search structure maps directly onto ILS: an initial solution (aircraft-to-position assignment + job start times), a perturbation phase (change one or more position assignments or reschedule), and a local search phase (improve timing given fixed assignment). The HHILS controller can adaptively select among multiple perturbation operators (e.g., single-aircraft reassignment, two-aircraft swap, re-timing a rear-access aircraft) without manual tuning. Cost: moderate — requires defining the perturbation operator set and a feasibility-preserving local search. Risk: low at the framework level.

- **Adaptive Pursuit (AP) for operator selection** — AP is the best-performing action selection model in the benchmark, and it has a single parameter (beta = 0.8 per the chapter default). For paper #2, the candidate low-level perturbations are structurally diverse: (a) swap two aircraft positions, (b) reassign one aircraft to a different position, (c) shift job start times within a fixed assignment to reduce Mode-C collisions, (d) insert idle gaps to enable Mode-B accesses. AP will naturally shift probability mass toward whichever of these is most productive on the current instance without requiring per-instance tuning. Cost: ~20 lines of bookkeeping. Risk: low; AP is parameter-robust per the literature.

- **UCB multi-armed bandit (HHILS-MAB) as alternative** — UCB (eq. 6) provides the strongest exploration guarantee among the five models. For paper #2, where perturbation operators may have very different applicability depending on the topology (number of blocking arcs, depth of chains), UCB's forced exploration of rarely tried operators provides an important safety net against premature convergence to a single strategy. Cost: trivial (same bookkeeping as AP plus a visit counter). Risk: low; UCB is well-understood theoretically.

- **Sliding-window credit assignment (eq. 1)** — The reward `r_i = (1 + improvement_i) / t_i` normalised over a sliding window of w recent evaluations is directly applicable to paper #2. The normalisation by time spent (`t_i`) is particularly apt because perturbation operators in paper #2 have very different computational costs (a timing-only reschedule is cheap; a full reassignment with mode-classification is expensive). Cost: one parameter (window size w). Risk: low.

- **Metropolis acceptance criterion normalised by mean improvement** — The acceptance probability `p = exp((f_cur - f_tmp) / (T * mu_i))` uses the running mean improvement `mu_i` rather than a fixed scale, making the temperature T problem-independent. For paper #2 the objective mixes makespan, delay, and movement count with very different scales (W^M = 0.1, W^D = 1.0, W^S = 10), so normalising by observed improvement magnitude avoids the need to manually calibrate T to the objective scale. Cost: one extra running mean. Risk: low.

- **Active local search list (Algorithm 2)** — The greedy local search drops non-improving LS methods from the active list until all are exhausted, then returns the best found. For paper #2 this is natural: several local search neighbourhoods can coexist (e.g., improve timing within assignment, close unnecessary Mode-C events, compress idle gaps), and Algorithm 2 automatically focuses on the productive ones per call without explicit priority management. Cost: trivial once neighbourhoods are defined. Risk: low.

- **Problem-domain decomposition insight from scheduling section** — The chapter's review of scheduling hyper-heuristics ([80]: Workover Rigs, [86]: intercell scheduling with ant colony HH) consistently shows that effective perturbation heuristics must respect the sub-problem structure (assignment vs. sequencing vs. timing). For paper #2, this strongly suggests maintaining a clear separation between the position-assignment perturbation layer and the job-timing local search layer, exactly as the two-phase GRASP approach in the GRASP digest recommends. The hyper-heuristic layer then selects which assignment-level perturbation to apply, while the local search always handles the timing sub-problem. Cost: architectural — must be designed in from the start. Risk: medium if the two layers interact in complex ways.

## What does NOT transfer

- **HyFlex framework itself** — HyFlex is a Java platform with pre-coded problem domains (SAT, bin packing, TSP, etc.). Paper #2 is not one of those domains and would need to be implemented from scratch; there is no benefit to adopting HyFlex over a native Python implementation.

- **Cross-domain generalisation** — A significant portion of the chapter concerns hyper-heuristics that transfer learned behaviour across problem classes. Paper #2 is a single, well-defined problem; cross-domain generality is irrelevant.

- **Generation hyper-heuristics (GP-based, grammatical evolution)** — These automatically design new low-level heuristics. Paper #2 already has well-understood operator types (reassign, swap, retime); generating new ones via GP is unnecessary complexity.

- **Multi-objective hyper-heuristic extensions** — Paper #2 has a weighted-sum single objective (eq. in problem_statement.md). The multi-objective hyper-heuristic literature (choice function + hypervolume guidance, MOEA/D-based HH) does not apply.

- **Bin packing, SAT, TSP experimental results** — The numerical tables (Tables 1–5) are benchmarks on HyFlex domains unrelated to aircraft scheduling; the specific numbers provide no direct guidance.

- **Lifelong learning / self-organising hyper-heuristics** — Systems that learn continuously across unseen instances [14, 21–23] are irrelevant: paper #2 is solved instance-by-instance within a fixed time budget.

## Verdict for theory_assisted

**Priority:** Medium

**Rationale:** The HHILS framework (ILS + adaptive operator selection) is a clean, well-tested architecture that fits paper #2 well: ILS naturally decomposes into the position-assignment perturbation and job-timing local search that the problem requires, and the five action selection models (especially AP and UCB-MAB) provide principled, low-overhead mechanisms to avoid manual tuning of operator probabilities. The sliding-window credit assignment and Metropolis acceptance normalised by mean improvement are directly reusable implementation details. However, the chapter does not add a qualitatively new algorithmic idea beyond what GRASP+VNS already covers: the GRASP digest already captures the iterative construction-and-local-search loop, path relinking, and multi-neighbourhood descent. The main additive value here is the **action selection module** (AP / UCB) as a principled replacement for fixed operator weights or a random restart strategy — and Algorithm 2's active-list local search as a lightweight multi-neighbourhood mechanism. These are medium-cost, medium-gain additions to the theory_assisted design.

## Cross-references

- [GRASP.md](GRASP.md) — The GRASP framework provides the construction phase and path relinking that HHILS lacks. Combining GRASP construction with HHILS's ILS+AP perturbation loop is the natural synthesis: use GRASP to generate a diverse initial solution, then hand it to HHILS-AP for intensification. The reactive-α mechanism in GRASP maps onto the same exploration-exploitation concern as UCB in HHILS.
