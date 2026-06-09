"""Problem definitions — one subpackage per problem.

Each subpackage owns the problem statement, instance schema, instance
loader, compliance checker, and instance JSON files for that problem.
This package is on the import path of every solving method; it must not
import from ``methods/`` or ``papers/``.
"""
