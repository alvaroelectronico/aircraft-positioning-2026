"""Unit tests for RQ08: minimum separation between consecutive aircraft at the same position."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "output_data"))
from check_solution import check_solution

DELTA = 10.0


def _make_instance(min_separation=DELTA):
    return {
        "min_separation": min_separation,
        "jobs": [],
        "aircrafts": [],
        "hangar": {"blocking_arcs": []},
        "job_precedences": [],
    }


def _make_solution(aircraft_list):
    """aircraft_list: [(id, position, start, finish), ...]"""
    aircraft = []
    for aid, pos, s, f in aircraft_list:
        aircraft.append({
            "id": aid,
            "position": pos,
            "start": s,
            "finish": f,
            "delay": 0.0,
            "jobs": [],
        })
    return {
        "status": "test",
        "objective": 0.0,
        "metrics": {"makespan": 0.0, "movements": 0, "total_delay": 0.0},
        "aircraft": aircraft,
    }


# --- Test 1: 2 aircraft, 1 position, gap = 0 → FAIL ---
def test_gap_zero_fails():
    instance = _make_instance()
    sol = _make_solution([
        ("A1", "P1", 0.0,  30.0),
        ("A2", "P1", 30.0, 60.0),   # gap = 30.0 - 30.0 = 0 < delta=10
    ])
    report = check_solution(sol, instance)
    rq08 = report["requirements"]["RQ08"]
    assert not rq08["pass"], "Expected RQ08 to FAIL with gap=0"
    assert rq08["num_violations"] == 1
    assert abs(rq08["violations"][0]["shortfall"] - 10.0) < 1e-6
    print("test_gap_zero_fails: PASS")


# --- Test 2: 2 aircraft, 1 position, gap = delta → PASS ---
def test_gap_exactly_delta_passes():
    instance = _make_instance()
    sol = _make_solution([
        ("A1", "P1", 0.0,  30.0),
        ("A2", "P1", 40.0, 70.0),   # gap = 40 - 30 = 10 = delta
    ])
    report = check_solution(sol, instance)
    rq08 = report["requirements"]["RQ08"]
    assert rq08["pass"], f"Expected RQ08 to PASS with gap=delta, got: {rq08['detail']}"
    assert rq08["num_violations"] == 0
    print("test_gap_exactly_delta_passes: PASS")


# --- Test 3: 3 aircraft, 1 position, all gaps >= delta → PASS ---
def test_three_aircraft_all_gaps_ok():
    instance = _make_instance()
    sol = _make_solution([
        ("A1", "P1", 0.0,  20.0),
        ("A2", "P1", 30.0, 50.0),   # gap = 10 = delta
        ("A3", "P1", 65.0, 80.0),   # gap = 15 > delta
    ])
    report = check_solution(sol, instance)
    rq08 = report["requirements"]["RQ08"]
    assert rq08["pass"], f"Expected RQ08 to PASS, got: {rq08['detail']}"
    assert rq08["num_violations"] == 0
    assert abs(rq08["min_same_pos_gap"] - 10.0) < 1e-6
    print("test_three_aircraft_all_gaps_ok: PASS")


# --- Test 4: gap > delta → PASS ---
def test_gap_above_delta_passes():
    instance = _make_instance()
    sol = _make_solution([
        ("A1", "P1", 0.0,  20.0),
        ("A2", "P1", 35.0, 55.0),   # gap = 15 > delta
    ])
    report = check_solution(sol, instance)
    rq08 = report["requirements"]["RQ08"]
    assert rq08["pass"]
    print("test_gap_above_delta_passes: PASS")


# --- Test 5: gap < delta (but > 0) → FAIL ---
def test_gap_partial_violation_fails():
    instance = _make_instance()
    sol = _make_solution([
        ("A1", "P1", 0.0,  30.0),
        ("A2", "P1", 35.0, 65.0),   # gap = 5 < delta=10
    ])
    report = check_solution(sol, instance)
    rq08 = report["requirements"]["RQ08"]
    assert not rq08["pass"]
    assert rq08["num_violations"] == 1
    assert abs(rq08["violations"][0]["shortfall"] - 5.0) < 1e-6
    print("test_gap_partial_violation_fails: PASS")


# --- Test 6: 2 aircraft at different positions → not checked against each other ---
def test_different_positions_ignored():
    instance = _make_instance()
    sol = _make_solution([
        ("A1", "P1", 0.0,  30.0),
        ("A2", "P2", 30.0, 60.0),   # different position, gap irrelevant for RQ08
    ])
    report = check_solution(sol, instance)
    rq08 = report["requirements"]["RQ08"]
    assert rq08["pass"]
    assert rq08["min_same_pos_gap"] is None   # no same-position pairs
    print("test_different_positions_ignored: PASS")


if __name__ == "__main__":
    test_gap_zero_fails()
    test_gap_exactly_delta_passes()
    test_three_aircraft_all_gaps_ok()
    test_gap_above_delta_passes()
    test_gap_partial_violation_fails()
    test_different_positions_ignored()
    print("\nAll RQ08 tests passed.")
