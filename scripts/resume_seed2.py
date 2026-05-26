"""resume_seed2.py — recover the seed2 batch interrupted on 2026-05-25.

The previous run (data/logs/run_experiments_20260525_081504.log) finished
12/12 experiments on 7 instances, partially ran 2 instances where the
3 milp_baseline_* variants aborted, broke off in the middle of
``scn_triangle_tight_P5_R30_seed2`` (missing topology_ms6_wC,
fas_on_topo_wC, safe_pipeline_wC), and never started two more instances
(``scn_triangle_tight_P5_R5_seed2`` and
``scn_two_rows_tight_P5_R10_seed2``).

This script runs ONLY the missing experiments, then merges the new
summary records into the original log file (a ``.bak`` copy is created
first).
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts"))

from run_experiments import (                                  # noqa: E402
    EXPERIMENTS,
    SEED_EXPERIMENTS,
    MULTISTART_EXPERIMENTS,
    INSTANCE_PATHS,
    run_experiments,
    _build_config_header,
    _format_summary,
)

# =============================================================================
#  What needs to be (re-)run
# =============================================================================

WEIGHT_C_TAIL = ["topology_ms6_wC", "fas_on_topo_wC", "safe_pipeline_wC"]
FULL_TWELVE   = [
    "milp_baseline",     "topology_ms6",     "fas_on_topo",     "safe_pipeline",
    "milp_baseline_wB",  "topology_ms6_wB",  "fas_on_topo_wB",  "safe_pipeline_wB",
    "milp_baseline_wC",  "topology_ms6_wC",  "fas_on_topo_wC",  "safe_pipeline_wC",
]

RESUME_PLAN: list[tuple[str, list[str]]] = [
    ("scn_triangle_tight_P5_R30_seed2", WEIGHT_C_TAIL),
    ("scn_triangle_tight_P5_R5_seed2",  FULL_TWELVE),
    ("scn_two_rows_tight_P5_R10_seed2", FULL_TWELVE),
]

ORIG_LOG = _ROOT / "data" / "logs" / "run_experiments_20260525_081504.log"


# =============================================================================
#  Parse the original log into summary records (ok + failed)
# =============================================================================

_OK_ROW_RE = re.compile(
    r"^\s{2,}"
    r"(?P<instance>\S+)\s+"
    r"(?P<experiment>\S+)\s+"
    r"(?P<status>.+?)\s{2,}"
    r"(?P<objective>-?\d+(?:\.\d+)?)\s+"
    r"(?P<makespan>-?\d+(?:\.\d+)?)\s+"
    r"(?P<delay>-?\d+(?:\.\d+)?)\s+"
    r"(?P<movements>\d+)\s+"
    r"(?P<gap>-|\d+(?:\.\d+)?%)\s+"
    r"(?P<time>-?\d+(?:\.\d+)?)\s*$"
)

_FAILED_RE = re.compile(
    r"^\s+x\s+(?P<instance>\S+)\s+·\s+(?P<experiment>\S+)\s+->\s+(?P<err>.+)$"
)


def parse_old_log(text: str) -> list[dict]:
    """Return a list of record dicts in the same shape as run_experiments builds."""
    records: list[dict] = []

    in_failed_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("Failed runs:"):
            in_failed_section = True
            continue
        if not stripped:
            continue
        if stripped.startswith("=") or stripped.startswith("-"):
            continue

        if in_failed_section:
            mf = _FAILED_RE.match(line)
            if mf:
                records.append({
                    "instance":     mf.group("instance"),
                    "experiment":   mf.group("experiment"),
                    "status":       None,
                    "objective":    None,
                    "makespan":     None,
                    "movements":    None,
                    "total_delay":  None,
                    "mip_gap":      None,
                    "solve_time_s": None,
                    "error":        mf.group("err").strip(),
                })
            continue

        m = _OK_ROW_RE.match(line)
        if not m:
            continue
        gap_text = m.group("gap")
        if gap_text == "-":
            mip_gap = None
        else:
            mip_gap = float(gap_text.rstrip("%")) / 100.0
        records.append({
            "instance":     m.group("instance"),
            "experiment":   m.group("experiment"),
            "status":       m.group("status").strip(),
            "objective":    float(m.group("objective")),
            "makespan":     float(m.group("makespan")),
            "movements":    int(m.group("movements")),
            "total_delay":  float(m.group("delay")),
            "mip_gap":      mip_gap,
            "solve_time_s": float(m.group("time")),
            "error":        None,
        })
    return records


# =============================================================================
#  Ordering helpers
# =============================================================================

def _experiment_order_index() -> dict[str, int]:
    """Return {label: order} matching the canonical EXPERIMENTS list order."""
    return {exp["label"]: i for i, exp in enumerate(EXPERIMENTS)}


def merge_records(old: list[dict], new: list[dict]) -> list[dict]:
    """Combine *old* and *new* records, dedup by (instance, experiment).

    Newer entries (those in *new*) win on collisions.
    Output ordering: alphabetical by instance, then by EXPERIMENTS order.
    """
    by_key: dict[tuple[str, str], dict] = {}
    for r in old:
        by_key[(r["instance"], r["experiment"])] = r
    for r in new:
        by_key[(r["instance"], r["experiment"])] = r

    exp_order = _experiment_order_index()
    fallback = len(exp_order) + 1

    return sorted(
        by_key.values(),
        key=lambda r: (r["instance"], exp_order.get(r["experiment"], fallback)),
    )


# =============================================================================
#  Resume execution
# =============================================================================

def _experiments_for_labels(labels: list[str]) -> list[dict]:
    all_exps = EXPERIMENTS + SEED_EXPERIMENTS + MULTISTART_EXPERIMENTS
    wanted = set(labels)
    selected = [e for e in all_exps if e["label"] in wanted]
    # Keep canonical experiment order so warm-cache dependencies resolve.
    selected.sort(key=lambda e: next(
        (i for i, exp in enumerate(EXPERIMENTS) if exp["label"] == e["label"]),
        10_000,
    ))
    return selected


def _instance_path_for(stem: str) -> Path:
    for p in INSTANCE_PATHS:
        if p.stem == stem:
            return p
    raise FileNotFoundError(f"No instance file matches stem '{stem}'")


def run_resume() -> list[dict]:
    """Run every (instance, experiments) entry in RESUME_PLAN and return the
    aggregated list of new summary records.
    """
    new_records: list[dict] = []
    for stem, labels in RESUME_PLAN:
        inst_path = _instance_path_for(stem)
        experiments = _experiments_for_labels(labels)
        print(f"\n>>> Resuming {stem} with {len(experiments)} experiments")
        summary = run_experiments([inst_path], experiments, log_path=None)
        new_records.extend(summary)
    return new_records


# =============================================================================
#  Write the merged log over the original (with .bak)
# =============================================================================

def write_merged_log(merged_records: list[dict], log_path: Path) -> None:
    config_header = _build_config_header(_experiments_for_labels(FULL_TWELVE))

    import io
    buf = io.StringIO()
    buf.write(config_header)
    buf.write("\n")
    _format_summary(buf, merged_records)

    # Backup the original before overwriting
    if log_path.exists():
        bak = log_path.with_suffix(log_path.suffix + ".bak")
        shutil.copy2(log_path, bak)
        print(f"Backup of original log: {bak}")

    log_path.write_text(buf.getvalue(), encoding="utf-8")
    print(f"Merged log written to:  {log_path}")


# =============================================================================
#  Entry point
# =============================================================================

if __name__ == "__main__":
    old_text = ORIG_LOG.read_text(encoding="utf-8")
    old_records = parse_old_log(old_text)
    print(f"Parsed {len(old_records)} records from original log "
          f"({sum(1 for r in old_records if r['error'] is None)} ok / "
          f"{sum(1 for r in old_records if r['error'] is not None)} failed)")

    new_records = run_resume()
    print(f"\nResume run produced {len(new_records)} new records "
          f"({sum(1 for r in new_records if r['error'] is None)} ok / "
          f"{sum(1 for r in new_records if r['error'] is not None)} failed)")

    merged = merge_records(old_records, new_records)
    print(f"Merged total: {len(merged)} records")

    write_merged_log(merged, ORIG_LOG)
