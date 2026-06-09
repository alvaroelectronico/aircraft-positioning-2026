"""
check_solution_jobs_v2.py — verifies a solution against the **paper #2**
problem statement (job-level scheduling with refined blocking semantics).

This is a sibling module to ``check_solution.py``.  Paper #1's checker is
intentionally untouched; paper-#2 callers use this module instead.  The
public API is identical:

    from check_solution_jobs_v2 import check_solution, print_check
    report = check_solution(solution, instance)
    print_check(report)

Requirements validated
----------------------
* RQ01 — Each job assigned exactly once (identical to v1)
* RQ02 — Each aircraft on a single position; all its jobs co-located (identical to v1)
* RQ03_v2 — Job duration matches  D_j + delta * kappa_j  for some non-negative
            integer kappa_j, and kappa_j = 0 when the job is not interruptible
* RQ04 — Earliest-start / target-finish handling (identical to v1)
* RQ05 — Job precedences respected (identical to v1)
* RQ06 — No overlapping jobs at the same position (identical to v1)
* RQ07_v2 — Every access (entry and exit) of every rear aircraft is classified
            into Mode A (front vacant), Mode B (inter-job gap, cumulative gap
            >= mu * #accesses), or Mode C (strictly inside interruptible job).
            An access that falls inside a non-interruptible job is infeasible.
* RQ08 — Minimum separation between consecutive aircraft at the same position
         (identical to v1, parameter epsilon = ``min_separation``)
* RQ09 — Per-job interruption counter consistency: the kappa_j inferred from
         RQ03_v2 must equal the number of Mode-C events triggered against
         job j across all rear neighbours and both access sides.

Instance parameters
-------------------
Reads with safe defaults:
    instance["min_separation"]   -> epsilon (existing key; required by schema)
    instance.get("mu", 1.0)      -> Mode-B inter-job pause
    instance.get("delta", 2.0)   -> Mode-C job extension
    instance.get("eta", 1.0)     -> granularity for strict inequalities

For every job j:
    job.get("interruptible", False) -> I_j

Return schema
-------------
Same shape as v1 (compliant flag + per-RQ dicts), with two additions:
``RQ07_v2`` (replaces RQ07) carries an extra ``mode`` field per event,
and a new ``RQ09`` key.
"""

from __future__ import annotations

TOL = 1e-4   # numerical tolerance for float comparisons

# Defaults used when an instance does not carry the paper-#2 fields
DEFAULT_MU    = 1.0
DEFAULT_DELTA = 2.0
DEFAULT_ETA   = 1.0


# =============================================================================
#  Main verification function
# =============================================================================

