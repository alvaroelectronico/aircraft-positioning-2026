"""
evaluate.py — the harness that scores the current working copy of
``autoresearch_heuristics/topology_heuristic_job.py`` against the MILP
baseline.

Public entry point
------------------
    from autoresearch_heuristics.evaluate import eval_variant
    verdict = eval_variant("fast_eval")

CLI
---
    python autoresearch_heuristics/evaluate.py [fast_eval|validation]

Returned schema
---------------
    {
      "score":        float,    # mean relative gap; +inf if any non-compliant
      "mean_gap":     float,    # same as score when n_compliant == n_total
      "n_compliant":  int,
      "n_total":      int,
      "per_instance": [
        {"stem": "scn_...", "obj_var": 220.5, "obj_milp": 163.35,
         "gap": 0.35, "compliant": True, "solve_time_s": 30.0,
         "movements": 0, "makespan": 84.0, "total_delay": 167.5,
         "status": "topology_job"},
        ...
      ],
      "elapsed_s":    float,
      "mode":         "fast_eval",
    }
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import math
import sys
import time
from pathlib import Path


_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent

# Make the rest of the repo importable.  The working copy of
# topology_heuristic_job lives next to this file — we import it explicitly
# rather than through sys.path so that there is no risk of accidentally
# picking up solvers/topology_heuristic_job.py.
sys.path.insert(0, str(_ROOT / "scripts" / "input_data"))
sys.path.insert(0, str(_ROOT / "scripts" / "output_data"))
sys.path.insert(0, str(_ROOT / "solvers"))
sys.path.insert(0, str(_ROOT / "models"))

from instance_io           import load_json                # noqa: E402
from check_solution_jobs_v2 import check_solution           # noqa: E402


_BENCHMARK_PATH = _HERE / "benchmark.json"
_BASELINE_PATH  = _HERE / "baseline_metrics.json"
_WORKING_COPY   = _HERE / "topology_heuristic_job.py"


def _load_working_copy_class():
    """Load (or reload) TopologyHeuristicJob from the working copy.

    Uses importlib.util.spec_from_file_location with an explicit module name
    so we never confuse it with solvers/topology_heuristic_job.py on sys.path.
    """
    module_name = "_autoresearch_topology_heuristic_job"
    spec = importlib.util.spec_from_file_location(module_name, str(_WORKING_COPY))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load working copy at {_WORKING_COPY}")
    mod = importlib.util.module_from_spec(spec)
    # Reload semantics: drop the previous version if already imported.
    if module_name in sys.modules:
        del sys.modules[module_name]
    spec.loader.exec_module(mod)
    sys.modules[module_name] = mod
    return mod.TopologyHeuristicJob


def _format_row(rec: dict) -> str:
    obj  = f"{rec['obj_var']:>9.2f}" if rec.get("obj_var") is not None else "       —"
    milp = f"{rec['obj_milp']:>9.2f}" if rec.get("obj_milp") is not None else "       —"
    gap  = f"{rec['gap']*100:>+7.2f}%" if (rec.get("gap") is not None and math.isfinite(rec["gap"])) else "      —"
    cmp_ = "Y" if rec.get("compliant") else "N"
    t    = f"{rec.get('solve_time_s', 0.0):>5.1f}s"
    stem = rec["stem"]
    return f"  {stem:<48}  obj={obj}  milp={milp}  gap={gap}  c={cmp_}  t={t}"


def eval_variant(mode: str = "fast_eval") -> dict:
    """Evaluate the current working copy of TopologyHeuristicJob.

    Parameters
    ----------
    mode : str
        Which benchmark set to use ("fast_eval" or "validation").

    Returns
    -------
    dict
        See module docstring for the schema.
    """
    with open(_BENCHMARK_PATH, encoding="utf-8") as f:
        bench = json.load(f)
    if mode not in bench:
        raise ValueError(f"Unknown benchmark mode {mode!r}; "
                         f"expected one of {[k for k in bench if not k.startswith('_')]}.")
    if not _BASELINE_PATH.exists():
        raise FileNotFoundError(
            "baseline_metrics.json is missing.  Run precompute_baseline.py first."
        )

    with open(_BASELINE_PATH, encoding="utf-8") as f:
        baseline = json.load(f)

    cfg              = bench[mode]
    weights          = bench["weight_profile"]
    instance_paths   = [_ROOT / rel for rel in cfg["instances"]]
    time_limit_s     = float(cfg["time_limit_per_run"])

    cls = _load_working_copy_class()

    per_instance: list[dict] = []
    t_start = time.perf_counter()
    n_compliant = 0

    for path in instance_paths:
        stem  = path.stem
        inst  = load_json(str(path))
        solver = cls()
        solver.configure_solver(
            time_limit_s     = time_limit_s,
            weight_makespan  = weights["weight_makespan"],
            weight_delay     = weights["weight_delay"],
            weight_movements = weights["weight_movements"],
            weight_topology  = weights.get("weight_topology", 1.0),
            alpha            = weights.get("alpha", 0.3),
            n_starts         = weights.get("n_starts", 6),
            seed             = weights.get("seed", 1),
        )
        t0 = time.perf_counter()
        try:
            sol = solver.solve(inst)
            run_err = None
        except Exception as exc:  # noqa: BLE001
            sol = None
            run_err = repr(exc)
        elapsed = time.perf_counter() - t0

        if sol is None or sol.get("objective") is None:
            per_instance.append({
                "stem":          stem,
                "obj_var":       None,
                "obj_milp":      baseline.get(stem, {}).get("objective"),
                "gap":           None,
                "compliant":     False,
                "solve_time_s":  round(elapsed, 2),
                "movements":     None,
                "makespan":      None,
                "total_delay":   None,
                "status":        "error" if run_err else (sol or {}).get("status"),
                "error":         run_err,
            })
            continue

        # Compliance check
        report     = check_solution(sol, inst)
        compliant  = bool(report["compliant"])
        if compliant:
            n_compliant += 1

        obj_var  = float(sol["objective"])
        obj_milp = baseline.get(stem, {}).get("objective")
        if obj_milp is None:
            gap = None    # cannot compute a relative gap without a reference
        else:
            denom = max(1.0, abs(float(obj_milp)))
            gap   = (obj_var - float(obj_milp)) / denom

        per_instance.append({
            "stem":          stem,
            "obj_var":       obj_var,
            "obj_milp":      obj_milp,
            "gap":           gap,
            "compliant":     compliant,
            "solve_time_s":  round(elapsed, 2),
            "movements":     sol["metrics"]["movements"],
            "makespan":      sol["metrics"]["makespan"],
            "total_delay":   sol["metrics"]["total_delay"],
            "status":        sol.get("status"),
        })

    elapsed_total = time.perf_counter() - t_start
    n_total       = len(per_instance)
    # Score = mean(gap) over compliant instances; +inf if any are non-compliant.
    if n_compliant == n_total and n_total > 0:
        valid_gaps = [r["gap"] for r in per_instance if r["gap"] is not None]
        mean_gap   = (sum(valid_gaps) / len(valid_gaps)) if valid_gaps else math.inf
        score      = mean_gap
    else:
        mean_gap = math.inf
        score    = math.inf

    return {
        "score":        score,
        "mean_gap":     mean_gap,
        "n_compliant":  n_compliant,
        "n_total":      n_total,
        "per_instance": per_instance,
        "elapsed_s":    round(elapsed_total, 2),
        "mode":         mode,
    }


def _print_verdict(verdict: dict) -> None:
    print(f"\nautoresearch_heuristics/evaluate.py  ({verdict['mode']})")
    print("-" * 86)
    for rec in verdict["per_instance"]:
        print(_format_row(rec))
    print("-" * 86)
    score = verdict["score"]
    score_str = f"{score:+.4f}" if math.isfinite(score) else "+inf"
    print(f"  score={score_str}  compliant={verdict['n_compliant']}/{verdict['n_total']}"
          f"  elapsed={verdict['elapsed_s']}s")


if __name__ == "__main__":
    import argparse
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    ap = argparse.ArgumentParser(description="Evaluate the autoresearch working copy of TopologyHeuristicJob.")
    ap.add_argument("mode", nargs="?", choices=["fast_eval", "validation"], default="fast_eval")
    ap.add_argument("--json-only", action="store_true",
                    help="Print only the JSON dict (no human-readable table).")
    ap.add_argument("--write", type=Path, default=None,
                    help="Also write the verdict to this JSON path.")
    args = ap.parse_args()

    verdict = eval_variant(args.mode)
    if not args.json_only:
        _print_verdict(verdict)
    print("\nJSON_VERDICT_START")
    # math.inf is not JSON-serialisable; replace with the string "inf"
    def _enc(v):
        return v if (v is None or math.isfinite(v) if isinstance(v, float) else True) else "inf"
    safe = json.loads(json.dumps(verdict, default=lambda o: "inf" if isinstance(o, float) and not math.isfinite(o) else None))
    # The default above only catches non-finite floats at serialisation; do a pass.
    def _walk(d):
        if isinstance(d, dict):
            return {k: _walk(v) for k, v in d.items()}
        if isinstance(d, list):
            return [_walk(v) for v in d]
        if isinstance(d, float) and not math.isfinite(d):
            return "inf"
        return d
    print(json.dumps(_walk(verdict), indent=2))
    print("JSON_VERDICT_END")

    if args.write:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        with open(args.write, "w", encoding="utf-8") as f:
            json.dump(_walk(verdict), f, indent=2)
        print(f"\nVerdict written to {args.write}")
