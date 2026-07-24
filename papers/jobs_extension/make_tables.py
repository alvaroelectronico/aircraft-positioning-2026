"""Generate the LaTeX result tables for the job-level extension paper.

Built on the **2026-07-13 full battery** (heuristic IGVND v01 at Attempt 7 /
`cbf64c7` vs the cached MILP), **excluding the Full topology**.  Data sources
(kept consistent with the experimentation, NOT a blanket results.csv read):

  * heuristic, ALL 29 configs : parsed from the single battery log
    `202605_02_main_methods_20260714_174533.log` (870 runs / 0 failures;
    results.csv 'latest' igvnd rows are not a reliable paper source — they
    get overwritten by ablation reruns);
  * MILP, all configs         : latest milp_job_* per (instance,label) in
    results.csv, with the Gurobi optimality gap read from the solution JSONs.

Failed MILP runs (Gurobi ran **out of memory** on the largest R=30 instances)
are recorded as the solver being **unable to solve** the instance: those seeds
carry no objective and no gap, and the MILP gap table flags them explicitly.

Emits, into ``papers/jobs_extension/tables/``:
  * res_gap_profile.tex  -- relative gap (heuristic vs MILP), columns
                            Type / R / Slack / one per weight profile / All.
  * res_components.tex    -- per-component mean delta (heuristic - MILP).
  * res_milp_conv.tex     -- mean Gurobi optimality gap, with OOM flagged.

Run:  py -3 papers/jobs_extension/make_tables.py
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
BATTERY_LOG = ROOT / "outputs" / "logs" / "202605_02_main_methods_20260714_174533.log"
OUT = Path(__file__).resolve().parent / "tables"

# (profile key, MILP label, heuristic label, display header)
PROFILES = [
    ("wMK",  "milp_job_wMK",  "igvnd_wMK",  r"$w^{\mathrm{MK}}$"),
    ("wDLY", "milp_job_wDLY", "igvnd_wDLY", r"$w^{\mathrm{DLY}}$"),
    ("wMOV", "milp_job_wMOV", "igvnd_wMOV", r"$w^{\mathrm{MOV}}$"),
]
MILP_LABELS = {ml for _, ml, _, _ in PROFILES}
IGVND_LABELS = {hl for _, _, hl, _ in PROFILES}

TYPE_LABEL = {"none": "None", "chain": "Chain", "hub": "Hub",
              "two_rows": "Two rows", "triangle": "Triangle"}
TYPE_ORDER = {"none": 0, "chain": 1, "hub": 2, "two_rows": 3, "triangle": 4}
SLACK_ORDER = {"loose": 0, "medium": 1, "tight": 2}
EXCLUDE_TOPO = {"full"}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def itype(stem: str) -> str:
    return re.sub(r"_seed\d+$", "", stem)


def parse_stem(stem: str):
    """scn_<topo>_<slack>_P<P>_R<R>  ->  (topo, slack, R)  or None."""
    m = re.match(r"scn_(.+?)_(loose|medium|tight)_P\d+_R(\d+)$", stem)
    if not m:
        return None
    return m.group(1), m.group(2), int(m.group(3))


# ---------------------------------------------------------------------------
# Data loading (combined battery)
# ---------------------------------------------------------------------------

def _parse_battery_igvnd() -> dict:
    """{(instance, igvnd_label): (obj, mk, mov, dly)} from the battery log."""
    pat = re.compile(r"\s+(scn_\S+)\s+(igvnd_w\w+)\s+heuristic_\S*\s+"
                     r"([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(\d+)\s")
    out = {}
    for line in BATTERY_LOG.read_text(encoding="utf-8", errors="replace").splitlines():
        m = pat.match(line)
        if m:
            inst, exp, obj, mk, dly, mov = m.groups()
            out[(inst, exp)] = (float(obj), float(mk), float(mov), float(dly))
    return out


def load_combined() -> dict:
    """instance -> label -> (obj, mk, mov, dly): heuristic from the battery
    log, MILP (latest per instance/label) from the cached results.csv."""
    byinst: dict[str, dict] = defaultdict(dict)

    # heuristic — single fresh battery log (all 29 configs)
    for (inst, label), tup in _parse_battery_igvnd().items():
        byinst[inst][label] = tup

    # MILP (latest) from the cached ledger
    milp_ts: dict[tuple, str] = {}
    for r in csv.reader(open(CSV, newline="")):
        if len(r) < 10:
            continue
        inst, label, ts = r[0], r[2], r[3]
        obj = _num(r[6])
        if obj is None:
            continue
        tup = (obj, _num(r[7]), _num(r[8]), _num(r[9]))   # obj, mk, mov, dly
        key = (inst, label)
        if label in MILP_LABELS:
            if key not in milp_ts or ts > milp_ts[key]:
                milp_ts[key] = ts
                byinst[inst][label] = tup
    return byinst


def load_milp_gaps() -> dict:
    """Latest Gurobi optimality gap per (instance, milp_label) from the MILP
    solution JSONs (results.csv stores status, not the gap)."""
    latest_ts, latest_gap = {}, {}
    for f in glob.glob(str(ROOT / "outputs" / "solutions" / "*__milp_job_*__*.json")):
        name = Path(f).name[:-5]
        parts = name.split("__")
        if len(parts) != 3 or parts[1] not in MILP_LABELS:
            continue
        inst, label, ts = parts
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


def config_rows(byinst: dict) -> list:
    """Ordered list of (stem, topo, slack, R) for every non-Full config."""
    rows = []
    for stem in {itype(i) for i in byinst}:
        parsed = parse_stem(stem)
        if not parsed:
            continue
        topo, slack, R = parsed
        if topo in EXCLUDE_TOPO:
            continue
        rows.append((stem, topo, slack, R))
    rows.sort(key=lambda x: (TYPE_ORDER.get(x[1], 9), x[3], SLACK_ORDER.get(x[2], 9)))
    return rows


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

def _desc_cells(topo, slack, R, prev):
    """Type / R / Slack cells; blank Type/R when repeated from the previous row."""
    t = TYPE_LABEL.get(topo, topo)
    pt, pR = prev
    type_cell = "" if t == pt else t
    r_cell = "" if (t == pt and R == pR) else str(R)
    return type_cell, r_cell, slack


def gap_table(byinst, rows) -> str:
    out = [r"\begin{table}[htbp]", r"  \centering",
           r"  \caption{Relative objective gap of IGVND against the MILP "
           r"baseline, $g = (z_{\mathrm{MILP}} - z_{\mathrm{IGVND}})/"
           r"z_{\mathrm{MILP}}$ (mean over 10 seeds, in \%). $g>0$ means IGVND "
           r"attains the \emph{lower} objective. All runs share a 60\,s budget. "
           r"Table~\ref{tab:milp_conv} reports the MILP's optimality gap per "
           r"configuration; where it is large the MILP reference is a timed-out "
           r"incumbent, not a proven optimum.}",
           r"  \label{tab:gap_profile}",
           r"  \begin{tabular}{lll rrr r}", r"    \toprule",
           r"    Type & $R$ & Slack & $w^{\mathrm{MK}}$ & $w^{\mathrm{DLY}}$"
           r" & $w^{\mathrm{MOV}}$ & All \\", r"    \midrule"]
    prev = (None, None)
    for stem, topo, slack, R in rows:
        insts = [i for i in byinst if itype(i) == stem]
        cells = list(_desc_cells(topo, slack, R, prev))
        prev = (TYPE_LABEL.get(topo, topo), R)
        allg = []
        for pk, ml, hl, _ in PROFILES:
            gs = [(byinst[i][ml][0] - byinst[i][hl][0]) / byinst[i][ml][0]
                  for i in insts if ml in byinst[i] and hl in byinst[i] and byinst[i][ml][0]]
            allg += gs
            cells.append(f"{100 * sum(gs) / len(gs):+.1f}" if gs else "--")
        cells.append(f"{100 * sum(allg) / len(allg):+.1f}" if allg else "--")
        out.append("    " + " & ".join(cells) + r" \\")
    out += [r"    \bottomrule", r"  \end{tabular}", r"\end{table}"]
    return "\n".join(out) + "\n"


def comp_table(byinst, rows) -> str:
    out = [r"\begin{table}[htbp]", r"  \centering", r"  \footnotesize",
           r"  \caption{Per-component mean difference (IGVND $-$ MILP) over 10 "
           r"seeds for each weight profile: makespan $\Delta m$, total delay "
           r"$\Delta D$, movement count $\Delta n$. Negative values favour "
           r"IGVND. Read alongside Table~\ref{tab:gap_profile}, whose relative "
           r"gap is inflated by small denominators when the optimal delay is "
           r"near zero.}",
           r"  \label{tab:components}",
           r"  \begin{tabular}{lll *{9}{r}}", r"    \toprule",
           r"    & & & \multicolumn{3}{c}{$w^{\mathrm{MK}}$}"
           r" & \multicolumn{3}{c}{$w^{\mathrm{DLY}}$}"
           r" & \multicolumn{3}{c}{$w^{\mathrm{MOV}}$} \\",
           r"    \cmidrule(lr){4-6}\cmidrule(lr){7-9}\cmidrule(lr){10-12}",
           r"    Type & $R$ & Slack"
           r" & $\Delta m$ & $\Delta D$ & $\Delta n$"
           r" & $\Delta m$ & $\Delta D$ & $\Delta n$"
           r" & $\Delta m$ & $\Delta D$ & $\Delta n$ \\", r"    \midrule"]
    prev = (None, None)
    for stem, topo, slack, R in rows:
        insts = [i for i in byinst if itype(i) == stem]
        cells = list(_desc_cells(topo, slack, R, prev))
        prev = (TYPE_LABEL.get(topo, topo), R)
        for pk, ml, hl, _ in PROFILES:
            pairs = [(byinst[i][ml], byinst[i][hl]) for i in insts
                     if ml in byinst[i] and hl in byinst[i]]
            if not pairs:
                cells += ["--", "--", "--"]
                continue
            n = len(pairs)
            dm = sum(h[1] - m[1] for m, h in pairs) / n      # makespan
            dd = sum(h[3] - m[3] for m, h in pairs) / n      # delay
            dn = sum(h[2] - m[2] for m, h in pairs) / n      # movements
            cells += [f"{dm:+.1f}", f"{dd:+.1f}", f"{dn:+.1f}"]
        out.append("    " + " & ".join(cells) + r" \\")
    out += [r"    \bottomrule", r"  \end{tabular}", r"\end{table}"]
    return "\n".join(out) + "\n"


def milp_gap_table(byinst, rows, gaps) -> str:
    body = []
    any_oom = False
    prev = (None, None)
    for stem, topo, slack, R in rows:
        insts = [i for i in byinst if itype(i) == stem]
        cells = list(_desc_cells(topo, slack, R, prev))
        prev = (TYPE_LABEL.get(topo, topo), R)
        for pk, ml, hl, _ in PROFILES:
            # seeds the heuristic ran (expected MILP coverage) vs MILP solved
            expected = [i for i in insts if hl in byinst[i]]
            solved = [gaps[(i, ml)] for i in expected if (i, ml) in gaps]
            n_oom = len(expected) - len(solved)
            if n_oom:
                any_oom = True
            if not solved:
                cells.append(r"\textsc{oom}" if n_oom else "--")
            else:
                txt = f"{100 * sum(solved) / len(solved):.1f}"
                if n_oom:
                    txt += rf"$^{{({n_oom})}}$"
                cells.append(txt)
        body.append("    " + " & ".join(cells) + r" \\")
    caption = (r"Mean optimality gap reported by Gurobi within the 60\,s "
               r"budget, per configuration and weight profile (in \%, over 10 "
               r"seeds). $0.0$ means a proven optimum on every seed; a larger "
               r"value means Gurobi returns a feasible incumbent without "
               r"closing the bound.")
    if any_oom:
        caption += (r" A superscript $(k)$ marks the $k$ seeds on which Gurobi "
                    r"\emph{ran out of memory and returned no solution at all} "
                    r"-- the MILP could not solve the instance; the reported "
                    r"value averages the remaining seeds. \textsc{oom} marks a "
                    r"configuration the MILP could not solve on any seed.")
    out = [r"\begin{table}[htbp]", r"  \centering",
           rf"  \caption{{{caption}}}",
           r"  \label{tab:milp_conv}",
           r"  \begin{tabular}{lll rrr}", r"    \toprule",
           r"    Type & $R$ & Slack & $w^{\mathrm{MK}}$ & $w^{\mathrm{DLY}}$"
           r" & $w^{\mathrm{MOV}}$ \\", r"    \midrule"]
    out += body
    out += [r"    \bottomrule", r"  \end{tabular}", r"\end{table}"]
    return "\n".join(out) + "\n"


def main():
    OUT.mkdir(exist_ok=True)
    byinst = load_combined()
    rows = config_rows(byinst)
    gaps = load_milp_gaps()
    (OUT / "res_gap_profile.tex").write_text(gap_table(byinst, rows), encoding="utf-8")
    (OUT / "res_components.tex").write_text(comp_table(byinst, rows), encoding="utf-8")
    (OUT / "res_milp_conv.tex").write_text(milp_gap_table(byinst, rows, gaps), encoding="utf-8")
    print(f"wrote 3 tables for {len(rows)} configs (Full excluded)")


if __name__ == "__main__":
    main()
