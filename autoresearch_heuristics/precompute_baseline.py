"""
precompute_baseline.py — runs MILPJobsV2Solver on every benchmark instance
and stores the resulting objective / metrics in baseline_metrics.json.

The values produced here are the *reference* against which every iteration
of the autoresearch loop measures its variant.  The metric is

    score = mean over instances of (obj_variant - obj_milp) / max(1, |obj_milp|)

so the MILP's incumbent objective (whether or not it is provably optimal)
is the denominator.  Both fast_eval and validation instances are processed
in one run.

The script is idempotent: instances whose stem is already a key in
baseline_metrics.json are skipped, unless --force is passed.

Usage
-----
    python autoresearch_heuristics/precompute_baseline.py            # both sets
    python autoresearch_heuristics/precompute_baseline.py fast_eval  # one set
    python autoresearch_heuristics/precompute_baseline.py --force    # re-run all
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent

sys.path.insert(0, str(_ROOT / "scripts" / "input_data"))
sys.path.insert(0, str(_ROOT / "scripts" / "output_data"))
sys.path.insert(0, str(_ROOT / "solvers"))
sys.path.insert(0, str(_ROOT / "models"))

from instance_io           import load_json                # noqa: E402
from check_solution_jobs_v2 import check_solution           # noqa: E402
from milp_jobs_v2_solver   import MILPJobsV2Solver         # noqa: E402


_BENCHMARK = _HERE / "benchmark.json"
_OUTPUT    = _HERE / "baseline_metrics.json"


def _load_existing() -> dict:
    if _OUTPUT.exists():
        with open(_OUTPUT, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save(data: dict) -> None:
    with open(_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _run_milp_on(path: Path, time_limit_s: float, weights: dict) -> dict:
    inst = load_json(str(path))
    solver = MILPJobsV2Solver()
    solver.configure_solver(
        time_limit_s     = time_limit_s,
        weight_makespan  = weights["weight_makespan"],
        weight_delay     = weights["weight_delay"],
        weight_movements = weights["weight_movements"],
        MIPGap           = 0.0,
    )
    t0 = time.perf_counter()
    sol = solver.solve(inst)
    elapsed = time.perf_counter() - t0

    if sol["objective"] is None:
        return {
            "status":      sol["status"],
            "objective":   None,
            "makespan":    None,
            "delay":       None,
            "movements":   None,
            "mip_gap":     None,
            "time_s":      round(elapsed, 2),
            "compliant":   False,
            "note":        "MILP returned no feasible solution within the budget",
        }

    report = check_solution(sol, inst)
    return {
        "status":     sol["status"],
        "objective":  sol["objective"],
        "makespan":   sol["metrics"]["makespan"],
        "delay":      sol["metrics"]["total_delay"],
        "movements":  sol["metrics"]["movements"],
        "mip_gap":    sol.get("mip_gap"),
        "time_s":     round(elapsed, 2),
        "compliant":  bool(report["compliant"]),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("set", nargs="?",
                    choices=["fast_eval", "validation", "all"], default="all",
                    help="Which benchmark set to precompute (default: all).")
    ap.add_argument("--force", action="store_true",
                    help="Re-run instances even if already in baseline_metrics.json.")
    ap.add_argument("--time-limit", type=float, default=60.0,
                    help="Override MILP time limit per instance (default 60s).")
    args = ap.parse_args()

    with open(_BENCHMARK, encoding="utf-8") as f:
        bench = json.load(f)
    weights = bench["weight_profile"]

    if args.set == "all":
        sets = ["fast_eval", "validation"]
    else:
        sets = [args.set]

    # Deduplicate instances across sets while preserving discovery order
    instance_paths: list[Path] = []
    seen: set[str] = set()
    for s in sets:
        for rel in bench[s]["instances"]:
            full = _ROOT / rel
            if full.stem in seen:
                continue
            seen.add(full.stem)
            instance_paths.append(full)

    data = _load_existing()
    total = len(instance_paths)
    for i, path in enumerate(instance_paths, 1):
        stem = path.stem
        if not args.force and stem in data and data[stem].get("objective") is not None:
            print(f"[{i:>2}/{total}] {stem}  (cached, skip)")
            continue
        print(f"[{i:>2}/{total}] {stem}  solving MILP (budget {args.time_limit:.0f}s)...")
        try:
            entry = _run_milp_on(path, args.time_limit, weights)
        except Exception as exc:  # noqa: BLE001
            print(f"           ERROR: {exc}")
            entry = {"status": "error", "objective": None,
                     "note": str(exc), "time_s": 0.0, "compliant": False}
        data[stem] = entry
        _save(data)
        obj_str = f"{entry['objective']:.2f}" if entry["objective"] is not None else "None"
        gap_str = f"{entry['mip_gap'] * 100:.1f}%" if entry.get("mip_gap") not in (None, 0.0) else (
                  "0.0%" if entry.get("mip_gap") == 0.0 else "—")
        print(f"           obj={obj_str}  gap={gap_str}  compliant={entry['compliant']}  t={entry['time_s']}s")

    print(f"\nbaseline_metrics.json now has {len(data)} entries; wrote {_OUTPUT}")


if __name__ == "__main__":
    main()
