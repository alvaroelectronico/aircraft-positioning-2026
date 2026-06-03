"""Unit tests for check_solution_jobs_v2 — the paper-#2 solution checker.

Covers the three access modes (A/B/C), the gap-cumulative rule for Mode B,
the strict-interior rule for Mode C, the non-interruptible infeasibility
case, and the kappa consistency between RQ03_v2 and RQ09.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "output_data"))
from check_solution_jobs_v2 import check_solution  # noqa: E402


# =============================================================================
#  Instance / solution builders
# =============================================================================

MU       = 1.0
DELTA    = 2.0
ETA      = 1.0
EPSILON  = 0.5


def _make_instance(
    jobs:           list[dict],
    aircrafts:      list[dict],
    blocking_arcs:  list[tuple[str, str]] = (),
    precedences:    list[tuple[str, str]] = (),
    positions:      list[str] = ("P1", "P2"),
    mu:             float = MU,
    delta:          float = DELTA,
    eta:            float = ETA,
    min_separation: float = EPSILON,
) -> dict:
    """Build a minimal instance dict with paper-#2 fields."""
    return {
        "min_separation": min_separation,
        "mu":             mu,
        "delta":          delta,
        "eta":            eta,
        "hangar": {
            "positions":     list(positions),
            "blocking_arcs": [{"front": f, "rear": r} for (f, r) in blocking_arcs],
        },
        "aircrafts":       aircrafts,
        "jobs":            jobs,
        "job_precedences": [{"before": b, "after": a} for (b, a) in precedences],
    }


def _make_solution(
    aircraft_specs: list[dict],
    movements:      int = 0,
) -> dict:
    """Build a solution dict from a per-aircraft specification.

    Each spec is {"id", "position", "start", "finish", "jobs": [{"id","start","finish"}, ...]}.
    """
    aircraft_list = []
    for spec in aircraft_specs:
        aircraft_list.append({
            "id":       spec["id"],
            "position": spec["position"],
            "start":    spec["start"],
            "finish":   spec["finish"],
            "delay":    spec.get("delay", 0.0),
            "jobs":     spec["jobs"],
        })
    makespan = max(a["finish"] for a in aircraft_list) if aircraft_list else 0.0
    return {
        "status": "test",
        "objective": 0.0,
        "metrics": {
            "makespan":    makespan,
            "movements":   movements,
            "total_delay": 0.0,
        },
        "aircraft": aircraft_list,
    }


def _ac(a_id, pos, jobs, *, delay=0.0):
    """Convenience helper: build an aircraft spec with start/finish derived from jobs."""
    return {
        "id":       a_id,
        "position": pos,
        "start":    jobs[0]["start"],
        "finish":   jobs[-1]["finish"],
        "delay":    delay,
        "jobs":     jobs,
    }


# =============================================================================
#  Test 1 — Mode A: front position vacant
# =============================================================================

def test_mode_A_vacant_front_no_movement():
    """Rear aircraft enters BEFORE front aircraft starts: no manoeuvre."""
    instance = _make_instance(
        jobs=[
            {"id": "J1-1", "aircraft_id": "R1", "duration": 5, "is_first": True,
             "is_last": True, "interruptible": False},
            {"id": "J2-1", "aircraft_id": "R2", "duration": 5, "is_first": True,
             "is_last": True, "interruptible": False},
        ],
        aircrafts=[
            {"id": "R1", "client": "C1", "earliest_start": 0,  "target_finish": 100},
            {"id": "R2", "client": "C1", "earliest_start": 0,  "target_finish": 100},
        ],
        blocking_arcs=[("P1", "P2")],
    )
    sol = _make_solution([
        _ac("R1", "P1", [{"id": "J1-1", "start": 50.0, "finish": 55.0}]),
        _ac("R2", "P2", [{"id": "J2-1", "start": 0.0,  "finish":  5.0}]),
    ], movements=0)
    report = check_solution(sol, instance)
    assert report["compliant"], report["requirements"]
    assert report["requirements"]["RQ07"]["movements_count"] == 0
    for ev in report["requirements"]["RQ07"]["movements"]:
        assert ev["mode"] == "A", ev


