"""One-off driver: regenerate the 120-instance benchmark with the integer
generator into per-configuration subfolders under
``problems/aircraft/instances/``.

Layout produced:
    problems/aircraft/instances/<config_dirname>/<config_dirname>_seed{N}.json

where ``<config_dirname>`` is the filename stem without the trailing
``_seed{N}`` (e.g. ``scn_chain_tight_P5_R10``).

Run:
    python experiments/regenerate_benchmark.py [--force]

Without ``--force``, existing files are overwritten only if their seed/config
matches; with ``--force``, the per-config subfolder is wiped clean first.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "scripts"))

from generate_benchmark import BENCHMARK_SPEC, generate_instance  # noqa: E402

OUTPUT_ROOT = _ROOT / "data" / "instances_202605"


def _config_dirname(g) -> str:
    """Return ``scn_<topo>_<slack>_P<P>_R<R>`` (same as filename stem prefix)."""
    return f"scn_{g.topology}_{g.slack}_P{g.n_positions}_R{g.n_aircraft}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--force", action="store_true",
        help="Wipe each per-config subfolder before regenerating.",
    )
    args = ap.parse_args()

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    print(f"Output root: {OUTPUT_ROOT}")
    print(f"Configurations: {len(BENCHMARK_SPEC)}")
    print()

    total_written = 0
    for g in BENCHMARK_SPEC:
        subdir = OUTPUT_ROOT / _config_dirname(g)
        if args.force and subdir.exists():
            shutil.rmtree(subdir)
        subdir.mkdir(parents=True, exist_ok=True)

        seeds = list(g.seeds)
        print(f"  {_config_dirname(g)}  (seeds {seeds[0]}-{seeds[-1]}, "
              f"tasks={g.tasks_range}, dur={g.duration_range})")

        for seed in seeds:
            inst = generate_instance(
                topology       = g.topology,
                slack          = g.slack,
                n_positions    = g.n_positions,
                n_aircraft     = g.n_aircraft,
                tasks_range    = g.tasks_range,
                seed           = seed,
                duration_range = g.duration_range,
                min_separation = g.min_separation,
            )
            fname = f"{_config_dirname(g)}_seed{seed}.json"
            (subdir / fname).write_text(
                json.dumps(inst, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            total_written += 1

    print()
    print(f"Wrote {total_written} instance JSONs to {OUTPUT_ROOT}.")


if __name__ == "__main__":
    main()
