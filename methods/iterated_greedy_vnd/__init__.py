"""Iterated Greedy + VND solving method.

Originated from the `theory_assisted` literature-informed process (see
``jobs/synthesis.md`` and ``jobs/design.md``) and graduated to its own
isolated method once the implementation matured.

Visibility (enforced by ``experiments/tests/test_method_isolation.py``
plus the per-directory ``CLAUDE.md``):

    MAY read:    problems/<paper>/, shared/,
                 methods/iterated_greedy_vnd/ (own code + docs).
    MAY NOT read: methods/manual/, methods/autoresearch/,
                  methods/theory_assisted/ (other methods, including
                  the digest/ + inspiration/ folders that informed
                  THIS method's design — they are out of scope now
                  that the method is mature).
"""
