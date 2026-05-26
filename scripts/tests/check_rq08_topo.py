"""Quick RQ08 audit on existing topology_ms6 solutions."""
import json, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "output_data"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "input_data"))
from check_solution import check_solution
from instance_io import load_json

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")

pairs = [
    ("data/experiment_instances/scn_many-medium_seed1_P5_pl20.json",
     "data/solutions/scn_many-medium_seed1_P5_pl20__topology_ms6__20260514_094643.json"),
    ("data/experiment_instances/scn_custom_many_tight_pl10.json",
     "data/solutions/scn_custom_many_tight_pl10__topology_ms6__20260514_093617.json"),
    ("data/experiment_instances/scn_heavy-tight_seed1_P4_pl30.json",
     "data/solutions/scn_heavy-tight_seed1_P4_pl30__topology_ms6__20260514_094232.json"),
    ("data/experiment_instances/scn_few-loose_seed1_P3_pl5.json",
     "data/solutions/scn_few-loose_seed1_P3_pl5__topology_ms6__20260514_093727.json"),
    ("data/experiment_instances/scn_few-tight_seed1_P2_pl5.json",
     "data/solutions/scn_few-tight_seed1_P2_pl5__topology_ms6__20260514_093838.json"),
]

print(f"{'Instance':<35} {'RQ08':6} {'viol':5} {'min_gap':10} {'worst':8}")
print("-" * 70)
for inst_p, sol_p in pairs:
    inst = load_json(os.path.join(ROOT, inst_p))
    with open(os.path.join(ROOT, sol_p)) as f:
        sol = json.load(f)
    rep = check_solution(sol, inst)
    rq08 = rep["requirements"]["RQ08"]
    name = os.path.basename(inst_p).replace(".json", "")[:34]
    status = "PASS" if rq08["pass"] else "FAIL"
    mg = f"{rq08['min_same_pos_gap']:.2f}" if rq08["min_same_pos_gap"] is not None else "N/A"
    print(f"{name:<35} {status:6} {rq08['num_violations']:5} {mg:>10} {rq08['worst_violation']:8.2f}")
    if rq08["violations"]:
        for v in rq08["violations"][:3]:
            print(f"  -> pos={v['position']} {v['first']}→{v['second']} gap={v['gap']:.2f} shortfall={v['shortfall']:.2f}")
