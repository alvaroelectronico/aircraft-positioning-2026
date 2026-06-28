# Isolation contract for the `theory_assisted` method

> **Contract update — 2026-06-28 (read isolation LIFTED by the user).**
> The user has explicitly granted read access to **the entire project**:
> all code under `methods/<X>/`, all manuscripts under `papers/`, and
> every other file. The original read-isolation rule below is kept as
> **advisory history**, not a hard ban, because it documents an
> experimental design that still matters (see the warning under "Your
> task"). Two things are unchanged and remain in force: (1) the solver's
> **import** independence — `theory_assisted` code must not `import`
> another method's source (the `test_method_isolation.py` gate +
> `_ALLOWLIST` protocol below still apply); (2) the **cached-MILP rule** —
> do not re-run the MILP each iteration. Use the new read freedom with
> judgement: reading another in-progress attempt before finishing your
> own can still contaminate the replication experiment, even though it is
> no longer forbidden.

You are working inside `methods/theory_assisted/`.

**In one sentence (post-update):** you can now read **everything in the
repository**. Historically this method was developed in read-isolation
from every other method (`methods/manual/`, `methods/autoresearch/`,
`methods/iterated_greedy_vnd_v01/`, `methods/iterated_greedy_vnd_v02/`,
`methods/brkga_v02/`, …) so each attempt produced its own answer without
seeing prior implementations. That rationale is preserved below as
context; the hard read-bans are lifted.

## Starting state for this attempt

This is a **clean scaffold** for a new attempt at paper #2.  Previous
attempts have graduated to their own isolated method directories:

- `methods/iterated_greedy_vnd_v01/` — ChatGPT-assisted, Candidate A.
- `methods/iterated_greedy_vnd_v02/` — Claude-assisted, Candidate A
  (same baseline as v01).
- `methods/brkga_v02/` — Claude-assisted, Candidate C (BRKGA with
  mixed-chromosome decoder).

## Your task: a SECOND independent attempt at Candidate C (BRKGA)

> **Read [`starting_guidelines.md`](starting_guidelines.md) right after
> this file.**  It contains the user's per-attempt schema (file
> layout, chromosome shape, decoder steps, BRKGA hyperparameters,
> profile-gating, what to leave out of the MVP) plus the fixed
> workflow and a recap of the non-negotiable rules.  Confirm the
> schema with the user before writing any code.

You are building **Candidate C — BRKGA with mixed-chromosome decoder
+ warm-start** again, from scratch, with full isolation from the first
Claude-assisted attempt at the same candidate (`methods/brkga_v02/`).

The experimental purpose is **replication**: how much do two Claude-
assisted attempts at the same algorithm, from the same digests, on
the same scaffold, *diverge* in implementation choices and final
quality?  For the comparison to be meaningful you should **avoid**
reading `methods/brkga_v02/` (`brkga.py`, `brkga_engine.py`,
`decoder.py`, `brkga.md`, `design.md`, `PROVENANCE.md`, Change log)
**until you have committed your own implementation choices** — they
reveal choices that would contaminate the replication.  Since the
2026-06-28 update this is **advisory, not a hard ban**: you *may* read
it now, but doing so before finishing your own attempt weakens the
experiment, so prefer not to unless the user asks for a deliberate
comparison.

You are NOT building A, B, or D.  If you find the BRKGA shape doesn't
appeal, tell the user — do not silently switch to a different
candidate.  Switching the algorithm voids the replication experiment.

This time you start fresh:

- `jobs/theory_assisted_job.py` is a **stub** with the `Application`
  contract wired and `solve()` raising `NotImplementedError`.  Replace
  its body with your BRKGA implementation, or split into multiple
  modules.  When the method matures and graduates, the directory
  will likely be named `methods/brkga_v03/` (parallel to v02 ChatGPT
  vs v02 Claude on IG+VND) — but the naming is the user's call at
  graduation time.
- `jobs/notes/synthesis.md` is the **literature synthesis from prior
  attempts** (same digests, same 4 candidates A/B/C/D).  Read it.
  In particular read its **Candidate C section** — that is your
  guidance.  The synthesis describes Candidate C as "BRKGA with a
  mixed-chromosome decoder (indicator keys for position assignment
  + permutation keys for in-position job sequencing)" — that is the
  algorithm family you are building.
- `jobs/notes/` is otherwise empty — fill it with your own design
  notes (`design.md`) and experiments log as you iterate.  Your
  design.md will diverge from brkga_v02's design.md in the choices
  you make — that divergence is the experimental data point.
