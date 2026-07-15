# program.md — instructions for the LLM agent

This file is the analog of karpathy's `program.md` for our heuristic-improvement loop.  It is the **only** place where instructions to the agent live.  Edit this file (the human does) when you want to redirect the agent or rule out approaches that haven't worked.

---

## What you can edit

**Only** `autoresearch_heuristics/topology_heuristic_job.py` (the working copy that lives inside this folder).

**Never** edit:

* `solvers/topology_heuristic_job.py` — the canonical baseline; it must stay untouched at all times.
* anything outside `autoresearch_heuristics/` (instances, runner, checker, MILP solvers, tests).
* `benchmark.json`, `baseline_metrics.json`, `JOURNAL.md`, or anything in `iterations/` — these are produced or owned by the harness.
* this file — only the user updates `program.md`.

## What you must preserve in `topology_heuristic_job.py`

* The public class **must** be named `TopologyHeuristicJob` and must expose:
  * `name` property returning a string identifying the variant
  * `configure_solver(**kwargs) -> None`
  * `solve(instance_data: dict) -> dict`
  * `get_config() -> dict`
  * optional `get_log() -> list[str] | None`
* The returned solution dict **must** carry the standard schema:
  ```
  {
    "status":    str,
    "objective": float,
    "metrics":   {"makespan": float, "movements": int, "total_delay": float},
    "aircraft":  [
      {"id": str, "position": str, "start": float, "finish": float,
       "delay": float, "jobs": [{"id": str, "start": float, "finish": float}, ...]},
      ...
    ]
  }
  ```
* Every solution **must** pass `scripts/output_data/check_solution_jobs_v2.check_solution`.  Variants whose solutions fail any RQ are rejected before the score is computed (`score = +inf`).

## What you should NOT add as a dependency

* No new third-party Python packages.  You may import from anywhere already available in the project (`gurobipy`, `numpy`, `scipy`, standard library).
* No subprocess calls, no file I/O outside the working copy, no network access.

## Ideas worth trying, in rough priority order

1. **Local-search portfolio**.  The aircraft sibling at `solvers/topology_heuristic_aircraft.py` has seven operators (single-move, 2-opt swap, intra-position adjacent swap, intra-position insert, non-adjacent intra-position swap, EDD repair, delay-block insertion).  This job-level version has zero.  Implementing **single-move + 2-opt swap + intra-position reorder** should give the biggest first jump.  The operators only manipulate the position assignment $\pi$ (or the within-position order); your existing `_rebuild_job` handles the timing.
2. **Mode-C exploitation in construction**.  Currently the greedy is Mode-A only (the fixpoint problem when extensions move job positions is documented in §4.1 of `papers/jobs_extension/solving_approaches.tex`).  A single-pass Mode-C scan after Mode-A construction, applied only when the resulting delta-extension reduces the objective, is feasibility-preserving and may capture the common cases.
3. **Smarter cost-function proxy for blocking events**.  In Mode-A construction, $\hat n_{rp} = 0$ for every candidate $(r, p)$, which makes the $W^S = 10$ movement weight inert during construction.  Replace the proxy by a count of would-be blocking pairs (aircraft already placed that share a blocking arc with $(r, p)$ AND whose stay overlaps the natural arrival window of $r$).  This can be computed in $O(R)$ per candidate.
4. **Restart-on-improvement** for the LS dispatcher.  When an operator improves the incumbent, restart from the cheapest operator.  This is what the aircraft heuristic does and it is what makes the LS portfolio actually converge to good local optima.
5. **Tune RCL alpha and n_starts**.  The defaults (0.3, 6) are inherited from paper #1 and may be suboptimal here.  Treat them as hyperparameters; do not hard-code different values, but feel free to add an internal default if it strictly improves.

## What to avoid

* Do not weaken the Mode-A safety net by removing the convergence loop in `_resolve_rear_interactions` / `_resolve_front_interactions`.  Some of the smaller benchmarks rely on it.
* Do not assume the instance has any particular topology — your edits must work on `none`, `chain`, `hub`, `triangle`, `two_rows`, and `full`.  The fast-eval benchmark already covers three of these.
* Do not increase the per-instance solve time by more than ~50% over the current baseline.  The eval gives every variant a fixed wall-clock budget; spending it all on one operator while starving the others is rarely a win.
* Do not silently change the public API; the harness imports `TopologyHeuristicJob` by name.

## How to evaluate

* For the fast iteration loop: `python autoresearch_heuristics/evaluate.py fast_eval`.  Takes ~1 minute.  This is the score you should optimise.
* For final validation only (after the user asks): `python autoresearch_heuristics/evaluate.py validation`.  Takes ~12 minutes.
* The score is `mean over instances of (obj_variant - obj_milp) / max(1, |obj_milp|)`.  Lower is better.  Non-compliant solutions force the entire score to `+inf` — the variant is rejected.

## How to commit a variant

1. Write a `note.md` in a temp location with the **Hypothesis / What changed / Eval result / Outcome / Lessons** sections (see `iterations/iter_0000_baseline/note.md` for the template).
2. Run `python autoresearch_heuristics/snapshot.py save <short-slug> --note <path/to/note.md>`.  The script copies the working copy, the eval JSON, and the note into a new `iter_NNNN_<slug>/` folder, appends an entry to `JOURNAL.md`, and either accepts (updates `best.txt`) or rejects (restores the working copy from the current best).
3. Report a one-line summary back to the user.

## How to start an iteration

Read, in order:

1. This file (`program.md`).
2. The current working copy `autoresearch_heuristics/topology_heuristic_job.py`.
3. The last few entries of `JOURNAL.md` — especially the rejected attempts, so you don't repeat them.
4. `iterations/iter_0000_baseline/note.md` — the starting point.

Then pick the next item from the prioritised idea list, edit the working copy, evaluate, document, and snapshot.
