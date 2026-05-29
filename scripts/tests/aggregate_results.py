"""Aggregate computational results across the 12 benchmark configurations.

Reads the per-configuration log files in data/logs/ that follow the pattern
    scn_<topo>_<slack>_P<n>_R<n>[__extra]_<timestamp>.log
parses each SUMMARY table, computes mean metrics per (configuration, method),
and prints two LaTeX tables to stdout:

  1. Per-configuration means under the default weight profile.
  2. Cross-weight-profile aggregation (default / wB / wC).

Run:
    python scripts/tests/aggregate_results.py
"""
from __future__ import annotations

import re
import statistics
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_LOG_DIR = _ROOT / "data" / "logs"

# Configurations to include, in the row order they will appear in the paper.
# Each entry: (config_key, latex_label, axis_group)
CONFIGS: list[tuple[str, str, str]] = [
    ("scn_none_tight_P5_R10",      r"None ($R{=}10$, tight)",           "Topology"),
    ("scn_chain_tight_P5_R10",     r"Chain ($R{=}10$, tight)",          "Topology"),
    ("scn_hub_tight_P5_R10",       r"Hub ($R{=}10$, tight)",            "Topology"),
    ("scn_triangle_tight_P5_R10",  r"Triangle ($R{=}10$, tight)",       "Topology"),
    ("scn_two_rows_tight_P5_R10",  r"Two rows ($R{=}10$, tight)",       "Topology"),
    ("scn_full_tight_P5_R10",      r"Full ($R{=}10$, tight)",           "Topology"),
    ("scn_triangle_tight_P5_R5",   r"Triangle ($R{=}5$, tight)",        "Size"),
    ("scn_triangle_tight_P5_R20",  r"Triangle ($R{=}20$, tight)",       "Size"),
    ("scn_triangle_tight_P5_R30",  r"Triangle ($R{=}30$, tight)",       "Size"),
    ("scn_triangle_medium_P5_R10", r"Triangle ($R{=}10$, medium)",      "Slack"),
    ("scn_triangle_loose_P5_R10",  r"Triangle ($R{=}10$, loose)",       "Slack"),
    ("scn_full_tight_P5_R20",      r"Full ($R{=}20$, tight)",           "Hard"),
]

METHODS_DEFAULT = ["milp_baseline", "topology_ms6", "fas_on_topo", "safe_pipeline"]
METHODS_HEUR    = ["milp_baseline_heur", "topology_ms6_heur", "fas_on_topo_heur", "safe_pipeline_heur"]
METHODS_WB      = ["milp_baseline_wB", "topology_ms6_wB", "fas_on_topo_wB", "safe_pipeline_wB"]
METHODS_WC      = ["milp_baseline_wC", "topology_ms6_wC", "fas_on_topo_wC", "safe_pipeline_wC"]
METHOD_LABELS = {
    "milp_baseline":  "MILP",
    "topology_ms6":   "Topo",
    "fas_on_topo":    "FAS",
    "safe_pipeline":  "Safe",
}


# Parse a single SUMMARY row.  Format produced by _format_summary in run_experiments.py:
#   "  {instance}  {experiment}  {status:10}  {obj:>10.2f}  {makespan:>9.2f}  {delay:>9.2f}  {mov:>4}  {gap}  {time:>8.1f}"
#
# Status is truncated to 10 chars and may contain spaces (e.g. "topology (").
# All other fields are space-free tokens, so we parse from the right.

def _maybe_float(tok: str) -> float | None:
    """Parse a numeric column token; ``"-"`` / ``"---"`` mean "no value"."""
    if tok in {"-", "---"}:
        return None
    return float(tok)


def _maybe_int(tok: str) -> int | None:
    if tok in {"-", "---"}:
        return None
    return int(tok)


