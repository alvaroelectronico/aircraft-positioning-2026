"""
check_solution.py — Verifies a solution against all requirements in problem_statement.tex.

Usage
-----
As a library:
    from check_solution import check_solution, print_check
    report = check_solution(solution, instance)
    print_check(report)

As a script:
    python check_solution.py <instance_path> <solution_json_path>

Parameters
----------
solution : dict
    Output of get_solution() — see models/milp_pyomo.py for schema.
instance : dict
    Raw instance data loaded by load_instance().

Return schema of check_solution()
----------------------------------
{
    "compliant": bool,           # True only if all hard requirements pass
    "requirements": {
        "RQ01": {"pass": bool, "detail": str},
        "RQ02": {"pass": bool, "detail": str},
        "RQ03": {"pass": bool, "detail": str},
        "RQ04": {"pass": bool, "detail": str, "delays": [str]},
        "RQ05": {"pass": bool, "detail": str},
        "RQ06": {"pass": bool, "detail": str},
        "RQ07": {
            "pass":             bool,
            "movements_count":  int,      # inferred from blocking analysis
            "movements":        [         # one entry per blocking event
                {
                    "type":                 "entry" | "exit",
                    "event":                str,          # human-readable summary
                    "blocker":              str,          # aircraft that moves temporarily
                    "blocker_position":     str,          # front (blocking) position
                    "blocked":              str,          # aircraft that needs access
                    "blocked_position":     str,          # rear (blocked) position
                    "blocking_arc":         [str, str],   # [front, rear]
                    "trigger_time":         float,        # start or finish of blocked aircraft
                    "blocker_active_window":[float, float],
                    "returns_to":           str,          # always == blocker_position
                    "movements_generated":  int,          # always 2 (out + back)
                }
            ],
            "detail": str,
        },
        "RQ08": {
            "pass":                  bool,
            "num_violations":        int,    # pairs with gap < delta
            "min_same_pos_gap":      float,  # smallest observed gap (None if no pairs)
            "worst_violation":       float,  # largest shortfall below delta (0 if none)
            "violations":            [       # one entry per violating pair
                {
                    "position":  str,
                    "first":     str,   # aircraft id finishing first
                    "second":    str,   # aircraft id starting second
                    "gap":       float, # S_second - F_first
                    "shortfall": float, # delta - gap
                }
            ],
            "detail": str,
        },
    }
}
"""

from __future__ import annotations

TOL = 1e-4  # numerical tolerance for float comparisons


# =============================================================================
#  Main verification function
# =============================================================================

