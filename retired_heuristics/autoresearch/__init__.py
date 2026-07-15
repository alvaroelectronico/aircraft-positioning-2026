"""Autoresearch method — LLM-iterative improvement loop.

Each iteration the LLM proposes a code modification to a designated
"working copy" solver, the harness scores it on a fixed benchmark, and
the variant is kept only if it strictly improves the metric.  Organised
per problem under ``aircraft/`` and ``jobs/``.
"""
