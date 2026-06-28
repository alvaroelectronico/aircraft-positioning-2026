"""Generate the LaTeX result tables for the job-level extension paper.

Reads the cached ledger ``outputs/solutions/results.csv`` and emits, into
``papers/jobs_extension/tables/``:

  * ``res_gap_profile.tex``  -- headline relative-gap table (heuristic vs MILP),
                                mean per weight profile + aggregate, by type.
  * ``res_components.tex``    -- per-component mean delta (heuristic - MILP) for
                                makespan / delay / movements, per profile.
  * ``res_milp_conv.tex``     -- MILP convergence: #optimal / #timed-out and mean
                                runtime per type, substantiating the "times out
                                at scale" claim.

Gap convention (matches experiments/gap_summary.py):

    gap = (MILP_obj - heuristic_obj) / MILP_obj      (>0 => heuristic better)

The MILP baseline is fixed; the heuristic rows are the IGVND v01 battery
(labels igvnd_wMK / igvnd_wDLY / igvnd_wMOV).  Run:

    py -3 papers/jobs_extension/make_tables.py
"""
from __future__ import annotations

import csv
import glob
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CSV = ROOT / "outputs" / "solutions" / "results.csv"
OUT = Path(__file__).resolve().parent / "tables"

# (profile key, MILP label, heuristic label, display header)
PROFILES = [
    ("wMK",  "milp_job_wMK",  "igvnd_wMK",  r"$w^{\mathrm{MK}}$"),
    ("wDLY", "milp_job_wDLY", "igvnd_wDLY", r"$w^{\mathrm{DLY}}$"),
    ("wMOV", "milp_job_wMOV", "igvnd_wMOV", r"$w^{\mathrm{MOV}}$"),
]

# display order (mirrors the benchmark matrix) -> (csv type, pretty label)
ROW_ORDER = [
    ("scn_none_tight_P5_R10",      r"None ($R{=}10$)"),
    ("scn_chain_tight_P5_R10",     r"Chain ($R{=}10$)"),
    ("scn_hub_tight_P5_R10",       r"Hub ($R{=}10$)"),
    ("scn_triangle_tight_P5_R10",  r"Triangle ($R{=}10$)"),
    ("scn_two_rows_tight_P5_R10",  r"Two rows ($R{=}10$)"),
    ("scn_full_tight_P5_R10",      r"Full ($R{=}10$)"),
    ("scn_triangle_loose_P5_R10",  r"Triangle, loose"),
    ("scn_triangle_medium_P5_R10", r"Triangle, medium"),
    ("scn_triangle_tight_P5_R5",   r"Triangle ($R{=}5$)"),
    ("scn_triangle_tight_P5_R20",  r"Triangle ($R{=}20$)"),
    ("scn_triangle_tight_P5_R30",  r"Triangle ($R{=}30$)"),
    ("scn_full_tight_P5_R20",      r"Full ($R{=}20$)"),
]


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_latest():
    """Return {(instance,label): row} keeping the latest timestamp per key."""
    latest = {}
    with open(CSV, newline="") as f:
        for r in csv.reader(f):
            if len(r) < 10:
                continue
            inst, _typ, label, ts = r[0], r[1], r[2], r[3]
            key = (inst, label)
            if key not in latest or ts > latest[key][3]:
                latest[key] = r
    return latest


def itype(stem: str) -> str:
    return re.sub(r"_seed\d+$", "", stem)


def collect(latest):
    """type -> profile -> list of dicts with obj/makespan/mov/delay for both."""
    # index objectives by (instance,label)
    byinst = defaultdict(dict)  # instance -> label -> (obj, mk, mov, dly)
    for (inst, label), r in latest.items():
        byinst[inst][label] = (_num(r[6]), _num(r[7]), _num(r[8]), _num(r[9]))
    data = defaultdict(lambda: defaultdict(list))
    for inst, labs in byinst.items():
        t = itype(inst)
        for pk, ml, hl, _ in PROFILES:
            if ml in labs and hl in labs and labs[ml][0] and labs[hl][0]:
                data[t][pk].append((labs[ml], labs[hl]))
    return data


