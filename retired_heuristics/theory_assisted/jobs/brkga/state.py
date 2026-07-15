"""Schedule data structures produced by the decoder.

Kept separate from ``decoder.py`` so the decoder stays small and the state is
easy to inspect when comparing against ``problems/jobs/checker.py``.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class JobState:
    job_id: str
    start: float
    finish: float
    duration: float          # nominal D_j
    interruptible: bool
    kappa: int = 0           # number of Mode-C pauses (0 in v0)


@dataclass
class AircraftState:
    aircraft_id: str
    position: str
    start: float             # aircraft-level start = first job start
    finish: float            # aircraft-level finish = last job finish
    jobs: list[JobState]


@dataclass
class ScheduleState:
    aircraft: dict[str, AircraftState] = field(default_factory=dict)
    by_position: dict[str, list[str]] = field(default_factory=dict)
    movements: int = 0
    infeasible_accesses: int = 0
