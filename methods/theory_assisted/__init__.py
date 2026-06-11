"""Theory-assisted solving method.

Defining feature: this method is informed by external scheduling and OR
literature (``literature_review/``) but is structurally isolated from
the implementations of ``methods/manual/`` and ``methods/autoresearch/``.

Visibility (enforced by ``experiments/tests/test_method_isolation.py``
and reinforced by per-directory CLAUDE.md instructions):

    MAY read:    problems/<paper>/, shared/, literature_review/,
                 methods/theory_assisted/ (own code).
    MAY NOT read: methods/manual/, methods/autoresearch/, papers/,
                  papers/_legacy_draft/.

Rationale: a new method starts from a clean slate.  External literature
is fair game (that is the point of the method).  Other methods'
implementations are not, because the goal is to compare independent
attacks on the same problem.
"""