# =============================================================================
#  Test 2 — Mode B: inter-job gap, gap == mu → OK
# =============================================================================

def test_mode_B_gap_exactly_mu_passes():
    """Rear entry falls in a gap of width exactly mu; Mode B with +2 movements
    on entry, Mode A on exit (after the blocker has finished)."""
    # Blocker R1 has two jobs at P1: [0,5] then [6,10] → gap [5,6] of width 1 = mu.
    # Rear R2 enters at tau=5.5 (Mode B in gap) and exits at tau=12 (Mode A
    # after r_finish=10).
    instance = _make_instance(
        jobs=[
            {"id": "J1-1", "aircraft_id": "R1", "duration": 5, "is_first": True,
             "is_last": False, "interruptible": False},
            {"id": "J1-2", "aircraft_id": "R1", "duration": 4, "is_first": False,
             "is_last": True, "interruptible": False},
            {"id": "J2-1", "aircraft_id": "R2", "duration": 7, "is_first": True,
             "is_last": True, "interruptible": False},
        ],
        aircrafts=[
            {"id": "R1", "client": "C1", "earliest_start": 0,  "target_finish": 100},
            {"id": "R2", "client": "C1", "earliest_start": 0,  "target_finish": 100},
        ],
        blocking_arcs=[("P1", "P2")],
        precedences=[("J1-1", "J1-2")],
    )
    sol = _make_solution([
        _ac("R1", "P1", [
            {"id": "J1-1", "start": 0.0, "finish": 5.0},
            {"id": "J1-2", "start": 6.0, "finish": 10.0},
        ]),
        _ac("R2", "P2", [
            {"id": "J2-1", "start": 5.5, "finish": 12.5},   # entry in gap, exit after stay
        ]),
    ], movements=2)   # single Mode-B entry = 2 movements
    report = check_solution(sol, instance)
    assert report["compliant"], report["requirements"]
    rq07 = report["requirements"]["RQ07"]
    assert rq07["movements_count"] == 2
    b_events = [ev for ev in rq07["movements"] if ev["mode"] == "B"]
    assert len(b_events) == 1, rq07["movements"]
    assert b_events[0]["type"] == "entry"


# =============================================================================
#  Test 3 — Mode B: gap shorter than mu → FAIL
# =============================================================================

def test_mode_B_gap_below_mu_fails():
    """Single Mode-B access in a gap < mu fails RQ07_v2 (gap shortfall)."""
    instance = _make_instance(
        jobs=[
            {"id": "J1-1", "aircraft_id": "R1", "duration": 5, "is_first": True,
             "is_last": False, "interruptible": False},
            {"id": "J1-2", "aircraft_id": "R1", "duration": 4, "is_first": False,
             "is_last": True, "interruptible": False},
            {"id": "J2-1", "aircraft_id": "R2", "duration": 1, "is_first": True,
             "is_last": True, "interruptible": False},
        ],
        aircrafts=[
            {"id": "R1", "client": "C1", "earliest_start": 0,  "target_finish": 100},
            {"id": "R2", "client": "C1", "earliest_start": 0,  "target_finish": 100},
        ],
        blocking_arcs=[("P1", "P2")],
        precedences=[("J1-1", "J1-2")],
        mu=2.0,        # require 2 days of gap, but R1 only leaves 1 day.
    )
    sol = _make_solution([
        _ac("R1", "P1", [
            {"id": "J1-1", "start": 0.0, "finish": 5.0},
            {"id": "J1-2", "start": 6.0, "finish": 10.0},
        ]),
        _ac("R2", "P2", [
            {"id": "J2-1", "start": 5.4, "finish": 5.6},
        ]),
    ], movements=4)
    report = check_solution(sol, instance)
    rq07 = report["requirements"]["RQ07"]
    assert not rq07["pass"], "Gap < mu should fail RQ07_v2"
    assert len(rq07["gap_violations"]) >= 1


