"""Iterated Greedy + VND solving method (v01, ChatGPT-assisted).

First version of an IG+VND attack on paper #2.  Originated from the
`theory_assisted` literature-informed process (see ``jobs/synthesis.md``
and ``jobs/design.md``) and graduated to its own isolated method once
the implementation matured.

**Assistance**: developed by the human with ChatGPT (GPT-4-class
model) as coding assistant.  See ``PROVENANCE.md`` for the full record.

A parallel attempt is starting at the time of this writing under the
same `theory_assisted` scaffold but with Claude as the assistant —
that work will land in its own method directory (v02) once mature, so
the two LLM-assisted developer workflows can be compared head-to-head
on identical theory inputs.

Visibility (enforced by ``experiments/tests/test_method_isolation.py``
plus the per-directory ``CLAUDE.md``):

    MAY read:    problems/<paper>/, shared/,
                 methods/iterated_greedy_vnd_v01/ (own code + docs).
    MAY NOT read: methods/manual/, methods/autoresearch/,
                  methods/iterated_greedy_vnd_v02/ (the sibling
                  Claude-assisted attempt from the same baseline —
                  reading it contaminates the v01-vs-v02 comparison),
                  methods/theory_assisted/ (the scaffold reused for
                  future attempts), and any other future methods.
"""