def parse_log(path: Path) -> list[dict]:
    """Return the rows from a log file's SUMMARY section.

    The SUMMARY section is delimited by two ``===`` lines, then a header line
    and a dashes line, followed by one data row per run starting with
    ``"  scn_"``.  We rely on the data-row prefix instead of stateful section
    tracking to keep the parser robust.

    Rows produced by a MILP that never returned a feasible solution use
    ``"-"`` placeholders in the numeric columns; we keep those rows but with
    ``None`` values, so the aggregator can filter them via the status field.
    """
    rows: list[dict] = []
    index: dict[tuple[str, str], int] = {}   # (instance, experiment) -> position in rows
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.startswith("  scn_"):
            continue
        # Last 6 tokens: obj, makespan, delay, movements, gap, time
        toks = raw.split()
        if len(toks) < 9:
            continue
        try:
            time_s   = float(toks[-1])
            gap_tok  = toks[-2]
            mov      = _maybe_int(toks[-3])
            delay    = _maybe_float(toks[-4])
            makespan = _maybe_float(toks[-5])
            obj      = _maybe_float(toks[-6])
        except ValueError:
            continue
        # Remaining prefix is "  {instance}  {experiment}  {status:10}".
        # Status occupies the final 10 chars before the obj field, but may
        # contain spaces, so we instead consume instance and experiment from
        # the left (both are space-free) and treat the rest as status.
        prefix_tokens = toks[:-6]
        if len(prefix_tokens) < 3:
            continue
        inst, exp = prefix_tokens[0], prefix_tokens[1]
        status = " ".join(prefix_tokens[2:]).strip()
        gap = None if gap_tok == "-" else (
            float(gap_tok.rstrip("%")) / 100.0 if gap_tok.endswith("%") else None
        )
        row = {
            "instance":   inst,
            "experiment": exp,
            "status":     status,
            "objective":  obj,
            "makespan":   makespan,
            "delay":      delay,
            "movements":  mov,
            "gap":        gap,
            "time_s":     time_s,
        }
        key = (inst, exp)
        if key in index:
            rows[index[key]] = row   # RESUME section overwrites the original entry
        else:
            index[key] = len(rows)
            rows.append(row)
    return rows


def load_all() -> dict[str, list[dict]]:
    """Return {config_key -> list of rows} using the most recent log per config."""
    log_files = sorted(_LOG_DIR.glob("scn_*.log"))
    # Map config_key -> latest log
    by_cfg: dict[str, Path] = {}
    for f in log_files:
        for cfg_key, _, _ in CONFIGS:
            stem = f.stem
            # Match longest prefix; handles names like
            # "scn_two_rows_tight_P5_R10_seed8_20260523_113339"
            if stem.startswith(cfg_key):
                prev = by_cfg.get(cfg_key)
                if prev is None or f.stat().st_mtime > prev.stat().st_mtime:
                    by_cfg[cfg_key] = f
                break
    rows_by_cfg: dict[str, list[dict]] = {}
    for cfg_key, log_path in by_cfg.items():
        rows_by_cfg[cfg_key] = parse_log(log_path)
    return rows_by_cfg


def load_single_log(log_path: Path | list[Path]) -> dict[str, list[dict]]:
    """Return {config_key -> list of rows} from one or several multi-config logs.

    Each row's instance is matched against the longest CONFIGS prefix to
    determine which configuration bucket it belongs to.  When multiple logs
    are provided, their rows are merged additively (useful when one batch
    failed and a follow-up batch fills in the missing configurations).
    """
    paths = [log_path] if isinstance(log_path, Path) else list(log_path)
    rows_by_cfg: dict[str, list[dict]] = {cfg: [] for cfg, _, _ in CONFIGS}
    cfg_keys = sorted([cfg for cfg, _, _ in CONFIGS], key=len, reverse=True)
    for p in paths:
        for r in parse_log(p):
            for cfg in cfg_keys:
                if r["instance"].startswith(cfg):
                    rows_by_cfg[cfg].append(r)
                    break
    return rows_by_cfg


def mean(vals: list[float]) -> float:
    return statistics.mean(vals) if vals else float("nan")


def _is_no_solution(status: str) -> bool:
    """Return True when *status* indicates the solver never produced a solution.

    Covers:
      * ``"infeasible"`` — legacy build-timeout label used by milp_solver
        before the 2026-05-25 rename.
      * ``"feasible s"`` — current 10-char truncation of
        ``"feasible solution not found (build timeout)"`` written into the
        SUMMARY table.  We also accept the un-truncated form for safety.
    """
    s = (status or "").strip()
    return s == "infeasible" or s.startswith("feasible s")


def aggregate(rows: list[dict], method: str) -> dict:
    """Aggregate one method across all seeds of a configuration."""
    runs = [r for r in rows if r["experiment"] == method and not _is_no_solution(r["status"])]
    if not runs:
        return {"n": 0, "obj": float("nan"), "mks": float("nan"), "dly": float("nan"),
                "mov": float("nan"), "time": float("nan"), "opt": 0, "gap": float("nan")}
    # Optimality counter: runs whose status starts with "optimal"
    n_opt = sum(1 for r in runs if r["status"].lower().startswith("optimal"))
    gaps  = [r["gap"] for r in runs if r["gap"] is not None]
    return {
        "n":    len(runs),
        "obj":  mean([r["objective"] for r in runs]),
        "mks":  mean([r["makespan"]  for r in runs]),
        "dly":  mean([r["delay"]     for r in runs]),
        "mov":  mean([r["movements"] for r in runs]),
        "time": mean([r["time_s"]    for r in runs]),
        "opt":  n_opt,
        "gap":  mean(gaps) if gaps else float("nan"),
    }


