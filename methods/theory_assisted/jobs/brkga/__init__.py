"""BRKGA (Candidate C) implementation for the theory_assisted method, paper #2.

Second independent Claude-assisted attempt at the mixed-chromosome BRKGA
decoder.  Developed in isolation from any other method (see
``methods/theory_assisted/CLAUDE.md``).

Modules
-------
instance   : normalise the instance JSON into an internal Model.
state      : schedule data structures (JobState / AircraftState / ScheduleState).
windows    : pure interval-set algebra (intersect / shift / first-point).
access     : Mode-A/B/C access semantics, faithful to problems/jobs/checker.py.
decoder    : chromosome -> deterministic feasible schedule -> solution dict.
warm_start : greedy/NEH seed + reverse-encoding (Hito 2).
engine     : self-contained BRKGA evolutionary loop (Hito 2).
smoke      : random-chromosome smoke test against the checker.
"""