def check_solution(solution: dict, instance: dict) -> dict:
    """Verify *solution* against the paper-#2 requirements.

    See module docstring for the report schema.
    """
    # ------------------------------------------------------------------ #
    #  Lookup structures                                                  #
    # ------------------------------------------------------------------ #
    job_by_id      = {j["id"]: j for j in instance["jobs"]}
    aircraft_by_id = {a["id"]: a for a in instance["aircrafts"]}
    blocking_arcs  = [
        (arc["front"], arc["rear"]) for arc in instance["hangar"]["blocking_arcs"]
    ]
    precedences = [
        (p["before"], p["after"]) for p in instance["job_precedences"]
    ]

    epsilon = instance.get("min_separation", 0.5)
    mu      = instance.get("mu",    DEFAULT_MU)
    delta   = instance.get("delta", DEFAULT_DELTA)
    eta     = instance.get("eta",   DEFAULT_ETA)

    # Flat lookup: job_id -> {start, finish, aircraft_id, position}
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

    # Per-aircraft ordered job list (by start time, ties broken by precedence).
    # We rebuild the chain from the solution to match the order in which jobs
    # actually run; the instance precedences are used only by RQ05.
    chain_by_aircraft: dict[str, list[str]] = {}
    for a in solution["aircraft"]:
        ordered = sorted(
            [j["id"] for j in a["jobs"]],
            key=lambda jid: (job_sol[jid]["start"], jid),
        )
        chain_by_aircraft[a["id"]] = ordered

    # Position -> list[(aircraft_id, start, finish)]
    position_occupancy: dict[str, list[tuple]] = {}
    for a in solution["aircraft"]:
        position_occupancy.setdefault(a["position"], []).append(
            (a["id"], a["start"], a["finish"])
        )

    results: dict[str, dict] = {}
    all_pass = True

    # ------------------------------------------------------------------ #
    #  RQ01 — each job assigned exactly once                              #
    # ------------------------------------------------------------------ #
    rq01_failures: list[str] = []
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
            if not rq01_failures else "; ".join(rq01_failures)
        ),
    }
    if rq01_failures:
        all_pass = False

    # ------------------------------------------------------------------ #
    #  RQ02 — single position per aircraft; all its jobs co-located       #
    # ------------------------------------------------------------------ #
    rq02_failures: list[str] = []
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
            if not rq02_failures else "; ".join(rq02_failures)
        ),
    }
    if rq02_failures:
        all_pass = False

    # ------------------------------------------------------------------ #
    #  RQ03_v2 — Job duration matches D_j + delta * kappa_j               #
    #                                                                      #
    #  For each job j in the solution we infer                            #
    #      kappa_j = round( (finish - start - D_j) / delta )              #
    #  and require:                                                        #
    #    * (finish - start - D_j) is a non-negative integer multiple of   #
    #      delta (within TOL),                                             #
    #    * kappa_j = 0 when I_j = 0.                                       #
    #                                                                      #
    #  The kappa_j inferred here is used downstream by RQ09 to             #
    #  cross-check the count of Mode-C events.                             #
    # ------------------------------------------------------------------ #
    rq03_failures: list[str] = []
    inferred_kappa: dict[str, int] = {}

    for j_id, j_s in job_sol.items():
        if j_id not in job_by_id:
            continue
        nominal_dur = job_by_id[j_id]["duration"]
        I_j         = bool(job_by_id[j_id].get("interruptible", False))
        actual_dur  = j_s["finish"] - j_s["start"]
        extension   = actual_dur - nominal_dur

        if extension < -TOL:
            rq03_failures.append(
                f"Job {j_id}: duration {actual_dur:.4f} is below nominal {nominal_dur}."
            )
            inferred_kappa[j_id] = 0
            continue

        if delta <= 0:
            # No extensions possible; require exact match.
            if abs(extension) > TOL:
                rq03_failures.append(
                    f"Job {j_id}: delta=0 but duration extension is {extension:.4f}."
                )
            inferred_kappa[j_id] = 0
            continue

        k_float = extension / delta
        k_int   = int(round(k_float))
        if abs(k_int * delta - extension) > TOL:
            rq03_failures.append(
                f"Job {j_id}: extension {extension:.4f} is not an integer multiple "
                f"of delta={delta} (would require kappa={k_float:.4f})."
            )
            inferred_kappa[j_id] = 0
            continue

        if k_int < 0:
            rq03_failures.append(
                f"Job {j_id}: inferred negative kappa={k_int}."
            )
            k_int = 0

        if k_int > 0 and not I_j:
            rq03_failures.append(
                f"Job {j_id} is not interruptible (I_j=0) but its duration "
                f"implies kappa={k_int} > 0."
            )

        inferred_kappa[j_id] = k_int

    results["RQ03"] = {
        "pass":   not rq03_failures,
        "detail": (
            f"All {len(inferred_kappa)} job durations match D_j + delta * kappa_j "
            f"with kappa consistent with the interruptibility flag."
            if not rq03_failures else "; ".join(rq03_failures)
        ),
        "inferred_kappa": dict(inferred_kappa),
    }
    if rq03_failures:
        all_pass = False

    # ------------------------------------------------------------------ #
    #  RQ04 — earliest-start (hard) and target-finish (soft)              #
    # ------------------------------------------------------------------ #
    rq04_failures: list[str] = []
    rq04_delays:   list[str] = []
    for a in solution["aircraft"]:
        a_id = a["id"]
        if a_id not in aircraft_by_id:
            continue
        earliest = aircraft_by_id[a_id]["earliest_start"]
        target   = aircraft_by_id[a_id]["target_finish"]
        if a["start"] < earliest - TOL:
            rq04_failures.append(
                f"Aircraft {a_id}: starts at {a['start']:.2f}, before earliest_start={earliest}."
            )
        if a["finish"] > target + TOL:
            rq04_delays.append(
                f"Aircraft {a_id}: finishes at {a['finish']:.2f}, delay={a['delay']:.2f} (target_finish={target})."
            )

    results["RQ04"] = {
        "pass":   not rq04_failures,
        "detail": (
            "All earliest-start constraints satisfied."
            if not rq04_failures else "; ".join(rq04_failures)
        ) + (
            f" Delays (soft): {'; '.join(rq04_delays)}" if rq04_delays else ""
        ),
        "delays": rq04_delays,
    }
    if rq04_failures:
        all_pass = False

    # ------------------------------------------------------------------ #
    #  RQ05 — precedences                                                 #
    # ------------------------------------------------------------------ #
    rq05_failures: list[str] = []
    for (j_before, j_after) in precedences:
        if j_before not in job_sol or j_after not in job_sol:
            continue
        s_after  = job_sol[j_after]["start"]
        f_before = job_sol[j_before]["finish"]
        if s_after < f_before - TOL:
            rq05_failures.append(
                f"Precedence {j_before}→{j_after} violated: "
                f"{j_after} starts at {s_after:.2f} before {j_before} finishes at {f_before:.2f}."
            )

    results["RQ05"] = {
        "pass":   not rq05_failures,
        "detail": (
            f"All {len(precedences)} precedence relation(s) respected."
            if not rq05_failures else "; ".join(rq05_failures)
        ),
    }
    if rq05_failures:
        all_pass = False

    # ------------------------------------------------------------------ #
    #  RQ06 — no two jobs overlap at the same position                    #
    # ------------------------------------------------------------------ #
    rq06_failures: list[str] = []
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
            if not rq06_failures else "; ".join(rq06_failures)
        ),
    }
    if rq06_failures:
        all_pass = False

    # ------------------------------------------------------------------ #
    #  RQ07_v2 — three-mode access classification                         #
    #                                                                      #
    #  For each blocking arc (p_front, p_rear), each pair (r at p_front,  #
    #  rp at p_rear), and each access instant tau in {rp_start, rp_end}:  #
    #                                                                      #
    #    Mode A  : tau <= s_r - eta  OR  tau >= f_r + eta                 #
    #              -> no movement, no penalty                              #
    #    Mode B  : tau in [f_{j^r_k}, s_{j^r_{k+1}}] for some inter-job   #
    #              gap k of r                                              #
    #              -> +2 movements; gap must accommodate the cumulative   #
    #                 number of Mode-B events that use it (>= mu * count) #
    #    Mode C  : s_j + eta <= tau <= f_j - eta for some job j of r      #
    #              with I_j = 1                                            #
    #              -> +2 movements; counts towards kappa_j                 #
    #    None of the above (e.g. tau strictly inside a non-interruptible   #
    #    job, or in a gap shorter than the required cumulative mu):       #
    #              -> INFEASIBLE.                                          #
    # ------------------------------------------------------------------ #
    movements: list[dict] = []
    infeasibilities: list[dict] = []
    counted_mode_c: dict[str, int] = {j_id: 0 for j_id in job_sol}
    # gap_uses[(r_id, k)] = number of Mode-B events that go through the
    # k-th inter-job gap of r.  Used to verify the cumulative mu rule.
    gap_uses: dict[tuple[str, int], int] = {}

    for (p_front, p_rear) in blocking_arcs:
        front_aircraft = position_occupancy.get(p_front, [])
        rear_aircraft  = position_occupancy.get(p_rear,  [])

        for (r_id, r_start, r_finish) in front_aircraft:
            r_chain = chain_by_aircraft.get(r_id, [])
            # Job intervals [start, finish] in chain order
            job_intervals: list[tuple[str, float, float]] = []
            for jid in r_chain:
                j_s = job_sol[jid]
                job_intervals.append((jid, j_s["start"], j_s["finish"]))

            for (rp_id, rp_start, rp_finish) in rear_aircraft:
                if rp_id == r_id:
                    continue
                for access_side, tau in (("entry", rp_start), ("exit", rp_finish)):
                    mode = _classify_access(
                        tau, r_start, r_finish, job_intervals, job_by_id, eta,
                    )
                    if mode["kind"] == "A":
                        continue
                    elif mode["kind"] == "B":
                        gap_uses[(r_id, mode["gap_index"])] = (
                            gap_uses.get((r_id, mode["gap_index"]), 0) + 1
                        )
                        movements.append({
                            "type":                 access_side,
                            "mode":                 "B",
                            "blocker":              r_id,
                            "blocker_position":     p_front,
                            "blocked":              rp_id,
                            "blocked_position":     p_rear,
                            "blocking_arc":         [p_front, p_rear],
                            "trigger_time":         tau,
                            "gap_jobs":             [mode["gap_before"], mode["gap_after"]],
                            "movements_generated":  2,
                        })
                    elif mode["kind"] == "C":
                        counted_mode_c[mode["job_id"]] = (
                            counted_mode_c.get(mode["job_id"], 0) + 1
                        )
                        movements.append({
                            "type":                 access_side,
                            "mode":                 "C",
                            "blocker":              r_id,
                            "blocker_position":     p_front,
                            "blocked":              rp_id,
                            "blocked_position":     p_rear,
                            "blocking_arc":         [p_front, p_rear],
                            "trigger_time":         tau,
                            "interrupted_job":      mode["job_id"],
                            "movements_generated":  2,
                        })
                    else:  # "infeasible"
                        infeasibilities.append({
                            "type":              access_side,
                            "blocker":           r_id,
                            "blocked":           rp_id,
                            "blocking_arc":      [p_front, p_rear],
                            "trigger_time":      tau,
                            "reason":            mode["reason"],
                        })

    # Cumulative Mode-B gap check
    gap_violations: list[dict] = []
    for (r_id, k), n_uses in gap_uses.items():
        chain = chain_by_aircraft[r_id]
        jid_k    = chain[k]
        jid_k1   = chain[k + 1]
        gap_size = job_sol[jid_k1]["start"] - job_sol[jid_k]["finish"]
        required = mu * n_uses
        if gap_size + TOL < required:
            gap_violations.append({
                "blocker":     r_id,
                "gap_index":   k,
                "gap_jobs":    [jid_k, jid_k1],
                "gap_size":    gap_size,
                "n_accesses":  n_uses,
                "required":    required,
                "shortfall":   required - gap_size,
            })

    inferred_count = sum(m["movements_generated"] for m in movements)
    reported_count = solution.get("metrics", {}).get("movements", inferred_count)
    count_match    = inferred_count == reported_count

    rq07_failures: list[str] = []
    if infeasibilities:
        rq07_failures.append(
            f"{len(infeasibilities)} infeasible access(es) detected (non-interruptible "
            f"job blocked or no feasible window)."
        )
    if gap_violations:
        rq07_failures.append(
            f"{len(gap_violations)} Mode-B gap(s) too narrow for cumulative mu."
        )
    if not count_match:
        rq07_failures.append(
            f"Movement count mismatch: classification infers {inferred_count} movements "
            f"({len(movements)} event(s) × 2), but solution reports {reported_count}."
        )

    movements_sorted = sorted(movements, key=lambda m: m["trigger_time"])

    results["RQ07"] = {
        "pass":            not rq07_failures,
        "movements_count": inferred_count,
        "movements":       movements_sorted,
        "infeasibilities": infeasibilities,
        "gap_violations":  gap_violations,
        "detail": (
            f"{inferred_count} movement(s) from {len(movements)} blocking event(s) "
            f"(Mode A vacant front, Mode B inter-job gaps, Mode C interruptible jobs)."
            if not rq07_failures else "; ".join(rq07_failures)
        ),
    }
    if rq07_failures:
        all_pass = False

    # ------------------------------------------------------------------ #
    #  RQ08 — minimum separation between consecutive aircraft (epsilon)   #
    # ------------------------------------------------------------------ #
    rq08_violations: list[dict] = []
    min_gap: float | None = None
    for pos, occupants in position_occupancy.items():
        if len(occupants) < 2:
            continue
        sorted_occ = sorted(occupants, key=lambda x: x[1])
        for i in range(len(sorted_occ) - 1):
            r_id,  _, r_finish  = sorted_occ[i]
            rp_id, rp_start, _  = sorted_occ[i + 1]
            gap = rp_start - r_finish
            if min_gap is None or gap < min_gap:
                min_gap = gap
            if gap < epsilon - TOL:
                rq08_violations.append({
                    "position":  pos,
                    "first":     r_id,
                    "second":    rp_id,
                    "gap":       gap,
                    "shortfall": epsilon - gap,
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
                f"All consecutive same-position pairs separated by >= {epsilon} "
                f"(min gap = {min_gap:.2f})."
                if min_gap is not None
                else "No consecutive same-position pairs to check."
            )
            if rq08_pass else (
                f"{len(rq08_violations)} separation violation(s) detected "
                f"(epsilon={epsilon}, worst shortfall={worst_violation:.2f}, "
                f"min gap={min_gap:.2f})."
            )
        ),
    }
    if not rq08_pass:
        all_pass = False

    # ------------------------------------------------------------------ #
    #  RQ09 — kappa consistency between RQ03_v2 inference and RQ07_v2     #
    #         Mode-C event count                                          #
    # ------------------------------------------------------------------ #
    rq09_failures: list[str] = []
    for j_id, inferred in inferred_kappa.items():
        counted = counted_mode_c.get(j_id, 0)
        if inferred != counted:
            rq09_failures.append(
                f"Job {j_id}: duration implies kappa={inferred} but RQ07_v2 counts "
                f"{counted} Mode-C event(s) against it."
            )

    results["RQ09"] = {
        "pass":   not rq09_failures,
        "detail": (
            f"Per-job interruption counters consistent across {len(inferred_kappa)} job(s)."
            if not rq09_failures else "; ".join(rq09_failures)
        ),
    }
    if rq09_failures:
        all_pass = False

    return {
        "compliant":    all_pass,
        "requirements": results,
    }