# =============================================================================
#  Test 4 — Mode C: strictly inside interruptible job, kappa += 1
# =============================================================================

def test_mode_C_interruptible_job_increments_kappa():
    """Rear access mid-interruptible-job → +2 movements, job extended by delta."""
    instance = _make_instance(
        jobs=[
            {"id": "J1-1", "aircraft_id": "R1", "duration": 6, "is_first": True,
             "is_last": True, "interruptible": True},
            {"id": "J2-1", "aircraft_id": "R2", "duration": 1, "is_first": True,
             "is_last": True, "interruptible": False},
        ],
        aircrafts=[
            {"id": "R1", "client": "C1", "earliest_start": 0,  "target_finish": 100},
            {"id": "R2", "client": "C1", "earliest_start": 0,  "target_finish": 100},
        ],
        blocking_arcs=[("P1", "P2")],
    )
    # R1's J1-1: nominal 6 + delta*kappa_j. kappa_j=2 (one Mode-C on entry, one
    # on exit) → finish = 0 + 6 + 2*2 = 10
    sol = _make_solution([
        _ac("R1", "P1", [
            {"id": "J1-1", "start": 0.0, "finish": 10.0},  # +4 days extension
        ]),
        _ac("R2", "P2", [
            {"id": "J2-1", "start": 3.0, "finish": 4.0},
        ]),
    ], movements=4)
    report = check_solution(sol, instance)
    assert report["compliant"], report["requirements"]
    rq03 = report["requirements"]["RQ03"]
    assert rq03["inferred_kappa"]["J1-1"] == 2
    rq07 = report["requirements"]["RQ07"]
    assert rq07["movements_count"] == 4
    assert all(ev["mode"] == "C" for ev in rq07["movements"]), rq07["movements"]
    # RQ09 ties together: 2 inferred from duration == 2 events counted
    assert report["requirements"]["RQ09"]["pass"]


# =============================================================================
#  Test 5 — Mode C on a non-interruptible job → INFEASIBLE
# =============================================================================

def test_mode_C_on_non_interruptible_job_fails():
    """Rear access strictly inside a non-interruptible job: RQ07_v2 must fail."""
    instance = _make_instance(
        jobs=[
            {"id": "J1-1", "aircraft_id": "R1", "duration": 6, "is_first": True,
             "is_last": True, "interruptible": False},  # NOT interruptible
            {"id": "J2-1", "aircraft_id": "R2", "duration": 1, "is_first": True,
             "is_last": True, "interruptible": False},
        ],
        aircrafts=[
            {"id": "R1", "client": "C1", "earliest_start": 0,  "target_finish": 100},
            {"id": "R2", "client": "C1", "earliest_start": 0,  "target_finish": 100},
        ],
        blocking_arcs=[("P1", "P2")],
    )
    sol = _make_solution([
        _ac("R1", "P1", [
            {"id": "J1-1", "start": 0.0, "finish": 6.0},  # nominal
        ]),
        _ac("R2", "P2", [
            {"id": "J2-1", "start": 3.0, "finish": 4.0},  # strictly inside J1-1
        ]),
    ], movements=0)
    report = check_solution(sol, instance)
    rq07 = report["requirements"]["RQ07"]
    assert not rq07["pass"], "Mid non-interruptible job should be infeasible"
    assert any("non-interruptible" in ev["reason"]
               for ev in rq07["infeasibilities"]), rq07["infeasibilities"]


# =============================================================================
#  Test 6 — Cumulative Mode-B: two accesses in one gap need 2*mu
# =============================================================================

