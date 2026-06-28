"""One-shot generator for the extended Two-rows / Triangle grid.

Grid: {two_rows, triangle} x R{5,10,20,30} x {loose,medium,tight} x 10 seeds.
Writes into the standard battery tree data/instances_202605_02/<config>/, one
sub-directory per config, skipping any seed file that already exists (so only
the genuinely new configs are produced). tasks_range follows the existing
size convention. Validation uses the real problems/jobs schema.

Usage:
    py -3 experiments/_gen_new_instances.py --dry-run
    py -3 experiments/_gen_new_instances.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

import generate_benchmark as gb

# Point the generator's schema at the real one (its default path is missing).
gb._SCHEMA = ROOT / "problems" / "jobs" / "instance_schema.json"

OUTBASE = ROOT / "data" / "instances_202605_02"
TASKS = {5: (3, 5), 10: (4, 6), 20: (4, 6), 30: (5, 7)}   # size -> tasks_range
TOPOS = ["two_rows", "triangle"]
RS = [5, 10, 20, 30]
SLACKS = ["loose", "medium", "tight"]
SEEDS = range(1, 11)

dry = "--dry-run" in sys.argv

new_cfgs, written, skipped, errors = [], 0, 0, 0
for topo in TOPOS:
    for R in RS:
        for slack in SLACKS:
            stem = f"scn_{topo}_{slack}_P5_R{R}"
            cfg_dir = OUTBASE / stem
            cfg_new = 0
            for seed in SEEDS:
                p = cfg_dir / f"{stem}_seed{seed}.json"
                if p.exists():
                    skipped += 1
                    continue
                cfg_new += 1
                if dry:
                    written += 1
                    continue
                try:
                    inst = gb.generate_instance(
                        topology=topo, slack=slack, n_positions=5,
                        n_aircraft=R, tasks_range=TASKS[R], seed=seed,
                    )
                    cfg_dir.mkdir(parents=True, exist_ok=True)
                    p.write_text(json.dumps(inst, indent=2, ensure_ascii=False), encoding="utf-8")
                    written += 1
                except Exception as exc:   # noqa: BLE001
                    print(f"  [ERR] {p.name} -> {exc}", file=sys.stderr)
                    errors += 1
            if cfg_new:
                new_cfgs.append((stem, cfg_new))

print(f"\n{'DRY-RUN plan' if dry else 'Generation'}: new configs ({len(new_cfgs)}):")
for stem, n in new_cfgs:
    print(f"  {stem:<34} +{n} seeds")
print(f"\n{written} {'would be written' if dry else 'written'} / {skipped} skipped (already exist) / {errors} errors")
