"""
run_experiments.py — Batch runner for aircraft positioning experiments.

Runs a set of named solver configurations against a set of instances,
saves one JSON per run and updates outputs/solutions/results.csv.

Usage
-----
    python experiments/run_experiments.py                  # all instances, all experiments
    python experiments/run_experiments.py scn_few-loose    # instances whose name contains the pattern
    python experiments/run_experiments.py scn_few-loose milp_baseline   # filter instances AND experiment
"""
from __future__ import annotations

import io
import sys
import traceback
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — repo restructured into shared/, problems/, methods/.
# The flat sys.path additions below import the existing file names from
# their new locations.  All file names were preserved across the move so
# the ``from <name> import ...`` lines do not change.
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))                                      # for package imports (problems.*, methods.*, shared.*)
sys.path.insert(0, str(_ROOT / "shared"))                           # application, instance_io, plotting, rcl
sys.path.insert(0, str(_ROOT / "problems" / "aircraft"))            # checker (paper #1)
sys.path.insert(0, str(_ROOT / "problems" / "jobs"))                # checker (paper #2) — see name-clash note below
sys.path.insert(0, str(_ROOT / "methods" / "manual" / "aircraft"))  # paper #1 MILP + heuristics
sys.path.insert(0, str(_ROOT / "methods" / "manual" / "jobs"))      # paper #2 MILPs + heuristics

# Both problems define a top-level ``checker.py`` (with distinct contents).
# To disambiguate we import them via their package paths and alias the
# module symbol.
from problems.aircraft import checker as _checker_aircraft        # noqa: E402
from problems.jobs     import checker as _checker_jobs            # noqa: E402

from milp_jobs_solver import MILPSolver                     # noqa: E402
from milp_aircraft_solver import MILPAircraftSolver         # noqa: E402
from milp_jobs_v2_solver  import MILPJobsV2Solver           # noqa: E402
from constructive_heuristic import ConstructiveHeuristic    # noqa: E402  (used in archived experiments)
from lns_solver import LNSSolver                            # noqa: E402  (used in archived experiments)
from topology_heuristic_aircraft import TopologyHeuristicAircraft  # noqa: E402
from topology_heuristic_job      import TopologyHeuristicJob       # noqa: E402

# Autoresearch variant of TopologyHeuristicJob — loaded explicitly from the
# autoresearch_heuristics/ working copy so it does not collide with the
# canonical one already imported above.  Same public class name, distinct
# in-memory class object.
import importlib.util as _il_util                                  # noqa: E402
_AR_PATH = _ROOT / "methods" / "autoresearch" / "jobs" / "topology_heuristic_job.py"
_ar_spec = _il_util.spec_from_file_location(
    "_ar_topology_heuristic_job", str(_AR_PATH),
)
_ar_mod = _il_util.module_from_spec(_ar_spec)
_ar_spec.loader.exec_module(_ar_mod)
TopologyHeuristicJobAR = _ar_mod.TopologyHeuristicJob

# theory_assisted method — Iterated Greedy + VND (Candidate A).  Imported
# from its own package path; this runner is NOT under methods/<X>/ so it is
# exempt from the cross-method isolation scan, and importing the solver here
# is the sanctioned batch-registration step (README step 6).
sys.path.insert(0, str(_ROOT / "methods" / "theory_assisted" / "jobs"))  # iterated_greedy_vnd
from iterated_greedy_vnd import IteratedGreedyVNDJobSolver  # noqa: E402

from tgr_solver import TGRSolver                            # noqa: E402
from fixed_assignment_scheduler_aircraft import FixedAssignmentSchedulerAircraft  # noqa: E402
from fixed_assignment_scheduler_job      import FixedAssignmentSchedulerJob       # noqa: E402
from application import Application                         # noqa: E402  (was aircraft_positioning.py — now shared/application.py)


# =============================================================================
#  INSTANCES — edit this list or use a glob pattern
# =============================================================================

# Canonical layout: problems/aircraft/instances/<config>/<config>_seed{N}.json.
# Earlier flat layouts (data/experiment_instances/...) are no longer
# scanned automatically; legacy validation files there are kept for
# reference but not auto-discovered.
INSTANCE_PATHS: list[Path] = sorted(
    (_ROOT / "problems" / "aircraft" / "instances").glob("scn_*/scn_*.json"),
)


# =============================================================================
#  EXPERIMENTS — one entry per named configuration
#
#  Each entry is a dict with:
#    label        : str          — unique name used in filenames and the summary
#    solver_class : type         — solver class (instantiated fresh for each run)
#    config       : dict         — kwargs forwarded to configure_solver()
# =============================================================================

# Shared configuration — overridden per experiment where needed
_BASE_CONFIG: dict = {
    "weight_makespan":  0.1,
    "weight_delay":     1.0,
    "weight_movements": 10,
    "time_limit_s":     60,
    "MIPGap":           0.00,
    "NoRelHeurTime":    0,     # 0 = disabled
}

# Gurobi heuristic variant — NoRelHeurTime = 50% of budget (30 s out of 60 s)
_BASE_CONFIG_HEUR: dict = {**_BASE_CONFIG, "NoRelHeurTime": 30}

# Weight variant B — delay-priority
_BASE_CONFIG_WB: dict = {**_BASE_CONFIG, "weight_makespan": 1, "weight_delay": 10, "weight_movements": 0.1}

# Weight variant C — makespan-priority
_BASE_CONFIG_WC: dict = {**_BASE_CONFIG, "weight_makespan": 10, "weight_delay": 0.1, "weight_movements": 1}