def test_mode_B_two_accesses_need_cumulative_gap():
    """Two separate Mode-B accesses sharing one gap require gap >= 2*mu."""
    # Blocker R1 has two jobs with a gap of 1.5 (< 2*mu=2).
    # Two rear aircraft R2, R3 each use the gap with their entry → 2 accesses.
    instance = _make_instance(
        jobs=[
            {"id": "J1-1", "aircraft_id": "R1", "duration": 5, "is_first": True,
             "is_last": False, "interruptible": False},
            {"id": "J1-2", "aircraft_id": "R1", "duration": 4, "is_first": False,
             "is_last": True, "interruptible": False},
            {"id": "J2-1", "aircraft_id": "R2", "duration": 0.2, "is_first": True,
             "is_last": True, "interruptible": False},
            {"id": "J3-1", "aircraft_id": "R3", "duration": 0.2, "is_first": True,
             "is_last": True, "interruptible": False},
        ],
        aircrafts=[
            {"id": "R1", "client": "C1", "earliest_start": 0,  "target_finish": 100},
            {"id": "R2", "client": "C1", "earliest_start": 0,  "target_finish": 100},
            {"id": "R3", "client": "C1", "earliest_start": 0,  "target_finish": 100},
        ],
        blocking_arcs=[("P1", "P2"), ("P1", "P3")],
        precedences=[("J1-1", "J1-2")],
        positions=["P1", "P2", "P3"],
    )
    sol = _make_solution([
        _ac("R1", "P1", [
            {"id": "J1-1", "start": 0.0, "finish": 5.0},
            {"id": "J1-2", "start": 6.5, "finish": 10.5},  # gap of 1.5
        ]),
        _ac("R2", "P2", [
            {"id": "J2-1", "start": 5.7, "finish": 5.9},
        ]),
        _ac("R3", "P3", [
            {"id": "J3-1", "start": 6.0, "finish": 6.2},
        ]),
    ], movements=8)
    report = check_solution(sol, instance)
    rq07 = report["requirements"]["RQ07"]
    # 4 accesses (entry+exit of R2 and R3) all use the gap; required = 4*mu=4
    # but gap = 1.5 → shortfall
    assert not rq07["pass"], "Cumulative gap rule should fire"
    assert len(rq07["gap_violations"]) == 1
    gv = rq07["gap_violations"][0]
    assert gv["n_accesses"] == 4
    assert gv["required"] == pytest.approx(4.0)


# =============================================================================
#  Test 7 — RQ09: declared kappa mismatch with counted Mode-C events
# =============================================================================

def test_rq09_kappa_mismatch_fails():
    """Solution claims an extension but no Mode-C event is detected."""
    instance = _make_instance(
        jobs=[
            {"id": "J1-1", "aircraft_id": "R1", "duration": 6, "is_first": True,
             "is_last": True, "interruptible": True},
        ],
        aircrafts=[
            {"id": "R1", "client": "C1", "earliest_start": 0,  "target_finish": 100},
        ],
        blocking_arcs=[],
    )
    # Job extended by 2 days (kappa=1) but no Mode-C event exists.
    sol = _make_solution([
        _ac("R1", "P1", [
            {"id": "J1-1", "start": 0.0, "finish": 8.0},  # 6 + delta=2 ⇒ kappa=1
        ]),
    ], movements=0)
    report = check_solution(sol, instance)
    assert not report["requirements"]["RQ09"]["pass"], \
        "Extension without matching Mode-C event should fail RQ09"


# =============================================================================
#  Test 8 — Extension on a non-interruptible job is forbidden by RQ03_v2
# =============================================================================

def test_rq03_v2_extension_on_non_interruptible_fails():
    instance = _make_instance(
        jobs=[
            {"id": "J1-1", "aircraft_id": "R1", "duration": 6, "is_first": True,
             "is_last": True, "interruptible": False},
        ],
        aircrafts=[
            {"id": "R1", "client": "C1", "earliest_start": 0,  "target_finish": 100},
        ],
    )
    sol = _make_solution([
        _ac("R1", "P1", [
            {"id": "J1-1", "start": 0.0, "finish": 8.0},  # extended by 2 = delta
        ]),
    ], movements=0)
    report = check_solution(sol, instance)
    assert not report["requirements"]["RQ03"]["pass"], \
        "Duration extension on non-interruptible job should fail RQ03_v2"
