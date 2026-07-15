"""Decoder smoke test: random chromosomes -> decode -> checker.

For each instance it reports the spec from ``starting_guidelines.md``:
checker_pass count, objective / makespan / delay / movements of the best random
chromosome, ``runtime_decoder_avg_ms``, and any checker errors.  It also
cross-checks that the decoder's own movement count equals the checker's RQ07
count (the faithful-mirror invariant).

Usage:
    py -3 methods/theory_assisted/jobs/brkga/smoke.py [N] [inst_substr ...]
"""
from __future__ import annotations

import random
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent          # .../jobs/brkga
_JOBS = _HERE.parent                              # .../jobs
_ROOT = _JOBS.parent.parent.parent                # repo root
for _p in (str(_JOBS), str(_ROOT / "shared"), str(_ROOT / "problems" / "jobs")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from instance_io import load_json                 # noqa: E402
from checker import check_solution                # noqa: E402

from brkga.instance import build_model            # noqa: E402
from brkga.decoder import decode, to_solution_dict  # noqa: E402

_WEIGHTS = {"makespan": 0.1, "delay": 1.0, "movements": 10.0}

# A small, representative ladder: no-arcs control, then increasing blocking.
_DEFAULT_INSTANCES = [
    "scn_none_tight_P5_R10/scn_none_tight_P5_R10_seed1",
    "scn_chain_tight_P5_R10/scn_chain_tight_P5_R10_seed1",
    "scn_triangle_loose_P5_R10/scn_triangle_loose_P5_R10_seed1",
    "scn_triangle_tight_P5_R5/scn_triangle_tight_P5_R5_seed1",
    "scn_triangle_tight_P5_R10/scn_triangle_tight_P5_R10_seed1",
    "scn_triangle_tight_P5_R20/scn_triangle_tight_P5_R20_seed1",
    "scn_triangle_tight_P5_R30/scn_triangle_tight_P5_R30_seed1",
    "scn_full_tight_P5_R20/scn_full_tight_P5_R20_seed1",
]


def _first_error(report: dict) -> str:
    for rq, info in report["requirements"].items():
        if not info["pass"]:
            return f"{rq}: {info['detail']}"
    return ""


def run_instance(path: Path, n: int, rng: random.Random) -> dict:
    inst = load_json(path)
    model = build_model(inst)
    L = model.chromosome_length

    passes = 0
    mismatch = 0
    best = None
    total_ms = 0.0
    first_err = ""

    for _ in range(n):
        chromo = [rng.random() for _ in range(L)]
        t0 = time.perf_counter()
        obj, state = decode(chromo, model, _WEIGHTS)
        total_ms += (time.perf_counter() - t0) * 1000.0

        sol = to_solution_dict(state, model, _WEIGHTS, "smoke")
        report = check_solution(sol, inst)
        if report["compliant"]:
            passes += 1
        elif not first_err:
            first_err = _first_error(report)

        # faithful-mirror invariant: decoder movements == checker RQ07 count
        if report["requirements"]["RQ07"]["movements_count"] != state.movements:
            mismatch += 1

        m = sol["metrics"]
        cand = (obj, m["makespan"], m["total_delay"], m["movements"])
        if best is None or cand[0] < best[0]:
            best = cand

    return {
        "name": path.stem,
        "nR": model.num_aircraft,
        "nP": model.num_positions,
        "nArcs": len(model.arcs),
        "passes": passes,
        "n": n,
        "mismatch": mismatch,
        "best_obj": best[0],
        "best_makespan": best[1],
        "best_delay": best[2],
        "best_mov": best[3],
        "decoder_avg_ms": total_ms / n,
        "first_err": first_err,
    }


def main() -> int:
    args = sys.argv[1:]
    n = 100
    substrs: list[str] = []
    if args and args[0].isdigit():
        n = int(args[0])
        substrs = args[1:]
    else:
        substrs = args

    inst_root = _ROOT / "data" / "instances_202605_02"
    if substrs:
        paths = [p for p in sorted(inst_root.rglob("*.json"))
                 if any(s in str(p) for s in substrs)]
    else:
        paths = [inst_root / f"{rel}.json" for rel in _DEFAULT_INSTANCES]
        paths = [p for p in paths if p.exists()]

    rng = random.Random(12345)
    print(f"{'instance':40s} {'R':>3} {'P':>2} {'arc':>3} "
          f"{'pass':>7} {'mism':>4} {'best_obj':>10} {'mk':>7} {'dly':>7} {'mov':>4} {'ms/dec':>7}")
    all_ok = True
    for p in paths:
        r = run_instance(p, n, rng)
        ok = (r["passes"] == r["n"]) and (r["mismatch"] == 0)
        all_ok = all_ok and ok
        flag = "" if ok else "  <-- FAIL"
        print(f"{r['name']:40s} {r['nR']:>3} {r['nP']:>2} {r['nArcs']:>3} "
              f"{r['passes']:>3}/{r['n']:<3} {r['mismatch']:>4} {r['best_obj']:>10.2f} "
              f"{r['best_makespan']:>7.2f} {r['best_delay']:>7.2f} {r['best_mov']:>4} "
              f"{r['decoder_avg_ms']:>7.3f}{flag}")
        if r["first_err"]:
            print(f"    first error: {r['first_err']}")

    print("\nRESULT:", "ALL PASS" if all_ok else "FAILURES PRESENT")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