# ---------------------------------------------------------------------------
# theory_assisted comparison — three single-dominant weight permutations
# (the dominant weight = 100, the other two = 1), 60 s cap.  Used to compare
# the job-level MILP baseline against the IG+VND heuristic across objectives.
# ---------------------------------------------------------------------------
_W_MK:  dict = {**_BASE_CONFIG, "weight_makespan": 100, "weight_delay": 1,   "weight_movements": 1,   "time_limit_s": 60}
_W_DLY: dict = {**_BASE_CONFIG, "weight_makespan": 1,   "weight_delay": 100, "weight_movements": 1,   "time_limit_s": 60}
_W_MOV: dict = {**_BASE_CONFIG, "weight_makespan": 1,   "weight_delay": 1,   "weight_movements": 100, "time_limit_s": 60}

EXPERIMENTS: list[dict] = [
    # =========================================================================
    # GROUP 1 — Exact reference
    # Only feasible for small instances within the 60 s budget.
    # =========================================================================
    {
        "label":        "milp_baseline",
        "solver_class": MILPAircraftSolver,
        "config":       {**_BASE_CONFIG, "cuts": "none"},   # original formulation, no LP-tightening
    },
    {
        "label":        "milp_baseline_cuts",
        "solver_class": MILPAircraftSolver,
        "config":       {**_BASE_CONFIG, "cuts": "all"},    # tight per-pair big-M + implied lower bounds
    },

    # =========================================================================
    # GROUP 2 — Topology multi-start portfolio
    # Divides the 60 s budget into N equal slices, each with a different seed.
    # ms3 = 3×20s, ms6 = 6×10s, ms12 = 12×5s — returns best across all starts.
    # =========================================================================
    {
        "label":        "topology_ms3",
        "solver_class": TopologyHeuristicAircraft,
        "config": {
            **_BASE_CONFIG,
            "alpha":           0.3,
            "weight_topology": 1.0,
            "n_starts":        3,
            "seed":            1,
        },
    },
    {
        "label":        "topology_ms6",
        "solver_class": TopologyHeuristicAircraft,
        "config": {
            **_BASE_CONFIG,
            "alpha":           0.3,
            "weight_topology": 1.0,
            "n_starts":        6,
            "seed":            1,
        },
    },
    {
        "label":        "topology_ms12",
        "solver_class": TopologyHeuristicAircraft,
        "config": {
            **_BASE_CONFIG,
            "alpha":           0.3,
            "weight_topology": 1.0,
            "n_starts":        12,
            "seed":            1,
        },
    },

    # =========================================================================
    # GROUP 3 — TGR-MILP: topology assignment generator + FixedAssignmentSchedulerAircraft.
    # tgr_k5: 5 assignments × 2s topology + remaining budget shared across MILPs.
    # tgr_k3: 3 assignments × 3s topology + longer MILP per assignment.
    # =========================================================================
    {
        "label":        "tgr_k5",
        "solver_class": TGRSolver,
        "config": {
            **_BASE_CONFIG,
            "n_assignments":   5,
            "time_topology_s": 10,
            "alpha":           0.3,
            "weight_topology": 1.0,
            "seed":            1,
        },
    },
    {
        "label":        "tgr_k3",
        "solver_class": TGRSolver,
        "config": {
            **_BASE_CONFIG,
            "n_assignments":   3,
            "time_topology_s": 9,
            "alpha":           0.3,
            "weight_topology": 1.0,
            "NOTE":            1,
        },
    },

    # =========================================================================
    # GROUP 5 — fas_on_topo: FixedAssignmentSchedulerAircraft on topology_ms6 assignment.
    # "Honest milp_fix1" — same assignment as topology_ms6 but with correct delta.
    # fas_from key is handled by the runner (bypasses Application, calls FAS directly).
    # Must run AFTER topology_ms6 so the warm cache is populated.
    # =========================================================================
    {
        "label":    "fas_on_topo",
        "fas_from": "topology_ms6",   # runner extracts assignment from this cached solution
        "config":   {**_BASE_CONFIG},
    },

    # =========================================================================
    # GROUP 6 — fas_2cand: FAS with 2 position candidates per aircraft.
    # Candidates = union of positions across K=10 topology assignments.
    # Attacks the residual gap on R=10 (fas_on_topo=7.06 vs milp=5.87).
    # Must run AFTER topology_ms6.
    # =========================================================================
    {
        "label":      "fas_2cand",
        "fas_2cand":  True,
        "fas_from":   "topology_ms6",
        "config":     {**_BASE_CONFIG},
    },

    # =========================================================================
    # GROUP 7 — safe_pipeline: min(topology_ms6, fas_on_topo, fas_2cand).
    # Guarantees FAS never degrades the topology solution.
    # Must run AFTER topology_ms6, fas_on_topo, and fas_2cand.
    # =========================================================================
    {
        "label":       "safe_pipeline",
        "safe_from":   ["topology_ms6", "fas_on_topo", "fas_2cand"],
        "config":      {**_BASE_CONFIG},
    },

    # =========================================================================
    # GROUP 8 — Gurobi heuristic mode: NoRelHeurTime=35s (59% of 60s budget).
    # Uses Gurobi's NoRelaxation heuristic phase before branch-and-bound.
    # Applies to milp_baseline and fas_on_topo (both call Gurobi directly).
    # topology_ms6_heur provides the assignment for fas_on_topo_heur.
    # =========================================================================
    {
        "label":        "milp_baseline_heur",
        "solver_class": MILPAircraftSolver,
        "config":       {**_BASE_CONFIG_HEUR},
    },
    {
        "label":        "topology_ms6_heur",
        "solver_class": TopologyHeuristicAircraft,
        "config": {
            **_BASE_CONFIG_HEUR,
            "alpha":           0.3,
            "weight_topology": 1.0,
            "n_starts":        6,
            "seed":            1,
        },
    },
    {
        "label":    "fas_on_topo_heur",
        "fas_from": "topology_ms6_heur",
        "config":   {**_BASE_CONFIG_HEUR},
    },
    {
        "label":     "safe_pipeline_heur",
        "safe_from": ["topology_ms6_heur", "fas_on_topo_heur"],
        "config":    {**_BASE_CONFIG_HEUR},
    },

    # =========================================================================
    # GROUP 9 — Weight variant B: delay-priority (wm=1, wd=10, wmov=0.1)
    # Same 4-method pipeline as groups 1/2/5/7, independent weight profile.
    # =========================================================================
    {
        "label":        "milp_baseline_wB",
        "solver_class": MILPAircraftSolver,
        "config":       {**_BASE_CONFIG_WB},
    },
    {
        "label":        "topology_ms6_wB",
        "solver_class": TopologyHeuristicAircraft,
        "config": {
            **_BASE_CONFIG_WB,
            "alpha":           0.3,
            "weight_topology": 1.0,
            "n_starts":        6,
            "seed":            1,
        },
    },
    {
        "label":    "fas_on_topo_wB",
        "fas_from": "topology_ms6_wB",
        "config":   {**_BASE_CONFIG_WB},
    },
    {
        "label":     "safe_pipeline_wB",
        "safe_from": ["topology_ms6_wB", "fas_on_topo_wB"],
        "config":    {**_BASE_CONFIG_WB},
    },

    # =========================================================================
    # GROUP 10 — Weight variant C: makespan-priority (wm=10, wd=0.1, wmov=1)
    # =========================================================================
    {
        "label":        "milp_baseline_wC",
        "solver_class": MILPAircraftSolver,
        "config":       {**_BASE_CONFIG_WC},
    },
    {
        "label":        "topology_ms6_wC",
        "solver_class": TopologyHeuristicAircraft,
        "config": {
            **_BASE_CONFIG_WC,
            "alpha":           0.3,
            "weight_topology": 1.0,
            "n_starts":        6,
            "seed":            1,
        },
    },
    {
        "label":    "fas_on_topo_wC",
        "fas_from": "topology_ms6_wC",
        "config":   {**_BASE_CONFIG_WC},
    },
    {
        "label":     "safe_pipeline_wC",
        "safe_from": ["topology_ms6_wC", "fas_on_topo_wC"],
        "config":    {**_BASE_CONFIG_WC},
    },

    # =========================================================================
    # GROUP 4 — milp_fix1 diagnostic: positions fixed from topology_ms6 solution,
    # let MILP optimise timing/sequencing only.
    # Run AFTER milp_baseline and topology_ms6 so the warm cache is populated.
    # =========================================================================
    {
        "label":          "milp_fix1",
        "solver_class":   MILPAircraftSolver,
        "fix_from":       "topology_ms6",   # use topology_ms6 solution from cache
        "config":         {**_BASE_CONFIG},
    },

    # =========================================================================
    # JOB-LEVEL SIBLINGS — job-as-scheduling-unit problem (paper #2)
    # Three-mode blocking semantics with mu/delta/eta parameters.
    # =========================================================================
    {
        "label":        "milp_baseline_job",
        "solver_class": MILPJobsV2Solver,
        "config":       {**_BASE_CONFIG},
    },
    {
        "label":        "milp_baseline_job_heur",
        "solver_class": MILPJobsV2Solver,
        "config":       {**_BASE_CONFIG_HEUR},
    },
    {
        "label":        "topology_ms6_job",
        "solver_class": TopologyHeuristicJob,
        "config": {
            **_BASE_CONFIG,
            "alpha":           0.3,
            "weight_topology": 1.0,
            "n_starts":        6,
            "seed":            1,
        },
    },
    {
        "label":        "topology_ms6_job_ar",
        "solver_class": TopologyHeuristicJobAR,
        "config": {
            **_BASE_CONFIG,
            "alpha":           0.3,
            "weight_topology": 1.0,
            "n_starts":        6,
            "seed":            1,
        },
    },
    {
        "label":     "fas_on_topo_job",
        "fas_from":  "topology_ms6_job",
        "fas_class": FixedAssignmentSchedulerJob,
        "config":    {**_BASE_CONFIG},
    },
    {
        "label":     "safe_pipeline_job",
        "safe_from": ["topology_ms6_job", "fas_on_topo_job"],
        "config":    {**_BASE_CONFIG},
    },

    # =========================================================================
    # THEORY_ASSISTED — IG+VND (Candidate A) vs job-level MILP baseline,
    # three single-dominant weight permutations (100/1/1), 60 s cap.
    # Interleaved MILP/heuristic per weight profile so each MILP row is
    # immediately followed by the IG+VND row for the same problem.
    # =========================================================================
    {"label": "milp_job_wMK",  "solver_class": MILPJobsV2Solver,           "config": {**_W_MK}},
    {"label": "igvnd_wMK",     "solver_class": IteratedGreedyVNDJobSolver, "config": {**_W_MK,  "seed": 1}},
    {"label": "milp_job_wDLY", "solver_class": MILPJobsV2Solver,           "config": {**_W_DLY}},
    {"label": "igvnd_wDLY",    "solver_class": IteratedGreedyVNDJobSolver, "config": {**_W_DLY, "seed": 1}},
    {"label": "milp_job_wMOV", "solver_class": MILPJobsV2Solver,           "config": {**_W_MOV}},
    {"label": "igvnd_wMOV",    "solver_class": IteratedGreedyVNDJobSolver, "config": {**_W_MOV, "seed": 1}},

    # =========================================================================
    # ARCHIVED — uncomment to reproduce earlier experiments
    # =========================================================================
    # {   "label": "constructive",       alpha=0.4                              },
    # {   "label": "topology",           single-start, seed=None                },
    # {   "label": "topology_no_penalty",weight_topology=0.0                    },
    # {   "label": "topology_no_kicks",  kick_interval_ratio=0.0                },
    # {   "label": "lns",                destroy=mixed, repair=grasp            },
    # {   "label": "lns_alns",           destroy=alns, repair=submilp           },
    # {   "label": "lns_warm_topo",      warm_start_from=topology               },
    # {   "label": "constructive_7",     alpha=0.7                              },
    # {   "label": "lns_submilp",        repair_time_s=1.0                      },
    # {   "label": "milp_heuristic",     NoRelHeurTime=10                       },
]


