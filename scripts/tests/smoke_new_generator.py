"""Smoke test for the integer-arithmetic generator.

Generates a couple of representative instances and verifies:
  - duration, earliest_start, target_finish are integers
  - feasibility margin L_r - E_r - D_r >= 1 for every aircraft
  - reproducibility from the same seed
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

from generate_benchmark import generate_instance  # noqa: E402


def _check(inst: dict, label: str) -> None:
    print(f"\n=== {label} ===")
    # First aircraft + first jobs for visual inspection
    for a in inst["aircrafts"][:3]:
        print(f"  aircraft: {a}")
    for j in inst["jobs"][:5]:
        print(f"  job:      {j}")

    int_dur = all(isinstance(j["duration"], int) for j in inst["jobs"])
    int_es  = all(isinstance(a["earliest_start"], int) for a in inst["aircrafts"])
    int_tf  = all(isinstance(a["target_finish"], int) for a in inst["aircrafts"])
    print(f"  all durations int?       {int_dur}")
    print(f"  all earliest_start int?  {int_es}")
    print(f"  all target_finish int?   {int_tf}")

    job_by_ac = collections.defaultdict(list)
    for j in inst["jobs"]:
        job_by_ac[j["aircraft_id"]].append(j["duration"])

    bad = []
    for a in inst["aircrafts"]:
        D = sum(job_by_ac[a["id"]])
        margin = a["target_finish"] - a["earliest_start"] - D
        if margin < 1:
            bad.append((a["id"], margin))
    if bad:
        print(f"  INFEASIBLE aircraft (margin < 1):")
        for ac, m in bad:
            print(f"    {ac} margin={m}")
    else:
        print(f"  all feasible (margin >= 1)? True")


def main() -> None:
    cfgs = [
        ("none",     "tight",  5, 10, (4, 6), 1),
        ("triangle", "tight",  5, 30, (5, 7), 1),
        ("triangle", "loose",  5, 10, (4, 6), 1),
        ("triangle", "medium", 5, 10, (4, 6), 1),
        ("full",     "tight",  5, 20, (4, 6), 1),
    ]
    for c in cfgs:
        inst = generate_instance(*c)
        label = f"{c[0]}/{c[1]} R={c[3]} tasks={c[4]} seed={c[5]}"
        _check(inst, label)

    # Reproducibility: same seed → byte-identical JSON
    a = generate_instance("triangle", "tight", 5, 10, (4, 6), seed=42)
    b = generate_instance("triangle", "tight", 5, 10, (4, 6), seed=42)
    print()
    print("=== Reproducibility ===")
    print(f"  same seed, same JSON? {json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)}")


if __name__ == "__main__":
    main()
