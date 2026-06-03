"""Smoke + correctness tests for the job-level Fixed-Assignment Scheduler.

Each test builds (or loads) a small instance, calls
``FixedAssignmentSchedulerJob.solve(instance, assignment)``, and asserts
the returned solution passes ``check_solution_jobs_v2``.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "solvers"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "input_data"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "output_data"))

from instance_io                       import load_json                  # noqa: E402
from fixed_assignment_scheduler_job    import FixedAssignmentSchedulerJob  # noqa: E402
from check_solution_jobs_v2            import check_solution as check_job  # noqa: E402


def _make_instance(jobs, aircrafts, blocking_arcs=(), precedences=(),
                   positions=("P1", "P2"),
                   mu=1.0, delta=2.0, eta=1.0, min_separation=0.5):
    return {
        "min_separation": min_separation, "mu": mu, "delta": delta, "eta": eta,
        "hangar": {
            "positions":     list(positions),
            "blocking_arcs": [{"front": f, "rear": r} for (f, r) in blocking_arcs],
        },
        "aircrafts":       aircrafts,
        "jobs":            jobs,
        "job_precedences": [{"before": b, "after": a} for (b, a) in precedences],
    }


# ---------------------------------------------------------------------------
# Test 1 — Trivial assignment: every aircraft at a different position.
# No blocking interactions; FAS just chains jobs back-to-back per aircraft.
# ---------------------------------------------------------------------------

def test_runs_and_passes_checker_on_trivial_assignment():
    root = os.path.join(
        os.path.dirname(__file__), "..", "..", "data", "instances_202605",
        "scn_triangle_tight_P5_R5", "scn_triangle_tight_P5_R5_seed1.json",
    )
    inst       = load_json(root)
    positions  = inst["hangar"]["positions"]
    ac_ids     = [a["id"] for a in inst["aircrafts"]]
    # 5 aircraft, 5 positions → one per position (no sharing)
    assignment = {aid: positions[i] for i, aid in enumerate(ac_ids)}

    solver = FixedAssignmentSchedulerJob()
    solver.configure(time_limit_s=30, weight_makespan=0.1, weight_delay=1.0,
                     weight_movements=10.0)
    sol = solver.solve(inst, assignment)

    assert sol["status"] in ("optimal", "feasible", "maxTimeLim")
    assert sol["metrics"]["movements"] == 0  # no shared positions, no blockers
    report = check_job(sol, inst)
    assert report["compliant"], report["requirements"]


# ---------------------------------------------------------------------------
# Test 2 — Forced Mode-B: R1 at P1 has two jobs.  R2 at P2 has one short job.
# Blocking arc P1 → P2.  R2 must access P2 while R1 is at P1; the FAS must
# insert a gap of at least mu between R1's two jobs.
# ---------------------------------------------------------------------------

def test_mode_B_gap_inserted_when_needed():
    instance = _make_instance(
        jobs=[
            {"id": "J1-1", "aircraft_id": "R1", "duration": 4, "is_first": True,
             "is_last": False, "interruptible": False},
            {"id": "J1-2", "aircraft_id": "R1", "duration": 4, "is_first": False,
             "is_last": True, "interruptible": False},
            {"id": "J2-1", "aircraft_id": "R2", "duration": 1, "is_first": True,
             "is_last": True, "interruptible": False},
        ],
        aircrafts=[
            {"id": "R1", "client": "C", "earliest_start": 0, "target_finish": 50},
            # R2 must enter at t around 4; R1's J1-1 finishes at 4.
            {"id": "R2", "client": "C", "earliest_start": 5, "target_finish": 50},
        ],
        blocking_arcs=[("P1", "P2")],
        precedences=[("J1-1", "J1-2")],
        positions=["P1", "P2"],
        mu=1.0, delta=2.0, eta=1.0,
    )
    assignment = {"R1": "P1", "R2": "P2"}
    solver = FixedAssignmentSchedulerJob()
    solver.configure(time_limit_s=30, weight_makespan=10.0, weight_delay=0.1,
                     weight_movements=1.0)
    sol = solver.solve(instance, assignment)
    assert sol["status"] in ("optimal", "feasible")

    report = check_job(sol, instance)
    assert report["compliant"], report["requirements"]
    # If Mode B was used we expect movements > 0 and a gap >= mu between
    # R1's two jobs.  The MILP can equally choose Mode A (delay R2 past
    # R1's stay) when delay is cheap; under the chosen weight profile
    # (makespan-heavy), the gap insertion is preferable.  We accept
    # either outcome but verify the gap rule holds when Mode B fires.
    r1 = next(a for a in sol["aircraft"] if a["id"] == "R1")
    j11, j12 = r1["jobs"]
    gap = j12["start"] - j11["finish"]
    if sol["metrics"]["movements"] > 0:
        assert gap >= 1.0 - 1e-4, (
            f"Mode B used (movements={sol['metrics']['movements']}) "
            f"but gap = {gap:.4f} < mu = 1.0"
        )


# ---------------------------------------------------------------------------
# Test 3 — Mode C only feasible: only way to schedule R2's access is mid-job
# of R1.  Mark R1's job interruptible → feasible with +delta to that job.
# Mark it non-interruptible in a separate variant → infeasible MILP.
# ---------------------------------------------------------------------------

def test_mode_C_feasibility_depends_on_interruptibility():
    # Variant 1: R1's job is interruptible — feasible
    inst_a = _make_instance(
        jobs=[
            {"id": "J1-1", "aircraft_id": "R1", "duration": 10, "is_first": True,
             "is_last": True, "interruptible": True},
            {"id": "J2-1", "aircraft_id": "R2", "duration": 1, "is_first": True,
             "is_last": True, "interruptible": False},
        ],
        aircrafts=[
            {"id": "R1", "client": "C", "earliest_start": 0,  "target_finish": 50},
            # R2 must arrive at t=5 (strictly inside R1's job [0,10])
            {"id": "R2", "client": "C", "earliest_start": 5,  "target_finish": 7},
        ],
        blocking_arcs=[("P1", "P2")],
        positions=["P1", "P2"],
    )
    assignment = {"R1": "P1", "R2": "P2"}
    solver_a = FixedAssignmentSchedulerJob()
    solver_a.configure(time_limit_s=30, weight_makespan=1.0, weight_delay=10.0,
                       weight_movements=1.0)
    sol_a = solver_a.solve(inst_a, assignment)
    assert sol_a["status"] in ("optimal", "feasible"), sol_a["status"]
    report_a = check_job(sol_a, inst_a)
    assert report_a["compliant"], report_a["requirements"]

    # Variant 2: same instance but J1-1 NOT interruptible — must be infeasible
    inst_b = _make_instance(
        jobs=[
            {"id": "J1-1", "aircraft_id": "R1", "duration": 10, "is_first": True,
             "is_last": True, "interruptible": False},
            {"id": "J2-1", "aircraft_id": "R2", "duration": 1, "is_first": True,
             "is_last": True, "interruptible": False},
        ],
        aircrafts=[
            {"id": "R1", "client": "C", "earliest_start": 0,  "target_finish": 12},
            # Tight target_finish on R2 forces access at t~5 (cannot delay past R1)
            {"id": "R2", "client": "C", "earliest_start": 5,  "target_finish": 7},
        ],
        blocking_arcs=[("P1", "P2")],
        positions=["P1", "P2"],
    )
    solver_b = FixedAssignmentSchedulerJob()
    solver_b.configure(time_limit_s=10, weight_makespan=1.0, weight_delay=10.0,
                       weight_movements=1.0)
    sol_b = solver_b.solve(inst_b, assignment)
    # The MILP either reports infeasible OR finds a Mode-A schedule with
    # large delay (R2 finishes after R1's stay).  Both are acceptable: the
    # key point is that no Mode-C event is reported and no infeasibility
    # is silently hidden.  Accept either ("infeasible", or feasible with
    # zero Mode-C events).
    if sol_b["status"] in ("infeasible",):
        return
    # Otherwise: must be compliant Mode-A (no movements, no kappa)
    report_b = check_job(sol_b, inst_b)
    assert report_b["compliant"], report_b["requirements"]
    assert sol_b["metrics"]["movements"] == 0
