# `autoresearch_heuristics/` — autoresearch loop for `topology_heuristic_job`

A self-contained, karpathy/autoresearch-style improvement loop that proposes,
evaluates, and journals modifications to a job-level topology heuristic.
Everything related to the loop lives inside this folder; the canonical
[solvers/topology_heuristic_job.py](../solvers/topology_heuristic_job.py)
is **never** modified by the loop.

## Anatomy

| Path                        | Role                                                                                      |
| --------------------------- | ----------------------------------------------------------------------------------------- |
| `program.md`                | The instruction manual for the LLM agent — the only place where directives live.         |
| `topology_heuristic_job.py` | **Working copy** — the file the LLM agent edits every iteration.                          |
| `benchmark.json`            | Which instances, which time budgets, which weight profile.                                |
| `baseline_metrics.json`     | MILP-incumbent objectives over the benchmark, produced once by `precompute_baseline.py`.  |
| `precompute_baseline.py`    | One-time MILP run that populates `baseline_metrics.json`.                                 |
| `evaluate.py`               | The harness: `eval_variant(mode)` → JSON verdict with `score`, `n_compliant`, etc.        |
| `snapshot.py`               | save / restore / list / log — atomic accept-or-reject of an iteration.                    |
| `JOURNAL.md`                | Rolling log — one entry per iteration (accepted **and** rejected).                        |
| `iterations/iter_NNNN_*/`   | Frozen artifacts of each iteration: working-copy snapshot, eval JSON, agent's note.       |
| `best.txt`                  | One-line pointer to the current-best iteration folder.                                    |

## Metric

For every instance `i` in the eval set:

```
gap_i = (obj_variant_i - obj_milp_i) / max(1, |obj_milp_i|)
```

The aggregate `score` is `mean_i(gap_i)` if **every** variant solution is
compliant under `check_solution_jobs_v2.check_solution`; otherwise `score = +inf`
(the variant is rejected before aggregation).

Lower is better.  Acceptance is a strict improvement over the current best.

## One-time setup

```
# Seed the working copy from the canonical solver (already done once).
cp solvers/topology_heuristic_job.py autoresearch_heuristics/topology_heuristic_job.py

# Precompute the MILP reference values for fast_eval.
python autoresearch_heuristics/precompute_baseline.py fast_eval

# Optional: also precompute for the validation set (~12 minutes).
python autoresearch_heuristics/precompute_baseline.py validation

# Evaluate the seeded baseline + snapshot it as iter_0000_baseline.
python autoresearch_heuristics/evaluate.py fast_eval --write /tmp/eval_baseline.json
# write a baseline note.md, then:
python autoresearch_heuristics/snapshot.py save baseline \
    --eval /tmp/eval_baseline.json --note /tmp/note_baseline.md
```

## Per-iteration workflow (Claude Code)

The user types into Claude Code something like:

> Read `autoresearch_heuristics/program.md` and the current
> `autoresearch_heuristics/topology_heuristic_job.py`.  Propose the next
> improvement from the prioritised list, apply it to the working copy,
> evaluate it on `fast_eval`, write a `note.md`, and snapshot it.

Claude then:

1. Reads `program.md`, the working copy, and the last entries of `JOURNAL.md`
   (so it doesn't repeat a dead end).
2. Edits `autoresearch_heuristics/topology_heuristic_job.py` (and **only**
   that file).
3. Runs `python autoresearch_heuristics/evaluate.py fast_eval --write tmp_eval.json`.
4. Writes a `note.md` (Hypothesis / What changed / Eval result / Outcome / Lessons).
5. Calls `python autoresearch_heuristics/snapshot.py save <slug> --eval tmp_eval.json --note tmp_note.md`.
6. Reports a one-line summary back to the user.

`snapshot.py` handles the atomic accept/reject branch: on rejection it
restores the working copy from the current best.  On acceptance it updates
`best.txt`.  Either way it appends a journal entry.

## What the loop is allowed to touch

* **Editable**: `autoresearch_heuristics/topology_heuristic_job.py`.
* **Read-only (produced by the harness)**: `iterations/`, `JOURNAL.md`,
  `baseline_metrics.json`, `best.txt`.
* **Read-only (configuration)**: `program.md`, `benchmark.json`.
* **Off-limits**: anything outside this folder, including the canonical
  `solvers/topology_heuristic_job.py`.

Graduating an improvement back to `solvers/` is an explicit, manual diff-and-copy
step the user performs when the research is "done"; the loop never auto-promotes.

## Inspecting progress

* `python autoresearch_heuristics/snapshot.py list` — tabular score history.
* `python autoresearch_heuristics/snapshot.py log` — dump `JOURNAL.md`.
* `python autoresearch_heuristics/snapshot.py restore best` — overwrite the
  working copy with the current-best snapshot (e.g. after a manual mishap).
* `python autoresearch_heuristics/snapshot.py restore iter_0003_<slug>` —
  rewind to a specific past iteration.