# =============================================================================
#  MULTI-SEED EXPERIMENTS — robustness study for topology heuristic
#
#  Runs the topology solver with 12 fixed seeds to measure objective variance.
#  Use with CLI filter to restrict to relevant instance sizes:
#
#    python scripts/run_experiments.py scn_many-medium topology_seed
#    python scripts/run_experiments.py scn_heavy-tight topology_seed
# =============================================================================

SEED_EXPERIMENTS: list[dict] = [
    {
        "label":        f"topology_seed{s}",
        "solver_class": TopologyHeuristicAircraft,
        "config": {
            **_BASE_CONFIG,
            "alpha":           0.3,
            "weight_topology": 1.0,
            "seed":            s,
            "log_enabled":     False,
        },
    }
    for s in range(1, 13)
]


# MULTISTART_EXPERIMENTS intentionally empty — ms3/ms6/ms12 are defined in
# EXPERIMENTS above.  This list is kept as an extension point for future
# variants (e.g. different alpha or w_topo per start count).
MULTISTART_EXPERIMENTS: list[dict] = []


# =============================================================================
#  Runner
# =============================================================================

def run_experiments(
    instances: list[Path],
    experiments: list[dict],
    solutions_dir: Path | None = None,
    log_path: Path | None = None,
) -> list[dict]:
    """Run every experiment on every instance.

    Parameters
    ----------
    instances:
        Paths to instance JSON files.
    experiments:
        List of experiment dicts (see module header).
    solutions_dir:
        Where to write solution files.  Defaults to ``outputs/solutions/``.
    log_path:
        If given, rewrite this file after each instance with the experiment
        configurations followed by the latest summary table.

    Returns
    -------
    list[dict]
        One summary record per completed run.
    """
    solutions_dir = solutions_dir or _ROOT / "outputs" / "solutions"
    total   = len(instances) * len(experiments)
    done    = 0
    summary = []

    # Build the static config header once
    config_header = _build_config_header(experiments)

    print(f"\n{'='*66}")
    print(f"  Experiments : {len(experiments)}")
    print(f"  Instances   : {len(instances)}")
    print(f"  Total runs  : {total}")
    print(f"{'='*66}\n")

    # warm_solution cache: {(instance_stem, label): solution_dict}
    _warm_cache: dict[tuple[str, str], dict] = {}

    for inst_path in instances:
        for exp in experiments:
            done += 1
            label = exp["label"]
            tag   = f"[{done:>3}/{total}] {inst_path.stem}  ·  {label}"
            print(f"\n{'-'*66}")
            print(tag)
            print(f"{'-'*66}")

            record: dict = {
                "instance":   inst_path.stem,
                "experiment": label,
                "status":     None,
                "objective":  None,
                "makespan":   None,
                "movements":  None,
                "total_delay":None,
                "mip_gap":    None,
                "solve_time_s": None,
                "error":      None,
            }

            try:
                # ---- safe_from: return best of multiple cached solutions ----
                safe_from = exp.get("safe_from")
                if safe_from is not None:
                    best_sol = None
                    best_obj = float("inf")
                    for src_label in safe_from:
                        cached = _warm_cache.get((inst_path.stem, src_label))
                        if cached is None:
                            continue  # source not in this experiment set — skip gracefully
                        if cached.get("objective", float("inf")) < best_obj:
                            best_obj = cached["objective"]
                            best_sol = cached
                    if best_sol is None:
                        record["error"] = "all safe_from sources missing from warm cache"
                        summary.append(record)
                        continue
                    sol = best_sol
                    metrics = sol["metrics"]
                    _warm_cache[(inst_path.stem, label)] = sol
                    record.update({
                        "status":       sol["status"],
                        "objective":    sol["objective"],
                        "makespan":     metrics["makespan"],
                        "movements":    metrics["movements"],
                        "total_delay":  metrics["total_delay"],
                        "solve_time_s": 0.0,
                    })
                    print(f"  safe_pipeline  best_src={[s for s in safe_from if _warm_cache.get((inst_path.stem, s), {}).get('objective') == best_obj][0]}"
                          f"  obj={sol['objective']}")
                    summary.append(record)
                    print_summary(summary)
                    if log_path is not None:
                        _write_log(log_path, config_header, summary)
                    continue

                # ---- fas_from: run a FixedAssignmentScheduler on a cached assignment ----
                # An optional `fas_class` key in the experiment dict selects which
                # FAS variant to use (default = FixedAssignmentSchedulerAircraft for
                # the CJOR paper).  Job-level experiments set fas_class to
                # FixedAssignmentSchedulerJob.
                fas_from = exp.get("fas_from")
                if fas_from is not None and not exp.get("fas_2cand"):
                    from instance_io import load_json as _load_json
                    fas_sol = _warm_cache.get((inst_path.stem, fas_from))
                    if fas_sol is None:
                        raise RuntimeError(
                            f"fas_from='{fas_from}' not found in warm cache for {inst_path.stem}"
                        )
                    assignment = {a["id"]: a["position"] for a in fas_sol["aircraft"]}
                    print(f"  fas_from '{fas_from}'  assignment={list(assignment.values())[:5]}...")
                    fas_cfg   = dict(exp["config"])
                    fas_class = exp.get("fas_class", FixedAssignmentSchedulerAircraft)
                    fas       = fas_class()
                    fas.configure(
                        time_limit_s    = fas_cfg.get("time_limit_s", 60),
                        min_separation  = fas_cfg.get("min_separation", 10.0),
                        weight_makespan = fas_cfg.get("weight_makespan", 10.0),
                        weight_delay    = fas_cfg.get("weight_delay", 100.0),
                        weight_movements= fas_cfg.get("weight_movements", 1.0),
                        MIPGap          = fas_cfg.get("MIPGap", 0.0),
                    )
                    import time as _time
                    _t0 = _time.perf_counter()
                    raw_inst = _load_json(inst_path)
                    sol = fas.solve(raw_inst, assignment)
                    solve_time = round(_time.perf_counter() - _t0, 3)
                    metrics = sol["metrics"]
                    _warm_cache[(inst_path.stem, label)] = sol
                    record.update({
                        "status":       sol["status"],
                        "objective":    sol["objective"],
                        "makespan":     metrics["makespan"],
                        "movements":    metrics["movements"],
                        "total_delay":  metrics["total_delay"],
                        "mip_gap":      sol.get("mip_gap"),
                        "solve_time_s": solve_time,
                    })
                    gap_str = f"  gap={sol['mip_gap']:.4f}" if sol.get("mip_gap") is not None else ""
                    print(
                        f"  OK  status={sol['status']}  obj={sol['objective']}"
                        f"  makespan={metrics['makespan']}  delay={metrics['total_delay']}"
                        f"  mov={metrics['movements']}{gap_str}  time={solve_time}s"
                        f"  build={sol.get('_build_time_s','?')}s"
                        f"  solve={sol.get('_solve_time_s','?')}s"
                    )
                    summary.append(record)
                    print_summary(summary)
                    if log_path is not None:
                        _write_log(log_path, config_header, summary)
                    continue   # skip the Application path below

                # ---- fas_2cand: FAS with multi-candidate positions from generate_assignments ----
                if exp.get("fas_2cand"):
                    from instance_io import load_json as _load_json
                    from solvers.topology_heuristic_aircraft import TopologyHeuristicAircraft
                    fas_from2 = exp.get("fas_from")
                    fas_sol2 = _warm_cache.get((inst_path.stem, fas_from2))
                    if fas_sol2 is None:
                        raise RuntimeError(
                            f"fas_from='{fas_from2}' not found in warm cache for {inst_path.stem}"
                        )
                    primary_assignment = {a["id"]: a["position"] for a in fas_sol2["aircraft"]}
                    aircraft_ids = list(primary_assignment.keys())
                    raw_inst = _load_json(inst_path)
                    # Generate K diverse assignments to build candidate sets
                    topo = TopologyHeuristicAircraft()
                    fas_cfg2 = dict(exp["config"])
                    topo.configure_solver(
                        time_limit_s=fas_cfg2.get("time_limit_s", 60),
                        min_separation=fas_cfg2.get("min_separation", 10.0),
                        weight_makespan=fas_cfg2.get("weight_makespan", 10.0),
                        weight_delay=fas_cfg2.get("weight_delay", 100.0),
                        weight_movements=fas_cfg2.get("weight_movements", 1.0),
                        weight_topology=fas_cfg2.get("weight_topology", 1.0),
                        seed=fas_cfg2.get("seed", 1),
                    )
                    diverse = topo.generate_assignments(raw_inst, k=10, time_per_assign=1.0)
                    # Build candidate set: primary position + alternatives from diverse runs.
                    # Limit extra candidates to the MAX_FLEX_AC aircraft with most delay
                    # to keep the MILP tractable.
                    MAX_FLEX_AC = 4
                    all_cands: dict[str, list[str]] = {}
                    for r, p in primary_assignment.items():
                        all_cands[r] = [p]
                    for asgn in diverse:
                        for r, p in asgn.items():
                            if p not in all_cands.get(r, []):
                                all_cands.setdefault(r, []).append(p)
                    # Score aircraft by delay+makespan contribution in fas_on_topo.
                    # fas_on_topo gives the best timing for the primary assignment.
                    # Aircraft with non-zero delay OR that finish at makespan
                    # might benefit from an alternative position.
                    fas_on_topo_cached = _warm_cache.get((inst_path.stem, "fas_on_topo"))
                    score_source = fas_on_topo_cached if fas_on_topo_cached else fas_sol2
                    ms_val = score_source.get("metrics", {}).get("makespan", 0.0)
                    def _ac_score(a_dict: dict) -> float:
                        delay = a_dict.get("delay", 0.0)
                        # also penalise aircraft finishing at makespan (they determine it)
                        finish_at_ms = 1.0 if abs(a_dict.get("finish", 0.0) - ms_val) < 1e-3 else 0.0
                        return delay + finish_at_ms * 0.5
                    primary_score = {
                        a["id"]: _ac_score(a)
                        for a in score_source.get("aircraft", [])
                    }
                    flex_sorted = sorted(
                        [r for r in aircraft_ids if len(all_cands[r]) > 1],
                        key=lambda r: -primary_score.get(r, 0.0),
                    )
                    flex_ac = set(flex_sorted[:MAX_FLEX_AC])
                    cands_map = {
                        r: (all_cands[r] if r in flex_ac else [primary_assignment[r]])
                        for r in aircraft_ids
                    }
                    n_multi = sum(1 for v in cands_map.values() if len(v) > 1)
                    print(f"  fas_2cand: {n_multi}/{len(primary_assignment)} aircraft have >1 candidate"
                          f"  (top-{MAX_FLEX_AC} by delay)")
                    fas2 = FixedAssignmentSchedulerAircraft()
                    fas2.configure(
                        time_limit_s    = fas_cfg2.get("time_limit_s", 60),
                        min_separation  = fas_cfg2.get("min_separation", 10.0),
                        weight_makespan = fas_cfg2.get("weight_makespan", 10.0),
                        weight_delay    = fas_cfg2.get("weight_delay", 100.0),
                        weight_movements= fas_cfg2.get("weight_movements", 1.0),
                        MIPGap          = fas_cfg2.get("MIPGap", 0.0),
                    )
                    import time as _time
                    _t0 = _time.perf_counter()
                    sol = fas2.solve(raw_inst, primary_assignment, candidates=cands_map)
                    solve_time = round(_time.perf_counter() - _t0, 3)
                    metrics = sol["metrics"]
                    _warm_cache[(inst_path.stem, label)] = sol
                    record.update({
                        "status":       sol["status"],
                        "objective":    sol["objective"],
                        "makespan":     metrics["makespan"],
                        "movements":    metrics["movements"],
                        "total_delay":  metrics["total_delay"],
                        "mip_gap":      sol.get("mip_gap"),
                        "solve_time_s": solve_time,
                    })
                    gap_str = f"  gap={sol['mip_gap']:.4f}" if sol.get("mip_gap") is not None else ""
                    print(
                        f"  OK  status={sol['status']}  obj={sol['objective']}"
                        f"  makespan={metrics['makespan']}  delay={metrics['total_delay']}"
                        f"  mov={metrics['movements']}{gap_str}  time={solve_time}s"
                    )
                    summary.append(record)
                    print_summary(summary)
                    if log_path is not None:
                        _write_log(log_path, config_header, summary)
                    continue

                # ---- standard path via Application ----
                app = Application(solver=exp["solver_class"]())
                app.read_data(inst_path)

                # Inject warm_solution / fix_positions_from if requested
                run_config = dict(exp["config"])
                warm_from  = exp.get("warm_start_from")
                if warm_from is not None:
                    warm_sol = _warm_cache.get((inst_path.stem, warm_from))
                    if warm_sol is not None:
                        run_config["warm_solution"] = warm_sol
                        print(f"  warm start from '{warm_from}'  obj={warm_sol['objective']:.2f}")
                    else:
                        print(f"  WARNING: warm_start_from='{warm_from}' not found in cache — using cold start")

                fix_from = exp.get("fix_from")
                if fix_from is not None:
                    fix_sol = _warm_cache.get((inst_path.stem, fix_from))
                    if fix_sol is not None:
                        run_config["fix_positions_from"] = fix_sol
                        print(f"  fix positions from '{fix_from}'  obj={fix_sol['objective']:.2f}")
                    else:
                        print(f"  WARNING: fix_from='{fix_from}' not found in cache — running without fix")

                app.configure_solver(**run_config)
                app.solve()
                app.save_solution(solutions_dir, label=label)

                sol     = app.get_solution()
                metrics = sol["metrics"]
                # Cache solution so later experiments can use it as warm start
                _warm_cache[(inst_path.stem, label)] = sol
                record.update({
                    "status":       sol["status"],
                    "objective":    sol["objective"],
                    "makespan":     metrics["makespan"],
                    "movements":    metrics["movements"],
                    "total_delay":  metrics["total_delay"],
                    "mip_gap":      sol.get("mip_gap"),
                    "solve_time_s": app._solve_time_s,
                })
                gap_str = f"  gap={sol['mip_gap']:.4f}" if sol.get("mip_gap") is not None else ""
                print(
                    f"  OK  status={sol['status']}  obj={sol['objective']}  "
                    f"makespan={metrics['makespan']}  "
                    f"delay={metrics['total_delay']}  "
                    f"mov={metrics['movements']}{gap_str}  "
                    f"time={app._solve_time_s}s"
                )

            except Exception as exc:  # noqa: BLE001
                record["error"] = str(exc)
                print(f"  ERR  {exc}")
                traceback.print_exc()

            summary.append(record)

            # Print and log the running summary after every completed run
            print_summary(summary)
            if log_path is not None:
                _write_log(log_path, config_header, summary)

    return summary


