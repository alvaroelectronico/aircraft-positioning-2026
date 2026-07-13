# `iterated_greedy_vnd_v01` — the ACTIVE method under improvement

You are working inside `methods/iterated_greedy_vnd_v01/`.  Since the
repo refocus (2026-07-13) this is **the** method the repository exists
to improve: the IG+VND heuristic for the job-level problem (paper #2),
measured against the fixed MILP baseline
(`methods/manual/jobs/milp_jobs_v2_solver.py`, labels `milp_job_*`).

> **History.** This method originated as the "v01 attempt" of a
> multi-method comparison built with ChatGPT assistance (see
> [`PROVENANCE.md`](PROVENANCE.md)) and was frozen while sister attempts
> (v02, brkga_v02, theory_assisted) were explored.  That era is over:
> the freeze is lifted, the sister attempts are retired (inert, pending
> deletion; preserved on `archive/pre-restructure-20260713`), and
> behaviour-changing work on this method is the repo's main activity.

## Read policy

Project-wide read access (user-authorised 2026-06-28).  The retired
method directories (`iterated_greedy_vnd_v02`, `brkga_v02`,
`theory_assisted`, `autoresearch`) may be read for reference but are
dead code — do not resurrect or import from them.

## Import policy (still enforced)

The solver imports nothing from other methods (only stdlib + the lazy
`problems/jobs/checker` import).  Before any commit here:

```
py -3 experiments/tests/test_method_isolation.py     # must report 0 violations
```

New cross-method imports require an `_ALLOWLIST` entry in that test
with a written rationale.

## Workflow for behaviour changes (the improvement loop)

Every improvement attempt follows the journal discipline in
[`IMPROVEMENT_LOG.md`](IMPROVEMENT_LOG.md):

1. Branch `exp/<slug>` off `dev`; open a journal entry with the
   **hypothesis before coding**.
2. Measure both arms FRESH (baseline vs candidate) against the
   **cached MILP** rows in `outputs/solutions/results.csv` — never
   re-run the MILP, and never trust cached heuristic rows (they go
   stale; see Step 0 of the 2026-07 campaign).
3. Apply the noise-floor check (per-stratum; see the journal) — a delta
   below the run-to-run spread is NEUTRAL, not an improvement.
4. KEPT → merge `--no-ff` into `main`, tag `igvnd-v01-<milestone>`,
   run `/sync-method-doc`.  DROPPED → keep the `exp/` branch and add a
   Change-log "attempted & DROPPED" row.

**Simplicity is an acceptance criterion** (user, 2026-07-13): prefer
changes that REMOVE parts (knobs, rules, phases) over ones that add
them; a new mechanism must pay for itself by retiring at least as much
machinery as it introduces.

## The battery

Composition, cached-MILP rule, subset shortcuts and result-reading
conventions live in [`experiments/BATTERY.md`](../../experiments/BATTERY.md).
Standard run:

```
py -3 experiments/run_experiments.py "<inst_filter>" \
    "igvnd_wMK,igvnd_wDLY,igvnd_wMOV" data/instances_202605_02
```

## Documentation layers (keep all three in sync)

- [`jobs/iterated_greedy_vnd.md`](jobs/iterated_greedy_vnd.md) — living
  spec (Part I method / II results / III roadmap / IV code + Change
  log).  Sync after every behaviour change and every battery via
  `/sync-method-doc`.
- [`IMPROVEMENT_LOG.md`](IMPROVEMENT_LOG.md) — attempt journal
  (hypothesis → verdict), including dead ends.
- `jobs/design.md` + `jobs/synthesis.md` — design rationale and the
  literature synthesis that seeded the method (historical, stable).