def fmt(v: float, decimals: int = 2) -> str:
    if v is None or v != v:   # NaN
        return "---"
    return f"{v:.{decimals}f}"


def n_seeds(data: dict[str, list[dict]]) -> int:
    """Return the maximum number of distinct instances seen across configurations.

    Used to render an accurate "Mean results over N seeds" caption regardless
    of how many seed batches have been merged into *data*.
    """
    return max(
        (len({r["instance"] for r in rows}) for rows in data.values()),
        default=0,
    )


# -----------------------------------------------------------------------------
# Table 1: per-configuration means under the DEFAULT weight profile
# -----------------------------------------------------------------------------

def table_default_profile(data: dict[str, list[dict]]) -> str:
    # Wrapped in a normal `table` + `\resizebox{\textwidth}{!}{...}`: the
    # 21-column tabular is scaled to fit the portrait page width, so
    # NO rotation is needed.  The user explicitly preferred a smaller-
    # font portrait page over any rotated page (sidewaystable rotates
    # the typeset content even though the PDF page stays portrait, which
    # the user found annoying).
    out: list[str] = []
    out.append(r"% This file is autogenerated by scripts/tests/aggregate_results.py.")
    out.append(r"% Do not edit by hand — rerun the script to regenerate.")
    n = n_seeds(data)
    out.append(r"\begin{table}[htbp]")
    out.append(r"  \centering")
    # Check whether any milp_baseline data exists for R=30 configurations
    _r30_milp = any(
        any(r["experiment"] == "milp_baseline" and r.get("objective") is not None
            for r in rows)
        for cfg, rows in data.items() if "R30" in cfg or "tight_P5_R30" in cfg
    )
    _milp_note = (r" MILP results for $R{=}30$ are based on a single usable seed."
                  if _r30_milp else r" MILP is unavailable for $R{=}30$.")
    out.append(r"  \caption{Mean results over " + str(n) + r" seeds per configuration under the default weight profile "
               r"$(W^M, W^D, W^S) = (0.1, 1, 10)$. Columns per method: mean objective $\bar f$, "
               r"mean makespan $\bar m$, mean total delay $\bar v^D$, mean movements $\bar n$, "
               r"and mean wall-clock time $\bar t$ (s)." + _milp_note + r"}")
    out.append(r"  \label{tab:res_default}")
    out.append(r"  \setlength{\tabcolsep}{3pt}%")
    out.append(r"  \scriptsize")
    out.append(r"  \begin{tabular}{l" + ("rrrrr" * 4) + r"}")
    out.append(r"    \toprule")
    # Method header
    head = "    Configuration"
    for m in METHODS_DEFAULT:
        head += f" & \\multicolumn{{5}}{{c}}{{\\textbf{{{METHOD_LABELS[m.replace('_heur','').replace('_wB','').replace('_wC','')]}}}}}"
    out.append(head + r" \\")
    # column subhead
    sub = "    "
    for _ in METHODS_DEFAULT:
        sub += r" & $\bm{\bar{f}}$ & $\bar m$ & $\bar v^D$ & $\bar n$ & $\bar t$"
    out.append(sub + r" \\")
    out.append(r"    \midrule")
    # rows grouped by axis
    cur_axis = None
    for cfg_key, latex_label, axis in CONFIGS:
        if axis != cur_axis:
            if cur_axis is not None:
                out.append(r"    \midrule")
            cur_axis = axis
        rows = data.get(cfg_key, [])
        cells = [latex_label]
        for m in METHODS_DEFAULT:
            agg = aggregate(rows, m)
            f_val = fmt(agg["obj"], 2)
            cells.extend([
                r"\textbf{" + f_val + r"}",
                fmt(agg["mks"], 2),
                fmt(agg["dly"], 2),
                fmt(agg["mov"], 1),
                fmt(agg["time"], 1),
            ])
        out.append("    " + " & ".join(cells) + r" \\")
    out.append(r"    \bottomrule")
    out.append(r"  \end{tabular}")
    out.append(r"\end{table}")
    return "\n".join(out)


# -----------------------------------------------------------------------------
# Table 2: MILP optimality / gap summary across configurations
# -----------------------------------------------------------------------------

