# Synthesis — theory_assisted method for paper #2

**Generated:** 2026-06-11
**Digests considered:** 10 files, listed below
**Focus from invocation:** (none — general)

---

## Digests considered

| slug | technique | verdict | most transferable idea |
| ---- | --------- | ------- | --------------------- |
| [[GRASP]] | GRASP: two-phase randomised-greedy construction + local search, reactive α, elite pool, path relinking | High | Reactive GRASP outer loop with value-based RCL on (aircraft, position) greedy cost; GRASP+VND as local search phase |
| [[Scheduling_Heuristics]] | NEH insertion heuristic, Iterated Greedy, ATC dispatching | High | IG destruction-reconstruction as a low-parameter perturbation loop; NEH-style greedy insertion as construction and seed |
| [[Variable_Neighborhood_Descent]] | Sequential VND, Nested VND, Mixed VND, Adaptive VND | High | SeqVND (B-VND reset) over three defined neighbourhoods: Retime, Reassign, Swap; Nested VND for decomposed assignment/timing |
| [[Iterated_Local_Search]] | ILS four-component framework (init / perturbation / local search / acceptance), PFSP instantiation, don't-look bits | High | ILS as outer loop chaining local optima; worst-k-aircraft destruction-reconstruction perturbation; don't-look bits for scan speed-up |
| [[Random-Key_Genetic_Algorithms_Principles_and_Applications]] | BRKGA: biased crossover, elite elitism, mutants, IPR, shake, island model | High | Mixed-chromosome decoder (indicator for position assignment + permutation for job ordering); warm-start injection; implicit path relinking |
| [[Matheuristics_by_Examples]] | Local Branching, Proximity Search, RINS, alternating variable fixing, staged two-model refinement | High | Local Branching (Hamming-k constraint on binary position-assignment vars) as a MIP-based large-neighbourhood search; Proximity Search as polishing |
| [[Constraint-Based_Local_Search]] | CBLS model (required/soft constraints, violation degrees, invariant graph, getAssignDelta), composite neighbourhood, tabu filter | High | Incremental delta-evaluation of Mode-A/B/C access conditions via an invariant graph; required/soft split for initialisation vs. optimisation |
| [[Data_Mining_in_Heuristics]] | DM-MSH / MDM-MSH / MineReduce: frequent-itemset mining over elite set, pattern-seeded construction, reduce-optimise-expand | Medium | MineReduce: fix high-confidence (aircraft, position) pairs from mined elite set, solve reduced sub-instance, expand and locally search |
| [[Hyper-heuristics]] | HHILS: ILS + adaptive operator selection (AP, UCB-MAB), sliding-window credit assignment, active LS list | Medium | Adaptive Pursuit (AP) for operator selection among perturbation types; Metropolis acceptance normalised by mean improvement |
| [[Adaptive_and_Multi-level_Metaheuristics]] | ALNS adaptive weight update, Delorme reactive GRASP formula, reactive tabu tenure | Medium | ALNS three-score weight update (α ∈ {0.5,1.5,2.0}) for selecting among destroy/repair pairs; Delorme formula as a more stable reactive-α update |

---

## Convergent themes

- **Separation of position assignment from job timing** — Supported by [[Variable_Neighborhood_Descent]], [[Iterated_Local_Search]], [[Constraint-Based_Local_Search]], [[Random-Key_Genetic_Algorithms_Principles_and_Applications]], [[Matheuristics_by_Examples]].  All five digests independently arrive at the same two-layer architecture: a combinatorial *outer* decision (which aircraft goes to which position) that has small cardinality and is expensive to change, and a *timing inner* decision (when does each job start) that is cheaper to adjust once positions are fixed.  Concrete instance for paper #2: position assignment is a discrete variable with |R|×|P| choices; job timing given fixed assignment is a constraint propagation problem solvable greedily (earliest-feasible-start sweep respecting precedence, ε gaps, and Mode-B μ gaps).  The correct architecture always fixes or perturbs positions at the outer level, then re-solves timing at the inner level.

