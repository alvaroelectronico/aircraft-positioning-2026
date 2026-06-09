# Aircraft positioning with job-level scheduling (paper #2)

## Operational overview

A maintenance hangar consists of a finite number of parking positions
arranged in space.  Because of the physical geometry of the facility,
some positions are **rear** positions whose only access path runs
across one or more **front** positions.  An aircraft parked at a front
position therefore physically obstructs the entry and exit of any
aircraft at the rear positions behind it.  Whenever a rear-position
aircraft has to enter or leave the hangar while a front aircraft is
being serviced, the front aircraft must be temporarily towed out of
the way and returned to its slot once the manoeuvre is complete.
Each such manoeuvre is operationally expensive: it occupies the ground
crew, interrupts service, and carries a non-negligible risk of damage.

A fleet of aircraft must be serviced in the hangar over a planning
horizon.  For each aircraft the airline specifies the work to be
performed, an earliest date on which work can start, and a target date
by which it should be finished; finishing later than the target incurs
a delay cost that the operator wants to minimise.  The work itself is
an ordered list of **jobs** with known individual durations and a
strict chain of precedences: a job cannot start until its predecessor
has finished.  Each job is also tagged as either **interruptible**,
meaning the ground crew can pause it briefly to clear the way for a
neighbouring movement and resume it shortly afterwards, or
**non-interruptible**, meaning it must run from start to finish without
external disturbance.

A schedule consists of two decisions per aircraft: which position to
assign it to, and when to start each of its jobs.  Two aircraft sharing
a position must be serviced one after the other.  An aircraft assigned
to a rear position can always enter or leave when the relevant front
position is unoccupied at that instant.  When the front position is
occupied, only two situations make the manoeuvre possible:

1. The front aircraft is between two consecutive jobs and the gap is
   wide enough to absorb the tow-out and tow-back.
2. The front aircraft is mid-job and that job is interruptible, in
   which case the job is paused, the manoeuvre is performed, and the
   job is resumed at the cost of some additional working time.

Any other attempt to access the rear position is operationally
infeasible.  The schedule must satisfy all of the above and minimise a
weighted combination of makespan, total delay, and number of
manoeuvres.

## Formal definition

The hangar is modelled as a directed acyclic graph $G = (P, A)$ where
$P = \{p_1, \dots, p_P\}$ is the set of parking positions and
$A \subseteq P \times P$ is the set of **blocking arcs**: an arc
$(p, p') \in A$ means that position $p$ (the *front*) obstructs the
access path to position $p'$ (the *rear*).

Let $R = \{r_1, \dots, r_R\}$ be the fleet of aircraft to be serviced.
Each aircraft $r \in R$ carries an ordered chain of jobs

$$
J_r = (j^r_1, j^r_2, \ldots, j^r_{N_r}),
$$

in which $j^r_{k+1}$ may only start after $j^r_k$ has finished.  Let
$J = \bigcup_{r \in R} J_r$ be the global job set.  Each job $j \in J$
has a nominal duration $D_j > 0$ and an interruptibility flag

$$
I_j \in \{0, 1\}, \qquad I_j = 1 \iff j \text{ is interruptible.}
$$

The aggregate processing time of aircraft $r$ is $T_r = \sum_{j \in J_r} D_j$.
Each aircraft has an earliest start $E_r \ge 0$ and a target finish
$L_r > E_r$.

Four positive temporal parameters complete the instance:

- $\varepsilon$ — the towing time of an aircraft into or out of a
  parking slot.  Used as the minimum separation between two
  consecutive aircraft serviced at the same position.
- $\mu$ — the minimum inter-job pause that must be left between two
  consecutive jobs of an aircraft when a neighbouring access manoeuvre
  takes place during that pause.  In its absence the gap may be zero.
- $\delta$ — the additional working time added to an interruptible
  job each time it is paused to allow a neighbouring access manoeuvre.

All three parameters are specified per instance.

## Variables and basic constraints

A solution assigns each aircraft $r \in R$ to exactly one position
$\pi(r) \in P$, and fixes a start time $s_j \ge 0$ for every job
$j \in J$.  The finish time of a job is

$$
f_j = s_j + D_j + \delta \cdot \kappa_j,
$$

where $\kappa_j \in \mathbb{N}_{\ge 0}$ counts how many times job $j$
was paused during its execution to enable a neighbouring access
manoeuvre.  Note $\kappa_j > 0$ requires $I_j = 1$.

Job-level start and finish times induce aircraft-level start and
finish times $s_r = s_{j^r_1}$ and $f_r = f_{j^r_{N_r}}$, and the
per-aircraft delay $v^D_r = \max(0,\, f_r - L_r)$.

The basic feasibility requirements are:

$$
\begin{aligned}
&\textstyle\sum_{p \in P} \mathbf{1}[\pi(r) = p] = 1 && \forall r \in R, \\
&s_{j^r_{k+1}} \ge f_{j^r_k} && \forall r \in R,\ k = 1, \ldots, N_r - 1, \\
&s_r \ge E_r && \forall r \in R, \\
&[s_r, f_r] \cap [s_{r'}, f_{r'}] = \emptyset \text{ and the gap} \ge \varepsilon && \forall r \ne r' \text{ with } \pi(r) = \pi(r').
\end{aligned}
$$