def fmt_pct(x):
    return f"{100*x:+.1f}"


def gap_table(data):
    lines = []
    lines.append(r"\begin{table}[htbp]")
    lines.append(r"  \centering")
    lines.append(r"  \caption{Relative objective gap of IGVND against the MILP "
                 r"baseline, $g = (z_{\mathrm{MILP}} - z_{\mathrm{IGVND}})/"
                 r"z_{\mathrm{MILP}}$ (mean over 10 seeds, in \%). "
                 r"$g>0$ means IGVND attains the \emph{lower} objective. "
                 r"All runs share a 60\,s budget. Table~\ref{tab:milp_conv} "
                 r"reports, per configuration, on how many seeds the MILP "
                 r"reference is a proven optimum rather than a timed-out "
                 r"incumbent.}")
    lines.append(r"  \label{tab:gap_profile}")
    lines.append(r"  \begin{tabular}{lrrrr}")
    lines.append(r"    \toprule")
    hdr = " & ".join(["Configuration"] + [h for *_, h in PROFILES] + ["All"])
    lines.append(f"    {hdr} \\\\")
    lines.append(r"    \midrule")
    for t, label in ROW_ORDER:
        cells = [label]
        allg = []
        for pk, *_ in PROFILES:
            recs = data[t][pk]
            if not recs:
                cells.append("--")
                continue
            gaps = [(m[0] - h[0]) / m[0] for m, h in recs]
            allg += gaps
            cells.append(fmt_pct(sum(gaps) / len(gaps)))
        cells.append(fmt_pct(sum(allg) / len(allg)) if allg else "--")
        lines.append("    " + " & ".join(cells) + r" \\")
    lines.append(r"    \bottomrule")
    lines.append(r"  \end{tabular}")
    lines.append(r"\end{table}")
    return "\n".join(lines) + "\n"


def comp_table(data):
    lines = []
    lines.append(r"\begin{table}[htbp]")
    lines.append(r"  \centering")
    lines.append(r"  \caption{Per-component mean difference (IGVND $-$ MILP) over "
                 r"10 seeds for each weight profile: makespan $\Delta m$, total "
                 r"delay $\Delta D$, movement count $\Delta n$. Negative values "
                 r"favour IGVND. These undistorted differences should be read "
                 r"alongside Table~\ref{tab:gap_profile}, whose relative gap is "
                 r"inflated by small denominators when the optimal delay is "
                 r"near zero.}")
    lines.append(r"  \label{tab:components}")
    lines.append(r"  \begin{tabular}{l*{9}{r}}")
    lines.append(r"    \toprule")
    lines.append(r"    & \multicolumn{3}{c}{$w^{\mathrm{MK}}$}"
                 r" & \multicolumn{3}{c}{$w^{\mathrm{DLY}}$}"
                 r" & \multicolumn{3}{c}{$w^{\mathrm{MOV}}$} \\")
    lines.append(r"    \cmidrule(lr){2-4}\cmidrule(lr){5-7}\cmidrule(lr){8-10}")
    lines.append(r"    Configuration & $\Delta m$ & $\Delta D$ & $\Delta n$"
                 r" & $\Delta m$ & $\Delta D$ & $\Delta n$"
                 r" & $\Delta m$ & $\Delta D$ & $\Delta n$ \\")
    lines.append(r"    \midrule")
    for t, label in ROW_ORDER:
        cells = [label]
        for pk, *_ in PROFILES:
            recs = data[t][pk]
            if not recs:
                cells += ["--", "--", "--"]
                continue
            n = len(recs)
            dm = sum(h[1] - m[1] for m, h in recs) / n
            dd = sum(h[3] - m[3] for m, h in recs) / n
            dn = sum(h[2] - m[2] for m, h in recs) / n
            cells += [f"{dm:+.1f}", f"{dd:+.1f}", f"{dn:+.1f}"]
        lines.append("    " + " & ".join(cells) + r" \\")
    lines.append(r"    \bottomrule")
    lines.append(r"  \end{tabular}")
    lines.append(r"\end{table}")
    return "\n".join(lines) + "\n"