- **NEH-style greedy insertion as construction backbone** — Supported by [[Scheduling_Heuristics]], [[GRASP]], [[Iterated_Local_Search]].  All three digests recommend a greedy best-insertion construction: sort aircraft by descending total processing time T_r; for each aircraft, try inserting it into every candidate position and keep the one with lowest incremental cost (estimated delay + movement penalty).  The resulting constructive heuristic is O(|R|·|P|) per aircraft, deterministic, and substantially better than random initialisation.  For paper #2 the incremental cost must account for the blocking-arc topology: a position p' with a heavily occupied front position p will incur higher Mode-C risk and should be penalised accordingly.

- **Destruction-reconstruction as the perturbation primitive** — Supported by [[Scheduling_Heuristics]] (IG), [[Iterated_Local_Search]], [[GRASP]] (path relinking), [[Random-Key_Genetic_Algorithms_Principles_and_Applications]] (shake / restart), [[Data_Mining_in_Heuristics]] (MineReduce).  Five digests all converge on the same perturbation operator: remove a subset of aircraft from their positions (destruction), then reinsert them greedily (reconstruction).  The selection of which aircraft to remove differs: random (IG baseline), worst-objective-contribution (ILS recommendation), highest blocking-arc involvement, or pattern-guided (MineReduce).  Concrete instance for paper #2: remove the k aircraft with the highest individual contribution to the objective W^D·v^D_r + W^S·n_r, then reinsert them via the NEH insertion criterion.

- **Reactive / adaptive self-tuning of parameters** — Supported by [[GRASP]] (reactive α, Prais-Ribeiro), [[Adaptive_and_Multi-level_Metaheuristics]] (Delorme formula, ALNS weight update), [[Hyper-heuristics]] (AP, UCB-MAB).  Three digests address the same problem (fixed parameters are fragile across instance types) and propose compatible solutions: maintain a probability distribution over parameter values or operators; update after each iteration using a normalised quality score.  Concrete instance for paper #2: for GRASP's α, use the Delorme formula [[Adaptive_and_Multi-level_Metaheuristics]] (more stable than Prais-Ribeiro because it normalises to [0,1]); for the choice among perturbation operators (retime-only, single-reassign, swap), use Adaptive Pursuit [[Hyper-heuristics]].  The Turkeš meta-analysis warning [[Adaptive_and_Multi-level_Metaheuristics]] that ALNS adaptivity contributes only ~0.14% on average is useful: do not over-engineer the adaptive layer.

- **Incremental move evaluation as the implementation bottleneck** — Supported by [[Constraint-Based_Local_Search]], [[Iterated_Local_Search]], [[Variable_Neighborhood_Descent]].  All three digests separately warn that the inner loop must evaluate candidate moves cheaply.  [[Constraint-Based_Local_Search]] provides the most precise solution: the invariant graph with O(1) `getAssignDelta` calls.  [[Iterated_Local_Search]] provides the don't-look-bit speed-up for neighbourhood scans.  [[Variable_Neighborhood_Descent]] recommends first-improvement for the large swap neighbourhood.  Concrete instance for paper #2: Mode-A/B/C classification of an access instant depends on whether time τ falls inside a job of the front aircraft.  After a position-reassignment move, only the blocking arcs incident on the moved aircraft change; the move evaluator need only re-classify the access instants on those arcs.

---

## Distinct angles

- **BRKGA mixed-chromosome decoder** — from [[Random-Key_Genetic_Algorithms_Principles_and_Applications]].  This is the only digest that suggests an evolutionary population framework as the outer loop, as opposed to single-solution metaheuristics (ILS, GRASP, VNS).  The mixed-chromosome encoding (indicator keys for position assignment, permutation keys for sequencing within positions) is a clean, decoder-centric architecture.  Interesting because it enables Implicit Path Relinking (IPR) entirely in key space — no problem-specific move operator needed for intensification — and because warm-start injection of the existing MILP baseline solution is straightforward.  The risk is that the decoder's Mode-A/B/C feasibility repair must be deterministic and correct; incorrect repair silently corrupts fitness.