# =============================================================================
#  Access classification helper
# =============================================================================

def _classify_access(
    tau: float,
    r_start: float,
    r_finish: float,
    job_intervals: list[tuple[str, float, float]],
    job_by_id: dict,
    eta: float,
) -> dict:
    """Classify an access instant *tau* against the blocker aircraft's stay.

    Parameters
    ----------
    tau : float
        Access instant of the rear aircraft (its start or finish).
    r_start, r_finish : float
        Aircraft-level start/finish of the front blocker.
    job_intervals : list of (job_id, start, finish)
        Ordered job intervals of the blocker (chain order, ascending by start).
    job_by_id : dict
        Instance-level lookup so we can read ``interruptible`` per job.
    eta : float
        Granularity used to enforce strict inequalities for Mode C and the
        "vacant-front" boundary of Mode A.

    Returns
    -------
    dict with key ``kind`` in {"A", "B", "C", "infeasible"} plus mode-specific
    fields:
        Mode A          : {"kind": "A"}
        Mode B          : {"kind": "B", "gap_index": int,
                            "gap_before": jid, "gap_after": jid}
        Mode C          : {"kind": "C", "job_id": jid}
        infeasible      : {"kind": "infeasible", "reason": str}
    """
    # Mode A: before the stay or after the stay (with eta strict margin so
    # that arrival/departure coincident with a job boundary on the front is
    # not silently treated as "outside")
    if tau <= r_start - eta + TOL:
        return {"kind": "A"}
    if tau >= r_finish + eta - TOL:
        return {"kind": "A"}

    # Mode C candidate: strictly inside some job of the blocker.
    # We use closed inequalities on the interior  [s_j + eta, f_j - eta].
    for (jid, j_start, j_finish) in job_intervals:
        if j_start + eta - TOL <= tau <= j_finish - eta + TOL:
            if bool(job_by_id.get(jid, {}).get("interruptible", False)):
                return {"kind": "C", "job_id": jid}
            return {
                "kind":   "infeasible",
                "reason": (
                    f"access at t={tau:.4f} falls inside non-interruptible job "
                    f"{jid} [{j_start:.4f}, {j_finish:.4f}]"
                ),
            }

    # Mode B candidate: in an inter-job gap of the blocker.
    for k in range(len(job_intervals) - 1):
        _, _, fk     = job_intervals[k]
        jk1_id, sk1, _ = job_intervals[k + 1]
        if fk - TOL <= tau <= sk1 + TOL:
            return {
                "kind":       "B",
                "gap_index":  k,
                "gap_before": job_intervals[k][0],
                "gap_after":  jk1_id,
            }

    # Boundary cases not picked up above: tau within [r_start - eta, r_start]
    # or within [r_finish, r_finish + eta].  Mark as Mode A: the access touches
    # the very edge of the stay but no manoeuvre is required because the front
    # aircraft is just entering / leaving its own slot.
    if r_start - eta <= tau <= r_start + TOL:
        return {"kind": "A"}
    if r_finish - TOL <= tau <= r_finish + eta:
        return {"kind": "A"}

    return {
        "kind":   "infeasible",
        "reason": (
            f"access at t={tau:.4f} cannot be classified into Mode A/B/C against "
            f"blocker stay [{r_start:.4f}, {r_finish:.4f}]"
        ),
    }


