"""sweep_seeds.py — run run_experiments.py back-to-back on a range of seeds.

For each seed N in the given list, this script:
  1. Invokes ``python scripts/run_experiments.py _seedN <EXP_FILTER>``
     synchronously (so we never have two runs colliding for the Gurobi
     licence).
  2. Locates the freshly produced ``data/logs/run_experiments_<ts>.log``
     and renames it to ``seedN_main_methods_<ts>.log`` to match the
     convention of the manual batches.

Usage
-----
    python scripts/sweep_seeds.py 6 7 8 9 10

Each seed produces ~144 records and currently takes roughly 1.5–2 hours;
the script blocks until the whole range is done.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_ROOT     = Path(__file__).resolve().parents[1]
_LOGS_DIR = _ROOT / "data" / "logs"
_RUNNER   = _ROOT / "scripts" / "run_experiments.py"

EXP_FILTER = (
    "milp_baseline,topology_ms6,fas_on_topo,safe_pipeline,"
    "milp_baseline_wB,topology_ms6_wB,fas_on_topo_wB,safe_pipeline_wB,"
    "milp_baseline_wC,topology_ms6_wC,fas_on_topo_wC,safe_pipeline_wC"
)


def _latest_unrenamed_log() -> Path | None:
    """Most recently modified ``run_experiments_*.log`` (not yet renamed)."""
    candidates = sorted(
        _LOGS_DIR.glob("run_experiments_*.log"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _rename_to_seed(log_path: Path, seed: int) -> Path:
    """Apply the ``seedN_main_methods_<ts>.log`` naming convention."""
    timestamp = log_path.stem.removeprefix("run_experiments_")
    target    = log_path.with_name(f"seed{seed}_main_methods_{timestamp}.log")
    log_path.rename(target)
    return target


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def run_one(seed: int, dry_run: bool = False) -> None:
    print(f"\n[{_ts()}] >>> seed{seed}: launching run_experiments.py", flush=True)
    pre = _latest_unrenamed_log()
    pre_mtime = pre.stat().st_mtime if pre else 0.0

    if dry_run:
        print(f"[{_ts()}] (dry-run) skipping subprocess")
        return

    subprocess.run(
        [sys.executable, str(_RUNNER), f"_seed{seed}", EXP_FILTER],
        cwd=_ROOT,
        check=True,
    )

    post = _latest_unrenamed_log()
    if post is None or post.stat().st_mtime <= pre_mtime:
        print(f"[{_ts()}] WARNING: no new log detected for seed{seed}", flush=True)
        return
    renamed = _rename_to_seed(post, seed)
    print(f"[{_ts()}] seed{seed} log renamed to {renamed.name}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("seeds", nargs="+", type=int, help="Seeds to run, e.g. 6 7 8 9 10")
    ap.add_argument("--dry-run", action="store_true", help="Print actions without executing")
    args = ap.parse_args()

    print(f"[{_ts()}] sweep_seeds starting: seeds={args.seeds}")
    for seed in args.seeds:
        run_one(seed, dry_run=args.dry_run)
    print(f"\n[{_ts()}] sweep_seeds done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