def load_milp_gaps():
    """Latest Gurobi optimality gap (``mip_gap``) per (instance, milp_label).

    ``results.csv`` does not store the gap, only the objective and status; the
    gap lives in each MILP solution JSON.  We keep the latest run per
    (instance, label) by the timestamp embedded in the filename, matching the
    "latest row" rule used elsewhere in this script."""
    wanted = {ml for _, ml, _, _ in PROFILES}
    latest_ts: dict[tuple[str, str], str] = {}
    latest_gap: dict[tuple[str, str], float] = {}
    for f in glob.glob(str(ROOT / "outputs" / "solutions" / "*__milp_job_*__*.json")):
        name = Path(f).name[:-5]            # strip ".json"
        parts = name.split("__")
        if len(parts) != 3:
            continue
        inst, label, ts = parts
        if label not in wanted:
            continue
        key = (inst, label)
        if key in latest_ts and ts <= latest_ts[key]:
            continue
        try:
            gap = json.load(open(f, encoding="utf-8")).get("mip_gap")
        except (OSError, ValueError):
            continue
        if gap is None:
            continue
        latest_ts[key] = ts
        latest_gap[key] = float(gap)
    return latest_gap


def milp_gap_table(gaps):
    """Mean Gurobi optimality gap (%), per type per profile."""
    agg = defaultdict(lambda: defaultdict(list))  # type -> profile -> [gap]
    for (inst, label), g in gaps.items():
        for pk, ml, _, _ in PROFILES:
            if label == ml:
                agg[itype(inst)][pk].append(g)
    lines = []
    lines.append(r"\begin{table}[htbp]")
    lines.append(r"  \centering")
    lines.append(r"  \caption{Mean optimality gap reported by Gurobi within the "
                 r"60\,s budget, per configuration and weight profile (in \%, "
                 r"averaged over 10 seeds). A value of $0.0$ means the MILP is a "
                 r"proven optimum on every seed; a larger value means Gurobi "
                 r"returns a feasible incumbent without closing the bound, so on "
                 r"those configurations a positive $g$ in Table~\ref{tab:gap_profile} "
                 r"means IGVND finds a better feasible solution than the exact "
                 r"solver does in the same time, not that it beats a proven optimum.}")
    lines.append(r"  \label{tab:milp_conv}")
    lines.append(r"  \begin{tabular}{lrrr}")
    lines.append(r"    \toprule")
    lines.append(r"    Configuration & $w^{\mathrm{MK}}$ & $w^{\mathrm{DLY}}$"
                 r" & $w^{\mathrm{MOV}}$ \\")
    lines.append(r"    \midrule")
    for t, label in ROW_ORDER:
        cells = [label]
        for pk, *_ in PROFILES:
            vals = agg[t][pk]
            cells.append(f"{100 * sum(vals) / len(vals):.1f}" if vals else "--")
        lines.append("    " + " & ".join(cells) + r" \\")
    lines.append(r"    \bottomrule")
    lines.append(r"  \end{tabular}")
    lines.append(r"\end{table}")
    return "\n".join(lines) + "\n"


def main():
    OUT.mkdir(exist_ok=True)
    latest = load_latest()
    data = collect(latest)
    (OUT / "res_gap_profile.tex").write_text(gap_table(data), encoding="utf-8")
    (OUT / "res_components.tex").write_text(comp_table(data), encoding="utf-8")
    (OUT / "res_milp_conv.tex").write_text(milp_gap_table(load_milp_gaps()), encoding="utf-8")
    print("wrote:", *(p.name for p in OUT.glob("res_*.tex")))


if __name__ == "__main__":
    main()
