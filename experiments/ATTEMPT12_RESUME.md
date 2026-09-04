# Attempt 12 (`exp/sim-boundaries`) — how to resume the experimentation

State written 2026-09-04 16:59, just before a machine reboot.  Everything
below is reproducible from the repo plus the worktree named here.

## What is finished

| Item | Where | Status |
|---|---|---|
| Solver change (closed-boundary `_sim_front`, `tau` candidate) | branch `exp/sim-boundaries`, commit `3bc423c` | done, pushed |
| Expressiveness test | `experiments/tests/test_igvnd_decoder_expressiveness.py` | green (163/439 floor) |
| Ablation (18 instances × 3) | `outputs/logs/attempt12_ablation_20260902.log` | 24W/26T/4L |
| **Candidate arm**, full grid | `outputs/logs/202605_02_main_methods_20260902_214555.log` | **1110/1110**, committed `433480d` |
| Paper (algorithm + results from the candidate battery) | `papers/jobs_extension/*`, commits `e0e9d13`, `ccaef34` | pushed; `paper.pdf` rebuilt locally (untracked) |
| Journal | `methods/iterated_greedy_vnd_v01/IMPROVEMENT_LOG.md` — Attempt 12 block + "Probe" section (rear-align probes, v3-seed probe) | up to date except the final verdict |

## What is running / interrupted: the FRESH BASELINE ARM (code of `main`)

Runs in a git worktree of `main` so the branch's tree and ledger stay clean:

    F:/repos/aircraft-baseline-wt        (git worktree add -f ... main, HEAD 49e616a)

Its outputs are local to the worktree (`outputs/logs/`, `outputs/solutions/`,
`data/logs_heuristic/`).  Progress at the time of writing: **242 / 1110
benchmark runs**, spread over three log segments (each interruption starts a
new segment; the runner writes the log after every run, so at most one run is
lost per interruption):

    outputs/logs/202605_02_main_methods_20260904_104100.log   85 rows  (killed by reboot #1)
    outputs/logs/202605_02_main_methods_20260904_135954.log  121 rows  (killed by me: its `_seedN$` filter also ran retired triangle/full instances)
    outputs/logs/202605_02_main_methods_20260904_160232.log   56 rows  (killed by reboot #2)

Rows for `scn_triangle_*` / `scn_full_*` inside these logs are harmless: the
verdict script only reads the 37 benchmark configs.

### Resume procedure (repeat after every interruption)

The runner's instance filter is comma-separated **substring / `$`-suffix**
patterns (`run_experiments.py::_match_stem`), NOT regex — never use
`_seedN$` alone (it matches retired topologies).  Compute the exact list of
benchmark instances that still lack one of the three profiles and pass it
via `runpy` (the list is ~9 KB, too long for a comfortable command line):

```bash
PY="/c/Users/alvaro/AppData/Local/Programs/Python/Python311/python.exe"
cd /f/repos/aircraft-positioning-2026
"$PY" - <<'PYEOF'
import sys, glob
from pathlib import Path
sys.path.insert(0, "experiments/tests"); import aggregate_results as A
done = {}
for lg in glob.glob("F:/repos/aircraft-baseline-wt/outputs/logs/202605_02_main_methods_2026090*.log"):
    for r in A.parse_log(Path(lg)): done.setdefault(r["instance"], set()).add(r["experiment"])
configs = ["scn_none_tight_P5_R10"] + [f"scn_{t}_{s}_P5_R{r}" for t in ("chain","hub","two_rows") for r in (5,10,20,30) for s in ("loose","medium","tight")]
need = [f"{c}_seed{s}" for s in range(1, 11) for c in configs if len(done.get(f"{c}_seed{s}", ())) < 3]
print("completed:", sum(len(done.get(f"{c}_seed{s}", ())) for s in range(1, 11) for c in configs), "/ 1110; instances to run:", len(need))
open("F:/repos/aircraft-baseline-wt/resume_filter.txt", "w").write(",".join(i + "$" for i in need))
PYEOF
cd /f/repos/aircraft-baseline-wt
"$PY" -c "import sys, runpy; sys.argv = ['run_experiments.py', open('resume_filter.txt').read().strip(), 'igvnd_wMK,igvnd_wDLY,igvnd_wMOV', 'data/instances_202605_02']; runpy.run_path('experiments/run_experiments.py', run_name='__main__')"
```

Keep the machine otherwise idle while it runs (60 s wall-clock budgets).
A partially-run instance is re-run in full; the verdict keeps the last row.

## Verdict (when the baseline arm reaches 1110/1110)

```bash
cd /f/repos/aircraft-positioning-2026   # branch exp/sim-boundaries
"$PY" experiments/attempt11_grid_verdict.py \
    --baseline-log  /f/repos/aircraft-baseline-wt/outputs/logs/202605_02_main_methods_20260904_104100.log \
    --baseline-log  /f/repos/aircraft-baseline-wt/outputs/logs/202605_02_main_methods_20260904_135954.log \
    --baseline-log  /f/repos/aircraft-baseline-wt/outputs/logs/202605_02_main_methods_20260904_160232.log \
    --baseline-log  <every later segment> \
    --candidate-log outputs/logs/202605_02_main_methods_20260902_214555.log
```

Then copy the baseline segments into the branch's `outputs/logs/` (names
`attempt12_baseline_<ts>.log`), commit them with the verdict in the journal,
and `git worktree remove /f/repos/aircraft-baseline-wt`.

Decision rules (house protocol, `methods/iterated_greedy_vnd_v01/CLAUDE.md`):
KEPT = favourable NET and no consistent regression (≥7/10 seeds above the
19-unit floor; R30 judged by its own band).  Interim picture vs the July
record: R5/R10 all wins, R30 eight consistent regressions of a size
compatible with machine drift (direct throughput check: the branch does
1–5 % fewer decodes at R30, +35 / ±0 objective on two cells).

* **KEPT** → `git switch main && git merge --no-ff exp/sim-boundaries`, tag
  `igvnd-v01-sim-boundaries`, `/sync-method-doc methods/iterated_greedy_vnd_v01/jobs/iterated_greedy_vnd.py`,
  close the journal entry; paper tables already point at the candidate log.
* **R30 cost real but small** → first retire the redundant `tau - eta`
  zero-move candidate in `_place_front` (throughput back), re-check, do not add machinery.
* **DROPPED** → keep the branch, Change-log row, revert `make_tables.py`
  BATTERY_LOG to `…_20260730_103730.log` and regenerate `tables/res_*.tex`.

## Next after Attempt 12: Attempt 14 `exp/ils-at-scale` (designed, not started)

Plan file: `C:\Users\alvaro\.claude\plans\cryptic-gathering-umbrella.md`.
Start with the zero-code diagnostics D0 (baseline vs `use_v3=False`, 60 s) and
H0 (baseline at 240 s) on `chain_loose_R30 s1`, `chain_tight_R30 s1`,
`hub_medium_R20 s1`, `two_rows_tight_R20 s1` × 3 profiles, K=2, machine idle.
Attempt 13 (rear-side stretch alignment) was probed and NOT opened — see the
journal "Probe" section; do not re-propose without new evidence.