def _build_config_header(experiments: list[dict]) -> str:
    """Return the experiment configurations as a compact human-readable header."""
    buf = io.StringIO()
    sep = "=" * 66

    buf.write(f"{sep}\n")
    buf.write(f"  EXPERIMENT CONFIGURATIONS  ({len(experiments)} experiments)\n")
    buf.write(f"{sep}\n")

    # Collect all configs and detect which keys are shared vs experiment-specific
    all_configs = []
    for exp in experiments:
        cfg = dict(exp["config"])
        cfg.pop("log_enabled", None)   # internal — not interesting in summary
        all_configs.append(cfg)

    all_keys   = list(dict.fromkeys(k for c in all_configs for k in c))
    shared     = {k: all_configs[0][k] for k in all_keys
                  if all(c.get(k) == all_configs[0].get(k) for c in all_configs)
                  and k in all_configs[0]}
    diff_keys  = [k for k in all_keys if k not in shared]

    # --- Shared parameters (one line each, two columns) ---
    if shared:
        buf.write("  Shared parameters:\n")
        items = [f"{k}={v}" for k, v in shared.items()]
        half  = (len(items) + 1) // 2
        for i in range(half):
            left  = items[i]
            right = items[i + half] if i + half < len(items) else ""
            buf.write(f"    {left:<28}  {right}\n")
        buf.write("\n")

    # --- Per-experiment table (only differing params) ---
    labels       = [exp["label"]                                          for exp in experiments]
    solver_names = [exp.get("solver_class", FixedAssignmentSchedulerAircraft).__name__ for exp in experiments]
    w_label      = max(len(l) for l in labels)
    w_solver     = max(len(s) for s in solver_names)

    col_headers = ["Label", "Solver"] + diff_keys
    col_widths  = (
        [w_label, w_solver]
        + [max(len(k), max(len(_fmt(c.get(k))) for c in all_configs))
           for k in diff_keys]
    )

    # header row
    header = "  " + "  ".join(h.ljust(w) for h, w in zip(col_headers, col_widths))
    buf.write(f"  Per-experiment parameters:\n")
    buf.write(header + "\n")
    buf.write("  " + "-" * (len(header) - 2) + "\n")

    for exp, cfg in zip(experiments, all_configs):
        row_vals = (
            [exp["label"], exp.get("solver_class", FixedAssignmentSchedulerAircraft).__name__]
            + [_fmt(cfg.get(k)) for k in diff_keys]
        )
        buf.write("  " + "  ".join(v.ljust(w) for v, w in zip(row_vals, col_widths)) + "\n")

    buf.write(f"{sep}\n\n")
    return buf.getvalue()


