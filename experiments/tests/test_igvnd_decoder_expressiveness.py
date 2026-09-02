"""Decoder-expressiveness check for the IGVND manoeuvre decoder (v3).

For every benchmark cell where the cached MILP proved optimality (mip_gap 0),
feed `_decode_v3` the MILP's OWN assignment and start order and ask two
questions:

  * is the decoded schedule compliant with the paper-#2 checker?  (hard)
  * does it reproduce the MILP objective?  (reported per cell; asserted only
    as a floor on the overall rate so a regression of the decoder's image is
    caught early — the search may still reach an optimum through a different
    structure, so this rate under-states what the solver finds)

A gap here means the decoder cannot *express* the optimal structure, so no
amount of search can reach it — the diagnosis behind Attempt 12.  Run as a
script for the per-cell table:

    py -3 experiments/tests/test_igvnd_decoder_expressiveness.py
"""
from __future__ import annotations

import glob
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "methods" / "iterated_greedy_vnd_v01" / "jobs"))
sys.path.insert(0, str(ROOT / "problems" / "jobs"))

from iterated_greedy_vnd import IteratedGreedyVNDJobSolver  # noqa: E402
from checker import check_solution  # noqa: E402

INST_DIR = ROOT / "data" / "instances_202605_02"
SOL_DIR = ROOT / "outputs" / "solutions"
WEIGHTS = {"wMK": (100, 1, 1), "wDLY": (1, 100, 1), "wMOV": (1, 1, 100)}
TOPOS = ("none", "chain", "hub", "two_rows")


def _latest_optimal_milp(stem: str, pk: str) -> dict | None:
    files = glob.glob(str(SOL_DIR / f"{stem}__milp_job_{pk}__*.json"))
    if not files:
        return None
    sol = json.load(open(max(files), encoding="utf-8"))
    gap = sol.get("mip_gap")
    return sol if gap is not None and gap <= 1e-9 and sol.get("objective") is not None else None


def cells(sizes=(5, 10)):
    for f in sorted(INST_DIR.glob("scn_*/scn_*_seed*.json")):
        m = re.match(r"scn_(\w+?)_(loose|medium|tight)_P5_R(\d+)_seed(\d+)$", f.stem)
        if not m or m.group(1) not in TOPOS or int(m.group(3)) not in sizes:
            continue
        for pk in WEIGHTS:
            milp = _latest_optimal_milp(f.stem, pk)
            if milp is not None:
                yield f, pk, milp


def decode_milp_structure(inst: dict, pk: str, milp: dict) -> dict:
    s = IteratedGreedyVNDJobSolver()
    s.time_limit = 60.0
    s.wM, s.wD, s.wS = (float(w) for w in WEIGHTS[pk])
    s._prepare(inst)
    s.rng = random.Random(1)
    s._deadline = float("inf")
    s._cache = {}
    s._decoder_tag = "v3"
    assignment = {a["id"]: a["position"] for a in milp["aircraft"]}
    order = [a["id"] for a in sorted(milp["aircraft"], key=lambda a: (a["start"], a["id"]))]
    return s._decode_v3(assignment, order)


def scan(sizes=(5, 10)):
    rows = []
    for f, pk, milp in cells(sizes):
        inst = json.load(open(f, encoding="utf-8"))
        sol = decode_milp_structure(inst, pk, milp)
        ok = bool(check_solution(sol, inst)["compliant"])
        rows.append((f.stem, pk, milp["objective"], sol["objective"], ok))
    return rows


def test_v3_decode_of_milp_structure_is_compliant():
    rows = scan()
    assert rows, "no proven-optimal MILP solutions found"
    bad = [r for r in rows if not r[4]]
    assert not bad, f"non-compliant v3 decodes: {bad[:5]}"


def test_v3_reproduction_rate_does_not_regress():
    # Floors = state after Attempt 12 (2026-09-02): 163/439 exact over all
    # proven-optimal R5+R10 cells, 66/180 on R5 wMK/wDLY.  Raise them when the
    # decoder's image grows (Attempt 13 targets exactly this number); a drop
    # means a change shrank what the manoeuvre decoder can express.
    rows = scan()
    exact_all = sum(abs(r[2] - r[3]) <= 1e-6 for r in rows)
    r5 = [r for r in rows if "_R5_" in r[0] and r[1] != "wMOV"]
    exact_r5 = sum(abs(r[2] - r[3]) <= 1e-6 for r in r5)
    assert exact_all >= 160, f"exact reproduction {exact_all}/{len(rows)} (floor 160)"
    assert exact_r5 >= 60, f"R5 wMK/wDLY exact {exact_r5}/{len(r5)} (floor 60)"


if __name__ == "__main__":
    rows = scan()
    by = {}
    for stem, pk, zm, zh, ok in rows:
        key = (re.sub(r"_seed\d+$", "", stem), pk)
        d = by.setdefault(key, [0, 0, 0, 0.0])
        d[0] += 1
        d[1] += abs(zm - zh) <= 1e-6
        d[2] += not ok
        d[3] += (zh - zm) / zm if zm else 0.0
    print(f"{'cell':30} {'pk':5} {'n':>3} {'exact':>5} {'noncompl':>8} {'mean rel gap %':>14}")
    for key in sorted(by):
        n, ex, nc, g = by[key]
        print(f"{key[0]:30} {key[1]:5} {n:3d} {ex:5d} {nc:8d} {100*g/n:14.1f}")
    tot = len(rows); ex = sum(abs(r[2]-r[3]) <= 1e-6 for r in rows); nc = sum(not r[4] for r in rows)
    print(f"\nTOTAL cells with proven MILP optimum: {tot}   exact: {ex}   non-compliant: {nc}")
