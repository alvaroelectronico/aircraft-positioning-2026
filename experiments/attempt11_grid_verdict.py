"""Two-arm paired verdict for Attempt 11 on the redefined (no-Triangle) grid.

Compares, cell by cell (config x weight profile), the objectives of:
  * the BASELINE arm  (solver on `main`)          -- from a battery log,
  * the CANDIDATE arm (solver on `exp/mode-a-band`) -- from a battery log,
  * the relaxed-MILP reference                     -- latest `milp_job_*`
    rows in outputs/solutions/results.csv (timestamps >= --milp-since).

Both arm logs must come from batteries run ON THE SAME MACHINE (the arms
are judged against each other; the MILP column is context).

Usage:
    py -3 experiments/attempt11_grid_verdict.py \
        --baseline-log  outputs/logs/<baseline_battery>.log \
        --candidate-log outputs/logs/<candidate_battery>.log
    # both flags repeatable if a battery was split across several logs

Output: per-cell table (mean base / cand / MILP, delta, wins/losses),
NET per topology and global, and cells flagged as regressions above the
~19-unit noise floor.  Verdict guidance: KEPT needs a favourable NET with
no consistent (>=7/10 seeds) regressions above noise.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments" / "tests"))
import aggregate_results as A  # noqa: E402

NOISE = 19.0          # ~run-to-run floor (see experiments/BATTERY.md)
PROFILES = ("wMK", "wDLY", "wMOV")
SEEDS = range(1, 11)

# The no-Triangle decision benchmark: 37 configs.
CONFIGS = (
    ["scn_none_tight_P5_R10"]
    + [f"scn_{t}_{s}_P5_R{r}"
       for t in ("chain", "hub", "two_rows")
       for r in (5, 10, 20, 30)
       for s in ("loose", "medium", "tight")]
)


def load_logs(paths: list[str]) -> dict:
    out: dict = {}
    for p in paths:
        for r in A.parse_log(Path(p)):
            if r["experiment"].startswith("igvnd_"):
                out[(r["instance"], r["experiment"])] = r["objective"]
    return out


def load_milp(since: str) -> dict:
    out: dict = {}
    seen: dict = {}
    with open(ROOT / "outputs" / "solutions" / "results.csv",
              newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if len(row) < 10 or not row[2].startswith("milp_job_"):
                continue
            if row[3] < since:
                continue
            key = (row[0], row[2].replace("milp_job_", "igvnd_"))
            if key in seen and seen[key] >= row[3]:
                continue
            try:
                out[key] = float(row[6])
                seen[key] = row[3]
            except ValueError:
                continue
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline-log", action="append", required=True)
    ap.add_argument("--candidate-log", action="append", required=True)
    ap.add_argument("--milp-since", default="20260723_19",
                    help="results.csv timestamp floor for the relaxed-MILP rows")
    args = ap.parse_args()

    base = load_logs(args.baseline_log)
    cand = load_logs(args.candidate_log)
    milp = load_milp(args.milp_since)

    print(f"{'cell':26} {'mean_base':>10} {'mean_cand':>10} {'mean_MILP':>10} "
          f"{'delta':>8} {'W/L':>5}")
    net_total = 0.0
    net_topo: dict = {}
    regressions = []
    missing = []
    for cfg in CONFIGS:
        topo = cfg.split("_")[1] if not cfg.startswith("scn_two_rows") else "two_rows"
        for prof in PROFILES:
            b_, c_, m_, d_ = [], [], [], []
            for seed in SEEDS:
                k = (f"{cfg}_seed{seed}", f"igvnd_{prof}")
                if k in base and k in cand:
                    b_.append(base[k]); c_.append(cand[k]); d_.append(cand[k] - base[k])
                    if k in milp:
                        m_.append(milp[k])
                else:
                    missing.append(k)
            if not b_:
                continue
            mb, mc = sum(b_) / len(b_), sum(c_) / len(c_)
            mm = sum(m_) / len(m_) if m_ else float("nan")
            delta = mc - mb
            net_total += delta * len(b_)
            net_topo[topo] = net_topo.get(topo, 0.0) + delta * len(b_)
            wins = sum(1 for x in d_ if x < -1e-6)
            losses = sum(1 for x in d_ if x > 1e-6)
            flag = ""
            if delta > NOISE and losses >= max(1, round(0.7 * len(d_))):
                flag = "  <<< consistent regression"
                regressions.append((cfg, prof, delta, f"{wins}W/{losses}L"))
            elif delta > NOISE:
                flag = "  <<< above noise (mixed seeds)"
            short = cfg.replace("scn_", "").replace("_P5_", "_")
            print(f"{short:26} {mb:10.1f} {mc:10.1f} {mm:10.1f} "
                  f"{delta:+8.1f} {wins:2}/{losses:<2}{flag}")

    print(f"\nNET global (cand - base): {net_total:+.1f}")
    for topo, v in sorted(net_topo.items()):
        print(f"  NET {topo:10}: {v:+.1f}")
    print(f"\nconsistent regressions above the {NOISE:.0f}-unit floor: "
          f"{regressions if regressions else 'NONE'}")
    if missing:
        print(f"\nWARNING: {len(missing)} (instance, label) pairs missing from "
              f"one of the arms — first few: {missing[:4]}")


if __name__ == "__main__":
    main()