The first equation enforces that every aircraft is assigned to exactly
one position; the second chains each aircraft's jobs in the prescribed
order; the third respects the earliest start; and the fourth forbids
overlapping occupancies at the same position and leaves at least
$\varepsilon$ time units between the finish of one aircraft and the
start of the next.

## Access conditions on blocked positions

Consider any arc $(p, p') \in A$ and an aircraft $r'$ assigned to the
rear position $p' = \pi(r')$.  Its two **access instants** are the
entry $\tau = s_{r'}$ and the exit $\tau = f_{r'}$.  Each of these
instants must fall into exactly one of three modes, depending on the
state of the front position $p$ at time $\tau$.

### Mode (A) — front position vacant at $\tau$

If no aircraft is being serviced at $p$ at time $\tau$ — formally, no
aircraft $r$ with $\pi(r) = p$ satisfies $s_r \le \tau \le f_r$ — the
access requires no manoeuvre and incurs no extra time and no movement
count.

### Mode (B) — front aircraft mid-stay, $\tau$ in an inter-job gap

If there exists an aircraft $r$ with $\pi(r) = p$ such that $\tau$
falls between two consecutive jobs $j^r_k$ and $j^r_{k+1}$ of $r$, i.e.

$$
f_{j^r_k} \le \tau \le s_{j^r_{k+1}},
$$

then $r$ is towed out, $r'$ accesses $p'$, and $r$ is towed back.
The gap must be wide enough to accommodate the manoeuvre:

$$
s_{j^r_{k+1}} - f_{j^r_k} \ge \mu
\quad \text{whenever any access instant uses this gap.}
$$

The event contributes 2 to the movement count (tow-out plus tow-back)
and does not extend any job.

### Mode (C) — front aircraft mid-job, job interruptible

If there exists an aircraft $r$ with $\pi(r) = p$ such that $\tau$
falls strictly within the execution of some job $j^r_k$ of $r$, i.e.

$$
s_{j^r_k} < \tau < f_{j^r_k},
$$

the access is feasible only if $I_{j^r_k} = 1$.  In that case
$j^r_k$ is paused, the manoeuvre is performed, $j^r_k$ resumes, and
the counter $\kappa_{j^r_k}$ is incremented by 1.  The event
contributes 2 to the movement count.

### Infeasibility

If the Mode-C window condition holds but $I_{j^r_k} = 0$, the access
instant $\tau$ is infeasible: the schedule must either retime $r'$ so
that $\tau$ falls into Mode (A) or Mode (B), or reassign $r'$ to a
different position.

### Independence of entry and exit

The mode of the entry $s_{r'}$ and the mode of the exit $f_{r'}$ are
determined independently, against potentially different front aircraft
and different jobs.  Each contributes its own movement count and, in
Mode (C), its own increment of $\kappa$.

## Objective

Let $m = \max_{r \in R} f_r$ be the makespan and let $n$ be the total
number of movements summed over all blocking arcs and aircraft pairs.
The objective is the weighted combination

$$
\min \;\; W^M \cdot m + W^D \sum_{r \in R} v^D_r + W^S \cdot n,
$$

where $W^M, W^D, W^S \ge 0$ are user-specified weights expressing the
relative priority of throughput, on-time delivery, and ground-crew
effort.  The default weight profile used in the benchmark is
$(W^M, W^D, W^S) = (0.1,\, 1.0,\, 10)$, encoding the operational
priority order **movements ≻ delay ≻ makespan**.

## Complexity

The problem is NP-hard: even without blocking arcs it contains the
single-machine scheduling problem with arbitrary release dates and
weighted completion times.  The blocking access conditions above
further enlarge the combinatorial structure.

## Inputs / outputs (operational contract)

A solving method consumes an instance JSON from
`problems/jobs/instances/` (schema in
[`instance_schema.json`](instance_schema.json)).  It produces a
solution dict that must pass the compliance checker in
[`checker.py`](checker.py).  The checker enforces all RQs including
the per-access mode classification described above and the consistency
of $\kappa_j$ with the inferred Mode-C events.
