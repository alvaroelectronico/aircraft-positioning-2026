"""Iterated Greedy + VND solving method (v02, Claude-assisted).

Second LLM-assisted attempt on paper #2.  Iterates from the same
30e1af0 IGVND baseline as the frozen v01 (ChatGPT-assisted) and
evolves it under the same `theory_assisted` scaffold but with Claude
as the LLM assistant.  Once mature, it graduated to its own isolated
method directory (this one).

**Assistance**: developed by the human with Claude (Anthropic) as
coding assistant.  See ``PROVENANCE.md`` for the full development
history (Mode-C / κ-fixpoint decoder, Mode-B inter-job gaps,
interval-caching decode-speed refactor, light-objective fast path,
incremental zero-decode in the VND, …).

Visibility (enforced by ``experiments/tests/test_method_isolation.py``
plus the per-directory ``CLAUDE.md``):

    MAY read:    problems/<paper>/, shared/,
                 methods/iterated_greedy_vnd_v02/ (own code + docs).
    MAY NOT read: methods/manual/, methods/autoresearch/,
                  methods/iterated_greedy_vnd_v01/ (sister attempt
                  with a different LLM assistant — kept blind for
                  apples-to-apples comparison),
                  methods/theory_assisted/ (the scaffold reset for
                  the next attempt).
"""
