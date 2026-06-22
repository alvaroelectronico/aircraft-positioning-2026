"""BRKGA v02 solving method (Claude-assisted, Candidate C).

Biased Random-Key Genetic Algorithm with a mixed-chromosome decoder
(indicator keys for position assignment + permutation keys for job
sequencing).  Implements **Candidate C** of the literature synthesis
that originated under the `theory_assisted` scaffold.

**Assistance**: developed by the human with Claude (Anthropic) as
coding assistant.  See ``PROVENANCE.md`` for the full development
history.

Parallel to ``methods/iterated_greedy_vnd_v02/`` (also Claude-assisted,
also from the `theory_assisted` scaffold but implementing Candidate A
instead).  The two together exhaust two of the four candidates from
the synthesis (A and C); B (GRASP+VND+PR) and D (matheuristic
GRASP+LB) remain for future attempts.

Visibility (enforced by ``experiments/tests/test_method_isolation.py``
plus the per-directory ``CLAUDE.md``):

    MAY read:    problems/<paper>/, shared/,
                 methods/brkga_v02/ (own code + docs).
    MAY NOT read: methods/manual/, methods/autoresearch/,
                  methods/iterated_greedy_vnd_v01/,
                  methods/iterated_greedy_vnd_v02/,
                  methods/theory_assisted/ (the scaffold reset for
                  the next attempt).
"""
