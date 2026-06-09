# Aircraft positioning problem (paper #1, aircraft-level)

## Overall description

The aircraft positioning problem consists of scheduling a set of
maintenance jobs over a continuous time horizon while assigning
aircraft to hangar positions.

A hangar is modelled as a directed acyclic graph $G = (P, A)$, where
$P = \{p_1, \dots, p_P\}$ is the finite set of **maintenance positions**
and $A \subseteq P \times P$ is the set of **blocking arcs**.  An arc
$(p, p') \in A$ means that position $p$ (the *front*) physically blocks
access to position $p'$ (the *rear*): an aircraft at position $p'$
cannot enter or leave the hangar without temporarily displacing the
aircraft at position $p$.  The **blocking load** of a position is

$$
\ell(p) = |\{q \in P : p \text{ can reach } q \text{ in } G\}|,
$$

so a higher blocking load means that aircraft at $p$ can obstruct more
other positions.

Each blocking arc induces movements:

- An **entry movement** whenever an aircraft arrives at the rear
  position while another aircraft is being serviced at the front.
- An **exit movement** whenever an aircraft departs from the rear
  while another aircraft is still at the front.

Each movement contributes 2 to the movement count (the displacement of
the front aircraft and its return).

## Aircraft

Let $R = \{r_1, \dots, r_R\}$ be the fleet of aircraft.  Each aircraft
$r \in R$ requires a fixed amount of maintenance work of total
**duration** $D_r > 0$, which is treated as atomic: while $r$ occupies
a position, the position is busy for exactly $D_r$ time units in a
single uninterrupted block.  In practice the work is a sequence of
jobs whose individual timings can be reconstructed deterministically
once the aircraft start time is known; this aircraft-level problem
aggregates them because makespan, delay, and blocking interactions
depend only on the per-aircraft block.

Each aircraft has an **earliest start** $E_r \ge 0$ before which work
cannot begin, and a **target finish** $L_r > E_r$ beyond which
completion incurs delay.

## Assumptions

- Aircraft movements are considered instantaneous and do not consume
  schedulable time.
- The towing parameter $\varepsilon > 0$ is the time needed to tow an
  aircraft in or out of a position.  It plays two roles with the same
  physical meaning: the minimum separation between two consecutive
  aircraft serviced at the same position, and the margin in the
  blocking-arc access conditions.  Throughout, time is measured in
  days and a typical value is $\varepsilon = 0.5$ days.  The value is
  recorded in every instance file.

## Decisions

A solution makes two coupled decisions:

- **Assignment**: send each aircraft $r$ to exactly one position
  $\pi(r) \in P$.
- **Scheduling**: fix a start time $s_r \ge 0$ for every aircraft;
  the finish time follows as $f_r = s_r + D_r$.

## Requirements

- **RQ01** — Every aircraft is assigned to exactly one position:

  $$
  \textstyle\sum_{p \in P} \mathbf{1}[\pi(r) = p] = 1 \qquad \forall r \in R.
  $$

- **RQ02** — A position handles its aircraft sequentially with
  separation $\varepsilon$: for $r \ne r'$ with $\pi(r) = \pi(r')$,

  $$
  [s_r, f_r] \cap [s_{r'}, f_{r'}] = \emptyset \text{ and the gap is at least } \varepsilon.
  $$

- **RQ03** — Each aircraft respects its earliest-start time window,
  $s_r \ge E_r$.

- **RQ04** — Blocking-arc access conditions.  For every arc
  $(p, p') \in A$ and every pair of aircraft $r, r'$ with $\pi(r) = p$
  and $\pi(r') = p'$:

  - An **entry movement** is incurred when $s_r \le s_{r'} \le f_r - \varepsilon$.
  - An **exit movement** is incurred when $s_r \le f_{r'} \le f_r - \varepsilon$.

  Each event triggers a temporary displacement of the front aircraft
  and counts as 2 movements (out + back).

## Objective

The objective is a weighted combination of three criteria:

$$
\min \;\; W^M \cdot m + W^D \sum_{r \in R} v^D_r + W^S \cdot n,
$$

where

- $m = \max_{r \in R} f_r$ is the **makespan**,
- $v^D_r = \max(0,\, f_r - L_r)$ is the **delay** of aircraft $r$,
- $n$ counts the **blocking movements** induced by the access conditions,
- $W^M, W^D, W^S \ge 0$ are user-defined weights.

The default weight profile used in the benchmark is
$(W^M, W^D, W^S) = (0.1,\, 1.0,\, 10)$, encoding the operational
priority order **movements ≻ delay ≻ makespan**.  Two alternative
profiles are also of interest for sensitivity studies: delay-priority
$(1, 10, 0.1)$ and makespan-priority $(10, 0.1, 1)$.

## Complexity

The problem is NP-hard: it subsumes the single-machine
weighted-completion-time scheduling problem with arbitrary release
dates, which is itself NP-hard.  The position-assignment layer and the
blocking-arc constraints further enlarge the search space.

## Inputs / outputs (operational contract)

A solving method consumes an instance JSON from
`problems/aircraft/instances/` (schema in
[`instance_schema.json`](instance_schema.json)).  It produces a
solution dict that must pass the compliance checker in
[`checker.py`](checker.py).  Both interfaces are stable and shared
across every solving method.
