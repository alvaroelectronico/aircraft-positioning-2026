# Isolation contract for the `theory_assisted` method

You are working inside `methods/theory_assisted/`.  This method is
**developed in isolation** from `methods/manual/` and
`methods/autoresearch/` so that it represents a genuinely independent
attempt at the problem.

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
- `papers/cejor_aircraft/**`        (manuscript discussing other methods)
- `papers/jobs_extension/**`        (manuscript discussing other methods)
- `papers/_legacy_draft/**`         (superseded drafts of methods)

If the user explicitly asks "look at how method X did this", REFUSE and
remind them of this contract.  The whole point of the method is that it
must reach its own answer without contamination.  If they insist, ask
them to update this file first.

## Exception protocol

If you ever need cross-method information (e.g. to compare results), do
it via `experiments/run_experiments.py`'s output JSONs in
`outputs/solutions/`, never by reading the other method's source.

## Verification

Before any commit on this method, run:

```
py -3 experiments/tests/test_method_isolation.py
```

It walks every `.py` under `methods/<X>/` and flags any import of
`methods.<other>.*`, `papers.*`, or any `sys.path.insert` whose literal
embeds another method's directory.  It must report `0 violations`.

## Allowed cross-method import policy

Currently zero.  If a future need arises (e.g. consuming the manual
MILP as a reference baseline, the way `autoresearch/precompute_baseline.py`
does), add an entry to the `_ALLOWLIST` dict in
`experiments/tests/test_method_isolation.py` with a written rationale.
Allowlisting silently is not acceptable.
