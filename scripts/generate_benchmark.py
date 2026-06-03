"""
generate_benchmark.py — Benchmark instance generator for aircraft positioning.

Generates JSON instances directly (no xlsx intermediate) with configurable:
  - Hangar topology (blocking arc structure)
  - Number of positions (P)
  - Number of aircraft (R)
  - Slack level (tight / medium / loose)
  - Random seed

Usage
-----
    python scripts/generate_benchmark.py               # generate all instances
    python scripts/generate_benchmark.py --dry-run     # preview without writing
    python scripts/generate_benchmark.py --outdir PATH # write to alternative directory
    python scripts/generate_benchmark.py --filter chain_tight  # substring filter on filename
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_ROOT       = Path(__file__).resolve().parents[1]
_SCHEMA     = _ROOT / "scripts" / "input_data" / "instance_schema.json"
_OUTPUT_DIR = _ROOT / "data" / "experiment_instances"

# ---------------------------------------------------------------------------
# Generation defaults
# ---------------------------------------------------------------------------

# Integer uniform range for job processing times.
DEFAULT_DURATION_RANGE: tuple[int, int] = (3, 8)

# Tow-in/tow-out time epsilon, in the same time units as durations.
# Stored per-instance so each instance is self-contained.
DEFAULT_MIN_SEPARATION: float = 0.5

# Paper-#2 optional parameters; written verbatim to every generated instance
# so the file is self-describing for both papers.  See check_solution_jobs_v2.
DEFAULT_MU:            float = 1.0     # Mode-B inter-job pause
DEFAULT_DELTA:         float = 2.0     # Mode-C job extension
DEFAULT_ETA:           float = 1.0     # strict-inequality granularity
DEFAULT_INTERRUPTIBLE: bool  = False   # per-job flag

# Slack ratio applied to L_r = E_r + D_r + ceil(rho * D_r).
SLACK_PARAMS: dict[str, float] = {
    "loose":  0.80,
    "medium": 0.35,
    "tight":  0.05,
}

# ---------------------------------------------------------------------------
# Hangar topology builders
# Each receives a list of position names and returns blocking_arcs list.
# ---------------------------------------------------------------------------

def build_none(positions: list[str]) -> list[dict]:
    """No blocking arcs — positions are fully independent."""
    return []


def build_chain(positions: list[str]) -> list[dict]:
    """Linear row: each position blocks the next one.

    P1 → P2 → P3 → ... → Pn
    Physically: positions arranged in a single file; exiting Pk requires
    moving all Pi with i < k first.
    """
    return [{"front": positions[i], "rear": positions[i + 1]}
            for i in range(len(positions) - 1)]


def build_hub(positions: list[str]) -> list[dict]:
    """Star topology: P1 (front/aisle position) blocks all others.

    Physically: one central aisle position in front of all hangar slots.
    """
    front = positions[0]
    return [{"front": front, "rear": p} for p in positions[1:]]


def build_triangle(positions: list[str]) -> list[dict]:
    """Reproduces the current benchmark topology.

    The last three positions form a triangle (fully connected):
    P[-3] → P[-2], P[-3] → P[-1], P[-2] → P[-1].
    Remaining positions have no blocking arcs.
    This matches the existing P3→P4, P3→P5, P4→P5 layout when len=5.
    """
    if len(positions) < 3:
        return []
    a, b, c = positions[-3], positions[-2], positions[-1]
    return [
        {"front": a, "rear": b},
        {"front": a, "rear": c},
        {"front": b, "rear": c},
    ]


def build_two_rows(positions: list[str]) -> list[dict]:
    """Two-row layout: front half blocks corresponding rear half.

    For P positions: front row = positions[:P//2], rear row = positions[P//2:].
    Each front position blocks the rear position at the same index.
    Physically: two parallel rows in the hangar; front row blocks access to rear.
    """
    mid = len(positions) // 2
    front_row = positions[:mid]
    rear_row  = positions[mid:mid + len(front_row)]
    return [{"front": f, "rear": r} for f, r in zip(front_row, rear_row)]


def build_full(positions: list[str]) -> list[dict]:
    """All pairs blocked — maximally constrained topology.

    Every position blocks all positions that follow it in the list.
    """
    arcs = []
    for i, f in enumerate(positions):
        for r in positions[i + 1:]:
            arcs.append({"front": f, "rear": r})
    return arcs


TOPOLOGY_BUILDERS: dict[str, Callable[[list[str]], list[dict]]] = {
    "none":     build_none,
    "chain":    build_chain,
    "hub":      build_hub,
    "triangle": build_triangle,
    "two_rows": build_two_rows,
    "full":     build_full,
}

# ---------------------------------------------------------------------------
# Instance generation
# ---------------------------------------------------------------------------

def _sample_duration(rng: np.random.Generator, p_min: int = 3, p_max: int = 8) -> int:
    """Integer uniform sample on {p_min, ..., p_max}."""
    return int(rng.integers(p_min, p_max + 1))


def _make_aircraft(
    rng: np.random.Generator,
    n_aircraft: int,
    n_positions: int,
    tasks_range: tuple[int, int],
    slack: str,
    duration_range: tuple[int, int],
) -> tuple[list[dict], list[dict], list[dict]]:
    """Generate aircraft, jobs, and job_precedences lists.

    All temporal quantities are integers.  Feasibility is guaranteed by
    target_finish = earliest_start + total_duration + max(1, ceil(rho * D_r)),
    so target_finish - earliest_start >= total_duration + 1.
    """
    p_min, p_max = duration_range
    avg_p = (p_min + p_max) / 2.0
    # Arrival spread: scales naturally with the steady-state span of the fleet
    # (R aircraft / P positions × average aircraft block).  No reference to a
    # global horizon.
    spread = max(1, math.ceil(n_aircraft * avg_p / n_positions))
    rho = SLACK_PARAMS[slack]
    n_clients = max(2, min(6, n_aircraft // 2))

    aircrafts: list[dict]       = []
    jobs: list[dict]            = []
    precedences: list[dict]     = []

    for r in range(1, n_aircraft + 1):
        n_tasks = int(rng.integers(tasks_range[0], tasks_range[1] + 1))
        durations = [_sample_duration(rng, p_min, p_max) for _ in range(n_tasks)]
        total_dur = sum(durations)                          # int

        es = int(rng.integers(0, spread + 1))               # int in {0, ..., S}
        slack_units = max(1, math.ceil(rho * total_dur))    # guarantees +1 unit margin
        tf = es + total_dur + slack_units                   # int

        client_id = f"C{int(rng.integers(1, n_clients + 1))}"
        aircraft_id = f"R{r}"

        aircrafts.append({
            "id":             aircraft_id,
            "client":         client_id,
            "earliest_start": es,
            "target_finish":  tf,
        })

        job_ids: list[str] = []
        for t, dur in enumerate(durations, start=1):
            job_id = f"J{r}-{t}"
            jobs.append({
                "id":            job_id,
                "aircraft_id":   aircraft_id,
                "duration":      int(dur),
                "is_first":      t == 1,
                "is_last":       t == n_tasks,
                "interruptible": DEFAULT_INTERRUPTIBLE,  # paper-#2 flag; ignored by paper-#1
            })
            job_ids.append(job_id)

        for t in range(len(job_ids) - 1):
            precedences.append({"before": job_ids[t], "after": job_ids[t + 1]})

    return aircrafts, jobs, precedences


def generate_instance(
    topology: str,
    slack: str,
    n_positions: int,
    n_aircraft: int,
    tasks_range: tuple[int, int],
    seed: int,
    duration_range: tuple[int, int] = DEFAULT_DURATION_RANGE,
    min_separation: float = DEFAULT_MIN_SEPARATION,
) -> dict:
    """Generate and return a single validated instance dict.

    Parameters
    ----------
    topology:
        Name of a key in TOPOLOGY_BUILDERS.
    slack:
        One of 'loose', 'medium', 'tight'.
    n_positions:
        Number of hangar positions (P).
    n_aircraft:
        Number of aircraft (R).
    tasks_range:
        (min_tasks, max_tasks) per aircraft (inclusive).
    seed:
        Random seed for reproducibility.
    duration_range:
        Integer uniform range {p_min, ..., p_max} for job durations.
        Defaults to ``DEFAULT_DURATION_RANGE``.
    """
    if topology not in TOPOLOGY_BUILDERS:
        raise ValueError(f"Unknown topology '{topology}'. Available: {sorted(TOPOLOGY_BUILDERS)}")
    if slack not in SLACK_PARAMS:
        raise ValueError(f"Unknown slack '{slack}'. Available: {sorted(SLACK_PARAMS)}")

    rng = np.random.default_rng(seed)

    positions = [f"P{i}" for i in range(1, n_positions + 1)]
    blocking_arcs = TOPOLOGY_BUILDERS[topology](positions)

    aircrafts, jobs, precedences = _make_aircraft(
        rng, n_aircraft, n_positions, tasks_range, slack, duration_range,
    )

    instance = {
        "min_separation": min_separation,
        "mu":             DEFAULT_MU,     # paper-#2 default; ignored by paper-#1
        "delta":          DEFAULT_DELTA,  # paper-#2 default; ignored by paper-#1
        "eta":            DEFAULT_ETA,    # paper-#2 default; ignored by paper-#1
        "hangar": {
            "positions":     positions,
            "blocking_arcs": blocking_arcs,
        },
        "aircrafts":       aircrafts,
        "jobs":            jobs,
        "job_precedences": precedences,
    }
    _validate(instance)
    return instance


def _validate(data: dict) -> None:
    """Validate against instance_schema.json (same schema used by instance_io.py)."""
    try:
        import jsonschema
    except ImportError:
        return  # skip validation if jsonschema not installed
    with open(_SCHEMA, encoding="utf-8") as f:
        schema = json.load(f)
    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as exc:
        raise ValueError(f"Generated instance failed schema validation: {exc.message}") from exc


# ---------------------------------------------------------------------------
# Benchmark specification
# ---------------------------------------------------------------------------

@dataclass
class BenchmarkGroup:
    topology:    str
    slack:       str
    n_positions: int
    n_aircraft:  int
    tasks_range: tuple[int, int]
    seeds:       range | list[int] = field(default_factory=lambda: range(1, 4))
    duration_range: tuple[int, int] = DEFAULT_DURATION_RANGE
    min_separation: float = DEFAULT_MIN_SEPARATION

    def filename(self, seed: int) -> str:
        return (
            f"scn_{self.topology}_{self.slack}"
            f"_P{self.n_positions}_R{self.n_aircraft}_seed{seed}.json"
        )


# =============================================================================
#  BENCHMARK_SPEC — edit this list to change the generated benchmark set
#
#  BenchmarkGroup(topology, slack, n_positions, n_aircraft, tasks_range, seeds)
#
#  Topologies : none | chain | hub | triangle | two_rows | full
#  Slack      : loose | medium | tight
#
#  Design (instances_202605):
#   • 10 seeds per configuration
#   • Three independent axes — topology, size, slack — each varied while
#     the others are held constant, so effects are separable.
#   • Fixed baseline: P=5, tight, tasks=(4,6); triangle is the "current" topology.
#
#  Axis 1 — Topology (fixed R=10, P=5, tight):
#    none, chain, hub, triangle, two_rows, full  → 6 configs
#  Axis 2 — Size (fixed triangle, tight):
#    R=5, R=10, R=20, R=30  (R=10 shared with Axis 1)  → 3 extra configs
#  Axis 3 — Slack (fixed triangle, R=10):
#    loose, medium  (tight already in Axis 1)  → 2 extra configs
#  Axis 4 — Hard large (full, tight, R=20):
#    Maximum blocking at large scale  → 1 extra config
#
#  Total: 12 configs × 10 seeds = 120 instances
# =============================================================================

_S10 = range(1, 11)  # 10 seeds

BENCHMARK_SPEC: list[BenchmarkGroup] = [

    # ── Axis 1: Topology comparison ───────────────────────────────────────────
    # R=10, P=5, tight — isolates the effect of blocking structure
    BenchmarkGroup("none",     "tight", n_positions=5, n_aircraft=10, tasks_range=(4, 6), seeds=_S10),
    BenchmarkGroup("chain",    "tight", n_positions=5, n_aircraft=10, tasks_range=(4, 6), seeds=_S10),
    BenchmarkGroup("hub",      "tight", n_positions=5, n_aircraft=10, tasks_range=(4, 6), seeds=_S10),
    BenchmarkGroup("triangle", "tight", n_positions=5, n_aircraft=10, tasks_range=(4, 6), seeds=_S10),
    BenchmarkGroup("two_rows", "tight", n_positions=5, n_aircraft=10, tasks_range=(4, 6), seeds=_S10),
    BenchmarkGroup("full",     "tight", n_positions=5, n_aircraft=10, tasks_range=(4, 6), seeds=_S10),

    # ── Axis 2: Size scaling ──────────────────────────────────────────────────
    # triangle, tight, P=5 — isolates the effect of R (R=10 shared with Axis 1)
    BenchmarkGroup("triangle", "tight", n_positions=5, n_aircraft=5,  tasks_range=(3, 5), seeds=_S10),
    BenchmarkGroup("triangle", "tight", n_positions=5, n_aircraft=20, tasks_range=(4, 6), seeds=_S10),
    BenchmarkGroup("triangle", "tight", n_positions=5, n_aircraft=30, tasks_range=(5, 7), seeds=_S10),

    # ── Axis 3: Slack sensitivity ─────────────────────────────────────────────
    # triangle, R=10, P=5 — isolates the effect of time windows (tight in Axis 1)
    BenchmarkGroup("triangle", "medium", n_positions=5, n_aircraft=10, tasks_range=(4, 6), seeds=_S10),
    BenchmarkGroup("triangle", "loose",  n_positions=5, n_aircraft=10, tasks_range=(4, 6), seeds=_S10),

    # ── Axis 4: Hard-large ────────────────────────────────────────────────────
    # Maximum blocking at large scale — hardest configuration
    BenchmarkGroup("full",     "tight", n_positions=5, n_aircraft=20, tasks_range=(4, 6), seeds=_S10),

]


# ---------------------------------------------------------------------------
# Spec expansion and CLI
# ---------------------------------------------------------------------------

def expand_spec(spec: list[BenchmarkGroup]) -> list[tuple[BenchmarkGroup, int]]:
    """Return a flat list of (group, seed) pairs."""
    return [(g, s) for g in spec for s in g.seeds]


def _dry_run_table(spec: list[BenchmarkGroup]) -> None:
    pairs = expand_spec(spec)
    header = f"{'Topology':<10} {'Slack':<8} {'P':>3} {'R':>4} {'Seeds':<8} {'Count':>5}  Filename pattern"
    print(header)
    print("-" * len(header))
    for g in spec:
        seeds = list(g.seeds)
        seed_range = f"{seeds[0]}–{seeds[-1]}" if len(seeds) > 1 else str(seeds[0])
        pattern = g.filename("{s}")
        print(f"{g.topology:<10} {g.slack:<8} {g.n_positions:>3} {g.n_aircraft:>4} "
              f"{seed_range:<8} {len(seeds):>5}  {pattern}")
    print(f"\nTOTAL: {len(pairs)} instances")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Generate benchmark JSON instances for aircraft positioning.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="Print the generation plan without writing any files.",
    )
    ap.add_argument(
        "--outdir", default=str(_OUTPUT_DIR),
        help=f"Output directory (default: {_OUTPUT_DIR})",
    )
    ap.add_argument(
        "--filter", default="",
        help="Only generate instances whose filename contains this substring.",
    )
    args = ap.parse_args()

    spec = BENCHMARK_SPEC

    if args.dry_run:
        # Apply filter for preview too
        if args.filter:
            filtered = [g for g in spec
                        if any(args.filter in g.filename(s) for s in g.seeds)]
            spec = filtered
        _dry_run_table(spec)
        return

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    pairs = expand_spec(spec)
    if args.filter:
        pairs = [(g, s) for g, s in pairs if args.filter in g.filename(s)]

    if not pairs:
        print(f"No instances match filter '{args.filter}'.", file=sys.stderr)
        sys.exit(1)

    ok = skipped = errors = 0
    for g, seed in pairs:
        fname = g.filename(seed)
        out_path = outdir / fname
        if out_path.exists():
            print(f"  [skip] {fname}  (already exists)")
            skipped += 1
            continue
        try:
            instance = generate_instance(
                topology       = g.topology,
                slack          = g.slack,
                n_positions    = g.n_positions,
                n_aircraft     = g.n_aircraft,
                tasks_range    = g.tasks_range,
                seed           = seed,
                duration_range = g.duration_range,
                min_separation = g.min_separation,
            )
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(instance, f, indent=2, ensure_ascii=False)
            n_arcs = len(instance["hangar"]["blocking_arcs"])
            print(f"  [ok]   {fname}  "
                  f"(R={g.n_aircraft}, P={g.n_positions}, arcs={n_arcs})")
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  [ERR]  {fname}  → {exc}", file=sys.stderr)
            errors += 1

    total = ok + skipped + errors
    print(f"\n{ok} written  /  {skipped} skipped  /  {errors} errors  /  {total} total")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
