"""Build the combined 290-instance paper battery log (heuristic vs MILP).

Sources (kept consistent with the paper, NOT a blanket results.csv read — the
'latest' igvnd rows for the 120 old configs were overwritten by a later
rerun, so we take them from the June-14 paper log instead):

  * old igvnd (120 x 3): parsed from the named June-14 v01 battery log.
  * new igvnd (170 x 3): the step-2 battery rows in results.csv (ts >= 20260628_0810).
  * MILP (all 290 x 3): latest milp_job_* per (instance,label) from results.csv
    (old = June cache, new = step-2). 2 R30 wMK cells are missing (Gurobi OOM).

Emits a single self-contained log: gap summary table (all 290) + per-instance
MILP-row-then-heuristic-row detail.
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
from gap_summary import format_gap_table          # noqa: E402
from paired_report import detail_block            # noqa: E402

JUN14_LOG = ROOT / "outputs" / "logs" / "instances_main_methods_20260614_114558_iterated_greedy_vnd_v01.log"
CSV = ROOT / "outputs" / "solutions" / "results.csv"
OUT = ROOT / "outputs" / "logs" / "combined_290_main_methods_20260628_081042.log"
STEP2_TS = "20260628_0810"   # new-igvnd rows are at/after this timestamp

MILP_LABELS = {"milp_job_wMK", "milp_job_wDLY", "milp_job_wMOV"}
IGVND_LABELS = {"igvnd_wMK", "igvnd_wDLY", "igvnd_wMOV"}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_old_igvnd(log_path: Path) -> list[dict]:
    pat = re.compile(r"\s+(scn_\S+)\s+(igvnd_w\w+)\s+heuristic_\S*\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(\d+)\s")
    seen: dict[tuple[str, str], dict] = {}
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = pat.match(line)
        if m:
            inst, exp, obj, mk, dly, mov = m.groups()
            seen[(inst, exp)] = {"instance": inst, "experiment": exp, "error": None,
                                 "objective": float(obj), "makespan": float(mk),
                                 "total_delay": float(dly), "movements": float(mov)}
    return list(seen.values())


def main() -> None:
    old_igvnd = parse_old_igvnd(JUN14_LOG)
    old_instances = {r["instance"] for r in old_igvnd}

    # results.csv: latest milp per (inst,label) over all time; new igvnd at step-2 ts.
    milp_latest: dict[tuple[str, str], dict] = {}
    new_igvnd: dict[tuple[str, str], dict] = {}
    for r in csv.reader(open(CSV, newline="")):
        if len(r) < 10:
            continue
        inst, label, ts = r[0], r[2], r[3]
        rec = {"instance": inst, "experiment": label, "error": None,
               "objective": _num(r[6]), "makespan": _num(r[7]),
               "movements": _num(r[8]), "total_delay": _num(r[9])}
        if rec["objective"] is None:
            continue
        key = (inst, label)
        if label in MILP_LABELS:
            if key not in milp_latest or ts > milp_latest[key]["_ts"]:
                rec["_ts"] = ts
                milp_latest[key] = rec
        elif label in IGVND_LABELS and ts >= STEP2_TS:
            if key not in new_igvnd or ts > new_igvnd[key]["_ts"]:
                rec["_ts"] = ts
                new_igvnd[key] = rec

    new_instances = {inst for (inst, _l) in new_igvnd}
    instances = old_instances | new_instances        # the 290

    records: list[dict] = list(old_igvnd)
    records += [dict(r) for r in new_igvnd.values()]
    records += [dict(r) for (inst, _l), r in milp_latest.items() if inst in instances]
    for r in records:
        r.pop("_ts", None)

    n_inst = len({r["instance"] for r in records})
    n_ig = sum(1 for r in records if r["experiment"] in IGVND_LABELS)
    n_mp = sum(1 for r in records if r["experiment"] in MILP_LABELS)

    sep = "=" * 86
    head = (
        f"{sep}\n"
        "  COMBINED PAPER BATTERY — 290 instances (heuristic IGVND v01 vs MILP)\n"
        f"{sep}\n"
        f"  Instances: {n_inst}   igvnd rows: {n_ig}   milp rows: {n_mp}\n"
        "  Sources:\n"
        "    - old 120 configs igvnd : instances_main_methods_20260614_114558_iterated_greedy_vnd_v01.log (60 s, paper battery)\n"
        "    - new 170 configs igvnd : 202605_02_main_methods_20260628_081042.log (60 s, step-2 battery)\n"
        "    - MILP (all)            : outputs/solutions/results.csv, latest milp_job_* per (instance,label)\n"
        "                              (old = June cache, new = step-2; 2 R30 wMK cells missing -> Gurobi OOM)\n"
        f"{sep}\n\n"
    )
    OUT.write_text(head + format_gap_table(records) + "\n\n" + detail_block(records), encoding="utf-8")
    print(f"wrote {OUT}")
    print(f"  instances={n_inst}  igvnd_rows={n_ig}  milp_rows={n_mp}")


if __name__ == "__main__":
    main()