# =============================================================================
#  Pretty-printer
# =============================================================================

def print_check(report: dict, indent: int = 4) -> None:
    """Human-readable rendering of a paper-#2 ``check_solution`` report."""
    pad = " " * indent

    status = "COMPLIANT" if report["compliant"] else "NON-COMPLIANT"
    bar    = "=" * 60
    print(bar)
    print(f"  Solution Check (paper #2, jobs_v2) — Overall: {status}")
    print(bar)

    for rq_id, info in report["requirements"].items():
        mark = "PASS" if info["pass"] else "FAIL"
        print(f"\n[{mark}] {rq_id}")
        print(f"{pad}{info['detail']}")

        if rq_id == "RQ07":
            if info.get("infeasibilities"):
                print(f"{pad}Infeasibilities:")
                for ev in info["infeasibilities"]:
                    print(
                        f"{pad}  - {ev['type']} of {ev['blocked']} vs blocker "
                        f"{ev['blocker']} at t={ev['trigger_time']:.2f}: "
                        f"{ev['reason']}"
                    )
            if info.get("gap_violations"):
                print(f"{pad}Mode-B gap shortfalls:")
                for gv in info["gap_violations"]:
                    print(
                        f"{pad}  - blocker {gv['blocker']} gap between "
                        f"{gv['gap_jobs'][0]} and {gv['gap_jobs'][1]}: "
                        f"size={gv['gap_size']:.2f}, required>={gv['required']:.2f} "
                        f"(shortfall {gv['shortfall']:.2f})"
                    )
            for i, m in enumerate(info.get("movements", []), start=1):
                extra = (
                    f", job={m.get('interrupted_job')}"
                    if m.get("mode") == "C" else
                    f", gap=[{m['gap_jobs'][0]}, {m['gap_jobs'][1]}]"
                    if m.get("mode") == "B" else ""
                )
                print(
                    f"{pad}  [{i}] {m['type']} t={m['trigger_time']:.2f} "
                    f"Mode {m['mode']}{extra}  (+2 movements)"
                )

        if rq_id == "RQ04" and info.get("delays"):
            for d in info["delays"]:
                print(f"{pad}  ! {d}")

        if rq_id == "RQ08" and info.get("violations"):
            for v in info["violations"]:
                print(
                    f"{pad}  Position {v['position']}: "
                    f"{v['first']} → {v['second']}  "
                    f"gap={v['gap']:.2f}  shortfall={v['shortfall']:.2f}"
                )

    print(f"\n{bar}")
    print(f"  Hard requirements: {'all passed' if report['compliant'] else 'ONE OR MORE FAILED'}")
    print(bar)


# =============================================================================
#  CLI
# =============================================================================

if __name__ == "__main__":
    import json
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "input_data"))
    from instance_io import load_json as load_instance  # noqa: E402

    if len(sys.argv) != 3:
        print(
            "Usage: python check_solution_jobs_v2.py <instance_path> <solution_json_path>",
            file=sys.stderr,
        )
        sys.exit(1)

    raw_instance = load_instance(sys.argv[1])
    with open(sys.argv[2], "r", encoding="utf-8") as fh:
        raw_solution = json.load(fh)

    print_check(check_solution(raw_solution, raw_instance))
