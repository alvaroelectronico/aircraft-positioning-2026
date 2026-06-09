"""Paper #2: job-level extension of the aircraft positioning problem.

Adds per-aircraft job chains, interruptibility flags, and the
three-mode (A/B/C) access semantics on blocking arcs.  Self-contained.
Read ``problem_statement.md`` for the operational and formal
description; ``checker.py`` enforces all RQs including the
mode-classification of every access instant.
"""