def table_optimality(data: dict[str, list[dict]]) -> str:
    out: list[str] = []
    out.append(r"% This file is autogenerated by scripts/tests/aggregate_results.py.")
    out.append(r"% Do not edit by hand — rerun the script to regenerate.")
    out.append(r"\begin{table}[htbp]")
    out.append(r"  \centering\small")
    out.append(r"  \caption{MILP performance under the 60\,s budget per configuration. "
               r"$n$ = number of usable runs (out of " + str(n_seeds(data)) + r" seeds; "
               r"rows aborted by Gurobi or whose Pyomo build exceeded 60\,s are excluded); "
               r"\textit{Opt} = number of instances proved optimal; "
               r"$\overline{\mathrm{gap}}$ = mean Gurobi optimality gap; "
               r"$\overline{t_{\mathrm{MILP}}}$ = mean wall-clock time (s).}")
    out.append(r"  \label{tab:res_milp_opt}")
    out.append(r"  \begin{tabular}{lrrrr}")
    out.append(r"    \toprule")
    out.append(r"    Configuration & $n$ & Opt & $\overline{\mathrm{gap}}$ (\%) & $\overline{t_{\mathrm{MILP}}}$ \\")
    out.append(r"    \midrule")
    cur_axis = None
    for cfg_key, latex_label, axis in CONFIGS:
        if axis != cur_axis:
            if cur_axis is not None:
                out.append(r"    \midrule")
            cur_axis = axis
        rows = data.get(cfg_key, [])
        agg = aggregate(rows, "milp_baseline")
        if agg["n"] == 0:
            out.append(f"    {latex_label} & 0 & --- & --- & --- \\\\")
            continue
        gap_pct = agg["gap"] * 100 if agg["gap"] == agg["gap"] else float("nan")
        out.append(f"    {latex_label} & {agg['n']} & {agg['opt']} & {fmt(gap_pct,2)} & {fmt(agg['time'],1)} \\\\")
    out.append(r"    \bottomrule")
    out.append(r"  \end{tabular}")
    out.append(r"\end{table}")
    return "\n".join(out)


# -----------------------------------------------------------------------------
# Table 3: heuristic-vs-MILP relative gap (only where MILP is available and
# Opt > 0 in at least some configurations).  For each config & method we
# report mean relative gap to the best objective found in that row of methods.
# -----------------------------------------------------------------------------

def best_obj_per_seed(rows: list[dict], methods: list[str]) -> dict[str, float]:
    """For each seed, find the best objective achieved by any of *methods*.

    Rows whose status indicates no feasible solution (``objective`` is None or
    the status flags a build/solve timeout) are skipped — they have no
    objective to compete with.
    """
    by_seed: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        if r["experiment"] not in methods:
            continue
        if r["objective"] is None or _is_no_solution(r["status"]):
            continue
        by_seed[r["instance"]].append(r["objective"])
    return {k: min(v) for k, v in by_seed.items() if v}


def table_method_gap(data: dict[str, list[dict]]) -> str:
    """Mean relative gap of each method to the best objective of that seed."""
    out: list[str] = []
    out.append(r"% This file is autogenerated by scripts/tests/aggregate_results.py.")
    out.append(r"% Do not edit by hand — rerun the script to regenerate.")
    out.append(r"\begin{table}[htbp]")
    out.append(r"  \centering\small")
    out.append(r"  \caption{Mean relative gap (\%) of each method with respect to the best "
               r"objective found across the four methods on the same seed, "
               r"under the default weight profile. The Safe pipeline is the per-seed minimum "
               r"of Topo and FAS, so its gap is always $\leq$ both. Lower is better.}")
    out.append(r"  \label{tab:res_method_gap}")
    out.append(r"  \begin{tabular}{lrrrr}")
    out.append(r"    \toprule")
    out.append(r"    Configuration & MILP & Topo & FAS & Safe \\")
    out.append(r"    \midrule")
    cur_axis = None
    for cfg_key, latex_label, axis in CONFIGS:
        if axis != cur_axis:
            if cur_axis is not None:
                out.append(r"    \midrule")
            cur_axis = axis
        rows = data.get(cfg_key, [])
        best = best_obj_per_seed(rows, METHODS_DEFAULT)
        cells = [latex_label]
        for m in METHODS_DEFAULT:
            gaps_pct: list[float] = []
            for r in rows:
                if r["experiment"] != m:
                    continue
                if r["objective"] is None or _is_no_solution(r["status"]):
                    continue
                b = best.get(r["instance"])
                if b is None or b <= 1e-9:
                    continue
                gaps_pct.append((r["objective"] - b) / b * 100.0)
            cells.append(fmt(mean(gaps_pct), 2) if gaps_pct else "---")
        out.append("    " + " & ".join(cells) + r" \\")
    out.append(r"    \bottomrule")
    out.append(r"  \end{tabular}")
    out.append(r"\end{table}")
    return "\n".join(out)