def _fmt(v) -> str:
    """Format a config value compactly."""
    if v is None:
        return "—"
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v)


def _write_log(log_path: Path, config_header: str, summary: list[dict]) -> None:
    """Overwrite *log_path* with the config header and the latest summary table."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    buf.write(config_header)
    buf.write("\n")
    _format_summary(buf, summary)
    log_path.write_text(buf.getvalue(), encoding="utf-8")


def _format_summary(out: io.StringIO, summary: list[dict]) -> None:
    """Write a compact results table into *out*."""
    ok     = [r for r in summary if r["error"] is None]
    failed = [r for r in summary if r["error"] is not None]

    out.write(f"\n{'='*66}\n")
    out.write(f"  SUMMARY  —  {len(ok)} ok  /  {len(failed)} failed  /  {len(summary)} total\n")
    out.write(f"{'='*66}\n")

    if not ok:
        return

    w_inst = max(len(r["instance"])   for r in ok)
    w_exp  = max(len(r["experiment"]) for r in ok)

    header = (
        f"  {'Instance':<{w_inst}}  {'Experiment':<{w_exp}}  "
        f"{'Status':<10}  {'Obj':>10}  {'Makespan':>9}  "
        f"{'Delay':>9}  {'Mov':>4}  {'Gap':>8}  {'Time(s)':>8}"
    )
    out.write(header + "\n")
    out.write(f"  {'-'*(len(header)-2)}\n")

    for r in ok:
        status   = str(r["status"])[:10]
        gap_val  = r.get("mip_gap")
        gap_str  = f"{gap_val*100:7.2f}%" if gap_val is not None else "       -"
        # A "no feasible solution found" row (MILP build/solve timeout
        # with the synthetic dict, or anything else lacking a real
        # objective) renders numerics as "-" so the aggregator can skip
        # them and downstream readers don't mistake a synthetic 0.0 for
        # a real zero objective.
        no_sol = (
            r["status"] is None
            or str(r["status"]).strip().startswith(("feasible solution not found", "infeasible"))
            or r["objective"] is None
        )
        if no_sol:
            obj_s   = f"{'-':>10}"
            mks_s   = f"{'-':>9}"
            dly_s   = f"{'-':>9}"
            mov_s   = f"{'-':>4}"
        else:
            obj_s   = f"{r['objective']:>10.2f}"
            mks_s   = f"{r['makespan']:>9.2f}"
            dly_s   = f"{r['total_delay']:>9.2f}"
            mov_s   = f"{r['movements']:>4}"
        out.write(
            f"  {r['instance']:<{w_inst}}  {r['experiment']:<{w_exp}}  "
            f"{status:<10}  {obj_s}  {mks_s}  {dly_s}  {mov_s}  {gap_str}  "
            f"{r['solve_time_s']:>8.1f}\n"
        )

    if failed:
        out.write("\n  Failed runs:\n")
        for r in failed:
            out.write(f"    x {r['instance']}  ·  {r['experiment']}  ->  {r['error']}\n")

    out.write(f"{'='*66}\n")


def print_summary(summary: list[dict]) -> None:
    """Print a compact results table to stdout."""
    buf = io.StringIO()
    _format_summary(buf, summary)
    print(buf.getvalue(), end="")


def print_seed_summary(summary: list[dict]) -> None:
    """Print per-instance statistics for multi-seed runs.

    Groups runs by instance, then reports min/mean/median/max/std of the
    objective across all seeds for each instance.
    """
    import statistics

    ok = [r for r in summary if r["error"] is None and r["objective"] is not None]
    if not ok:
        return

    # Group by instance
    by_inst: dict[str, list[float]] = {}
    for r in ok:
        by_inst.setdefault(r["instance"], []).append(r["objective"])

    sep = "=" * 74
    print(f"\n{sep}")
    print(f"  SEED SUMMARY  ({len(ok)} runs across {len(by_inst)} instances)")
    print(f"{sep}")

    w_inst = max(len(k) for k in by_inst)
    header = (
        f"  {'Instance':<{w_inst}}  {'N':>3}  {'Min':>10}  {'Mean':>10}"
        f"  {'Median':>10}  {'Max':>10}  {'Std':>8}"
    )
    print(header)
    print(f"  {'-'*(len(header)-2)}")

    for inst, vals in sorted(by_inst.items()):
        n      = len(vals)
        v_min  = min(vals)
        v_mean = statistics.mean(vals)
        v_med  = statistics.median(vals)
        v_max  = max(vals)
        v_std  = statistics.stdev(vals) if n > 1 else 0.0
        print(
            f"  {inst:<{w_inst}}  {n:>3}  {v_min:>10.2f}  {v_mean:>10.2f}"
            f"  {v_med:>10.2f}  {v_max:>10.2f}  {v_std:>8.3f}"
        )
    print(f"{sep}\n")


# =============================================================================
#  CLI
# =============================================================================

if __name__ == "__main__":
    # ==========================================================================
    #  RUN CONFIGURATION
    #  Edit the two variables below, then run with "Run in Terminal".
    #
    #  INST_FILTER : comma-separated substrings to match instance stems
    #                (e.g. "_seed2" picks up scn_<config>_seed2 across all
    #                configurations).  "" / None runs every instance under
    #                problems/aircraft/instances (or whichever root is supplied
    #                as the third CLI argument).
    #
    #  EXP_FILTER  : comma-separated EXACT experiment labels (no substring
    #                match) so "milp_baseline" does not also pull in
    #                "milp_baseline_heur".  "" / None runs the default
    #                EXPERIMENTS list.
    #
    #  Current preset: seed10 run of the main four methods × three weight
    #  profiles (12 experiments, no _heur variants), matching the seed1
    #  batch in outputs/logs/seed1_main_methods_*.log.
    # ==========================================================================

    INST_FILTER: str = "_seed10"                                                                                         # ← edit here
    EXP_FILTER:  str = "milp_baseline,topology_ms6,fas_on_topo,safe_pipeline,milp_baseline_wB,topology_ms6_wB,fas_on_topo_wB,safe_pipeline_wB,milp_baseline_wC,topology_ms6_wC,fas_on_topo_wC,safe_pipeline_wC"  # ← edit here

    # ------------------------------------------------------------------
    # Resolution — do not edit below this line
    # ------------------------------------------------------------------

    # Support CLI overrides (argv still works for scripted use).
    # Positional args: <inst_filter> <exp_filter> [<instance_root>]
    inst_filter = sys.argv[1] if len(sys.argv) > 1 else INST_FILTER or None
    exp_filter  = sys.argv[2] if len(sys.argv) > 2 else EXP_FILTER  or None
    inst_root   = Path(sys.argv[3]) if len(sys.argv) > 3 else None

    # Resolve the instance-discovery root.  Default: problems/aircraft/instances.
    # When a third argument is provided (or the user wants an alternate
    # benchmark folder), use that instead.
    if inst_root is not None:
        _root_path = inst_root if inst_root.is_absolute() else (_ROOT / inst_root)
        _instance_paths = sorted(_root_path.glob("scn_*/scn_*.json"))
    else:
        _instance_paths = INSTANCE_PATHS

    # inst_filter supports comma-separated patterns.
    # Each pattern is a substring match by default; a trailing "$" means
    # "stem ends with this pattern" (useful to distinguish "_seed1" from
    # "_seed10" when filtering).
    def _match_stem(stem: str, patterns: list[str]) -> bool:
        for pat in patterns:
            if pat.endswith("$"):
                if stem.endswith(pat[:-1]):
                    return True
            else:
                if pat in stem:
                    return True
        return False

    if inst_filter:
        _patterns = [p.strip() for p in inst_filter.split(",")]
        instances = [p for p in _instance_paths if _match_stem(p.stem, _patterns)]
    else:
        instances = _instance_paths

    # exp_filter uses EXACT label matching (labels are unique strings,
    # substring would inadvertently pull "_heur"/"_wB"/"_wC" siblings).
    _all_experiments = EXPERIMENTS + SEED_EXPERIMENTS + MULTISTART_EXPERIMENTS
    if exp_filter:
        _wanted = {e.strip() for e in exp_filter.split(",")}
        experiments = [e for e in _all_experiments if e["label"] in _wanted]
    else:
        experiments = EXPERIMENTS

    if not instances:
        print(f"No instances match filter '{inst_filter}'.", file=sys.stderr)
        sys.exit(1)
    if not experiments:
        print(f"No experiments match filter '{exp_filter}'.", file=sys.stderr)
        sys.exit(1)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Derive a seed tag from INST_FILTER for consistent log naming, e.g. "_seed10" → "seed10_"
    _seed_tag = ""
    if inst_filter and inst_filter.strip().startswith("_seed"):
        _seed_tag = inst_filter.strip().lstrip("_") + "_"
    # If an alternate instance root was used, append its folder name as a tag
    # so the log filename remains self-describing (e.g. "seed1_202605_02_...").
    _root_tag = ""
    if inst_root is not None:
        _root_tag = inst_root.name.replace("instances_", "") + "_"
    log_path  = _ROOT / "outputs" / "logs" / f"{_seed_tag}{_root_tag}main_methods_{timestamp}.log"

    summary = run_experiments(instances, experiments, log_path=log_path)
    print(f"\nLog saved: {log_path}")

    # Print seed statistics if the run was a multi-seed experiment
    if exp_filter and "seed" in exp_filter:
        print_seed_summary(summary)
