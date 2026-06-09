"""Cross-method, cross-problem infrastructure.

Anything here is fair game for every solving method to import:
  - ``application``: the ``Application`` dispatcher used to plug a
    solver into the read-data / configure / solve / check pipeline.
  - ``instance_io``: the canonical JSON instance loader.
  - ``rcl``: GRASP RCL helpers (``_grasp_weights``,
    ``_biased_random_select_logged``) shared between constructive
    heuristics across both problems.
  - ``plotting``: Gantt-chart rendering.

This package must not import from ``methods/`` or ``papers/``.
"""
