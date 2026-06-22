"""Structural diagnosis of a saved solution — where does the gap come from?

Read-only: it loads a solution JSON (+ its instance), rebuilds the model, and
reports the structural breakdown that decides which improvement pays off:

  * front/rear aircraft split and per-position occupancy,
  * access-mode counts (A / B / C) over every blocking arc + access instant,
  * total rear "wait" induced by blocking (start − earliest-possible start),
  * delay and the critical aircraft that set the makespan,
  * which front positions block the most rear accesses.

It does NOT change the solver and needs no new runs.  (Solver-internal counters
like "Mode-C candidates rejected by reason" would need instrumentation; this
analyses the realised schedule, which already localises the deficit.)

Usage:
    py -3 methods/theory_assisted/jobs/brkga/diagnose.py <solution.json> [more.json ...]
    py -3 methods/theory_assisted/jobs/brkga/diagnose.py --latest <inst_substr> <label>
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_JOBS = _HERE.parent
_ROOT = _JOBS.parent.parent.parent
for _p in (str(_JOBS), str(_ROOT / "shared"), str(_ROOT / "problems" / "jobs")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import json

from instance_io import load_json                 # noqa: E402
from brkga.instance import build_model            # noqa: E402
from brkga.access import classify_access          # noqa: E402

_INST_ROOT = _ROOT / "data" / "instances_202605_02"


def _find_instance(stem: str) -> Path:
    hits = list(_INST_ROOT.rglob(f"{stem}.json"))
    if not hits:
        raise FileNotFoundError(f"instance {stem} not found under {_INST_ROOT}")
    return hits[0]


def diagnose(sol_path: Path) -> dict:
    sol = json.loads(sol_path.read_text(encoding="utf-8"))
    inst = load_json(_find_instance(sol["instance"]))
    model = build_model(inst)

    ac = {a["id"]: a for a in sol["aircraft"]}
    pos_of = {a["id"]: a["position"] for a in sol["aircraft"]}
    by_pos: dict[str, list[str]] = defaultdict(list)
    for a in sol["aircraft"]:
        by_pos[a["position"]].append(a["id"])
    for p in by_pos:
        by_pos[p].sort(key=lambda r: ac[r]["start"])

    makespan = max(a["finish"] for a in sol["aircraft"])
    total_delay = sum(a["delay"] for a in sol["aircraft"])
    critical = [a["id"] for a in sol["aircraft"] if abs(a["finish"] - makespan) < 1e-6]

    rear_positions = {p for p in model.positions if model.fronts_of.get(p)}
    n_front = sum(1 for a in sol["aircraft"] if pos_of[a["id"]] not in rear_positions)
    n_rear = len(sol["aircraft"]) - n_front

    # Access-mode counts and per-front-position blocking, replicating the checker loop.
    mode = defaultdict(int)
    block_by_front = defaultdict(int)
    for (p_front, p_rear) in model.arcs:
        for rf in by_pos.get(p_front, []):
            F = ac[rf]
            jobints = [(j["id"], j["start"], j["finish"]) for j in F["jobs"]]
            for rr in by_pos.get(p_rear, []):
                if rr == rf:
                    continue
                R = ac[rr]
                for tau in (R["start"], R["finish"]):
                    k = classify_access(tau, F["start"], F["finish"], jobints, model)
                    mode[k] += 1
                    if k in ("B", "C"):
                        block_by_front[p_front] += 1

    # Rear "wait": start minus the earliest it could start (E_r, prev+eps).
    total_wait = 0.0
    wait_by_air: dict[str, float] = {}
    for p in model.positions:
        prev_finish = None
        for r in by_pos.get(p, []):
            lower = model.earliest_start[r]
            if prev_finish is not None:
                lower = max(lower, prev_finish + model.epsilon)
            w = max(0.0, ac[r]["start"] - lower)
            if p in rear_positions:
                total_wait += w
                wait_by_air[r] = w
            prev_finish = ac[r]["finish"]

    worst_wait = sorted(wait_by_air.items(), key=lambda kv: -kv[1])[:5]

    return {
        "instance": sol["instance"],
        "label": sol.get("label", "?"),
        "objective": sol["objective"],
        "makespan": makespan,
        "total_delay": total_delay,
        "movements": sol["metrics"]["movements"],
        "status": sol.get("status", "?"),
        "n_front": n_front,
        "n_rear": n_rear,
        "modeA": mode["A"], "modeB": mode["B"], "modeC": mode["C"],
        "infeasible": mode["infeasible"],
        "total_rear_wait": total_wait,
        "worst_wait": worst_wait,
        "critical": critical,
        "block_by_front": dict(block_by_front),
    }


def _print(d: dict) -> None:
    print(f"\n=== {d['instance']}  [{d['label']}]  obj={d['objective']:.1f} ===")
    print(f"  status            : {d['status']}")
    print(f"  makespan={d['makespan']:.1f}  delay={d['total_delay']:.1f}  movements={d['movements']}")
    print(f"  aircraft          : {d['n_front']} front-pos / {d['n_rear']} rear-pos")
    print(f"  access modes       : A={d['modeA']}  B={d['modeB']}  C={d['modeC']}  infeasible={d['infeasible']}")
    print(f"  total rear wait    : {d['total_rear_wait']:.1f}  (start minus earliest-possible, summed over rear aircraft)")
    print(f"  worst rear waits   : " + ", ".join(f"{r}={w:.1f}" for r, w in d['worst_wait']))
    print(f"  makespan-critical  : {d['critical']}")
    print(f"  blocking by front  : {d['block_by_front']}")


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1
    if args[0] == "--latest":
        substr, label = args[1], args[2]
        cands = sorted((p for p in (_ROOT / "outputs" / "solutions").glob("*.json")
                        if substr in p.name and f"__{label}__" in p.name),
                       key=lambda p: p.stat().st_mtime)
        if not cands:
            print(f"no solution matching {substr} / {label}")
            return 1
        paths = [cands[-1]]
    else:
        paths = [Path(a) for a in args]
    for p in paths:
        _print(diagnose(p))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
