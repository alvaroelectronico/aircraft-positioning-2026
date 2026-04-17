"""
run_experiments.py — Batch runner for aircraft positioning experiments.

Runs a set of named solver configurations against a set of instances,
saves one JSON per run and updates data/solutions/results.csv.

Usage
-----
    python scripts/run_experiments.py                  # all instances, all experiments
    python scripts/run_experiments.py scn_few-loose    # instances whose name contains the pattern
    python scripts/run_experiments.py scn_few-loose milp_baseline   # filter instances AND experiment
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))                            # aircraft_positioning.py
sys.path.insert(0, str(_ROOT / "solvers"))
sys.path.insert(0, str(_ROOT / "scripts" / "input_data"))
sys.path.insert(0, str(_ROOT / "scripts" / "output_data"))

from milp_solver import MILPSolver                          # noqa: E402
from constructive_heuristic import ConstructiveHeuristic    # noqa: E402
from aircraft_positioning import Application                 # noqa: E402  (also sets up remaining paths)


# =============================================================================
#  INSTANCES — edit this list or use a glob pattern
# =============================================================================

# Instances to use for experimentation — move files into this folder as needed
INSTANCE_PATHS: list[Path] = sorted((_ROOT / "data" / "experiment_intances").glob("scn_*.json"))


# =============================================================================
#  EXPERIMENTS — one entry per named configuration
#
#  Each entry is a dict with:
#    label        : str          — unique name used in filenames and the summary
#    solver_class : type         — solver class (instantiated fresh for each run)
#    config       : dict         — kwargs forwarded to configure_solver()
# =============================================================================

# Shared configuration — overridden per experiment where needed
_BASE_CONFIG: dict = {
    "weight_makespan":  10.0,
    "weight_delay":     100.0,
    "weight_movements": 1.0,
    "time_limit_s":     60,
    "MIPGap":           0.05,
    "NoRelHeurTime":    0,     # 0 = disabled
}

EXPERIMENTS: list[dict] = [
    {
        "label":        "milp_baseline",
        "solver_class": MILPSolver,
        "config":       {**_BASE_CONFIG},
    },
    {
        "label":        "milp_heuristic",
        "solver_class": MILPSolver,
        "config":       {**_BASE_CONFIG, "NoRelHeurTime": 10},
    },
    {
        "label":        "constructive",
        "solver_class": ConstructiveHeuristic,
        "config": {
            "weight_makespan":  10.0,
            "weight_delay":     100.0,
            "weight_movements": 1.0,
            "time_limit_s":     60,
            "alpha":            0.8,
            "seed":             None,
        },
    },
]


# =============================================================================
#  Runner
# =============================================================================

def run_experiments(
    instances: list[Path],
    experiments: list[dict],
    solutions_dir: Path | None = None,
) -> list[dict]:
    """Run every experiment on every instance.

    Parameters
    ----------
    instances:
        Paths to instance JSON files.
    experiments:
        List of experiment dicts (see module header).
    solutions_dir:
        Where to write solution files.  Defaults to ``data/solutions/``.

    Returns
    -------
    list[dict]
        One summary record per completed run.
    """
    solutions_dir = solutions_dir or _ROOT / "data" / "solutions"
    total   = len(instances) * len(experiments)
    done    = 0
    summary = []

    print(f"\n{'='*66}")
    print(f"  Experiments : {len(experiments)}")
    print(f"  Instances   : {len(instances)}")
    print(f"  Total runs  : {total}")
    print(f"{'='*66}\n")

    for inst_path in instances:
        for exp in experiments:
            done += 1
            label = exp["label"]
            tag   = f"[{done:>3}/{total}] {inst_path.stem}  ·  {label}"
            print(f"\n{'-'*66}")
            print(tag)
            print(f"{'-'*66}")

            record: dict = {
                "instance":   inst_path.stem,
                "experiment": label,
                "status":     None,
                "objective":  None,
                "makespan":   None,
                "movements":  None,
                "total_delay":None,
                "solve_time_s": None,
                "error":      None,
            }

            try:
                app = Application(solver=exp["solver_class"]())
                app.read_data(inst_path)
                app.configure_solver(**exp["config"])
                app.solve()
                app.save_solution(solutions_dir)

                sol     = app.get_solution()
                metrics = sol["metrics"]
                record.update({
                    "status":       sol["status"],
                    "objective":    sol["objective"],
                    "makespan":     metrics["makespan"],
                    "movements":    metrics["movements"],
                    "total_delay":  metrics["total_delay"],
                    "solve_time_s": app._solve_time_s,
                })
                print(
                    f"  ✓  status={sol['status']}  obj={sol['objective']}  "
                    f"makespan={metrics['makespan']}  "
                    f"delay={metrics['total_delay']}  "
                    f"mov={metrics['movements']}  "
                    f"time={app._solve_time_s}s"
                )

            except Exception as exc:  # noqa: BLE001
                record["error"] = str(exc)
                print(f"  ✗  ERROR: {exc}")
                traceback.print_exc()

            summary.append(record)

    return summary


def print_summary(summary: list[dict]) -> None:
    """Print a compact results table to stdout."""
    ok      = [r for r in summary if r["error"] is None]
    failed  = [r for r in summary if r["error"] is not None]

    print(f"\n{'='*66}")
    print(f"  SUMMARY  —  {len(ok)} ok  /  {len(failed)} failed  /  {len(summary)} total")
    print(f"{'='*66}")

    if not ok:
        return

    # Column widths
    w_inst = max(len(r["instance"])   for r in ok)
    w_exp  = max(len(r["experiment"]) for r in ok)

    header = (
        f"  {'Instance':<{w_inst}}  {'Experiment':<{w_exp}}  "
        f"{'Status':<10}  {'Obj':>10}  {'Makespan':>9}  "
        f"{'Delay':>9}  {'Mov':>4}  {'Time(s)':>8}"
    )
    print(header)
    print(f"  {'-'*( len(header)-2 )}")

    for r in ok:
        status = str(r["status"])[:10]
        print(
            f"  {r['instance']:<{w_inst}}  {r['experiment']:<{w_exp}}  "
            f"{status:<10}  {r['objective']:>10.2f}  "
            f"{r['makespan']:>9.2f}  {r['total_delay']:>9.2f}  "
            f"{r['movements']:>4}  {r['solve_time_s']:>8.1f}"
        )

    if failed:
        print(f"\n  Failed runs:")
        for r in failed:
            print(f"    ✗ {r['instance']}  ·  {r['experiment']}  →  {r['error']}")

    print(f"{'='*66}\n")


# =============================================================================
#  CLI
# =============================================================================

if __name__ == "__main__":
    # Optional CLI filters: argv[1] = instance pattern, argv[2] = experiment label
    inst_filter = sys.argv[1] if len(sys.argv) > 1 else None
    exp_filter  = sys.argv[2] if len(sys.argv) > 2 else None

    instances = (
        [p for p in INSTANCE_PATHS if inst_filter in p.stem]
        if inst_filter else INSTANCE_PATHS
    )
    experiments = (
        [e for e in EXPERIMENTS if exp_filter in e["label"]]
        if exp_filter else EXPERIMENTS
    )

    if not instances:
        print(f"No instances match filter '{inst_filter}'.", file=sys.stderr)
        sys.exit(1)
    if not experiments:
        print(f"No experiments match filter '{exp_filter}'.", file=sys.stderr)
        sys.exit(1)

    summary = run_experiments(instances, experiments)
    print_summary(summary)