def check_solution(solution: dict, instance: dict) -> dict:
    """Verify *solution* against all requirements defined in problem_statement.tex.

    Parameters
    ----------
    solution:
        Dict returned by ``get_solution()`` (milp_pyomo.py).
    instance:
        Raw instance dict loaded by ``load_instance()``.

    Returns
    -------
    Report dict — see module docstring for the full schema.
    """

    # ------------------------------------------------------------------ #
    #  Build lookup structures                                             #
    # ------------------------------------------------------------------ #
    job_by_id      = {j["id"]: j for j in instance["jobs"]}
    aircraft_by_id = {a["id"]: a for a in instance["aircrafts"]}
    blocking_arcs  = [
        (arc["front"], arc["rear"]) for arc in instance["hangar"]["blocking_arcs"]
    ]
    precedences = [
        (p["before"], p["after"]) for p in instance["job_precedences"]
    ]

    # Flat job lookup: job_id -> {start, finish, aircraft_id, position}
    job_sol: dict[str, dict] = {}
    for a in solution["aircraft"]:
        for j in a["jobs"]:
            job_sol[j["id"]] = {
                "start":       j["start"],
                "finish":      j["finish"],
                "aircraft_id": a["id"],
                "position":    a["position"],
            }

    aircraft_sol = {a["id"]: a for a in solution["aircraft"]}

    # Position -> [(aircraft_id, start, finish), ...]
    position_occupancy: dict[str, list[tuple]] = {}
    for a in solution["aircraft"]:
        p = a["position"]
        position_occupancy.setdefault(p, []).append(
            (a["id"], a["start"], a["finish"])
        )

    results: dict[str, dict] = {}
    all_pass = True

    # ------------------------------------------------------------------ #
    #  RQ01 — Each job assigned to exactly one position                   #
    # ------------------------------------------------------------------ #
    rq01_failures = []
    instance_job_ids = {j["id"] for j in instance["jobs"]}
    solution_job_ids = set(job_sol.keys())

    missing = sorted(instance_job_ids - solution_job_ids)
    extra   = sorted(solution_job_ids - instance_job_ids)
    if missing:
        rq01_failures.append(f"Jobs missing from solution: {missing}")
    if extra:
        rq01_failures.append(f"Unexpected jobs in solution: {extra}")

    results["RQ01"] = {
        "pass":   not rq01_failures,
        "detail": (
            f"All {len(instance_job_ids)} jobs accounted for with exactly one position each."
            if not rq01_failures
            else "; ".join(rq01_failures)
        ),
    }
    if rq01_failures:
        all_pass = False

    # ------------------------------------------------------------------ #
    #  RQ02 — Each aircraft assigned to a single position;                #
    #         all its jobs executed in that position                       #
    # ------------------------------------------------------------------ #
    rq02_failures = []
    instance_aircraft_ids = {a["id"] for a in instance["aircrafts"]}
    solution_aircraft_ids = set(aircraft_sol.keys())

    missing_a = sorted(instance_aircraft_ids - solution_aircraft_ids)
    if missing_a:
        rq02_failures.append(f"Aircraft missing from solution: {missing_a}")

    for a in solution["aircraft"]:
        a_id = a["id"]
        if a_id not in aircraft_by_id:
            rq02_failures.append(f"Aircraft {a_id} in solution is not in the instance.")
            continue
        for j in a["jobs"]:
            if job_sol[j["id"]]["position"] != a["position"]:
                rq02_failures.append(
                    f"Job {j['id']} of aircraft {a_id} is at position "
                    f"{job_sol[j['id']]['position']}, but aircraft assigned to {a['position']}."
                )

    assignment_summary = ", ".join(
        f"{a['id']}→{a['position']}" for a in solution["aircraft"]
    )
    results["RQ02"] = {
        "pass":   not rq02_failures,
        "detail": (
            f"Each aircraft assigned to exactly one position and all jobs co-located. "
            f"Assignments: {assignment_summary}."
            if not rq02_failures
            else "; ".join(rq02_failures)
        ),
    }
    if rq02_failures:
        all_pass = False

    # ------------------------------------------------------------------ #
    #  RQ03 — Processing times respected                                  #
    # ------------------------------------------------------------------ #
    rq03_failures = []
    for j_id, j_s in job_sol.items():
        if j_id not in job_by_id:
            continue
        expected = job_by_id[j_id]["duration"]
        actual   = j_s["finish"] - j_s["start"]
        if abs(actual - expected) > TOL:
            rq03_failures.append(
                f"Job {j_id}: expected duration {expected}, "
                f"actual {actual:.4f} (start={j_s['start']}, finish={j_s['finish']})."
            )

    results["RQ03"] = {
        "pass":   not rq03_failures,
        "detail": (
            f"All {len(job_sol)} job durations match instance data."
            if not rq03_failures
            else "; ".join(rq03_failures)
        ),
    }
    if rq03_failures:
        all_pass = False

    # ------------------------------------------------------------------ #
    #  RQ04 — Aircraft-level time windows                                 #
    #  • earliest_start is a hard constraint                              #
    #  • target_finish is soft (minimised as delay); reported as warning  #
    # ------------------------------------------------------------------ #
    rq04_failures = []
    rq04_delays   = []
    for a in solution["aircraft"]:
        a_id = a["id"]
        if a_id not in aircraft_by_id:
            continue
        earliest = aircraft_by_id[a_id]["earliest_start"]
        target   = aircraft_by_id[a_id]["target_finish"]

        if a["start"] < earliest - TOL:
            rq04_failures.append(
                f"Aircraft {a_id}: starts at {a['start']:.2f}, "
                f"before earliest_start={earliest}."
            )
        if a["finish"] > target + TOL:
            rq04_delays.append(
                f"Aircraft {a_id}: finishes at {a['finish']:.2f}, "
                f"delay={a['delay']:.2f} (target_finish={target})."
            )

    results["RQ04"] = {
        "pass": not rq04_failures,
        "detail": (
            "All earliest-start constraints satisfied."
            if not rq04_failures
            else "; ".join(rq04_failures)
        ) + (
            f" Delays (soft): {'; '.join(rq04_delays)}"
            if rq04_delays else ""
        ),
        "delays": rq04_delays,
    }
    if rq04_failures:
        all_pass = False

    # ------------------------------------------------------------------ #
    #  RQ05 — Precedences respected                                       #
    # ------------------------------------------------------------------ #
    rq05_failures = []
    for (j_before, j_after) in precedences:
        if j_before not in job_sol or j_after not in job_sol:
            continue
        s_after  = job_sol[j_after]["start"]
        f_before = job_sol[j_before]["finish"]
        if s_after < f_before - TOL:
            rq05_failures.append(
                f"Precedence {j_before}→{j_after} violated: "
                f"{j_after} starts at {s_after:.2f} "
                f"before {j_before} finishes at {f_before:.2f}."
            )

    results["RQ05"] = {
        "pass":   not rq05_failures,
        "detail": (
            f"All {len(precedences)} precedence relation(s) respected."
            if not rq05_failures
            else "; ".join(rq05_failures)
        ),
    }
    if rq05_failures:
        all_pass = False

    # ------------------------------------------------------------------ #
    #  RQ06 — No two jobs overlap at the same position                    #
    # ------------------------------------------------------------------ #
    rq06_failures = []
    jobs_by_position: dict[str, list[tuple]] = {}
    for j_id, j_s in job_sol.items():
        jobs_by_position.setdefault(j_s["position"], []).append(
            (j_id, j_s["start"], j_s["finish"])
        )

    for pos, pos_jobs in jobs_by_position.items():
        for i, (j1_id, s1, f1) in enumerate(pos_jobs):
            for (j2_id, s2, f2) in pos_jobs[i + 1:]:
                if s1 < f2 - TOL and s2 < f1 - TOL:
                    rq06_failures.append(
                        f"Position {pos}: jobs {j1_id} [{s1:.2f}, {f1:.2f}] "
                        f"and {j2_id} [{s2:.2f}, {f2:.2f}] overlap."
                    )

    results["RQ06"] = {
        "pass":   not rq06_failures,
        "detail": (
            "No overlapping jobs at any position."
            if not rq06_failures
            else "; ".join(rq06_failures)
        ),
    }
    if rq06_failures:
        all_pass = False

    # ------------------------------------------------------------------ #
    #  RQ07 — Blocking movements                                          #
    #                                                                      #
    #  For each blocking arc (p_front, p_rear) and each pair of aircraft  #
    #  (r at p_front, rp at p_rear) we detect two kinds of events:        #
    #                                                                      #
    #  ENTRY — rp_start falls strictly inside (r_start, r_finish):        #
    #    r must move out temporarily so that rp can enter p_rear,         #
    #    then r returns to p_front.                                        #
    #    Simultaneous start (rp_start == r_start) is NOT a blocking       #
    #    event: both aircraft can be positioned together.                  #
    #                                                                      #
    #  EXIT  — rp_finish falls strictly inside (r_start, r_finish):       #
    #    r must move out temporarily so that rp can exit p_rear,          #
    #    then r returns to p_front.                                        #
    #    Simultaneous finish/start (rp_finish == r_start) is NOT          #
    #    a blocking event: rp can exit as r arrives.                       #
    #                                                                      #
    #  Each event generates exactly 2 movements (out + back).             #
    #  The inferred count is cross-checked against                        #
    #  solution["metrics"]["movements"].                                   #
    # ------------------------------------------------------------------ #
    movements: list[dict] = []

    for (p_front, p_rear) in blocking_arcs:
        front_aircraft = position_occupancy.get(p_front, [])
        rear_aircraft  = position_occupancy.get(p_rear,  [])

        for (r_id, r_start, r_finish) in front_aircraft:
            for (rp_id, rp_start, rp_finish) in rear_aircraft:

                # ENTRY: rp starts STRICTLY after r (simultaneous start → no blocking,
                # consistent with MILP: alphaIn=0 is feasible when start[rp] <= start[r]).
                if r_start + TOL < rp_start < r_finish - TOL:
                    movements.append({
                        "type":                  "entry",
                        "event":                 (
                            f"{r_id} (at {p_front}) must temporarily move "
                            f"to allow {rp_id} to ENTER {p_rear}"
                        ),
                        "blocker":               r_id,
                        "blocker_position":      p_front,
                        "blocked":               rp_id,
                        "blocked_position":      p_rear,
                        "blocking_arc":          [p_front, p_rear],
                        "trigger_time":          rp_start,
                        "blocker_active_window": [r_start, r_finish],
                        "returns_to":            p_front,
                        "movements_generated":   2,
                    })

                # EXIT: rp finishes STRICTLY after r starts (simultaneous finish/entry → no
                # blocking, consistent with MILP: alphaOut=0 feasible when finish[rp] <= start[r]).
                if r_start + TOL < rp_finish < r_finish - TOL:
                    movements.append({
                        "type":                  "exit",
                        "event":                 (
                            f"{r_id} (at {p_front}) must temporarily move "
                            f"to allow {rp_id} to EXIT {p_rear}"
                        ),
                        "blocker":               r_id,
                        "blocker_position":      p_front,
                        "blocked":               rp_id,
                        "blocked_position":      p_rear,
                        "blocking_arc":          [p_front, p_rear],
                        "trigger_time":          rp_finish,
                        "blocker_active_window": [r_start, r_finish],
                        "returns_to":            p_front,
                        "movements_generated":   2,
                    })

    inferred_count  = sum(m["movements_generated"] for m in movements)
    reported_count  = solution["metrics"]["movements"]
    count_match     = inferred_count == reported_count

    rq07_failures = []
    if not count_match:
        rq07_failures.append(
            f"Movement count mismatch: blocking analysis infers {inferred_count} "
            f"movements ({len(movements)} event(s) × 2), "
            f"but solution reports {reported_count}."
        )

    # Verify each blocker always returns to its assigned position:
    # because each aircraft has exactly one position in the solution dict,
    # the "returns_to" field is structurally guaranteed to equal "blocker_position".
    # Any inconsistency here would already have been caught by RQ02.

    movements_sorted = sorted(movements, key=lambda m: m["trigger_time"])

    results["RQ07"] = {
        "pass":            not rq07_failures,
        "movements_count": inferred_count,
        "movements":       movements_sorted,
        "detail": (
            f"{inferred_count} movement(s) from {len(movements)} blocking event(s), "
            f"matching solution metrics."
            if not rq07_failures
            else "; ".join(rq07_failures)
        ),
    }
    if rq07_failures:
        all_pass = False

    # ------------------------------------------------------------------ #
    #  RQ08 — Minimum separation between consecutive aircraft at the      #
    #          same position: S_next >= F_prev + delta                    #
    # ------------------------------------------------------------------ #
    min_sep = instance.get("min_separation", 10.0)

    rq08_violations: list[dict] = []
    min_gap: float | None = None

    for pos, occupants in position_occupancy.items():
        if len(occupants) < 2:
            continue
        sorted_occ = sorted(occupants, key=lambda x: x[1])  # sort by start
        for i in range(len(sorted_occ) - 1):
            r_id,  _, r_finish  = sorted_occ[i]
            rp_id, rp_start, _  = sorted_occ[i + 1]
            gap = rp_start - r_finish
            if min_gap is None or gap < min_gap:
                min_gap = gap
            if gap < min_sep - TOL:
                rq08_violations.append({
                    "position":  pos,
                    "first":     r_id,
                    "second":    rp_id,
                    "gap":       gap,
                    "shortfall": min_sep - gap,
                })

    worst_violation = max((v["shortfall"] for v in rq08_violations), default=0.0)
    rq08_pass = len(rq08_violations) == 0

    results["RQ08"] = {
        "pass":             rq08_pass,
        "num_violations":   len(rq08_violations),
        "min_same_pos_gap": min_gap,
        "worst_violation":  worst_violation,
        "violations":       rq08_violations,
        "detail": (
            (
                f"All consecutive same-position pairs separated by >= {min_sep} min "
                f"(min gap = {min_gap:.2f})."
                if min_gap is not None
                else "No consecutive same-position pairs to check."
            )
            if rq08_pass
            else (
                f"{len(rq08_violations)} separation violation(s) detected "
                f"(delta={min_sep}, worst shortfall={worst_violation:.2f}, "
                f"min gap={min_gap:.2f})."
            )
        ),
    }
    if not rq08_pass:
        all_pass = False

    return {
        "compliant":    all_pass,
        "requirements": results,
    }


