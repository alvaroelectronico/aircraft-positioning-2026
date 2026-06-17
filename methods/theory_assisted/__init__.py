"""Theory-assisted solving method.

Defining feature: this method is informed by external scheduling and OR
theory that the human curates into ``methods/theory_assisted/inspiration/``.
It is structurally isolated from the implementations of
``methods/manual/`` and ``methods/autoresearch/`` and does NOT consume
the repo-wide ``literature_review/`` either — only the curated
``inspiration/`` folder.

Visibility (enforced by ``experiments/tests/test_method_isolation.py``
and reinforced by per-directory CLAUDE.md instructions):

    MAY read:    problems/<paper>/, shared/,
                 methods/theory_assisted/ (own code, own inspiration,
                 own digests).
    MAY NOT read: literature_review/, methods/manual/,
                  methods/autoresearch/, methods/iterated_greedy_vnd_v01/,
                  methods/iterated_greedy_vnd_v02/, papers/,
                  papers/_legacy_draft/.

Rationale: a new method starts from a clean slate.  Curated theory is
the defining input (and the human controls what enters scope by what
they place in inspiration/).  Other methods' implementations are out
of scope, because the goal is to compare independent attacks on the
same problem.
"""