# -----------------------------------------------------------------------------
# Table 4: weight-profile sensitivity — Safe pipeline objective decomposition
# -----------------------------------------------------------------------------

def table_weight_profiles(data: dict[str, list[dict]]) -> str:
    """Compare safe_pipeline mean (makespan, delay, mov) across the 3 weight profiles."""
    out: list[str] = []
    n = n_seeds(data)
    out.append(r"% This file is autogenerated by scripts/tests/aggregate_results.py.")
    out.append(r"% Do not edit by hand — rerun the script to regenerate.")
    out.append(r"\begin{table}[htbp]")
    out.append(r"  \centering\small")
    out.append(r"  \caption{Effect of the weight profile on the Safe pipeline solution structure. "
               r"Mean $\bar m$, mean total delay $\bar v^D$, and mean movements $\bar n$ "
               r"(averaged over " + str(n) + r" seeds) under the three profiles: "
               r"default $(0.1,1,10)$, wB $(1,10,0.1)$ (delay-priority), wC $(10,0.1,1)$ (makespan-priority).}")
    out.append(r"  \label{tab:res_weights}")
    out.append(r"  \begin{tabular}{l" + ("rrr" * 3) + r"}")
    out.append(r"    \toprule")
    out.append(r"    Configuration & \multicolumn{3}{c}{\textbf{Default}} & \multicolumn{3}{c}{\textbf{wB (delay)}} & \multicolumn{3}{c}{\textbf{wC (makespan)}} \\")
    out.append(r"     & $\bar m$ & $\bar v^D$ & $\bar n$ "
               r"& $\bar m$ & $\bar v^D$ & $\bar n$ "
               r"& $\bar m$ & $\bar v^D$ & $\bar n$ \\")
    out.append(r"    \midrule")
    cur_axis = None
    for cfg_key, latex_label, axis in CONFIGS:
        if axis != cur_axis:
            if cur_axis is not None:
                out.append(r"    \midrule")
            cur_axis = axis
        rows = data.get(cfg_key, [])
        cells = [latex_label]
        for method in ("safe_pipeline", "safe_pipeline_wB", "safe_pipeline_wC"):
            agg = aggregate(rows, method)
            cells.extend([fmt(agg["mks"], 2), fmt(agg["dly"], 2), fmt(agg["mov"], 1)])
        out.append("    " + " & ".join(cells) + r" \\")
    out.append(r"    \bottomrule")
    out.append(r"  \end{tabular}")
    out.append(r"\end{table}")
    return "\n".join(out)


# -----------------------------------------------------------------------------
# Console-only debug summary
# -----------------------------------------------------------------------------

def print_debug_summary(data: dict[str, list[dict]]) -> None:
    print("\n=== Debug summary (rows parsed per configuration / method) ===")
    for cfg_key, latex_label, _ in CONFIGS:
        rows = data.get(cfg_key, [])
        if not rows:
            print(f"  {cfg_key}: NO ROWS")
            continue
        counts: dict[str, int] = defaultdict(int)
        for r in rows:
            counts[r["experiment"]] += 1
        present = ", ".join(f"{m}={counts[m]}" for m in sorted(counts))
        print(f"  {cfg_key}: {present}")


# -----------------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--log",
        type=Path,
        action="append",
        default=None,
        help="Multi-config log to parse; pass multiple times to merge "
             "several batches.  When provided, the per-config log "
             "auto-discovery is skipped.",
    )
    ap.add_argument(
        "--paper-dir",
        type=Path,
        default=_ROOT / "papers" / "cejor_aircraft",
        help="Paper folder whose tables/ subdirectory will receive the "
             "generated LaTeX files.  Defaults to papers/cejor_aircraft.  "
             "Use papers/jobs_extension for paper #2.",
    )
    args = ap.parse_args()

    if args.log:
        data = load_single_log(args.log)
    else:
        data = load_all()
    print_debug_summary(data)
    tables_dir = args.paper_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "res_milp_opt.tex":    table_optimality(data),
        "res_default.tex":     table_default_profile(data),
        "res_method_gap.tex":  table_method_gap(data),
        "res_weights.tex":     table_weight_profiles(data),
    }
    for fname, content in outputs.items():
        (tables_dir / fname).write_text(content + "\n", encoding="utf-8")
        print(f"wrote {tables_dir / fname}")
