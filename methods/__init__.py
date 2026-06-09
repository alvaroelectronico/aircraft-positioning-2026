"""Solving methods — one subpackage per approach.

Each method (``manual``, ``autoresearch``, …) is quarantined: it may
import from ``problems.<paper>`` and ``shared`` only, never from
``methods.<other_method>``.  The single bridge across methods is
``experiments/run_experiments.py``.
"""
