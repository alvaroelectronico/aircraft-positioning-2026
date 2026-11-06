"""Run (or resume) one arm (solver dir) on the ablation subset in-memory; JSON lines out.
usage: py -3 arm.py <solver_jobs_dir> <out.jsonl> <workers> [subset|file-with-stems]"""
import json, sys, time
from multiprocessing import Pool
from pathlib import Path
ROOT = Path(r"c:/Users/AntoniGuerrero/Desktop/Proyectos Baobab/aircraft-positioning-2026")
W = {"wMK": (100, 1, 1), "wDLY": (1, 100, 1), "wMOV": (1, 1, 100)}

def run(job):
    sdir, stem, pk = job
    sys.path.insert(0, sdir); sys.path.insert(0, str(ROOT / "problems/jobs"))
    from iterated_greedy_vnd import IteratedGreedyVNDJobSolver
    from checker import check_solution
    cfg = stem.rsplit("_seed", 1)[0]
    inst = json.load(open(ROOT / "data/instances_202605_02" / cfg / f"{stem}.json", encoding="utf-8"))
    s = IteratedGreedyVNDJobSolver()
    wm, wd, ws = W[pk]
    s.configure_solver(time_limit_s=60, weight_makespan=wm, weight_delay=wd, weight_movements=ws, seed=1)
    sol = s.solve(inst)
    ok = check_solution(sol, inst)["compliant"]
    return {"inst": stem, "pk": pk, "obj": sol["objective"], **sol["metrics"], "phase": sol.get("phase"),
            "ok": ok, "t": sol["solve_time_s"], "done": s.get_log()[-1]}

if __name__ == "__main__":
    sdir, out, nw = sys.argv[1], sys.argv[2], int(sys.argv[3])
    sys.path.insert(0, str(ROOT / "experiments"))
    if len(sys.argv) > 4 and sys.argv[4] != "subset":
        stems = [l.strip() for l in open(sys.argv[4]) if l.strip()]
    else:
        from ablation_subset import SUBSET as stems
    done = set()
    try:
        done = {(r["inst"], r["pk"]) for r in map(json.loads, open(out))}
    except FileNotFoundError:
        pass
    jobs = [(sdir, st, pk) for st in stems for pk in W if (st, pk) not in done]
    print(f"resuming: {len(done)} done, {len(jobs)} to run", flush=True)
    with Pool(nw) as pool, open(out, "a") as fo:
        for r in pool.imap_unordered(run, jobs):
            fo.write(json.dumps(r) + "\n"); fo.flush()