- **Local Branching / Proximity Search over the MILP** — from [[Matheuristics_by_Examples]].  The only digest that uses the existing MILP model as a component inside a heuristic loop rather than as a standalone solver.  Local Branching adds a single Hamming-k constraint on binary position-assignment variables, letting the solver re-optimise all start times freely within a Hamming neighbourhood.  This is qualitatively different from all other candidates: it does not require a hand-designed local search; the solver performs the optimisation within the neighbourhood.  Interesting because the paper already has a working MILP baseline (milp_baseline) — Local Branching costs almost nothing to implement on top of it and delivers a certified-quality neighbourhood search.

- **MineReduce for position-assignment sub-instance reduction** — from [[Data_Mining_in_Heuristics]].  The idea of fixing high-confidence (aircraft, position) pairs mined from an elite set, solving a reduced instance, and expanding back is not covered by any other digest.  Interesting because it exploits a structural property specific to paper #2: the blocking-arc topology means some aircraft-position pairs are almost universally good (e.g., aircraft with no rear-position neighbours always go to front positions) and can be locked early, shrinking the sub-instance dramatically.  Risk: over-fitting the mined pattern to a particular local-optimum basin; mitigated by using only high-support patterns.

- **Required/soft constraint split for two-phase local search** — from [[Constraint-Based_Local_Search]].  The explicit distinction between hard constraints (as required constraints R, used to initialise a feasible solution via flow-based assignment) and difficult constraints (as soft constraints S expressed as violation degrees) is not treated elsewhere.  Interesting for paper #2 because Mode-A/B/C access conditions are non-trivial to satisfy and can be treated as softened during an initial infeasibility-reduction phase, then hardened once feasibility is achieved.

---

## Candidate approaches

### Candidate A — Iterated Greedy with VND local search (IG+VND)

**Inspired by:** [[Scheduling_Heuristics]], [[Variable_Neighborhood_Descent]], [[Iterated_Local_Search]], [[GRASP]]

**One-line summary:** NEH-style construction seeds an IG outer loop whose perturbation removes the k worst-performing aircraft and reinserts them greedily; local search is SeqVND over three neighbourhoods (Retime, Reassign, Swap) with B-VND reset.

**Skeleton (pseudocode):**
```
1.  Sort aircraft by T_r descending (NEH order).
2.  Construct s0: for each aircraft in order, assign to the position
    minimising g(r, p) = estimated_delay(r,p) + W^S * blocking_penalty(r,p).
3.  Schedule jobs: for each position, run earliest-feasible-start sweep
    (respects precedence, ε gaps, Mode-B μ gaps; marks Mode-C events).
4.  s* := s0
5.  while time_budget not exhausted:
    a.  DESTRUCTION: identify the k aircraft with highest individual
        contribution to objective; remove them from their positions.
    b.  RECONSTRUCTION: reinsert each removed aircraft using NEH
        insertion criterion (try all positions, keep best partial objective).
    c.  Re-schedule jobs for all affected aircraft (inner sweep).
    d.  LOCAL SEARCH — SeqVND(s', N = [N1, N2, N3], B-VND reset):
          N1 (Retime): for each aircraft r, shift entire job chain by
               ±Δ; accept first improvement. O(|R|) per sweep.
          N2 (Reassign): extract one aircraft, try all other positions;
               re-schedule and re-classify Mode-A/B/C; accept first
               improvement. O(|R|*|P|) per sweep.
          N3 (Swap): exchange positions of two aircraft; re-schedule
               both; first-improvement with random pair order.
               O(|R|^2 / 2) per sweep.
          On improvement reset to N1 (B-VND rule). Stop when no
          neighbourhood improves.
    e.  ACCEPTANCE: accept s'' if objective(s'') < objective(s*);
        else accept with probability exp(-(obj(s'')-obj(s*))/T)
        (SA Metropolis, T calibrated on small instances).
    f.  Update s* if s'' is best found.
6.  Return s*.
```

**Fit with paper #2:**
- *Mode A/B/C:* The inner earliest-feasible-start sweep classifies each access instant; N2 re-classifies after reassignment; don't-look bits [[Iterated_Local_Search]] skip aircraft whose neighbourhood has not changed.
- *Blocking arcs:* The greedy function g(r, p) penalises rear-position assignments for aircraft with many blocking interactions; N3 (Swap) is the primary operator for resolving symmetric blocking conflicts.
- *Objective:* Construction and acceptance criterion directly optimise W^M·m + W^D·Σv^D_r + W^S·n; the default weights (W^S=10 ≫ W^D=1 ≫ W^M=0.1) mean the movement count dominates — the greedy penalty must weight W^S heavily to reflect this.

