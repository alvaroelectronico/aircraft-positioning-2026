# Isolation contract for the `theory_assisted` method

You are working inside `methods/theory_assisted/`.  This method is
**developed in isolation** from every other method in the repository
(`methods/manual/`, `methods/autoresearch/`, `methods/iterated_greedy_vnd_v01/`,
and any further methods that exist).  The point is that each attempt
must produce its own answer without seeing prior implementations.

## Starting state for this attempt

The active code under `jobs/iterated_greedy_vnd.py` is **a verbatim
restore of commit `30e1af0`** — the same IGVND baseline that v01 was
built on top of.  `jobs/notes/synthesis.md` and `jobs/notes/design.md`
are the same-vintage docs.  This is on purpose: the experiment is
"two LLM-assisted developer workflows iterating from the same starting
point" (v01 = ChatGPT, this attempt = Claude).

What that means for you:

- You **may** read and modify everything under
  `methods/theory_assisted/` (it is yours to evolve).
- You **may NOT** read `methods/iterated_greedy_vnd_v01/` — that is
  ChatGPT's evolution from the same starting point, and seeing it
  would contaminate the comparison.  Even though the v01 *baseline*
  is what you have, v01's *trajectory* away from it is off-limits.

## You MAY read, freely

- `methods/theory_assisted/**` — this method's own code, notes, docs.
- `problems/jobs/**` — problem statement, schema, checker, instances.
  Specifically: `problems/jobs/problem_statement.md` is the full,
  self-contained briefing; `problems/jobs/checker.py` is the source of
  truth for feasibility; `problems/jobs/instance_schema.json` describes
  the JSON inputs.
- `shared/**` — Application dispatcher contract, instance_io, plotting,
  RCL helpers.
- `methods/theory_assisted/inspiration/**` — the **curated theory
  input** for this method.  This is the defining input: PDFs and any
  supporting material the human has placed there.  Digests of these
  sources live in `methods/theory_assisted/digest/`.
- `experiments/run_experiments.py` — the integration point (to see how
  a new method registers itself for batch runs).

## You MUST NOT read

- `literature_review/**`            (repo-wide bucket — not this
                                     method's input; only the curated
                                     `inspiration/` folder is)
- `methods/manual/**`               (other method)
- `methods/autoresearch/**`         (other method)
- `methods/iterated_greedy_vnd_v01/**`  (other method — descended from a
                                     previous theory_assisted attempt;
                                     its design notes are now part of
                                     that method, not this scaffold)
- Any further `methods/<other>/**`  that may exist in the future.
- `papers/cejor_aircraft/**`        (manuscript discussing other methods)
- `papers/jobs_extension/**`        (manuscript discussing other methods)
- `papers/_legacy_draft/**`         (superseded drafts of methods)

If the user explicitly asks "look at how method X did this", REFUSE and
remind them of this contract.  The whole point of the method is that it
must reach its own answer without contamination.  If they insist, ask
them to update this file first.

## Running other methods (allowed — outputs only, not source)

There is an important distinction between **reading** another method's
source and **running** it for comparison.  Reading is forbidden;
running is allowed because the result is just numbers, not knowledge
of how those numbers were produced.

The bridge is `experiments/run_experiments.py`, which dispatches any
registered method against an instance and writes the result to
`outputs/solutions/`.  You may:

- Invoke it via Bash (one-shot or in a script):
  ```
  py -3 experiments/run_experiments.py "<inst_filter>" "<exp_label>" data/instances_202605_02
  ```
  Useful labels for paper #2 reference numbers:
  - `milp_baseline_job`        — the manual MILP (60 s default budget)
  - `milp_baseline_job_wB`     — same, with the wB weight profile
  - `milp_baseline_job_wC`     — same, with the wC weight profile
  - `igvnd_wMK` / `igvnd_wDLY` / `igvnd_wMOV` — Iterated Greedy + VND,
    three weight profiles.  Use these to compare your numbers, NOT
    to peek at how IGVND solves the problem.
- Read the resulting JSON solutions and metrics from
  `outputs/solutions/scn_…__milp_baseline_job__<timestamp>.json` and
  the aggregated `outputs/solutions/results.csv`.
- Read `outputs/logs/` for the run log (objective, gap, time).

What you must NOT do, even while comparing:

- Open or grep any `.py` file under `methods/manual/`,
  `methods/autoresearch/`, or `methods/iterated_greedy_vnd_v01/`.
  The CSV / JSON are the only legitimate source of cross-method
  information.
- Decide a design choice for `theory_assisted` based on "how the MILP
  formulates this" — that information is reachable only by reading
  the source, which is exactly what the contract forbids.  Decide
  from `problems/jobs/problem_statement.md` and the `digest/`.