- `digest/` and `inspiration/` carry the **same reusable theory base**
  the first BRKGA attempt had (10 PDFs + 10 digests).  Read them
  freely; they are the legitimate shared input.

Once you have a working solver, register it in
`experiments/run_experiments.py` with **fresh labels** distinct from
brkga_v02's `ta_brkga_*`.  Use something like `ta2_brkga_*` or
`brkga2_*` so the two attempts' results are paired in
`outputs/solutions/results.csv` and the comparison stays explicit.

What that means for you:

- You **may** read and modify everything under
  `methods/theory_assisted/` (it is yours to evolve).
- You **may** now read any other `methods/<X>/` and `papers/` too (the
  2026-06-28 update). Treat the replication-experiment warning above as
  guidance: prefer not to read another in-progress attempt's source
  before committing your own choices, but it is no longer forbidden.

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

## Read access (project-wide since 2026-06-28)

Read access is **no longer restricted**. You may `Read`, `Grep`, and
`Glob` anywhere in the repository, including:

- `methods/manual/**`, `methods/autoresearch/**`,
  `methods/iterated_greedy_vnd_v01/**`, `methods/iterated_greedy_vnd_v02/**`,
  `methods/brkga_v02/**`, and any further `methods/<other>/**`;
- `papers/cejor_aircraft/**`, `papers/jobs_extension/**`,
  `papers/_legacy_draft/**`;
- `literature_review/**`, `problems/aircraft/**`.

**Advisory (not a ban), kept from the original contract:**

- *Replication experiment* — reading another in-progress attempt's
  source (notably `methods/brkga_v02/`) before you have committed your
  own implementation choices still weakens the "two independent Claude
  attempts" comparison. Prefer not to, unless the user asks for a
  deliberate comparison.
- *Design provenance* — when you make a design choice for
  `theory_assisted`, base it on `problems/jobs/problem_statement.md` and
  the `digest/`, not on "how the MILP/other method formulates this".
  Reading is now allowed; copying another method's design wholesale would
  defeat the purpose of an independent attempt.

If you do read another method or a manuscript for a specific task (e.g.
tracing which `.log` a paper was built from), say so plainly in your
reply so the provenance of your reasoning is clear.

## Running other methods (for comparison numbers)

Running another method for comparison remains the cleanest way to get
its numbers without entangling your work with its source. (Reading that
source is now permitted too — see the section above — but you rarely
need to: the `outputs/` rows are the canonical cross-method numbers.)

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

Good practice while comparing (no longer hard bans):

- The CSV / JSON under `outputs/` are the canonical source of
  cross-method numbers — prefer them over re-deriving figures from
  another method's source.
- Base `theory_assisted` design choices on
  `problems/jobs/problem_statement.md` and the `digest/`, not on copying
  how another method formulates the problem. Reading is allowed; an
  independent attempt is still the goal.

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

## Documenting your work — non-optional

The living spec `.md` for this method **must always be in sync** with
the code and reference the most recent battery log.  Two hard rules:

1. **The `.md` filename equals the solver `.py` filename.**  If your
   solver ends up at `methods/theory_assisted/jobs/<name>.py`, its
   doc is at `methods/theory_assisted/jobs/<name>.md`.  Same basename,
   same directory.  If you rename the `.py`, rename the `.md` in the
   same commit.
2. **The latest battery log filename appears in the `.md`** in two
   places: the **Status** callout near the top of the file, and the
   **Log** row of Part II's Experimental setup table.  When you
   refresh Part II, you update BOTH; when you read the doc, the log
   reference tells you which battery the current numbers came from.

The skill that maintains this is `/sync-method-doc`.  **Invoke it:**

- **After every commit that changes the solver's behaviour**
  (algorithmic change, new neighbourhood, new config knob, …):
  ```
  /sync-method-doc methods/theory_assisted  <brief description>
  ```
  Refreshes Part IV from the new code, appends a Change log row,
  leaves Part II untouched (the numbers it cites are still the most
  recent measured).

- **After every battery run**, with the log path in the hint:
  ```
  /sync-method-doc methods/theory_assisted  <brief description>  log: outputs/logs/<file>.log
  ```
  Refreshes Part II's gap tables + Δ tables, updates the Status
  callout AND Part II's Log row to cite the new log, appends a
  Change log row.

If you only want a refresh without a change log entry (e.g. you just
re-ran the same code on a longer battery), invoke with `log: <path>`
only (no free-form description); the agent will refresh Part II
without appending a Change log row.

Do not skip the skill after cosmetic changes (typos, comments) —
those don't need a Change log row, but you also don't need to invoke
the skill at all for them.  The trigger is "did behaviour change OR
did I run a battery".

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
