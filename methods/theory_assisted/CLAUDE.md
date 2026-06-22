# Isolation contract for the `theory_assisted` method

You are working inside `methods/theory_assisted/`.

**In one sentence:** you can read **everything in this method's own
folder, the instances, the problem statement, and the supporting
infrastructure (shared/, experiments/, outputs/)**.  You cannot read
**anything that reveals how another solving method solved this
problem** — that means **no file** under any other `methods/<X>/`
(neither `.py` nor `.md` nor anything else), no manuscript under
`papers/`, and no superseded draft.

This method is **developed in isolation** from every other method in
the repository (`methods/manual/`, `methods/autoresearch/`,
`methods/iterated_greedy_vnd_v01/`, `methods/iterated_greedy_vnd_v02/`,
`methods/brkga_v02/`, and any further methods that exist).  The point
is that each attempt must produce its own answer without seeing prior
implementations.

## Starting state for this attempt

This is a **clean scaffold** for a new attempt at paper #2.  Previous
attempts have graduated to their own isolated method directories:

- `methods/iterated_greedy_vnd_v01/` — ChatGPT-assisted, Candidate A.
- `methods/iterated_greedy_vnd_v02/` — Claude-assisted, Candidate A
  (same baseline as v01).
- `methods/brkga_v02/` — Claude-assisted, **Candidate C** (BRKGA with
  mixed-chromosome decoder).

This time you start fresh:

- `jobs/theory_assisted_job.py` is a **stub** with the `Application`
  contract wired and `solve()` raising `NotImplementedError`.  Replace
  its body (or rename it / split it into multiple modules) with your
  approach.
- `jobs/notes/synthesis.md` is the **literature synthesis from prior
  attempts** (same digests, same 4 candidates A/B/C/D).  Read it.
  It is the menu of algorithmic approaches that the curated theory
  in `digest/` supports.
- `jobs/notes/` is otherwise empty — fill it with your own design
  notes (`design.md`) and experiments log as you iterate.
- `digest/` and `inspiration/` carry the **same reusable theory base**
  prior attempts had (10 PDFs + 10 digests).  Add more if you want
  to widen the input.

**Candidates A and C are exhausted.**  v01 + iterated_greedy_vnd_v02
implemented Candidate A (IG+VND); brkga_v02 implemented Candidate C
(BRKGA).  All three are off-limits to you (see "You MUST NOT read"
below), but the *fact* that A and C have been built is part of your
brief: **pick a different candidate**.

Your starting choice is among:

- **Candidate B — GRASP + VND with reactive α + elite-pool path relinking.**
- **Candidate D — Matheuristic: GRASP construction + Local Branching
  refinement** (uses the manual MILP as a subroutine; would need an
  allowlist entry in `experiments/tests/test_method_isolation.py`,
  see the Exception protocol below).

Read `jobs/notes/synthesis.md` for each candidate's skeleton,
supporting digests, effort estimate and risks.  If none feels right,
you may also re-run `/synthesize-theory` with a focus hint to bias
the candidate list (e.g. `/synthesize-theory  hyper-heuristic`), or
edit the digests first to expand the theory base.

What that means for you:

- You **may** read and modify everything under
  `methods/theory_assisted/` (it is yours to evolve).
- You **may NOT** read any other `methods/<X>/` — including the v01
  and v02 trajectories.  Their evolutions from earlier baselines are
  off-limits even though the underlying theory (in `digest/`) is
  shared.

## You MAY read, freely

- `methods/theory_assisted/**` — everything in this method's own
  folder: your code, your notes (design.md, synthesis.md, …), your
  `inspiration/` (curated PDFs) and your `digest/` (their distilled
  notes).  Edit freely.
- `data/instances_202605_02/**` — the **instance JSONs** for paper #2.
  120 files (12 configurations × 10 seeds).  Read directly via
  `shared/instance_io.load_json`, or implicitly through
  `experiments/run_experiments.py`.
- `problems/jobs/**` — the **problem statement** and operational
  contract:
  - `problems/jobs/problem_statement.md` — the self-contained briefing.
  - `problems/jobs/checker.py` — the source of truth for feasibility.
  - `problems/jobs/instance_schema.json` — the JSON instance schema.
- `shared/**` — supporting infrastructure:
  `shared/application.py` (the Application dispatcher / solver
  contract), `shared/instance_io.py` (loader),
  `shared/rcl.py` (RCL helpers), `shared/plotting.py`.