If you find yourself wanting to know HOW the other method works (not
just its numbers), stop and tell the user — that is a contract
violation, and the right response is either to update this file or to
abandon the line of investigation.

## Validating solver quality (the standard battery)

The benchmark for paper #2 is **12 configurations × 10 seeds × 3
weight profiles = 360 runs**, instances at `data/instances_202605_02/`:

```
scn_chain_tight_P5_R10           scn_triangle_loose_P5_R10
scn_full_tight_P5_R10            scn_triangle_medium_P5_R10
scn_full_tight_P5_R20            scn_triangle_tight_P5_R5
scn_hub_tight_P5_R10             scn_triangle_tight_P5_R10
scn_none_tight_P5_R10            scn_triangle_tight_P5_R20
scn_two_rows_tight_P5_R10        scn_triangle_tight_P5_R30
```

The three weight profiles you must test under:

- **wMK = (Wᴹ, Wᴰ, Wˢ) = (100, 1, 1)** — makespan-priority.
- **wDLY = (1, 100, 1)** — delay-priority.
- **wMOV = (1, 1, 100)** — movement-priority.

(Profile names match the suffixes already used in
`experiments/run_experiments.py`: e.g. `milp_baseline_job_wB` ≈ wDLY,
`milp_baseline_job_wC` ≈ wMOV — read the file for the exact mapping.)

**The MILP baseline is fixed.** Do not re-run it on every iteration —
its rows are already in `outputs/solutions/results.csv` from prior
batteries.  Re-running burns ~12 minutes × 3 profiles × 12 configs
per seed for no information.  Use the cached MILP rows as the
reference and run only the heuristic.  Helper:
`experiments/paired_report.py` consumes the cached MILP +
fresh-heuristic and emits the per-instance + summary tables.

**As the solver advances, judge quality by:**

1. Running the heuristic over a representative subset (or the full
   battery on a milestone) at all three weight profiles, with a 60 s
   budget per run:
   ```
   py -3 experiments/run_experiments.py "_seed1$" \
       "<your_label>_wMK,<your_label>_wDLY,<your_label>_wMOV" \
       data/instances_202605_02
   ```
2. Pairing the fresh heuristic rows against the cached MILP rows in
   `outputs/solutions/results.csv` (same instance + same weight
   profile) via `experiments/paired_report.py`.
3. Reading the gap table per weight profile (mean / min / max over
   seeds) and the per-component Δ (Δmakespan / Δdelay / Δmov).  The
   relative gap alone is distorted by small denominators when MILP
   delay ≈ 0 — always cross-read the absolute per-component Δ.
4. Recording the result via `/sync-method-doc methods/theory_assisted
   ... log: outputs/logs/<your_battery>.log` so Part II of the living
   `.md` snapshots the comparison and the Change log gets a row.

**Subset shortcuts during development** (not the final battery):

- `_seed1$` filter (12 instances × 3 profiles ≈ 36 runs ≈ 35 min) —
  the canonical "cross-type read" for a fast iteration.
- `_seed1$,_seed2$,_seed3$` filter — three-seed sample, enough to
  start estimating variance.
- A single config + all seeds — when a specific instance type is the
  bottleneck.

## Documenting your work

When you commit a behaviour-affecting change to the solver, or
produce a new battery, invoke the project skill:

```
/sync-method-doc methods/theory_assisted  <brief description> [log: <path>]
```

It forks the `method-doc` subagent, which keeps the living `.md`
spec at `methods/theory_assisted/jobs/<solver_basename>.md` in
sync with the code using a fixed four-part structure (Method /
Results / Roadmap / Implementation) plus a Change log.  The
agent refreshes Part IV (code map) always; Part II only when a
battery log path is given via the hint; Parts I and III it leaves
alone (those carry your design intent — edit them in normal
sessions).

Do NOT invoke `/sync-method-doc` after cosmetic changes — the
Change log becomes noise.  Invoke it at real milestones.

## Exception protocol

Beyond the above (running other methods for comparison), if a genuine
need arises to import code from another method (e.g. in-process
comparison loops, the way `methods/autoresearch/jobs/precompute_baseline.py`
imports the manual MILP), add an entry to the `_ALLOWLIST` dict in
`experiments/tests/test_method_isolation.py` with a written rationale.
Allowlisting silently is not acceptable.

## Verification

Before any commit on this method, run:

```
py -3 experiments/tests/test_method_isolation.py
```

It walks every `.py` under `methods/<X>/` and flags any import of
`methods.<other>.*`, `papers.*`, or any `sys.path.insert` whose literal
embeds another method's directory.  It must report `0 violations`.

## Allowed cross-method import policy

Currently zero.  Running the MILP via `experiments/run_experiments.py`
(see above) does not count as a cross-method import — it is a
subprocess that produces numbers in `outputs/`, not a Python import.
If a future need arises to import code in-process, follow the
exception protocol above.