**Effort estimate:** M — NEH construction + three neighbourhood evaluators + earliest-feasible-start sweep.  The critical engineering cost is the Mode-A/B/C re-classification after each N2/N3 move; a well-structured incremental evaluator keeps this manageable.

**Key risks:**
1. The earliest-feasible-start sweep may not find the timing that minimises movement count (it greedily minimises makespan); a separate timing-optimisation pass [[Variable_Neighborhood_Descent]] may be needed.
2. SA temperature T is instance-size sensitive because objective magnitudes scale with |R| and the W^S=10 multiplier; requires per-size calibration or replacement with the Delorme adaptive rule [[Adaptive_and_Multi-level_Metaheuristics]].
3. For instances with many non-interruptible jobs, Mode-C infeasibility may be widespread and the earliest-feasible-start sweep may produce large timing inflation; the algorithm needs a fallback repair that forces Mode-A access (delay the rear aircraft).

**First smoke test:** Instance `scn_triangle_tight_P5_R5_seed1` (5 positions, 5 aircraft, tight blocking topology already used in existing baseline runs).  Measure: does IG+VND find a lower objective than the topology heuristic (`topology_ms6_job_ar`) within 10 seconds?  Check that checker.py reports 0 violations.

---

### Candidate B — GRASP + VND with reactive α and elite-pool path relinking (GRASP+VND+PR)

**Inspired by:** [[GRASP]], [[Variable_Neighborhood_Descent]], [[Adaptive_and_Multi-level_Metaheuristics]], [[Constraint-Based_Local_Search]]

**One-line summary:** Reactive GRASP outer loop (Delorme α self-tuning) constructs diverse initial solutions; each is polished by SeqVND; an elite pool is maintained and path relinking is applied as post-processing between the current solution and a randomly drawn elite member.

**Skeleton (pseudocode):**
```
1.  Initialise α-probability vector over A = {0.0, 0.1, ..., 1.0}
    uniformly; elite pool E = {}.
2.  while time_budget not exhausted:
    a.  CONSTRUCTION (reactive GRASP, VB-RCL):
          Sample α from current distribution.
          Sort (aircraft, position) pairs by g(r,p) ascending.
          Form RCL: all pairs with g(r,p) <= g_min + α*(g_max - g_min).
          Iteratively select uniformly from RCL; assign aircraft;
          update residual greedy costs for remaining aircraft.
          Schedule jobs via earliest-feasible-start sweep.
    b.  LOCAL SEARCH — SeqVND (same N1/N2/N3 as Candidate A, B-VND reset).
    c.  Update α weights using Delorme formula:
          λ_i = ( mean_{x in pool_i}[f(x) - f(x*)] / (f(worst) - f(x*)) )^δ
          renormalise to probabilities.
    d.  If objective(s'') < any solution in E or |E| < max_elite:
          add s'' to E (maintain E sorted, size <= max_elite = 10).
    e.  PATH RELINKING (every P_freq iterations):
          Pick guiding solution y from E at random.
          Walk through Δ(s'', y) (set of aircraft with differing
          positions); at each step apply the reassignment move from s''
          toward y that gives the best intermediate objective;
          apply VND to the best intermediate solution found.
    f.  Update s* if best found.
3.  Return s*.
```

**Fit with paper #2:**
- *Mode A/B/C:* VND handles same incremental classification as Candidate A.  The GRASP RCL greedy function includes a static blocking penalty; path relinking refines the assignment by moving toward an elite solution whose positions are known to be Mode-A-friendly.
- *Blocking arcs:* Elite pool naturally accumulates solutions where problematic blocking arcs are resolved; path relinking propagates those good assignments to new solutions.
- *Objective:* Reactive α self-tunes toward the greediness level that best serves the current objective profile (W^S dominant).  The Delorme formula [[Adaptive_and_Multi-level_Metaheuristics]] is more stable than Prais-Ribeiro because it normalises the improvement signal.