# =============================================================================
#  Pretty-printer
# =============================================================================

def print_check(report: dict, indent: int = 4) -> None:
    """Print *report* (output of ``check_solution``) in a human-readable format."""
    pad = " " * indent

    status = "COMPLIANT" if report["compliant"] else "NON-COMPLIANT"
    bar    = "=" * 60
    print(bar)
    print(f"  Solution Check — Overall: {status}")
    print(bar)

    for rq_id, info in report["requirements"].items():
        mark = "PASS" if info["pass"] else "FAIL"
        print(f"\n[{mark}] {rq_id}")

        if rq_id == "RQ07":
            print(f"{pad}{info['detail']}")
            if not info["movements"]:
                print(f"{pad}No blocking events detected.")
            else:
                print(f"{pad}Blocking events (sorted by trigger time):")
                for i, m in enumerate(info["movements"], start=1):
                    print(
                        f"{pad}  [{i}] {m['type'].upper()} — trigger t={m['trigger_time']:.2f}"
                    )
                    print(f"{pad}       {m['event']}")
                    print(
                        f"{pad}       Blocking arc : {m['blocking_arc'][0]} → {m['blocking_arc'][1]}"
                    )
                    print(
                        f"{pad}       Blocker window: "
                        f"[{m['blocker_active_window'][0]:.2f}, "
                        f"{m['blocker_active_window'][1]:.2f}]"
                    )
                    print(
                        f"{pad}       {m['blocker']} moves out of {m['blocker_position']}, "
                        f"then returns to {m['returns_to']}  "
                        f"(+{m['movements_generated']} movements)"
                    )
        elif rq_id == "RQ08":
            print(f"{pad}{info['detail']}")
            if info["violations"]:
                print(f"{pad}Violations:")
                for v in info["violations"]:
                    print(
                        f"{pad}  Position {v['position']}: "
                        f"{v['first']} → {v['second']}  "
                        f"gap={v['gap']:.2f}  shortfall={v['shortfall']:.2f}"
                    )
        else:
            print(f"{pad}{info['detail']}")
            if rq_id == "RQ04" and info.get("delays"):
                for d in info["delays"]:
                    print(f"{pad}  ! {d}")

    print(f"\n{bar}")
    print(f"  Hard requirements: {'all passed' if report['compliant'] else 'ONE OR MORE FAILED'}")
    print(bar)


# =============================================================================
#  CLI entry point
# =============================================================================

if __name__ == "__main__":
    import json
    import os
    import sys

    sys.path.insert(
        0, os.path.join(os.path.dirname(__file__), "..", "input_data")
    )
    from instance_io import load_json as load_instance  # noqa: E402

    if len(sys.argv) != 3:
        print(
            "Usage: python check_solution.py <instance_path> <solution_json_path>",
            file=sys.stderr,
        )
        sys.exit(1)

    instance_path = sys.argv[1]
    solution_path = sys.argv[2]

    raw_instance = load_instance(instance_path)
    with open(solution_path, "r", encoding="utf-8") as fh:
        raw_solution = json.load(fh)

    report = check_solution(raw_solution, raw_instance)
    print_check(report)