- `experiments/**` — orchestration and reporting tooling:
  `experiments/run_experiments.py` (the batch runner where you
  register your method),
  [`experiments/BATTERY.md`](../../experiments/BATTERY.md) (standard
  battery convention),
  `experiments/paired_report.py` (heuristic-vs-cached-MILP tables),
  `experiments/ablation_subset.py`, etc.  These do not reveal another
  method's source — they wrap and consume them.
- `outputs/solutions/**`, `outputs/logs/**` — **read-only** results
  and logs of past runs across all methods.  Use them to compare
  numbers; never as a back-channel to other methods' internals.

## You MUST NOT read

- `literature_review/**`            (repo-wide bucket — not this
                                     method's input; only the curated
                                     `inspiration/` folder is)
- `methods/manual/**`               (other method)
- `methods/autoresearch/**`         (other method)
- `methods/iterated_greedy_vnd_v01/**`  (other method — ChatGPT-assisted
                                     descendent of a previous
                                     theory_assisted attempt;
                                     its design notes are now part of
                                     that method, not this scaffold)
- `methods/iterated_greedy_vnd_v02/**`  (other method — Claude-assisted
                                     descendent of a previous
                                     theory_assisted attempt; same
                                     reasoning)
- `methods/brkga_v02/**`            (other method — Claude-assisted
                                     BRKGA descendent of a previous
                                     theory_assisted attempt;
                                     Candidate C of the synthesis)
- Any further `methods/<other>/**`  that may exist in the future.
- `papers/cejor_aircraft/**`        (manuscript discussing other methods)
- `papers/jobs_extension/**`        (manuscript discussing other methods)
- `papers/_legacy_draft/**`         (superseded drafts of methods)
- `problems/aircraft/**`            (paper #1 — a different problem,
                                     out of scope for this method)

**"MUST NOT read" applies to every file type, not just `.py`.**  An
`.md`, a `.json` config, a docstring excerpt, a commit message body
— anything under `methods/<other>/` reveals how that method was
built.  If you find yourself running `Read`, `Grep`, or `Glob`
against any path in the forbidden list, stop.

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
  - `igvnd_wMK` / `igvnd_wDLY` / `igvnd_wMOV` — v01 IGVND (ChatGPT-
    assisted), three weight profiles.  Use to compare your numbers,
    NOT to peek at the solver's source.
  - `ta_igvnd_wMK` / `ta_igvnd_wDLY` / `ta_igvnd_wMOV` — v02 IGVND
    (Claude-assisted), three weight profiles.  Same rule.
  - `ta_brkga_wMK` / `ta_brkga_wDLY` / `ta_brkga_wMOV` — brkga_v02
    (Claude-assisted, Candidate C), three weight profiles.  Same rule.
- Read the resulting JSON solutions and metrics from
  `outputs/solutions/scn_…__milp_baseline_job__<timestamp>.json` and
  the aggregated `outputs/solutions/results.csv`.
- Read `outputs/logs/` for the run log (objective, gap, time).

What you must NOT do, even while comparing:

- Open or grep **any file** (`.py`, `.md`, `.json`, anything) under
  `methods/manual/`, `methods/autoresearch/`,
  `methods/iterated_greedy_vnd_v01/`, `methods/iterated_greedy_vnd_v02/`,
  or `methods/brkga_v02/`.  The CSV / JSON under `outputs/` are the
  only legitimate source of cross-method information.
- Decide a design choice for `theory_assisted` based on "how the MILP
  formulates this" — that information is reachable only by reading
  the source, which is exactly what the contract forbids.  Decide
  from `problems/jobs/problem_statement.md` and the `digest/`.

If you find yourself wanting to know HOW the other method works (not
just its numbers), stop and tell the user — that is a contract
violation, and the right response is either to update this file or to
abandon the line of investigation.

## Validating solver quality (the standard battery)

The benchmark, weight profiles, cached-MILP rule, subset shortcuts,
and quality-judging procedure are all defined in
[`experiments/BATTERY.md`](../../experiments/BATTERY.md).  **Read it
in full** the first time you sit down to evaluate this method.

The two non-negotiables to keep in mind here:

1. **Three weight profiles** (`wMK`, `wDLY`, `wMOV`).  A method is
   not validated until it has been measured under all three — they
   stress different parts of the design.
2. **Cached MILP.**  The MILP rows for these instances live in
   `outputs/solutions/results.csv`; do NOT re-run the MILP every
   iteration.  Run only your heuristic and pair against the cached
   rows via `experiments/paired_report.py`.

After a milestone battery, record the result via:

```
/sync-method-doc methods/theory_assisted  <brief desc>  log: outputs/logs/<your_log>.log
```

so Part II of the living `.md` snapshots the new numbers and the
Change log gets a row.

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