**Effort estimate:** M-L — GRASP construction requires a careful greedy function that captures blocking-arc risk; the path relinking walk requires a well-defined move on Δ(s'', y); the Delorme update is 5 lines but requires maintaining per-α solution pools.  Substantially more code than Candidate A, but each component is independently testable.

**Key risks:**
1. The greedy function g(r,p) is a static estimate; it may rank positions poorly in the early construction when timing interactions are not yet known, leading to a weak RCL.  Mitigate with a two-pass construction (first pass assigns aircraft, second pass re-evaluates and optionally re-assigns the worst 20%).
2. Path relinking requires a meaningful elite pool; for small instances (|R|=5) the pool may not diversify enough to add value over VND alone.
3. GRASP is intrinsically a multistart algorithm and requires many iterations to converge; with a tight time budget (< 30 s), fewer iterations than needed may yield worse results than the single-run IG of Candidate A.

**First smoke test:** Same instance as Candidate A.  Compare GRASP+VND objective trajectory vs. IG+VND at 10 s, 30 s, 60 s.  If GRASP+VND does not pull ahead of IG+VND by 60 s, the path relinking or α-diversity is not helping and Candidate A is preferable.

---

### Candidate C — BRKGA with mixed-chromosome decoder and warm-start (BRKGA-decoder)

**Inspired by:** [[Random-Key_Genetic_Algorithms_Principles_and_Applications]], [[Scheduling_Heuristics]], [[GRASP]]

**One-line summary:** A BRKGA population encodes aircraft-to-position assignments (indicator keys) and within-position sequencing priorities (permutation keys); the decoder computes the earliest-feasible schedule with Mode-A/B/C classification; the existing MILP baseline solution warm-starts the population.

**Skeleton (pseudocode):**
```
1.  CHROMOSOME LAYOUT (length n = 2|R|):
      Genes 1..|R|: position-assignment keys.
        key_r -> position floor(key_r * |P|) (indicator decoder).
      Genes |R|+1..2|R|: sequencing priority keys.
        For aircraft sharing a position, process in ascending key order.

2.  DECODER(chromosome):
    a.  Assign each aircraft r to position pi(r) = floor(key_r * |P|).
    b.  For each position p, sort its assigned aircraft by sequencing
        key; schedule in that order via earliest-feasible-start sweep:
        - Respect E_r (earliest start), ε inter-aircraft gap.
        - For each access instant (entry s_r', exit f_r'):
            Classify Mode A/B/C against front-position aircraft.
            If Mode C with non-interruptible job: push start time of
            r' forward to the next Mode-A or Mode-B window.
        - Compute κ_j for Mode-C events; update f_j accordingly.
    c.  Compute objective W^M*makespan + W^D*Σdelay + W^S*movements.
    d.  Return (objective, solution_dict).

3.  WARM START:
    Reverse-encode existing MILP baseline and topology heuristic
    solutions into chromosomes; inject into initial population.

4.  BRKGA LOOP (use Python API github.com/ceandrade/brkga_mp_ipr_python):
    - Population size |P_pop| = max(100, 10*n).
    - Elite fraction 15%, mutant fraction 10%, ρ = 0.7.
    - Every I_shake = 50 generations without improvement: Shake
      (resample non-elite chromosomes, keep elite).
    - Every I_ipr = 100 generations: Implicit Path Relinking between
      two elite chromosomes with minimum Hamming distance md = n/2.
    - Terminate on time budget.

5.  Return best decoded solution.
```

**Fit with paper #2:**
- *Mode A/B/C:* The decoder's earliest-feasible-start sweep handles Mode classification and repair deterministically; the chromosome never encodes infeasible solutions because the decoder always repairs.
- *Blocking arcs:* The indicator decoder assigns aircraft to positions freely; the sweep immediately detects and resolves Mode-C conflicts.  The fitness landscape naturally penalises assignments with many Mode-C events through the W^S=10 movement weight.
- *Objective:* The decoder computes the exact composite objective; crossover propagates elite position-assignment patterns (the indicator keys) to offspring, gradually concentrating population on low-movement assignments.

**Effort estimate:** L — the decoder's Mode-A/B/C repair is the most complex component (must be deterministic and match checker.py exactly); the population loop is almost free via the Python API.  The decoder repair logic is independently testable against checker.py before the BRKGA loop is added.

**Key risks:**
1. Decoder correctness: incorrect Mode-C repair silently produces infeasible solutions that earn an artificially low objective; the decoder must be validated against checker.py exhaustively before integration.
2. Chromosome diversity collapse: if the repair logic always snaps access instants to the same Mode-A window, crossover over the sequencing keys produces little timing variety, and the population stagnates.  Mitigate by incorporating a small deliberate timing jitter in the repair (push to second-best Mode-A window with 10% probability).
3. Large chromosome length: n = 2|R| means for |R|=20 aircraft, n=40 genes; the BRKGA parameter defaults (|P_pop|=400) may require a wall-clock budget that exceeds paper #2's benchmark limit.

**First smoke test:** Implement decoder only (no BRKGA loop), called with a random chromosome.  Verify checker.py passes on 10 random chromosomes.  Then run BRKGA for 60 s on the `scn_triangle_tight` instance and compare to MILP baseline solution quality.

---

### Candidate D — Matheuristic: GRASP construction + Local Branching refinement (GRASP+LB)

**Inspired by:** [[Matheuristics_by_Examples]], [[GRASP]], [[Scheduling_Heuristics]]

**One-line summary:** A GRASP construction (or NEH insertion) produces a warm-start solution; the existing MILP is then invoked with a Local Branching constraint (Hamming-k on position-assignment binary variables) to re-optimise job timing and movements within a k-aircraft neighbourhood.

**Skeleton (pseudocode):**
```
1.  PHASE 1 — CONSTRUCTION:
    Run NEH-style greedy insertion to produce s0 (as in Candidate A).
    Schedule jobs via earliest-feasible-start sweep.
    Optionally run a short VND pass (N1+N2 only) to polish s0.

2.  PHASE 2 — LOCAL BRANCHING LOOP:
    x_bar := binary encoding of s0's position assignment
             (x_{r,p} = 1 if aircraft r is at position p).
    while time_budget not exhausted:
      a.  Add Local Branching constraint to MILP:
            Σ_{r,p: x_bar_{r,p}=0} x_{r,p}
          + Σ_{r,p: x_bar_{r,p}=1} (1 - x_{r,p}) <= k
          where k = min(5, |R|/2).
      b.  Set MIP time limit = min(30 s, remaining_budget / 3).
      c.  Solve modified MILP (all job start times and κ_j free;
          position assignments restricted to Hamming-k of x_bar).
      d.  If improvement found: update x_bar, remove LB constraint, go to (a).
      e.  Else (no improvement): increment k by 2 (expand neighbourhood);
          if k > |R|: break.

3.  PHASE 3 — PROXIMITY POLISH (optional, if budget remains):
    Replace objective with minimise Δ(x, x_bar) (Hamming distance).
    Add constraint: W^M*m + W^D*Σv^D + W^S*n <= current_best - θ.
    Solve with short time limit.

4.  Return best feasible solution found.
```

**Fit with paper #2:**
- *Mode A/B/C:* The MILP already encodes Mode-A/B/C conditions (the existing milp_baseline handles them); the LB constraint only restricts position assignments, leaving timing variables completely free for re-optimisation by the solver.
- *Blocking arcs:* The MILP's constraint set fully captures blocking interactions; LB lets the solver escape the current position-assignment local optimum within a controlled radius, which is exactly what hand-coded neighbourhood search does but with exact evaluation.
- *Objective:* The full weighted objective (W^M·m + W^D·Σv^D_r + W^S·n) is maximally exploited by the MIP solver within the LB neighbourhood; no approximation of movement counts or delay.

**Effort estimate:** S — the LB constraint is one additional linear inequality added to the existing milp_baseline model; the phase 1 construction is shared with Candidate A.  This is the lowest-code-volume candidate.

**Key risks:**
1. MIP solve time per LB iteration may be prohibitive for large instances (|R| > 15); the time limit per solve must be tight to keep the loop useful.
2. The existing MILP baseline may not expose the position-assignment binary variables in a form directly compatible with the LB constraint formulation; requires inspecting the model structure.
3. For instances where the construction heuristic already produces a near-optimal position assignment, LB will not improve it (k small → no better assignment within radius); the k-escalation in step (e) mitigates this but increases each solve cost.

**First smoke test:** Add the LB constraint (k=3) to the existing milp_baseline for `scn_triangle_tight_P5_R5_seed1`; set solver time limit = 10 s; compare resulting objective to the unconstrained MILP solve.  If LB finds a better solution in fewer seconds than unconstrained MILP, the matheuristic loop is viable.

---

## Recommendation

**Build Candidate A (IG+VND) first.**

The four candidates form a natural risk/reward ordering.  Candidate A requires no MILP solver, no evolutionary infrastructure, and no data-mining library — only three neighbourhood evaluators, an earliest-feasible-start sweep, and a simple perturbation loop.  Every component is independently testable, and the two controlling parameters (destruction size k, SA temperature T) can be fixed at literature-informed defaults (k ≈ max(2, |R|/4), T calibrated on one small instance) before any tuning.  The digests that recommend this architecture — [[Scheduling_Heuristics]] (IG pseudocode is complete), [[Variable_Neighborhood_Descent]] (B-VND is empirically best quality/time), [[Iterated_Local_Search]] (ILS is state-of-the-art on SMTWTP and flow-shop problems sharing paper #2's objective structure) — are all High-priority and cross-validate each other.

The trade-off against the candidates not picked: Candidate D (GRASP+LB) is cheaper to code but depends on the MILP solve time staying tractable and does not add a new algorithmic contribution (it is the existing solver with a neighbourhood constraint).  Candidate B (GRASP+VND+PR) is richer but is strictly an extension of Candidate A with more moving parts; it should be built incrementally on top of A, not instead of it.  Candidate C (BRKGA) has the highest potential on large instances but the decoder engineering risk — the Mode-A/B/C repair must be provably correct — means it should only be attempted after the incremental move evaluation logic from Candidate A has been fully debugged (that logic is shared with the decoder).

The recommended development sequence is therefore: A → A+B (add reactive GRASP construction and path relinking) → A+C (repurpose the sweep as a BRKGA decoder) → D (bolt LB onto the working model as a polishing step).

---

## Open questions

1. **Timing granularity of the inner sweep.** The earliest-feasible-start sweep is O(|R| per position × number of jobs per aircraft) but its quality depends on whether it also minimises movement count or only makespan.  With W^S=10 dominant, a sweep that minimises movements (not just completion time) may be needed; this is non-trivial and could require a single-position dynamic program.

2. **Mode-B gap constraint (μ) interaction with IG.** After destruction and reconstruction, the reconstruction greedy may insert aircraft such that Mode-B access instants no longer satisfy the μ requirement.  It is unclear whether the earliest-feasible-start sweep corrects this automatically or whether a separate feasibility repair pass is needed.

3. **Instance size range.** The benchmark currently has instances with |R|=5, |P|=5.  The synthesis assumes |R| up to ~20.  For |R| ≤ 5, SA Metropolis (Candidate A) may behave poorly (too few local optima to escape); strict-improvement acceptance may be better for small instances.

4. **MILP model structure for LB (Candidate D).** The existing `milp_baseline` model must expose binary `x_{r,p}` position-assignment variables explicitly for the LB constraint to be written.  If positions are encoded differently (e.g., as integer variables or via big-M time-window constraints), the Hamming distance formulation needs to be adapted.

5. **Reactive α convergence speed.** Both the Prais-Ribeiro formula ([[GRASP]]) and the Delorme formula ([[Adaptive_and_Multi-level_Metaheuristics]]) require a warm-up phase of at least 5–10 iterations per α value before probabilities stabilise.  For small instances where the total budget is 50–100 iterations, this warm-up may consume most of the budget; a fixed α = 0.3 may outperform reactive GRASP in that regime.

---

## Archived (previous synthesis)

*(No previous synthesis — first run.)*
